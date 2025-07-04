#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import dash_bootstrap_components as dbc
from dash import Input
from dash import Output
from dash import State
from dash import callback
from dash import dcc
from dash import html
from plantdb.client.rest_api import get_tasks_fileset_from_api
from plantdb.client.rest_api import list_task_images_uri

from plantimager.webui.utils import IMAGE_TASKS
from plantimager.webui.visu import dash_boostrap_carousel


@callback(
    Output('select-image-task', 'options'),
    Input("carousel-modal", "is_open"),
    State('view-dataset', 'data'),
    State('rest-api-host', 'data'),
    State('rest-api-port', 'data'),
    State('rest-api-prefix', 'data'),
)
def update_image_task_dropdown(open_modal, dataset_id, host, port, prefix):
    """Updates the dropdown options for image tasks based on the dataset and API configuration.

    This callback function is triggered when the carousel modal is opened or closed. It fetches
    the available tasks for a given dataset from the API and filters them against predefined
    IMAGE_TASKS to provide relevant options for the dropdown.

    Parameters
    ----------
    open_modal : bool
        State of the carousel modal (True if open, False if closed).
    dataset_id : str or None
        Identifier of the selected dataset. Can be None or empty string if no dataset is selected.
    host : str
       The hostname or IP address of the PlantDB REST API server.
    port : int
        The port number of the PlantDB REST API server.
    prefix : str
        The prefix of the PlantDB REST API server.

    Returns
    -------
    list of str
        List of available image task options. Returns ['images'] if the modal is closed
        or no dataset is selected. Otherwise returns the intersection of IMAGE_TASKS and
        the tasks available for the selected dataset.

    """
    if not open_modal or dataset_id is None or dataset_id == '':
        return ['images']
    tasks_fileset = get_tasks_fileset_from_api(dataset_id, host=host, port=port, prefix=prefix)
    return [task for task in IMAGE_TASKS if task in tasks_fileset]


@callback(Output('carousel', 'children'),
          # Output('carousel', 'figure'),
          Input("carousel-modal", "is_open"),
          Input("select-image-task", "value"),
          State('view-dataset', 'data'),
          State('rest-api-host', 'data'),
          State('rest-api-port', 'data'),
          State('rest-api-prefix', 'data'),
          )
def images_carousel(open_modal, image_task, dataset_id, host, port, prefix):
    """Create a Dash carousel component displaying images from a specified dataset task.

    This callback function generates a Bootstrap-styled carousel component for displaying
    images associated with a specific task in a dataset. The carousel is only generated
    when the modal is open and a valid dataset ID is provided.

    Parameters
    ----------
    open_modal : bool
        Flag indicating whether the carousel modal is open
    image_task : str
        Name of the image processing task to display images from
    dataset_id : str
        Identifier of the dataset to retrieve images from
    host : str
       The hostname or IP address of the PlantDB REST API server.
    port : int
        The port number of the PlantDB REST API server.
    prefix : str
        The prefix of the PlantDB REST API server.

    Returns
    -------
    dash_bootstrap_components.Carousel or None
        A Bootstrap carousel component containing the task images if conditions are met,
        None if the modal is closed or dataset_id is invalid
    """
    if not open_modal or dataset_id is None or dataset_id == '':
        return None

    images = list_task_images_uri(dataset_id, task_name=image_task, size='orig', host=host, port=port, prefix=prefix)

    # fig_layout_kwargs = {'font_family': FONT_FAMILY, 'paper_bgcolor': "#F3F3F3",
    #                      'autosize': True, 'margin': {'t': 25, 'b': 5}, 'width': None, 'height': None}
    # fig = plotly_image_carousel(images, title=dataset_id, layout_kwargs=fig_layout_kwargs)
    # fig.update_layout(uirevision='value')
    # # Remove the axis ticks and labels:
    # fig.update_layout(xaxis={'visible': False}, yaxis={'visible': False})
    # return fig
    return dash_boostrap_carousel(images)


caroussel_modal = dbc.Modal(children=[
    dbc.ModalHeader(
        dbc.ModalTitle(
            children="Carousel",
            id='carousel-modal-title'
        )
    ),
    dbc.ModalBody(children=[
        # Add a dropdown selector for task images to use as images sources:
        html.Div([
            "Select image task:",
            dcc.Dropdown(
                id="select-image-task",
                value='images',
                options=['images'],
                clearable=False,
                searchable=False,
                multi=False,
            ),
        ], style={"width": "200px"}
        ),
        # Part where the carousel will be displayed:
        # dcc.Loading([dcc.Graph(id='carousel', style={'height': '84vh'}, config={'responsive': True})])
        # For explanations on 'config={'responsive': True}', see:
        # https://dash.plotly.com/dash-core-components/graph#graph-resizing-and-responsiveness
        dcc.Loading(children=[], id='carousel')
    ])
], id='carousel-modal', is_open=False, size="lg",
)
