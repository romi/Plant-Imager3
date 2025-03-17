import logging
import sys

import colorlog


def create_logger(name: str, level=logging.DEBUG) -> logging.Logger:
    """
    Create a logger with the given name.

    This logger comes with a stream handler to sys.stderr and is formatted.

    Parameters
    ----------
    name: str
        Name of the logger.

    level: int, optional
        Logging level of the logger. Must be one of DEBUG, INFO, WARNING, ERROR, CRITICAL
        from the logging module.

    Returns
    -------
    logging.Logger
    """
    logger = logging.Logger(name)
    logger.setLevel(level)

    formatter = colorlog.LevelFormatter(fmt={
        logging.getLevelName(logging.DEBUG):    "{log_color}[{asctime}] {name} {threadName} - {levelname}: {message} ({filename}:{lineno})",
        logging.getLevelName(logging.INFO):     "{log_color}[{asctime}] {name} {threadName} - {levelname}: {message}",
        logging.getLevelName(logging.WARNING):  "{log_color}[{asctime}] {name} {threadName} - {levelname}: {message} ({filename}:{lineno})",
        logging.getLevelName(logging.ERROR):    "[{log_color}{asctime}] {name} {threadName} - {levelname}: {message} ({filename}:{lineno})",
        logging.getLevelName(logging.CRITICAL): "[{log_color}{asctime}] {name} {threadName} - {levelname}: {message} ({filename}:{lineno})",
    }, style="{")

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger