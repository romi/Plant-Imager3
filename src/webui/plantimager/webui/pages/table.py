#!/usr/bin/env python
# -*- coding: utf-8 -*-

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
from plantdb.client.rest_api import plantdb_url

from plantimager.webui.utils import get_dataset_dict
from plantimager.webui.utils import load_image_from_url

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

# Main container for the table view
layout = html.Div([
    # Navigation bar containing the back button, refresh button, and help
    html.Div([
        # Back button with the left arrow icon
        dbc.Button([html.I(className="bi bi-arrow-left me-2"), "Back"],
                   id='back-button', color="secondary", outline=True, n_clicks=0, href=""),
        # Container for refresh and help buttons
        html.Div([
            # Refresh button with a rotating arrow icon
            dbc.Button([html.I(className="bi bi-arrow-clockwise me-2"), "Refresh"],
                       id='refresh-table-button', color="primary", outline=True, n_clicks=0),
            # Help button with a question mark icon
            dbc.Button([html.I(className="bi bi-question-lg")],
                       id='home-table-help', color="secondary", outline=True, n_clicks=0),
            # Help popover that appears when the help button is clicked
            dbc.Popover([
                dbc.PopoverHeader("Help!"),
                dbc.PopoverBody([
                    # Sorting instructions
                    html.P(["You may sort the table by clicking on a column header."]),
                    # Filtering instructions
                    html.P(["Except for the 'Thumbnail' & 'Action' columns,",
                            "you can filter the displayed data by columns using the ",
                            html.I(className="bi bi-list"),
                            " icon that appears on hover and typing a query."]),
                    # Task filter specifics
                    html.P(["Note that the tasks column filters are `Yes` or `No`."]),
                    # Column reordering instruction
                    html.P(["You can drag the columns to reorder them."])
                ])
            ], target="home-table-help", trigger='legacy'),
        ], style={'display': 'flex', 'gap': '10px', 'marginLeft': 'auto'}),
    ], id="table-nav",
        style={"width": "100%", 'display': 'flex', 'justifyContent': 'space-between',
               'margin-bottom': '5px', 'alignItems': 'center'},
    ),

    # Loading component that shows the spinner while data is being fetched
    dcc.Loading(children=[
        # Container for the dataset table
        html.Div(
            id="dataset-table",
            children=[
                # Hidden div for storing DAG data that will be populated dynamically
                html.Div(id="plantdb-dag", style={"display": "none"}),
            ],
            style={"margin-left": "auto", "margin-right": "auto",
                   "display": "flex", "justifyContent": "center"}
        )
    ], target_components={"dataset-dict": "data", "dataset-table": "children"}),
])


@callback(
    Output("back-button", "href"),
    Input('url', 'pathname')
)
def update_back_button_href(_):
    """Update the href of the back button."""
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

    if col_name in ["Thumbnail"]:
        cdef["cellRenderer"] = "markdown"
        cdef["cellStyle"] |= {
            'justifyContent': 'center',  # horizontal centering
        }
    elif col_name == "Action":
        cdef["cellRenderer"] = "DBC_Dual_Buttons"  # Use the new dual button renderer
        # Add extra width to accommodate two buttons
        cdef["width"] = 200

    return cdef


# Handle the refresh button click - only active on the table page
@callback(
    Output('dataset-dict', 'data', allow_duplicate=True),
    Output('refresh-table-button', 'n_clicks'),
    Input('refresh-table-button', 'n_clicks'),
    State('plantdb-host', 'data'),
    State('plantdb-port', 'data'),
    State('plantdb-prefix', 'data'),
    State('plantdb-ssl', 'data'),
    State('access-token', 'data'),
    prevent_initial_call=True
)
def refresh_table_data(n_clicks, host, port, prefix, ssl, access_token):
    """Refresh the dataset dictionary.

    Parameters
    ----------
    n_clicks : int
        The number of times the button has been clicked.
    url : str
        The URL of the page.
    host : str
       The hostname or IP address of the PlantDB REST API server.
    port : int
        The port number of the PlantDB REST API server.
    prefix : str
        The prefix of the PlantDB REST API server.
    ssl : bool
        Whether the PlantDB REST API server is using SSL or not.
    access_token
        The PlantDB REST API access token.

    """
    if n_clicks > 0:
        dataset_dict = get_dataset_dict(host=host, port=port, prefix=prefix, ssl=ssl, session_token=access_token)
        return dataset_dict, 0
    return dash.no_update, 0


