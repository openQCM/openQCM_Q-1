"""
Offline regression test for the two-phase peak detection.

Replays real full-spectrum calibration sweeps (1-51 MHz, 1 kHz step)
through the very same CalibrationProcess methods the application uses, so
the algorithm can be validated without an instrument attached.

Run from the repository root:
    python -m unittest discover -s tests -v
"""
import os
import subprocess
import sys
import unittest

import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")   # constants.py imports pyqtgraph

from openQCM.core.constants import Constants                      # noqa: E402
from openQCM.processors.Calibration import CalibrationProcess     # noqa: E402
from openQCM.common.switcher import OvertoneSwitcher              # noqa: E402

TOL_HZ = 2000   # two sweep steps

# file -> (nominal MHz, fundamental Hz, accepted overtones Hz)
# The two files under openQCM/ are the committed factory defaults but are
# rewritten by every Peak Detection run; their expectations hold only for
# the committed content, so they are skipped when modified locally.
FIXTURES = {
    "openQCM/Calibration_5MHz.txt":
        (5, 5.003e6, [14.994e6, 24.986e6, 34.977e6, 44.966e6]),
    "openQCM/Calibration_10MHz.txt":
        (10, 10.018e6, [30.087e6, 50.150e6]),
    # Counter-example that once got F3 rejected (phase peak 35 kHz off)
    "tools/Calibration_10MHz.txt":
        (10, 10.019e6, [30.091e6, 50.155e6]),
    # 8 MHz quartz (Jan 2019): F3 has a spurious phase mode 96 kHz above the
    # magnitude peak; the 7th overtone (56 MHz) is outside the sweep
    "tools/Calibration_8MHz.txt":
        (8, 7.998e6, [23.938e6, 39.873e6]),
}


def locally_modified(relpath):
    """True if `relpath` differs from the committed version (or git is unavailable)."""
    try:
        return subprocess.call(["git", "diff", "--quiet", "--", relpath],
                               cwd=REPO_ROOT, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL) != 0
    except OSError:
        return True


def run_detection(relpath):
    data = np.loadtxt(os.path.join(REPO_ROOT, relpath))
    freq, mag, phase = data[:, 0], data[:, 1], data[:, 2]
    proc = CalibrationProcess(parser_process=None)
    mag_c, phase_c = proc.baseline_correction(freq, mag, phase)
    f0 = proc.peak_detection_fundamental(freq, mag_c, phase_c)
    overtones = proc.peak_detection_overtones(freq, mag_c, phase_c, f0)
    return proc, f0, overtones


class PeakDetectionRegression(unittest.TestCase):

    def test_fixtures(self):
        skipped = []
        for relpath, (nominal, f0_exp, ov_exp) in FIXTURES.items():
            if relpath.startswith("openQCM/") and locally_modified(relpath):
                skipped.append(relpath)   # SkipTest inside a subTest would abort the loop
                continue
            with self.subTest(file=relpath):
                proc, f0, overtones = run_detection(relpath)
                self.assertAlmostEqual(f0, f0_exp, delta=TOL_HZ)
                self.assertEqual(len(overtones), len(ov_exp),
                                 "accepted overtones: {}".format(overtones))
                for got, exp in zip(overtones, ov_exp):
                    self.assertAlmostEqual(got, exp, delta=TOL_HZ)
                self.assertTrue(proc.is_valid_quartz(f0, len(overtones)))
                label, _, path_calib, filename = proc.describe_quartz(f0)
                self.assertEqual(label, "{} MHz QCM".format(nominal))
                self.assertEqual(filename, "Calibration_{}MHz".format(nominal))
                self.assertTrue(path_calib.endswith("Calibration_{}MHz.txt".format(nominal)))
        if skipped:
            print("\n[skipped, rewritten by a local Peak Detection run — restore with "
                  "`git checkout -- <file>`]: " + ", ".join(skipped))
        self.assertLess(len(skipped), len(FIXTURES), "every fixture was skipped")


