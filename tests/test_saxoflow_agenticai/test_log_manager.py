# tests/unit/test_log_manager.py
"""
Unit tests for saxoflow_agenticai.core.log_manager.

These tests are hermetic:
- No real network.
- Files only created under tmp_path (ephemeral).
- Optional dependency `colorlog` is faked where needed for determinism.

We explicitly patch using the import paths used inside the SUT module.
"""

from __future__ import annotations

import io
import logging
import os
from types import SimpleNamespace
from typing import Iterable, Tuple

import pytest


# --------------------------
# Helpers / local test fakes
# --------------------------

class StdoutStub(io.StringIO):
    """StringIO with a configurable isatty() result."""
    def __init__(self, is_tty: bool) -> None:
        super().__init__()
        self._is_tty = is_tty

    def isatty(self) -> bool:  # pragma: no cover - tiny shim
        return self._is_tty


class FakeColoredFormatter(logging.Formatter):
    """Capture the arguments passed to the color formatter."""
    def __init__(
        self,
        fmt: str,
        datefmt: str,
        log_colors: dict,
        secondary_log_colors: dict,
    ) -> None:
        super().__init__(fmt=fmt, datefmt=datefmt)
        self.seen_fmt = fmt
        self.seen_datefmt = datefmt
        self.seen_log_colors = dict(log_colors)
        self.seen_secondary = {
            "name": dict(secondary_log_colors.get("name", {})),
            "message": dict(secondary_log_colors.get("message", {})),
        }


class FakeStreamHandler(logging.Handler):
    """A minimal stand-in for colorlog.StreamHandler(stream=sys.stdout)."""
    def __init__(self, stream=None) -> None:  # noqa: D401 - trivial
        super().__init__()
        self.stream = stream
        self._formatter = None

    def setFormatter(self, fmt: logging.Formatter) -> None:  # noqa: N802
        self._formatter = fmt

    @property
    def formatter(self) -> logging.Formatter | None:
        return self._formatter


def _fresh_logger(name: str) -> logging.Logger:
    """
    Return a clean logger (no handlers, no stream flag) to avoid cross-test bleed.
    """
    logger = logging.getLogger(name)
    for h in list(logger.handlers):
        logger.removeHandler(h)
    # Remove the SUT's idempotence flag if present
    if hasattr(logger, "_saxoflow_stream_handler_attached"):
        delattr(logger, "_saxoflow_stream_handler_attached")
    logger.propagate = True
    return logger


def _count_handlers(logger: logging.Logger) -> Tuple[int, int]:
    """Return (#stream_handlers, #file_handlers)."""
    s = sum(1 for h in logger.handlers if isinstance(h, logging.Handler) and not isinstance(h, logging.FileHandler))
    f = sum(1 for h in logger.handlers if isinstance(h, logging.FileHandler))
    return s, f


# --------------------------
# Tests
# --------------------------

def test_plain_stream_when_colorlog_unavailable(monkeypatch):
    """
    Verify plain StreamHandler is used when COLORLOG is unavailable,
    regardless of TTY state. Also verify the plain formatter format string.
    """
    from saxoflow_agenticai.core import log_manager as sut

    # Force "no colorlog"
    monkeypatch.setattr(sut, "COLORLOG_AVAILABLE", False, raising=True)
    monkeypatch.setattr(sut, "sys", SimpleNamespace(stdout=StdoutStub(True)), raising=True)

    name = "T_plain_no_colorlog"
    _fresh_logger(name)
    logger = sut.get_logger(name=name)

    # One stream handler, plain formatter
    s_count, f_count = _count_handlers(logger)
    assert s_count == 1 and f_count == 0

    (handler,) = logger.handlers
    # logging.StreamHandler exposes a logging.Formatter with the SUT's fmt
    assert isinstance(handler, logging.StreamHandler)
    assert getattr(handler.formatter, "_fmt") == sut._PLAIN_FMT  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "env_value",
    ["1", "true", "TRUE", "Yes", "on", "On"],
)
def test_force_color_env_truthy_overrides_non_tty(monkeypatch, env_value):
    """
    Force color via SAXOFLOW_FORCE_COLOR even when stdout is NOT a TTY.
    We stub a minimal `colorlog` with the two symbols the SUT uses.
    """
    from saxoflow_agenticai.core import log_manager as sut

    fake_colorlog = SimpleNamespace(
        StreamHandler=FakeStreamHandler,
        ColoredFormatter=FakeColoredFormatter,
    )
    monkeypatch.setattr(sut, "colorlog", fake_colorlog, raising=True)
    monkeypatch.setattr(sut, "COLORLOG_AVAILABLE", True, raising=True)
    monkeypatch.setenv("SAXOFLOW_FORCE_COLOR", env_value)
    monkeypatch.setattr(sut, "sys", SimpleNamespace(stdout=StdoutStub(False)), raising=True)

    name = f"T_force_color_{env_value}"
    _fresh_logger(name)
    logger = sut.get_logger(name=name)

    # Colored stream path selected
    (handler,) = logger.handlers
    assert isinstance(handler, FakeStreamHandler)
    assert isinstance(handler.formatter, FakeColoredFormatter)

    # Validate that the colored formatter got the expected format & color maps
    cf: FakeColoredFormatter = handler.formatter  # type: ignore[assignment]
    assert cf.seen_fmt == sut._COLOR_FMT
    assert cf.seen_log_colors == sut._LEVEL_COLORS
    assert cf.seen_secondary["name"] == sut._NAME_COLORS
    assert cf.seen_secondary["message"] == sut._MESSAGE_COLORS


