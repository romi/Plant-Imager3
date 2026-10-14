#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Camera page: live view and control of one picamera at a time.

Select a camera, take (lores) pictures through the controller RPC proxy,
inspect and edit the five rig controls, persist defaults, and copy the
controls as a TOML snippet for the scan config. Everything here is RPC;
power control stays on the controller touchscreen by design.
"""

import base64

import dash_bootstrap_components as dbc
from dash import Input
from dash import Output
from dash import State
from dash import callback
from dash import callback_context
from dash import dcc
from dash import html
from dash import no_update
from dash import register_page
from dash.exceptions import PreventUpdate

from plantimager.commons.RPC import NoResult
from plantimager.webui.camera_controls import build_toml_snippet
from plantimager.webui.camera_controls import camera_control_form
from plantimager.webui.camera_controls import merge_config
from plantimager.webui.camera_controls import parse_number
from plantimager.webui.controller_proxy import RPCController

register_page(__name__, path="/cameras")

#: Metadata keys shown under the preview, in order when present.
META_KEYS = ("format", "size", "rotation", "ExposureTime", "AnalogueGain",
             "ColourGains", "FrameDuration", "Lux", "ColourTemperature")

form_layout, _FORM_IDS = camera_control_form("cam")

layout = html.Div([
    html.H4("Cameras"),
    dbc.Row([
        dbc.Col(dbc.Select(id="cam-select", placeholder="Select a camera"), width=6),
        dbc.Col(dbc.Button("Refresh", id="cam-refresh", color="secondary"), width="auto"),
        dbc.Col(dbc.Button("Take picture", id="cam-shoot", color="primary"), width="auto"),
    ], className="mb-3 g-2 align-items-center"),
    dbc.Row([
        dbc.Col([
            html.Img(id="cam-preview", style={"width": "100%"}),
            html.Div(id="cam-meta", className="mt-2"),
        ], width=6),
        dbc.Col([
            form_layout,
            dbc.Row([
                dbc.Col(dbc.Button("Apply", id="cam-apply", color="primary"), width="auto"),
                dbc.Col(dbc.Button("Set default", id="cam-set-default", color="secondary"), width="auto"),
                dbc.Col(dbc.Button("Reset", id="cam-reset", color="secondary"), width="auto"),
            ], className="mb-3 g-2"),
            dbc.Button("Copy as TOML", id="cam-copy-toml", color="info", className="mb-2"),
            dbc.Textarea(id="cam-toml", readonly=True, rows=8,
                         placeholder="[camera.config] snippet lands here"),
        ], width=6),
    ]),
    dbc.Alert(id="cam-status", is_open=False, duration=8000),
    dcc.Store(id="cam-full-config", data={}),
    dcc.Store(id="cam-toml-store", data="", storage_type="session"),
    dcc.Interval(id="cam-list-refresh", interval=10_000),
], style={"margin": 20})


def _controller_or_status():
    """Return ``(controller, None)`` or ``(None, (message, color))``."""
    try:
        return RPCController.instance(), None
    except RuntimeError as exc:
        return None, (f"Controller not connected: {exc}", "danger")


def _form_values(config):
    """Split a full config dict into the six form values, in field order."""
    gains = config.get("ColourGains") or (None, None)
    gains = list(gains) + [None, None] if len(gains) != 2 else list(gains)
    return (config.get("ExposureTime"), config.get("AnalogueGain"),
            bool(config.get("AwbEnable", False)), config.get("AwbMode"),
            gains[0], gains[1])


def _meta_rows(info):
    """Render capture metadata as a definition list."""
    rows = []
    for key in META_KEYS:
        if key in info:
            rows += [html.Dt(key), html.Dd(str(info[key]))]
    return html.Dl(rows) if rows else "No metadata"


@callback(
    Output("cam-select", "options"),
    Output("cam-select", "value"),
    Input("cam-list-refresh", "n_intervals"),
    Input("cam-refresh", "n_clicks"),
    State("cam-select", "value"),
)
def refresh_camera_list(_, __, current):
    """Refresh the camera selector, keeping the selection when possible.

    The value output stays untouched while the selection is still valid:
    re-emitting it would re-fire the loader every interval tick and wipe
    in-progress edits.
    """
    controller, failed = _controller_or_status()
    if failed is not None:
        return [], None
    names = controller.camera_names
    if isinstance(names, NoResult):
        return [], None
    options = [{"label": name, "value": name} for name in names]
    if current in names:
        return options, no_update
    return options, names[0] if names else None


@callback(
    Output("cam-exposure", "value"),
    Output("cam-gain", "value"),
    Output("cam-awb-enable", "value"),
    Output("cam-awb-mode", "value"),
    Output("cam-gains-r", "value"),
    Output("cam-gains-b", "value"),
    Output("cam-full-config", "data"),
    Output("cam-status", "children"),
    Output("cam-status", "color"),
    Output("cam-status", "is_open"),
    Input("cam-select", "value"),
    prevent_initial_call=True,
)
def load_camera(name):
    """Load one camera's live controls into the form."""
    if not name:
        raise PreventUpdate
    controller, failed = _controller_or_status()
    if failed is not None:
        return (None,) * 6 + ({},) + failed + (True,)
    config = controller.get_camera_config(name)
    if isinstance(config, NoResult):
        return (None,) * 6 + ({},) + (f"Failed to read {name}", "danger", True)
    config = dict(config)
    return _form_values(config) + (config, f"Loaded {name}", "success", True)


