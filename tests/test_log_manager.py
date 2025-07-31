import logging
import sys
from pathlib import Path
import types

from saxoflow_agenticai.core import log_manager

def test_get_logger_returns_same_instance():
    logger1 = log_manager.get_logger("TestLogger")
    logger2 = log_manager.get_logger("TestLogger")
    assert logger1 is logger2

def test_get_logger_file_handler(tmp_path):
    log_file = tmp_path / "test.log"
    logger = log_manager.get_logger("FileLogger", log_to_file=str(log_file))
    logger.info("hello")
    assert log_file.exists()
    content = log_file.read_text()
    assert "hello" in content

def test_get_logger_no_colorlog(monkeypatch, capsys):
    # Simulate colorlog unavailable
    monkeypatch.setattr(log_manager, "COLORLOG_AVAILABLE", False)
    logger = log_manager.get_logger("NoColorLogger")
    logger.info("nocolor")
    # Output should be non-colored plain text
    out, err = capsys.readouterr()
    assert "nocolor" in out

def test_get_logger_multiple_file_handlers(tmp_path):
    log_file = tmp_path / "log1.log"
    logger = log_manager.get_logger("MultiFileLogger", log_to_file=str(log_file))
    # Add again with same path (should not duplicate)
    logger2 = log_manager.get_logger("MultiFileLogger", log_to_file=str(log_file))
    file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
    assert len(file_handlers) == 1

def test_get_logger_different_files(tmp_path):
    log_file1 = tmp_path / "log1.log"
    log_file2 = tmp_path / "log2.log"
    logger = log_manager.get_logger("DifferentFilesLogger", log_to_file=str(log_file1))
    logger2 = log_manager.get_logger("DifferentFilesLogger", log_to_file=str(log_file2))
    # Should attach two file handlers to the same logger (two different files)
    file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
    assert len(file_handlers) == 2

def test_logger_propagate_false():
    logger = log_manager.get_logger("PropLogger")
    assert logger.propagate is False

def test_logger_level_argument():
    logger = log_manager.get_logger("LevelLogger", level=logging.ERROR)
    assert logger.level == logging.ERROR

def test_stream_handler_writes_stdout(capsys):
    # Should output to stdout
    logger = log_manager.get_logger("StdoutLogger")
    logger.info("streamout")
    out, err = capsys.readouterr()
    assert "streamout" in out

def test_logger_no_duplicate_handlers(monkeypatch):
    # Remove all handlers and call get_logger multiple times, handler should not duplicate
    logger = log_manager.get_logger("NoDupLogger")
    logger.handlers = []
    if hasattr(logger, "_saxoflow_colored_handler_attached"):
        delattr(logger, "_saxoflow_colored_handler_attached")
    handler_ids = []
    for _ in range(3):
        logger = log_manager.get_logger("NoDupLogger")
        handler_ids.append(id(logger.handlers[0]))
    # All handler ids should be the same (only one stream handler)
    assert all(h == handler_ids[0] for h in handler_ids)

