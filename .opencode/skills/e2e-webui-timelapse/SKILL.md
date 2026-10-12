---
name: e2e-webui-timelapse
description: Use when end-to-end testing the Plant-Imager3 Dash WebUI timelapse form against the dummy stack — stack launch order with gates, single-tab Playwright flow (connect, login, cameras, configure, preview, schedule, start, cancel), QML oracle checks, faster-testing env knobs. Triggers on e2e webui, timelapse smoke, webui flow test, playwright dash, configure start cancel.
---

# E2E WebUI Timelapse (Plant-Imager3)

Manual runbook for the WebUI timelapse form: dummy stack + QML oracle +
single-tab Playwright flow, configure → preview → start → cancel. Companion
to `controller-gui-debug` (QML side) — load `py-qml-mcp` too for the
controller oracle steps. Source notes: vault ideas
`2026-10-08-e2e-webui-timelapse-form` (runbook) and
`2026-10-08-playwright-dash-feedback` (Playwright tooling lessons).

## 1. Preconditions

Conda env `plant-imager`; ports free: `23656` (PlantDB), `14567`
(controller RPC), `8080` (webui, default prefix setup — the app lives at `/`
when launched without prefix, `/webui/*` 404s).

```bash
PI3_ALLOW_DUMMY_CNC=1   # DummyCNC backend (or --allow-dummy-cnc argv)
DISPLAY=:1              # Xvfb headed display (offscreen hides exposure bugs)
PI3_CAMERASERVER_IMAGE  # or real_plant fallback via get_test_dataset
PI3_CAMERASERVER_LAG=100
```

- One RPC binder on `14567`: controller goes through py-qml `launch_app`
  only — a Popen controller alongside conflicts (`ZMQError: address in use`).
- Single browser tab for the whole run. Extra tabs add 4s RPC pollers and
  share session state.
- Known controller state first: cancel any active timelapse (stale
  `SCHEDULED` resumes on boot by design — check the QML corner).
- Distinctive dataset base name per run, e.g. `e2e_tl_<today>` — strays and
  phantoms are instantly recognizable in logs.

## 2. Faster-testing knobs (controller env only)

`PI3_MIN_WARMUP_SEC` (default 45) and `PI3_STANDBY_WARMUP_FACTOR` (default 2)
lower the warmup/standby minimums, e.g. `=5` / `=1` to observe the first scan
within seconds. The WebUI deliberately never hard-codes these (warn-not-reject),
so a lowered run also exercises that design choice. Leave production defaults
untouched.

## 3. Stack up (in order, with gates)

1. `fsdb_rest_api --test --empty --host localhost --port 23656` — gate: HTTP answers.
2. 2× `python -m plantimager.commons.examples.cameraserver` with the camera env.
3. Controller via `launch_app("plantimager.controller.main:main",
   args="--allow-dummy-cnc", ...)` — gate: Main 800×480 visible (`health` /
   `wait_for_idle`) **and** `camera_names >= 2`. Main takes 5–30s; re-run
   `health` after open/close and address `window[N]` by index.

Order matters: the controller hosts the device registry (`:5555`), so start
it **before** the cameras — cameras launched first fail registration and
never re-register (discovery then times out; fix is restarting the cameras,
not waiting longer).
4. Webui (`python -m plantimager.webui.app`, port 8080, no hot reload assumed).

Launch sequentially with gate checks, not all-at-once: cold controller
timeouts cascade into every dependent step.

## 4. WebUI flow (assertions are the test)

1. Connect PlantDB (host/port/prefix) → Test connexion → **Load datasets**
   (dataset uniqueness validation stays dead without it) → Close.
2. Login `admin` / `admin`.
3. Cameras card shows `DummyCamera`, `DummyCamera-1`.
4. Dataset name = run base name.
5. Timelapse accordion: switch ON (default), mode `interval`, defaults
   (`30s` × 5, advanced untouched). Tip for failure diagnosis: set advanced
   `on_scan_failed` to `fail_timelapse` so a failing slot ends the job
   immediately instead of skip-marching through every remaining slot. The switch is a positioned sibling of
   the header, not a child — clicking the header row toggles collapse, the
   switch toggles state.
6. Path + camera sections: slot names match the Camera section (auto-fill check).
7. Preview → 5 local-time rows, and no server state change (re-query
   `get_active_timelapse`).
