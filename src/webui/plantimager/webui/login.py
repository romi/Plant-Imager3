#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""User Authentication Module for Plant Imager Web UI.

This module provides components and callbacks for user authentication in the Plant Imager web interface,
including login, logout, and user profile management.

Key Features
------------
- User authentication with username and password
- User profile display with dynamically generated avatars
- Login/logout modal interface with Bootstrap styling
- REST API integration for authentication services
- Secure password handling
"""

import hashlib
import time

import dash_bootstrap_components as dbc
import requests
from dash import Input
from dash import Output
from dash import State
from dash import callback
from dash import html
from plantdb.client.rest_api import request_check_username
from plantdb.client.rest_api import request_login
from plantdb.client.rest_api import request_logout
from plantdb.client.rest_api import request_token_validation

from plantimager.webui.new_user import new_user_button


def create_avatar(fullname: str) -> html.Div | None:
    """Create an avatar with user's initials in a colored circle.

    Generates a circular avatar component containing the initials of a user's full name
    with a background color uniquely derived from the name using MD5 hashing.

    Parameters
    ----------
    fullname : str
        The full name of the user. Can contain multiple names separated by spaces.

    Returns
    -------
    dash.html.Div or None
        A Dash HTML Div component containing the user's initials with styled
        background, or ``None`` if fullname is empty.

    Notes
    -----
    - Background color is deterministically generated from the fullname using MD5 hash
    - Avatar is rendered as a 35x35px circle with centered text
    - Initials are automatically capitalized
    - Multiple word names will use the first letter of each word
    """
    if not fullname:
        return None

    # Get initials from fullname
    initials = ''.join(name[0].upper() for name in fullname.split() if name)
    # Generate a consistent color based on the fullname
    color_hash = hashlib.md5(fullname.encode('utf-8')).hexdigest()
    bg_color = f"#{color_hash[:6]}"
    avatar_style = {
        'backgroundColor': bg_color,
        'color': 'white',
        'borderRadius': '50%',
        'width': '35px',
        'height': '35px',
        'display': 'flex',
        'alignItems': 'center',
        'justifyContent': 'center',
        'fontSize': '14px',
        'fontWeight': 'bold',
    }
    return html.Div(initials, style=avatar_style)


def create_login_button(is_logged_in: bool = False, user_fullname: str | None = None) -> dbc.NavLink:
    """Create a login/logout button with avatar for the navigation bar.

    This function generates a navigation link component that displays either a default
    person icon (when logged out) or a user avatar (when logged in). The avatar is
    created using the user's full name initials.

    Parameters
    ----------
    is_logged_in : bool, optional
        Flag indicating whether a user is currently logged in.
        Default is ``False``.
    user_fullname : str or None, optional
        The full name of the logged-in user. Used to create the avatar display.
        Default is ``None``.

    Returns
    -------
    dash_bootstrap_components.NavLink
        A Bootstrap NavLink component containing either:
        - A user avatar (when logged in)
        - A default person icon (when logged out)

    See Also
    --------
    create_avatar : Function used to generate the user avatar display
    """
    if is_logged_in and user_fullname:
        return dbc.NavLink(
            children=create_avatar(user_fullname),
            id="login-avatar-button",
            n_clicks=0
        )
    else:
        return dbc.NavLink(
            children=html.I(className="bi bi-person-bounding-box fs-3"),
            id="login-avatar-button",
            n_clicks=0,
            style={'color': "#f3f3f3"},
        )


login_button_tooltip = dbc.Tooltip(
    children="Login to the Plant Imager",
    target="login-avatar-button",
    placement="bottom",
)

# Create login button components for the navigation bar
login_button = create_login_button()


def login_title(fullname: str | None = None, username: str | None = None) -> list:
    """Create a title for the login modal based on user login status.

    Parameters
    ----------
    fullname : str or None, optional
        The full name of the logged-in user, by default None
    username : str or None, optional
        The username of the logged-in user, by default None

    Returns
    -------
    list
        A list of components for the modal title, either showing the user's name and username
        or a default login icon and text
    """
    icon = html.I(className="bi bi-person-bounding-box me-2")
    if fullname:
        return [f"{fullname} (@{username})"]
    else:
        return [icon, "Login"]


login_modal = dbc.Modal(children=[
    dbc.ModalHeader(
        dbc.ModalTitle(id='login-modal-title')
    ),
    dbc.ModalBody(children=[
        # Username input, e.g., "username" or "firstname"
        dbc.InputGroup(children=[
            dbc.InputGroupText(
                html.I(className="bi bi-person")  # Alternatives: bi-person-badge, bi-at
            ),
            dbc.FormFloating(
                [
                    dbc.Input(
                        id='username-input',
                        type='text',
                        placeholder="Username",
                        persistence=True,
                        n_submit=0,
                        n_submit_timestamp=-1
                    ),
                    dbc.Label("Username", html_for="username-input"),
                ]),
        ], id='username-input-group', className="mb-3"),
        # Password input, e.g., "<PASSWORD>" or "<PASSWORD>"
        dbc.InputGroup(children=[
            dbc.InputGroupText(
                html.I(className="bi bi-key")  # Alternatives: bi-lock, bi-shield-lock
            ),
            dbc.FormFloating(
                [
                    dbc.Input(
                        id='password-input',
                        type='password',
                        placeholder="Password",
                        n_submit=0,
                        n_submit_timestamp=-1
                    ),
                    dbc.Label("Password", html_for="password-input"),
                ]),
        ], id='password-input-group'),
        # Messages placeholders
        html.Div(children=[
            dbc.Alert("Try to log-in first...", color="info", class_name="mb-0")
        ], id='login-attempt-message', style={'display': 'none'}, className="mt-3"),
    ]),
    dbc.ModalFooter(
        children=[
            new_user_button,
            # Login button
            dbc.Button(
                children=[
                    html.I(className="bi bi-box-arrow-right me-2"),  # Alternative: bi-check2-circle
                    'Login'
                ],
                id='login-button',
                n_clicks=0,
                disabled=False,
                class_name="me-2"
            ),
            # Logout button
            dbc.Button(
                children=[
                    html.I(className="bi bi-box-arrow-left me-2"),  # Alternative: bi-door-open
                    'Logout'
                ],
                id='logout-button',
                n_clicks=0,
                disabled=True,
                class_name="me-2"
            )
        ])
], id='login-modal', is_open=True, backdrop='static')


@callback(Output("login-modal", "is_open", allow_duplicate=True),
          Input('login-avatar-button', 'n_clicks'),
          State('login-modal', 'is_open'),
          State('logged-username', 'data'),
          prevent_initial_call=True)
def toggle_login_modal(_: int, is_open: bool, username: str | None) -> bool | None:
    """Toggle the visibility of the login modal.

    This callback function controls the visibility of the login modal when the login avatar button is clicked.

    Parameters
    ----------
    _ : int
        Number of clicks on the login avatar button (unused parameter)
    is_open : bool
        Current state of the login modal visibility

    Returns
    -------
    bool
        ``True`` to open the modal, ``False`` otherwise

    Notes
    -----
    The function only handles opening the modal. Closing is handled by other modal mechanisms
    """
    if not username:
        return True
    return not is_open


@callback(
    Output('username-input', 'valid'),
    Output('username-input', 'invalid'),
    Input('username-input', 'value'),
    State('login-modal', 'is_open'),
    State('plantdb-host', 'data'),
    State('plantdb-port', 'data'),
    State('plantdb-prefix', 'data'),
    State('plantdb-ssl', 'data'),
)
def validate_username(username: str | None, is_modal_open: bool, host: str, port: int | str, prefix: str, ssl: bool) -> \
        tuple[bool, bool]:
    """Validate a username by checking if it exists in the database.

    Parameters
    ----------
    username : str or None
        The username to validate
    is_modal_open : bool
        Whether the login modal is currently open
    host : str
       The hostname or IP address of the PlantDB REST API server.
    port : int
        The port number of the PlantDB REST API server.
    prefix : str
        The prefix of the PlantDB REST API server.
    ssl : bool
        Flag indicating whether SSL (HTTPS) is enabled.

    Returns
    -------
    tuple[bool, bool]
        A tuple of (valid, invalid) flags for the username input field

    Raises
    ------
    requests.exceptions.RequestException
        If there are network connectivity issues or server communication problems
    """
    if not is_modal_open or not username:
        return False, False

    # Check if username already exists in the backend before proceeding
    res_data = request_check_username(host, username, port=port, prefix=prefix, ssl=ssl).json()
    user_exists = res_data.get('exists', False)  # True if username is taken
    return user_exists, not user_exists


@callback(Output('logged-username', 'data', allow_duplicate=True),
          Output('logged-fullname', 'data', allow_duplicate=True),
          Output('session-token', 'data', allow_duplicate=True),
          Output('login-attempt-message', 'style'),
          Output('login-attempt-message', 'children'),
          Input('username-input', 'n_submit'),
          Input('password-input', 'n_submit'),
          Input('login-button', 'n_clicks'),
          State('username-input', 'value'),
          State('password-input', 'value'),
          State('plantdb-host', 'data'),
          State('plantdb-port', 'data'),
          State('plantdb-prefix', 'data'),
          State('plantdb-ssl', 'data'),
          prevent_initial_call=True)
def login(
        username_submit: int,
        password_submit: int,
        n_clicks: int,
        username: str,
        password: str,
        host: str,
        port: int | str,
        prefix: str,
        ssl: bool
) -> tuple[str | None, str | None, str | None, dict, dbc.Alert]:
    """Handle user authentication through the REST API.

    This callback function processes login attempts by sending credentials to a REST API endpoint
    and handling the response appropriately. It manages both successful and failed login attempts,
    including various error conditions.

    Parameters
    ----------
    username_submit : int or None
        Number of times the username input has been submitted via Enter key.
    password_submit : int or None
        Number of times the password input has been submitted via Enter key.
    n_clicks : int or None
        Number of times the login button has been clicked.
    username : str
        Username entered in the login form.
    password : str
        Password entered in the login form.
    host : str
       The hostname or IP address of the PlantDB REST API server.
    port : int
        The port number of the PlantDB REST API server.
    prefix : str
        The prefix of the PlantDB REST API server.
    ssl : bool
        Flag indicating whether SSL (HTTPS) is enabled.

    Returns
    -------
    str or None
        The authenticated username if login successful, ``None`` otherwise.
    str or None
        The user's full name if login successful, ``None`` otherwise.
    str or None
        The session token if login successful, ``None`` otherwise.
    dict
        CSS style dictionary for the message display.
    dash_bootstrap_components.Alert
        Bootstrap alert component containing success or error message.

    Raises
    ------
    requests.exceptions.RequestException
        If there are network connectivity issues or server communication problems.
    json.JSONDecodeError
        If the server response cannot be parsed as JSON.

    Notes
    -----
    Authentication state is maintained through Dash Store components in the application layout.
    """
    message_style = {'display': 'block', 'margin-top': '10px'}

    try:
        # Send login request to REST API endpoint
        loggin_data = request_login(host, username, password, port=port, prefix=prefix, ssl=ssl).json()
        login_msg = loggin_data['message']

        if 'user' in loggin_data:
            # Parse successful response
            fullname = loggin_data['user']['fullname']
            session_token = loggin_data['access_token']
            # Setup success message display
            alert = dbc.Alert(login_msg, color="success", class_name="mb-0")
            return username, fullname, session_token, message_style, alert

        # Handle failed login attempts
        error_msg = "Login failed. Please check your credentials."
        if 'message' in loggin_data:
            error_msg = login_msg

        alert = dbc.Alert(error_msg, color="danger", class_name="mb-0")
        return None, None, None, message_style, alert

    except requests.exceptions.RequestException as e:
        # Handle connection errors (network issues, server down, etc.)
        alert = dbc.Alert(f"Connection error: {str(e)}", color="danger", class_name="mb-0")
        return None, None, None, message_style, alert


@callback(
    Output('logged-username', 'data', allow_duplicate=True),
    Output('logged-fullname', 'data', allow_duplicate=True),
    Output('session-token', 'data', allow_duplicate=True),
    Input('session-token', 'data'),
    State('plantdb-host', 'data'),
    State('plantdb-port', 'data'),
    State('plantdb-prefix', 'data'),
    State('plantdb-ssl', 'data'),
    prevent_initial_call=True,
)
def restore_login(session_token, host, port, prefix, ssl):
    """
    If a session token exists in session storage, verify it with the API
    and populate the logged‑in stores. This runs on every page load.
    """
    if not session_token:
        return None, None, None

    try:
        # API endpoint that returns user info given a token
        user = request_token_validation(host, port=port, prefix=prefix, ssl=ssl, session_token=session_token).json()[
            'user']
        return user['username'], user['fullname'], session_token
    except Exception:
        # If the token is invalid, clear it so we don't keep an old one
        return None, None, None


@callback(
    Output("login-avatar-button", "children"),
    Input("logged-fullname", "data")
)
def update_login_avatar_button(fullname: str | None) -> list:
    """Update the login avatar button display based on user login status.

    This callback function modifies the login button appearance in the navigation bar
    to reflect whether a user is logged in or not. When logged in, it displays the
    user's full name; when logged out, it shows the default login button.

    Parameters
    ----------
    fullname : str or None
        The full name of the logged-in user. None if no user is logged in.

    Returns
    -------
    list
        A list of Dash components representing the children of the login button.
        The content varies based on login status.

    See Also
    --------
    create_login_button : The underlying function that creates the button components
    """
    if fullname:
        return create_login_button(
            is_logged_in=True,
            user_fullname=fullname
        ).children
    return create_login_button(is_logged_in=False).children


@callback(
    Output("login-modal-title", "children"),
    Input("logged-fullname", "data"),
    Input("logged-username", "data"),
)
def update_login_modal_title(fullname: str | None, username: str | None) -> list:
    """Updates the title of the login modal window dynamically based on the logged-in
    user's information. If the logged-in user's full name is available, it uses the
    provided full name and username to generate the title. Otherwise, it defaults
    to a generic title.

    Parameters
    ----------
    fullname : str or None
        The full name of the logged-in user.
        If ``None``, the default title is used instead.
    username : str or None
        The username of the logged-in user.
        Used in combination with the full name to generate the title.
        If ``None``, the default title is used.

    Returns
    -------
    str
        The dynamically generated title for the login modal window. This either
        includes the logged-in user's full name and username or a default message
        if no user information is provided.
    """
    if fullname:
        return login_title(fullname, username)
    return login_title()


@callback(
    Output("username-input-group", "style", allow_duplicate=True),
    Output("password-input-group", "style", allow_duplicate=True),
    Output("login-attempt-message", "children", allow_duplicate=True),
    Input("logged-fullname", "data"),
    State("login-attempt-message", "children"),
    prevent_initial_call=True,
)
def update_login_modal_body(fullname: str | None, msg: dbc.Alert) -> tuple[dict, dict, str]:
    """Update the visibility of login modal components based on login status.

    This callback controls the display of username and password input groups in the login modal,
    as well as any login attempt messages, based on whether a user is logged in.

    Parameters
    ----------
    fullname : str or None
        The full name of the logged-in user. ``None`` if no user is logged in.

    Returns
    -------
    dict
        Style dictionary for username-input-group component
    dict
        Style dictionary for password-input-group component
    str
        Login-attempt-message component (empty string in this case)

    Examples
    --------
    >>> update_login_modal_body(None)
    ({'display': 'flex'}, {'display': 'flex'}, "")
    >>> update_login_modal_body("John Doe")
    ({'display': 'none'}, {'display': 'none'}, "")
    """
    if not fullname:
        return {'display': 'flex'}, {'display': 'flex'}, msg
    return {'display': 'none'}, {'display': 'none'}, ""


@callback(
    Output("login-modal", "is_open", allow_duplicate=True),
    Input("logged-username", "data"),
    prevent_initial_call=True,
)
def timeout_modal(username: str | None) -> bool:
    """Control the visibility of the login-modal with a timeout.

    This callback automatically closes the login-modal after a 1-second delay
    when a user successfully logs in.

    Parameters
    ----------
    username : str or None
        The username of the logged-in user. None if no user is logged in.

    Returns
    -------
    bool
        ``False`` if a user is logged in (closes modal), ``True`` otherwise (keeps modal open)

    Notes
    -----
    The function includes a 1-second sleep delay to provide time for the logout callback to unset the username.
    """
    time.sleep(1)
    if username:
        return False  # close the login modal
    else:
        return True  # keep the login modal open


@callback(
    Output('logged-username', 'data', allow_duplicate=True),
    Output('logged-fullname', 'data', allow_duplicate=True),
    Output('session-token', "data", allow_duplicate=True),
    Output('login-attempt-message', 'style', allow_duplicate=True),
    Output("login-attempt-message", "children", allow_duplicate=True),
    Input('logout-button', 'n_clicks'),
    State('plantdb-host', 'data'),
    State('plantdb-port', 'data'),
    State('plantdb-prefix', 'data'),
    State('plantdb-ssl', 'data'),
    State('session-token', 'data'),
    prevent_initial_call=True,
)
def logout(_: int, host: str, port: int | str, prefix: str, ssl: bool, session_token: str) -> tuple[
    str | None, str | None, str | None, dict, dbc.Alert]:
    """Handle user logout functionality.

    This callback clears the user session data when the logout button is clicked.

    Parameters
    ----------
    _ : int
        Placeholder for the click event of the 'logout-button' (unused).
    host : str
       The hostname or IP address of the PlantDB REST API server.
    port : int
        The port number of the PlantDB REST API server.
    prefix : str
        The prefix of the PlantDB REST API server.
    ssl : bool
        Flag indicating whether SSL (HTTPS) is enabled.
    session_token
        The PlantDB REST API session token.

    Returns
    -------
    None
        Clears the logged username.
    None
        Clears the logged full name.
    None
        Clears the session token.
    dict
        CSS style dictionary for the message display.
    dash_bootstrap_components.Alert
        Bootstrap alert component containing success or error message.
    """
    message_style = {'display': 'block', 'margin-top': '10px'}

    if not session_token:
        alert = dbc.Alert(f"Missing session token, you need to login first!", color="danger", className="mb-0")
        return None, None, None, message_style, alert

    try:
        # Send login request to REST API endpoint
        response = request_logout(host, port=port, prefix=prefix, ssl=ssl, session_token=session_token)

    except requests.exceptions.RequestException as e:
        # Handle connection errors (network issues, server down, etc.)
        alert = dbc.Alert(f"Connection error: {str(e)}", color="danger", class_name="mb-0")
        return None, None, None, message_style, alert

    logout_msg = response.json().get('message')
    if response:
        # Parse successful response
        alert = dbc.Alert(logout_msg, color="success", class_name="mb-0")
        return None, None, None, message_style, alert
    else:
        alert = dbc.Alert(logout_msg, color="warning", class_name="mb-0")
        return None, None, None, message_style, alert


@callback(
    Output("logout-button", "disabled"),
    Input("logged-username", "data"),

)
def disable_logout_button(username: str | None) -> bool:
    """Control the enabled/disabled state of the logout button.

    This callback toggles the disabled state of the logout button based on whether
    a user is currently logged in.

    Parameters
    ----------
    username : str or None
        The username of the logged-in user. ``None`` if no user is logged in.

    Returns
    -------
    bool
        ``True`` if the logout button should be disabled (no user logged in),
        ``False`` if the button should be enabled (user is logged in).
    """
    if username:
        return False
    return True
