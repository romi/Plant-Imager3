import logging
import sys

import colorlog


def create_logger(name: str) -> logging.Logger:
    logger = logging.Logger(name)
    logger.setLevel(logging.DEBUG)

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