"""Shared camera-control vocabulary for the controller and WebUI.

Both UIs edit the same small set of libcamera controls and must show the
same names for the same values. This module owns that vocabulary so the
Qt control panel (via ``CameraBridge``) and the WebUI camera page read
one table instead of each hardcoding its own.

The AwbMode names come from libcamera (``control_ids_core.yaml``) and
are confirmed against the rig in ``docs/camera-tuning.md``; the value
``5`` (daylight) is the rig default (see ``Camera.DEFAULT_CONTROLS``).
"""

AWB_MODES = (
    (0, "Auto"),
    (1, "Incandescent"),
    (2, "Tungsten"),
    (3, "Fluorescent"),
    (4, "Indoor"),
    (5, "Daylight"),
    (6, "Cloudy"),
    (7, "Custom"),
)
"""AwbMode value/name pairs (libcamera enum, 0-7)."""

COMMON_CONTROLS = (
    "ExposureTime",
    "AnalogueGain",
    "AwbEnable",
    "AwbMode",
    "ColourGains",
)
"""v1 editable set (locked 2026-10-13): the rig-relevant controls.

``ColourGains`` only takes effect with ``AwbEnable`` off; UIs must
disable its editor otherwise instead of letting users set ignored
values (and must never write ``(0, 0)``, which silently re-enables
AWB — see ``docs/camera-tuning.md``).
"""


def awb_mode_name(value):
    """Human name for an AwbMode value, ``"?"`` when unknown.

    Parameters
    ----------
    value : int
        Libcamera AwbMode enum value (0-7).

    Returns
    -------
    str
        The mode name, or ``"?"`` for values outside the table (e.g.
        from a newer libcamera than this table).
    """
    return dict(AWB_MODES).get(value, "?")
