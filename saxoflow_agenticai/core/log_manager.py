# saxoflow_agenticai/core/log_manager.py
"""
Centralized logger factory for SaxoFlow Agentic AI.

This module provides a single entry point, :func:`get_logger`, that returns a
configured :class:`logging.Logger`. It supports:
- Colored console logs via `colorlog` when available and stdout is a TTY
- Plain console logs as a fallback
- Optional file logging (UTF-8)
- Idempotent handler attachment (prevents duplicate handlers)

Environment variables
---------------------
SAXOFLOW_FORCE_COLOR=true|false
    Force-enable colored logging when `colorlog` is installed, even if stdout
    is not a TTY. Defaults to standard behavior (enabled only if stdout.isatty()).

Notes
-----
- We keep `secondary_log_colors` mappings for agent names to colorize `%(name)s`
  and `%(message)s` tokens when using `colorlog`.
- The public API remains unchanged to avoid breaking callers.

Python: 3.9+
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Dict, Optional

try:  # pragma: no cover - optional dependency
    import colorlog  # type: ignore
    COLORLOG_AVAILABLE = True
except Exception:  # pragma: no cover
    COLORLOG_AVAILABLE = False


__all__ = ["get_logger"]


# -----------------------
# Color configuration map
# -----------------------

# Colors for log levels (colorlog)
_LEVEL_COLORS: Dict[str, str] = {
    "DEBUG": "cyan",
    "INFO": "green",
    "WARNING": "yellow",
    "ERROR": "red",
    "CRITICAL": "bold_red",
}

# Colors for the logger name and the message segment (per agent class).
# Ensure names match your actual logger names used in the codebase.
_NAME_COLORS: Dict[str, str] = {
    "RTLGenAgent": "blue",
    "TBGenAgent": "magenta",
    "RTLReviewAgent": "cyan",
    "TBReviewAgent": "bold_magenta",
    "DebugAgent": "bold_yellow",
    "SimAgent": "white",
    "FormalPropGenAgent": "bold_green",
    "FormalPropReviewAgent": "bold_cyan",
    "ReportAgent": "white",
    "AgentOrchestrator": "bold_white",
    "AgentManager": "bold_blue",
    # Add more as needed; must match logger name.
}

_MESSAGE_COLORS: Dict[str, str] = dict(_NAME_COLORS)  # same mapping by default

# Base formats
_PLAIN_FMT = "[%(levelname)s] %(asctime)s - [%(name)s] %(message)s"
_PLAIN_DATEFMT = "%Y-%m-%d %H:%M:%S"

# colorlog supports additional placeholders:
#   %(log_color)s, %(reset)s, %(name_log_color)s, %(message_log_color)s
_COLOR_FMT = (
    "%(log_color)s[%(levelname)s]%(reset)s %(asctime)s - "
    "[%(name_log_color)s%(name)s%(reset)s] "
    "%(message_log_color)s%(message)s%(reset)s"
)


# ---------------
# Helper builders
# ---------------

def _should_use_color() -> bool:
    """Return True if colorized logs should be used."""
    if not COLORLOG_AVAILABLE:
        return False
    env = os.getenv("SAXOFLOW_FORCE_COLOR")
    if env is not None:
        return env.strip().lower() in {"1", "true", "yes", "on"}
    # Default behavior: enable only if stdout is a TTY.
    try:
        return sys.stdout.isatty()
    except Exception:  # pragma: no cover - very defensive
        return False


def _build_colored_stream_handler() -> logging.Handler:
    """Create a colorlog StreamHandler with our format and color maps."""
    handler = colorlog.StreamHandler(stream=sys.stdout)  # type: ignore[name-defined]
    formatter = colorlog.ColoredFormatter(  # type: ignore[name-defined]
        fmt=_COLOR_FMT,
        datefmt=_PLAIN_DATEFMT,
        log_colors=_LEVEL_COLORS,
        secondary_log_colors={
            "name": _NAME_COLORS,
            "message": _MESSAGE_COLORS,
        },
    )
    handler.setFormatter(formatter)
    return handler


def _build_plain_stream_handler() -> logging.Handler:
    """Create a plain (non-colored) StreamHandler."""
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(logging.Formatter(fmt=_PLAIN_FMT, datefmt=_PLAIN_DATEFMT))
    return handler


def _attach_stream_handler(logger: logging.Logger) -> None:
    """
    Attach a single stream handler to `logger` if not already attached.

    We mark the logger with a private attribute to avoid duplicate stream handlers.
    """
    if getattr(logger, "_saxoflow_stream_handler_attached", False):
        return

    handler = _build_colored_stream_handler() if _should_use_color() else _build_plain_stream_handler()
    logger.addHandler(handler)
    # Mark so subsequent calls do not add duplicates.
    logger._saxoflow_stream_handler_attached = True  # type: ignore[attr-defined]


def _attach_file_handler(logger: logging.Logger, log_to_file: str) -> None:
    """
    Attach a file handler to `logger` for the given path, if not already present.

    Ensures only one FileHandler per absolute file path per logger.
    """
    if not log_to_file:
        return

    log_file_path = os.path.abspath(log_to_file)
    for h in logger.handlers:
        if isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", None) == log_file_path:
            return  # already attached

    try:
        fhandler = logging.FileHandler(log_file_path, encoding="utf-8")
    except OSError as exc:  # pragma: no cover - filesystem errors
        logger.error("Failed to open log file '%s': %s", log_file_path, exc)
        return

    fhandler.setFormatter(logging.Formatter(fmt=_PLAIN_FMT, datefmt=_PLAIN_DATEFMT))
    logger.addHandler(fhandler)


# ----------------
# Public interface
# ----------------

def get_logger(
    name: str = "SaxoFlowAgent",
    level: int = logging.INFO,
    log_to_file: Optional[str] = None,
) -> logging.Logger:
    """
    Return a configured, reusable :class:`logging.Logger`.

    Parameters
    ----------
    name : str, default "SaxoFlowAgent"
        Logger name (e.g., "RTLGenAgent", "TBReviewAgent").
    level : int, default logging.INFO
        Log level for this logger (see :mod:`logging`).
    log_to_file : Optional[str], default None
        Optional filesystem path for file logging. The file handler is attached
        once per unique path per logger.

    Returns
    -------
    logging.Logger
        A configured logger instance.

    Notes
    -----
    - The logger has `propagate = False` to avoid duplicate logs if the root
      logger is configured elsewhere.
    - Colored logs require `colorlog` to be installed. If not available or
      disabled, a plain formatter is used.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    _attach_stream_handler(logger)
    if log_to_file:
        _attach_file_handler(logger, log_to_file)

    # Avoid propagating to root to prevent duplicate outputs if the app also
    # configures the root logger.
    logger.propagate = False
    return logger


