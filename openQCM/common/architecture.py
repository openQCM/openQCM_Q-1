"""
Cross-platform helpers used to branch on the host OS and Python version.
"""
import platform
import sys
from enum import Enum


class OSType(Enum):
    unknown = 0
    linux = 1
    macosx = 2
    windows = 3


class Architecture:
    """Static utility methods to query OS / Python information."""

    @staticmethod
    def get_os():
        """Return the current `OSType` based on `platform.platform()`."""
        name = str(Architecture.get_os_name())
        if "Linux" in name:
            return OSType.linux
        if "Windows" in name:
            return OSType.windows
        # 'Darwin' on most macOS releases; 'macOS' on macOS 12+ in some toolchains
        if "Darwin" in name or "macOS" in name:
            return OSType.macosx
        return OSType.unknown

    @staticmethod
    def get_os_name():
        """Return the platform string as reported by `platform.platform()`."""
        return platform.platform()

    @staticmethod
    def get_path():
        """Return the directory the script is running from (sys.path[0])."""
        return sys.path[0]

    @staticmethod
    def get_python_version():
        """Return the running Python version formatted as 'major.minor.release'."""
        v = sys.version_info
        return "{}.{}.{}".format(v[0], v[1], v[2])

    @staticmethod
    def is_python_version(major, minor=0):
        """
        :return: True if the running interpreter is at least `major.minor`.
        """
        v = sys.version_info
        return v[0] >= major and v[1] >= minor
