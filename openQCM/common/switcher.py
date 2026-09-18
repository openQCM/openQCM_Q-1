"""
Overtone-to-sweep-window mapping.

`OvertoneSwitcher` takes the array of peak frequencies detected during
calibration (fundamental first) and, given an index into that array,
returns:
    (name, center_freq, start_freq, stop_freq,
     savitzky_golay_window, spline_smoothing_factor)

The window and smoothing come from `Constants.sweep_profile_for`, keyed on
the absolute resonance frequency, so no crystal type is involved. The
name is derived from the harmonic ratio to the fundamental ("F0" for the
fundamental, then "F3", "F5", ...), which stays correct even when the
calibration rejected an intermediate overtone.
"""
from openQCM.core.constants import Constants

TAG = "[Switcher]"


class OvertoneSwitcher:

    def __init__(self, peak_frequencies):
        self.peak_frequencies = peak_frequencies

    @staticmethod
    def harmonic_name(peak, fundamental):
        n = int(round(peak / fundamental))
        return "F0" if n == 1 else "F{}".format(n)

    def to_freq_range(self, index):
        peak = self.peak_frequencies[index]
        L, R, sg_window, spline_factor = Constants.sweep_profile_for(peak)
        return (self.harmonic_name(peak, self.peak_frequencies[0]),
                peak, peak - L, peak + R, sg_window, spline_factor)
