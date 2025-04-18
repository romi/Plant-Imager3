# Documentation Guidelines

This page describes the documentation system used in the Plant-Imager3 project and provides guidelines for contributing to the documentation.

## Documentation System

The Plant-Imager3 documentation is built using [MkDocs](https://www.mkdocs.org/) with the [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/) theme.
The API reference documentation is automatically generated using [mkdocstrings](https://mkdocstrings.github.io/).

## Docstring Format

All Python code in the Plant-Imager3 project should use the NumPy docstring format. This format is well-structured and provides a clear way to document parameters, return values, exceptions, and examples.

### Example Class Docstring

```python
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
    """
```

### Example Method Docstring

```python
def moveto(self, x, y, z):
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
```

## Markdown Files

In addition to docstrings, the documentation includes Markdown files that provide higher-level information about the project.
These files should follow these guidelines:

1. Use descriptive headings and subheadings
2. Include code examples where appropriate
3. Use admonitions (notes, warnings, tips) to highlight important information
4. Include links to related documentation
5. Use images and diagrams to illustrate complex concepts

### Admonitions

Admonitions are a great way to highlight important information. Here are some examples:

```markdown
!!! note
    This is a note admonition.

!!! warning
    This is a warning admonition.

!!! tip
    This is a tip admonition.
```

## Building and Testing Documentation

Before submitting changes to the documentation, you should build and test it locally:

1. Install the required dependencies:
   ```shell
   pip install mkdocs mkdocs-material mkdocs-gen-files mkdocs-literate-nav mkdocs-section-index mkdocstrings mkdocstrings-python markdown-exec
   ```

2. Build the documentation:
   ```shell
   mkdocs build
   ```

3. Serve the documentation locally:
   ```shell
   mkdocs serve
   ```

4. Open your browser and navigate to [http://localhost:8000](http://localhost:8000)

## Automatic API Reference Generation

The API reference documentation is automatically generated using the `gen_ref_pages.py` script in the `docs/assets/scripts` directory.
This script scans the source code and generates Markdown files for each module, class, and function.

The script is configured to exclude certain files and directories from the documentation.
If you need to exclude additional files or directories, you can modify the `EXCLUDED_FILES` and `EXCLUDED_DIRS` lists in the script.