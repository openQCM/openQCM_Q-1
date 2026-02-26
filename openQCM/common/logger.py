import logging
import logging.handlers
import sys
from enum import Enum

from openQCM.common.architecture import Architecture
from openQCM.common.fileManager import FileManager
from openQCM.core.constants import Constants

###############################################################################
# Logging package - All packages can use this module
###############################################################################
class Logger:

    ###########################################################################
    # Creates logging file (.txt)
    ###########################################################################
    def __init__(self, level, enable_console=True):
        """
        :param level: Level to show in log.
        :type level: int.
        """
        log_format_file = logging.Formatter('%(asctime)s,%(levelname)s,%(message)s')
        log_format_console = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
        self.logger = logging.getLogger()
        self.logger.setLevel(level.value)

        FileManager.create_dir(Constants.log_export_path)
        file_handler = logging.handlers.RotatingFileHandler("{}/{}"
                                                            .format(Constants.log_export_path, Constants.log_filename),
                                                            maxBytes=Constants.log_max_bytes,
                                                            backupCount=0)
        file_handler.setFormatter(log_format_file)
        self.logger.addHandler(file_handler)

        if enable_console:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(log_format_console)
            self.logger.addHandler(console_handler)
        self._show_user_info()

    ###########################################################################
    # Closes the enabled loggers.
    ###########################################################################
    @staticmethod
    def close():
        logging.shutdown()

    ###########################################################################
    # Logs at debug level (debug,info,warning and error messages)
    ###########################################################################
    @staticmethod
    def d(tag, msg):
        """
        :param tag: TAG to identify the log :type tag: str.
        :param msg: Message to log.         :type msg: str.
        """
        logging.debug("[{}] {}".format(str(tag), str(msg)))
    
    ####
    @staticmethod
    def i(tag, msg):
        logging.info("[{}] {}".format(str(tag), str(msg)))
    
    ####
    @staticmethod
    def w(tag, msg):
        logging.warning("[{}] {}".format(str(tag), str(msg)))
    
    ####
    @staticmethod
    def e(tag, msg):
        logging.error("[{}] {}".format(str(tag), str(msg)))


    ###########################################################################
    # logs and prints architecture-related informations
    ###########################################################################
    @staticmethod
    def _show_user_info():
        tag = ""#"[User]"
        print("-----------------------------")
        print(" {} - {}".format(Constants.app_title,Constants.app_version))
        print("-----------------------------")
        print("\n{} SYSTEM INFORMATIONS:".format(tag))
        print(tag,"Platform: {}".format(Architecture.get_os_name()))
        Logger.i(tag, "Platform: {}".format(Architecture.get_os_name()))
        Logger.i(tag, "Path: {}".format(Architecture.get_path()))
        print(tag,"Python version: {}".format(Architecture.get_python_version()))
        Logger.i(tag, "Python version: {}".format(Architecture.get_python_version()))


###############################################################################
# Enumeration for the Logger levels
###############################################################################        
class LoggerLevel(Enum):
    CRITICAL = logging.CRITICAL
    ERROR = logging.ERROR
    WARNING = logging.WARNING
    INFO = logging.INFO
    DEBUG = logging.DEBUG
