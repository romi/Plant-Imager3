#!/usr/bin/env python3
"""Launch dummy cameras + PlantDB + controller (DummyCNC) and prepare GUI in CONFIGURED state.

Spawns:
 - 2 dummy cameras (plantimager.commons.examples.cameraserver)
 - 1 PlantDB FSDB --test --empty
 - 1 controller app (plantimager.controller.main --allow-dummy-cnc)

Then connects via RPCController (webui) to configure an interval timelapse
30s × 5 and leaves GUI at CONFIGURED 0/5 (pencil+ok) waiting for operator
to start via WebUI start_timelapse() (no args, recomputed at arm).

Images: PI3_CAMERASERVER_IMAGE or real_plant fallback.
Run with plain `python` per docs.
"""

import gc
import os
import signal
import subprocess
import sys
import time
import tomllib

import zmq
from plantdb.client.plantdb_client import PlantDBClient
from plantdb.commons.auth.models import Permission
from plantdb.commons.test_database import get_test_dataset

from plantimager.webui.controller_proxy import RPCController


def _images_path():
    p = os.getenv("PI3_CAMERASERVER_IMAGE")
    if p and os.path.isdir(p):
        return p
    try:
        return str(get_test_dataset("real_plant") / "images")
    except Exception:
        return None


def _kill(proc):
    if proc and proc.poll() is None:
        try:
            proc.send_signal(signal.SIGINT)
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def main():
    images_path = _images_path()
    if not images_path:
        print("No images found (PI3_CAMERASERVER_IMAGE or real_plant)", file=sys.stderr)
        sys.exit(1)
    print(f"images: {images_path}")

    db_port = int(os.getenv("PI3_DB_PORT", "23656"))
    db_url = f"http://localhost:{db_port}"
    rpc_addr = os.getenv("PI3_RPC_ADDR", "tcp://localhost:14567")

    camera_env = os.environ.copy()
    camera_env["PI3_CAMERASERVER_IMAGE"] = images_path
    camera_env["PI3_CAMERASERVER_LAG"] = "100"
    # ensure DummyCNC for controller
    os.environ["PI3_ALLOW_DUMMY_CNC"] = "1"

    cameras = []
    plantdb = None
    controller = None
    ctx = None
    try:
        print("[spawning] 2 cameras...")
        cameras = [
            subprocess.Popen([sys.executable, "-m", "plantimager.commons.examples.cameraserver"], env=camera_env)
            for _ in range(2)
        ]
        print("[spawning] PlantDB...")
        plantdb = subprocess.Popen(
            ["fsdb_rest_api", "--test", "--empty", "--host", "localhost", "--port", str(db_port)],
            env=os.environ,
        )
        print("[spawning] controller --allow-dummy-cnc...")
        controller = subprocess.Popen([sys.executable, "-m", "plantimager.controller.main", "--allow-dummy-cnc"], env=os.environ)

        time.sleep(5)

        ctx = zmq.Context()
        print("--> RPC connect", rpc_addr)
        rpc = RPCController(ctx, rpc_addr)
        print("<-- connected")

        # wait for cameras
        for _ in range(120):
            try:
                names = rpc.camera_names
            except Exception:
                names = []
            print(f"  cameras: {names}")
            if len(names) >= 2:
                break
            time.sleep(0.5)
        else:
            print("Timeout waiting for cameras", file=sys.stderr)
            sys.exit(1)

        # DB setup
        db_client = PlantDBClient(db_url)
        db_client.login("admin", "admin")
        base_name = os.getenv("PI3_TIMELAPSE_BASE", "dummy_tl")
        rpc.set_db_url(db_url)
        rpc.set_base_name(base_name)

        # load scan config (now includes timelapse example)
        config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../src/webui/plantimager/webui/assets/config_scan.toml"))
        with open(config_path, "rb") as f:
            conf = tomllib.load(f)
        conf["ScanPath"]["kwargs"]["n_points"] = 4
        for cam_name in rpc.camera_names:
            conf[cam_name] = conf["picamera"].copy()
        rpc.set_config(conf)

        snap = rpc.config_timelapse(conf)
        print(f"CONFIGURED {snap['state']} {snap['next_idx']}/{len(snap['schedule_times'])} next={snap['schedule_times'][0] if snap['schedule_times'] else '-'}")
        # Long-lived token covering the whole span: a single glob entry
        # ({base}* matches the container and every base_N scan). Issued now
        # (post-Configure, schedule known) so the first scan never races it.
        from datetime import datetime
        sched = snap["schedule_times"]
        span = 0.0
        if len(sched) >= 2:
            span = max(0.0, (datetime.fromisoformat(sched[-1]) - datetime.fromisoformat(sched[0])).total_seconds())
        token_exp = int(span + snap.get("grace_period", 120) + 24 * 3600)
        api_token = db_client.create_api_token(
            token_exp,
            {f"{base_name}*": (Permission.WRITE, Permission.CREATE, Permission.READ)},
        )
        rpc.set_api_token(api_token)
        print(f"API token valid ~{token_exp // 3600}h for '{base_name}*'.")
        n = len(snap['schedule_times'])
        print(f"GUI should show CONFIGURED 0/{n} (pencil+ok). Start via WebUI start_timelapse() with no args.")
        print("Waiting for operator to start… Ctrl+C to discard and exit.")

        try:
            while True:
                snap = rpc.get_active_timelapse()
                if snap and snap["state"] != "configured":
                    print(f"State now {snap['state']} — operator started, waiting for completion or Ctrl+C…")
                    # keep running until terminal or interrupt
                    while True:
                        s = rpc.get_active_timelapse()
                        if not s or s["state"] in ("completed", "failed", "cancelled"):
                            print(f"Timelapse {s['state'] if s else 'none'} — exiting wait.")
                            break
                        time.sleep(1)
                    break
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nInterrupted — discarding draft…")
            try:
                rpc.cancel_timelapse()
                print("Discarded to IDLE")
            except Exception as exc:
                print(f"cancel failed: {exc}", file=sys.stderr)

    finally:
        print("[cleanup] stopping subprocesses…")
        gc.collect()
        for cam in cameras:
            _kill(cam)
        _kill(plantdb)
        _kill(controller)
        if ctx is not None:
            try:
                ctx.term()
            except Exception:
                pass
        # reset singleton for next run in same process
        try:
            RPCController._instance = None
        except Exception:
            pass
        print("done")


if __name__ == "__main__":
    main()
