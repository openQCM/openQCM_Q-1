"""
Application-wide logger.

Wraps Python's `logging` package with a fixed file format and an optional
console handler. The log file lives in `Constants.log_export_path` and
is rotated when it exceeds `Constants.log_max_bytes`.

Usage:
    from openQCM.common.logger import Logger as Log
    Log.i("[Tag]", "Some informational message")
    Log.w("[Tag]", "Some warning")
    Log.e("[Tag]", "Some error")

Logger must be instantiated once at application start (typically by
`app.py`) before any module calls the static helpers.
"""
import logging
import logging.handlers
import sys
from enum import Enum

from openQCM.common.architecture import Architecture
from openQCM.common.fileManager import FileManager
from openQCM.core.constants import Constants


class LoggerLevel(Enum):
    CRITICAL = logging.CRITICAL
    ERROR = logging.ERROR
    WARNING = logging.WARNING
    INFO = logging.INFO
    DEBUG = logging.DEBUG


class Logger:
    """Static-style logging facade. Instantiate once to configure handlers."""

    def __init__(self, level, enable_console=True):
        """
        :param level:          a `LoggerLevel` enum value
        :param enable_console: also emit log records to stdout
        """
        log_format_file = logging.Formatter('%(asctime)s,%(levelname)s,%(message)s')
        log_format_console = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
        self.logger = logging.getLogger()
        self.logger.setLevel(level.value)

        FileManager.create_dir(Constants.log_export_path)
        file_handler = logging.handlers.RotatingFileHandler(
            "{}/{}".format(Constants.log_export_path, Constants.log_filename),
            maxBytes=Constants.log_max_bytes,
            backupCount=0)
        file_handler.setFormatter(log_format_file)
        self.logger.addHandler(file_handler)

        if enable_console:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(log_format_console)
            self.logger.addHandler(console_handler)

        self._show_user_info()

    @staticmethod
    def close():
        """Flush and shut down all logging handlers."""
        logging.shutdown()

    @staticmethod
    def d(tag, msg):
        """Log at DEBUG level. `tag` is prepended in square brackets."""
        logging.debug("[{}] {}".format(tag, msg))

    @staticmethod
    def i(tag, msg):
        """Log at INFO level."""
        logging.info("[{}] {}".format(tag, msg))

    @staticmethod
    def w(tag, msg):
        """Log at WARNING level."""
        logging.warning("[{}] {}".format(tag, msg))

    @staticmethod
    def e(tag, msg):
        """Log at ERROR level."""
        logging.error("[{}] {}".format(tag, msg))

    @staticmethod
    def _show_user_info():
        """Emit a banner with app version and platform info at startup."""
        tag = ""
        print("-----------------------------")
        print(" {} - {}".format(Constants.app_title, Constants.app_version))
        print("-----------------------------")
        print("\n{} SYSTEM INFORMATIONS:".format(tag))
        print(tag, "Platform: {}".format(Architecture.get_os_name()))
        Logger.i(tag, "Platform: {}".format(Architecture.get_os_name()))
        Logger.i(tag, "Path: {}".format(Architecture.get_path()))
        print(tag, "Python version: {}".format(Architecture.get_python_version()))
        Logger.i(tag, "Python version: {}".format(Architecture.get_python_version()))
