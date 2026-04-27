"""
CLI argument parser for the openQCM Q-1 application.

Supported flags:
    -i / --info       enable INFO log level
    -d / --debug      enable DEBUG log level
    -v / --verbose    also emit log records to the console
    -s / --samples    override the default samples-per-sweep
"""
import argparse

from openQCM.common.logger import Logger as Log
from openQCM.common.logger import LoggerLevel
from openQCM.core.constants import Constants


TAG = ""  # set to "[Arguments]" for verbose tagged prints


class Arguments:

    def __init__(self):
        self._parser = None

    def create(self):
        """Build the argparse parser and parse `sys.argv`."""
        parser = argparse.ArgumentParser(
            description='openQCM Q-1 — real-time QCM acquisition and logging GUI')
        parser.add_argument("-i", "--info",
                            dest="log_level_info",
                            action='store_true',
                            help="Enable INFO-level log messages")
        parser.add_argument("-d", "--debug",
                            dest="log_level_debug",
                            action='store_true',
                            help="Enable DEBUG-level log messages")
        parser.add_argument("-v", "--verbose",
                            dest="log_to_console",
                            action='store_true',
                            help="Mirror log messages to the console",
                            default=Constants.log_default_console_log)
        parser.add_argument("-s", "--samples",
                            dest="user_samples",
                            default=Constants.argument_default_samples,
                            help="Override the default samples-per-sweep")
        self._parser = parser.parse_args()

    def set_user_log_level(self):
        """Configure the logger according to the parsed arguments."""
        if self._parser is None:
            Log.w(TAG, "Parser was not created!")
            return None
        self._parse_log_level()

    def get_user_samples(self):
        """Return the samples-per-sweep chosen by the user (or the default)."""
        return int(self._parser.user_samples)

    def get_user_console_log(self):
        """Return True when `--verbose` was passed."""
        return self._parser.log_to_console

    def _parse_log_level(self):
        """Internal: instantiate the Logger with the requested level."""
        log_to_console = self.get_user_console_log()
        level = LoggerLevel.INFO
        if self._parser.log_level_info:
            level = LoggerLevel.INFO
        elif self._parser.log_level_debug:
            level = LoggerLevel.DEBUG
        Log(level, enable_console=log_to_console)
