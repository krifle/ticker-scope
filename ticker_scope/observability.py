from __future__ import annotations

import logging
import os
import sys
from collections.abc import Mapping
from typing import Any


LOGGER_NAME = "ticker_scope"
DEFAULT_LOG_LEVEL = "INFO"
SECRET_PARAM_NAMES = {"apikey", "api_key", "token", "password", "secret"}


def configure_logging(level: str | None = None) -> None:
    resolved_level_name = (
        level or os.getenv("TICKER_SCOPE_LOG_LEVEL") or DEFAULT_LOG_LEVEL
    ).upper()
    resolved_level = getattr(logging, resolved_level_name, logging.INFO)

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(resolved_level)
    logger.propagate = False

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        logger.addHandler(handler)

    for handler in logger.handlers:
        handler.setLevel(resolved_level)


def get_logger(name: str) -> logging.Logger:
    if name == LOGGER_NAME or name.startswith(f"{LOGGER_NAME}."):
        return logging.getLogger(name)
    return logging.getLogger(f"{LOGGER_NAME}.{name}")


def masked_params(params: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: "***" if key.lower() in SECRET_PARAM_NAMES and value else value
        for key, value in params.items()
    }
