"""
Location of the Peak Detection output files (PeakFrequencies.txt and the
full Calibration_<N>MHz.txt sweeps).

A calibration belongs to a board + sensor, not to the installation. In
single-instrument mode the historical folder `openQCM/` is used (legacy
root, unchanged behaviour). In dual-instrument mode each board gets its own
folder `openQCM/boards/<key>/`, keyed by the EEPROM serial number, so that
Peak Detection on one board can never overwrite the calibration of the
other.

Instances only hold a plain string root, so they pickle cleanly when the
acquisition processes are spawned (Windows / macOS `spawn` start method).
"""
import os
import re

from openQCM.core.constants import Constants


class CalibrationPaths:

    boards_subdir = "boards"

    def __init__(self, root):
        self.root = root

    @classmethod
    def legacy(cls):
        """Shared installation folder used by single-instrument mode."""
        return cls(Constants.csv_calibration_export_path)

    @classmethod
    def for_board(cls, serial=None, port=None):
        """
        Per-board folder. The EEPROM serial is the stable key; boards without
        a programmed serial (NO_SERIAL, pre-v2.2 firmware) fall back to the
        port name, which is stable per device on macOS and usually on Windows
        but not guaranteed — the caller should warn the user.
        """
        def safe(s):
            return re.sub(r'[^A-Za-z0-9._-]+', '_', s).strip('_')

        if serial:
            key = safe(serial)
        elif port:
            key = "port_" + safe(port)
        else:
            raise ValueError("A board serial number or a port name is required")
        return cls(os.path.join(Constants.csv_calibration_export_path,
                                cls.boards_subdir, key))

    # ------------------------------------------------------------------
    # File paths
    # ------------------------------------------------------------------
    def _txt(self, name):
        return os.path.join(self.root, "{}.{}".format(name, Constants.txt_extension))

    @property
    def peak_frequencies(self):
        return self._txt(Constants.csv_peakfrequencies_filename)

    @property
    def calibration_3(self):
        return self._txt(Constants.csv_calibration_filename3)

    @property
    def calibration_5(self):
        return self._txt(Constants.csv_calibration_filename)

    @property
    def calibration_10(self):
        return self._txt(Constants.csv_calibration_filename10)

    def calibration_for(self, fundamental):
        """Full calibration sweep file for the sensor with this fundamental (Hz)."""
        if 4e6 < fundamental < 6e6:
            return self.calibration_5
        if 9e6 < fundamental < 11e6:
            return self.calibration_10
        return None

    def has_calibration(self):
        """True once Peak Detection has written PeakFrequencies.txt here."""
        return os.path.isfile(self.peak_frequencies)

    def __repr__(self):
        return "CalibrationPaths({!r})".format(self.root)