def test_color_when_colorlog_available_and_tty(monkeypatch):
    """
    With colorlog available and stdout TTY, colored stream handler is used.
    """
    from saxoflow_agenticai.core import log_manager as sut

    fake_colorlog = SimpleNamespace(
        StreamHandler=FakeStreamHandler,
        ColoredFormatter=FakeColoredFormatter,
    )
    monkeypatch.setattr(sut, "colorlog", fake_colorlog, raising=True)
    monkeypatch.setattr(sut, "COLORLOG_AVAILABLE", True, raising=True)
    monkeypatch.delenv("SAXOFLOW_FORCE_COLOR", raising=False)
    monkeypatch.setattr(sut, "sys", SimpleNamespace(stdout=StdoutStub(True)), raising=True)

    name = "T_color_tty"
    _fresh_logger(name)
    logger = sut.get_logger(name=name)

    (handler,) = logger.handlers
    assert isinstance(handler, FakeStreamHandler)
    assert isinstance(handler.formatter, FakeColoredFormatter)


@pytest.mark.parametrize("env_value", ["0", "false", "False", "no", "off"])
def test_force_color_env_falsey_uses_plain_handler(monkeypatch, env_value):
    """
    Falsey SAXOFLOW_FORCE_COLOR should NOT trigger colored path when not a TTY.
    """
    from saxoflow_agenticai.core import log_manager as sut

    monkeypatch.setattr(sut, "COLORLOG_AVAILABLE", True, raising=True)
    monkeypatch.setenv("SAXOFLOW_FORCE_COLOR", env_value)
    monkeypatch.setattr(sut, "sys", SimpleNamespace(stdout=StdoutStub(False)), raising=True)

    name = f"T_env_falsey_{env_value}"
    _fresh_logger(name)
    logger = sut.get_logger(name=name)

    (handler,) = logger.handlers
    # Plain handler will be a logging.StreamHandler (not our fake)
    assert isinstance(handler, logging.StreamHandler)
    assert getattr(handler.formatter, "_fmt") == sut._PLAIN_FMT  # type: ignore[attr-defined]


def test_isatty_exception_falls_back_to_plain(monkeypatch):
    """
    If sys.stdout.isatty() raises, _should_use_color() safely returns False.
    """
    from saxoflow_agenticai.core import log_manager as sut

    class BadStdout(StdoutStub):
        def isatty(self) -> bool:  # pragma: no cover - tiny edge case
            raise RuntimeError("isatty broke")

    monkeypatch.setattr(sut, "COLORLOG_AVAILABLE", True, raising=True)
    monkeypatch.setattr(sut, "sys", SimpleNamespace(stdout=BadStdout(True)), raising=True)

    name = "T_isatty_raises"
    _fresh_logger(name)
    logger = sut.get_logger(name=name)

    (handler,) = logger.handlers
    assert isinstance(handler, logging.StreamHandler)
    assert getattr(handler.formatter, "_fmt") == sut._PLAIN_FMT  # type: ignore[attr-defined]


