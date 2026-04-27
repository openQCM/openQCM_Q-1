"""
Application entry point for the openQCM Q-1 GUI.

Sets up the QApplication, the platform-specific taskbar / dock icon, parses
the CLI arguments and the logger, then opens the MainWindow.

Run from the project root with:
    python -m openQCM.app
or via the platform-specific launcher scripts in `scripts/`.
"""
import os
import sys
from multiprocessing import freeze_support

from PyQt5 import QtGui, QtWidgets

from openQCM.common.architecture import Architecture, OSType
from openQCM.common.arguments import Arguments
from openQCM.common.logger import Logger as Log
from openQCM.common.resources import get_resource_path
from openQCM.core.constants import MinimalPython, Constants
from openQCM.ui import mainWindow


TAG = ""  # set to "[Application]" for verbose tagged prints


class OPENQCM:
    """Top-level coordinator: builds the QApplication and runs the event loop."""

    def __init__(self, argv=sys.argv):
        # Required for PyInstaller-frozen builds that spawn children
        freeze_support()
        self._args = self._init_logger()

        # Ensure the runtime data directories exist next to the executable
        # (or next to the source tree in dev mode). This makes the .exe
        # self-sufficient: a fresh user can launch it without any companion
        # folder and Peak Detection will be able to write its output files.
        self._ensure_runtime_dirs()

        # On Windows, AppUserModelID must be set BEFORE creating the QApplication
        # so the taskbar groups our windows under the openQCM icon and not under
        # the Python interpreter icon.
        if Architecture.get_os() is OSType.windows:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                'openQCM.Q1.RealTimeMonitor.2.1')

        self._app = QtWidgets.QApplication(argv)

        # Application icon: ICO is preferred on Windows, PNG on macOS / Linux.
        if Architecture.get_os() is OSType.windows:
            icon_path = get_resource_path('icons/favicon.ico')
        else:
            icon_path = get_resource_path('icons/favicon.png')
        self._app.setWindowIcon(QtGui.QIcon(icon_path))

        # Set the Windows console title (only relevant when launched from cmd)
        if Architecture.get_os() is OSType.windows:
            import ctypes
            ctypes.windll.kernel32.SetConsoleTitleW(
                "Real-Time openQCM GUI - command line")

    def run(self):
        """Open the main window and enter the Qt event loop."""
        if not Architecture.is_python_version(MinimalPython.major, minor=MinimalPython.minor):
            self._fail()
            self.close()
            return

        print(TAG, "Path:", os.path.dirname(__file__))
        print('')
        print(TAG, "Application started")
        Log.i(TAG, "Application started")

        win = mainWindow.MainWindow(samples=self._args.get_user_samples())
        self._app.exec()
        print(TAG, "Finishing Application...")
        print(TAG, "Application closed")
        Log.i(TAG, "Finishing Application...\n")
        Log.i(TAG, "Application closed\n")
        win.close()
        self.close()

    def close(self):
        """Tear down the Qt event loop and exit the interpreter."""
        self._app.exit()
        Log.close()
        sys.exit()

    @staticmethod
    def _init_logger():
        """Parse CLI arguments and instantiate the logger."""
        args = Arguments()
        args.create()
        args.set_user_log_level()
        return args

    @staticmethod
    def _ensure_runtime_dirs():
        """
        Make sure the runtime data directories exist.

        Creates `openQCM/` (calibration files) and `logged_data/` (CSV logs)
        next to the executable so Peak Detection and Measurement can write
        their output without crashing on a fresh install.
        """
        for path in (Constants.csv_calibration_export_path,
                     Constants.csv_export_path,
                     Constants.log_export_path):
            if path and not os.path.isdir(path):
                try:
                    os.makedirs(path, exist_ok=True)
                    print(TAG, "Created runtime directory:", path)
                except OSError as e:
                    print(TAG, "WARNING: cannot create {}: {}".format(path, e))

    @staticmethod
    def _fail():
        """Emit a clear error if the running Python version is too old."""
        txt = "Application requires Python {}.{} to run".format(
            MinimalPython.major, MinimalPython.minor)
        print(TAG, txt)
        Log.e(TAG, txt)


if __name__ == '__main__':
    OPENQCM().run()
