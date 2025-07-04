#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import numpy as np
import dash_bootstrap_components as dbc

def plotly_image_carousel(images, height=900, width=900, title="Carousel", layout_kwargs=None):
    """An image carousel based on Plotly.

    Parameters
    ----------
    images : list
        The list of image to represent, should be convertible into numpy array.
    height : float, optional
        The height of the figure to create, in pixels.
        Defaults to ``900``.
    width : float, optional
        The width of the figure to create, in pixels.
        Defaults to ``900``.
    title : str, optional
        The title to give to the figure.
        Defaults to ``"Carousel"``.
    layout_kwargs : dict, optional
        A dictionary to customize the figure layout.

    Returns
    -------
    plotly.graph_objects.Figure
        The plotly figure to display.

    See Also
    --------
    plotly.graph_objects.Figure

    References
    ----------
    Plotly documentation for `Layout`: https://plotly.com/python/reference/layout/

    """
    import plotly.express as px

    layout_style = {'height': height, 'width': width, 'title': title, 'showlegend': False,
                    'xaxis': {'visible': False}, 'yaxis': {'visible': False}}
    if isinstance(layout_kwargs, dict):
        layout_style.update(layout_kwargs)

    array = np.array([np.array(img) for img in images])
    fig = px.imshow(array, animation_frame=0, binary_string=True, labels=dict(animation_frame="Image"))
    fig.update_layout(**layout_style)
    fig.update_scenes(aspectmode='data')

    return fig


def dash_boostrap_carousel(images: list[str]):
    images.sort()
    carousel = dbc.Carousel(
        items=[{"key": idx, "src": img} for idx, img in enumerate(images)],
        controls=True,
        indicators=True,
        slide=False,
        class_name="carousel-fade",
    )
    return carousel