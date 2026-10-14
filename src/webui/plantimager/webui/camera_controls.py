#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Shared camera-control form pieces for the WebUI.

The camera page (``pages/cameras.py``) and the scan cards (step 6) edit
the same five libcamera controls with the same widgets. This module owns
the field specs, the value coercion, and the TOML snippet format so the
two stay identical by construction. Control names and AwbMode labels
come from :mod:`plantimager.commons.camera_controls` — the same table
the Qt panel reads — so the WebUI can never drift from it.
"""

import toml
import tomllib

import dash_bootstrap_components as dbc
from dash import html

from plantimager.commons.camera_controls import AWB_MODES

#: Dropdown options for AwbMode, shared by every camera form.
AWB_OPTIONS = [{"label": name, "value": value} for value, name in AWB_MODES]

#: Form field suffixes, in display order.
FIELDS = ("exposure", "gain", "awb-enable", "awb-mode", "gains-r", "gains-b")


def field_ids(prefix: str) -> dict:
    """Component ids for one camera form instance.

    Parameters
    ----------
    prefix : str
        Id namespace (``"cam"`` for the camera page, ``f"cam-{i}"`` for
        scan card slot ``i``), keeping Dash ids unique across pages.

    Returns
    -------
    dict
        Mapping of field suffix (see :data:`FIELDS`) to component id.
    """
    return {field: f"{prefix}-{field}" for field in FIELDS}


def camera_control_form(prefix: str) -> tuple:
    """Build the five-field camera control form.

    Parameters
    ----------
    prefix : str
        Id namespace, see :func:`field_ids`.

    Returns
    -------
    tuple
        ``(layout, ids)`` with the form layout and its field id mapping.
        Colour gains disable while AwbEnable is on (same guard as Qt);
        wiring the enable/disable + Apply merging is the caller's job.
    """
    ids = field_ids(prefix)
    layout = dbc.Col([
        dbc.Row([
            dbc.Col(dbc.Label("Exposure (µs)"), width=4),
            dbc.Col(dbc.Input(id=ids["exposure"], type="number"), width=8),
        ], className="mb-2 g-1 align-items-center"),
        dbc.Row([
            dbc.Col(dbc.Label("Gain"), width=4),
            dbc.Col(dbc.Input(id=ids["gain"], type="number", step=0.1), width=8),
        ], className="mb-2 g-1 align-items-center"),
        dbc.Row([
            dbc.Col(dbc.Label("Auto WB"), width=4),
            dbc.Col(dbc.Switch(id=ids["awb-enable"]), width=8),
        ], className="mb-2 g-1 align-items-center"),
        dbc.Row([
            dbc.Col(dbc.Label("WB mode"), width=4),
            dbc.Col(dbc.Select(id=ids["awb-mode"], options=AWB_OPTIONS), width=8),
        ], className="mb-2 g-1 align-items-center"),
        dbc.Row([
            dbc.Col(dbc.Label("Gains (R/B)"), width=4),
            dbc.Col(dbc.Input(id=ids["gains-r"], type="number", step=0.01), width=4),
            dbc.Col(dbc.Input(id=ids["gains-b"], type="number", step=0.01), width=4),
        ], className="mb-2 g-1 align-items-center"),
        html.Div("Manual gains need AWB off",
                 id=f"{prefix}-gains-hint",
                 className="text-warning mb-2"),
    ])
    return layout, ids


def parse_number(value):
    """Coerce a form value to a number, ``None`` when empty or garbage.

    Parameters
    ----------
    value : object
        Raw Dash component value (number, numeric string, empty, ...).

    Returns
    -------
    int | float | None
        The number, preserving int-ness (``"5"`` → ``5``), else ``None``
        so callers can keep the previous value.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        try:
            return float(text)
        except ValueError:
            return None


def merge_config(full: dict, edits: dict) -> dict:
    """Merge edited fields over a full snapshot (replace-wholesale safe).

    The server setter replaces the whole dict, so callers must send the
    five edited fields merged over the last-read full config — never the
    five alone, which would drop every other control.
    """
    merged = dict(full or {})
    merged.update({k: v for k, v in edits.items() if v is not None})
    return merged


def build_toml_snippet(name: str, config: dict) -> str:
    """Render a copy/paste TOML snippet for one camera's controls.

    The ``[<name>.config]`` shape matches the scan file convention
    (``assets/config_scan.toml``), so the snippet pastes straight into
    a scan config.
    """
    return toml.dumps({name: {"config": dict(config)}})


def parse_toml_snippet(text: str) -> dict:
    """Parse a pasted snippet back to a control dict.

    Accepts the full ``[<name>.config]`` snippet from
    :func:`build_toml_snippet` as well as bare ``key = value`` lines.

    Raises
    ------
    ValueError
        If the text is not valid TOML or not a control mapping.
    """
    try:
        doc = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"not valid TOML: {exc}") from exc
    if len(doc) == 1:
        ((_, node),) = doc.items()
        if isinstance(node, dict):
            nested = node.get("config")
            if isinstance(nested, dict):
                return dict(nested)
    if all(not isinstance(value, dict) for value in doc.values()):
        return dict(doc)
    raise ValueError("expected a [name.config] snippet or bare key = value lines")