8. Configure Timelapse → response `Timelapse configured (draft)` **and** QML
   corner CONFIGURED (pencil+ok) **and** status card `<base> · interval · 0/5`.
9. View schedule → 5 rows, all `pending` in draft (QML parity: `next`
   appears only once SCHEDULED — re-check the modal after Start as an extra
   assertion).
10. Start → `Timelapse started`, QML SCHEDULED, badge flips (fast — no scan
    runs yet inside the warmup window).
11. Cancel → CANCELLED → IDLE on both surfaces; schedule modal empty-state;
    no scan ever ran.

## 5. Teardown

Cancel if active → controller `close_app` → SIGINT cameras/PlantDB → webui
down. PlantDB `--test` is fresh-`--empty` each run; a `cancelled` XDG row
afterwards is expected.

## 6. Playwright discipline (earned the hard way)

- MCP wants an up-to-date firefox build (it demanded `firefox-1553` while only
  `154x` was present) — run the suggested install first. No browser-selection param.
- Aria refs expire on every re-render — re-snapshot before each click batch;
  prefer getByRole names in clicks.
- Startup modals intercept pointer events — dismiss via Close buttons (CSS
  hiding is screenshots-only).
- Real `browser_click` for state-changing clicks (`evaluate` `.click()` can
  toggle DOM without reaching Dash callbacks); `evaluate` for reads — hidden
  `scan-cfg-toml` textarea and Dash internals are the fastest assertion path.
- Never `stopPropagation` inside a Dash subtree (kills Dash delivery at the
  root listener). Row ids go on wrapper divs, never on `dbc.InputGroup`
  (callback-output `display:block` breaks its flex layout).
- The PlantDB config modal auto-closes on successful Test connexion —
  reopen it via the navbar button (`#plantdb-cfg-button >> nth=0`; the id is
  triplicated nested anchors, plain `#id` fails strict mode) for Load datasets.
- No page reloads mid-flow; single tab throughout.

## 7. Process hazards (do not work around, report)

- **Phantom legacy runs**: `run_scan` background callback self-fires (page
  loads included) with whatever dataset is set. Unexplained scan/CNC motion
  → note base name + timestamp, do not chase mid-run. Pre-existing bug.
  Attribution trap: `run_scan`'s "Scan in progress" running-indicator
  overwrites `scan-response`, so a phantom firing seconds after your Start
  click is indistinguishable from your click going legacy in the UI — check
  server-side (`get_active_timelapse`, worker PIDs) before concluding, and
  SIGTERM stray workers by exact PID before judging Start results.
- **RPC stalls**: a running (legacy) scan starves the single-threaded RPC
  handler → timeouts → permanently wedged client sockets. Wait for idle, do
  not restart mid-flow.
- **Shell timeouts kill tracked background processes** — even `setsid`-detached
  ones. Keep every call well under its timeout; verify PIDs after any restart,
  never blindly retry. Kill by exact PID; `pkill -f "pattern"` matches your
  own invoking shell — use the `[b]`racket trick.
- Unbuffered logs (`-u` / `stdbuf`): killed processes lose their last
  buffered lines, which are exactly the forensics you need.

## 8. Debugger recipe (live controller introspection)

mcp-debugger attach needs a `debugpy --listen` target — relaunch via py-qml
`launch_app` with `python` pointed at a wrapper script
(`exec <env-python> -m debugpy --listen 127.0.0.1:<port> "$@"`); the QML
oracle stays alive in the same process. `create_debug_session(python)` →
`attach_to_process(host, port)` → logpoints, not breakpoints, for the scan
path (slot start, refresh, create, moveto, grab, got-image, upload stream
into `get_output` without stopping).

- `evaluate_expression` takes EXPRESSIONS only: `__import__('sys')._current_frames()`
  plus `__import__('traceback').format_stack(...)` dumps every thread's stack
  without pausing each one (`threading.enumerate()` maps ident→name).
- `set_breakpoint` statement/expectedContent addressing fails when the server
  can't read the source tree — pure `file + line` works; the echoed line
  content doubles as verification.
- `pause_execution` lands on an arbitrary thread; `detach_from_process` +
  `close_debug_session` when done, target keeps running.
