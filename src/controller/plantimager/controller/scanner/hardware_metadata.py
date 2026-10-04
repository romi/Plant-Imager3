"""Constant description of the Plant Imager hardware rig.

Formerly the ``[Metadata.hardware]`` section of ``config_scan.toml`` (removed
from the config in the MIAPPE-schema update — rig hardware is a constant, not
a per-scan operator input).

Do not mutate: consumers must take a per-instance copy
(``dict(HARDWARE_METADATA)``) before any per-run adjustment.
"""

HARDWARE_METADATA: dict[str, str] = {
    "name": "RDP_PlantImagerv3",
    "frame": "30profile v3",
    "X_motor": "X-Carve NEMA23",
    "Y_motor": "X-Carve NEMA23",
    "Z_motor": "None",
    "pan_motor": "Nema 23 Hollow Shaft 23HS18-2004H",
    "tilt_motor": "None",
    "sensor_1": "PiCamera HQ / Official 6mm lens 3MP",
    "sensor_2": "PiCamera HQ / Official 6mm lens 3MP",
}
