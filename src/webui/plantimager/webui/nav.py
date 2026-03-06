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
import os

import dash_bootstrap_components as dbc
from dash import Input
from dash import Output
from dash import callback
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

#: Link component pointing to the home (page
scan_link: dbc.NavLink = dbc.NavLink(
    children=html.I(className="bi bi-camera fs-3"),
    id="scan-link",
    href="",  # Use get_relative_path to handle prefixes,
    n_clicks=0,
    style={'color': "#f3f3f3"},
)

#: Tooltip component providing help text for the tutorial link
scan_tooltip: dbc.Tooltip = dbc.Tooltip(
    children="Dataset acquisition page",
    target="scan-link",
    placement="bottom",
)

#: Link component providing a tutorial link to the Plant Imager documentation page, with a tooltip for user guidance
dataset_table_link: dbc.NavLink = dbc.NavLink(
    children=html.I(className="bi bi-table fs-3"),
    id="dataset-table-link",
    href="",  # Use get_relative_path to handle prefixes,
    n_clicks=0,
    style={'color': "#f3f3f3"},
)

#: Tooltip component providing help text for the tutorial link
dataset_table_tooltip: dbc.Tooltip = dbc.Tooltip(
    children="Dataset table page",
    target="dataset-table-link",
    placement="bottom",
)

#: Get the directory where the current file is located
current_dir = os.path.dirname(os.path.abspath(__file__))

# Callback to update the ROMI project logo (used in the navigation bar) src once the app is running
@callback(
    Output("navbar-logo", "src"),
    Input("url", "pathname")
)
def update_logo_url(_):
    return current_dir + "/.." + get_asset_url("logo.svg")

# Then update the href through a callback when the app starts
@callback(
    Output("scan-link", "href"),
    Input('url', 'pathname')
)
def update_scan_link_href(_):
    return get_relative_path("/")


# Then update the href of the dataset table page through a callback when the app starts
@callback(
    Output("dataset-table-link", "href"),
    Input('url', 'pathname')
)
def update_table_link_href(_):
    return get_relative_path("/table")


#: Define main navigation items including scan, database, and documentation links
nav_items: list = [
    dbc.NavItem(children=[login_avatar_button, login_avatar_button_tooltip]),
    dbc.NavItem(children=[tutorial_link, tutorial_tooltip]),
    dbc.NavItem(children=[scan_link, scan_tooltip]),
    dbc.NavItem(children=[dataset_table_link, dataset_table_tooltip]),
    dbc.NavItem(children=[cfg_button, cfg_tooltip]),
]

#: Construct a responsive navigation bar with ROMI logo and branding
navbar_layout = dbc.Navbar(
    dbc.Container([
        # Logo and brand section
        html.A(
            dbc.Row(children=[
                dbc.Col(html.Img(id="navbar-logo", height="35px")),
                dbc.Col(
                    dbc.NavbarBrand(
                        id="navbar-brand",
                        children="Plant Imager",
                        href="/",
                        style={'color': "#f3f3f3", 'font-size': '30px'}
                    )
                ),
            ], align="center"),
            href="https://romi-project.eu/",
            style={"textDecoration": "none"},
        ),
        dbc.Nav(
            children=nav_items,
            navbar=True, className="align-items-center"
        ),
    ], className="align-items-center"),
    color="#00a960", class_name="mb-3",
)


# Callback to update NavbarBrand href
@callback(
    Output("navbar-brand", "href"),
    Input('plantdb-prefix', 'data')
)
def update_navbar_brand_href(prefix):
    if prefix:
        return prefix
    return "/"