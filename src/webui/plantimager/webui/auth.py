#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Token management helpers for the Plant Imager Web UI.

This module centralises the authentication logic of the web UI: it owns the
user's ``access``/``refresh`` token pair and makes token refreshes deliberate
rather than an implicit side-effect of a library call. It runs **only in the
main web UI process**, so the rotated token pair can be written back to the
Dash Stores and the background scan process never needs to touch user
credentials (it only receives a scoped per-scan API token).
"""
from plantdb.client.plantdb_client import PlantDBClient
from plantdb.client.rest_api.urls import plantdb_url


def ensure_valid_token(url: str, port: int | str, prefix: str, ssl: bool,
                       access_token: str, refresh_token: str, username: str) -> tuple[PlantDBClient, str, str] | tuple[None, None, None]:
    """Return ``(client, access_token, refresh_token)`` with a valid access token.

    The token pair is refreshed **explicitly** whenever the supplied access
    token is no longer accepted, so the resulting rotation is intentional and
    the caller can persist the new pair back to the Dash Stores.

    Parameters
    ----------
    url : str
        The hostname or IP address of the PlantDB REST API server.
    port : int or str
        The port number of the PlantDB REST API server.
    prefix : str
        The prefix of the PlantDB REST API server.
    ssl : bool
        Whether the PlantDB REST API server is using SSL.
    access_token : str
        The current PlantDB REST API access token.
    refresh_token : str
        The current PlantDB REST API refresh token.
    username : str
        The logged-in username. Setting it prevents the implicit token
        refresh inside :meth:`PlantDBClient.validate_token`.

    Returns
    -------
    tuple or tuple[None, None, None]
        ``(client, access_token, refresh_token)`` where the returned tokens
        are guaranteed to be fresh and valid, or ``(None, None, None)`` if the
        session could not be restored (the user must log in again).
    """
    client = PlantDBClient(plantdb_url(url, port=port, prefix=prefix, ssl=ssl))
    client._access_token = access_token
    client._refresh_token = refresh_token
    # Set the username so `validate_token` does not silently rotate the pair.
    client._username = username
    if not client.validate_token(access_token):
        if not client.refresh_token():
            return None, None, None
    return client, client._access_token, client._refresh_token
