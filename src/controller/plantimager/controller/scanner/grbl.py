#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""GRBL-based CNC Controller for Plant Imaging Systems.

A concrete implementation of CNC machine control for 3D plant imaging systems using the GRBL firmware.
This module enables precise XYZ positioning with millimeter accuracy for X/Y axes and degree accuracy for the rotational Z axis.

Key Features:
- Serial communication with GRBL controller boards
- Complete 3-axis (X, Y, Z) movement control with position tracking
- Support for both synchronous and asynchronous operations
- Safety features including position limits and homing procedures
- Comprehensive access to GRBL firmware settings
- Proper error handling and machine status reporting
- Hardware abstraction layer compliant with AbstractCNC interface

Usage Examples:
```python
>>> from plantimager.controller.scanner.grbl import CNC
>>> cnc = CNC("/dev/ttyUSB0")  # Connect to GRBL controller
>>> cnc.home()  # Perform a homing sequence
>>> cnc.moveto(100, 100, 45)  # Move to position (100mm, 100mm, 45°)
>>> x, y, z = cnc.get_position()  # Get the current position
>>> cnc.moveto_async(200, 200, 90)  # Start asynchronous movement
>>> cnc.wait()  # Wait for movement completion
```
"""

import re
import time
import traceback
from weakref import finalize

import numpy as np
import serial

from plantimager.commons.logging import create_logger
from .hal import AbstractCNC
from .units import deg, time_s
from .units import length_mm

logger = create_logger(__name__)

#: Regular expression pattern for parsing GRBL status messages to extract X,Y,Z coordinates.
pos_regex = re.compile("MPos:(-?[0-9]+.[0-9]+),(-?[0-9]+.[0-9]+),(-?[0-9]+.[0-9]+)")

#: Dictionary mapping the GRBL codes to their meaning, units and default values.
GRBL_SETTINGS = {
    "$0": ("Step pulse", "microseconds", 10),
    "$1": ("Step idle delay", "milliseconds", 255),
    "$2": ("Step port invert", "mask", 0),
    "$3": ("Direction port invert", "mask", 7),
    "$4": ("Step enable invert", "boolean", 0),
    "$5": ("Limit pins invert", "boolean", 0),
    "$6": ("Probe pin invert", "boolean", 0),
    "$10": ("Status report", "mask", 115),
    "$11": ("Junction deviation", "mm", 0.02),
    "$12": ("Arc tolerance", "mm", 0.002),
    "$13": ("Report inches", "boolean", 0),
    "$20": ("Soft limits", "boolean", 0),
    "$21": ("Hard limits", "boolean", 0),
    "$22": ("Homing cycle", "boolean", 1),
    "$23": ("Homing dir invert", "mask", 4),
    "$24": ("Homing feed", "mm/min", 200),
    "$25": ("Homing seek", "mm/min", 1000),
    "$26": ("Homing debounce", "milliseconds", 250),
    "$27": ("Homing pull-off", "mm", 20),
    "$30": ("Max spindle speed", "RPM", 12000),
    "$31": ("Min spindle speed", "RPM", 0),
    "$32": ("Laser mode", "boolean", 0),
    "$100": ("X steps/mm", "steps/mm", 80),
    "$101": ("Y steps/mm", "steps/mm", 80),
    "$102": ("Z steps/deg", "steps/deg", 8.88889),
    "$110": ("X Max rate", "mm/min", 6000),
    "$111": ("Y Max rate", "mm/min", 6000),
    "$112": ("Z Max rate", "deg/min", 1500),
    "$120": ("X Acceleration", "mm/sec^2", 500),
    "$121": ("Y Acceleration", "mm/sec^2", 500),
    "$122": ("Z Acceleration", "deg/sec^2", 50),
    "$130": ("X Max travel", "mm", 740),
    "$131": ("Y Max travel", "mm", 740),
    "$132": ("Z Max travel", "deg", 360 - 8)  # 8 degree offset from encoder 0
}

def angle_min_travel(current_angle: deg, desired_angle: deg) -> deg:
    """Calculate the postion of the machine to achieve a desired angle with minimal travel.
    Minimal travel means that machine_order-current_angle is in [-180, 180]
    """
    if (desired_angle - current_angle) % 360 > 180:
        return current_angle - 360 + (desired_angle - current_angle) % 360
    else:
        return current_angle + (desired_angle - current_angle) % 360

def angle_min_travel_distance(current_angle: deg, desired_angle: deg) -> deg:
    """Calculate the minimal angle the machine has to turn to achieve a desired angle with minimal travel.
    Minimal travel means that machine_order-current_angle is in [-180, 180]
    """
    if (desired_angle - current_angle) % 360 > 180:
        return - 360 + (desired_angle - current_angle) % 360
    else:
        return (desired_angle - current_angle) % 360

class CNC(AbstractCNC):
    """A concrete implementation of CNC machine control using GRBL firmware.

    This class provides functionality to control a CNC machine running GRBL firmware
    over a serial connection. It supports movement along X, Y, and Z axes, homing,
    position queries, and both synchronous and asynchronous operations.

    Attributes
    ----------
    port : str
        Serial port used for communication
    baud_rate : int
        Communication baudrate (typically 115200 for Arduino UNO)
    x_lims : tuple[float, float]
        Allowed range for X-axis movement
    y_lims : tuple[float, float]
        Allowed range for Y-axis movement
    z_lims : tuple[float, float]
        Allowed range for Z-axis movement (rotationa axis)
    serial_port : serial.Serial
        Serial connection instance
    invert_x : bool
        Whether to invert X-axis direction
    invert_y : bool
        Whether to invert Y-axis direction
    invert_z : bool
        Whether to invert Z-axis direction
    grbl_settings : dict
        Current GRBL configuration parameters

    Notes
    -----
    - All movements are performed in absolute coordinates (G90 mode)
    - Units are set to millimeters (G21 mode)
    - Position limits are enforced for safety
    - Homing is performed on startup

    Examples
    --------
    >>> from plantimager.controller.scanner.grbl import CNC
    >>> cnc = CNC("/dev/ttyACM0")  # Initialize CNC connection
    >>> cnc.home()  # Perform homing sequence
    >>> cnc.moveto(100, 100, 50)  # Move to position synchronously
    >>> x, y, z = cnc.get_position()  # Get current position
    >>> cnc.moveto_async(200, 200, 50)  # Move asynchronously
    >>> cnc.wait()  # Wait for move to complete

    Raises
    ------
    ValueError
        If movement coordinates are outside allowed limits
    RuntimeError
        If unable to read position from CNC
    SerialException
        If serial communication fails

    References
    ----------
    - GRBL Commands: https://github.com/gnea/grbl/wiki/Grbl-v1.1-Commands
    - G-Code Reference: http://linuxcnc.org/docs/html/gcode/g-code.html
    """

    def __init__(self, port: str="/dev/ttyUSB0", baud_rate: int=115200) -> None:
        """Initializes the GRBL controller."""
        super().__init__()
        self.port = port
        self.baud_rate = baud_rate
        self.x_lims = (-1, -1)
        self.y_lims = (-1, -1)
        self.z_lims = (-1, -1)
        self.invert_x = False
        self.invert_y = False
        self.invert_z = False
        self.serial_port = None
        self.grbl_settings = None
        self._start()
        finalize(self, self.stop)

    def _start(self) -> None:
        """Initialize the serial connection with Arduino and configure the GRBL-based CNC machine.

        This method establishes a serial connection with the Arduino running GRBL firmware,
        configures initial GRBL settings, performs homing, and sets up the coordinate system.

        Notes
        -----
        - Serial communication is established with a 1-second timeout
        - The method waits 2 seconds after initial connection for GRBL to initialize
        - Axis inversion is determined by reading GRBL setting ``$3`` (direction port invert mask)
        - Machine is configured to use:
            * Absolute distance mode (``G90``)
            * Metric units (``G21``)
        - Axis limits are set based on GRBL settings ``$130``, ``$131``, and ``$132``

        References
        ----------
        - ``G90``/``G91`` Mode: http://linuxcnc.org/docs/html/gcode/g-code.html#gcode:g90-g91
        - ``G20``/``G21`` Units: http://linuxcnc.org/docs/html/gcode/g-code.html#gcode:g20-g21

        Raises
        ------
        serial.SerialException
            If unable to establish serial connection
        RuntimeError
            If GRBL settings cannot be retrieved or applied
        """
        # Initialize serial connection with timeout of 1 second
        self.serial_port = serial.Serial(self.port, self.baud_rate, timeout=1)
        self.has_started = True

        # Send carriage returns to wake up GRBL
        self.serial_port.write("\r\n\r\n".encode())
        # Wait for GRBL to initialize
        time.sleep(2)
        # Clear input buffer
        self.serial_port.flushInput()

        # Apply all GRBL configuration settings from a predefined dictionary
        for code, (_, _, value) in GRBL_SETTINGS.items():
            self.send_cmd(f"{code}={value}", wait=True, timeout=1)

        # Get current GRBL settings
        self.grbl_settings = self.get_grbl_settings()

        # Parse direction port invert mask (setting $3) to determine axis inversions
        invert_mask = self.grbl_settings["$3"]
        self.invert_x = bool(invert_mask & 1)  # Bit 0 controls X axis
        self.invert_y = bool(invert_mask & 2)  # Bit 1 controls Y axis
        self.invert_z = bool(invert_mask & 4)  # Bit 2 controls Z axis

        # Run a homing cycle to find machine zero
        self.home()

        # Configure the machine to use absolute coordinates (G90) and metric units (G21)
        self.send_cmd("g90")  # Absolute distance mode
        self.send_cmd("g21")  # Millimeter units

        # Set axis travel limits using GRBL settings $130-$132 (max travel distances)
        self.x_lims = (0, self.grbl_settings["$130"])
        self.y_lims = (0, self.grbl_settings["$131"])
        self.z_lims = (0, self.grbl_settings["$132"])

    def stop(self) -> None:
        """Close the serial connection to the GRBL controller.

        Notes
        -----
        It's recommended to call this method in a try/finally block to ensure proper cleanup

        Raises
        ------
        SerialException
            If there's an error while closing the serial port
        """
        if self.has_started:
            self.serial_port.close()

    def compute_move_time(self, x: length_mm, y: length_mm, z: deg) -> time_s:
        """Compute the estimated time required to move the CNC machine to the specified coordinates."""
        pos = self.get_position() # [mm, mm, deg]
        logger.debug(f"position: {pos}, desired position: ({x}, {y}, {z})")
        dist = np.array(pos) - np.array([x, y, z]) # [mm, mm, deg]
        dist[2] = angle_min_travel_distance(z, pos[2])
        dist = np.abs(dist)
        logger.debug(f"distance: {dist}")
        #dist[2] = angle_min_travel(pos[2], z)
        max_speed = np.array([self.grbl_settings["$110"], self.grbl_settings["$111"], self.grbl_settings["$112"]])/60 # mm/s, mm/s, deg/s
        acceleration = np.array([self.grbl_settings["$120"], self.grbl_settings["$121"], self.grbl_settings["$122"]])

        # compute the time it would take to reach maximum speed on each axis
        acceleration_to_max_speed_time = max_speed / acceleration #  [s, s, s]

        # compute max speed as if the maximum speed is not reached (accelerate for half the time then decelerate for the other half)
        t_acc = np.sqrt(dist/acceleration) #  [s, s, s]
        v_max = np.zeros(3)
        v_max[t_acc!=0] = dist[t_acc!=0]/t_acc[t_acc!=0]
        times = t_acc*2

        # if v_max > than maximum speed of the machine then compute corrected times
        times2 = (dist - acceleration_to_max_speed_time*max_speed)/max_speed
        times[v_max>max_speed] = times2[v_max>max_speed]

        logger.debug(f"estimated travel times {times}")
        return times.max()

    def get_position(self) -> tuple[length_mm, length_mm, deg]:
        """Get the current XYZ position of the CNC machine by querying GRBL controller.

        Returns
        -------
        length_mm
            Current X-axis position in millimeters
        length_mm
            Current Y-axis position in millimeters
        deg
            Current Z-axis position in degrees

        Raises
        ------
        RuntimeError
            If unable to parse position data from the GRBL response
        serial.SerialException
            If communication with the serial port fails

        Notes
        -----
        - Position values are returned in absolute coordinates (``G90`` mode)
        - The method expects GRBL to be properly configured and responding to status queries
        - Z-axis is treated as rotational, hence returned in degrees
        - Response parsing uses regex to extract position values from a GRBL status message
        """
        # Send status query command '?' to GRBL
        self.serial_port.write("?\n".encode("ascii"))
        # Read machine position response from GRBL
        res = self.serial_port.readline()
        # Skip 'ok' confirmation message
        self.serial_port.readline()  # b'ok\r\n'

        # Decode and clean up response string
        res = res.decode("ascii").strip()
        # Extract X, Y,Z coordinates using a regex pattern
        match = pos_regex.search(res)
        if match:
            # If match found, extract the three position values
            x, y, z = match.groups()
            x = -float(x) if self.invert_x else float(x)
            y = -float(y) if self.invert_y else float(y)
            z = -float(z) if self.invert_z else float(z)
        else:
            # If no match found, position data is invalid
            raise RuntimeError("Error reading position from cnc")

        # Return current position as tuple of (x,y,z) coordinates
        return x, y, z

    @property
    def x(self) -> length_mm:
        """Get the current X-axis position of the CNC machine.

        Returns
        -------
        length_mm
            The current X-axis position in millimeters.

        Raises
        ------
        RuntimeError
            If unable to read position from CNC controller.
        SerialException
            If serial communication with GRBL fails.

        See Also
        --------
        - y : Y-axis position property
        - z : Z-axis position property
        - get_position : Method to get a complete X,Y,Z position tuple
        """
        return self.get_position()[0]

    @property
    def y(self) -> length_mm:
        """Get the current Y-axis position of the CNC machine.

        Returns
        -------
        length_mm
            The current Y-axis position in millimeters.

        Raises
        ------
        RuntimeError
            If unable to read position from CNC controller.
        SerialException
            If serial communication with GRBL fails.

        See Also
        --------
        - x : X-axis position property
        - z : Z-axis position property
        - get_position : Method to get a complete X,Y,Z position tuple
        """
        return self.get_position()[1]

    @property
    def z(self) -> deg:
        """Get the current Z-axis position of the CNC machine.

        Returns
        -------
        deg
            The current Z-axis position in degrees.

        Raises
        ------
        RuntimeError
            If unable to read position from CNC controller.
        SerialException
            If serial communication with GRBL fails.

        See Also
        --------
        - x : X-axis position property
        - y : Y-axis position property
        - get_position : Method to get a complete X,Y,Z position tuple
        """
        return self.get_position()[2]

    def home(self) -> None:
        """Performs the GRBL homing cycle and sets machine coordinates.

        Notes
        -----
        The homing procedure consists of two steps:
        1. Execute GRBL homing cycle (``$H``)
        2. Account for pull-off distance by setting machine coordinates (``G92``)

        The final position is affected by three GRBL settings:
        - ``$27``: Homing pull-off distance
        - ``$23``: Homing direction mask
        - ``$3``: Direction port invert mask

        Raises
        ------
        RuntimeError
            If GRBL reports an error during homing or coordinate setting

        References
        ----------
        - GRBL Homing Cycle: https://github.com/gnea/grbl/wiki/Grbl-v1.1-Commands#h---run-homing-cycle
        - ``G92`` Reference: http://linuxcnc.org/docs/html/gcode/g-code.html#gcode:g92
        """
        # Execute GRBL homing cycle to find machine zero
        self.send_cmd("$H", wait=True, timeout=60)

        # Get GRBL settings that affect homing behavior
        pulloff = self.grbl_settings["$27"]  # Distance machine moves after finding the limit switch
        pulloff_mask = self.grbl_settings["$23"]  # Determines positive/negative homing direction
        dir_mask = self.grbl_settings["$3"]  # Inverts motor direction signals
        x_max, y_max, z_max = self.grbl_settings["$130"], self.grbl_settings["$131"], self.grbl_settings["$132"]

        # Calculate direction signs for each axis based on homing and direction masks
        # XOR operation determines if a pull-off direction should be inverted
        sign_x = -1 if dir_mask & 1 else 1  # Check bit 0 for X axis
        sign_y = -1 if dir_mask & 2 else 1  # Check bit 1 for Y axis
        sign_z = -1 if dir_mask & 4 else 1  # Check bit 2 for Z axis

        # Set machine coordinates to account for pull-off distance
        # G92 sets the current position without moving the machine
        x_init = sign_x * (x_max - pulloff) if pulloff_mask & 1 else sign_x * pulloff  # if homing dir is inverted, homing to max range
        y_init = sign_y * (y_max - pulloff) if pulloff_mask & 2 else sign_y * pulloff
        z_init = sign_z * (z_max - pulloff) if pulloff_mask & 4 else sign_z * pulloff
        self.send_cmd(f"g92 x{x_init} y{y_init} z{z_init}", wait=True, timeout=10)

    def _check_move(self, x: float, y: float, z: float) -> None:
        """Validate that the requested movement coordinates are within the machine's axis limits.

        No limit on z axis rotation

        Parameters
        ----------
        x : float
            The target X-axis position in millimeters
        y : float
            The target Y-axis position in millimeters
        z : float
            The target Z-axis position in degrees (rotary axis)

        Raises
        ------
        AssertionError
            If any coordinate (x, y) is outside its defined limits
        """
        assert self.x_lims[0] <= x <= self.x_lims[1], "Move command coordinates is outside the x-limits!"
        assert self.y_lims[0] <= y <= self.y_lims[1], "Move command coordinates is outside the y-limits!"

    def moveto(self, x: length_mm, y: length_mm, z: deg) -> None:
        """Move the CNC machine to specified coordinates and wait until the target position is reached.

        Parameters
        ----------
        x : length_mm
            Target position along the X-axis in millimeters. Must be within the
            machine's x_lims range.
        y : length_mm
            Target position along the Y-axis in millimeters. Must be within the
            machine's y_lims range.
        z : deg
            Target position along the Z-axis in degrees. Must be within the
            machine's z_lims range.

        Raises
        ------
        ValueError
            If any of the target coordinates are outside the allowed limits defined
            in x_lims, y_lims, or z_lims.
        RuntimeError
            If the movement cannot be completed or position verification fails.

        Notes
        -----
        - The movement is performed in absolute coordinates (``G90`` mode)
        - Units are in millimeters (``G21`` mode)
        - The method will block until the movement is complete
        """
        # Validate that the target coordinates are within machine limits
        self._check_move(x, y, z)

        z = angle_min_travel(self.z, z)
        travel_time = self.compute_move_time(x, y, z)
        travel_time += min(travel_time * 0.1, 1)

        # Apply axis inversions based on machine configuration
        # Convert coordinates to integers for GRBL compatibility
        x = int(-x) if self.invert_x else int(x)
        y = int(-y) if self.invert_y else int(y)
        z = int(-z) if self.invert_z else int(z)


        t0 = time.time()
        # Send G0 rapid positioning command with target coordinates
        # G0 moves at maximum speed in a straight line
        response = self.send_cmd(f"g0 x{x} y{y} z{z}", wait=True, timeout=int(travel_time*2))
        if not response:
            self.wait(timeout=30)
        if time.time() - t0 < travel_time:
            time.sleep(travel_time - (time.time() - t0))

    def moveto_async(self, x: length_mm, y: length_mm, z: deg) -> bytes:
        """Asynchronously move the CNC machine to specified coordinates using G0 rapid positioning.

        This method executes a rapid linear movement (G0) to the specified position without
        waiting for the movement to complete. The movement is executed at maximum speed.
        Axis inversions are applied based on the machine configuration.

        Parameters
        ----------
        x : length_mm
            Target position along the X-axis in millimeters. Must be within the
            machine's x_lims range.
        y : length_mm
            Target position along the Y-axis in millimeters. Must be within the
            machine's y_lims range.
        z : deg
            Target position along the Z-axis in degrees. Must be within the
            machine's z_lims range.

        Returns
        -------
        bytes
            Response from GRBL after sending the G0 command. b'ok' if successful. '' if still processing.

        Notes
        -----
        - A small delay (0.1 s) is added after sending the command to prevent buffer overflow
        - Movement is executed in absolute coordinates (``G90`` mode)
        - Units are in millimeters (``G21`` mode)
        - Position limits are checked before movement
        - This method returns immediately without waiting for movement completion
        - Multiple async moves may queue up in GRBL's motion planner

        References
        ----------
        http://linuxcnc.org/docs/html/gcode/g-code.html#gcode:g0
        """
        # Validate that the target coordinates are within machine limits
        self._check_move(x, y, z)

        z = angle_min_travel(self.z, z)

        # Apply axis inversions based on machine configuration
        # Convert coordinates to integers for GRBL compatibility
        x = int(-x) if self.invert_x else int(x)
        y = int(-y) if self.invert_y else int(y)
        z = int(-z) if self.invert_z else int(z)

        # Send G0 rapid positioning command with target coordinates
        # G0 moves at maximum speed in a straight line
        return self.send_cmd(f"g0 x{x} y{y} z{z}", wait=False)

    def wait(self, timeout: int=60) -> None:
        """Wait for the CNC machine to complete any ongoing operations and returns the last response.

        Notes
        -----
        - This method blocks until a response is received from the device
        - Uses a 10 ms delay between polling attempts to prevent CPU overload
        - The status query command '?' is part of the GRBL protocol
        - This method is typically used after async operations to ensure completion

        Raises
        ------
        serial.SerialException
            If there are communication issues with the serial port
        RuntimeError
            If the serial port is closed or not properly initialized
        TimeoutError
            If the machine does not respond within the timeout period
        """

        start_time = time.time()

        try:
            # Send a status query command ('?') to check if the machine is idle
            self.serial_port.write(b"?\r\n")
            # Poll until we get a response indicating the machine is idle
            while True:
                # Read response
                lines = self.serial_port.readlines()
                # Check if we got a response and if it indicates the machine is idle
                if lines:
                    status_line = lines[0].decode('ascii', errors='ignore').strip()
                    # GRBL status format is typically <status|...>, check for 'Idle' status
                    if 'Idle' in status_line or 'Home' in status_line:
                        return lines[1] if len(lines) > 1 else ""
                # Check for timeout
                if time.time() - start_time > timeout:
                    raise TimeoutError("Timeout waiting for CNC machine to become idle")
                # Short delay to prevent CPU overload
                time.sleep(0.01)

        except Exception as e:
            if self.serial_port is None or not self.serial_port.is_open:
                raise RuntimeError("Serial port is closed or not properly initialized") from e
            raise

    def send_cmd(self, cmd: str, wait=False, timeout=None) -> str:
        """Send a command to the GRBL controller and return its response.

        Parameters
        ----------
        cmd : str
            A GRBL-compatible G-code command or system command.
            Must be a valid command according to the GRBL command specification.
        wait : bool, optional
            If wait is True, the method will block until the command is completed or until timeout is reached.
        timeout : int, optional
            Specifies the maximum time in seconds to wait for the command to complete.

        Returns
        -------
        bytes
            The raw response from the GRBL controller, including any trailing whitespace
            and newline characters. Typically ends with 'ok\r\n' for successful commands.

        Examples
        --------
        >>> from plantimager.controller.scanner.grbl import CNC
        >>> cnc = CNC("/dev/ttyUSB0")
        >>> response = cnc.send_cmd("G90")  # Set absolute positioning mode
        >>> print(response.strip())
        b'ok'

        >>> response = cnc.send_cmd("?")  # Get status
        >>> print(response.strip())
        b'<Idle|MPos:0.000,0.000,0.000|FS:0,0|WCO:0.000,0.000,0.000>'

        Notes
        -----
        - Includes a 100ms delay after each command to prevent buffer overflow
        - Always clears the input buffer before sending new commands
        - Logs both sent commands and received responses at debug level

        Raises
        ------
        serial.SerialException
            If there are communication errors with the serial port
        serial.SerialTimeoutException
            If reading the response times out

        References
        ----------
        https://github.com/gnea/grbl/wiki/Grbl-v1.1-Commands
        """
        cmd = cmd.strip()  # Remove leading/trailing whitespace

        try:
            # Clear any pending input before sending a new command
            self.serial_port.reset_input_buffer()
            logger.debug(f"{cmd} -> cnc")
            # Encode and send command with newline terminator
            self.serial_port.write(f"{cmd}\n".encode("ascii"))
            # Read response from GRBL controller
            grbl_out = self.serial_port.readline()

            if not grbl_out and not wait:
                logger.debug("cnc -> response pending (async)")
                return ""
            elif not grbl_out and wait:
                grbl_out = self.wait(timeout=timeout)

            logger.debug(f"cnc -> {grbl_out.strip()}")
            grbl_out = grbl_out.decode("ascii").strip()

            # Check for error and alarm responses
            if grbl_out.startswith('error:'):
                logger.error(f"GRBL error: {grbl_out}")
                raise RuntimeError(f"GRBL error: {grbl_out}")
            elif grbl_out.startswith('ALARM:'):
                logger.error(f"GRBL alarm: {grbl_out}")
                raise RuntimeError(f"GRBL alarm: {grbl_out}")

            # Add delay based on the command type - movement commands need a longer delay
            movement_commands = ('G0', 'G1', 'G2', 'G3')
            delay = 0.2 if any(cmd.upper().startswith(c) for c in movement_commands) else 0.1
            time.sleep(delay)

            return grbl_out

        except (serial.SerialException, serial.SerialTimeoutException) as e:
            logger.error(f"Serial communication error: {e}")
            raise
        except TimeoutError:
            # Re-raise the timeout error for proper handling upstream
            raise
        except Exception as e:
            logger.error(f"Unexpected error in GRBL communication: {e}")
            raise

    def get_status(self):
        """Query and parse the current status of the GRBL controller.

        Returns
        -------
        dict or None
            A dictionary containing the parsed status information with the following keys:
            - 'status' (str): Current state of the machine (e.g., 'Idle', 'Run')
            - 'position' (tuple of float): Current (x, y, z) position in mm, with
              configured axis inversions applied

            Returns ``None`` if an error occurs during communication or parsing.

        Notes
        -----
        - The response format from GRBL is typically '<status|MPos:x,y,z|...>',
          where additional fields may be present depending on GRBL configuration.
        - This method only extracts the status and machine position information.
        - Axis inversions are applied according to the instance's configuration.
        """
        # Send status query command '?' to GRBL
        self.serial_port.write("?\n".encode("ascii"))
        try:
            # Read the response line containing status information
            res = self.serial_port.readline()
            # Read and discard the "ok" confirmation message
            self.serial_port.readline()  # b"ok\r\n"

            # Decode the binary response to ASCII string
            res = res.decode("ascii")
            # Remove the enclosing angle brackets (< >)
            res = res[1:-1]
            # Split the response into segments separated by '|'
            res = res.split('|')

            # Create a dictionary to store formatted results
            res_fmt = {}
            # The first segment is the machine status (e.g., 'Idle', 'Run')
            res_fmt['status'] = res[0]

            # Extract position values from the second segment (format: 'MPos:x,y,z')
            pos = res[1].split(':')[-1].split(',')

            # Calculate signs for axis inversion based on configuration
            # Convert boolean invert flags (0/1) to multipliers (-1/1)
            sign = (-2 * self.invert_x + 1, -2 * self.invert_y + 1, -2 * self.invert_z + 1)

            # Apply axis inversions to position values and convert to float
            pos = tuple(s * float(p) for s, p in zip(sign, pos))
            res_fmt['position'] = pos

        except Exception as e:
            # Print full exception details if any error occurs
            traceback.print_exception(e)
            return None

        return res_fmt

    def get_grbl_settings(self):
        """Returns the GRBL firmware settings as a dictionary.

        Returns
        -------
        dict
            Dictionary containing GRBL settings in the format {'$param': value}, where:
            - Keys are parameter identifiers (strings) prefixed with '$'
            - Values are numeric settings (either int or float)

        Notes
        -----
        - Clears the input buffer before sending the command to ensure clean communication
        - All settings are converted to appropriate numeric types (int or float)
        - Parameter identifiers in the returned dictionary include the '$' prefix
        - Non-setting responses from GRBL are filtered out
        """
        # Clear any pending data in the input buffer to avoid reading stale information
        self.serial_port.reset_input_buffer()
        # Send the $$ command to GRBL which requests all current settings
        self.serial_port.write(("$$" + "\n").encode("ascii"))

        # Read all response lines from GRBL containing the settings
        str_settings = self.serial_port.readlines()

        # Initialize dictionary to store parsed settings
        settings = {}
        # Process each line in the GRBL response
        for line in str_settings:
            # Clean up the line by removing whitespace and decoding from bytes
            line = line.strip()  # remove potential leading and trailing whitespace & eol
            line = line.decode()
            # Skip lines that don't start with '$' (these are not setting entries)
            if not line.startswith('$'):
                # All params are prefixed with a dollar sign '$'
                continue
            # Split the line into parameter and value parts (format: $param=value)
            param, value = line.split("=")
            # Try to convert value to integer first (for whole number settings)
            try:
                settings[param] = int(value)
            except ValueError:
                # If integer conversion fails, store as float (for decimal settings)
                settings[param] = float(value)

        # Return the complete dictionary of GRBL settings
        return settings

    def print_grbl_settings(self):
        """Print the GRBL firmware settings in a formatted, human-readable form.

        Notes
        -----
        The parameter names, units, and descriptions are defined in the `GRBL_SETTINGS`
        constant dictionary in this module.

        See Also
        --------
        GRBL_SETTINGS : Dictionary containing parameter information
        get_grbl_settings : Method that retrieves current GRBL settings

        References
        ----------
        https://github.com/gnea/grbl/wiki/Grbl-v1.1-Configuration#grbl-settings
        """
        # Retrieve the current GRBL settings from the controller
        settings = self.get_grbl_settings()

        print("Obtained GRBL settings:")
        for param, value in settings.items():
            # Extract parameter metadata from the GRBL_SETTINGS dictionary
            # Each entry contains description, unit type, and default value (not used here)
            param_name, param_unit, _ = GRBL_SETTINGS[param]
            # For boolean and mask units, add parentheses for clarity in the output
            if param_unit in ['boolean', 'mask']:
                param_unit = f"({param_unit})"
            # Format and print each setting with its parameter code, name, value, and unit
            print(f" - ({param}) {param_name}: {value} {param_unit}")
