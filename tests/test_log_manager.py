"""
Tests for saxoflow_agenticai.core.log_manager.

The log manager configures coloured and file based logging.  The tests
ensure that loggers are singletons per name and that file handlers are
attached when requested.  Note that colourlog might not be installed;
these tests do not assume its presence.
"""

from pathlib import Path
import tempfile

from saxoflow_agenticai.core import log_manager


def test_get_logger_returns_same_instance():
    logger1 = log_manager.get_logger("TestLogger")
    logger2 = log_manager.get_logger("TestLogger")
    assert logger1 is logger2


def test_get_logger_file_handler(tmp_path):
    log_file = tmp_path / "test.log"
    logger = log_manager.get_logger("FileLogger", log_to_file=str(log_file))
    # Log a message
    logger.info("hello")
    # File should exist and contain the message
    assert log_file.exists()
    content = log_file.read_text()
    assert "hello" in content