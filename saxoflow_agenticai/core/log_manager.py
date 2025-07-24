# saxoflow_agenticai/core/log_manager.py

import logging
import sys
import os

try:
    import colorlog
    COLORLOG_AVAILABLE = True
except ImportError:
    COLORLOG_AVAILABLE = False

def get_logger(name="SaxoFlowAgent", level=logging.INFO, log_to_file: str = None) -> logging.Logger:
    """
    Return a configured logger.
    - name: logger name (e.g., "RTLGenAgent", "TBReviewAgent")
    - level: logging level (e.g., logging.INFO)
    - log_to_file: Optional path to file for output.
    NOTE: For colored logs, `colorlog` Python package must be installed.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Prevent duplicate handlers (stream)
    if not getattr(logger, "_saxoflow_colored_handler_attached", False):
        if COLORLOG_AVAILABLE and sys.stdout.isatty():
            handler = colorlog.StreamHandler(sys.stdout)
            handler.setFormatter(colorlog.ColoredFormatter(
                "%(log_color)s[%(levelname)s] %(asctime)s - [%(name_log_color)s%(name)s%(reset)s] %(message_log_color)s%(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
                log_colors={
                    'DEBUG':    'cyan',
                    'INFO':     'green',
                    'WARNING':  'yellow',
                    'ERROR':    'red',
                    'CRITICAL': 'bold_red',
                },
                secondary_log_colors={
                    'name': {
                        'RTLGenAgent':      'blue',
                        'TBGenAgent':       'magenta',
                        'RTLReviewAgent':   'cyan',
                        'TBReviewAgent':    'bold_magenta',
                        'DebugAgent':       'bold_yellow',
                        'SimAgent':         'white',
                        'FormalPropGenAgent':    'bold_green',
                        'FormalPropReviewAgent': 'bold_cyan',
                        'ReportAgent':      'white',
                        'AgentOrchestrator': 'bold_white',
                        'AgentManager':     'bold_blue',
                        # Add more as needed, make sure names match!
                    },
                    'message': {
                        'RTLGenAgent':      'blue',
                        'TBGenAgent':       'magenta',
                        'RTLReviewAgent':   'cyan',
                        'TBReviewAgent':    'bold_magenta',
                        'DebugAgent':       'bold_yellow',
                        'SimAgent':         'white',
                        'FormalPropGenAgent':    'bold_green',
                        'FormalPropReviewAgent': 'bold_cyan',
                        'ReportAgent':      'white',
                        'AgentOrchestrator': 'bold_white',
                        'AgentManager':     'bold_blue',
                    }
                }
            ))
        else:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(logging.Formatter(
                "[%(levelname)s] %(asctime)s - [%(name)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            ))
        logger.addHandler(handler)
        logger._saxoflow_colored_handler_attached = True

    # --- File handler (plain text, only add if not already attached) ---
    if log_to_file:
        log_file_path = os.path.abspath(log_to_file)
        already_attached = any(
            isinstance(h, logging.FileHandler) and
            getattr(h, 'baseFilename', None) == log_file_path
            for h in logger.handlers
        )
        if not already_attached:
            fhandler = logging.FileHandler(log_file_path, encoding='utf-8')
            fhandler.setFormatter(logging.Formatter(
                "[%(levelname)s] %(asctime)s - [%(name)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            ))
            logger.addHandler(fhandler)

    logger.propagate = False

    return logger
