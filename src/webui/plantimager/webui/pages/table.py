#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#  Copyright (c) 2022 Univ. Lyon, ENS de Lyon, UCB Lyon 1, CNRS, INRAe, Inria
#  All rights reserved.
#  This file is part of the TimageTK library, and is released under the "GPLv3"
#  license. Please see the LICENSE.md file that should have been included as
#  part of this package.
# ------------------------------------------------------------------------------

import dash
import dash_ag_grid as dag
import dash_bootstrap_components as dbc
import pandas as pd
from dash import Input
from dash import Output
from dash import State
from dash import callback
from dash import dcc
from dash import get_relative_path
from dash import html
from dash import register_page
from plantdb.client.rest_api import base_url

from plantimager.webui.utils import get_dataset_dict

register_page(__name__, path='/table')

# -----------------------------------------------------------------------------
# Table
# -----------------------------------------------------------------------------

TASKS = [
    "Colmap",
    "PointCloud",
    "TriangleMesh",
    "CurveSkeleton",
    "TreeGraph",
    "AnglesAndInternodes",
]

layout = html.Div([
    html.Div([
        dbc.Button([html.I(className="bi bi-arrow-left me-2"), "Back"],
                   id='back-button', color="secondary", outline=True, n_clicks=0, href=""),
        html.Div([
            dbc.Button([html.I(className="bi bi-arrow-clockwise me-2"), "Refresh"],
                       id='refresh-table-button', color="primary", outline=True, n_clicks=0),
            dbc.Button([html.I(className="bi bi-question-lg")],
                       id='home-table-help', color="secondary", outline=True, n_clicks=0),
            dbc.Popover([
                dbc.PopoverHeader("Help!"),
                dbc.PopoverBody([
                    html.P(["You may sort the table by clicking on a column header."]),
                    html.P(["Except for the 'Thumbnail' & 'Action' columns,",
                            "you can filter the displayed data by columns using the ",
                            html.I(className="bi bi-list"),
                            " icon that appears on hover and typing a query."]),
                    html.P(["Note that the tasks column filters are `Yes` or `No`."]),
                    html.P(["You can drag the columns to reorder them."])
                ])
            ], target="home-table-help", trigger='legacy'),
        ], style={'display': 'flex', 'gap': '10px', 'marginLeft': 'auto'}),
    ], id="table-nav",
        style={"width": "100%", 'display': 'flex', 'justifyContent': 'space-between',
               'margin-bottom': '5px', 'alignItems': 'center'},
    ),
    dcc.Loading(children=[
        html.Div(
            id="dataset-table",
            children=[
                # Add an empty div with the ID that will be updated later
                html.Div(id="plantdb-dag", style={"display": "none"}),
            ],
            style={"margin-left": "auto", "margin-right": "auto",
                   "display": "flex", "justifyContent": "center"}
        )
    ], target_components={"dataset-dict": "data", "dataset-table": "children"}),
])


# Add this callback to handle the back button href
@callback(
    Output("back-button", "href"),
    Input('url', 'pathname')
)
def update_back_button_href(_):
    return get_relative_path("/")


def _column_defs(col_name):
    """Set the properties of the AG Grid columns."""
    no_filter_cols = ["Thumbnail", "Action"]
    cdef = {"field": col_name, 'filter': True if col_name not in no_filter_cols else False}
    cdef["cellStyle"] = {
        'display': 'flex',  # Using flexbox for centering
        'alignItems': 'center',  # Vertical centering
        'height': '100%'  # Ensure the cell takes full height
    }
    # Enable markdown rendering to include images and icons:
    # if col_name in ["Thumbnail"]:
    #     cdef["field"] = "img"
    #     cdef["cellRenderer"] = "ImgThumbnail"
    #     cdef["width"] = 100
    if col_name in ["Thumbnail"]:
        cdef["cellRenderer"] = "markdown"
        cdef["cellStyle"] |= {
            'justifyContent': 'center',  # horizontal centering
        }
    elif col_name == "Action":
        cdef["cellRenderer"] = "DBC_Button_Simple"  # defined in assets/dashAgGridComponentFunctions.js

    return cdef


