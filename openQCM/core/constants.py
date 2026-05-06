"""
openQCM Q-1 — application-wide constants and helper axis classes.

Constants are grouped by feature area:
    - Application & plot defaults
    - Per-overtone signal-processing parameters (5 MHz / 10 MHz sensors)
    - Serial / process / log / file paths
    - Peak detection (calibration) tuning
    - Auto-tracking and signal-quality thresholds
    - Buffer averaging (trimmed mean)

Custom pyqtgraph axis classes used by the live plots are defined at the
bottom of this module:
    - DateAxis           absolute timestamp → HH:MM:SS
    - ElapsedTimeAxis    relative time → HH:MM:SS / M:SS / SS
    - NonScientificAxis  integer ticks (no SI prefix)
    - OneDecimalAxis     one-decimal ticks (used for temperature)
"""
import os
import datetime
from enum import Enum
from time import strftime, localtime

import numpy as np
from pyqtgraph import AxisItem

from openQCM.common.resources import get_data_path


###############################################################################
# Acquisition mode (must match the order of `Constants.app_sources`)
###############################################################################
class SourceType(Enum):
    serial = 0          # Measurement
    calibration = 1     # Peak Detection
    SocketClient = 2    # reserved (unused)


###############################################################################
# Minimum supported Python version (checked at startup)
###############################################################################
class MinimalPython:
    major = 3
    minor = 2
    release = 0


