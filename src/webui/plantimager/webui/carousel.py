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

from plantimager.webui.utils import FONT_FAMILY
from plantimager.webui.utils import IMAGE_TASKS
from plantimager.webui.visu import plotly_image_carousel


# Callback to initialize the available dropdown option (list of image related tasks):
@callback(
    Output('select-image-task', 'options'),
    Input('dataset-id', 'data'),
    State('rest-api-host', 'data'),
    State('rest-api-port', 'data')
)
def update_image_task_dropdown(dataset_id, host, port):
    tasks_fileset = get_tasks_fileset_from_api(dataset_id, host=host, port=port)
    return [task for task in IMAGE_TASKS if task in tasks_fileset]


@callback(Output('carousel', 'figure'),
          Input('view-dataset', 'data'),
          Input("select-image-task", "value"),
          State('rest-api-host', 'data'),
          State('rest-api-port', 'data'))
def images_carousel(dataset_id, task, host, port):
    images = list_task_images_uri(dataset_id, task_name=task, size='orig', host=host, port=port)
    fig_layout_kwargs = {'font_family': FONT_FAMILY, 'paper_bgcolor': "#F3F3F3",
                         'autosize': True, 'margin': {'t': 25, 'b': 5}, 'width': None, 'height': None}
    fig = plotly_image_carousel(images, title=None, layout_kwargs=fig_layout_kwargs)
    fig.update_layout(uirevision='value')

    # Remove the axis ticks and labels:
    fig.update_layout(xaxis={'visible': False}, yaxis={'visible': False})
    return fig


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
                clearable=False,
                searchable=False,
                multi=False,
            ),
        ], style={"width": "200px"}
        ),
        # Part where the carousel will be displayed:
        dcc.Loading([dcc.Graph(id='carousel', style={'height': '84vh'}, config={'responsive': True})])
        # For explanations on 'config={'responsive': True}', see:
        # https://dash.plotly.com/dash-core-components/graph#graph-resizing-and-responsiveness
    ])
], id='carousel-modal', is_open=False, size="lg",
)