def test_stream_idempotent_and_level_update(monkeypatch):
    """
    Repeated calls must not duplicate stream handlers; level should update.
    """
    from saxoflow_agenticai.core import log_manager as sut

    monkeypatch.setattr(sut, "COLORLOG_AVAILABLE", False, raising=True)
    monkeypatch.setattr(sut, "sys", SimpleNamespace(stdout=StdoutStub(True)), raising=True)

    name = "T_idem_stream"
    _fresh_logger(name)
    logger1 = sut.get_logger(name=name, level=logging.INFO)
    logger2 = sut.get_logger(name=name, level=logging.DEBUG)

    assert logger1 is logger2
    s_count, f_count = _count_handlers(logger1)
    assert s_count == 1 and f_count == 0
    assert logger2.level == logging.DEBUG
    # Private idempotence flag should exist (white-box assertion)
    assert getattr(logger2, "_saxoflow_stream_handler_attached", False) is True


def test_file_handler_single_per_path(tmp_path, monkeypatch):
    """
    Attaches one FileHandler per absolute path per logger; second call is a no-op.
    """
    from saxoflow_agenticai.core import log_manager as sut

    monkeypatch.setattr(sut, "COLORLOG_AVAILABLE", False, raising=True)
    monkeypatch.setattr(sut, "sys", SimpleNamespace(stdout=StdoutStub(True)), raising=True)

    log1 = tmp_path / "a.log"
    log2 = tmp_path / "b.log"
    name = "T_file_idempotent"
    _fresh_logger(name)

    logger = sut.get_logger(name=name, log_to_file=str(log1))
    s_count, f_count = _count_handlers(logger)
    assert s_count == 1 and f_count == 1

    # Attach same file again -> still one file handler
    logger = sut.get_logger(name=name, log_to_file=str(log1))
    s_count, f_count = _count_handlers(logger)
    assert s_count == 1 and f_count == 1

    # Attach a different file -> +1 file handler
    logger = sut.get_logger(name=name, log_to_file=str(log2))
    s_count, f_count = _count_handlers(logger)
    assert s_count == 1 and f_count == 2


def test_file_handler_open_failure_logs_error(monkeypatch, caplog):
    """
    If FileHandler raises OSError, SUT logs an error and continues without crash.
    (The except block is marked pragma:no cover in SUT, but we validate behavior.)
    """
    from saxoflow_agenticai.core import log_manager as sut

    def boom(*_a, **_kw):
        raise OSError("nope")

    monkeypatch.setattr(sut, "COLORLOG_AVAILABLE", False, raising=True)
    monkeypatch.setattr(sut, "sys", SimpleNamespace(stdout=StdoutStub(True)), raising=True)
    monkeypatch.setattr(logging, "FileHandler", boom, raising=True)

    name = "T_file_open_failure"
    _fresh_logger(name)
    with caplog.at_level(logging.ERROR):
        sut.get_logger(name=name, log_to_file="does_not_matter.log")

    # An error is logged mentioning the file path
    msgs = [r.message for r in caplog.records if r.levelno >= logging.ERROR]
    assert any("Failed to open log file" in str(m) for m in msgs)


def test_propagate_false_and_same_instance(monkeypatch):
    """
    Logger must have propagate=False and maintain identity across calls.
    """
    from saxoflow_agenticai.core import log_manager as sut

    monkeypatch.setattr(sut, "COLORLOG_AVAILABLE", False, raising=True)
    monkeypatch.setattr(sut, "sys", SimpleNamespace(stdout=StdoutStub(True)), raising=True)

    name = "T_propagate_same_instance"
    _fresh_logger(name)
    l1 = sut.get_logger(name=name)
    l2 = sut.get_logger(name=name)

    assert l1 is l2
    assert l1.propagate is False


def test_unicode_messages_do_not_crash(monkeypatch, caplog):
    """
    Logging arbitrary Unicode should not crash for either path.
    """
    from saxoflow_agenticai.core import log_manager as sut

    monkeypatch.setattr(sut, "COLORLOG_AVAILABLE", False, raising=True)
    monkeypatch.setattr(sut, "sys", SimpleNamespace(stdout=StdoutStub(True)), raising=True)

    name = "T_unicode"
    _fresh_logger(name)
    logger = sut.get_logger(name=name)
    with caplog.at_level(logging.INFO):
        logger.info("Unicode: Café Δ ✓ — test")
    # Caplog should have at least one record
    assert any("Café" in r.message for r in caplog.records)
