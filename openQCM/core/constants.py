"""
openQCM Q-1 — application-wide constants and helper axis classes.

Constants are grouped by feature area:
    - Application & plot defaults
    - Per-overtone signal-processing parameters (by resonance frequency)
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
    # The sweep window and smoothing used in Measurement mode depend on the
    # *absolute frequency* of the resonance being tracked, not on the crystal
    # type: higher overtones have lower Q, broader and more asymmetric peaks,
    # and need wider windows and stronger smoothing. One table therefore
    # serves 5, 8, 10 MHz crystals alike. Each row is
    #     (upper bound Hz, L, R, SG window, spline factor)
    #   L / R          = Hz subtracted from / added to the peak -> sweep start / stop
    #   SG window      = Savitzky-Golay smoothing window (must be odd)
    #   spline factor  = scipy UnivariateSpline smoothing factor (s parameter)
    # The values are the empirically tuned ones formerly stored per crystal
    # (L5_*, L10_*, ...); every 5 / 10 MHz resonance maps to exactly the
    # profile it had before.
    SG_order = 3                                           # SG polynomial order (common to all)

    sweep_profiles = [
        # ~5 MHz fundamentals
        (7.5e6,   15000,  5000,  9, 0.05),
        # 8-30 MHz: fundamentals of 8/10 MHz crystals, F3/F5 of 5 MHz, F3 of 8/10 MHz
        (32.5e6,  15000,  5000, 11, 0.01),
        # ~35 MHz: F7 of 5 MHz
        (37.5e6,  50000,  2500, 33, 0.01),
        # ~40 MHz: F5 of 8 MHz — borrows the 50 MHz profile, still to be
        # validated on real hardware (no 8 MHz crystal in house)
        (42.5e6,  23000,  3000, 19, 0.01),
        # ~45 MHz: F9 of 5 MHz — placeholder pending validation (see TODO.md)
        (47.5e6, 5000000, 100000, 5, 0.5),
        # ~50 MHz: F5 of 10 MHz
        (51.0e6,  23000,  3000, 19, 0.01),
    ]

    @classmethod
    def sweep_profile_for(cls, frequency):
        """(L, R, SG window, spline factor) for a resonance at `frequency` Hz."""
        for upper, L, R, sg, spline in cls.sweep_profiles:
            if frequency < upper:
                return L, R, sg, spline
        return cls.sweep_profiles[-1][1:]

    # ---------- Serial port ----------
    serial_default_speed = 115200
    serial_default_overtone = None
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

    # Calibration sweep files. Peak Detection names them from the measured
    # fundamental (see calibration_filename_for below); the two legacy names
    # are kept because they are the factory-default files shipped in the
    # release bundle (tools/package_release.py) and committed in openQCM/.
    csv_calibration_export_path = get_data_path("openQCM")
    csv_calibration_filename    = "Calibration_5MHz"
    csv_calibration_filename10  = "Calibration_10MHz"
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
    # fallback. The two-phase algorithm (find fundamental, then find overtones)
    # uses peak_points_fundamental / peak_points_overtone instead.
    legacy_findpeak_distance = 8000

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
    # Half-width of the window, centred on the magnitude peak, inside which
    # the phase maximum is searched:
    #   phase_window_half = (calib_fStep * peak_points_overtone) / peak_freq_diff_divisor
    # Currently 50 kHz (divisor=2). Searching the phase *inside* this window
    # (instead of taking the global phase maximum of the +-400 kHz overtone
    # window) keeps a stronger spurious phase peak nearby from masking the
    # resonance — seen on F3 of tools/Calibration_8MHz.txt, where a 50.3 deg
    # spur at +96 kHz beat the 49.0 deg true peak and got F3 rejected.
    peak_freq_diff_divisor = 2

    # Generic quartz support — the *measured* fundamental drives the search,
    # there is no predefined crystal type. Any fundamental inside
    # [peak_freq_sweep_min, peak_freq_sweep_max] is accepted provided at least
    # this many overtones are confirmed by phase: a spurious peak has no
    # harmonic series, a real resonator does.
    peak_min_confirmed_overtones = 1

    @staticmethod
    def quartz_nominal_mhz(freq_fundamental):
        """Nominal crystal frequency in MHz (7.998 MHz -> 8), for labels and file names."""
        return int(round(freq_fundamental / 1e6))

    @classmethod
    def quartz_label(cls, freq_fundamental):
        return "{} MHz QCM".format(cls.quartz_nominal_mhz(freq_fundamental))

    @classmethod
    def calibration_filename_for(cls, freq_fundamental):
        """
        `Calibration_<N>MHz` derived from the fundamental. For 5 and 10 MHz
        crystals this yields the same names as the legacy constants above,
        so existing installations keep working unchanged.
        """
        return "Calibration_{}MHz".format(cls.quartz_nominal_mhz(freq_fundamental))

    @classmethod
    def calibration_path_for(cls, freq_fundamental):
        return os.path.join(cls.csv_calibration_export_path,
                            "{}.{}".format(cls.calibration_filename_for(freq_fundamental),
                                           cls.txt_extension))

    # ---------- Ring buffers (live measurement) ----------
    ring_buffer_samples = 16363          # max history kept in memory for plotting

    # ---------- Auto-tracking & signal-quality safety ----------
    # When the measured resonance frequency drifts more than this threshold
    # from the current reference, the sweep window is recentred automatically.
    auto_tracking_threshold = 100        # Hz
    # Hysteresis on the tracking-safety state machine:
    # - if both -3dB frequencies are missing for `auto_tracking_max_edge_errors`
    #   consecutive sweeps, auto-tracking is disabled;
    # - it re-enables automatically only after `auto_tracking_consecutive_good_to_resume`
    #   consecutive sweeps where the peak is back AND has at least one identifiable
    #   -3dB frequency. The sustained-recovery requirement avoids flapping caused
    #   by lucky single sweeps in the noise of a still-disconnected sensor.
    auto_tracking_max_edge_errors = 10
    auto_tracking_consecutive_good_to_resume = 5
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
