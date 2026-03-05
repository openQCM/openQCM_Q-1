from PyQt5 import QtGui, QtCore, QtWidgets
import pyqtgraph as pg
import numpy as np

TAG = "[CalibrationPlot]"

###############################################################################
# Diagnostic plot window for Peak Detection results
# Shows amplitude and phase with baseline correction and detected peaks
###############################################################################
class CalibrationPlotWindow(QtGui.QDialog):

    # QCM overtone multipliers: fundamental=1, then odd harmonics
    OVERTONE_LABELS = [1, 3, 5, 7, 9]

    def __init__(self, parent=None, theme='dark'):
        super(CalibrationPlotWindow, self).__init__(parent)
        self.setWindowTitle("Peak Detection Diagnostic")
        self.resize(1000, 700)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, False)

        self._theme = theme
        self._apply_theme_style()

        # Layout
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # Title label
        self._title_label = QtWidgets.QLabel("Peak Detection Diagnostic")
        self._title_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self._title_label)

        # Graphics layout for plots
        self._graphics = pg.GraphicsLayoutWidget()
        layout.addWidget(self._graphics)

        # Apply theme colors
        bg_color, fg_color, self._grid_alpha = self._get_theme_colors()
        self._graphics.setBackground(bg_color)
        self._fg_color = fg_color

        # Amplitude plot
        self._plt_amp = self._graphics.addPlot(row=0, col=0, title="Amplitude (Magnitude)")
        self._plt_amp.setLabel('left', 'Amplitude', units='dB', color=fg_color)
        self._plt_amp.setLabel('bottom', 'Frequency', units='Hz', color=fg_color)
        self._plt_amp.showGrid(x=True, y=True, alpha=self._grid_alpha)
        self._plt_amp.addLegend(offset=(10, 10))
        # Performance: clip data to visible range
        self._plt_amp.setClipToView(True)
        self._plt_amp.setDownsampling(mode='peak')

        # Phase plot
        self._plt_phase = self._graphics.addPlot(row=1, col=0, title="Phase")
        self._plt_phase.setLabel('left', 'Phase', units='deg', color=fg_color)
        self._plt_phase.setLabel('bottom', 'Frequency', units='Hz', color=fg_color)
        self._plt_phase.showGrid(x=True, y=True, alpha=self._grid_alpha)
        self._plt_phase.addLegend(offset=(10, 10))
        # Performance: clip data to visible range
        self._plt_phase.setClipToView(True)
        self._plt_phase.setDownsampling(mode='peak')

        # Link x-axes
        self._plt_phase.setXLink(self._plt_amp)

        # Style axes
        for plt in [self._plt_amp, self._plt_phase]:
            for axis_name in ['left', 'bottom', 'top', 'right']:
                axis = plt.getAxis(axis_name)
                axis.setPen(pg.mkPen(color=fg_color, width=1))
                axis.setTextPen(pg.mkPen(color=fg_color))
            plt.titleLabel.item.setDefaultTextColor(pg.mkColor(fg_color))


    def _get_theme_colors(self):
        """Returns (bg_color, fg_color, grid_alpha) based on current theme."""
        if self._theme == 'dark':
            return '#2b2b2b', '#ffffff', 0.3
        else:
            return '#f0f0f0', '#000000', 0.2

    def _apply_theme_style(self):
        """Apply stylesheet based on theme."""
        if self._theme == 'dark':
            self.setStyleSheet("background-color: #2b2b2b; color: #ffffff;")
        else:
            self.setStyleSheet("background-color: #f0f0f0; color: #000000;")


    def show_results(self, calib_file_path, peaks_file_path):
        """
        Load calibration data and peak frequencies, compute baseline correction,
        and display diagnostic plots.

        :param calib_file_path: Path to Calibration_XMHz.txt (3 columns: freq, mag, phase)
        :param peaks_file_path: Path to PeakFrequencies.txt (2 columns: freq, freq)
        """
        try:
            # Load calibration raw data
            calib_data = np.loadtxt(calib_file_path)
            freq = calib_data[:, 0]
            raw_mag = calib_data[:, 1]
            raw_phase = calib_data[:, 2]
            print(TAG, "Loaded calibration data from: {}".format(calib_file_path))

            # Load peak frequencies
            peak_data = np.loadtxt(peaks_file_path)
            peak_freqs = peak_data[:, 0]
            print(TAG, "Loaded {} peak frequencies from: {}".format(len(peak_freqs), peaks_file_path))

            # Compute baseline correction (polynomial order 8, same as Calibration.baseline_estimation)
            coeffs_mag = np.polyfit(freq, raw_mag, 8)
            baseline_mag = np.polyval(coeffs_mag, freq)
            corrected_mag = raw_mag - baseline_mag

            coeffs_phase = np.polyfit(freq, raw_phase, 8)
            baseline_phase = np.polyval(coeffs_phase, freq)
            corrected_phase = raw_phase - baseline_phase

            # Find amplitude and phase values at peak frequencies
            peak_mag_values = np.zeros(len(peak_freqs))
            peak_phase_values = np.zeros(len(peak_freqs))
            for i, pf in enumerate(peak_freqs):
                if pf > 0:
                    idx = np.abs(freq - pf).argmin()
                    peak_mag_values[i] = corrected_mag[idx]
                    peak_phase_values[i] = corrected_phase[idx]

            # Filter out peaks with frequency == 0
            valid_mask = peak_freqs > 0
            valid_peak_freqs = peak_freqs[valid_mask]
            valid_peak_mag = peak_mag_values[valid_mask]
            valid_peak_phase = peak_phase_values[valid_mask]

            # Build valid overtone indices (matching the valid_mask)
            all_indices = list(range(len(peak_freqs)))
            valid_indices = [idx for idx, m in zip(all_indices, valid_mask) if m]

            # Update title
            if len(valid_peak_freqs) > 0:
                fund_freq = valid_peak_freqs[0]
                if 4e6 < fund_freq < 6e6:
                    qcm_type = "5 MHz QCM"
                elif 9e6 < fund_freq < 11e6:
                    qcm_type = "10 MHz QCM"
                else:
                    qcm_type = "Unknown"
                self._title_label.setText(
                    "Peak Detection Diagnostic -- {} -- {} peaks detected".format(
                        qcm_type, len(valid_peak_freqs)))

            # Theme-aware colors for raw signal
            if self._theme == 'dark':
                raw_color = (150, 150, 150)
            else:
                raw_color = (160, 160, 160)

            # ---- AMPLITUDE PLOT ----
            # Raw signal (gray, thin) — performance: skipFiniteCheck
            self._plt_amp.plot(freq, raw_mag,
                               pen=pg.mkPen(color=raw_color, width=1),
                               name='Raw signal', skipFiniteCheck=True)
            # Baseline fit (orange, dashed)
            self._plt_amp.plot(freq, baseline_mag,
                               pen=pg.mkPen(color=(255, 165, 0), width=1,
                                            style=QtCore.Qt.DashLine),
                               name='Baseline (poly 8)', skipFiniteCheck=True)
            # Baseline-corrected (red, bold)
            self._plt_amp.plot(freq, corrected_mag,
                               pen=pg.mkPen(color='#ff0000', width=2),
                               name='Corrected', skipFiniteCheck=True)
            # Peak markers (green circles)
            scatter_amp = pg.ScatterPlotItem(
                x=valid_peak_freqs, y=valid_peak_mag,
                symbol='o', size=12,
                brush=pg.mkBrush(0, 255, 100, 200),
                pen=pg.mkPen('w', width=1),
                name='Peaks')
            self._plt_amp.addItem(scatter_amp)

            # Add text labels for each peak: F1, F3, F5, F7, F9
            for vi, (pf, pv) in zip(valid_indices, zip(valid_peak_freqs, valid_peak_mag)):
                n = self.OVERTONE_LABELS[vi] if vi < len(self.OVERTONE_LABELS) else '?'
                label = "F{}: {:.0f} Hz".format(n, pf)
                text = pg.TextItem(text=label, color='#00ff64', anchor=(0.5, 1.2))
                text.setPos(pf, pv)
                self._plt_amp.addItem(text)

            # ---- PHASE PLOT ----
            # Raw signal (gray, thin)
            self._plt_phase.plot(freq, raw_phase,
                                 pen=pg.mkPen(color=raw_color, width=1),
                                 name='Raw signal', skipFiniteCheck=True)
            # Baseline fit (orange, dashed)
            self._plt_phase.plot(freq, baseline_phase,
                                 pen=pg.mkPen(color=(255, 165, 0), width=1,
                                              style=QtCore.Qt.DashLine),
                                 name='Baseline (poly 8)', skipFiniteCheck=True)
            # Baseline-corrected (blue, bold)
            self._plt_phase.plot(freq, corrected_phase,
                                 pen=pg.mkPen(color='#0072bd', width=2),
                                 name='Corrected', skipFiniteCheck=True)
            # Peak markers (green circles)
            scatter_phase = pg.ScatterPlotItem(
                x=valid_peak_freqs, y=valid_peak_phase,
                symbol='o', size=12,
                brush=pg.mkBrush(0, 255, 100, 200),
                pen=pg.mkPen('w', width=1),
                name='Peaks')
            self._plt_phase.addItem(scatter_phase)

            # Add text labels for each peak: F1, F3, F5, F7, F9
            for vi, (pf, pv) in zip(valid_indices, zip(valid_peak_freqs, valid_peak_phase)):
                n = self.OVERTONE_LABELS[vi] if vi < len(self.OVERTONE_LABELS) else '?'
                label = "F{}: {:.0f} Hz".format(n, pf)
                text = pg.TextItem(text=label, color='#00ff64', anchor=(0.5, 1.2))
                text.setPos(pf, pv)
                self._plt_phase.addItem(text)

            print(TAG, "Diagnostic plots rendered successfully")

        except Exception as e:
            print(TAG, "ERROR: Could not render diagnostic plots: {}".format(e))
            import traceback
            traceback.print_exc()
