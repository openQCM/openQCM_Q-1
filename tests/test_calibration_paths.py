"""
Offline checks for per-board calibration folders (dual-instrument mode).

The legacy folder must resolve to exactly the paths used before
CalibrationPaths existed, and a per-board folder holding the same files
must give the acquisition process the same overtones, sweep window and
baseline. No hardware or display needed.

Run from OPENQCM/:  python -m pytest tests/test_calibration_paths.py
           or:      python tests/test_calibration_paths.py
"""
import os
import pickle
import shutil
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openQCM.common.calibrationPaths import CalibrationPaths
from openQCM.core.constants import Constants, SourceType
from openQCM.core.worker import Worker
from openQCM.processors.Calibration import CalibrationProcess
from openQCM.processors.Serial import SerialProcess


def test_legacy_paths_unchanged():
    leg = CalibrationPaths.legacy()
    assert leg.peak_frequencies == Constants.cvs_peakfrequencies_path
    assert leg.calibration_3 == Constants.csv_calibration_path3
    assert leg.calibration_5 == Constants.csv_calibration_path
    assert leg.calibration_10 == Constants.csv_calibration_path10


def test_board_keys():
    def key(**kw):
        return os.path.basename(CalibrationPaths.for_board(**kw).root)
    assert key(serial="19-0055") == "19-0055"
    assert key(port="/dev/tty.usbmodem14101") == "port_dev_tty.usbmodem14101"
    assert key(port="COM3") == "port_COM3"
    # Serial wins over port: the same board keeps its folder on any port
    assert key(serial="19-0055", port="COM7") == "19-0055"
    board = CalibrationPaths.for_board(serial="19-0055")
    assert pickle.loads(pickle.dumps(board)).root == board.root


def test_board_folder_matches_legacy():
    leg = CalibrationPaths.legacy()
    if not leg.has_calibration():
        print("SKIP: no legacy calibration in openQCM/")
        return
    tmp = tempfile.mkdtemp()
    try:
        for f in (leg.peak_frequencies, leg.calibration_5, leg.calibration_10):
            if os.path.isfile(f):
                shutil.copy(f, tmp)
        speeds = SerialProcess.get_speeds()
        assert SerialProcess.get_speeds(tmp) == speeds
        assert Worker.get_source_speeds(SourceType.serial, tmp) == speeds

        samples = Constants.argument_default_samples
        legacy_proc, board_proc = SerialProcess(None), SerialProcess(None, calib_dir=tmp)
        for proc in (legacy_proc, board_proc):
            proc._overtone_int = 0
        assert board_proc.get_frequencies(samples)[:3] == legacy_proc.get_frequencies(samples)[:3]
        assert np.allclose(board_proc.baseline_coeffs(), legacy_proc.baseline_coeffs())
    finally:
        shutil.rmtree(tmp)


def test_empty_board_folder():
    tmp = tempfile.mkdtemp()
    try:
        assert not CalibrationPaths(tmp).has_calibration()
        assert SerialProcess.get_speeds(tmp) == []
    finally:
        shutil.rmtree(tmp)


def test_peak_detection_writes_into_board_folder():
    tmp = tempfile.mkdtemp()
    try:
        for f0 in (5e6, 10e6):
            _, peaks, calib, _, _ = CalibrationProcess(None, calib_dir=tmp).auto_detect_qcm_type(f0)
            assert os.path.dirname(peaks) == tmp and os.path.dirname(calib) == tmp
        _, peaks, _, _, _ = CalibrationProcess(None).auto_detect_qcm_type(5e6)
        assert peaks == Constants.cvs_peakfrequencies_path
    finally:
        shutil.rmtree(tmp)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