###############################################################################
# Application-wide constants
###############################################################################
class Constants:
    # ---------- Application ----------
    app_title = "Real-Time openQCM GUI"
    app_version = '3.0'
    fw_version = "2.2"                                     # expected firmware version (must match firmware FW_VERSION)
    app_sources = ["Measurement", "Peak Detection"]        # indices match SourceType
    app_encoding = "utf-8"

    # ---------- Plot ----------
    plot_update_ms = 50                                    # GUI plot refresh interval
    plot_colors = ['#ff0000', '#0072bd', '#008EC0',
                   '#DD8E6B', '#7e2f8e', '#77ac30',
                   '#4dbeee', '#a2142f']

    # ---------- Sweep size ----------
    argument_default_samples = 501                         # samples per measurement sweep

    # ---------- Signal processing per overtone ----------
    # For each overtone:
    #   L*  = Hz to subtract from the peak to define sweep start
    #   R*  = Hz to add to the peak to define sweep stop
    #   SG_window_size* = Savitzky-Golay smoothing window (must be odd)
    #   Spline_factor*  = scipy UnivariateSpline smoothing factor (s parameter)
    SG_order = 3                                           # SG polynomial order (common to all overtones)

    # 5 MHz sensor — fundamental F0 ~5 MHz
    L5_fundamental = 15000
    R5_fundamental = 5000
    SG_window_size5_fundamental = 9
    Spline_factor5_fundamental = 0.05
    # 5 MHz sensor — 3rd overtone F3 ~15 MHz
    L5_3th_overtone = 15000
    R5_3th_overtone = 5000
    SG_window_size5_3th_overtone = 11
    Spline_factor5_3th_overtone = 0.01
    # 5 MHz sensor — 5th overtone F5 ~25 MHz
    L5_5th_overtone = 15000
    R5_5th_overtone = 5000
    SG_window_size5_5th_overtone = 11
    Spline_factor5_5th_overtone = 0.01
    # 5 MHz sensor — 7th overtone F7 ~35 MHz
    L5_7th_overtone = 50000
    R5_7th_overtone = 2500
    SG_window_size5_7th_overtone = 33
    Spline_factor5_7th_overtone = 0.01
    # 5 MHz sensor — 9th overtone F9 ~45 MHz
    # NOTE: parameters are placeholders pending hardware validation (see TODO.md)
    L5_9th_overtone = 5000000
    R5_9th_overtone = 100000
    SG_window_size5_9th_overtone = 5
    Spline_factor5_9th_overtone = 0.5

    # 10 MHz sensor — fundamental F0 ~10 MHz
    L10_fundamental = 15000
    R10_fundamental = 5000
    SG_window_size10_fundamental = 11
    Spline_factor10_fundamental = 0.01
    # 10 MHz sensor — 3rd overtone F3 ~30 MHz
    L10_3th_overtone = 15000
    R10_3th_overtone = 5000
    SG_window_size10_3th_overtone = 11
    Spline_factor10_3th_overtone = 0.01
    # 10 MHz sensor — 5th overtone F5 ~50 MHz
    L10_5th_overtone = 23000
    R10_5th_overtone = 3000
    SG_window_size10_5th_overtone = 19
    Spline_factor10_5th_overtone = 0.01

    # ---------- Serial port ----------
    serial_default_speed = 115200
    serial_default_overtone = None
    serial_default_QCS = "@10MHz"
    serial_writetimeout_ms = 0
    serial_timeout_ms = None

    # ---------- Multiprocessing ----------
    process_join_timeout_ms = 2000
    parser_timeout_ms = 0.005

    # ---------- Logging ----------
    log_export_path = get_data_path("logged_data")
    log_filename = "{}.log".format(app_title)
    log_max_bytes = 5120
    log_default_level = 1
    log_default_console_log = False

    # ---------- File paths ----------
    slash = os.sep                                         # platform path separator (kept for legacy callers)
    csv_delimiter = ","
    csv_default_prefix = "%Y-%m-%d_%H-%M-%S"               # log filename timestamp prefix → YYYY-MM-DD_hh-mm-ss
    csv_extension = "csv"
    txt_extension = "txt"
    csv_export_path = get_data_path("logged_data")         # measurement CSV logs
    csv_sweeps_filename = "sweep"                          # base name for raw sweep dumps (when enabled)

    # Calibration files: one per supported sensor type
    csv_calibration_export_path = get_data_path("openQCM")
    csv_calibration_filename3   = "Calibration_3MHz"
    csv_calibration_filename    = "Calibration_5MHz"
    csv_calibration_filename10  = "Calibration_10MHz"
    csv_calibration_path3  = os.path.join(csv_calibration_export_path,
                                          "{}.{}".format(csv_calibration_filename3, txt_extension))
    csv_calibration_path   = os.path.join(csv_calibration_export_path,
                                          "{}.{}".format(csv_calibration_filename,  txt_extension))
    csv_calibration_path10 = os.path.join(csv_calibration_export_path,
                                          "{}.{}".format(csv_calibration_filename10, txt_extension))

    # Detected fundamental + overtone frequencies, written by Peak Detection
    csv_peakfrequencies_filename = "PeakFrequencies"
    cvs_peakfrequencies_path = os.path.join(csv_calibration_export_path,
                                            "{}.{}".format(csv_peakfrequencies_filename, txt_extension))

    # ---------- Peak detection (calibration) ----------
    # Distance in samples between neighbouring peaks for the legacy FindPeak
    # algorithm. The two-phase algorithm (find fundamental, then find overtones)
    # uses peak_points_fundamental / peak_points_overtone instead.
    dist5  = 8000      # 5 MHz sensor
    dist10 = 10000     # 10 MHz sensor

    # Full-spectrum calibration scan: 1 MHz → 51 MHz, 1 kHz step
    calibration_default_samples = 50001
    calibration_frequency_start = 1000000
    calibration_frequency_stop  = 51000000
    calibration_fStep = (calibration_frequency_stop - calibration_frequency_start) / (calibration_default_samples - 1)
    calibration_readFREQ = np.arange(calibration_default_samples) * calibration_fStep + calibration_frequency_start

    # Calibration is acquired in `calib_sections` partial sweeps that are then
    # concatenated to cover the whole spectrum.
    calib_fStep = 1000
    calib_fRange = 5000000
    calib_samples = 5001
    calib_sections = 10

    # Two-phase peak detection — fundamental search
    peak_freq_sweep_min = 1000000        # 1 MHz lower bound
    peak_freq_sweep_max = 12000000       # 12 MHz upper bound
    peak_points_fundamental = 6000       # argrelextrema order: 6 MHz min spacing
    # Two-phase peak detection — overtone search
    peak_freq_range_half = 400000        # ±400 kHz window centred on the expected overtone
    peak_points_overtone = 100           # argrelextrema order: 100 kHz min spacing
    peak_overtone_multipliers = [3, 5, 7, 9]
    peak_max_frequency_limit = 51000000
    # Cross-validation between magnitude and phase peaks
    peak_phase_threshold = 10            # minimum phase peak (degrees) to accept an overtone
    # Frequency-difference threshold between magnitude and phase peaks:
    #   diff_threshold = (calib_fStep * peak_points_overtone) / peak_freq_diff_divisor
    # Currently 50 kHz (divisor=2). See TODO.md — needs more counter-examples to tune.
    peak_freq_diff_divisor = 2

    # ---------- Ring buffers (live measurement) ----------
    ring_buffer_samples = 16363          # max history kept in memory for plotting

    # ---------- Auto-tracking & signal-quality safety ----------
    # When the measured resonance frequency drifts more than this threshold
    # from the current reference, the sweep window is recentred automatically.
    auto_tracking_threshold = 100        # Hz
    # If both -3dB frequencies are missing for this many consecutive
    # sweeps, auto-tracking is disabled. It re-enables automatically as soon
    # as the peak returns with at least one -3dB frequency identifiable.
    auto_tracking_max_edge_errors = 10
    # Minimum Q-factor below which the resonance is considered invalid.
    # Used to detect "sensor disconnected" (board sends amplifier noise).
    # Real QCM resonances have Q ≫ 100; pure noise gives a tiny Q.
    min_valid_q_factor = 100

    # ---------- Buffer averaging (sent to GUI / auto-tracking) ----------
    # `environment` samples are accumulated in a circular buffer; once full,
    # frequency / dissipation / temperature are aggregated with a trimmed mean
    # to smooth noise and reject occasional outliers.
    environment = 50
    trim_mean_fraction = 0.10            # drop 10% lowest + 10% highest before averaging

    # ---------- Reserved (unused) ----------
    class SocketClient:
        timeout = 0.01
        host_default = "localhost"
        port_default = [5555, 8080, 9090]
        buffer_recv_size = 1024


