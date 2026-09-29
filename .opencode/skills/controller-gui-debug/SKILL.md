---
name: controller-gui-debug
description: Use when visually verifying the Plant-Imager3 controller app (PlantImagerApp QML) — full dummy stack or MCP-only launch, RPC state prep, tiered checks (graph → region crop → fullscreen). Triggers on controller GUI, verify badge, TimelapsePanel, visual check, gui debug, CONFIGURED check.
---

# Controller GUI Debug (Plant-Imager3)

Visual verification for the controller touch app (800×480) via `py-qml-mcp`
plus RPC state prep. Load the `py-qml-mcp` skill too — this file only adds
the project-specific environment, launch modes, and check discipline.

## 1. Environment prep

Conda env is `plant-imager`; the MCP target python must have `pi_qml_mcp`
importable (`pip install -e /home/arthur/dev/py-qml-mcp --no-deps` if the
child dies with `No module named 'pi_qml_mcp'`).

```bash
PI3_ALLOW_DUMMY_CNC=1   # DummyCNC backend (or --allow-dummy-cnc argv)
DISPLAY=:1              # Xvfb headed display (offscreen hides exposure bugs)
PI3_CAMERASERVER_IMAGE  # or real_plant fallback via get_test_dataset
PI3_CAMERASERVER_LAG=100
PI3_DB_PORT=23656 PI3_RPC_ADDR=tcp://localhost:14567 PI3_TIMELAPSE_BASE=dummy_tl
```

One RPC binder at a time on `14567` — an MCP-launched controller and a
`Popen`-launched one conflict (`ZMQError: address in use`).

## 2. Launch modes

### (a) Full dummy stack, controller under MCP (preferred for agents)

Launch the controller **first** via `launch_app` (Main takes 5–30s;
warms QML cache while the rest spawns):

```
launch_app(app="plantimager.controller.main:main", args="--allow-dummy-cnc",
  cwd=<repo>, env={PI3_ALLOW_DUMMY_CNC:1, DISPLAY:":1"},
  python=".../miniconda3/envs/plant-imager/bin/python", idle_timeout=600)
```

In parallel (bash): 2× `python -m plantimager.commons.examples.cameraserver`
with the camera env, plus `fsdb_rest_api --test --empty --host localhost
--port $PI3_DB_PORT`. Join gates before any `set_config`: Main 800×480
visible (`health` → `windowList`, or `wait_for_idle`) **and**
`rpc.camera_names >= 2` (poll 120×0.5s).

DB wiring: `login("admin","admin")`, per-`base_name` API token
(`WRITE,CREATE,READ`), `set_api_token/set_db_url/set_base_name`,
`set_config` from `src/webui/plantimager/webui/assets/config_scan.toml`
with `n_points=4` + per-camera `picamera` copy. Then
`config_timelapse(conf)` for the `CONFIGURED` draft (interval 30s×5).

Reference: `scripts/run_timelapse_dummy_gui.py` (same stack, but its
controller is `Popen`-based for operator-handheld use — mutually exclusive
with this mode).

### (b) MCP-only launch (no cameras/DB)

Same `launch_app`, skip cameras/PlantDB. Enough for badge/panel/dialog
checks; real-scan `RUNNING`/`COMPLETED` needs mode (a).

## 3. Window map

Splash (`Loader.qml`) loads `Main.qml` as a **second window**. Bare `window`
works iff exactly one candidate exists — always re-run `health` after
open/close and address `window[N]` by index (indices shift; titles are
usually absent). Anonymous items use `Type[idx]`/`#[idx]`; `id`-only items
resolve via indexed path — then `set_alias` for reuse. Dialogs live under
`window[N]/QQuickOverlay[0]/Dialog`.

Snapshot contract: `state`/`mode` arrive **lowercase** (Python enum
`.value`); QML uppercases once in `refreshTl()` — keep literals uppercase.

## 4. Tiered verification (in this order)

- **Tier 0 — graph (default):** `explore_graph` / `list_children` /
  `get_properties` (`enabled`, `visible`, state). Answers state questions
  without rendering anything.
- **Tier 1 — region crop:** `screenshot(target, region={...})` on the
  region of interest (badge strip, dialog box) when the question is
  rendering (glyph, color, truncation, 800×480 layout).
- **Tier 2 — fullscreen:** agent judgment, for final sign-off or layout
  issues (centering, proportions, touch spacing).

Worked example (CONFIGURED flow) uses all three: Tier 0 — panel tree +
Cancel `enabled:true`; Tier 1 — badge crop (pencil+ok), dialog crop
(title, `0/5` text, both buttons); Tier 2 — fullscreen panel + dialog.

## 5. Cleanup

Controller via `close_app`; cameras/PlantDB via SIGINT → kill fallback;
`ctx.term()`; reset `RPCController._instance = None`. Cancel live jobs
first (`cancel_timelapse`) so no timers fire after close. A `cancelled`
row persisting in XDG storage after a live test is expected — flag it.
