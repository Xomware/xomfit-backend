"""
XOMFIT Logger
"""

import logging
import os


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logger.setLevel(getattr(logging, level, logging.INFO))
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("[%(levelname)s] %(name)s: %(message)s"))
        logger.addHandler(handler)
    return logger
