import csv
from openQCM.common.fileManager import FileManager
from openQCM.core.constants import Constants
from openQCM.common.logger import Logger as Log
from time import strftime, localtime
import datetime
import numpy as np
import os

TAG = ""#"[FileStorage]"

###############################################################################
# Stores and exports data to file (CSV/TXT): saves incoming and outcoming data
###############################################################################
class FileStorage:
    
    ###########################################################################
    # Saves CSV files of processed data in an assigned directory
    ###########################################################################
    @staticmethod
    def CSVsave(filename, path, data_save0, data_save1, data_save2, data_save3): 
        """
        :param filename: Name for the file :type filename: str.
        :param path: Path for the file     :type path: str.
        :param data_save1: data to store (resonance frequency) :type float. 
        :param data_save2: data to store (dissipation)         :type float.
        """
        # Creates a directory if the specified path doesn't exist
        #FileManager.create_dir(path)
        # Creates a file full path based on parameters
        full_path = FileManager.create_full_path(filename, extension=Constants.csv_extension, path=path)
        if not FileManager.file_exists(full_path):
            print("\n")
            print(TAG, "Exporting data to CSV file...")
            print(TAG, "Storing in: {}".format(full_path))
            Log.i(TAG, "Storing in: {}".format(full_path))
            
        # checks the path for the header insertion
        if os.path.exists(full_path):
           header_exists = True
        else:
           header_exists = False
           
        # opens the file to write data
        with open(full_path,'a', newline='') as tempFile:   
         tempFileWriter = csv.writer(tempFile)
         # inserts the header if it doesn't exist
         if not header_exists:
            tempFileWriter.writerow(["Date","Time","Relative_time","Temperature", "Resonance_Frequency", "Dissipation"])
         #csv_time_prefix = strftime(Constants.csv_default_prefix, localtime())
         #now = datetime.datetime.now()
         #csv_time_prefix = "{}-{}-{}.{}:{}:{}.{}".format(now.year,now.month,now.day,now.hour,now.minute,now.second,now.microsecond)         
         fix1= "%Y-%m-%d"
         fix2= "%H:%M:%S"
         csv_time_prefix1 = (strftime(fix1, localtime()))
         csv_time_prefix2 = (strftime(fix2, localtime()))
         d0=float("{0:.2f}".format(data_save0))
         d1=float("{0:.2f}".format(data_save1))
         d2=float("{0:.2f}".format(data_save2))
         #d3=float("{0:.4e}".format(data_save3))
         tempFileWriter.writerow([csv_time_prefix1,csv_time_prefix2, d0, d1, d2, data_save3])
         #tempFileWriter.writerow([csv_time_prefix, data_save1, data_save2, data_save3])
        tempFile.close()
    
    
    ###########################################################################
    # Saves a CSV-formatted CSV file per sweeps in an assigned directory
    ###########################################################################     
    @staticmethod
    def CSV_sweeps_save(filename, path, data_save1, data_save2, data_save3):
        """
        :param filename: Name for the file :type filename: str.
        :param path: Path for the file     :type path: str.
        :param data_save1: data to store (frequency) :type float. 
        :param data_save2: data to store (Amplitude) :type float.
        :param data_save2: data to store (Phase)     :type float.
        """
        # Creates a directory if the specified path doesn't exist
        FileManager.create_dir(path)
        # Creates a file full path based on parameters
        full_path = FileManager.create_full_path(filename, extension=Constants.csv_extension, path=path)
        # creates CSV file
        np.savetxt(full_path, np.column_stack([data_save1, data_save2, data_save3]), delimiter=',')
    
    
    ###########################################################################
    # Saves a CSV-formatted Text file per sweeps in an assigned directory
    ###########################################################################     
    @staticmethod
    def TXT_sweeps_save(filename, path, data_save1, data_save2, data_save3):
        """
        :param filename: Name for the file :type filename: str.
        :param path: Path for the file     :type path: str.
        :param path: Path for the file     :type path: str.
        :param data_save1: data to store (frequency) :type float. 
        :param data_save2: data to store (Amplitude) :type float.
        :param data_save2: data to store (Phase)     :type float.
        """
        # Creates a directory if the specified path doesn't exist
        FileManager.create_dir(path)
        # Creates a file full path based on parameters
        full_path = FileManager.create_full_path(filename, extension=Constants.txt_extension, path=path)
        # creates TXT file
        np.savetxt(full_path, np.column_stack([data_save1, data_save2, data_save3]))  