@callback(
    Output("cam-preview", "src"),
    Output("cam-meta", "children"),
    Output("cam-status", "children", allow_duplicate=True),
    Output("cam-status", "color", allow_duplicate=True),
    Output("cam-status", "is_open", allow_duplicate=True),
    Input("cam-shoot", "n_clicks"),
    State("cam-select", "value"),
    prevent_initial_call=True,
)
def take_picture(_, name):
    """Capture a lores picture and show it with its metadata."""
    if not name:
        raise PreventUpdate
    controller, failed = _controller_or_status()
    if failed is not None:
        return None, "", failed[0], failed[1], True
    res = controller.get_camera_image(name, lores=True)
    if isinstance(res, NoResult):
        return None, "", f"Failed to capture from {name}", "danger", True
    buffer, info = res
    src = "data:image/jpeg;base64," + base64.b64encode(bytes(buffer)).decode("ascii")
    return src, _meta_rows(dict(info)), f"Captured from {name}", "success", True


@callback(
    Output("cam-exposure", "value", allow_duplicate=True),
    Output("cam-gain", "value", allow_duplicate=True),
    Output("cam-awb-enable", "value", allow_duplicate=True),
    Output("cam-awb-mode", "value", allow_duplicate=True),
    Output("cam-gains-r", "value", allow_duplicate=True),
    Output("cam-gains-b", "value", allow_duplicate=True),
    Output("cam-full-config", "data", allow_duplicate=True),
    Output("cam-status", "children", allow_duplicate=True),
    Output("cam-status", "color", allow_duplicate=True),
    Output("cam-status", "is_open", allow_duplicate=True),
    Input("cam-apply", "n_clicks"),
    Input("cam-set-default", "n_clicks"),
    Input("cam-reset", "n_clicks"),
    State("cam-select", "value"),
    State("cam-exposure", "value"),
    State("cam-gain", "value"),
    State("cam-awb-enable", "value"),
    State("cam-awb-mode", "value"),
    State("cam-gains-r", "value"),
    State("cam-gains-b", "value"),
    State("cam-full-config", "data"),
    prevent_initial_call=True,
)
def write_controls(apply, set_default, reset, name, exposure, gain,
                   awb_enable, awb_mode, gains_r, gains_b, full):
    """Apply, persist, or reset one camera's controls, then echo effective."""
    if not name:
        raise PreventUpdate
    controller, failed = _controller_or_status()
    if failed is not None:
        return (None,) * 6 + ({},) + failed + (True,)
    gains = [parse_number(gains_r), parse_number(gains_b)]
    edits = {
        "ExposureTime": parse_number(exposure),
        "AnalogueGain": parse_number(gain),
        "AwbEnable": bool(awb_enable),
        "AwbMode": parse_number(awb_mode),
        "ColourGains": gains if all(g is not None for g in gains) else None,
    }
    triggered = [t["prop_id"] for t in callback_context.triggered]
    if any(t.startswith("cam-reset") for t in triggered):
        effective = controller.reset_camera_controls(name)
        what = "reset"
    elif any(t.startswith("cam-set-default") for t in triggered):
        effective = controller.set_camera_default_controls(
            name, merge_config(full, edits))
        what = "persisted as defaults"
    else:
        effective = controller.set_camera_config(name, merge_config(full, edits))
        what = "applied"
    if isinstance(effective, NoResult):
        return (None,) * 6 + (full or {},) + (f"Failed to write {name}", "danger", True)
    effective = dict(effective)
    return _form_values(effective) + (effective, f"{name} {what}", "success", True)


@callback(
    Output("cam-toml", "value"),
    Output("cam-toml-store", "data"),
    Output("cam-status", "children", allow_duplicate=True),
    Output("cam-status", "color", allow_duplicate=True),
    Output("cam-status", "is_open", allow_duplicate=True),
    Input("cam-copy-toml", "n_clicks"),
    State("cam-select", "value"),
    State("cam-full-config", "data"),
    prevent_initial_call=True,
)
def copy_toml(_, name, full):
    """Render the current controls as a scan-config TOML snippet."""
    if not name or not full:
        raise PreventUpdate
    snippet = build_toml_snippet(name, full)
    return snippet, snippet, "Snippet ready — paste it into the scan config", "info", True


@callback(
    Output("cam-gains-r", "disabled"),
    Output("cam-gains-b", "disabled"),
    Output("cam-gains-hint", "style"),
    Input("cam-awb-enable", "value"),
)
def guard_gains(awb_enable):
    """Disable manual gains while AWB is on (same guard as Qt)."""
    disabled = bool(awb_enable)
    return disabled, disabled, {"display": "block" if disabled else "none"}
