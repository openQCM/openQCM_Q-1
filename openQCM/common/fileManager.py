"""Lightweight filesystem helpers used by the logger and CSV writers."""
import os

from openQCM.common.architecture import Architecture, OSType


class FileManager:
    """Static helpers for directory creation and path composition."""

    @staticmethod
    def create_dir(path=None):
        """
        Ensure `path` exists (mkdir -p style).

        :return: True if the directory exists after the call.
        """
        if path is not None:
            if not os.path.isdir(path):
                os.makedirs(path)
        return os.path.isdir(path)

    @staticmethod
    def create_full_path(filename, extension="txt", path=None):
        """
        Compose a full file path with the appropriate platform separator.

        :param filename:  base name (no extension)
        :param extension: extension without the leading dot
        :param path:      optional directory (None → file in CWD)
        :return:          composed full path as a string
        """
        # On POSIX systems use '/'; on Windows use '\'.
        if Architecture.get_os() in (OSType.macosx, OSType.linux):
            slash = "/"
        else:
            slash = "\\"

        if path is None:
            return "{}.{}".format(filename, extension)
        return "{}{}{}.{}".format(path, slash, filename, extension)

    @staticmethod
    def file_exists(filename):
        """Return True if `filename` points to an existing file."""
        if filename is not None:
            return os.path.isfile(filename)
        return False