# Handle the refresh button click - only active on the table page
@callback(
    Output('dataset-dict', 'data', allow_duplicate=True),
    Output('refresh-table-button', 'n_clicks'),
    Input('refresh-table-button', 'n_clicks'),
    State('rest-api-host', 'data'),
    State('rest-api-port', 'data'),
    State('rest-api-prefix', 'data'),
    prevent_initial_call=True
)
def refresh_table_data(n_clicks, host, port, prefix):
    if n_clicks > 0:
        dataset_dict = get_dataset_dict(host=host, port=port, prefix=prefix)
        return dataset_dict, 0
    return dash.no_update, 0


# Handle URL-based updates - works globally
@callback(
    Output('dataset-dict', 'data'),
    Input('url', 'pathname'),
    State('rest-api-host', 'data'),
    State('rest-api-port', 'data'),
    State('rest-api-prefix', 'data')
)
def update_on_url_change(url, host, port, prefix):
    if url.endswith('/table'):
        return get_dataset_dict(host=host, port=port, prefix=prefix)
    return dash.no_update


@callback(Output('dataset-table', 'children'),
          Input('dataset-dict', 'data'),
          State('rest-api-host', 'data'),
          State('rest-api-port', 'data'))
def update_table(dataset_dict, url, port):
    """Update the AG Grid table.

    Parameters
    ----------
    dataset_dict : dict
        The currently stored dataset dictionary.
    host : str
       The IP address of the PlantDB REST API.
    port : int
        The port of the PlantDB REST API.

    Returns
    -------
    dash_ag_grid.AgGrid
        The AG Grid to display.
    """
    thumb_size = 150  # max width or height
    if dataset_dict is not None:
        table_dict = {col: [] for col in ["Thumbnail", "Name", "Action", "Date", "Species", "Images"]}
        plantdb_url = base_url(url, port)

        for ds_id, md in dataset_dict.items():
            thumbnail_url = md["thumbnailUri"].replace('thumb', f'{thumb_size}')
            # Include the first image thumbnail and a link to the carousel
            table_dict["Thumbnail"].append(f"![{ds_id}]({plantdb_url}{thumbnail_url})")
            table_dict["Name"].append(ds_id)
            table_dict["Action"].append("Open")
            table_dict["Date"].append(md["metadata"]["date"])
            table_dict["Species"].append(md["metadata"]["species"])
            table_dict["Images"].append(md["metadata"]["nbPhotos"])

        df = pd.DataFrame().from_dict(table_dict)
        table = dag.AgGrid(
            id="plantdb-dag",
            rowData=df.to_dict("records"),
            columnDefs=[_column_defs(col) for col in df.columns],
            getRowId="params.data.Name",
            dashGridOptions={
                "rowHeight": 120,
                "animateRows": False,
                "pagination": True,
                "paginationAutoPageSize": True,
            },
            persistence=True,
            persisted_props=["filterModel"],
            columnSize="autoSize",
            style={"margin": "auto auto", "height": "80vh"},
        )
    else:
        table = "No dataset loaded yet!"
    return table


@callback(
    Output("view-dataset", "data"),
    Output("carousel-modal", "is_open"),
    Output("carousel-modal-title", "children"),
    Input("plantdb-dag", "cellRendererData"),
)
def show_carousel_modal(cell_data):
    if cell_data is None:
        return None, False, "Carousel"

    try:
        # If using row data, you can access it through:
        dataset_name = cell_data.get('rowId', None)
        return dataset_name, True, f"Carousel - {dataset_name}"
    except Exception as e:
        print(f"Error in show_carousel_modal: {e}")
        return None, False, "Carousel"
