
from PyQt5 import QtCore, QtGui, QtWidgets
from pyqtgraph import GraphicsLayoutWidget
from openQCM.common.resources import get_resource_path
import webbrowser


###############################################################################################################
# UNIFIED MAIN WINDOW UI - Dark/Light Theme Scientific Interface
# Restructured: Minimal left sidebar, no right sidebar, bottom status dock, horizontal splitter
###############################################################################################################

# Dark theme colors
DARK_BG = "#2b2b2b"
DARK_PANEL = "#3c3c3c"
DARK_BORDER = "#555555"
DARK_TEXT = "#e0e0e0"
DARK_TEXT_SECONDARY = "#a0a0a0"

# Light theme colors
LIGHT_BG = "#f5f5f5"
LIGHT_PANEL = "#ffffff"
LIGHT_BORDER = "#cccccc"
LIGHT_TEXT = "#333333"
LIGHT_TEXT_SECONDARY = "#666666"

# Accent colors (shared between themes)
ACCENT_CYAN = "#00bcd4"
ACCENT_ORANGE = "#ff9800"
ACCENT_GREEN = "#4caf50"
ACCENT_RED = "#f44336"


###############################################################################################################
# Device Information Dialog - Non-modal popup window
###############################################################################################################
class DeviceInfoDialog(QtWidgets.QDialog):
    """Non-modal dialog showing device information that updates in real-time."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Device Information")
        self.setMinimumSize(280, 320)
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.Tool)  # Tool window style

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        # Create info rows
        self.info1a = self._create_row("Setup", "---")
        layout.addWidget(self.info1a)

        self.info11 = self._create_row("Mode", "---")
        layout.addWidget(self.info11)

        self.info2 = self._create_row("Overtone", "---")
        layout.addWidget(self.info2)

        self.info6 = self._create_row("Freq. Value", "---")
        layout.addWidget(self.info6)

        self.info3 = self._create_row("Start Freq.", "---")
        layout.addWidget(self.info3)

        self.info4 = self._create_row("Stop Freq.", "---")
        layout.addWidget(self.info4)

        self.info4a = self._create_row("Range", "---")
        layout.addWidget(self.info4a)

        self.info5 = self._create_row("Freq. Step", "---")
        layout.addWidget(self.info5)

        self.info7 = self._create_row("Samples", "---")
        layout.addWidget(self.info7)

        layout.addStretch()

    def _create_row(self, label_text, value_text):
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(widget)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(12)

        label = QtWidgets.QLabel(label_text + ":")
        label.setMinimumWidth(80)
        layout.addWidget(label)

        value = QtWidgets.QLabel(value_text)
        value.setObjectName("dataValue")
        value.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        layout.addWidget(value, stretch=1)

        widget.valueLabel = value
        return widget


###############################################################################################################
# Data Viewer Dialog - Non-modal window for viewing logged CSV data
###############################################################################################################
class DataViewerDialog(QtWidgets.QDialog):
    """Non-modal dialog for viewing logged CSV data with Frequency and Dissipation plots."""

    def __init__(self, parent=None, csv_path=None, theme='dark'):
        super().__init__(parent)
        import os
        self._csv_path = csv_path
        self._theme = theme
        self.setWindowTitle("Data View - {}".format(os.path.basename(csv_path) if csv_path else ""))
        self.setMinimumSize(900, 600)
        self.resize(1000, 700)
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.Window)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)

        # Colors based on theme
        if theme == 'dark':
            bg_color = DARK_BG
            text_color = '#ffffff'
            axis_color = '#aaaaaa'
            grid_color = (80, 80, 80)
        else:
            bg_color = LIGHT_BG
            text_color = '#333333'
            axis_color = '#666666'
            grid_color = (200, 200, 200)

        # Main layout
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # Info label
        self._info_label = QtWidgets.QLabel("")
        self._info_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self._info_label)

        # PyQtGraph plot widget
        import pyqtgraph as pg
        self._plot_widget = pg.GraphicsLayoutWidget()
        self._plot_widget.setBackground(bg_color)
        layout.addWidget(self._plot_widget, stretch=1)

        # Plot 1: Resonance Frequency
        self._plt_freq = self._plot_widget.addPlot(row=0, col=0)
        self._plt_freq.setLabel('left', 'Resonance Frequency', units='Hz', color=text_color)
        self._plt_freq.setLabel('bottom', 'Relative Time', units='s', color=text_color)
        self._plt_freq.showGrid(x=True, y=True, alpha=0.3)
        self._plt_freq.getAxis('left').setPen(axis_color)
        self._plt_freq.getAxis('left').setTextPen(axis_color)
        self._plt_freq.getAxis('bottom').setPen(axis_color)
        self._plt_freq.getAxis('bottom').setTextPen(axis_color)
        legend_freq = self._plt_freq.addLegend(offset=(10, 10))
        legend_freq.setBrush(pg.mkBrush('#3c3c3c80' if theme == 'dark' else '#ffffff80'))
        legend_freq.setPen(pg.mkPen('#555555' if theme == 'dark' else '#cccccc'))

        # Plot 2: Dissipation
        self._plt_diss = self._plot_widget.addPlot(row=1, col=0)
        self._plt_diss.setLabel('left', 'Dissipation', color=text_color)
        self._plt_diss.setLabel('bottom', 'Relative Time', units='s', color=text_color)
        self._plt_diss.showGrid(x=True, y=True, alpha=0.3)
        self._plt_diss.getAxis('left').setPen(axis_color)
        self._plt_diss.getAxis('left').setTextPen(axis_color)
        self._plt_diss.getAxis('bottom').setPen(axis_color)
        self._plt_diss.getAxis('bottom').setTextPen(axis_color)
        legend_diss = self._plt_diss.addLegend(offset=(10, 10))
        legend_diss.setBrush(pg.mkBrush('#3c3c3c80' if theme == 'dark' else '#ffffff80'))
        legend_diss.setPen(pg.mkPen('#555555' if theme == 'dark' else '#cccccc'))

        # Link X axes
        self._plt_diss.setXLink(self._plt_freq)

        # Load and plot data
        if csv_path:
            self._load_and_plot(csv_path)

    def _load_and_plot(self, csv_path):
        """Load CSV file and plot Frequency and Dissipation vs Relative Time."""
        import pyqtgraph as pg
        import numpy as np
        try:
            # Read CSV (skip header row)
            # Columns: Date, Time, Relative_time, Temperature, Resonance_Frequency, Dissipation
            data = []
            import csv
            with open(csv_path, 'r') as f:
                reader = csv.reader(f)
                header = next(reader)  # skip header
                for row in reader:
                    try:
                        rel_time = float(row[2])
                        freq = float(row[4])
                        diss = float(row[5])
                        data.append((rel_time, freq, diss))
                    except (ValueError, IndexError):
                        continue

            if not data:
                self._info_label.setText("No valid data found in file.")
                return

            data = np.array(data)
            t = data[:, 0]
            freq = data[:, 1]
            diss = data[:, 2]

            # Info label
            duration_s = t[-1] - t[0]
            duration_min = duration_s / 60.0
            self._info_label.setText("{} data points | Duration: {:.1f} min ({:.0f} s)".format(
                len(t), duration_min, duration_s))

            # Plot Frequency
            self._plt_freq.plot(t, freq, pen=pg.mkPen('#ff0000', width=1), name='Resonance Frequency')

            # Plot Dissipation
            self._plt_diss.plot(t, diss, pen=pg.mkPen('#0072bd', width=1), name='Dissipation')

        except Exception as e:
            self._info_label.setText("Error loading file: {}".format(str(e)))


###############################################################################################################
# Raw Data Viewer Dialog - Non-modal window showing LIVE amplitude and phase sweep curves
###############################################################################################################
class RawDataViewDialog(QtWidgets.QDialog):
    """
    Non-modal dialog showing LIVE amplitude and phase sweep curves.
    Reads data from worker buffers and computes spline/peak/bandwidth locally.
    Zero overhead on the acquisition pipeline when the dialog is closed.
    """

    def __init__(self, parent=None, main_window=None, theme='dark'):
        super().__init__(parent)
        import pyqtgraph as pg

        self._main_window = main_window
        self._theme = theme
        self.setWindowTitle("Raw Data View - Live Sweep")
        self.setMinimumSize(900, 650)
        self.resize(1050, 750)
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.Window)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)

        # Theme colors
        if theme == 'dark':
            bg_color = DARK_BG
            text_color = '#ffffff'
            axis_color = '#aaaaaa'
        else:
            bg_color = LIGHT_BG
            text_color = '#333333'
            axis_color = '#666666'

        # Main layout
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # Info label (shows overtone, peak freq, bandwidth, Q-factor, dissipation)
        self._info_label = QtWidgets.QLabel("Waiting for data...")
        self._info_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self._info_label)

        # PyQtGraph plot widget with two rows
        self._plot_widget = pg.GraphicsLayoutWidget()
        self._plot_widget.setBackground(bg_color)
        layout.addWidget(self._plot_widget, stretch=1)

        # --- Plot 1: Amplitude ---
        self._plt_amp = self._plot_widget.addPlot(row=0, col=0)
        self._plt_amp.setLabel('left', 'Amplitude', units='dB', color=text_color)
        self._plt_amp.setLabel('bottom', 'Frequency', units='Hz', color=text_color)
        self._plt_amp.showGrid(x=True, y=True, alpha=0.3)
        self._plt_amp.setTitle("Amplitude Sweep", color=text_color)
        for ax_name in ['left', 'bottom']:
            self._plt_amp.getAxis(ax_name).setPen(axis_color)
            self._plt_amp.getAxis(ax_name).setTextPen(axis_color)
        legend_amp = self._plt_amp.addLegend(offset=(10, 10))
        legend_amp.setBrush(pg.mkBrush('#3c3c3c80' if theme == 'dark' else '#f0f0f0e0'))
        legend_amp.setPen(pg.mkPen('#555555' if theme == 'dark' else '#cccccc'))

        # Layer 1: Raw data scatter (SG-filtered data from queue1)
        self._curve_raw = pg.ScatterPlotItem(
            size=3, pen=None,
            brush=pg.mkBrush('#00bcd4' if theme == 'dark' else '#0288d1'),
            name='SG-Filtered Data'
        )
        self._plt_amp.addItem(self._curve_raw)

        # Layer 2: Spline fit line
        self._curve_spline = self._plt_amp.plot(
            pen=pg.mkPen('#ff9800' if theme == 'dark' else '#e65100', width=2),
            name='Spline Fit'
        )

        # Layer 3: Peak maximum marker (red diamond)
        self._peak_marker = pg.ScatterPlotItem(
            size=12, pen=pg.mkPen('#ffffff', width=1.5),
            brush=pg.mkBrush('#f44336'),
            symbol='d',
            name='Peak'
        )
        self._plt_amp.addItem(self._peak_marker)

        # Layer 4: -3dB bandwidth region (semi-transparent green)
        self._bw_region = pg.LinearRegionItem(
            values=[0, 0], movable=False,
            brush=pg.mkBrush(76, 175, 80, 40),
            pen=pg.mkPen('#4caf50', width=1, style=QtCore.Qt.DashLine)
        )
        self._bw_region.setZValue(-10)
        self._plt_amp.addItem(self._bw_region)
        self._bw_region.setVisible(False)

        # Layer 5: -3dB threshold line (horizontal dotted green)
        self._threshold_line = pg.InfiniteLine(
            pos=0, angle=0, movable=False,
            pen=pg.mkPen('#4caf50', width=1, style=QtCore.Qt.DotLine)
        )
        self._threshold_line.setVisible(False)
        self._plt_amp.addItem(self._threshold_line)

        # --- Plot 2: Phase ---
        self._plt_phase = self._plot_widget.addPlot(row=1, col=0)
        self._plt_phase.setLabel('left', 'Phase', units='deg', color=text_color)
        self._plt_phase.setLabel('bottom', 'Frequency', units='Hz', color=text_color)
        self._plt_phase.showGrid(x=True, y=True, alpha=0.3)
        self._plt_phase.setTitle("Phase Sweep", color=text_color)
        for ax_name in ['left', 'bottom']:
            self._plt_phase.getAxis(ax_name).setPen(axis_color)
            self._plt_phase.getAxis(ax_name).setTextPen(axis_color)

        self._curve_phase = self._plt_phase.plot(
            pen=pg.mkPen('#e040fb' if theme == 'dark' else '#7b1fa2', width=1.5),
            name='Phase'
        )

        # Link X axes (zoom/pan synchronized)
        self._plt_phase.setXLink(self._plt_amp)

        # Timer for periodic updates (300ms interval)
        self._update_timer = QtCore.QTimer(self)
        self._update_timer.timeout.connect(self._refresh_data)
        self._update_timer.start(300)

    def _refresh_data(self):
        """
        Reads worker buffers, computes spline/peak/bandwidth, and updates plots.
        All computation is local — zero impact on acquisition pipeline.
        """
        import numpy as np
        from scipy.interpolate import UnivariateSpline

        # Access current worker (resilient to STOP/START recreating the worker)
        if self._main_window is None:
            return
        worker = getattr(self._main_window, 'worker', None)
        if worker is None:
            return

        # Read buffers
        amp_data = worker.get_value1_buffer()
        phase_data = worker.get_value2_buffer()
        freq_range = worker.get_frequency_range()
        spline_factor = worker.get_spline_factor()

        # Guard: skip if data not ready
        if amp_data is None or freq_range is None:
            return
        if len(amp_data) == 0 or len(freq_range) == 0:
            return
        if np.all(amp_data == 0):
            return

        # --- Update raw amplitude scatter (SG-filtered data points) ---
        self._curve_raw.setData(x=freq_range, y=amp_data)

        # --- Update phase curve ---
        if phase_data is not None and len(phase_data) == len(freq_range):
            self._curve_phase.setData(x=freq_range, y=phase_data)

        # --- Compute spline fit and peak/bandwidth ---
        try:
            if spline_factor is None or spline_factor <= 0:
                spline_factor = 0.05  # fallback

            spline_points = int(freq_range[-1] - freq_range[0]) + 1
            if spline_points < 10:
                return

            xrange_idx = np.arange(len(amp_data))
            freq_fine = np.linspace(freq_range[0], freq_range[-1], spline_points)
            s = UnivariateSpline(xrange_idx, amp_data, s=spline_factor)
            xs = np.linspace(0, len(amp_data) - 1, spline_points)
            mag_fit = s(xs)

            # Update spline curve
            self._curve_spline.setData(x=freq_fine, y=mag_fit)

            # --- parameters_finder algorithm (replicated from Serial.py) ---
            f_max = np.max(mag_fit)
            i_max = np.argmax(mag_fit)
            percent = 0.707  # -3dB threshold

            if f_max <= 0:
                self._bw_region.setVisible(False)
                self._threshold_line.setVisible(False)
                return

            # Find left edge (-3dB)
            err_left = False
            index_m = int(i_max)
            while mag_fit[index_m] > percent * f_max:
                if index_m < 1:
                    err_left = True
                    break
                index_m -= 1

            if not err_left:
                m_left = (mag_fit[index_m + 1] - mag_fit[index_m]) / (freq_fine[index_m + 1] - freq_fine[index_m])
                c_left = mag_fit[index_m] - freq_fine[index_m] * m_left
                f_leading = (percent * f_max - c_left) / m_left if m_left != 0 else freq_fine[index_m]
            else:
                f_leading = freq_fine[0]

            # Find right edge (-3dB)
            err_right = False
            index_M = int(i_max)
            while mag_fit[index_M] > percent * f_max:
                if index_M >= len(mag_fit) - 1:
                    err_right = True
                    break
                index_M += 1

            if not err_right:
                m_right = (mag_fit[index_M - 1] - mag_fit[index_M]) / (freq_fine[index_M - 1] - freq_fine[index_M])
                c_right = mag_fit[index_M] - freq_fine[index_M] * m_right
                f_trailing = (percent * f_max - c_right) / m_right if m_right != 0 else freq_fine[index_M]
            else:
                f_trailing = freq_fine[-1]

            bandwidth = abs(f_trailing - f_leading)
            peak_freq = freq_fine[i_max]
            q_factor = peak_freq / bandwidth if bandwidth > 0 else 0
            dissipation = 1.0 / q_factor if q_factor > 0 else 0

            # Update peak marker
            self._peak_marker.setData(x=[peak_freq], y=[f_max])

            # Update -3dB bandwidth region
            self._bw_region.setRegion([f_leading, f_trailing])
            self._bw_region.setVisible(True)

            # Update -3dB threshold line
            self._threshold_line.setValue(percent * f_max)
            self._threshold_line.setVisible(True)

            # Update info label
            overtone_info = worker.get_overtone()
            overtone_name = overtone_info[0] if overtone_info[0] else "---"
            overtone_value = overtone_info[1] if overtone_info[1] else 0
            self._info_label.setText(
                "Overtone: {} ({:.0f} Hz)  |  Peak: {:.2f} Hz  |  "
                "BW(-3dB): {:.2f} Hz  |  Q: {:.0f}  |  D: {:.2e}".format(
                    overtone_name, overtone_value,
                    peak_freq, bandwidth, q_factor, dissipation
                )
            )

        except Exception:
            # Spline/peak computation failed — just show raw data
            self._bw_region.setVisible(False)
            self._threshold_line.setVisible(False)
            self._info_label.setText("Live sweep (spline computation pending...)")

    def closeEvent(self, event):
        """Stop the timer when dialog is closed."""
        self._update_timer.stop()
        event.accept()


###############################################################################################################
# Status Label Proxy - maintains compatibility with old infostatus/infobar API
###############################################################################################################
class StatusLabelProxy:
    """
    Proxy class that mimics QLabel interface but updates a unified status display.
    When setText() or setStyleSheet() is called, it updates the combined statusMessage.
    """
    def __init__(self, ui_ref, label_type):
        """
        :param ui_ref: Reference to Ui_Main instance
        :param label_type: 'status' for infostatus, 'message' for infobar
        """
        self._ui = ui_ref
        self._type = label_type
        self._text = ""
        self._stylesheet = ""

    def setText(self, text):
        self._text = text
        self._ui._update_unified_status()

    def text(self):
        return self._text

    def setStyleSheet(self, style):
        self._stylesheet = style
        # Extract color from stylesheet for the indicator
        if self._type == 'status':
            self._ui._update_status_indicator(style)

    def styleSheet(self):
        return self._stylesheet


###############################################################################################################
# Main UI Class
###############################################################################################################
class Ui_Main(object):

    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")
        MainWindow.setMinimumSize(QtCore.QSize(1000, 600))
        MainWindow.resize(1200, 750)

        # Store MainWindow reference for dialogs
        self._mainWindow = MainWindow

        # Enable transparency
        MainWindow.setAttribute(QtCore.Qt.WA_TranslucentBackground, False)
        MainWindow.setWindowOpacity(1.0)

        self.centralwidget = QtWidgets.QWidget(MainWindow)

        # Main vertical layout (content + status dock)
        self.mainVerticalLayout = QtWidgets.QVBoxLayout(self.centralwidget)
        self.mainVerticalLayout.setContentsMargins(0, 0, 0, 0)
        self.mainVerticalLayout.setSpacing(0)

        # =====================================================================
        # MAIN HORIZONTAL SPLITTER (Left sidebar | Center content)
        # =====================================================================
        self.mainSplitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.mainSplitter.setHandleWidth(5)
        self.mainSplitter.setChildrenCollapsible(True)

        # =====================================================================
        # LEFT SIDEBAR - Minimal Controls
        # =====================================================================
        self.leftSidebarWidget = QtWidgets.QWidget()
        self.leftSidebarWidget.setMinimumWidth(180)
        self.leftSidebarWidget.setMaximumWidth(280)
        self.leftSidebarLayout = QtWidgets.QVBoxLayout(self.leftSidebarWidget)
        self.leftSidebarLayout.setContentsMargins(8, 8, 8, 8)
        self.leftSidebarLayout.setSpacing(12)

        # -----------------------------------------------------------------
        # Serial Connection Group
        # -----------------------------------------------------------------
        self.grpConnection = QtWidgets.QGroupBox("Serial Connection")
        self.grpConnectionLayout = QtWidgets.QVBoxLayout(self.grpConnection)
        self.grpConnectionLayout.setSpacing(6)
        self.grpConnectionLayout.setContentsMargins(10, 18, 10, 10)

        # Port label and combo
        self.portLabel = QtWidgets.QLabel("Port")
        self.portLabel.setObjectName("sectionLabel")
        self.grpConnectionLayout.addWidget(self.portLabel)

        self.cBox_Port = QtWidgets.QComboBox()
        self.grpConnectionLayout.addWidget(self.cBox_Port)

        # Refresh and Connect buttons
        self.connectionButtonsLayout = QtWidgets.QHBoxLayout()
        self.connectionButtonsLayout.setSpacing(6)
        self.pButton_Refresh = QtWidgets.QPushButton("Refresh")
        self.pButton_Refresh.setFixedHeight(28)
        self.pButton_Connect = QtWidgets.QPushButton("Connect")
        self.pButton_Connect.setObjectName("btnConnect")
        self.pButton_Connect.setFixedHeight(28)
        self.connectionButtonsLayout.addWidget(self.pButton_Refresh)
        self.connectionButtonsLayout.addWidget(self.pButton_Connect)
        self.grpConnectionLayout.addLayout(self.connectionButtonsLayout)

        self.leftSidebarLayout.addWidget(self.grpConnection)

        # -----------------------------------------------------------------
        # Measurement Setup Group
        # -----------------------------------------------------------------
        self.grpMeasurement = QtWidgets.QGroupBox("Measurement Setup")
        self.grpMeasurementLayout = QtWidgets.QVBoxLayout(self.grpMeasurement)
        self.grpMeasurementLayout.setSpacing(6)
        self.grpMeasurementLayout.setContentsMargins(10, 18, 10, 10)

        # Mode label and combo
        self.modeLabel = QtWidgets.QLabel("Mode")
        self.modeLabel.setObjectName("sectionLabel")
        self.grpMeasurementLayout.addWidget(self.modeLabel)

        self.cBox_Source = QtWidgets.QComboBox()
        self.grpMeasurementLayout.addWidget(self.cBox_Source)

        # Spacer between Mode and Frequency
        self.grpMeasurementLayout.addSpacing(4)

        # Frequency label and combo
        self.freqLabel = QtWidgets.QLabel("Frequency")
        self.freqLabel.setObjectName("sectionLabel")
        self.grpMeasurementLayout.addWidget(self.freqLabel)

        self.cBox_Speed = QtWidgets.QComboBox()
        self.grpMeasurementLayout.addWidget(self.cBox_Speed)

        self.leftSidebarLayout.addWidget(self.grpMeasurement)

        # -----------------------------------------------------------------
        # Current Readings (moved from right sidebar)
        # -----------------------------------------------------------------
        self.grpReadings = QtWidgets.QGroupBox("Current Readings")
        self.grpReadingsLayout = QtWidgets.QVBoxLayout(self.grpReadings)
        self.grpReadingsLayout.setSpacing(4)
        self.grpReadingsLayout.setContentsMargins(10, 18, 10, 10)

        self.l7 = self._create_data_row("Frequency", "---")
        self.grpReadingsLayout.addWidget(self.l7)

        self.l6 = self._create_data_row("Dissipation", "---")
        self.grpReadingsLayout.addWidget(self.l6)

        self.l6a = self._create_data_row("Temperature", "---")
        self.grpReadingsLayout.addWidget(self.l6a)

        self.leftSidebarLayout.addWidget(self.grpReadings)

        # Spacer
        self.leftSidebarLayout.addSpacing(8)

        # -----------------------------------------------------------------
        # Plot Controls
        # -----------------------------------------------------------------
        self.grpPlotControls = QtWidgets.QGroupBox("Plot Controls")
        self.grpPlotControlsLayout = QtWidgets.QVBoxLayout(self.grpPlotControls)
        self.grpPlotControlsLayout.setSpacing(6)
        self.grpPlotControlsLayout.setContentsMargins(10, 18, 10, 10)

        self.pButton_Clear = QtWidgets.QPushButton("Clear")
        self.pButton_Clear.setFixedHeight(28)
        self.grpPlotControlsLayout.addWidget(self.pButton_Clear)

        self.pButton_Reference = QtWidgets.QPushButton("Set Reference")
        self.pButton_Reference.setFixedHeight(28)
        self.grpPlotControlsLayout.addWidget(self.pButton_Reference)

        self.pButton_Autoscale = QtWidgets.QPushButton("Autoscale")
        self.pButton_Autoscale.setFixedHeight(28)
        self.pButton_Autoscale.setEnabled(False)
        self.grpPlotControlsLayout.addWidget(self.pButton_Autoscale)

        self.leftSidebarLayout.addWidget(self.grpPlotControls)

        # Expandable spacer - pushes Acquisition group to bottom
        self.leftSidebarLayout.addStretch()

        # -----------------------------------------------------------------
        # Acquisition (Sampling time + START/STOP buttons)
        # -----------------------------------------------------------------
        self.grpAcquisition2 = QtWidgets.QGroupBox("Acquisition")
        self.grpAcquisition2Layout = QtWidgets.QVBoxLayout(self.grpAcquisition2)
        self.grpAcquisition2Layout.setSpacing(8)
        self.grpAcquisition2Layout.setContentsMargins(10, 18, 10, 10)

        # Sampling time indicator
        self.l6b = self._create_data_row("Sampling", "---")
        self.grpAcquisition2Layout.addWidget(self.l6b)

        # Unified START / STOP toggle button
        self.pButton_StartStop = QtWidgets.QPushButton("START")
        self.pButton_StartStop.setObjectName("btnStart")
        self.pButton_StartStop.setFixedHeight(36)
        self.grpAcquisition2Layout.addWidget(self.pButton_StartStop)

        self.leftSidebarLayout.addWidget(self.grpAcquisition2)

        # -----------------------------------------------------------------
        # Hidden widgets for compatibility
        # -----------------------------------------------------------------
        # Acquisition group (hidden)
        self.grpAcquisition = QtWidgets.QGroupBox("Acquisition")
        self.grpAcquisitionLayout = QtWidgets.QFormLayout(self.grpAcquisition)
        self.sBox_Samples = QtWidgets.QSpinBox()
        self.sBox_Samples.setMinimum(1)
        self.sBox_Samples.setMaximum(100000)
        self.sBox_Samples.setValue(500)
        self.sBox_Samples.setSuffix(" samples")
        self.grpAcquisitionLayout.addRow("Samples:", self.sBox_Samples)
        self.chBox_export = QtWidgets.QCheckBox("Export sweep data")
        self.grpAcquisitionLayout.addRow("", self.chBox_export)
        self.grpAcquisition.hide()

        # Reference group (hidden, kept for compatibility)
        self.grpReference = QtWidgets.QWidget()
        self.grpReferenceLayout = QtWidgets.QVBoxLayout(self.grpReference)
        self.inforef1 = self._create_data_row("Ref. Freq.", "not set")
        self.grpReferenceLayout.addWidget(self.inforef1)
        self.inforef2 = self._create_data_row("Ref. Diss.", "not set")
        self.grpReferenceLayout.addWidget(self.inforef2)
        self.grpReference.hide()

        # Footer links (hidden, moved to Help menu)
        self.footerWidget = QtWidgets.QWidget()
        self.footerLayout = QtWidgets.QVBoxLayout(self.footerWidget)
        self.lg = QtWidgets.QLabel()
        self.lmail = QtWidgets.QLabel()
        self.l4 = QtWidgets.QLabel()
        self.footerWidget.hide()

        # Placeholder for logo (hidden)
        self.l3 = QtWidgets.QLabel()
        self.l3.hide()

        # Add left sidebar to splitter
        self.mainSplitter.addWidget(self.leftSidebarWidget)

        # =====================================================================
        # CENTER - Plots and Tabs
        # =====================================================================
        self.centerWidget = QtWidgets.QWidget()
        self.centerLayout = QtWidgets.QVBoxLayout(self.centerWidget)
        self.centerLayout.setContentsMargins(8, 8, 8, 8)
        self.centerLayout.setSpacing(8)

        # Title
        self.label = QtWidgets.QLabel("openQCM Q-1 Real-Time Monitor")
        self.label.setObjectName("titleLabel")
        self.label.setAlignment(QtCore.Qt.AlignCenter)
        self.centerLayout.addWidget(self.label)

        # Tab Widget
        self.tabWidget = QtWidgets.QTabWidget()
        self.tabWidget.setObjectName("mainTabWidget")

        # -----------------------------------------------------------------
        # TAB 1: Plots
        # -----------------------------------------------------------------
        self.tabPlots = QtWidgets.QWidget()
        self.tabPlotsLayout = QtWidgets.QVBoxLayout(self.tabPlots)
        self.tabPlotsLayout.setContentsMargins(4, 4, 4, 4)
        self.tabPlotsLayout.setSpacing(4)

        # Plots container
        self.grpPlots = QtWidgets.QGroupBox()
        self.grpPlots.setObjectName("plotsGroup")
        self.grpPlotsLayout = QtWidgets.QVBoxLayout(self.grpPlots)
        self.grpPlotsLayout.setContentsMargins(4, 4, 4, 4)
        self.grpPlotsLayout.setSpacing(0)

        # Vertical splitter for plots
        self.plotSplitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        self.plotSplitter.setObjectName("plotSplitter")
        self.plotSplitter.setHandleWidth(6)

        # Top plots: Amplitude/Phase and Temperature
        self.plt = GraphicsLayoutWidget()
        self.plt.setBackground('#2b2b2b')
        self.plt.setMinimumHeight(200)
        self.plotSplitter.addWidget(self.plt)

        # Bottom plot: Frequency/Dissipation
        self.pltB = GraphicsLayoutWidget()
        self.pltB.setBackground('#2b2b2b')
        self.pltB.setMinimumHeight(180)
        self.plotSplitter.addWidget(self.pltB)

        # Set initial sizes
        self.plotSplitter.setSizes([220, 400])
        self.plotSplitter.setStretchFactor(0, 0)
        self.plotSplitter.setStretchFactor(1, 1)
        self.plotSplitter.splitterMoved.connect(self._on_splitter_moved)

        self.grpPlotsLayout.addWidget(self.plotSplitter)
        self.tabPlotsLayout.addWidget(self.grpPlots, stretch=1)
        self.tabWidget.addTab(self.tabPlots, "Plots")

        # -----------------------------------------------------------------
        # TAB 2: System Log
        # -----------------------------------------------------------------
        self.tabLog = QtWidgets.QWidget()
        self.tabLogLayout = QtWidgets.QVBoxLayout(self.tabLog)
        self.tabLogLayout.setContentsMargins(4, 4, 4, 4)
        self.tabLogLayout.setSpacing(4)

        self.systemLog = QtWidgets.QTextEdit()
        self.systemLog.setObjectName("systemLog")
        self.systemLog.setReadOnly(True)
        self.systemLog.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.systemLog.setPlaceholderText("Log messages...")
        self.tabLogLayout.addWidget(self.systemLog)

        self.tabWidget.addTab(self.tabLog, "System Log")

        self.centerLayout.addWidget(self.tabWidget, stretch=1)

        # Add center to splitter
        self.mainSplitter.addWidget(self.centerWidget)

        # Configure splitter
        self.mainSplitter.setSizes([200, 800])
        self.mainSplitter.setCollapsible(0, True)   # Left sidebar collapsible
        self.mainSplitter.setCollapsible(1, False)  # Center not collapsible
        # Connect splitter moved signal to sync menu checkbox
        self.mainSplitter.splitterMoved.connect(self._on_main_splitter_moved)

        self.mainVerticalLayout.addWidget(self.mainSplitter, stretch=1)

        # =====================================================================
        # BOTTOM STATUS DOCK (Collapsible) - Single row: status + progress bar
        # =====================================================================
        self.statusDock = QtWidgets.QDockWidget("Status", MainWindow)
        self.statusDock.setObjectName("statusDock")
        self.statusDock.setAllowedAreas(QtCore.Qt.BottomDockWidgetArea)
        self.statusDock.setFeatures(
            QtWidgets.QDockWidget.DockWidgetClosable |
            QtWidgets.QDockWidget.DockWidgetMovable
        )

        self.statusDockWidget = QtWidgets.QWidget()
        self.statusDockLayout = QtWidgets.QHBoxLayout(self.statusDockWidget)
        self.statusDockLayout.setContentsMargins(12, 6, 12, 6)
        self.statusDockLayout.setSpacing(12)

        # Status indicator (colored dot + text)
        self.statusIndicator = QtWidgets.QLabel("●")
        self.statusIndicator.setObjectName("statusIndicator")
        self.statusIndicator.setFixedWidth(16)
        self.statusDockLayout.addWidget(self.statusIndicator)

        # Unified status message (combines infostatus + infobar)
        self.statusMessage = QtWidgets.QLabel("Standby | Ready")
        self.statusMessage.setObjectName("statusMessage")
        self.statusDockLayout.addWidget(self.statusMessage)

        # Spacer to push readings to the right
        self.statusDockLayout.addStretch()

        # Current Readings in Status Bar (visible when left panel is hidden)
        self.statusReadingsWidget = QtWidgets.QWidget()
        self.statusReadingsLayout = QtWidgets.QHBoxLayout(self.statusReadingsWidget)
        self.statusReadingsLayout.setContentsMargins(0, 0, 0, 0)
        self.statusReadingsLayout.setSpacing(16)

        # Frequency reading
        self.statusFreqLabel = QtWidgets.QLabel("F:")
        self.statusFreqLabel.setObjectName("statusReadingLabel")
        self.statusFreqValue = QtWidgets.QLabel("---")
        self.statusFreqValue.setObjectName("statusReadingValue")
        self.statusReadingsLayout.addWidget(self.statusFreqLabel)
        self.statusReadingsLayout.addWidget(self.statusFreqValue)

        # Dissipation reading
        self.statusDissLabel = QtWidgets.QLabel("D:")
        self.statusDissLabel.setObjectName("statusReadingLabel")
        self.statusDissValue = QtWidgets.QLabel("---")
        self.statusDissValue.setObjectName("statusReadingValue")
        self.statusReadingsLayout.addWidget(self.statusDissLabel)
        self.statusReadingsLayout.addWidget(self.statusDissValue)

        # Separator between primary (F, D) and secondary (T, S) readings
        self.statusReadingSep = QtWidgets.QFrame()
        self.statusReadingSep.setFrameShape(QtWidgets.QFrame.VLine)
        self.statusReadingSep.setObjectName("statusSeparator")
        self.statusReadingsLayout.addWidget(self.statusReadingSep)

        # Temperature reading
        self.statusTempLabel = QtWidgets.QLabel("T:")
        self.statusTempLabel.setObjectName("statusReadingLabel")
        self.statusTempValue = QtWidgets.QLabel("---")
        self.statusTempValue.setObjectName("statusReadingValue")
        self.statusReadingsLayout.addWidget(self.statusTempLabel)
        self.statusReadingsLayout.addWidget(self.statusTempValue)

        # Sampling time reading
        self.statusSampLabel = QtWidgets.QLabel("S:")
        self.statusSampLabel.setObjectName("statusReadingLabel")
        self.statusSampValue = QtWidgets.QLabel("---")
        self.statusSampValue.setObjectName("statusReadingValue")
        self.statusReadingsLayout.addWidget(self.statusSampLabel)
        self.statusReadingsLayout.addWidget(self.statusSampValue)

        self.statusDockLayout.addWidget(self.statusReadingsWidget)

        # Separator before progress bar
        self.statusSeparator = QtWidgets.QFrame()
        self.statusSeparator.setFrameShape(QtWidgets.QFrame.VLine)
        self.statusSeparator.setObjectName("statusSeparator")
        self.statusDockLayout.addWidget(self.statusSeparator)

        # Progress bar (smaller, right side)
        self.progressBar = QtWidgets.QProgressBar()
        self.progressBar.setValue(0)
        self.progressBar.setFixedHeight(10)
        self.progressBar.setFixedWidth(120)
        self.progressBar.setTextVisible(False)
        self.statusDockLayout.addWidget(self.progressBar)

        self.statusDock.setWidget(self.statusDockWidget)

        # Compatibility: create proxy objects for infostatus and infobar
        # These mimic QLabel API but update the unified statusMessage
        self.infostatus = StatusLabelProxy(self, 'status')
        self.infostatus._text = "Standby"
        self.infobar = StatusLabelProxy(self, 'message')
        self.infobar._text = "Ready"

        MainWindow.setCentralWidget(self.centralwidget)
        MainWindow.addDockWidget(QtCore.Qt.BottomDockWidgetArea, self.statusDock)

        # =====================================================================
        # Device Info Dialog (created but not shown)
        # =====================================================================
        self.deviceInfoDialog = DeviceInfoDialog(MainWindow)

        # Copy references for compatibility
        self.info1a = self.deviceInfoDialog.info1a
        self.info11 = self.deviceInfoDialog.info11
        self.info2 = self.deviceInfoDialog.info2
        self.info6 = self.deviceInfoDialog.info6
        self.info3 = self.deviceInfoDialog.info3
        self.info4 = self.deviceInfoDialog.info4
        self.info4a = self.deviceInfoDialog.info4a
        self.info5 = self.deviceInfoDialog.info5
        self.info7 = self.deviceInfoDialog.info7

        # =====================================================================
        # Software info widgets (hidden, used by get_web_info)
        # =====================================================================
        self.grpSoftware = QtWidgets.QWidget()
        self.lweb2 = self._create_data_row("Connection", "checking...")
        self.lweb3 = self._create_data_row("Updates", "checking...")
        self.pButton_Download = QtWidgets.QPushButton("Download Update")
        self.pButton_Download.setEnabled(False)
        self.grpSoftware.hide()

        # =====================================================================
        # MENU BAR
        # =====================================================================
        self.menubar = QtWidgets.QMenuBar(MainWindow)
        self.menubar.setObjectName("menubar")
        MainWindow.setMenuBar(self.menubar)

        # -----------------------------------------------------------------
        # View Menu
        # -----------------------------------------------------------------
        self.menuView = QtWidgets.QMenu(self.menubar)
        self.menuView.setTitle("View")
        self.menubar.addMenu(self.menuView)

        # Device Information action
        self.actionDeviceInfo = QtWidgets.QAction(MainWindow)
        self.actionDeviceInfo.setText("Device Information")
        self.actionDeviceInfo.triggered.connect(self._show_device_info)
        self.menuView.addAction(self.actionDeviceInfo)

        # Toggle Status Bar
        self.actionToggleStatus = self.statusDock.toggleViewAction()
        self.actionToggleStatus.setText("Status Bar")
        self.menuView.addAction(self.actionToggleStatus)

        # Toggle Left Panel
        self.actionToggleLeftPanel = QtWidgets.QAction(MainWindow)
        self.actionToggleLeftPanel.setText("Left Panel")
        self.actionToggleLeftPanel.setCheckable(True)
        self.actionToggleLeftPanel.setChecked(True)
        self.actionToggleLeftPanel.triggered.connect(self._toggle_left_panel)
        self.menuView.addAction(self.actionToggleLeftPanel)

        # Toggle Cursors (for Frequency/Dissipation plot)
        self.actionToggleCursors = QtWidgets.QAction(MainWindow)
        self.actionToggleCursors.setText("Cursors")
        self.actionToggleCursors.setCheckable(True)
        self.actionToggleCursors.setChecked(False)
        self.menuView.addAction(self.actionToggleCursors)

        self.menuView.addSeparator()

        # Theme submenu
        self.menuTheme = QtWidgets.QMenu(self.menuView)
        self.menuTheme.setTitle("Theme")
        self.menuView.addMenu(self.menuTheme)

        # Theme actions
        self.actionDarkTheme = QtWidgets.QAction(MainWindow)
        self.actionDarkTheme.setText("Dark Theme")
        self.actionDarkTheme.setCheckable(True)
        self.actionDarkTheme.setChecked(True)
        self.menuTheme.addAction(self.actionDarkTheme)

        self.actionLightTheme = QtWidgets.QAction(MainWindow)
        self.actionLightTheme.setText("Light Theme")
        self.actionLightTheme.setCheckable(True)
        self.actionLightTheme.setChecked(False)
        self.menuTheme.addAction(self.actionLightTheme)

        # Theme action group
        self.themeActionGroup = QtWidgets.QActionGroup(MainWindow)
        self.themeActionGroup.addAction(self.actionDarkTheme)
        self.themeActionGroup.addAction(self.actionLightTheme)
        self.themeActionGroup.setExclusive(True)

        # -----------------------------------------------------------------
        # Data Menu
        # -----------------------------------------------------------------
        self.menuData = QtWidgets.QMenu(self.menubar)
        self.menuData.setTitle("Data")
        self.menubar.addMenu(self.menuData)

        self.actionDataView = QtWidgets.QAction(MainWindow)
        self.actionDataView.setText("Log Data View")
        self.menuData.addAction(self.actionDataView)

        self.actionRawDataView = QtWidgets.QAction(MainWindow)
        self.actionRawDataView.setText("Raw Data View")
        self.menuData.addAction(self.actionRawDataView)

        # -----------------------------------------------------------------
        # Help Menu
        # -----------------------------------------------------------------
        self.menuHelp = QtWidgets.QMenu(self.menubar)
        self.menuHelp.setTitle("Help")
        self.menubar.addMenu(self.menuHelp)

        # User Guide
        self.actionUserGuide = QtWidgets.QAction(MainWindow)
        self.actionUserGuide.setText("User Guide")
        self.actionUserGuide.triggered.connect(
            lambda: webbrowser.open("https://openqcm.com/shared/q-1/openQCM_Q-1-userguide-v2.0.pdf")
        )
        self.menuHelp.addAction(self.actionUserGuide)

        # Website
        self.actionWebsite = QtWidgets.QAction(MainWindow)
        self.actionWebsite.setText("Website")
        self.actionWebsite.triggered.connect(
            lambda: webbrowser.open("https://openqcm.com/")
        )
        self.menuHelp.addAction(self.actionWebsite)

        # Email Support
        self.actionEmailSupport = QtWidgets.QAction(MainWindow)
        self.actionEmailSupport.setText("Email Support")
        self.actionEmailSupport.triggered.connect(
            lambda: webbrowser.open("mailto:info@openqcm.com")
        )
        self.menuHelp.addAction(self.actionEmailSupport)

        self.menuHelp.addSeparator()

        # Check for Updates
        self.actionCheckUpdates = QtWidgets.QAction(MainWindow)
        self.actionCheckUpdates.setText("Check for Updates...")
        self.menuHelp.addAction(self.actionCheckUpdates)

        # Download Update (initially disabled)
        self.actionDownloadUpdate = QtWidgets.QAction(MainWindow)
        self.actionDownloadUpdate.setText("Download Update")
        self.actionDownloadUpdate.setEnabled(False)
        self.menuHelp.addAction(self.actionDownloadUpdate)

        self.menuHelp.addSeparator()

        # About
        self.actionAbout = QtWidgets.QAction(MainWindow)
        self.actionAbout.setText("About openQCM Q-1")
        self.actionAbout.triggered.connect(self._show_about)
        self.menuHelp.addAction(self.actionAbout)

        # Store current theme
        self._current_theme = 'dark'

        # Apply dark stylesheet (default)
        MainWindow.setStyleSheet(self._get_dark_stylesheet())

        self.retranslateUi(MainWindow)
        QtCore.QMetaObject.connectSlotsByName(MainWindow)

    def _create_data_row(self, label_text, value_text):
        """Create a label-value row widget."""
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(widget)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(8)

        label = QtWidgets.QLabel(label_text)
        label.setMinimumWidth(70)
        layout.addWidget(label)

        value = QtWidgets.QLabel(value_text)
        value.setObjectName("dataValue")
        value.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        layout.addWidget(value, stretch=1)

        widget.valueLabel = value
        return widget

    def _update_unified_status(self):
        """Update the unified status message from infostatus and infobar proxy values."""
        status_text = self.infostatus._text if self.infostatus._text else "Standby"
        message_text = self.infobar._text if self.infobar._text else "Ready"
        self.statusMessage.setText(f"{status_text} | {message_text}")

    def _update_status_indicator(self, stylesheet):
        """
        Update the status indicator color based on the stylesheet.

        Color scheme (machine state):
        - Gray (#888888)   = Disconnected (serial not connected)
        - Yellow (#ffd700) = Connected + Standby (ready but not acquiring)
        - Orange (#ff9800) = Processing / Warning (acquiring, transitional states)
        - Green (#4caf50)  = Monitoring / Success (active and working)
        - Red (#f44336)    = Error (critical failure)
        """
        # Parse background color from stylesheet to determine state
        if '#00ff72' in stylesheet or '#e8f5e9' in stylesheet or '#2e7d32' in stylesheet:
            # Green - Monitoring/Success (active and working)
            self.statusIndicator.setStyleSheet("color: #4caf50; font-size: 14px;")
        elif '#ff0000' in stylesheet or '#ffebee' in stylesheet or '#c62828' in stylesheet:
            # Red - Error (critical failure)
            self.statusIndicator.setStyleSheet("color: #f44336; font-size: 14px;")
        elif '#ffff00' in stylesheet or '#ff8000' in stylesheet or '#fff3e0' in stylesheet:
            # Orange - Processing/Warning (transitional states)
            self.statusIndicator.setStyleSheet("color: #ff9800; font-size: 14px;")
        else:
            # Default - check if it's standby (connected) or disconnected
            # This will be handled by set_connection_state() method
            pass

    def set_connection_state(self, connected):
        """
        Update status indicator based on serial connection state.
        Called from mainWindow.py when connection state changes.

        :param connected: True if serial port is connected
        """
        if connected:
            # Yellow - Connected + Standby
            self.statusIndicator.setStyleSheet("color: #ffd700; font-size: 14px;")
        else:
            # Gray - Disconnected
            self.statusIndicator.setStyleSheet("color: #888888; font-size: 14px;")

    def update_status_bar_readings(self, frequency=None, dissipation=None, temperature=None, sampling_time=None):
        """
        Update the current readings displayed in the status bar.
        These are visible even when the left panel is hidden.

        :param frequency: Frequency value string (e.g., "9999845.2 Hz")
        :param dissipation: Dissipation value string (e.g., "0.000012")
        :param temperature: Temperature value string (e.g., "25.3 °C")
        :param sampling_time: Sampling time string (e.g., "3.2 s")
        """
        if frequency is not None:
            self.statusFreqValue.setText(frequency)
        if dissipation is not None:
            self.statusDissValue.setText(dissipation)
        if temperature is not None:
            self.statusTempValue.setText(temperature)
        if sampling_time is not None:
            self.statusSampValue.setText(sampling_time)

    def _toggle_left_panel(self, checked):
        """
        Show or hide the left panel (sidebar).
        Called when View -> Left Panel menu action is triggered.
        """
        if checked:
            # Show left panel
            self.leftSidebarWidget.show()
            # Restore reasonable sizes
            total_width = self.mainSplitter.width()
            self.mainSplitter.setSizes([200, total_width - 200])
        else:
            # Hide left panel by collapsing it
            self.mainSplitter.setSizes([0, self.mainSplitter.width()])

    def _on_main_splitter_moved(self, pos, index):
        """
        Sync the Left Panel menu checkbox when user drags the splitter.
        If left panel is collapsed (size=0), uncheck the menu item.
        """
        sizes = self.mainSplitter.sizes()
        left_panel_visible = sizes[0] > 10  # Consider visible if width > 10px
        # Update menu checkbox without triggering the action
        self.actionToggleLeftPanel.blockSignals(True)
        self.actionToggleLeftPanel.setChecked(left_panel_visible)
        self.actionToggleLeftPanel.blockSignals(False)

    def _on_splitter_moved(self, pos, index):
        """Enforce vertical splitter constraints."""
        total_height = self.plotSplitter.height()
        max_top_height = total_height // 2
        min_top_height = 200

        sizes = self.plotSplitter.sizes()
        top_height = sizes[0]

        if top_height > max_top_height:
            self.plotSplitter.setSizes([max_top_height, total_height - max_top_height])
        elif top_height < min_top_height:
            self.plotSplitter.setSizes([min_top_height, total_height - min_top_height])

    def _show_device_info(self):
        """Show the Device Information dialog."""
        self.deviceInfoDialog.show()
        self.deviceInfoDialog.raise_()
        self.deviceInfoDialog.activateWindow()

    def _show_about(self):
        """Show About dialog."""
        from openQCM.core.constants import Constants
        QtWidgets.QMessageBox.about(
            self._mainWindow,
            "About openQCM Q-1",
            f"<h3>openQCM Q-1 Real-Time Monitor</h3>"
            f"<p>Version {Constants.app_version}</p>"
            f"<p>Open-source Python application for real-time data acquisition "
            f"and analysis from openQCM Q-1 Device.</p>"
            f"<p><a href='https://openqcm.com/'>openqcm.com</a></p>"
        )

    def _get_dark_stylesheet(self):
        return """
            QMainWindow, QWidget {
                background-color: #2b2b2b;
                color: #e0e0e0;
                font-size: 12px;
            }

            QMenuBar {
                background-color: #2b2b2b;
                color: #e0e0e0;
                border-bottom: 1px solid #555555;
            }
            QMenuBar::item {
                background: transparent;
                padding: 4px 10px;
            }
            QMenuBar::item:selected {
                background-color: #3c3c3c;
            }
            QMenu {
                background-color: #2b2b2b;
                color: #e0e0e0;
                border: 1px solid #555555;
            }
            QMenu::item {
                padding: 6px 20px;
            }
            QMenu::item:selected {
                background-color: #3c3c3c;
            }
            QMenu::indicator:checked {
                image: none;
                width: 12px;
                height: 12px;
                background-color: #00bcd4;
                border-radius: 2px;
            }

            /* Section labels */
            #sectionLabel {
                color: #a0a0a0;
                font-size: 11px;
                font-weight: bold;
                padding-bottom: 2px;
            }

            QGroupBox {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                border-radius: 4px;
                margin-top: 12px;
                padding-top: 10px;
                font-weight: bold;
                color: #e0e0e0;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 6px;
                color: #e0e0e0;
            }

            QComboBox {
                background-color: #2b2b2b;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 4px 8px;
                color: #e0e0e0;
                min-height: 22px;
            }
            QComboBox:hover {
                border-color: #777777;
            }
            QComboBox:focus {
                border-color: #888888;
            }
            QComboBox::drop-down {
                border: none;
                width: 18px;
                background: transparent;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 4px solid #888888;
                margin-right: 4px;
            }
            QComboBox QAbstractItemView {
                background-color: #2b2b2b;
                color: #e0e0e0;
                selection-background-color: #555555;
                selection-color: #ffffff;
                border: 1px solid #555555;
            }
            QComboBox QAbstractItemView::item {
                padding: 4px 8px;
                min-height: 20px;
            }
            QComboBox QAbstractItemView::item:hover {
                background-color: #3c3c3c;
            }

            QSpinBox {
                background-color: #2b2b2b;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 4px 8px;
                color: #e0e0e0;
                min-height: 22px;
            }

            QPushButton {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 6px 12px;
                color: #e0e0e0;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
                border-color: #666666;
            }
            QPushButton:pressed {
                background-color: #555555;
            }
            QPushButton:disabled {
                background-color: #333333;
                color: #666666;
                border-color: #444444;
            }

            #btnConnect, #btnStart {
                background-color: #008EC0;
                color: #ffffff;
                border: 1px solid #007AA8;
            }
            #btnConnect:hover, #btnStart:hover {
                background-color: #0099D0;
            }
            #btnDisconnect, #btnStop {
                background-color: #DD8E6B;
                color: #ffffff;
                border: 1px solid #C47D5C;
            }
            #btnDisconnect:hover, #btnStop:hover {
                background-color: #E49E7E;
            }
            #btnConnect:disabled, #btnStart:disabled, #btnDisconnect:disabled, #btnStop:disabled {
                background-color: #383838;
                border-color: #404040;
                color: #666666;
            }

            QProgressBar {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                border-radius: 3px;
                text-align: center;
                color: #e0e0e0;
            }
            QProgressBar::chunk {
                background-color: #707070;
                border-radius: 2px;
            }

            #statusIndicator {
                color: #888888;
                font-size: 14px;
            }

            #statusMessage {
                color: #e0e0e0;
                padding: 2px 4px;
            }

            #statusReadingLabel {
                color: #a0a0a0;
                font-size: 11px;
            }

            #statusReadingValue {
                color: #ffffff;
                font-weight: bold;
                font-size: 11px;
                min-width: 80px;
            }

            #statusSeparator {
                color: #555555;
            }

            #titleLabel {
                color: #e0e0e0;
                font-size: 14px;
                font-weight: bold;
                padding: 8px;
            }

            #plotsGroup {
                background-color: #2b2b2b;
                border: 1px solid #555555;
                border-radius: 4px;
                margin-top: 0px;
                padding: 4px;
            }

            QSplitter::handle {
                background-color: #404040;
            }
            QSplitter::handle:hover {
                background-color: #505050;
            }
            QSplitter::handle:pressed {
                background-color: #606060;
            }

            #dataValue {
                color: #ffffff;
                font-weight: bold;
            }

            QCheckBox {
                color: #e0e0e0;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 1px solid #555555;
                border-radius: 3px;
                background-color: #3c3c3c;
            }
            QCheckBox::indicator:checked {
                background-color: #00bcd4;
                border-color: #00bcd4;
            }

            QLabel {
                color: #e0e0e0;
                background: transparent;
            }

            QScrollBar:vertical {
                background-color: #2b2b2b;
                width: 10px;
                border: none;
            }
            QScrollBar::handle:vertical {
                background-color: #555555;
                border-radius: 5px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #666666;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
            }

            QTabWidget::pane {
                border: 1px solid #555555;
                border-radius: 4px;
                background-color: #2b2b2b;
            }
            QTabBar::tab {
                background-color: #3c3c3c;
                color: #e0e0e0;
                border: 1px solid #555555;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                padding: 8px 20px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #2b2b2b;
                border-bottom: 1px solid #2b2b2b;
            }
            QTabBar::tab:hover:!selected {
                background-color: #4a4a4a;
            }

            #systemLog {
                background-color: #2b2b2b;
                color: #b0b0b0;
                border: none;
                font-family: "SF Mono", "Menlo", "Consolas", monospace;
                font-size: 11px;
                padding: 12px;
            }

            QDockWidget {
                color: #e0e0e0;
                titlebar-close-icon: none;
            }
            QDockWidget::title {
                background-color: #3c3c3c;
                padding: 6px;
                border: 1px solid #555555;
            }

            QDialog {
                background-color: #2b2b2b;
                color: #e0e0e0;
            }
        """

    def _get_light_stylesheet(self):
        return """
            QMainWindow, QWidget {
                background-color: #f5f5f5;
                color: #333333;
                font-size: 12px;
            }

            QMenuBar {
                background-color: #ffffff;
                color: #333333;
                border-bottom: 1px solid #cccccc;
            }
            QMenuBar::item {
                background: transparent;
                padding: 4px 10px;
            }
            QMenuBar::item:selected {
                background-color: #e0e0e0;
            }
            QMenu {
                background-color: #ffffff;
                color: #333333;
                border: 1px solid #cccccc;
            }
            QMenu::item {
                padding: 6px 20px;
            }
            QMenu::item:selected {
                background-color: #e0e0e0;
            }

            #sectionLabel {
                color: #666666;
                font-size: 11px;
                font-weight: bold;
                padding-bottom: 2px;
            }

            QGroupBox {
                background-color: #ffffff;
                border: 1px solid #cccccc;
                border-radius: 4px;
                margin-top: 12px;
                padding-top: 10px;
                font-weight: bold;
                color: #333333;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 6px;
                color: #333333;
            }

            QComboBox {
                background-color: #ffffff;
                border: 1px solid #cccccc;
                border-radius: 3px;
                padding: 4px 8px;
                color: #333333;
                min-height: 22px;
            }
            QComboBox:hover {
                border-color: #999999;
            }
            QComboBox:focus {
                border-color: #00bcd4;
            }
            QComboBox::drop-down {
                border: none;
                width: 18px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 4px solid #666666;
                margin-right: 4px;
            }
            QComboBox QAbstractItemView {
                background-color: #ffffff;
                color: #333333;
                selection-background-color: #e0e0e0;
                border: 1px solid #cccccc;
            }

            QSpinBox {
                background-color: #ffffff;
                border: 1px solid #cccccc;
                border-radius: 3px;
                padding: 4px 8px;
                color: #333333;
                min-height: 22px;
            }

            QPushButton {
                background-color: #ffffff;
                border: 1px solid #cccccc;
                border-radius: 3px;
                padding: 6px 12px;
                color: #333333;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #f0f0f0;
                border-color: #999999;
            }
            QPushButton:pressed {
                background-color: #e0e0e0;
            }
            QPushButton:disabled {
                background-color: #f5f5f5;
                color: #aaaaaa;
                border-color: #dddddd;
            }

            #btnConnect, #btnStart {
                background-color: #008EC0;
                color: #ffffff;
                border: 1px solid #007AA8;
            }
            #btnConnect:hover, #btnStart:hover {
                background-color: #0099D0;
            }
            #btnDisconnect, #btnStop {
                background-color: #DD8E6B;
                color: #ffffff;
                border: 1px solid #C47D5C;
            }
            #btnDisconnect:hover, #btnStop:hover {
                background-color: #E49E7E;
            }
            #btnConnect:disabled, #btnStart:disabled, #btnDisconnect:disabled, #btnStop:disabled {
                background-color: #f0f0f0;
                color: #aaaaaa;
                border-color: #dddddd;
            }

            QProgressBar {
                background-color: #e0e0e0;
                border: 1px solid #cccccc;
                border-radius: 3px;
                text-align: center;
                color: #333333;
            }
            QProgressBar::chunk {
                background-color: #909090;
                border-radius: 2px;
            }

            #statusIndicator {
                color: #888888;
                font-size: 14px;
            }

            #statusMessage {
                color: #333333;
                padding: 2px 4px;
            }

            #statusReadingLabel {
                color: #666666;
                font-size: 11px;
            }

            #statusReadingValue {
                color: #000000;
                font-weight: bold;
                font-size: 11px;
                min-width: 80px;
            }

            #statusSeparator {
                color: #cccccc;
            }

            #titleLabel {
                color: #333333;
                font-size: 14px;
                font-weight: bold;
                padding: 8px;
            }

            #plotsGroup {
                background-color: #ffffff;
                border: 1px solid #cccccc;
                border-radius: 4px;
                margin-top: 0px;
                padding: 4px;
            }

            QSplitter::handle {
                background-color: #d0d0d0;
            }
            QSplitter::handle:hover {
                background-color: #c0c0c0;
            }

            #dataValue {
                color: #000000;
                font-weight: bold;
            }

            QCheckBox {
                color: #333333;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 1px solid #cccccc;
                border-radius: 3px;
                background-color: #ffffff;
            }
            QCheckBox::indicator:checked {
                background-color: #00bcd4;
                border-color: #00bcd4;
            }

            QLabel {
                color: #333333;
                background: transparent;
            }

            QScrollBar:vertical {
                background-color: #f5f5f5;
                width: 10px;
            }
            QScrollBar::handle:vertical {
                background-color: #cccccc;
                border-radius: 5px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #aaaaaa;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
            }

            QTabWidget::pane {
                border: 1px solid #cccccc;
                border-radius: 4px;
                background-color: #ffffff;
            }
            QTabBar::tab {
                background-color: #e0e0e0;
                color: #333333;
                border: 1px solid #cccccc;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                padding: 8px 20px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #ffffff;
                border-bottom: 1px solid #ffffff;
            }
            QTabBar::tab:hover:!selected {
                background-color: #d0d0d0;
            }

            #systemLog {
                background-color: #ffffff;
                color: #555555;
                border: none;
                font-family: "SF Mono", "Menlo", "Consolas", monospace;
                font-size: 11px;
                padding: 12px;
            }

            QDockWidget {
                color: #333333;
            }
            QDockWidget::title {
                background-color: #e0e0e0;
                padding: 6px;
                border: 1px solid #cccccc;
            }

            QDialog {
                background-color: #f5f5f5;
                color: #333333;
            }
        """

    def get_current_theme(self):
        """Return the current theme name ('dark' or 'light')"""
        return self._current_theme

    def retranslateUi(self, MainWindow):
        MainWindow.setWindowTitle("openQCM Q-1 - Real-Time Monitor")
        MainWindow.setWindowIcon(QtGui.QIcon(get_resource_path('icons/favicon.ico')))
