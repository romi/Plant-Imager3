#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from dash import html
from dash import register_page

from plantimager.webui.scan import scan_layout

register_page(__name__, path='/')

layout = html.Div(
    children=[scan_layout],
    style={"margin": 20}
)