# Handle URL-based updates - works globally
@callback(
    Output('dataset-dict', 'data'),
    Input('url', 'pathname'),
    State('plantdb-host', 'data'),
    State('plantdb-port', 'data'),
    State('plantdb-prefix', 'data'),
    State('plantdb-ssl', 'data'),
    State('access-token', 'data'),
)
def update_on_url_change(url, host, port, prefix, ssl, access_token):
    """Update the dataset dictionary when the URL changes.

    Parameters
    ----------
    url : str
        The URL of the page.
    host : str
       The hostname or IP address of the PlantDB REST API server.
    port : int
        The port number of the PlantDB REST API server.
    prefix : str
        The prefix of the PlantDB REST API server.
    ssl : bool
        Whether the PlantDB REST API server is using SSL or not.
    access_token
        The PlantDB REST API access token.
    """
    if url.endswith('/table'):
        return get_dataset_dict(host=host, port=port, prefix=prefix, ssl=ssl, session_token=access_token)
    return dash.no_update


@callback(Output('dataset-table', 'children'),
          Input('dataset-dict', 'data'),
          State('plantdb-host', 'data'),
          State('plantdb-port', 'data'),
          State('plantdb-prefix', 'data'),
          State('plantdb-ssl', 'data'),
          State('access-token', 'data'))
def update_table(dataset_dict, host, port, prefix, ssl, access_token):
    """Update the AG Grid table.

    Parameters
    ----------
    dataset_dict : dict
        The currently stored dataset dictionary.
    host : str
        The hostname or IP address of the PlantDB REST API server.
    port : int
        The port number of the PlantDB REST API server.
    prefix : str
        The prefix of the PlantDB REST API server.
    ssl : bool
        Whether the PlantDB REST API server is using SSL or not.
    access_token : str
        AN access token used to authenticate against PlantDB.

    Returns
    -------
    dash_ag_grid.AgGrid
        The AG Grid to display.
    """
    thumb_size = 150  # max width or height
    if dataset_dict is not None:
        table_dict = {col: [] for col in ["Thumbnail", "Name", "Action", "Date", "Species", "Images"]}
        url = plantdb_url(host, port=port if not prefix else None, prefix=prefix, ssl=ssl)

        for ds_id, md in dataset_dict.items():
            thumbnail_url = md["thumbnailUri"].replace('thumb', f'{thumb_size}')
            full_url = url.rstrip('/') + '/' + thumbnail_url
            img_data = load_image_from_url(full_url, access_token)
            # Include the first image thumbnail and a link to the carousel
            table_dict["Thumbnail"].append(f"![{ds_id}]({img_data})")
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
    """
    Display a carousel modal dialog based on cell data from a plantdb-dag component.

    This callback function manages the visibility and content of a carousel modal
    dialog that displays dataset information. It processes cell renderer data
    from a plantdb-dag component to extract dataset information and controls
    the modal's state.

    Parameters
    ----------
    cell_data : dict or None
        Cell renderer data from the plantdb-dag component. Expected to contain
        a 'rowId' key with the dataset name. If None, the modal will be closed.

    Returns
    -------
    str or None
        The name of the dataset to be displayed
    bool
        Boolean flag indicating whether the modal should be open (True) or closed (False)
    str
        The title to be displayed in the modal header
    """
    if cell_data is None:
        return None, False, "Carousel"

    try:
        # If using row data, you can access it through:
        dataset_name = cell_data.get('rowId', None)
        return dataset_name, True, f"Carousel - {dataset_name}"
    except Exception as e:
        print(f"Error in show_carousel_modal: {e}")
        return None, False, "Carousel"
