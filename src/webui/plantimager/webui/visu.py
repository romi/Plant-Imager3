#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from concurrent.futures.thread import ThreadPoolExecutor
from typing import Any
from typing import Dict
from typing import Optional

import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from dash_bootstrap_components import Carousel

# Type aliases for clarity
ImageLike = Any  # Any object convertible to a numpy array
Figure = go.Figure
LayoutDict = Dict[str, Any]


def plotly_image_carousel(
        images: list[ImageLike],
        height: float = 900.0,
        width: float = 900.0,
        title: str = "Carousel",
        layout_kwargs: Optional[LayoutDict] = None,
) -> Figure:
    """An image carousel based on Plotly.

    Parameters
    ----------
    images : list[ImageLike]
        The list of images to represent, each of which should be convertible into a ``numpy.ndarray``.
    height : float, optional
        The height of the figure to create, in pixels. Defaults to ``900``.
    width : float, optional
        The width of the figure to create, in pixels. Defaults to ``900``.
    title : str, optional
        The title to give to the figure. Defaults to ``"Carousel"``.
    layout_kwargs : dict[str, Any] | None, optional
        A dictionary to customize the figure layout. If provided, it will be merged with the
        default layout style.

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
    layout_style: LayoutDict = {
        "height": height,
        "width": width,
        "title": title,
        "showlegend": False,
        "xaxis": {"visible": False},
        "yaxis": {"visible": False},
    }
    if isinstance(layout_kwargs, dict):
        layout_style.update(layout_kwargs)

    array: np.ndarray = np.array([np.array(img) for img in images])
    fig: Figure = px.imshow(
        array,
        animation_frame=0,
        binary_string=True,
        labels=dict(animation_frame="Image"),
    )
    fig.update_layout(**layout_style)
    fig.update_scenes(aspectmode='data')

    return fig


def dash_boostrap_carousel(images: list[str], access_token: Optional[str]) -> Carousel:
    """
    Creates a Bootstrap Carousel component from a list of image URLs.

    Parameters
    ----------
    images
        A list of image URLs to include in the carousel.
    access_token : Optional[str]
        A access token used to authenticate against PlantDB.

    Returns
    -------
    Carousel
        A Dash Bootstrap Components Carousel.

    Notes
    -----
    The image URLs are sorted alphabetically before being added to the carousel.
    """
    from plantimager.webui.utils import load_image_from_url

    images.sort()

    with ThreadPoolExecutor(max_workers=4) as pool:
        encoded_images = list(pool.map(lambda img: load_image_from_url(img, access_token), images))
    carousel = Carousel(
        items=[{"key": idx, "alt": img.split('/')[-1], "src": encoded_images[idx]} for idx, img in
               enumerate(images)],
        controls=True,
        indicators=True,
        slide=False,
        class_name="carousel-fade",
    )
    return carousel
