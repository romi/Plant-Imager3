#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Navigation Components for Plant Imager Web UI.

This module provides the navigation bar and related UI components for the Plant Imager web interface.

Key Features
------------
- Responsive Bootstrap navigation bar with ROMI branding
- Integration with configuration and login components
- External links to documentation and tutorials
- Consistent styling with tooltips for user guidance
"""
import dash_bootstrap_components as dbc
from dash import get_asset_url
from dash import get_relative_path
from dash import html

from plantimager.webui.config import cfg_button
from plantimager.webui.config import cfg_tooltip
from plantimager.webui.login import login_avatar_button
from plantimager.webui.login import login_avatar_button_tooltip

#: Link component providing a tutorial link to the Plant Imager documentation page, with a tooltip for user guidance
tutorial_link: dbc.NavLink = dbc.NavLink(
    children=html.I(className="bi bi-journal-text fs-3"),
    id="tutorial-link",
    href="https://docs.romi-project.eu/plant_imager/tutorials/reconstruct_scan/",
    n_clicks=0,
    style={'color': "#f3f3f3"},
)

#: Tooltip component providing help text for the tutorial link
tutorial_tooltip: dbc.Tooltip = dbc.Tooltip(
    children="Tutorials on how to configure a scan",
    target="tutorial-link",
    placement="bottom",
)

#: Tooltip component providing help text for the camera link
camera_tooltip: dbc.Tooltip = dbc.Tooltip(
    children="Camera live view and controls",
    target="camera-link",
    placement="bottom",
)
#: Tooltip component providing help text for the tutorial link
scan_tooltip: dbc.Tooltip = dbc.Tooltip(
    children="Dataset acquisition page",
    target="scan-link",
    placement="bottom",
)

#: Tooltip component providing help text for the tutorial link
dataset_table_tooltip: dbc.Tooltip = dbc.Tooltip(
    children="Dataset table page",
    target="dataset-table-link",
    placement="bottom",
)

def build_navbar_layout() -> dbc.Navbar:
    """Build the main navigation bar with resolved hrefs and asset URLs.

    Hrefs and the logo source are resolved at layout-build time (after the
    Dash app exists), so the initial layout always carries correct URLs
    instead of relying on callbacks that can miss a batch.

    Returns
    -------
    dash_bootstrap_components.Navbar
        The navigation bar layout with resolved links.
    """
    scan_link = dbc.NavLink(
        children=html.I(className="bi bi-camera fs-3"),
        id="scan-link",
        href=get_relative_path("/"),
        n_clicks=0,
        style={'color': "#f3f3f3"},
    )
    camera_link = dbc.NavLink(
        children=html.I(className="bi bi-camera-fill fs-3"),
        id="camera-link",
        href=get_relative_path("/cameras"),
        n_clicks=0,
        style={'color': "#f3f3f3"},
    )
    dataset_table_link = dbc.NavLink(
        children=html.I(className="bi bi-table fs-3"),
        id="dataset-table-link",
        href=get_relative_path("/table"),
        n_clicks=0,
        style={'color': "#f3f3f3"},
    )

    nav_items = [
        dbc.NavItem(children=[login_avatar_button, login_avatar_button_tooltip]),
        dbc.NavItem(children=[tutorial_link, tutorial_tooltip]),
        dbc.NavItem(children=[scan_link, scan_tooltip]),
        dbc.NavItem(children=[camera_link, camera_tooltip]),
        dbc.NavItem(children=[dataset_table_link, dataset_table_tooltip]),
        dbc.NavItem(children=[cfg_button, cfg_tooltip]),
    ]

    return dbc.Navbar(
        dbc.Container([
            # Logo and brand section
            dbc.Row(children=[
                dbc.Col(html.A(
                    html.Img(id="navbar-logo", src=get_asset_url("logo.svg"), height="35px"),
                    href="https://romi-project.eu/",
                    style={"textDecoration": "none"},
                )),
                dbc.Col(
                    dbc.NavbarBrand(
                        id="navbar-brand",
                        children="Plant Imager",
                        href=get_relative_path("/"),
                        style={'color': "#f3f3f3", 'font-size': '30px'}
                    )
                ),
            ], align="center"),
            dbc.Nav(
                children=nav_items,
                navbar=True, className="align-items-center gap-3"
            ),
        ], className="align-items-center"),
        color="#00a960", class_name="mb-3",
    )