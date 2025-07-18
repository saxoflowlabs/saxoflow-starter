# saxoflow_agenticai/core/log_manager.py
import logging
import sys
import os

def get_logger(name="SaxoFlowAgent", level=logging.INFO, log_to_file: str = None) -> logging.Logger:
    """
    Return a configured logger.
    - name: logger name (usually "SaxoFlowAgent")
    - level: logging level (e.g., logging.INFO)
    - log_to_file: Optional path to file for output.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Avoid duplicate handlers
    if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "[%(levelname)s] %(asctime)s - %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    # Optionally add file handler (for agent session logs)
    if log_to_file and not any(isinstance(h, logging.FileHandler) and h.baseFilename == os.path.abspath(log_to_file) for h in logger.handlers):
        fhandler = logging.FileHandler(log_to_file, encoding='utf-8')
        fformatter = logging.Formatter(
            "[%(levelname)s] %(asctime)s - %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        fhandler.setFormatter(fformatter)
        logger.addHandler(fhandler)

    return logger
