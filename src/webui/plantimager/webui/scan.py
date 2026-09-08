#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Scan Configuration and Execution Components for Plant Imager Web UI.

This module provides the user interface components and functionality for configuring
and executing plant scans in the Plant Imager system.

Key Features
------------
- TOML-based scan configuration editor
- Dataset name validation with real-time feedback
- Scan execution controls with status reporting
- Configuration file upload functionality
- Comprehensive error handling and user feedback
"""
import os
import tomllib
import traceback
from base64 import b64decode
from typing import Dict

import dash_bootstrap_components as dbc
import diskcache
import requests
import toml
import zmq
from dash import DiskcacheManager
from dash import Input
from dash import Output
from dash import State
from dash import callback
from dash import callback_context
from dash import clientside_callback
from dash import ctx
from dash import dcc
from dash import html
from dash import no_update
from dash.exceptions import PreventUpdate
from plantdb.client.metadata_app.field_spec import FIELD_SPECS
from plantdb.client.metadata_app.field_spec import flatten
from plantdb.client.metadata_app.field_spec import sections
from plantdb.client.metadata_app.field_spec import specs_for_section
from plantdb.client.metadata_app.field_spec import unflatten
from plantdb.client.rest_api.requests import request_api_token
from plantdb.client.rest_api.urls import plantdb_url
from plantdb.commons.auth.models import Permission
from plantimager.commons.RPC import NoResult

from plantimager.webui.auth import ensure_valid_token
from plantimager.webui.controller_proxy import RPCController

#: Characters not allowed in dataset names for system compatibility
FORBIDDEN_CHAR = [":", "/", "*", "#", "@", ">", "<", "?", "|", "\"", "\'"]

#: Get the directory where the current file is located
current_dir = os.path.dirname(os.path.abspath(__file__))

cache = diskcache.Cache("./cache")
background_callback_manager = DiskcacheManager(cache)

#: Number of camera configuration cards (fixed slots, shown/hidden).
MAX_CAMERAS = 6

#: Path kwargs shown per ``ScanPath.class_name``.
PATH_FIELDS = {
    "Circle": ["center_x", "center_y", "radius", "n_points"],
    "Line": ["x_0", "y_0", "x_1", "y_1", "pan", "n_points"],
}
#: Display order of every possible path kwarg input (all always rendered, toggled by class).
PATH_ORDER = ["center_x", "center_y", "radius",
              "n_points", "n_circles", "x_0", "y_0", "x_1", "y_1", "pan"]
#: Per-field (column, default, min, max) for the two-column kwargs menu.
#: ``None`` means no default / no bound. Column is 1 (left) or 2 (right).
PATH_SPEC = {
    "radius": (1, 350, 100, 375),
    "n_points": (1, 36, 3, 360),
    "center_x": (2, 375, None, None),
    "center_y": (2, 375, None, None),
    "x_0": (1, None, None, None),
    "y_0": (1, None, None, None),
    "x_1": (2, None, None, None),
    "y_1": (2, None, None, None),
    "pan": (2, None, None, None),
}
#: Camera offset axes (matches ``Pose``/``scanner`` offset contract).
CAMERA_AXES = ["x", "y", "z", "pan", "tilt"]


def _num(value):
    """Coerce a form value to ``int``/``float``, keeping it as-is if not numeric."""
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return value


def _load_cfg(toml_text: str | None) -> dict:
    """Parse the hidden TOML source of truth into a config dict."""
    return tomllib.loads(toml_text) if toml_text else {}


def _dump(cfg: dict) -> str:
    """Serialize a config dict back to a TOML string (hidden source of truth)."""
    return toml.dumps(cfg)


def _free_camera_name(used: set[str]) -> str:
    """Return a default camera name (``picamera``, ``picameraN``) not in ``used``."""
    name = "picamera"
    i = 0
    while name in used:
        i += 1
        name = f"picamera{i}"
    return name


def _bio_field_id(path: str) -> str:
    """Return a Dash-safe component id for a MIAPPE field path."""
    return "bio-" + path.replace(".", "__")


def _tooltip(spec: dict) -> str:
    """Build a compact tooltip string for a MIAPPE field spec."""
    tt = spec["tooltip"]
    lines = [tt["definition"]]
    if tt.get("format"):
        lines.append(f"Format: {tt['format']}")
    if tt.get("example"):
        lines.append(f"Example: {tt['example']}")
    if tt.get("codename"):
        lines.append(f"MIAPPE: {tt['codename']}")
    return " | ".join(lines)


def _path_form() -> html.Div:
    """Build the path configuration form: class dropdown (1/3) + kwargs menu (2/3).

    The class dropdown sits in the left third; the kwargs inputs for the selected
    class are laid out in a two-column menu on the remaining two thirds.
    """

    def field(f):
        col, default, lo, hi = PATH_SPEC.get(f, (1, None, None, None))
        return html.Div([
            dbc.InputGroup([
                dbc.InputGroupText(f, className="text-capitalize"),
                dbc.Input(id=f"path-kwarg-{f}", type="number", debounce=True,
                          min=lo, max=hi, placeholder=default),
            ]),
        ], id=f"path-kwarg-{f}-row", style={"display": "none"}, className="mb-1")

    cols = {1: [], 2: []}
    for f in PATH_ORDER:
        cols[PATH_SPEC.get(f, (1,))[0]].append(field(f))

    return html.Div([
        dbc.Row([
            dbc.Col([
                html.Div([
                    dbc.Label("Path type", className="mb-0 me-2 text-nowrap"),
                    dbc.Select(id="path-class", options=[{"label": c, "value": c} for c in PATH_FIELDS],
                               value="Circle", style={"minWidth": "75px", "maxWidth": "150px"}),
                ], className="d-flex align-items-center"),
            ], md=4),
            dbc.Col([
                dbc.Row([dbc.Col(cols[1], md=6), dbc.Col(cols[2], md=6)], className="g-1"),
            ], md=8),
        ], className="g-2 align-items-start"),
    ])


def _camera_card(i: int) -> dbc.Card:
    """Build one camera configuration card (fixed slot ``i``, hidden until active)."""
    offset_row = dbc.Row([
        dbc.Col(dbc.InputGroup([dbc.InputGroupText(axis), dbc.Input(id=f"cam-{i}-offset-{axis}", type="number")]),
                className="col")
        for axis in CAMERA_AXES
    ], className="mb-2 g-1")
    return dbc.Card([
        dbc.CardHeader([
            dbc.Row([
                dbc.Col(dbc.Label("Camera name", className="mb-0 me-2 text-nowrap"),
                        className="align-self-center", style={"maxWidth": "fit-content"}),
                dbc.Col(dbc.Input(id=f"cam-{i}-name", type="text", placeholder="camera name",
                                  style={"minWidth": "125px", "maxWidth": "250px"}),
                        className="align-self-center"),
                dbc.Col(dbc.Button("Remove", id=f"cam-{i}-remove", color="danger", size="sm"), width="auto"),
            ], className="g-1 align-items-center"),
        ]),
        dbc.CardBody([
            dbc.Row([
                dbc.Col(dbc.InputGroup([dbc.InputGroupText("res_x"), dbc.Input(id=f"cam-{i}-res-x", type="number")])),
                dbc.Col(dbc.InputGroup([dbc.InputGroupText("res_y"), dbc.Input(id=f"cam-{i}-res-y", type="number")])),
                dbc.Col(dbc.InputGroup([
                    dbc.InputGroupText("encoding"),
                    dbc.Select(id=f"cam-{i}-encoding", options=[{"label": e, "value": e} for e in ("jpeg", "png")]),
                ])),
                dbc.Col(dbc.Checkbox(id=f"cam-{i}-advanced", label="Advanced", className="mt-2 align-self-center"),
                        width="auto"),
            ], className="mb-2 g-1"),
            dbc.Label("Offset", className="mt-2 mb-1"),
            offset_row,
            dbc.Label("Advanced configuration", id=f"cam-{i}-config-label", className="mt-2 mb-1"),
            dbc.Textarea(id=f"cam-{i}-config", size="sm", placeholder="[picamera2 properties]",
                         style={"display": "none"}),
            # https://pip-assets.raspberrypi.com/categories/652-raspberry-pi-camera-module-2/documents/RP-008156-DS-3-picamera2-manual.pdf
        ]),
    ], id=f"camera-card-{i}", style={"display": "none"}, className="mb-2")


def _bio_form() -> dbc.Accordion:
    """Build the MIAPPE biological metadata form from ``field_spec``."""
    section_accordion = dbc.Accordion([], always_open=True)
    for section in sections():
        specs = specs_for_section(section)
        if not specs:
            continue
        rows = []
        for spec in specs:
            path = spec["path"]
            kind = {"type": "number"} if spec["type"] in ("int", "float") else {"type": "text"}
            rows.append(dbc.InputGroup([
                dbc.InputGroupText(html.Label(spec["label"]), className="align-self-center"),
                dbc.Input(id=_bio_field_id(path), debounce=True, **kind),
                dbc.InputGroupText(html.I(className="bi bi-question-circle", title=_tooltip(spec)),
                                   className="align-self-center"),
            ], className="mb-1 field-group"))
        section_accordion.children.append(dbc.AccordionItem(rows, title=section, className="mb-2"))
    return section_accordion


# Card for scan configuration settings (path / camera / biological metadata accordion)
configuration_card = [
    dbc.Card(
        id="configuration-card",
        children=[
            dbc.CardHeader(children=[html.I(className="bi bi-code-square me-2"), "Configuration"]),
            dbc.CardBody([
                dbc.Accordion([
                    dbc.AccordionItem(_path_form(), title="Path configuration", item_id="path"),
                    dbc.AccordionItem([
                        *[_camera_card(i) for i in range(MAX_CAMERAS)],
                        dbc.Button("+ Add camera", id="add-cam-btn", color="secondary", size="sm", class_name="mt-2"),
                        dcc.Store(id="cam-active", data=[]),
                    ], title="Camera configuration", item_id="camera"),
                    dbc.AccordionItem(_bio_form(), title="Biological metadata configuration", item_id="bio"),
                ], start_collapsed=True, always_open=True),
                # Hidden single source of truth, consumed by `run_scan`/`config_scan`.
                dbc.Textarea(id="scan-cfg-toml", style={"display": "none"}),
            ]),
            dbc.CardFooter([
                dcc.Upload(
                    children=[
                        html.I(className="bi bi-cloud-arrow-up me-2"),
                        "Drag and Drop or Select a TOML configuration file."
                    ],
                    id="cfg-upload",
                    style={
                        'width': '100%',
                        'height': '60px',
                        'lineHeight': '60px',
                        'borderWidth': '1px',
                        'borderStyle': 'dashed',
                        'borderRadius': '5px',
                        'textAlign': 'center',
                    },
                    accept=".toml",
                    multiple=False,
                ),
                dbc.Alert(
                    id="cfg-upload-alert",
                    color="danger",
                    dismissable=True,
                    is_open=False,
                    className="mt-2 mb-0",
                ),
                dcc.Store(id="uploaded-cfg", data=None),
            ]),
        ]
    )
]

# Card for dataset name input with validation
dataset_name_card = [
    dbc.Card(
        id="dataset-card",
        children=[
            dbc.CardHeader(children=[html.I(className="bi bi-tag me-2"), "Dataset"]),
            dbc.CardBody(children=[
                html.Div([
                    dbc.Label("Name of the dataset to create:"),
                    dbc.Input(id="dataset-input-name", placeholder="Dataset name",
                              class_name="mb-3", invalid=True, persistence=True,
                                  style={"minWidth": "125px", "maxWidth": "250px"}),
                    dbc.FormText(dcc.Markdown(
                        "The list of forbidden characters is: " + ', '.join([f'`{c}`' for c in FORBIDDEN_CHAR])
                    )),
                ]),
                html.Div(children=[
                    dbc.Alert(
                        "Dataset name already exists. Please choose a different name.",
                        color="danger",
                        dismissable=True
                    )
                ], id='dataset-exists-message', style={'display': 'none'}),
            ]),
        ]
    )
]

camera_card = [
    dbc.Card(
        id="camera-card",
        children=[
            dbc.CardHeader(children=[html.I(className="bi bi-camera me-2"), "Camera"]),
            dbc.CardBody(
                children=[
                    dcc.Markdown(id="available-cameras", children="No camera connected")
                ]
            ),
        ]
    )
]

# Card containing scan controls and status information
scan_card = [
    dbc.Card(
        id="scan-card",
        children=[
            dbc.CardHeader(children=[html.I(className="bi bi-upc-scan me-2"), "Scan"]),
            dbc.CardBody([
                dbc.Row([
                    # --- Scanner Configuration Button ---
                    dbc.Col([
                        dbc.Button(
                            children=[
                                html.I(className="bi bi-gear-fill me-2"),
                                'Configure Scanner'
                            ],
                            id='config-scan-button',
                            color="primary",
                            style={'width': '100%'},
                        ),
                    ], width=3),
                    # --- Start Scan Button ---
                    dbc.Col([
                        dbc.Button(
                            children=[
                                html.I(className="bi bi-play-fill me-2"),
                                'Start Scanning'
                            ],
                            id='start-scan-button',
                            color="success",
                            style={'width': '100%'},
                        ),
                    ], width=3),
                    # --- Cancel Scan Button ---
                    dbc.Col([
                        dbc.Button(
                            children=[
                                html.I(className="bi bi-x-circle-fill me-2"),
                                'Cancel Scan'
                            ],
                            id='cancel-scan-button',
                            disabled=True,  # inactive by default
                            color="danger",
                            style={'width': '100%'},
                        ),
                    ], width=3),
                ], align="center"),
                # --- Scan Output Section
                dbc.Row([
                    dbc.Col([
                        dbc.Alert(
                            id='scan-response',
                            children="Configure or start a scann to the the ouptut here...",
                            color="secondary",
                            className="mb-0",
                            style={'display': 'none', 'color': 'gray'}
                        )
                    ], width="auto"),
                ], align="center", style={"margin-top": "15px"}),
                # --- Scan ProgressBar Section
                dbc.Row([
                    dbc.Col([
                        dbc.Progress(
                            id='scan-progress', style={"margin-top": "15px"}, className="mb-3"
                        ),
                    ])
                ])
            ]),
            dbc.CardFooter([
                dbc.Accordion(
                    dbc.AccordionItem(children=[
                        dcc.Markdown(id="scan-output", children="_Run a scan first..._"),
                    ],
                        title="Detailed scan output:"
                    ),
                    start_collapsed=True, flush=True
                )
            ], style={'bs-accordion-btn-bg': '#21252908'})
        ]
    )
]

# Main container for the "scan" layout: two equally sized columns
# Left column, containing the configuration card
# Right column, containing multiple stacked cards
scan_layout = html.Div(
    children=[
        dcc.Interval(id='main-interval', disabled=False, interval=4000),
        dbc.Row([
            dbc.Col(configuration_card, md=6),
            dbc.Col(dataset_name_card + [html.Br()] + camera_card + [html.Br()] + scan_card, md=6)
        ]),
        # Modal asking to confirm overriding the current config with the uploaded file.
        dbc.Modal(id="override-modal", is_open=False, size="lg", children=[
            dbc.ModalHeader(
                dbc.ModalTitle(children=[html.I(className="bi bi-arrow-repeat me-2"), "Override configuration?"])
            ),
            dbc.ModalBody([
                dbc.Alert(
                    "The uploaded TOML file is valid. Overriding will replace the current configuration.",
                    color="info", className="mb-3",
                ),
                dbc.Label("Uploaded configuration:"),
                dbc.Textarea(id="override-cfg-content", readOnly=True, style={"font-family": "monospace"}),
            ]),
            dbc.ModalFooter([
                dbc.Button("Abort", id="override-abort", color="secondary", className="ms-auto"),
                dbc.Button([html.I(className="bi bi-check-lg me-2"), "Override"], id="override-confirm",
                           color="primary"),
            ]),
        ]),
    ], id="scan-page-layout"
)


# Callback to update the default configuration file once the app is running
@callback(
    Output('scan-cfg-toml', 'value'),
    Input('url', 'pathname')
)
def load_default_toml_cfg(_):
    # Construct the path to the sample TOML config file (`assets` directory)
    default_toml_path = os.path.join(current_dir, 'assets', 'config_scan.toml')
    # Load the default TOML configuration file into a string variable
    with open(default_toml_path, 'r') as f:
        default_toml = f.read()
    return default_toml


CAM_FIELDS = ['name', 'res-x', 'res-y', 'encoding',
              *[f'offset-{a}' for a in CAMERA_AXES], 'config']


# --- Path configuration -------------------------------------------------------
@callback(
    Output('path-class', 'value'),
    *[Output(f'path-kwarg-{f}', 'value') for f in PATH_ORDER],
    *[Output(f'path-kwarg-{f}-row', 'style') for f in PATH_ORDER],
    Input('scan-cfg-toml', 'value'),
)
def populate_path(toml_text):
    """Fill the path form from the hidden config (single source of truth)."""
    cfg = _load_cfg(toml_text)
    sp = cfg.get("ScanPath") or {}
    cls = sp.get("class_name", "Circle")
    kwargs = sp.get("kwargs") or {}
    vals = {f: "" for f in PATH_ORDER}
    if cls == "Cylinder":
        zr = kwargs.get("z_range")
        if isinstance(zr, (list, tuple)) and len(zr) == 2:
            vals["z_min"], vals["z_max"] = zr[0], zr[1]
        for f in PATH_FIELDS["Cylinder"]:
            if f not in ("z_min", "z_max"):
                vals[f] = kwargs.get(f)
    else:
        for f in PATH_FIELDS.get(cls, []):
            vals[f] = kwargs.get(f)
    show = set(PATH_FIELDS.get(cls, []))
    out = [cls]
    for f in PATH_ORDER:
        v = vals[f]
        if v is None:
            v = PATH_SPEC.get(f, (1, None))[1]
        out.append("" if v is None else str(v))
    for f in PATH_ORDER:
        out.append({"display": "block"} if f in show else {"display": "none"})
    return out


@callback(
    Output('scan-cfg-toml', 'value', allow_duplicate=True),
    Input('path-class', 'value'),
    *[Input(f'path-kwarg-{f}', 'value') for f in PATH_ORDER],
    State('scan-cfg-toml', 'value'),
    prevent_initial_call=True,
)
def rebuild_path(cls, center_x, center_y, radius, n_points, n_circles, x_0, y_0, x_1, y_1, pan, toml_text):
    """Rebuild the ``ScanPath`` section of the config from the path form."""
    cfg = _load_cfg(toml_text)
    vals = dict(zip(PATH_ORDER, (center_x, center_y, radius, n_points, n_circles, x_0, y_0, x_1, y_1, pan)))
    kwargs = {k: _num(vals[k]) for k in PATH_FIELDS.get(cls, [])}
    kwargs = {k: v for k, v in kwargs.items() if v is not None}
    cfg["ScanPath"] = {"class_name": cls, "kwargs": kwargs}
    return _dump(cfg)


# --- Camera configuration -----------------------------------------------------
@callback(
    Output('cam-active', 'data'),
    *[Output(f'camera-card-{i}', 'style') for i in range(MAX_CAMERAS)],
    *[Output(f'cam-{i}-{f}', 'value') for i in range(MAX_CAMERAS) for f in CAM_FIELDS],
    Input('scan-cfg-toml', 'value'),
)
def populate_cameras(toml_text):
    """Fill the camera cards and active-slot list from the hidden config."""
    cfg = _load_cfg(toml_text)
    cameras = [(k, v) for k, v in cfg.items() if k not in ("ScanPath", "Metadata")]
    active = list(range(len(cameras)))
    out = [active]
    for i in range(MAX_CAMERAS):
        out.append({"display": "block"} if i < len(cameras) else {"display": "none"})
    for i in range(MAX_CAMERAS):
        if i < len(cameras):
            name, cam = cameras[i]
            offset = cam.get("offset") or {}
            vals = {
                'name': name,
                'res-x': cam.get("res_x"), 'res-y': cam.get("res_y"),
                'encoding': cam.get("encoding"),
                **{f'offset-{a}': offset.get(a) for a in CAMERA_AXES},
                'config': _dump(cam.get("config") or {}),
            }
        else:
            vals = {f: "" for f in CAM_FIELDS}
        for f in CAM_FIELDS:
            v = vals[f]
            out.append("" if v is None else str(v))
    return out


@callback(
    Output('scan-cfg-toml', 'value', allow_duplicate=True),
    Output('cam-active', 'data', allow_duplicate=True),
    Input('add-cam-btn', 'n_clicks'),
    *[Input(f'cam-{i}-remove', 'n_clicks') for i in range(MAX_CAMERAS)],
    *[Input(f'cam-{i}-{f}', 'value') for i in range(MAX_CAMERAS) for f in CAM_FIELDS],
    State('cam-active', 'data'),
    State('scan-cfg-toml', 'value'),
    prevent_initial_call=True,
)
def rebuild_cameras(*args):
    """Rebuild the camera sections of the config and manage add/remove of cards."""
    n_remove = MAX_CAMERAS
    field_vals = args[1 + n_remove:1 + n_remove + n_remove * len(CAM_FIELDS)]
    active = args[-2]
    toml_text = args[-1]
    cfg = _load_cfg(toml_text)
    active = list(active or [])

    def cam_vals(i):
        base = i * len(CAM_FIELDS)
        return {f: field_vals[base + j] for j, f in enumerate(CAM_FIELDS)}

    triggered = [t["prop_id"] for t in callback_context.triggered]

    added_slot = None
    if any(t.startswith("add-cam-btn") for t in triggered) and len(active) < MAX_CAMERAS:
        added_slot = max(active, default=-1) + 1
        active.append(added_slot)
    for i in range(MAX_CAMERAS):
        if any(t.startswith(f"cam-{i}-remove") for t in triggered) and i in active:
            active.remove(i)

    # Pick a default name for a newly added camera that does not collide with existing ones.
    used_names = set(cfg.keys()) - {"ScanPath", "Metadata"}
    new_name = _free_camera_name(used_names)

    cameras = {}
    for s in active:
        d = cam_vals(s)
        if s == added_slot:
            cameras[new_name] = {"res_x": 2000, "res_y": 1500, "encoding": "jpeg",
                                 "offset": {a: 0 for a in CAMERA_AXES}, "config": {}}
        else:
            name = d['name'] or f"picamera{s}"
            offset = {a: _num(d[f'offset-{a}']) for a in CAMERA_AXES}
            offset = {k: v for k, v in offset.items() if v is not None}
            config = {}
            if d.get('config'):
                try:
                    config = tomllib.loads(d['config'])
                except tomllib.TOMLDecodeError:
                    config = {}
            cam = {"res_x": _num(d['res-x']), "res_y": _num(d['res-y']),
                   "encoding": d['encoding'] or "jpeg", "offset": offset, "config": config}
        cameras[name] = cam

    for k in [k for k in cfg if k not in ("ScanPath", "Metadata")]:
        cfg.pop(k)
    cfg.update(cameras)
    return _dump(cfg), active


# --- Biological metadata configuration ----------------------------------------
@callback(
    *[Output(_bio_field_id(s['path']), 'value') for s in FIELD_SPECS],
    Input('scan-cfg-toml', 'value'),
)
def populate_bio(toml_text):
    """Fill the MIAPPE biological form from ``Metadata.object``."""
    cfg = _load_cfg(toml_text)
    obj = (cfg.get("Metadata") or {}).get("object") or {}
    flat = flatten(obj)
    return ["" if flat.get(s['path']) is None else str(flat[s['path']]) for s in FIELD_SPECS]


@callback(
    Output('scan-cfg-toml', 'value', allow_duplicate=True),
    *[Input(_bio_field_id(s['path']), 'value') for s in FIELD_SPECS],
    State('scan-cfg-toml', 'value'),
    prevent_initial_call=True,
)
def rebuild_bio(*args):
    """Rebuild ``Metadata.object`` (MIAPPE tree) from the biological form."""
    values = args[:-1]
    toml_text = args[-1]
    cfg = _load_cfg(toml_text)
    flat = {s['path']: values[i] for i, s in enumerate(FIELD_SPECS) if values[i] not in (None, "")}
    metadata = cfg.setdefault("Metadata", {})
    metadata["object"] = unflatten(flat)
    return _dump(cfg)


available_cameras = []


def update_available_cameras(val):
    global available_cameras
    available_cameras = val


@callback(
    Output('available-cameras', 'children'),
    Input('main-interval', 'n_intervals'))
def update_interval(n_intervals):
    """Updates various components on a timer.

    Returns
    -------
    str
        Markdown message which is printed at 'available-cameras'.
    """
    try:
        controller = RPCController.instance()
    except RuntimeError as e:
        return f"**Controller not connected**: {e}"
    if update_available_cameras not in controller.cameraNamesChanged.connections:
        controller.cameraNamesChanged.connect(update_available_cameras)
        update_available_cameras(controller.camera_names)

    if available_cameras:
        lines = []
        for camera in available_cameras:
            lines.append(f"- {camera}")
        return "\n".join(lines)
    else:
        return "No camera connected"


@callback(
    Output('scan-cfg-toml', 'valid'),
    Output('scan-cfg-toml', 'invalid'),
    Input('scan-cfg-toml', 'value'),
)
def validate_toml_textarea(toml_text: str) -> tuple[bool, bool]:
    """Validate the TOML configuration entered by the user."""
    # Empty textarea should not be flagged
    if not toml_text:
        return False, False

    try:
        # Attempt to parse the TOML; we only care about success/failure
        tomllib.loads(toml_text)
        # Valid TOML → keep normal appearance
        return True, False
    except Exception:
        # Invalid TOML → add a red border for visual feedback
        return False, True


@callback(
    Output('uploaded-cfg', 'data'),
    Output('cfg-upload-alert', 'is_open'),
    Output('cfg-upload-alert', 'children'),
    Output('override-cfg-content', 'value'),
    Output('override-modal', 'is_open'),
    Input('cfg-upload', 'contents'),
    prevent_initial_call=True,
)
def handle_config_upload(contents: str | None):
    """Validate an uploaded TOML file and, if valid, open the override confirmation modal."""
    if not contents:
        return None, False, "", "", False
    try:
        text = b64decode(contents.split(',', 1)[1]).decode()
        tomllib.loads(text)
    except Exception:
        return (None, True, "Invalid TOML configuration file: could not be parsed.",
                "", False)
    return text, False, "", text, True


@callback(
    Output('scan-cfg-toml', 'value', allow_duplicate=True),
    Output('override-modal', 'is_open', allow_duplicate=True),
    Output('uploaded-cfg', 'data', allow_duplicate=True),
    Input('override-confirm', 'n_clicks'),
    Input('override-abort', 'n_clicks'),
    State('uploaded-cfg', 'data'),
    prevent_initial_call=True,
)
def apply_config_override(confirm_clicks, abort_clicks, uploaded: str | None):
    """On 'Override', replace the config with the uploaded TOML; on 'Abort', discard it."""
    if ctx.triggered_id == 'override-confirm' and uploaded:
        return uploaded, False, None
    return no_update, False, None


# Toggle visibility of each camera's "Advanced configuration" textarea via its "Advanced" checkbox.
for _i in range(MAX_CAMERAS):
    clientside_callback(
        """function(checked) {
            const style = {display: checked ? 'block' : 'none'};
            return [style, style];
        }""",
        Output(f'cam-{_i}-config', 'style'),
        Output(f'cam-{_i}-config-label', 'style'),
        Input(f'cam-{_i}-advanced', 'value'),
    )


def all_valid_characters(dataset_name: str) -> bool:
    """Validates if all characters in a given dataset name are permissible.

    Parameters
    ----------
    dataset_name : str
        The name of the dataset to be validated.

    Returns
    -------
    bool
        ``True`` if all characters in the dataset name are valid otherwise, ``False``.
    """
    return sum([letter in FORBIDDEN_CHAR for letter in dataset_name]) == 0


def is_valid_dataset_name(dataset_name: str, existing_datasets: list[str]) -> bool:
    """Check if a dataset name is valid and does not already exist.

    Parameters
    ----------
    dataset_name : str
        The name of the dataset to be validated.
    existing_datasets : list of str
        A list of dataset names that already exist.

    Returns
    -------
    bool
        ``True`` if the dataset name is valid and does not exist in the list of
        existing datasets, ``False`` otherwise.
    """
    if dataset_name not in existing_datasets and all_valid_characters(dataset_name):
        return True
    else:
        return False


# Callback to validate the selected dataset name:
@callback(
    Output('dataset-input-name', 'invalid'),
    Output('dataset-input-name', 'valid'),
    Output('dataset-id', 'data'),
    Input('dataset-input-name', 'value'),
    State('dataset-list', 'data')
)
def validate_dataset_name(dataset_name: str, existing_datasets: list[str]) -> tuple[bool, bool, str]:
    """Callback to validate the selected dataset name.

    It should follow two rules:
        1. unicity: it should not exist in the database
        2. decency: no fancy/weird/impossible characters are allowed!

    Parameters
    ----------
    dataset_name : str
        The dataset name to validate.
    existing_datasets : list
        The dataset indexed dictionary that exists in the database.

    Returns
    -------
    bool
        The `invalid` state of the 'dataset-input-name' `Input` component.
    bool
        The `valid` state of the 'dataset-input-name' `Input` component.
    str
        The name of the dataset.
    """
    if dataset_name is not None and is_valid_dataset_name(dataset_name, existing_datasets):
        return False, True, dataset_name
    else:
        return True, False, dataset_name


@callback(
    Output('dataset-exists-message', 'style'),
    Input('dataset-input-name', 'value'),
    State('dataset-list', 'data')
)
def check_dataset_name_uniqueness(dataset_name: str, existing_datasets: list[str]) -> dict[str, str]:
    """Check if the specified dataset name already exists.

    Parameters
    ----------
    dataset_name : str
        The name of the dataset input by the user, which needs to be checked
        for uniqueness.
    existing_datasets : list of str
        A list containing the names of datasets that already exist.

    Returns
    -------
    Dict[str, str]
        A style dictionary for controlling the visibility of a message. If the
        dataset name already exists, the dictionary will display the message.
        Otherwise, it will hide the message.
    """
    if dataset_name in existing_datasets:
        return {'display': 'block', 'margin-top': '10px'}
    else:
        return {'display': 'none'}


@callback(
    Output('start-scan-button', 'disabled'),
    Output('config-scan-button', 'disabled'),
    Input('dataset-input-name', 'valid'),
    Input('main-interval', 'n_intervals'),
    State('start-scan-button', 'disabled')
)
def disable_scan_button(valid: bool, n_intervals: int, previous_state: bool) -> tuple[bool, bool]:
    """Disables the 'Start scanning' button based on dataset validation status and if scanner is connected.

    This callback function determines whether the 'start-scan-button' element
    should be disabled or enabled based on the validity of input provided
    to the 'dataset-input-name' element. If the input is not valid, the
    'start-scan-button' is disabled.

    Parameters
    ----------
    valid : bool
        Indicates whether the dataset input is valid.
        ``True`` if valid, ``False`` otherwise.
    n_intervals : int
        Number of times interval is raised

    Returns
    -------
    bool
        Returns ``True`` if the scan button should be disabled, and ``False``
        if it should be enabled.
    """
    try:
        RPCController.instance()
    except RuntimeError:
        if previous_state:
            raise PreventUpdate
        return True, True
    if previous_state == (not valid):
        raise PreventUpdate
    return not valid, not valid


@callback(
    Output('access-token', 'data', allow_duplicate=True),
    Output('refresh-token', 'data', allow_duplicate=True),
    Output('scan-api-token', 'data'),
    Output('scan-job-id', 'data'),
    Output('scan-response', 'children', allow_duplicate=True),
    Output('scan-output', 'children', allow_duplicate=True),
    Input('start-scan-button', 'n_clicks'),
    State('plantdb-host', 'data'),
    State('plantdb-port', 'data'),
    State('plantdb-prefix', 'data'),
    State('plantdb-ssl', 'data'),
    State('access-token', 'data'),
    State('refresh-token', 'data'),
    State('logged-username', 'data'),
    State('dataset-input-name', 'value'),
    State('scan-job-id', 'data'),
    prevent_initial_call=True,
)
def prepare_scan(_, url: str, port: str, prefix: str, ssl: bool, access_token: str, refresh_token: str,
                 username: str, dataset_name: str, scan_job_id: int):
    """Authenticate and create a scoped per-scan API token.

    This runs in the main web UI process only. It makes the user token
    refresh deliberate (persisting any rotated pair back to the Dash Stores)
    and creates the short-lived API token that the scanner will use, so the
    background scan process never receives the user credentials.

    Parameters
    ----------
    _ : Any
        Unused parameter (n_clicks from the button).
    url : str
        The hostname or IP address of the PlantDB REST API server.
    port : str
        The port number of the PlantDB REST API server.
    prefix : str
        The prefix of the PlantDB REST API server.
    ssl : bool
        Whether the PlantDB REST API server is using SSL.
    access_token : str
        The PlantDB REST API access token of the user.
    refresh_token : str
        The PlantDB REST API refresh token of the user.
    username : str
        The logged-in username.
    dataset_name : str
        The name of the dataset to create the scoped API token for.
    scan_job_id : int
        The current scan job identifier, used to trigger the background scan.

    Returns
    -------
    tuple
        ``(access_token, refresh_token, api_token, scan_job_id, response_msg, output_msg)``.
        On success the first two are the fresh token pair, the API token is the
        scoped token for the scan and the job id is incremented to trigger the
        background scan, followed by a success status message. On failure the
        tokens are unmodified, the API token ``None``, the job id unchanged and
        the status messages describe what went wrong.
    """
    if not username:
        return (access_token, refresh_token, None, scan_job_id,
                "Not authenticated with plantdb.",
                "Please log in before starting a scan.")

    tokens = ensure_valid_token(url, port, prefix, ssl,
                                access_token, refresh_token, username)
    if tokens[0] is None or tokens[1] is None:
        return (access_token, refresh_token, None, scan_job_id,
                "Failed to authenticate with plantdb.",
                "The session tokens are invalid or expired. Please log out and log in again.")
    access_token, refresh_token = tokens

    if not dataset_name:
        return (access_token, refresh_token, None, scan_job_id,
                "No dataset name provided.",
                "Please enter and validate a dataset name before starting a scan.")

    try:
        datasets = {
            dataset_name: (
                Permission.WRITE.value,
                Permission.CREATE.value,
                Permission.READ.value,
            )
        }
        api_data = request_api_token(url, 1800, datasets, port=port, prefix=prefix, ssl=ssl,
                                     session_token=access_token)
        api_token = api_data.get("api_token") if isinstance(api_data, dict) else None
    except requests.exceptions.RequestException:
        api_token = None
    if not api_token:
        return (access_token, refresh_token, None, scan_job_id,
                "Failed to create the API token for plantdb.",
                "Unable to create the scoped API token used by the scanner.")

    return (access_token, refresh_token, api_token, (scan_job_id or 0) + 1,
            "Scan ready to start", "API token created, starting scanner...")


@callback(
    Output('scan-response', 'children'),
    Output('scan-output', 'children', allow_duplicate=True),
    Input('scan-job-id', 'data'),
    State('plantdb-host', 'data'),
    State('plantdb-port', 'data'),
    State('plantdb-prefix', 'data'),
    State('plantdb-ssl', 'data'),
    State('scan-api-token', 'data'),
    State('scan-cfg-toml', 'value'),
    State('dataset-input-name', 'value'),
    background=True,
    manager=background_callback_manager,
    prevent_initial_call=True,
    running=[
        (Output('start-scan-button', 'disabled', allow_duplicate=True), True, False),
        (Output('config-scan-button', 'disabled'), True, False),
        (Output('scan-response', 'children'), 'Scan in progress', ""),
        (Output('scan-output', 'children'), 'Scan in progress', ""),
        (Output('cancel-scan-button', 'disabled', allow_duplicate=True), False, True),
    ],
    progress=[
        Output('scan-progress', 'value'),
        Output('scan-progress', 'max'),
        Output('scan-progress', 'label'),
    ]
)
def run_scan(set_progress, scan_job_id: int, url: str, port: str, prefix: str, ssl: bool,
             api_token: str, cfg: str, dataset_name: str):
    """Execute a plant scan with the specified configuration.

    This runs in a separate background process and therefore never touches the
    user's access/refresh tokens: it only uses the scoped API token prepared by
    :func:`prepare_scan`.

    Parameters
    ----------
    set_progress : Callable
        The progress callback provided by Dash.
    scan_job_id : int
        The scan job identifier that triggered this callback (unused).
    url : str
        The hostname or IP address of the PlantDB REST API server.
    port : str
        The port number of the PlantDB REST API server.
    prefix : str
        The prefix of the PlantDB REST API server.
    ssl : bool
        Whether the PlantDB REST API server is using SSL.
    api_token : str
        The scoped API token granting access to the scan dataset.
    cfg : str
        The TOML configuration string for the scan.
    dataset_name : str
        The name to use for the dataset that will be created.

    Returns
    -------
    Tuple[str, str]
        A tuple containing two status messages:
        - First message: Short status for the alert component
        - Second message: Detailed status for the output component
    """
    if not api_token:
        return "Failed to authenticate with plantdb.", "No API token available, please log in and retry."

    # Background callbacks run in a new process. We must re-init the ZMQ context and Controller proxy.
    ctx = zmq.Context()
    # Using the same URL as app.py
    controller = RPCController(ctx, "tcp://localhost:14567")

    res: None | NoResult = controller.set_db_url(plantdb_url(url, port=port, prefix=prefix, ssl=ssl))
    if isinstance(res, NoResult):
        return f"Failed to connect to {'https' if ssl else 'http'}://{url}:{port}{prefix}", res.traceback

    res: None | NoResult = controller.set_api_token(api_token)
    if isinstance(res, NoResult):
        return "Failed to connect to set access token.", res.traceback
    res: None | NoResult = controller.set_dataset_name(dataset_name)
    if isinstance(res, NoResult):
        return f"Failed to set dataset {dataset_name}", res.traceback
    res: None | NoResult = controller.set_config(tomllib.loads(cfg))
    if isinstance(res, NoResult):
        return "Failed to configure scann", res.traceback

    m_prog = controller.max_progress

    def _update_progress(prog):
        set_progress((str(prog), str(m_prog), f"{prog}/{m_prog}"))

    controller.progressChanged.connect(_update_progress)

    res: None | NoResult = controller.run_scan()
    if isinstance(res, NoResult):
        return "Scan Failed", res.traceback

    return "Scan finished", "Scan complete"


@callback(
    Output('scan-response', 'children', allow_duplicate=True),
    Input('cancel-scan-button', 'n_clicks'),
    prevent_initial_call=True,
)
def cancel_scan(_):
    """Placeholder callback for the Cancel Scan button."""
    # TODO: implement actual cancellation logic
    return "Cancelling scan..."


@callback(
    Output('scan-response', 'children', allow_duplicate=True),
    Output('scan-output', 'children', allow_duplicate=True),
    Input('config-scan-button', 'n_clicks'),
    State('plantdb-host', 'data'),
    State('plantdb-port', 'data'),
    State('plantdb-prefix', 'data'),
    State('plantdb-ssl', 'data'),
    State('scan-cfg-toml', 'value'),
    State('dataset-input-name', 'value'),
    prevent_initial_call=True,
)
def config_scan(_, url: str, port: str, prefix: str, ssl: bool, cfg: str, dataset_name: str):
    """Configure a plant scan with the specified configuration.

    Parameters
    ----------
    _ : Any
        Unused parameter (n_clicks from the button).
    url : str
        The hostname or IP address of the PlantDB REST API server.
    port : str
        The port number of the PlantDB REST API server.
    prefix : str
        The prefix of the PlantDB REST API server.
    ssl : bool
        Whether the PlantDB REST API server is using SSL.
    cfg : str
        The TOML configuration string for the scan.
    dataset_name : str
        The name to use for the dataset that will be created.

    Returns
    -------
    Tuple[str, str]
        A tuple containing two status messages:
        - First message: Short status for the alert component
        - Second message: Detailed status for the output component

    Raises
    ------
    RuntimeError
        If the Raspberry Pi Controller is not initialized.
    """
    try:
        controller = RPCController.instance()
    except RuntimeError as e:
        return "Error: Raspberry Pi Controller not initialized!", str(e)

    res: None | NoResult = controller.set_db_url(plantdb_url(url, port=port, prefix=prefix, ssl=ssl))
    if isinstance(res, NoResult):
        return f"Failed to connect to {'https' if ssl else 'http'}://{url}:{port}{prefix}", res.traceback
    res: None | NoResult = controller.set_dataset_name(dataset_name)
    if isinstance(res, NoResult):
        return f"Failed to set dataset {dataset_name}", res.traceback
    try:
        config_dict = tomllib.loads(cfg)
    except tomllib.TOMLDecodeError:
        return "Failed to parse config file", traceback.format_exc(limit=1)
    res: None | NoResult = controller.set_config(config_dict)
    if isinstance(res, NoResult):
        return "Failed to configure scan", res.traceback

    return "Scan configured", "Scan configured, ready to start"
