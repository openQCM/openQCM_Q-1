from PyQt5 import QtGui, QtCore, QtWidgets
import pyqtgraph as pg
import numpy as np

TAG = "[CalibrationPlot]"

# Project-wide colors aligned with the main GUI
COLOR_BASELINE = '#DD8E6B'      # brown — same as Dissipation in main GUI
COLOR_PHASE    = '#008EC0'      # blue  — same as Phase / Frequency in main GUI
PEAK_FILL      = (255, 0, 0, 220)
PEAK_BORDER    = 'w'            # white outline around the red peak markers
# Window (in Hz) used to search for the phase peak around each amplitude peak
PHASE_PEAK_HALF_WINDOW = 200_000


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
        self._plt_amp.setClipToView(True)
        self._plt_amp.setDownsampling(mode='peak')

        # Phase plot
        self._plt_phase = self._graphics.addPlot(row=1, col=0, title="Phase")
        self._plt_phase.setLabel('left', 'Phase', units='deg', color=fg_color)
        self._plt_phase.setLabel('bottom', 'Frequency', units='Hz', color=fg_color)
        self._plt_phase.showGrid(x=True, y=True, alpha=self._grid_alpha)
        self._plt_phase.addLegend(offset=(10, 10))
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

        # Disable pyqtgraph's default right-click menu and route right-clicks
        # through our custom context handler (Auto-scale / Reset Zoom / Pan /
        # Select Mode), matching the convention used by the main GUI plots.
        for p in (self._plt_amp, self._plt_phase):
            p.setMenuEnabled(False)
            p.getViewBox().setMenuEnabled(False)
        # Both plots share the same scene, so we connect the click signal
        # once and dispatch by hit-testing the mouse position.
        self._graphics.scene().sigMouseClicked.connect(self._on_scene_right_click)


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

    # ------------------------------------------------------------------
    # Custom right-click context menu (matches the main GUI plots)
    # ------------------------------------------------------------------
    def _on_scene_right_click(self, event):
        """Show the standard Auto-scale / Reset Zoom / Pan / Select menu."""
        if event.button() != QtCore.Qt.RightButton:
            return
        scene_pos = event.scenePos()
        plot = None
        for p in (self._plt_amp, self._plt_phase):
            if p.sceneBoundingRect().contains(scene_pos):
                plot = p
                break
        if plot is None:
            return

        menu = QtWidgets.QMenu()
        auto_scale_action = menu.addAction("Auto-scale")
        reset_zoom_action = menu.addAction("Reset Zoom")
        menu.addSeparator()
        pan_mode_action = menu.addAction("Pan Mode")
        select_mode_action = menu.addAction("Select Mode")

        pos = event.screenPos()
        qpos = QtCore.QPoint(int(pos.x()), int(pos.y()))
        action = menu.exec_(qpos)

        if action == auto_scale_action:
            plot.enableAutoRange()
        elif action == reset_zoom_action:
            plot.getViewBox().autoRange()
        elif action == pan_mode_action:
            plot.getViewBox().setMouseMode(pg.ViewBox.PanMode)
        elif action == select_mode_action:
            plot.getViewBox().setMouseMode(pg.ViewBox.RectMode)
        event.accept()


    # ------------------------------------------------------------------
    # Main entry point — load files and render the diagnostic plots
    # ------------------------------------------------------------------
    def show_results(self, calib_file_path, peaks_file_path):
        """
        Load calibration data and peak frequencies, compute baseline correction,
        and display diagnostic plots.

        :param calib_file_path: path to Calibration_XMHz.txt (3 cols: freq, mag, phase)
        :param peaks_file_path: path to PeakFrequencies.txt (2 cols: freq, freq)
        """
        try:
            # Load calibration raw data
            calib_data = np.loadtxt(calib_file_path)
            freq = calib_data[:, 0]
            raw_mag = calib_data[:, 1]
            raw_phase = calib_data[:, 2]
            print(TAG, "Loaded calibration data from: {}".format(calib_file_path))

            # Load peak frequencies (atleast_2d handles single-peak case)
            peak_data = np.atleast_2d(np.loadtxt(peaks_file_path))
            peak_freqs = peak_data[:, 0]
            print(TAG, "Loaded {} peak frequencies from: {}".format(
                len(peak_freqs), peaks_file_path))

            # Baseline correction (8th-order polynomial — same as Calibration.py)
            coeffs_mag = np.polyfit(freq, raw_mag, 8)
            baseline_mag = np.polyval(coeffs_mag, freq)
            corrected_mag = raw_mag - baseline_mag

            coeffs_phase = np.polyfit(freq, raw_phase, 8)
            baseline_phase = np.polyval(coeffs_phase, freq)
            corrected_phase = raw_phase - baseline_phase

            # Sample mag / phase at each amplitude-peak frequency
            peak_mag_values = np.zeros(len(peak_freqs))
            peak_phase_at_amp = np.zeros(len(peak_freqs))
            for i, pf in enumerate(peak_freqs):
                if pf > 0:
                    idx = np.abs(freq - pf).argmin()
                    peak_mag_values[i] = corrected_mag[idx]
                    peak_phase_at_amp[i] = corrected_phase[idx]

            # Filter out empty (zero) peak slots
            valid_mask = peak_freqs > 0
            valid_peak_freqs = peak_freqs[valid_mask]
            valid_peak_mag = peak_mag_values[valid_mask]
            valid_peak_phase_at_amp = peak_phase_at_amp[valid_mask]
            valid_indices = [i for i, m in enumerate(valid_mask) if m]

            # Phase peak: the maximum of the corrected phase signal in a
            # ±PHASE_PEAK_HALF_WINDOW (Hz) window around each amplitude peak.
            phase_peak_freqs = np.zeros(len(valid_peak_freqs))
            phase_peak_values = np.zeros(len(valid_peak_freqs))
            for i, amp_pf in enumerate(valid_peak_freqs):
                window = (freq >= amp_pf - PHASE_PEAK_HALF_WINDOW) & \
                         (freq <= amp_pf + PHASE_PEAK_HALF_WINDOW)
                if np.any(window):
                    sub_freq = freq[window]
                    sub_phase = corrected_phase[window]
                    j = int(np.argmax(sub_phase))
                    phase_peak_freqs[i] = sub_freq[j]
                    phase_peak_values[i] = sub_phase[j]

            # Title
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

            # Theme-dependent colors
            if self._theme == 'dark':
                amp_color = (255, 255, 255)     # white  (matches main GUI Amplitude in dark)
                label_color = '#ffffff'         # white  (peak labels — high contrast on dark bg)
            else:
                amp_color = (0, 0, 0)           # black  (matches main GUI Amplitude in light)
                label_color = '#000000'         # black  (visible on light bg)
            phase_color = pg.mkColor(COLOR_PHASE).getRgb()[:3]
            baseline_pen = pg.mkPen(color=COLOR_BASELINE, width=1,
                                    style=QtCore.Qt.DashLine)
            peak_brush = pg.mkBrush(*PEAK_FILL)
            peak_pen = pg.mkPen(PEAK_BORDER, width=2)

            # ---------------------- AMPLITUDE PLOT ----------------------
            # Raw signal: scatter (small dots), same color as Corrected
            self._plt_amp.addItem(pg.ScatterPlotItem(
                x=freq, y=raw_mag,
                symbol='o', size=2,
                brush=pg.mkBrush(*amp_color, 200),
                pen=pg.mkPen(None),
                name='Raw signal'))
            # Baseline (brown dashed line)
            self._plt_amp.plot(freq, baseline_mag, pen=baseline_pen,
                               name='Baseline (poly 8)', skipFiniteCheck=True)
            # Corrected (solid line, theme color — white in dark / black in light)
            self._plt_amp.plot(freq, corrected_mag,
                               pen=pg.mkPen(color=amp_color, width=2),
                               name='Corrected', skipFiniteCheck=True)
            # Amplitude peak markers (red dot, white border)
            self._plt_amp.addItem(pg.ScatterPlotItem(
                x=valid_peak_freqs, y=valid_peak_mag,
                symbol='o', size=12,
                brush=peak_brush, pen=peak_pen,
                name='Amplitude peak'))
            # Peak labels (white in dark / black in light)
            for vi, (pf, pv) in zip(valid_indices,
                                    zip(valid_peak_freqs, valid_peak_mag)):
                n = self.OVERTONE_LABELS[vi] if vi < len(self.OVERTONE_LABELS) else '?'
                text = pg.TextItem(text="F{}: {:.0f} Hz".format(n, pf),
                                   color=label_color, anchor=(0.5, 1.2))
                text.setPos(pf, pv)
                self._plt_amp.addItem(text)

            # ---------------------- PHASE PLOT ----------------------
            # Raw signal: blue scatter dots
            self._plt_phase.addItem(pg.ScatterPlotItem(
                x=freq, y=raw_phase,
                symbol='o', size=2,
                brush=pg.mkBrush(*phase_color, 200),
                pen=pg.mkPen(None),
                name='Raw signal'))
            # Baseline (brown dashed)
            self._plt_phase.plot(freq, baseline_phase, pen=baseline_pen,
                                 name='Baseline (poly 8)', skipFiniteCheck=True)
            # Corrected (blue solid line)
            self._plt_phase.plot(freq, corrected_phase,
                                 pen=pg.mkPen(color=COLOR_PHASE, width=2),
                                 name='Corrected', skipFiniteCheck=True)
            # Reference marker on phase plot at AMPLITUDE peak position (circle)
            self._plt_phase.addItem(pg.ScatterPlotItem(
                x=valid_peak_freqs, y=valid_peak_phase_at_amp,
                symbol='o', size=12,
                brush=peak_brush, pen=peak_pen,
                name='Amplitude peak (ref)'))
            # Phase peak marker (star) at the actual phase maximum
            self._plt_phase.addItem(pg.ScatterPlotItem(
                x=phase_peak_freqs, y=phase_peak_values,
                symbol='star', size=18,
                brush=peak_brush, pen=peak_pen,
                name='Phase peak'))
            # Phase peak labels — frequency of the PHASE peak (for amp-vs-phase comparison)
            for vi, (pf, pv) in zip(valid_indices,
                                    zip(phase_peak_freqs, phase_peak_values)):
                n = self.OVERTONE_LABELS[vi] if vi < len(self.OVERTONE_LABELS) else '?'
                text = pg.TextItem(text="F{}: {:.0f} Hz".format(n, pf),
                                   color=label_color, anchor=(0.5, 1.2))
                text.setPos(pf, pv)
                self._plt_phase.addItem(text)

            print(TAG, "Diagnostic plots rendered successfully")

        except Exception as e:
            print(TAG, "ERROR: Could not render diagnostic plots: {}".format(e))
            import traceback
            traceback.print_exc()