###############################################################################
# Custom pyqtgraph axis classes
###############################################################################
class DateAxis(AxisItem):
    """Format a Unix timestamp (microseconds) as HH:MM:SS."""
    def __init__(self, *args, **kwargs):
        super(DateAxis, self).__init__(*args, **kwargs)

    def tickStrings(self, values, scale, spacing):
        TS_MULT_us = 1e6
        try:
            return [datetime.datetime.utcfromtimestamp(float(v) / TS_MULT_us).strftime("%H:%M:%S")
                    for v in values]
        except Exception:
            return ['' for _ in values]


class ElapsedTimeAxis(AxisItem):
    """
    Format elapsed time relative to a start reference as H:MM:SS / M:SS / SS.

    The start reference is set externally with `set_start_time(value)` from
    the first valid (non-NaN) sample of the data series. Use `reset_start_time()`
    when restarting the acquisition.
    """
    TS_MULT_us = 1e6

    def __init__(self, *args, **kwargs):
        super(ElapsedTimeAxis, self).__init__(*args, **kwargs)
        self._start_time = None

    def tickStrings(self, values, scale, spacing):
        try:
            if not values:
                return []
            if self._start_time is None:
                return [''] * len(values)

            result = []
            for v in values:
                t = (float(v) - float(self._start_time)) / self.TS_MULT_us
                if t < 0:
                    t = 0
                if t >= 3600:
                    h = int(t // 3600)
                    m = int((t % 3600) // 60)
                    s = int(t % 60)
                    result.append(f"{h}:{m:02d}:{s:02d}")
                elif t >= 60:
                    m = int(t // 60)
                    s = int(t % 60)
                    result.append(f"{m}:{s:02d}")
                else:
                    result.append(f"{int(t)}")
            return result
        except Exception:
            return [''] * len(values)

    def set_start_time(self, start_time):
        """Latch the start reference once, ignoring NaN/invalid values."""
        import math
        if self._start_time is None and start_time is not None:
            try:
                val = float(start_time)
                if not math.isnan(val):
                    self._start_time = val
            except (ValueError, TypeError):
                pass

    def reset_start_time(self):
        """Clear the start reference so the next sample latches a new one."""
        self._start_time = None


class NonScientificAxis(AxisItem):
    """Render tick labels as plain integers (no SI prefix, no scientific form)."""
    def __init__(self, *args, **kwargs):
        super(NonScientificAxis, self).__init__(*args, **kwargs)

    def tickStrings(self, values, scale, spacing):
        return [int(v) for v in values]


class OneDecimalAxis(AxisItem):
    """Render tick labels with exactly one decimal digit (used for temperature)."""
    def __init__(self, *args, **kwargs):
        super(OneDecimalAxis, self).__init__(*args, **kwargs)

    def tickStrings(self, values, scale, spacing):
        return [f"{v:.1f}" for v in values]
