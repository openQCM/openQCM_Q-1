"""
Resource Path Helper for PyInstaller Compatibility

This module provides functions to resolve paths correctly both during
development and when running as a PyInstaller executable.

Key concepts:
- RESOURCES (icons, images): bundled with PyInstaller, accessed via _MEIPASS
- DATA (logged_data, calibration): stored alongside executable, not in _MEIPASS

Usage:
    from openQCM.common.resources import get_resource_path, get_data_path

    icon_path = get_resource_path('icons/favicon.ico')
    data_dir = get_data_path('logged_data')
"""

import sys
import os


def is_frozen():
    """
    Check if running as a PyInstaller executable.

    :return: True if running as frozen executable, False in development
    :rtype: bool
    """
    return getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')


def get_base_path():
    """
    Get the base path for the application.

    In development: returns the OPENQCM directory (parent of openQCM package)
    In PyInstaller: returns sys._MEIPASS (temporary extraction folder)

    :return: Base path for bundled resources
    :rtype: str
    """
    if is_frozen():
        # PyInstaller: resources are extracted to _MEIPASS
        return sys._MEIPASS
    else:
        # Development: go up from openQCM/common/ to OPENQCM/
        return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_resource_path(relative_path):
    """
    Get the absolute path for a bundled resource (icons, images, etc.).

    These are resources that are bundled with the application and
    should be read-only.

    :param relative_path: Path relative to OPENQCM directory
    :type relative_path: str
    :return: Absolute path to the resource
    :rtype: str

    Example:
        icon = get_resource_path('icons/favicon.ico')
        logo = get_resource_path('icons/openqcm-logo.png')
    """
    return os.path.join(get_base_path(), relative_path)


def get_data_path(relative_path=''):
    """
    Get the absolute path for user data (logged_data, calibration files, etc.).

    In development: returns path relative to OPENQCM directory
    In PyInstaller: returns path relative to the executable's directory

    This ensures that user data is stored in a writable location that
    persists between application runs.

    :param relative_path: Path relative to data directory (optional)
    :type relative_path: str
    :return: Absolute path to the data location
    :rtype: str

    Example:
        log_dir = get_data_path('logged_data')
        calib_file = get_data_path('723calibration/723peak.txt')
    """
    if is_frozen():
        # PyInstaller: use directory where executable is located
        base = os.path.dirname(sys.executable)
    else:
        # Development: use OPENQCM directory
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    if relative_path:
        return os.path.join(base, relative_path)
    return base


def get_application_path():
    """
    Get the path where the application is running from.

    Useful for determining where to save configuration files or
    where the executable is located.

    :return: Directory containing the running application
    :rtype: str
    """
    if is_frozen():
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