class GenericQuartzRules(unittest.TestCase):

    def test_legacy_file_names_are_preserved(self):
        self.assertEqual(Constants.calibration_filename_for(5.003e6),
                         Constants.csv_calibration_filename)
        self.assertEqual(Constants.calibration_filename_for(10.018e6),
                         Constants.csv_calibration_filename10)
        self.assertEqual(Constants.calibration_path_for(10.018e6),
                         Constants.csv_calibration_path10)

    def test_validity_needs_range_and_harmonics(self):
        valid = CalibrationProcess.is_valid_quartz
        self.assertTrue(valid(8.0e6, 1))
        self.assertFalse(valid(8.0e6, 0), "a lone peak is not a resonator")
        self.assertFalse(valid(0.5e6, 3), "below the fundamental search range")
        self.assertFalse(valid(13.0e6, 3), "above the fundamental search range")

    def test_lone_spurious_peak_is_rejected(self):
        # Synthetic sweep: one sharp peak at 8 MHz and no harmonics at all
        freq = Constants.calibration_readFREQ
        mag = -10 + 15 * np.exp(-0.5 * ((freq - 8e6) / 2e3) ** 2)
        phase = 5 + 40 * np.exp(-0.5 * ((freq - 8e6) / 2e3) ** 2)
        proc = CalibrationProcess(parser_process=None)
        mag_c, phase_c = proc.baseline_correction(freq, mag, phase)
        f0 = proc.peak_detection_fundamental(freq, mag_c, phase_c)
        self.assertAlmostEqual(f0, 8e6, delta=TOL_HZ)
        overtones = proc.peak_detection_overtones(freq, mag_c, phase_c, f0)
        self.assertEqual(len(overtones), 0)
        self.assertFalse(proc.is_valid_quartz(f0, len(overtones)))


class SweepProfiles(unittest.TestCase):
    """The frequency-keyed table must reproduce the former per-crystal values."""

    LEGACY = {   # resonance Hz -> (L, R, SG window, spline)
        5.003e6:  (15000, 5000,  9, 0.05),   # 5 MHz F0
        14.994e6: (15000, 5000, 11, 0.01),   # 5 MHz F3
        24.986e6: (15000, 5000, 11, 0.01),   # 5 MHz F5
        34.977e6: (50000, 2500, 33, 0.01),   # 5 MHz F7
        44.966e6: (5000000, 100000, 5, 0.5), # 5 MHz F9 (placeholder)
        10.018e6: (15000, 5000, 11, 0.01),   # 10 MHz F0
        30.087e6: (15000, 5000, 11, 0.01),   # 10 MHz F3
        50.150e6: (23000, 3000, 19, 0.01),   # 10 MHz F5
    }

    def test_legacy_profiles_preserved(self):
        for f, expected in self.LEGACY.items():
            with self.subTest(freq_mhz=f / 1e6):
                self.assertEqual(Constants.sweep_profile_for(f), expected)

    def test_8mhz_peaks_get_sensible_profiles(self):
        self.assertEqual(Constants.sweep_profile_for(7.998e6), (15000, 5000, 11, 0.01))
        self.assertEqual(Constants.sweep_profile_for(23.938e6), (15000, 5000, 11, 0.01))
        self.assertEqual(Constants.sweep_profile_for(39.873e6), (23000, 3000, 19, 0.01))

    def test_sg_window_is_odd(self):
        for _, _, _, sg, _ in Constants.sweep_profiles:
            self.assertEqual(sg % 2, 1)


class Switcher(unittest.TestCase):

    def test_names_follow_harmonic_ratio(self):
        sw = OvertoneSwitcher(np.array([7.998e6, 23.938e6, 39.873e6]))
        self.assertEqual([sw.to_freq_range(i)[0] for i in range(3)], ["F0", "F3", "F5"])

    def test_missing_overtone_does_not_shift_names(self):
        sw = OvertoneSwitcher(np.array([5.003e6, 24.986e6]))   # F3 rejected
        self.assertEqual(sw.to_freq_range(1)[0], "F5")

    def test_window_matches_profile(self):
        sw = OvertoneSwitcher(np.array([5.003e6, 14.994e6]))
        name, centre, start, stop, sg, spline = sw.to_freq_range(1)
        self.assertEqual((centre - start, stop - centre, sg, spline), (15000, 5000, 11, 0.01))


if __name__ == "__main__":
    unittest.main()
