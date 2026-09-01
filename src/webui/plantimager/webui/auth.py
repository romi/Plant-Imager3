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
import requests

from plantdb.client.rest_api.requests import request_token_refresh
from plantdb.client.rest_api.requests import request_token_validation
from plantdb.commons.log import get_logger

logger = get_logger(__name__)


def ensure_valid_token(url: str, port: int | str, prefix: str, ssl: bool,
                       access_token: str, refresh_token: str,
                       username: str | None = None) -> tuple[str, str] | tuple[None, None]:
    """Return ``(access_token, refresh_token)`` with a valid access token.

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

    Returns
    -------
    tuple or tuple[None, None]
        ``(access_token, refresh_token)`` where the returned tokens are
        guaranteed to be fresh and valid, or ``(None, None)`` if the session
        could not be restored (the user must log in again).
    """
    # Try validating the current access token.
    try:
        data = request_token_validation(url, port=port, prefix=prefix, ssl=ssl,
                                        session_token=access_token)
        if isinstance(data, dict) and data.get("user"):
            return access_token, refresh_token
    except requests.exceptions.RequestException as exc:
        logger.info(
            f"ensure_valid_token: access token validation failed for {url}:{port}/{prefix} (user={username}): {exc} — attempting refresh"
        )

    # Validation failed — try refreshing with the refresh token.
    try:
        refreshed = request_token_refresh(url, port=port, prefix=prefix, ssl=ssl,
                                          refresh_token=refresh_token)
        if isinstance(refreshed, dict):
            new_access = refreshed.get("access_token")
            new_refresh = refreshed.get("refresh_token")
            if new_access and new_refresh:
                return new_access, new_refresh
            logger.info(
                f"ensure_valid_token: token refresh returned incomplete data for {url}:{port}/{prefix} (user={username}): {refreshed}"
            )
        else:
            logger.info(
                f"ensure_valid_token: token refresh returned non-dict for {url}:{port}/{prefix} (user={username}): {refreshed!r}"
            )
    except requests.exceptions.RequestException as exc:
        logger.info(
            f"ensure_valid_token: token refresh failed for {url}:{port}/{prefix} (user={username}): {exc}"
        )
    return None, None
