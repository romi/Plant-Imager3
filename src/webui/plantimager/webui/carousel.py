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
from plantimager.webui.visu import dash_boostrap_carousel
from plantimager.webui.visu import plotly_image_carousel


# Callback to initialize the available dropdown option (list of image related tasks):
@callback(
    Output('select-image-task', 'options'),
    Input("carousel-modal", "is_open"),
    State('view-dataset', 'data'),
    State('rest-api-host', 'data'),
    State('rest-api-port', 'data'),
    State('rest-api-prefix', 'data'),
)
def update_image_task_dropdown(open_modal, dataset_id, host, port, prefix):
    if not open_modal or dataset_id is None or dataset_id == '':
        return ['images']
    tasks_fileset = get_tasks_fileset_from_api(dataset_id, host=host, port=port, prefix=prefix)
    return [task for task in IMAGE_TASKS if task in tasks_fileset]


@callback(Output('carousel', 'children'),
            #Output('carousel', 'figure'),
          Input("carousel-modal", "is_open"),
          Input("select-image-task", "value"),
          State('view-dataset', 'data'),
          State('rest-api-host', 'data'),
          State('rest-api-port', 'data'),
          State('rest-api-prefix', 'data'),
          )
def images_carousel(open_modal, image_task, dataset_id, host, port, prefix):
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
        #dcc.Loading([dcc.Graph(id='carousel', style={'height': '84vh'}, config={'responsive': True})])
        # For explanations on 'config={'responsive': True}', see:
        # https://dash.plotly.com/dash-core-components/graph#graph-resizing-and-responsiveness
        dcc.Loading(children=[], id='carousel')
    ])
], id='carousel-modal', is_open=False, size="lg",
)
