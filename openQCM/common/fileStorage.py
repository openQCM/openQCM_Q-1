"""
CSV / TXT helpers for exporting acquired data.

Note: the live measurement log is written by `Worker._write_csv_row()` for
performance (the file stays open across the whole run). The helpers here
are used for one-shot dumps:
    - CSVsave              — append a single row of measurement data
    - CSV_sweeps_save      — dump a single sweep as CSV
    - TXT_sweeps_save      — dump a single sweep as TXT (used by the
                             calibration storage path)
"""
import os
import csv
import datetime
from time import strftime, localtime

import numpy as np

from openQCM.common.fileManager import FileManager
from openQCM.common.logger import Logger as Log
from openQCM.core.constants import Constants


TAG = ""  # set to "[FileStorage]" for verbose tagged prints


class FileStorage:

    @staticmethod
    def CSVsave(filename, path, data_save0, data_save1, data_save2, data_save3):
        """
        Append a row to the measurement CSV log.

        Columns: Date, Time, Relative_time, Temperature, Resonance_Frequency, Dissipation.
        Inserts the header automatically the first time the file is created.

        Note: kept for backward compatibility. The live acquisition uses
        `Worker._write_csv_row()` which keeps the file handle open.
        """
        full_path = FileManager.create_full_path(
            filename, extension=Constants.csv_extension, path=path)
        if not FileManager.file_exists(full_path):
            print("\n")
            print(TAG, "Exporting data to CSV file...")
            print(TAG, "Storing in: {}".format(full_path))
            Log.i(TAG, "Storing in: {}".format(full_path))

        header_exists = os.path.exists(full_path)

        with open(full_path, 'a', newline='') as tempFile:
            writer = csv.writer(tempFile)
            if not header_exists:
                writer.writerow(["Date", "Time", "Relative_time",
                                 "Temperature", "Resonance_Frequency", "Dissipation"])
            csv_date = strftime("%Y-%m-%d", localtime())
            csv_time = strftime("%H:%M:%S", localtime())
            d0 = float("{0:.2f}".format(data_save0))
            d1 = float("{0:.2f}".format(data_save1))
            d2 = float("{0:.2f}".format(data_save2))
            writer.writerow([csv_date, csv_time, d0, d1, d2, data_save3])

    @staticmethod
    def CSV_sweeps_save(filename, path, data_save1, data_save2, data_save3):
        """
        Save one acquired sweep (frequency, amplitude, phase) as a CSV file.

        :param data_save1: frequency array
        :param data_save2: amplitude array
        :param data_save3: phase array
        """
        FileManager.create_dir(path)
        full_path = FileManager.create_full_path(
            filename, extension=Constants.csv_extension, path=path)
        np.savetxt(full_path,
                   np.column_stack([data_save1, data_save2, data_save3]),
                   delimiter=',')

    @staticmethod
    def TXT_sweeps_save(filename, path, data_save1, data_save2, data_save3):
        """
        Save one acquired sweep (frequency, amplitude, phase) as a
        whitespace-separated TXT file. Used by the calibration storage
        path (e.g. Calibration_5MHz.txt).

        :param data_save1: frequency array
        :param data_save2: amplitude array
        :param data_save3: phase array
        """
        FileManager.create_dir(path)
        full_path = FileManager.create_full_path(
            filename, extension=Constants.txt_extension, path=path)
        np.savetxt(full_path,
                   np.column_stack([data_save1, data_save2, data_save3]))