# -----------------------------------------------------------------------------
# Unused/Optional features kept for reference (commented out intentionally)
# -----------------------------------------------------------------------------

# def get_json_logger(name: str = "SaxoFlowAgent", level: int = logging.INFO) -> logging.Logger:
#     """
#     Example JSON logger using a third-party formatter (e.g., python-json-logger).
#     Kept as a reference for future centralized log aggregation (e.g., ELK/Datadog).
#     Not used to avoid adding dependencies.
#     """
#     try:
#         from pythonjsonlogger import jsonlogger  # type: ignore
#     except Exception as exc:
#         raise RuntimeError("python-json-logger is not installed") from exc
#
#     logger = logging.getLogger(name)
#     logger.setLevel(level)
#     handler = logging.StreamHandler(stream=sys.stdout)
#     handler.setFormatter(jsonlogger.JsonFormatter())
#     logger.addHandler(handler)
#     logger.propagate = False
#     return logger
#
# def get_rotating_file_logger(
#     name: str,
#     log_file: str,
#     level: int = logging.INFO,
#     max_bytes: int = 5_000_000,
#     backup_count: int = 5,
# ) -> logging.Logger:
#     """
#     Example rotating file logger. Kept for future use when logs may grow large.
#     Not used to keep the current footprint minimal.
#     """
#     from logging.handlers import RotatingFileHandler
#     logger = logging.getLogger(name)
#     logger.setLevel(level)
#     handler = RotatingFileHandler(log_file, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8")
#     handler.setFormatter(logging.Formatter(fmt=_PLAIN_FMT, datefmt=_PLAIN_DATEFMT))
#     logger.addHandler(handler)
#     logger.propagate = False
#     return logger
