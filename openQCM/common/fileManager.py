import os
from openQCM.common.architecture import Architecture,OSType

###############################################################################
# File operations: create directory, full path and check if the existing file
###############################################################################
class FileManager:

    ###########################################################################
    # Creates a directory if the specified path doesn't exist.
    ###########################################################################
    @staticmethod
    def create_dir(path=None):
        """
        :param path: Directory name or full path        :type path: str.
        :return: True if the specified directory exists :rtype: bool.
        """
        if path is not None:
            if not os.path.isdir(path):
                os.makedirs(path)
        return os.path.isdir(path)

    
    ###########################################################################
    # Creates a file full path based on parameters
    ###########################################################################    
    @staticmethod
    def create_full_path(filename, extension="txt", path=None):
        """
        :param filename: Name for the file        :type filename: str.
        :param extension: Extension for the file  :type extension: str.
        :param path: Path for the file, if needed :type path: str.
        :return: Full path for the specified file :rtype: str.
        """
        # sets the slash depending on the OS types
        if Architecture.get_os() is (OSType.macosx or OSType.linux):
            slash="/"
        else:
            slash="\\"
            
        if path is None:
            full_path = str("{}.{}".format(filename, extension))
        else:
            full_path = str("{}{}{}.{}".format(path,slash, filename, extension))
        return full_path


    ###########################################################################
    #Checks if a file exists (True if file exists)
    ###########################################################################
    @staticmethod
    def file_exists(filename):
        """
        :param filename: Name of the file, including path :type filename: str.
        :return: True if file exists :rtype: bool.
        """
        if filename is not None:
            return os.path.isfile(filename)
