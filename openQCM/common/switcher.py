"""
Overtone-to-sweep-window mapping for 5 MHz and 10 MHz QCM sensors.

Each switcher takes the array of peak frequencies detected during
calibration and, given an overtone index (0..N), returns a tuple with:
    (name, center_freq, start_freq, stop_freq,
     savitzky_golay_window, spline_smoothing_factor)

These values are consumed by SerialProcess to configure the per-overtone
sweep window and the per-overtone signal-processing parameters.
"""
from openQCM.core.constants import Constants

TAG = "[Switcher]"


class Overtone_Switcher_10MHz:
    """Sweep-window mapping for a 10 MHz QCM sensor (F0, F3, F5)."""

    def __init__(self, peak_frequencies=None):
        self.peak_frequencies = peak_frequencies

    def overtone10MHz_to_freq_range(self, argument):
        """Dispatch to the corresponding `overtone_<n>` method."""
        method = getattr(self, 'overtone_' + str(argument), lambda: None)
        return method()

    def overtone_0(self):
        # Fundamental ~10 MHz
        name = "F0"
        start = self.peak_frequencies[0] - Constants.L10_fundamental
        stop  = self.peak_frequencies[0] + Constants.R10_fundamental
        return (name, self.peak_frequencies[0], start, stop,
                Constants.SG_window_size10_fundamental,
                Constants.Spline_factor10_fundamental)

    def overtone_1(self):
        # 3rd overtone ~30 MHz
        name = "F3"
        start = self.peak_frequencies[1] - Constants.L10_3th_overtone
        stop  = self.peak_frequencies[1] + Constants.R10_3th_overtone
        return (name, self.peak_frequencies[1], start, stop,
                Constants.SG_window_size10_3th_overtone,
                Constants.Spline_factor10_3th_overtone)

    def overtone_2(self):
        # 5th overtone ~50 MHz
        name = "F5"
        start = self.peak_frequencies[2] - Constants.L10_5th_overtone
        stop  = self.peak_frequencies[2] + Constants.R10_5th_overtone
        return (name, self.peak_frequencies[2], start, stop,
                Constants.SG_window_size10_5th_overtone,
                Constants.Spline_factor10_5th_overtone)


class Overtone_Switcher_5MHz:
    """Sweep-window mapping for a 5 MHz QCM sensor (F0, F3, F5, F7, F9)."""

    def __init__(self, peak_frequencies=None):
        self.peak_frequencies = peak_frequencies

    def overtone5MHz_to_freq_range(self, argument):
        """Dispatch to the corresponding `overtone_<n>` method."""
        method = getattr(self, 'overtone_' + str(argument), lambda: None)
        return method()

    def overtone_0(self):
        # Fundamental ~5 MHz
        name = "F0"
        start = self.peak_frequencies[0] - Constants.L5_fundamental
        stop  = self.peak_frequencies[0] + Constants.R5_fundamental
        return (name, self.peak_frequencies[0], start, stop,
                Constants.SG_window_size5_fundamental,
                Constants.Spline_factor5_fundamental)

    def overtone_1(self):
        # 3rd overtone ~15 MHz
        name = "F3"
        start = self.peak_frequencies[1] - Constants.L5_3th_overtone
        stop  = self.peak_frequencies[1] + Constants.R5_3th_overtone
        return (name, self.peak_frequencies[1], start, stop,
                Constants.SG_window_size5_3th_overtone,
                Constants.Spline_factor5_3th_overtone)

    def overtone_2(self):
        # 5th overtone ~25 MHz
        name = "F5"
        start = self.peak_frequencies[2] - Constants.L5_5th_overtone
        stop  = self.peak_frequencies[2] + Constants.R5_5th_overtone
        return (name, self.peak_frequencies[2], start, stop,
                Constants.SG_window_size5_5th_overtone,
                Constants.Spline_factor5_5th_overtone)

    def overtone_3(self):
        # 7th overtone ~35 MHz
        name = "F7"
        start = self.peak_frequencies[3] - Constants.L5_7th_overtone
        stop  = self.peak_frequencies[3] + Constants.R5_7th_overtone
        return (name, self.peak_frequencies[3], start, stop,
                Constants.SG_window_size5_7th_overtone,
                Constants.Spline_factor5_7th_overtone)

    def overtone_4(self):
        # 9th overtone ~45 MHz
        # NOTE: parameters are placeholders pending validation on real hardware
        # (see TODO.md). Some L/R/SG values may not be optimal yet.
        name = "F9"
        start = self.peak_frequencies[4] - Constants.L5_9th_overtone
        stop  = self.peak_frequencies[4] + Constants.R5_9th_overtone
        return (name, self.peak_frequencies[4], start, stop,
                Constants.SG_window_size5_9th_overtone,
                Constants.Spline_factor5_9th_overtone)
