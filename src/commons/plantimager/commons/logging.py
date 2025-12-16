#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Logging System for Application Monitoring

A comprehensive logging system that provides structured, configurable logging capabilities for
tracking application events, errors, and performance metrics across different components.
"""

import logging
import sys

import colorlog


def create_logger(name: str, level=logging.DEBUG) -> logging.Logger:
    """Create a logger with the given name and specified logging level.

    Parameters
    ----------
    name : str
        Name of the logger. This identifies the logger in the hierarchy.
    level : int, optional
        Logging level of the logger. Must be one of DEBUG, INFO, WARNING, ERROR, CRITICAL
        from the logging module. Default is logging.DEBUG.

    Returns
    -------
    logging.Logger
        Configured logger object with stream handler and level-specific formatting.

    Notes
    -----
    - The logger uses colorlog.LevelFormatter for colored output in console
    - Different log levels have different format patterns:
      - DEBUG: Includes timestamp, name, thread, level, message, filename, and line number
      - INFO: Simplified format with timestamp, name, thread, level, and message
      - WARNING/ERROR/CRITICAL: Similar to DEBUG format with file location information

    Examples
    --------
    >>> from plantimager.commons.logging import create_logger
    >>> logger = create_logger("my_app")
    >>> logger.info("Application started")
    [timestamp] my_app MainThread - INFO: Application started
    >>> logger.error("An error occurred")
    [timestamp] my_app MainThread - ERROR: An error occurred (logging.py:123)
    """
    # Create a new logger instance with the specified name
    logger = logging.Logger(name)
    # Set the minimum logging level
    logger.setLevel(level)

    # Create a LevelFormatter that uses different format strings based on log level
    # The log_color prefix enables colored output for each level
    formatter = colorlog.LevelFormatter(fmt={
        logging.getLevelName(logging.DEBUG):    "{log_color} {name} {threadName} - {levelname}: {message} ({filename}:{lineno})",
        logging.getLevelName(logging.INFO):     "{log_color} {name} {threadName} - {levelname}: {message}",
        logging.getLevelName(logging.WARNING):  "{log_color} {name} {threadName} - {levelname}: {message} ({filename}:{lineno})",
        logging.getLevelName(logging.ERROR):    "[{log_color}] {name} {threadName} - {levelname}: {message} ({filename}:{lineno})",
        logging.getLevelName(logging.CRITICAL): "[{log_color}] {name} {threadName} - {levelname}: {message} ({filename}:{lineno})",
    }, style="{")

    # Create a handler that outputs log messages to stderr
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)  # Apply the formatter to the handler
    logger.addHandler(handler)  # Add the configured handler to the logger

    return logger
