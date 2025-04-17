#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""A dummy CNC implementation based on GRBL.

Usage Examples
--------------
```python
>>> from plantimager.controller.scanner.dummy_cnc import DummyCNC
>>> # Initialize the dummy CNC
>>> cnc = DummyCNC()
>>> # Perform operations just like with a real CNC
>>> cnc.home()
>>> cnc.moveto(100, 100, 45)
>>> x, y, z = cnc.get_position()
>>> print(f"Current position: ({x}, {y}, {z})")
>>> # Async movement
>>> cnc.moveto_async(200, 200, 90)
>>> # Do other things...
>>> cnc.wait()  # Wait for movement to complete
"""

import time
import random

from plantimager.controller.scanner.hal import AbstractCNC
from plantimager.controller.scanner.units import deg, length_mm
from plantimager.commons.logging import create_logger

logger = create_logger(__name__)

class DummyCNC(AbstractCNC):
    """A dummy implementation of CNC machine control for testing purposes.
    
    This class mimics the behavior of the real CNC class without connecting to actual hardware.
    It simulates basic CNC operations like movement, positioning, and homing.
    
    Attributes
    ----------
    x_lims : tuple[float, float]
        Allowed range for X-axis movement
    y_lims : tuple[float, float]
        Allowed range for Y-axis movement
    z_lims : tuple[float, float]
        Allowed range for Z-axis movement (rotational axis)
    _position : tuple[float, float, float]
        Current position (x, y, z)
    _busy : bool
        Flag indicating if the CNC is currently moving
    """

    def __init__(self, x_limits=(0, 740), y_limits=(0, 740), z_limits=(0, 360)):
        """Initialize the dummy CNC controller with default axis limits."""
        super().__init__()
        self.x_lims = x_limits
        self.y_lims = y_limits
        self.z_lims = z_limits
        self._position = (0, 0, 0)  # Initial position
        self._busy = False
        self.has_started = True
        
        # Simulate initialization delay
        time.sleep(0.2)
        logger.info("Dummy CNC initialized")

    def _check_move(self, x, y, z):
        """Validate that the requested movement coordinates are within the machine's axis limits.

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
        ValueError
            If any coordinate (x, y, or z) is outside its defined limits
        """
        if not (self.x_lims[0] <= x <= self.x_lims[1]):
            raise ValueError(f"Move command coordinates {x} is outside the x-limits {self.x_lims}!")
        if not (self.y_lims[0] <= y <= self.y_lims[1]):
            raise ValueError(f"Move command coordinates {y} is outside the y-limits {self.y_lims}!")
        if not (self.z_lims[0] <= z <= self.z_lims[1]):
            raise ValueError(f"Move command coordinates {z} is outside the z-limits {self.z_lims}!")

    def home(self):
        """Simulate performing a homing cycle.
        
        Sets the current position to a starting point near the origin,
        simulating the behavior of the real CNC homing procedure.
        """
        logger.info("Dummy CNC homing...")
        self._busy = True
        # Simulate homing time
        time.sleep(1.5)
        # Set position to a slight offset from zero, simulating a real homing result
        self._position = (20, 20, 0)
        self._busy = False
        logger.info("Dummy CNC homing completed")

    def get_position(self):
        """Get the current XYZ position of the dummy CNC machine.

        Returns
        -------
        length_mm
            Current X-axis position in millimeters
        length_mm
            Current Y-axis position in millimeters
        deg
            Current Z-axis position in degrees
        """
        # Add a small amount of noise to simulate real sensor readings
        noise_x = random.uniform(-0.01, 0.01)
        noise_y = random.uniform(-0.01, 0.01)
        noise_z = random.uniform(-0.01, 0.01)
        
        return (
            self._position[0] + noise_x,
            self._position[1] + noise_y,
            self._position[2] + noise_z
        )

    def moveto(self, x, y, z):
        """Move the dummy CNC machine to specified coordinates and wait until the target position is reached.

        Parameters
        ----------
        x : length_mm
            Target position along the X-axis in millimeters
        y : length_mm
            Target position along the Y-axis in millimeters
        z : deg
            Target position along the Z-axis in degrees

        Raises
        ------
        ValueError
            If any of the target coordinates are outside the allowed limits
        """
        self.moveto_async(x, y, z)
        self.wait()

    def moveto_async(self, x, y, z):
        """Asynchronously move the dummy CNC machine to specified coordinates.

        Parameters
        ----------
        x : length_mm
            Target position along the X-axis in millimeters
        y : length_mm
            Target position along the Y-axis in millimeters
        z : deg
            Target position along the Z-axis in degrees

        Raises
        ------
        ValueError
            If any of the target coordinates are outside the allowed limits
        """
        # Convert to float to ensure compatibility
        x, y, z = float(x), float(y), float(z)
        
        # Check if the move is within limits
        self._check_move(x, y, z)
        
        # Set busy flag
        self._busy = True
        
        # Log the movement
        logger.info(f"Dummy CNC moving to (x={x}, y={y}, z={z})")
        
        # Start simulated movement in a separate thread
        import threading
        threading.Thread(
            target=self._simulate_movement,
            args=(x, y, z),
            daemon=True
        ).start()

    def _simulate_movement(self, target_x, target_y, target_z):
        """Simulate movement from current position to target position.
        
        This method runs in a separate thread to allow async operation.
        
        Parameters
        ----------
        target_x : float
            Target X position
        target_y : float
            Target Y position
        target_z : float
            Target Z position
        """
        # Get current position
        start_x, start_y, start_z = self._position
        
        # Calculate distance
        dx = target_x - start_x
        dy = target_y - start_y
        dz = target_z - start_z
        
        # Calculate total distance for time estimation
        distance = (dx**2 + dy**2 + dz**2)**0.5
        
        # Simulate movement time (longer for greater distances)
        movement_time = 0.5 + distance * 0.005  # Base time + distance-dependent time
        
        # Sleep to simulate movement time
        time.sleep(movement_time)
        
        # Update position
        self._position = (target_x, target_y, target_z)
        
        # Movement complete
        self._busy = False
        logger.info(f"Dummy CNC reached position (x={target_x}, y={target_y}, z={target_z})")

    def wait(self, timeout=60):
        """Wait for the dummy CNC machine to complete any ongoing operations.

        Parameters
        ----------
        timeout : int, optional
            Maximum time to wait in seconds, by default 60

        Raises
        ------
        TimeoutError
            If the simulated movement doesn't complete within the timeout
        """
        start_time = time.time()
        
        while self._busy:
            time.sleep(0.1)  # Small delay to prevent CPU overload
            if time.time() - start_time > timeout:
                raise TimeoutError("Timeout waiting for CNC movement to complete")

    def stop(self):
        """Stop the dummy CNC and clean up resources."""
        logger.info("Stopping dummy CNC")
        self._busy = False
    
    def send_cmd(self, cmd):
        """Simulate sending a command to the GRBL controller.

        Parameters
        ----------
        cmd : str
            A GRBL-compatible G-code command or system command

        Returns
        -------
        str
            Simulated response from the controller
        """
        logger.debug(f"Dummy CNC received command: {cmd}")
        # Simulate response delay
        time.sleep(0.1)
        return "ok"
    
    def get_status(self):
        """Simulate querying the current status of the GRBL controller.

        Returns
        -------
        dict
            A dictionary containing simulated status information
        """
        state = "Idle" if not self._busy else "Run"
        return {
            'status': state,
            'position': self._position
        }
    
    @property
    def x(self):
        """Get the current X-axis position."""
        return self.get_position()[0]
    
    @property
    def y(self):
        """Get the current Y-axis position."""
        return self.get_position()[1]
    
    @property
    def z(self):
        """Get the current Z-axis position."""
        return self.get_position()[2]