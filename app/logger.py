
"""Centralized logging for MtgSage."""

import logging
import os
import sys


LOGGER_NAME = "app"
HANDLER_NAME = "mtgsage-console"

LOG_FORMAT = (
    "%(asctime)s | %(levelname)-8s | "
    "%(name)s | %(message)s"
)

LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


def configure_logging(level: str | None = None) -> None:
    """Configure application logging without affecting dependencies."""
    name = (
        level or os.getenv("MTGSAGE_LOG_LEVEL", "INFO")
    ).strip().upper()

    if name not in LOG_LEVELS:
        raise ValueError(f"Unsupported log level: {name}")

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(LOG_LEVELS[name])
    logger.propagate = False

    # Repeated initialization must not duplicate output.
    if any(
        handler.name == HANDLER_NAME
        for handler in logger.handlers
    ):
        return

    handler = logging.StreamHandler(sys.stderr)
    handler.set_name(HANDLER_NAME)
    handler.setFormatter(
        logging.Formatter(
            LOG_FORMAT,
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Return a named application logger."""
    if name == "__main__":
        raise ValueError(
            "Use an explicit module name for executable entry points"
        )

    if name != LOGGER_NAME and not name.startswith(f"{LOGGER_NAME}."):
        raise ValueError(f"Logger must belong to {LOGGER_NAME}")

    return logging.getLogger(name)
