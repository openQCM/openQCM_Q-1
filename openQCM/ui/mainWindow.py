"""
MainWindow — top-level controller of the openQCM Q-1 GUI.

Responsibilities:
    - Build and show the main window (delegated to `Ui_Main` for layout).
    - Spin up the Worker / acquisition processes on START, tear them down on STOP.
    - Drive the plot refresh QTimer that drains the Worker queues and updates
      the persistent pyqtgraph curves (frequency, dissipation, temperature,
      amplitude, phase).
    - Manage the serial port lock, the CSV log handle, dialog windows
      (Data View, Raw Data View, Peak Data View, Measurement Parameters)
      and the various menu actions (theme, cursors, firmware check, updates).
    - Implement the minimum Y-axis scale enforcement and the auto-tracking
      safety GUI feedback (Tracking Stopped / Tracking Resumed).

The heavy lifting (signal processing, peak detection, sweep acquisition)
lives in the child processes (`SerialProcess`, `CalibrationProcess`).
This file is mostly UI plumbing and event handling.
"""
import os
import sys
from datetime import datetime

import numpy as np
from PyQt5 import QtCore, QtGui, QtWidgets
from pyqtgraph import AxisItem
import pyqtgraph as pg

from openQCM.ui.mainWindow_ui import Ui_Main
from openQCM.ui.popUp import PopUp
from openQCM.ui.calibrationPlot import CalibrationPlotWindow
from openQCM.core.worker import Worker
from openQCM.core.constants import (
    Constants, SourceType,
    DateAxis, NonScientificAxis, OneDecimalAxis, ElapsedTimeAxis,
)
from openQCM.common.logger import Logger as Log
from openQCM.common.architecture import Architecture, OSType


TAG = ""  # set to "[MainWindow]" for verbose tagged prints

# Minimum Y-axis display ranges, used to prevent the autoscale from "exploding"
# stable noise across the whole plot when the signal is essentially flat.
# (Override at runtime via the easter-egg right-click on the brand logo.)
MIN_FREQ_RANGE = 100        # Hz
MIN_DISS_RANGE = 0.000001   # 1e-6 (provisional — see TODO.md, needs real-data tuning)
MIN_TEMP_RANGE = 2.0        # °C


class LogStream:
    """
    Stream-like adapter that mirrors stdout / stderr into a QTextEdit while
    still forwarding to the original terminal stream. Used to surface child
    process prints in the System Log tab of the GUI.
    """
    def __init__(self, text_widget, original_stream):
        self.text_widget = text_widget
        self.original_stream = original_stream

    def write(self, text):
        if self.original_stream:
            self.original_stream.write(text)
        # Skip carriage-return-only lines (used for in-place progress prints)
        if text and text.strip() and text != '\r':
            timestamp = datetime.now().strftime("[%H:%M:%S] ")
            # Cross-thread safe append via Qt's queued meta call
            QtCore.QMetaObject.invokeMethod(
                self.text_widget, "append",
                QtCore.Qt.QueuedConnection,
                QtCore.Q_ARG(str, timestamp + text.rstrip()),
            )

    def flush(self):
        if self.original_stream:
            self.original_stream.flush()


def _set_data_value(widget, value):
    """Set a value on a sidebar data row (works with both compound and plain widgets)."""
    if hasattr(widget, 'valueLabel'):
        widget.valueLabel.setText(str(value))
    elif hasattr(widget, 'setText'):
        widget.setText(str(value))


def _extract_value(html_text):
    """Strip the leading HTML label (e.g. '<font color=...>Frequency</font> 1234')."""
    if '>' in html_text and '</font>' in html_text:
        parts = html_text.split('</font>')
        if len(parts) > 1:
            return parts[-1].strip()
    return html_text


class MainWindow(QtGui.QMainWindow):

    def __init__(self, samples=Constants.argument_default_samples):
        """
        :param samples: default samples per sweep used for the initial sidebar value
        """
        QtGui.QMainWindow.__init__(self)

        self.ui = Ui_Main()
        self.ui.setupUi(self)
        self.show()

        # Mirror stdout / stderr into the System Log tab so child-process prints
        # surface in the GUI alongside terminal output.
        self._original_stdout = sys.stdout
        self._original_stderr = sys.stderr
        sys.stdout = LogStream(self.ui.systemLog, self._original_stdout)
        sys.stderr = LogStream(self.ui.systemLog, self._original_stderr)
        print("System Log initialized - openQCM Q-1 Real-Time Monitor")

        # Shared variables, initial values
        self._plt0 = None
        self._plt1 = None
        self._plt2 = None
        self._plt3 = None
        self._plt4 = None
        self._timer_plot = None
        self._readFREQ = None
        self._QCS_installed = None
        self._ser_control = 0
        self._ser_error1 = 0
        self._ser_error2 = 0
        self._ser_err_usb= 0

        # Persistent pyqtgraph curve handles. Created once in `_configure_plot()`
        # and updated via setData() in `_update_plot()` to avoid the overhead of
        # rebuilding the plot scene on every timer tick.
        self._curve_amplitude = None      # plt0 — Amplitude vs frequency
        self._curve_phase = None          # plt1 — Phase vs frequency (twin Y)
        self._curve_frequency = None      # plt2 — Resonance frequency vs time
        self._curve_dissipation = None    # plt3 — Dissipation vs time (twin Y)
        self._curve_temperature = None    # plt4 — Temperature vs time

        # Theme-dependent curve colors (amplitude / temperature flip with theme)
        self._theme_amp_color = '#ffffff'   # white in dark mode (default)
        self._theme_temp_color = None

        # Resize debouncing: pause plot updates while the user drags the window
        # edge, then re-enable them after a short timeout (smoother resize).
        self._is_resizing = False
        self._resize_timer = QtCore.QTimer()
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._on_resize_finished)

        self._internet_connected = False

        # Serial connection state. The Connect / Disconnect button explicitly
        # opens and closes the port; the port is kept locked until Disconnect
        # is pressed, independent of the measurement mode.
        self._serial_connected = False
        self._connected_port = None
        self._serial_lock = None
        self._lock_file = None

        # Minimum Y-axis scale enforcement (prevents noise explosion on stable signals)
        self._min_scale_enabled = True

        # Reference variables
        self._reference_flag = False
        self._vector_reference_frequency = None
        self._vector_reference_dissipation = None
        self._vector_1 = None
        self._vector_2 = None

        # Auto-tracking persistent state (carried between sweeps)
        self._tracking_stopped_active = False

        # Instantiates a Worker class
        self.worker = Worker()

        # Populates comboBox for sources
        self.ui.cBox_Source.addItems(Constants.app_sources)

        # Configures specific elements of the PyQtGraph plots
        self._configure_plot()

        # Configures specific elements of the QTimers
        self._configure_timers()

        # Configures the connections between signals and UI elements
        self._configure_signals()

        # Populates combo box for serial ports
        self._source_changed()
        self.ui.cBox_Source.setCurrentIndex(SourceType.calibration.value)
        self.ui.sBox_Samples.setValue(samples)  #samples

        # enable ui
        self._enable_ui(True)
        # Set initial status indicator to gray (disconnected)
        self.ui.set_connection_state(False)
        self.ui.infostatus.setText("Disconnected")
        self.ui.infobar.setText("Select a port and click Connect")
        ###################################################################################################################################
        self.get_web_info()
        # Gets the QCS installed on the device (not used now)
        # self._QCS_installed = PopUp.question_QCM(self, Constants.app_title, "Please choose the Quartz Crystal Resonator installed on the openQCM-1 Device (default 5MHz if exit)")

    ###########################################################################
    # Starts the acquisition of the selected serial port
    ###########################################################################
    def start(self):

        import os
        os.system('cls' if os.name == 'nt' else 'clear')

        # This function is connected to the clicked signal of the Start button.
        print(TAG, 'Clicked START')
        Log.i(TAG, "Clicked START")

        # Check if serial is connected
        if not self._serial_connected:
            PopUp.warning(self, Constants.app_title,
                "Serial port not connected!\nPlease click Connect first.")
            return

        # Use the connected port
        port = self._connected_port

        # Release serial lock so the child process can access the port.
        # On Windows, COM ports are truly exclusive — only one handle can open them.
        # The lock will be reacquired in stop() after the process terminates.
        if self._serial_lock is not None and self._serial_lock.isOpen():
            self._serial_lock.close()
            print(TAG, "Serial lock released for acquisition")

        # Instantiates process
        # In calibration mode, use "Auto" for auto-detection of QCM type
        if self._get_source() == SourceType.calibration:
            speed_value = "Auto"
        else:
            speed_value = self.ui.cBox_Speed.currentText()

        self.worker = Worker(QCS_on = self._QCS_installed,
                             port = port,
                             speed = speed_value,
                             samples = self.ui.sBox_Samples.value(),
                             source = self._get_source(),
                             export_enabled = self.ui.chBox_export.isChecked())

        if self.worker.start():
            # Gets frequency range 
            self._readFREQ = self.worker.get_frequency_range()
            # Duplicate frequencies
            self._reference_flag = False
            self._vector_reference_frequency = list(self._readFREQ)
            self._reference_value_frequency = 0
            self._reference_value_dissipation = 0
            self._labelref1 = "not set"
            self._labelref2 = "not set"
            # progressbar variables
            self._completed=0
            self._ser_control = 0
            # error variables
            self._ser_error1 = 0
            self._ser_error2 = 0
            self._ser_err_usb= 0
            ##### other useful location #########
            #self.get_web_info()
            #####

            if self._get_source() == SourceType.serial:
                # Infer the QCM sensor type from the highest peak frequency listed
                # in PeakFrequencies.txt (last item, since the list is sorted desc).
                speeds = self.worker.get_source_speeds(SourceType.serial)
                overtones_number = len(speeds)
                top_freq = float(speeds[overtones_number - 1])
                if 4e6 < top_freq < 6e6:
                    label_quartz = "5 MHz QCM"
                elif 9e6 < top_freq < 11e6:
                    label_quartz = "10 MHz QCM"


                _set_data_value(self.ui.info1a, label_quartz)
                label11= "Measurement openQCM Q-1"
                _set_data_value(self.ui.info11, label11)
                self._overtone_name,self._overtone_value, self._fStep = self.worker.get_overtone()
                label6= str(int(self._overtone_value))+" Hz"
                _set_data_value(self.ui.info6, label6)
                label2= str(self._overtone_name)
                _set_data_value(self.ui.info2, label2)
                label3= str(int(self._readFREQ[0]))+" Hz"
                _set_data_value(self.ui.info3, label3)
                label4= str(int(self._readFREQ[-1]))+" Hz"
                _set_data_value(self.ui.info4, label4)
                label4a= str(int(self._readFREQ[-1]-self._readFREQ[0]))+" Hz"
                _set_data_value(self.ui.info4a, label4a)
                label5= str(int(self._fStep))+" Hz"
                _set_data_value(self.ui.info5, label5)
                label7= str(Constants.argument_default_samples-1)
                _set_data_value(self.ui.info7, label7)
                                     
            elif self._get_source() == SourceType.calibration:
                label_quartz = "QCM Auto-detect"
                _set_data_value(self.ui.info1a, label_quartz)
                label11= "Peak Detection openQCM Q-1"
                _set_data_value(self.ui.info11, label11)
                label6= "Overall Frequency Range"
                _set_data_value(self.ui.info6, label6)
                label2= "Overall Frequency Range"
                _set_data_value(self.ui.info2, label2)
                label3= str(Constants.calibration_frequency_start)+" Hz"
                _set_data_value(self.ui.info3, label3)
                label4= str(Constants.calibration_frequency_stop)+" Hz"
                _set_data_value(self.ui.info4, label4)
                label4a= str(int(Constants.calibration_frequency_stop - Constants.calibration_frequency_start))+" Hz"
                _set_data_value(self.ui.info4a, label4a)
                label5= str(int(Constants.calibration_fStep))+" Hz"
                _set_data_value(self.ui.info5, label5)
                label7= str(Constants.calibration_default_samples-1)
                _set_data_value(self.ui.info7, label7)  
            #
            # Reset elapsed time axes to start from 0
            self._xaxis.reset_start_time()
            self._xaxis_temp.reset_start_time()

            self._timer_plot.start(Constants.plot_update_ms)
            # Disconnect any previous connection to avoid double-firing on restart
            try:
                self._timer_plot.timeout.disconnect(self._update_plot)
            except TypeError:
                pass  # Not connected yet (first start)
            self._timer_plot.timeout.connect(self._update_plot)
            self._is_running = True
            self.ui.pButton_StartStop.setText("STOP")
            self._set_button_role(self.ui.pButton_StartStop, "btnStop")
            self.ui.pButton_Autoscale.setEnabled(True)
            self._enable_ui(False)
            self.ui.sBox_Samples.setEnabled(False) #insert

            # Show current log filename (elided in sidebar, full in title bar + tooltip)
            if self._get_source() == SourceType.serial:
                csv_name = "{}_{}.csv".format(self.worker._csv_filename, self.worker._overtone_name)
                lbl = self.ui.lblLogFile
                metrics = lbl.fontMetrics()
                avail = lbl.width() if lbl.width() > 20 else 120
                elided = metrics.elidedText(csv_name, QtCore.Qt.ElideMiddle, avail)
                lbl.setText(elided)
                lbl.setToolTip(csv_name)
                self.setWindowTitle("openQCM Q-1 v3.0 \u2014 {}".format(csv_name))

            if self._get_source() == SourceType.calibration:
               self.ui.pButton_Clear.setEnabled(False) #insert
               self.ui.pButton_Reference.setEnabled(False) #insert
        else:
            print(TAG, "Warning: port is not available!")
            Log.i(TAG, "Warning: port is not available")
            PopUp.warning(self, Constants.app_title, "Warning: Selected Port [{}] is not available!".format(self.ui.cBox_Port.currentText()))

        
    ###########################################################################
    # Stops the acquisition of the selected serial port
    ###########################################################################    
    def stop(self):

        # This function is connected to the clicked signal of the Stop button.
        # Update status to yellow (connected + standby) since serial is still connected
        self.ui.set_connection_state(True)
        self.ui.infostatus.setText("Standby")
        self.ui.infostatus.setStyleSheet('background: #ffff00; padding: 1px; border: 1px solid #cccccc')
        self.ui.infobar.setText("Acquisition stopped")
        self.ui.infobar.setStyleSheet('')
        _set_data_value(self.ui.inforef1, "not set")
        _set_data_value(self.ui.inforef2, "not set")
        # Reset status bar readings
        _set_data_value(self.ui.l6b, "---")
        self.ui.update_status_bar_readings(frequency="---", dissipation="---", temperature="---", sampling_time="---")
        # Clear log filename
        self.ui.lblLogFile.setText("")
        self.ui.lblLogFile.setToolTip("")
        self.setWindowTitle("openQCM Q-1 - version 3.0 (dev)")
        # Reset reference button label
        self.ui.pButton_Reference.setText("Set Reference")
        print("")
        print(TAG, "Clicked STOP")
        Log.i(TAG, "Clicked STOP")
        self._timer_plot.stop()
        self._is_running = False
        self.ui.pButton_StartStop.setText("START")
        self._set_button_role(self.ui.pButton_StartStop, "btnStart")
        self.ui.pButton_Autoscale.setEnabled(False)
        self._enable_ui(True)
        self.worker.stop()
        # Wait for process to terminate and reacquire serial lock
        self._finalize_acquisition_stop()

    ###########################################################################
    # Overrides the QTCloseEvent,is connected to the close button of the window
    ###########################################################################
    def closeEvent(self, evnt):
        """Override Qt's close handler to confirm shutdown and tear down resources."""
        # Prevent the dialog from popping up twice if Qt fires closeEvent again
        if hasattr(self, '_is_closing') and self._is_closing:
            evnt.accept()
            return

        res = PopUp.question(self, Constants.app_title, "Are you sure you want to quit openQCM application now?")
        if res:
            self._is_closing = True  # Set flag to prevent second dialog
            if self.worker.is_running():
                print(TAG, 'Window closed without stopping the capture, application will stop...')
                Log.i(TAG, "Window closed without stopping the capture, application will stop...")
                self.stop()
            # Release serial port and lock file on exit
            if self._serial_lock is not None:
                try:
                    self._serial_lock.close()
                    print(TAG, "Serial port closed on exit")
                    Log.i(TAG, "Serial port closed on exit")
                except Exception as e:
                    print(TAG, "Warning: Error closing serial port on exit: {}".format(str(e)))
                self._serial_lock = None
            # Release the lock file
            self._release_port_lock()
            # Close child dialogs
            for dlg in [getattr(self, '_data_viewer', None),
                        getattr(self, '_raw_data_viewer', None),
                        getattr(self, '_calib_plot_window', None),
                        getattr(self.ui, 'deviceInfoDialog', None)]:
                if dlg is not None:
                    dlg.close()
            evnt.accept()
        else:
            evnt.ignore()
    
          
    ###########################################################################
    # Enables or disables the UI elements of the window.
    ###########################################################################
    def _enable_ui(self, enabled):
        """
        Enable / disable the configuration widgets while acquisition runs.

        :param enabled: target enabled state (True before START, False during acquisition)
        """
        # Port and Refresh widgets are gated by the Connect button: they
        # remain disabled while the port is locked, regardless of `enabled`.
        if not self._serial_connected:
            self.ui.cBox_Port.setEnabled(enabled)
            self.ui.pButton_Refresh.setEnabled(enabled)
        self.ui.cBox_Speed.setEnabled(enabled)
        # Overtone buttons: enable/disable only those that were calibrated
        for label, btn in self.ui.overtone_buttons.items():
            if enabled:
                btn.setEnabled(btn.property('calibrated') == True)
            else:
                btn.setEnabled(False)
        self.ui.pButton_StartStop.setEnabled(self._serial_connected)
        self.ui.chBox_export.setEnabled(enabled)
        self.ui.cBox_Source.setEnabled(enabled)
        self.ui.pButton_Connect.setEnabled(enabled)
        self.ui.sBox_Samples.setEnabled(not enabled) #insert
        self.ui.pButton_Clear.setEnabled(not enabled)
        self.ui.pButton_Reference.setEnabled(not enabled)


    ###########################################################################
    # Waits for acquisition process to terminate and reacquires serial lock.
    # Called after stop() for both Measurement and Peak Detection modes.
    ###########################################################################
    def _finalize_acquisition_stop(self):
        """
        After signaling the acquisition process to stop, this method:
        1. Waits for the process to actually terminate (max 5s, then force-kill)
        2. Reacquires _serial_lock so the port is protected for the next start
        """
        import serial
        # Wait for the process to fully terminate
        self.worker.wait_for_process(timeout=5.0)

        # Reacquire serial lock if we're still connected
        if self._serial_connected and self._connected_port:
            if self._serial_lock is None or not self._serial_lock.isOpen():
                try:
                    try:
                        self._serial_lock = serial.Serial(self._connected_port, timeout=1, exclusive=True)
                    except TypeError:
                        self._serial_lock = serial.Serial(self._connected_port, timeout=1)
                    print(TAG, "Serial lock reacquired after acquisition")
                    Log.i(TAG, "Serial lock reacquired after acquisition")
                except serial.SerialException as e:
                    print(TAG, "WARNING: Failed to reacquire serial lock: {}".format(str(e)))
                    Log.w(TAG, "Failed to reacquire serial lock: {}".format(str(e)))

    ###########################################################################
    # Sets button objectName and refreshes stylesheet to match the new role.
    ###########################################################################
    def _set_button_role(self, button, role):
        button.setObjectName(role)
        button.style().unpolish(button)
        button.style().polish(button)

    ###########################################################################
    # Configures specific elements of the PyQtGraph plots.
    ###########################################################################
    def _configure_plot(self):

        #----------------------------------------------------------------------
        # set background color (dark theme)
        self.ui.plt.setBackground(background='#2b2b2b')
        self.ui.pltB.setBackground(background='#2b2b2b')

        #----------------------------------------------------------------------
        # Standardized axis styling - white color for dark theme (default)
        axis_color = '#ffffff'  # White for axes in dark mode
        axis_pen = pg.mkPen(color=axis_color, width=1)

        #----------------------------------------------------------------------
        # defines the graph title
        title1 = "Amplitude / Phase"
        title2 = "Resonance Frequency / Dissipation"
        title3 = "Temperature"
        #--------------------------------------------------------------------------------------------------------------
        # Configures elements of the PyQtGraph plots: amplitude
        self.ui.plt.setAntialiasing(True)
        self.ui.pltB.setAntialiasing(True)

        self._xaxis_sweep = NonScientificAxis(orientation='bottom')
        self._xaxis_sweep.enableAutoSIPrefix(False)
        self._xaxis_sweep.setPen(axis_pen)
        self._xaxis_sweep.setTextPen(axis_color)

        self._plt0 = self.ui.plt.addPlot(row=0, col=1, title=title1, axisItems={"bottom": self._xaxis_sweep})
        # Grid disabled for cleaner appearance
        self._plt0.showGrid(x=False, y=False)
        self._plt0.setLabel('bottom', 'Frequency', units='Hz', color=axis_color)
        self._plt0.setLabel('left', 'Amplitude', units='dB', color=axis_color)
        # Standardize axis appearance
        self._plt0.getAxis('left').setPen(axis_pen)
        self._plt0.getAxis('left').setTextPen(axis_color)
        # Set title color to white for dark mode
        self._plt0.setTitle(title1, color='#ffffff')

        #--------------------------------------------------------------------------------------------------------------
        # Configures elements of the PyQtGraph plots: Multiple Plot amplitude and phase
        self._plt1 = pg.ViewBox()
        self._plt0.showAxis('right')
        self._plt0.scene().addItem(self._plt1)
        self._plt0.getAxis('right').linkToView(self._plt1)
        self._plt1.setXLink(self._plt0)
        self._plt0.enableAutoRange(axis='y', enable=True)
        self._plt1.enableAutoRange(axis='y', enable=True)
        self._plt0.setLabel('right', 'Phase', units='deg', color=axis_color)
        self._plt0.getAxis('right').setPen(axis_pen)
        self._plt0.getAxis('right').setTextPen(axis_color)

        # Add legend for Amplitude/Phase plot
        self._legend0 = self._plt0.addLegend(offset=(10, 10))
        self._legend0.setBrush(pg.mkBrush('#3c3c3c80'))
        self._legend0.setPen(pg.mkPen('#555555'))

        #--------------------------------------------------------------------------------------------------------------
        # Configures elements of the PyQtGraph plots: resonance
        self._yaxis = NonScientificAxis(orientation='left')
        self._yaxis.enableAutoSIPrefix(False)
        self._yaxis.setPen(axis_pen)
        self._yaxis.setTextPen(axis_color)
        #self._yaxis.setTickSpacing(levels=[(280, 0),(25, 0), (10, 0)]) #(20,1, None)
        self._xaxis = ElapsedTimeAxis(orientation='bottom')  # Elapsed time in seconds
        self._xaxis.enableAutoSIPrefix(False)  # Disable auto SI prefix (removes x1e+15)
        self._xaxis.setPen(axis_pen)
        self._xaxis.setTextPen(axis_color)
        self._plt2 = self.ui.pltB.addPlot(row=0, col=2, title=title2, axisItems={"bottom": self._xaxis, 'left': self._yaxis})
        # Grid disabled for cleaner appearance
        self._plt2.showGrid(x=False, y=False)
        self._plt2.setLabel('bottom', 'Time (hh:mm:ss)', units='', color=axis_color)
        self._plt2.setLabel('left', 'Resonance Frequency', units='Hz', color=axis_color)
        # Set title color to white for dark mode
        self._plt2.setTitle(title2, color='#ffffff')

        #--------------------------------------------------------------------------------------------------------------
        # Configures elements of the PyQtGraph plots: Multiple Plot resonance frequency and dissipation
        self._plt3 = pg.ViewBox()
        self._plt2.showAxis('right')
        self._plt2.scene().addItem(self._plt3)
        self._plt2.getAxis('right').linkToView(self._plt3)
        self._plt3.setXLink(self._plt2)
        self._plt2.enableAutoRange(axis='y', enable=True)
        self._plt3.enableAutoRange(axis='y', enable=True)
        self._plt2.setLabel('bottom', 'Time (hh:mm:ss)', units='', color=axis_color)
        self._plt2.setLabel('right', 'Dissipation', units='', color=axis_color)
        self._plt2.getAxis('right').setPen(axis_pen)
        self._plt2.getAxis('right').setTextPen(axis_color)

        # Add legend for Frequency/Dissipation plot
        self._legend2 = self._plt2.addLegend(offset=(10, 10))
        self._legend2.setBrush(pg.mkBrush('#3c3c3c80'))
        self._legend2.setPen(pg.mkPen('#555555'))

        #-----------------------------------------------------------------------------------------------------------------
        # Configures elements of the PyQtGraph plots: temperature
        self._xaxis_temp = ElapsedTimeAxis(orientation='bottom')  # Elapsed time in seconds
        self._xaxis_temp.enableAutoSIPrefix(False)  # Disable auto SI prefix (removes x1e+15)
        self._xaxis_temp.setPen(axis_pen)
        self._xaxis_temp.setTextPen(axis_color)
        # Y-axis for temperature with one decimal place
        self._yaxis_temp = OneDecimalAxis(orientation='left')
        self._yaxis_temp.setPen(axis_pen)
        self._yaxis_temp.setTextPen(axis_color)
        self._plt4 = self.ui.plt.addPlot(row=0, col=3, title=title3, axisItems={'bottom': self._xaxis_temp, 'left': self._yaxis_temp})
        # Grid disabled for cleaner appearance
        self._plt4.showGrid(x=False, y=False)
        self._plt4.setLabel('bottom', 'Time (hh:mm:ss)', units='', color=axis_color)
        self._plt4.setLabel('left', 'Temperature', units='°C', color=axis_color)
        # Set title color to white for dark mode
        self._plt4.setTitle(title3, color='#ffffff')

        # Add legend for Temperature plot
        self._legend4 = self._plt4.addLegend(offset=(10, 10))
        self._legend4.setBrush(pg.mkBrush('#3c3c3c80'))
        self._legend4.setPen(pg.mkPen('#555555'))

        # =============================================================================
        # CPU OPTIMIZATION: Create persistent curve objects once at initialization
        # These curves are reused with setData() in _update_plot() instead of being
        # recreated on every timer tick, which dramatically reduces CPU overhead.
        # =============================================================================
        # Amplitude curve — white (dark mode) / black (light mode)
        self._curve_amplitude = self._plt0.plot(pen='#ffffff', name='Amplitude')
        # Phase curve — same blue as Frequency (#008EC0)
        self._curve_phase = pg.PlotCurveItem(pen='#008EC0', name='Phase')
        self._plt1.addItem(self._curve_phase)
        self._legend0.addItem(self._curve_phase, 'Phase')
        # Resonance frequency curve (color changes based on reference flag)
        self._curve_frequency = self._plt2.plot(pen=Constants.plot_colors[2], name='Frequency')
        # Dissipation curve (ViewBox item, color changes based on reference flag)
        self._curve_dissipation = pg.PlotCurveItem(pen=Constants.plot_colors[3], name='Dissipation')
        self._legend2.addItem(self._curve_dissipation, 'Dissipation')
        self._plt3.addItem(self._curve_dissipation)
        # Temperature curve - white for dark mode (default)
        self._curve_temperature = self._plt4.plot(pen='#ffffff', name='Temperature')

        # =============================================================================
        # CPU OPTIMIZATION: Connect ViewBox resize signals ONCE at initialization
        # Previously these were connected inside _update_plot() on every timer tick,
        # causing signal handler accumulation (memory leak) and severe performance issues.
        # =============================================================================
        def updateViews1():
            """Sync Phase ViewBox geometry with Amplitude plot"""
            self._plt1.setGeometry(self._plt0.vb.sceneBoundingRect())
            self._plt1.linkedViewChanged(self._plt0.vb, self._plt1.XAxis)

        def updateViews2():
            """Sync Dissipation ViewBox geometry with Frequency plot"""
            self._plt3.setGeometry(self._plt2.vb.sceneBoundingRect())
            self._plt3.linkedViewChanged(self._plt2.vb, self._plt3.XAxis)

        # Connect signals once - these handle resize synchronization for dual-axis plots
        self._plt0.vb.sigResized.connect(updateViews1)
        self._plt2.vb.sigResized.connect(updateViews2)
        # Initial sync
        updateViews1()
        updateViews2()

        # =============================================================================
        # CUSTOM RIGHT-CLICK CONTEXT MENU
        # Disable default pyqtgraph menu and implement custom context menu with:
        # Auto-scale, Reset Zoom, Pan Mode, Select Mode
        # =============================================================================
        # Disable default context menus on all plot items AND their ViewBoxes
        # _plt0 = Amplitude plot (main), _plt1 = Phase ViewBox (secondary)
        # _plt2 = Frequency plot (main), _plt3 = Dissipation ViewBox (secondary)
        # _plt4 = Temperature plot (single)
        self._plt0.setMenuEnabled(False)
        self._plt0.getViewBox().setMenuEnabled(False)
        self._plt1.setMenuEnabled(False)  # Secondary ViewBox for Phase
        self._plt2.setMenuEnabled(False)
        self._plt2.getViewBox().setMenuEnabled(False)
        self._plt3.setMenuEnabled(False)  # Secondary ViewBox for Dissipation
        self._plt4.setMenuEnabled(False)
        self._plt4.getViewBox().setMenuEnabled(False)

        # Connect right-click signals to custom handler
        self._plt0.scene().sigMouseClicked.connect(
            lambda ev: self._on_plot_right_click(self._plt0, ev)
        )
        self._plt2.scene().sigMouseClicked.connect(
            lambda ev: self._on_plot_right_click(self._plt2, ev)
        )
        self._plt4.scene().sigMouseClicked.connect(
            lambda ev: self._on_plot_right_click(self._plt4, ev)
        )

        # =============================================================================
        # CURSORS: Double vertical cursors for Frequency/Dissipation plot
        # Used to measure ΔTime, ΔFrequency, ΔDissipation between two points
        # =============================================================================
        self._cursors_visible = False

        # Cursor 1 (left) - Soft yellow
        self._cursor1 = pg.InfiniteLine(
            pos=0, angle=90, movable=True,
            pen=pg.mkPen('#d4c85c', width=1.5, style=QtCore.Qt.DashLine),
            hoverPen=pg.mkPen('#e8dc6a', width=2.5),
            label='C1', labelOpts={'position': 0.95, 'color': '#d4c85c', 'fill': '#2b2b2b80'}
        )
        # Prevent cursor from affecting Y-axis autoscale
        self._cursor1.dataBounds = lambda *args, **kwargs: [None, None]
        self._cursor1.sigPositionChanged.connect(self._on_cursor_moved)

        # Cursor 2 (right) - Soft green
        self._cursor2 = pg.InfiniteLine(
            pos=0, angle=90, movable=True,
            pen=pg.mkPen('#6abf7b', width=1.5, style=QtCore.Qt.DashLine),
            hoverPen=pg.mkPen('#82d494', width=2.5),
            label='C2', labelOpts={'position': 0.95, 'color': '#6abf7b', 'fill': '#2b2b2b80'}
        )
        # Prevent cursor from affecting Y-axis autoscale
        self._cursor2.dataBounds = lambda *args, **kwargs: [None, None]
        self._cursor2.sigPositionChanged.connect(self._on_cursor_moved)

        # Delta text label (shows ΔTime, ΔFrequency, ΔDissipation)
        # Uses ViewBox as parent so it stays fixed at top-left corner in pixel coords
        self._cursor_delta_text = pg.TextItem(
            '', anchor=(0, 0), color='#ffffff',
            fill=pg.mkBrush('#2b2b2bcc'), border=pg.mkPen('#55555580')
        )
        self._cursor_delta_text.setFont(QtGui.QFont('Arial', 12, QtGui.QFont.Bold))
        # Will be parented to ViewBox for fixed pixel positioning

        # Individual cursor value labels
        self._cursor1_text = pg.TextItem('', anchor=(0, 0), color='#d4c85c')
        self._cursor1_text.setFont(QtGui.QFont('Arial', 9))
        self._cursor2_text = pg.TextItem('', anchor=(0, 0), color='#6abf7b')
        self._cursor2_text.setFont(QtGui.QFont('Arial', 9))


    ###########################################################################
    # Configures specific elements of the QTimers
    ########################################################################### 
    def _configure_timers(self):
        
        self._timer_plot = QtCore.QTimer(self)
        #self._timer_plot.timeout.connect(self._update_plot) #moved to start method

    
    ###########################################################################
    # Configures the connections between signals and UI elements
    ###########################################################################
    def _configure_signals(self):

        self._is_running = False
        self.ui.pButton_StartStop.clicked.connect(self._toggle_start_stop)
        self.ui.pButton_Clear.clicked.connect(self.clear)
        self.ui.pButton_Reference.clicked.connect(self.reference)
        self.ui.pButton_Autoscale.clicked.connect(self.autoscale)
        self.ui.sBox_Samples.valueChanged.connect(self._update_sample_size)
        self.ui.cBox_Source.currentIndexChanged.connect(self._source_changed)
        #--------
        # Serial port refresh and connect/disconnect
        self.ui.pButton_Refresh.clicked.connect(self._refresh_ports)
        self.ui.pButton_Connect.clicked.connect(self._toggle_serial_connection)
        #--------
        self.ui.pButton_Download.clicked.connect(self.start_download)
        #--------
        # Theme switching
        self.ui.actionDarkTheme.triggered.connect(lambda: self._switch_theme('dark'))
        self.ui.actionLightTheme.triggered.connect(lambda: self._switch_theme('light'))
        #--------
        # Help menu actions (Firmware Check, Check for Updates, Download Update)
        self.ui.actionFirmwareCheck.triggered.connect(lambda: self._check_firmware_version(auto_mode=False))
        self.ui.actionCheckUpdates.triggered.connect(self._check_for_updates)
        self.ui.actionDownloadUpdate.triggered.connect(self.start_download)
        #--------
        # Cursors toggle (View menu)
        self.ui.actionToggleCursors.triggered.connect(self._toggle_cursors)
        #--------
        # Data menu actions
        self.ui.actionDataView.triggered.connect(self._open_data_viewer)
        self.ui.actionRawDataView.triggered.connect(self._open_raw_data_viewer)
        self.ui.actionPeakDataView.triggered.connect(self._open_peak_data_viewer)
        #--------
        # Overtone quick-select buttons
        for label, btn in self.ui.overtone_buttons.items():
            btn.clicked.connect(lambda checked, l=label: self._on_overtone_button_clicked(l))
        self.ui.cBox_Speed.currentIndexChanged.connect(self._sync_overtone_buttons)
        #--------
        # Easter egg: right-click on logo to unlock/lock axis limits
        self.ui.lblLogo.customContextMenuRequested.connect(self._on_logo_context_menu)

    ###########################################################################
    # Toggle START / STOP
    ###########################################################################
    def _toggle_start_stop(self):
        if self._is_running:
            self.stop()
        else:
            self.start()

    ###########################################################################
    # Custom right-click context menu handler for plots
    ###########################################################################
    def _on_plot_right_click(self, plot, event):
        """
        Handle right-click on plot to show custom context menu.
        Menu options: Auto-scale, Reset Zoom, Pan Mode, Select Mode
        For Frequency/Dissipation plot: also Show/Hide Cursors
        """
        if event.button() == QtCore.Qt.RightButton:
            # Create context menu
            menu = QtWidgets.QMenu()

            # Add menu actions
            auto_scale_action = menu.addAction("Auto-scale")
            reset_zoom_action = menu.addAction("Reset Zoom")
            menu.addSeparator()
            pan_mode_action = menu.addAction("Pan Mode")
            select_mode_action = menu.addAction("Select Mode")

            # Add Cursors option only for Frequency/Dissipation plot (_plt2)
            cursor_action = None
            if plot == self._plt2:
                menu.addSeparator()
                if self._cursors_visible:
                    cursor_action = menu.addAction("Hide Cursors")
                else:
                    cursor_action = menu.addAction("Show Cursors")

            # Show menu at mouse position
            pos = event.screenPos()
            qpos = QtCore.QPoint(int(pos.x()), int(pos.y()))
            action = menu.exec_(qpos)

            # Handle selected action
            if action == auto_scale_action:
                # Enable auto-range on both axes
                plot.enableAutoRange()
            elif action == reset_zoom_action:
                # Reset to show all data
                plot.getViewBox().autoRange()
            elif action == pan_mode_action:
                # Set mouse to pan mode (drag to move)
                plot.getViewBox().setMouseMode(pg.ViewBox.PanMode)
            elif action == select_mode_action:
                # Set mouse to rect/select mode (drag to zoom)
                plot.getViewBox().setMouseMode(pg.ViewBox.RectMode)
            elif cursor_action is not None and action == cursor_action:
                # Toggle cursors
                self._toggle_cursors(not self._cursors_visible)

            event.accept()

    ###########################################################################
    # Updates the sample size of the plot (now not used)
    ########################################################################### 
    def _update_sample_size(self):

        # This function is connected to the valueChanged signal of the sample Spin Box.
        if self.worker is not None:
            #Log.i(TAG, "Changing sample size")
            self.worker.reset_buffers(self.ui.sBox_Samples.value())

    
    ###########################################################################
    # Updates and redraws the graphics in the plot.
    ###########################################################################
    def _update_plot(self):

        # This function is connected to the timeout signal of a QTimer
        # Always consume queues to prevent buffer overflow, even during resize
        self.worker.consume_queue1()
        self.worker.consume_queue2()
        self.worker.consume_queue3()
        self.worker.consume_queue4()
        self.worker.consume_queue5()
        self.worker.consume_queue6()
        self.worker.consume_queue_tracking()

        # AUTO-TRACKING: Check for tracking updates and update X-axis if needed
        self._handle_auto_tracking()

        # =============================================================================
        # RESIZE OPTIMIZATION: Skip plot drawing during resize to prevent GUI lag
        # Data is still consumed above to prevent queue overflow
        # =============================================================================
        if self._is_resizing:
            return 
        
        # MEASUREMENT: dynamic frequency and dissipation labels at run-time
        ###################################################################
        if  self._get_source() == SourceType.serial:
            vector1 = self.worker.get_d1_buffer()
            vector2 = self.worker.get_d2_buffer()
            vectortemp = self.worker.get_d3_buffer()
            self._ser_error1,self._ser_error2, self._ser_control,self._ser_err_usb = self.worker.get_ser_error()
            _sampling_time_s = self.worker.get_sampling_time()
            if vector1.any:
               # progressbar
               if self._ser_control<=Constants.environment:
                  self._completed = self._ser_control*2

               if str(vector1[0])=='nan' and not self._ser_error1 and not self._ser_error2:
                  label1 = 'processing...'
                  label2 = 'processing...'
                  label3 = 'processing...' 
                  labelstatus = 'Processing'
                  self.ui.infostatus.setStyleSheet('background: #ffff00; padding: 1px; border: 1px solid #cccccc') #ff8000
                  color_err = '#000000'   
                  labelbar = 'Please wait, processing early data...'

               elif (str(vector1[0])=='nan' and (self._ser_error1 or self._ser_error2)):
                      label1= ""
                      label2= ""
                      label3= ""
                      labelstatus = 'Warning'
                      color_err = '#ff0000'
                      self.ui.infostatus.setStyleSheet('background: #ff0000; padding: 1px; border: 1px solid #cccccc')
                      if self._ser_error1 and self._ser_error2:
                        labelbar = 'Warning: lower and upper cut-off not found'
                      elif self._ser_error1:
                        labelbar = 'Warning: lower cut-off not found'
                      elif self._ser_error2:
                        labelbar = 'Warning: upper cut-off not found'
                      if self._tracking_stopped_active:
                          labelstatus = 'Tracking Stopped'
                          labelbar += ' — Auto-tracking stopped'
               else:
                  if not self._ser_error1 and not self._ser_error2:
                      if not self._reference_flag:
                          d1=float("{0:.1f}".format(vector1[0]))
                          d2=float("{0:.1f}".format(vector2[0]*1e6))
                          d3=float("{0:.1f}".format(vectortemp[0]))
                      else:
                          a1= vector1[0]-self._reference_value_frequency
                          a2= vector2[0]-self._reference_value_dissipation
                          d1=float("{0:.1f}".format(a1))
                          d2=float("{0:.1f}".format(a2*1e6))
                          d3=float("{0:.1f}".format(vectortemp[0]))
                      label1= str(d1)+ " Hz"
                      label2= str(d2)+ "e-06"
                      label3= str(d3)+ " °C"
                      labelstatus = 'Monitoring'
                      color_err = '#000000'
                      labelbar = 'Monitoring!'
                      self.ui.infostatus.setStyleSheet('background: #00ff72; padding: 1px; border: 1px solid #cccccc')
                      # If tracking was stopped and now the signal is back, show the resume message
                      # (the flag is cleared by _handle_auto_tracking when the worker reports re-enable)
                      if self._tracking_stopped_active:
                          labelbar = 'Monitoring! — Auto-tracking still stopped, waiting for resume'
                  else:
                      label1= "-"
                      label2= "-"
                      label3= "-"
                      labelstatus = 'Warning'
                      color_err = '#ff0000'
                      self.ui.infostatus.setStyleSheet('background: #ff0000; padding: 1px; border: 1px solid #cccccc')
                      if self._ser_error1 and self._ser_error2:
                        labelbar = 'Warning: lower and upper cut-off not found'
                      elif self._ser_error1:
                        labelbar = 'Warning: lower cut-off not found'
                      elif self._ser_error2:
                        labelbar = 'Warning: upper cut-off not found'
                      if self._tracking_stopped_active:
                          labelstatus = 'Tracking Stopped'
                          labelbar += ' — Auto-tracking stopped'
                         
               label_samp = "{0:.0f} ms".format(_sampling_time_s * 1000) if _sampling_time_s > 0 else "---"
               _set_data_value(self.ui.l6a, label3)
               _set_data_value(self.ui.l6b, label_samp)
               _set_data_value(self.ui.l6, label2)
               _set_data_value(self.ui.l7, label1)
               # Update status bar readings (visible when left panel is hidden)
               self.ui.update_status_bar_readings(frequency=label1, dissipation=label2, temperature=label3, sampling_time=label_samp)
               self.ui.infostatus.setText(labelstatus)
               self.ui.infobar.setText(labelbar)
               if color_err == '#ff0000':
                   self.ui.infobar.setStyleSheet('background-color: #ffebee; color: #c62828; padding: 8px; border-radius: 4px;')
               self.ui.progressBar.setValue(self._completed+2)

        # ---- Calibration mode: dynamic info in the status bar ----
        elif self._get_source() == SourceType.calibration:
            # Check for user cancellation (highest priority)
            if self.worker.is_calibration_cancelled():
                if self._is_running:  # Guard: only call stop() once
                    self.stop()
                    self.ui.infostatus.setText("Peak Detection Cancelled")
                    self.ui.infostatus.setStyleSheet('background: #ffff00; padding: 1px; border: 1px solid #cccccc')
                    self.ui.infobar.setText("Peak Detection cancelled by user.")
                    self.ui.infobar.setStyleSheet('background-color: #fff3e0; color: #e65100; padding: 8px; border-radius: 4px;')
                return

            # flag for terminating calibration
            stop_flag=0
            vector1 = self.worker.get_value1_buffer()
            # vector2[0] and vector3[0] flag error
            vector2 = self.worker.get_t3_buffer()
            vector3 = self.worker.get_d3_buffer()
            #print(vector1[0],vector2[0],vector3[0])
            label1 = 'not available'
            label2 = 'not available'
            label3 = 'not available' 
            labelstatus = 'Peak Detection Processing'
            color_err = '#000000'
            labelbar = 'please wait...'
            self.ui.infostatus.setStyleSheet('background: #ffff00; padding: 1px; border: 1px solid #cccccc')

            # Progress bar tracks the current calibration section
            error1, error2, error3, self._ser_control = self.worker.get_ser_error()
            if self._ser_control < Constants.calib_sections:
                self._completed = (self._ser_control / Constants.calib_sections) * 100

            # Calibration buffer empty (no acquisition flowing)
            if error1 == 1 and vector3[0] == 1:
                label1 = label2 = label3 = 'not available'
                color_err = '#ff0000'
                labelstatus = 'Peak Detection Warning'
                self.ui.infostatus.setStyleSheet('background: #ff0000; padding: 1px; border: 1px solid #cccccc')
                labelbar = 'empty buffer — Reconnect device and retry.'
                stop_flag = 1
            # Calibration buffer empty + ValueError from the serial port
            elif error1 == 1 and vector2[0] == 1:
                label1 = label2 = label3 = 'not available'
                color_err = '#ff0000'
                labelstatus = 'Peak Detection Warning'
                self.ui.infostatus.setStyleSheet('background: #ff0000; padding: 1px; border: 1px solid #cccccc')
                labelbar = 'empty buffer / value error — Reconnect device and retry.'
                stop_flag = 1
            # Calibration buffer is being filled normally
            elif error1 == 0:
                label1 = label2 = label3 = 'not available'
                labelstatus = 'Peak Detection Processing'
                color_err = '#000000'
                labelbar = 'please wait...'
                if vector2[0] == 0 and vector3[0] == 0:
                    labelstatus = 'Peak Detection Success'
                    self.ui.infostatus.setStyleSheet('background: #00ff72; padding: 1px; border: 1px solid #cccccc')
                    color_err = '#000000'
                    labelbar = 'peak detection completed — ready for baseline correction'
                    stop_flag = 1
                elif vector2[0] == 1 or vector3[0] == 1:
                 color_err = '#ff0000'
                 labelstatus = 'Peak Detection Warning'
                 self.ui.infostatus.setStyleSheet('background: #ff0000; padding: 1px; border: 1px solid #cccccc')
                 if vector2[0]== 1:
                   labelbar = 'generic signal acquisition error — retry.'
                   stop_flag=1 ##
                 elif vector3[0]== 1:
                   labelbar = 'peak not found — retry.'
                   stop_flag=1 ##

            _set_data_value(self.ui.l6a, label3)
            _set_data_value(self.ui.l6b, "---")
            _set_data_value(self.ui.l6, label2)
            _set_data_value(self.ui.l7, label1)
            # Update status bar readings (visible when left panel is hidden)
            self.ui.update_status_bar_readings(frequency=label1, dissipation=label2, temperature=label3, sampling_time="---")
            # progressbar -------------
            self.ui.progressBar.setValue(self._completed+10)

            # terminate the calibration
            if stop_flag == 1:
               self.stop()
               # Override stop() defaults with calibration result
               self.ui.infostatus.setText(labelstatus)
               self.ui.infobar.setText(labelbar)
               if color_err == '#ff0000':
                   # Warning: red
                   self.ui.infostatus.setStyleSheet('background: #ff0000; padding: 1px; border: 1px solid #cccccc')
                   self.ui.infobar.setStyleSheet('background-color: #ffebee; color: #c62828; padding: 8px; border-radius: 4px;')
                   PopUp.warning_nonblocking(self, "Peak Detection Warning", labelbar)
               else:
                   # Success: green
                   self.ui.infostatus.setStyleSheet('background: #00ff72; padding: 1px; border: 1px solid #cccccc')
                   self.ui.infobar.setStyleSheet('background-color: #e8f5e9; color: #2e7d32; padding: 8px; border-radius: 4px;')
                   # Show non-blocking popup with peak frequencies
                   try:
                       peak_data = np.loadtxt(Constants.cvs_peakfrequencies_path)
                       peaks = peak_data[:, 0]
                       # QCM overtone multipliers: 1 (fundamental), 3, 5, 7, 9
                       overtone_labels = [1, 3, 5, 7, 9]
                       lines = []
                       for j, f in enumerate(peaks):
                           if j < len(overtone_labels):
                               n = overtone_labels[j]
                               if n == 1:
                                   lines.append("Fundamental: {:.0f} Hz".format(f))
                               else:
                                   lines.append("Overtone {}: {:.0f} Hz".format(n, f))
                           else:
                               lines.append("Overtone: {:.0f} Hz".format(f))
                       freq_list = "\n".join(lines)
                       msg = "{} peaks detected (phase-validated):\n\n{}".format(len(peaks), freq_list)
                       PopUp.info_nonblocking(self, "Peak Detection Success", msg)
                   except Exception:
                       PopUp.info_nonblocking(self, "Peak Detection Success", "Peak Detection completed successfully!")
            else:
               # Still processing: show current status
               self.ui.infostatus.setText(labelstatus)
               self.ui.infobar.setText(labelbar)
               if color_err == '#ff0000':
                   self.ui.infobar.setStyleSheet('background-color: #ffebee; color: #c62828; padding: 8px; border-radius: 4px;')
               else:
                   self.ui.infobar.setStyleSheet('background-color: #e3f2fd; color: #1565c0; padding: 8px; border-radius: 4px;')                    
        # Plot updates use `setData()` on persistent curve objects rather than
        # clear() + plot(): the latter would allocate / free pyqtgraph items on
        # every timer tick, which is measurably more expensive in long runs.
        if self._reference_flag:
            _set_data_value(self.ui.inforef1, self._labelref1)
            _set_data_value(self.ui.inforef2, self._labelref2)

            ###################################################################
            # Amplitude and phase Plot - using setData() for efficiency
            # NOTE: sigResized.connect moved to _configure_plot() to avoid signal accumulation
            self._curve_amplitude.setData(x=self._readFREQ, y=self.worker.get_value1_buffer())
            self._curve_phase.setData(x=self._readFREQ, y=self.worker.get_value2_buffer())

            ###################################################################
            # Resonance frequency and dissipation Plot - using setData()
            # NOTE: sigResized.connect moved to _configure_plot() to avoid signal accumulation
            t1_buffer = self.worker.get_t1_buffer()
            self._vector_1 = np.array(self.worker.get_d1_buffer())-self._reference_value_frequency
            self._curve_frequency.setData(x=t1_buffer, y=self._vector_1)
            # Set start time for elapsed time axis from first valid (non-NaN) data point
            if len(t1_buffer) > 0:
                # Find first non-NaN value
                valid_mask = ~np.isnan(t1_buffer)
                if np.any(valid_mask):
                    first_valid = t1_buffer[valid_mask][0]
                    self._xaxis.set_start_time(first_valid)
            self._vector_2 = np.array(self.worker.get_d2_buffer())-self._reference_value_dissipation
            self._curve_dissipation.setData(x=self.worker.get_t2_buffer(), y=self._vector_2)

            # Enforce minimum Y-axis scale (reference mode)
            self._apply_min_scale(self._plt2, self._vector_1, MIN_FREQ_RANGE)
            self._apply_min_scale(self._plt3, self._vector_2, MIN_DISS_RANGE)

            ###################################################################
            # Temperature plot - using setData() for efficiency
            t3_buffer = self.worker.get_t3_buffer()
            temp_data = self.worker.get_d3_buffer()
            self._curve_temperature.setData(x=t3_buffer, y=temp_data)
            # Set start time for elapsed time axis from first valid (non-NaN) data point
            if len(t3_buffer) > 0:
                # Find first non-NaN value
                valid_mask = ~np.isnan(t3_buffer)
                if np.any(valid_mask):
                    first_valid = t3_buffer[valid_mask][0]
                    self._xaxis_temp.set_start_time(first_valid)
            # Enforce minimum Y-axis scale for temperature (reference mode)
            self._apply_min_scale(self._plt4, temp_data, MIN_TEMP_RANGE)
            # Theme-dependent colors: amplitude and temperature (white dark / black light)
            amp_color = self._theme_amp_color if self._theme_amp_color else '#ffffff'
            self._curve_amplitude.setPen(amp_color)
            temp_color = self._theme_temp_color if self._theme_temp_color else '#ffffff'
            self._curve_temperature.setPen(temp_color)

        # ---- Reference not set: plot raw values via setData on persistent curves ----
        else:
            _set_data_value(self.ui.inforef1, self._labelref1)
            _set_data_value(self.ui.inforef2, self._labelref2)

            ###################################################################
            # Amplitude and phase Plot - using setData() for efficiency
            # NOTE: sigResized.connect moved to _configure_plot() to avoid signal accumulation
            if self._get_source() == SourceType.calibration:
               calibration_readFREQ = np.arange(len(self.worker.get_value1_buffer())) * (Constants.calib_fStep) + Constants.calibration_frequency_start
               self._curve_amplitude.setData(x=calibration_readFREQ, y=self.worker.get_value1_buffer())
               self._curve_phase.setData(x=calibration_readFREQ, y=self.worker.get_value2_buffer())
            elif self._get_source() == SourceType.serial:
               self._curve_amplitude.setData(x=self._readFREQ, y=self.worker.get_value1_buffer())
               self._curve_phase.setData(x=self._readFREQ, y=self.worker.get_value2_buffer())

            ###################################################################
            # Resonance frequency and dissipation Plot - using setData()
            # NOTE: sigResized.connect moved to _configure_plot() to avoid signal accumulation
            t1_buffer = self.worker.get_t1_buffer()
            self._curve_frequency.setData(x=t1_buffer, y=self.worker.get_d1_buffer())
            # Set start time for elapsed time axis from first valid (non-NaN) data point
            if len(t1_buffer) > 0:
                # Find first non-NaN value
                valid_mask = ~np.isnan(t1_buffer)
                if np.any(valid_mask):
                    first_valid = t1_buffer[valid_mask][0]
                    self._xaxis.set_start_time(first_valid)
            diss_data = self.worker.get_d2_buffer()
            self._curve_dissipation.setData(x=self.worker.get_t2_buffer(), y=diss_data)

            # Enforce minimum Y-axis scale
            self._apply_min_scale(self._plt2, self.worker.get_d1_buffer(), MIN_FREQ_RANGE)
            self._apply_min_scale(self._plt3, diss_data, MIN_DISS_RANGE)

            ###################################################################
            # Temperature plot - using setData() for efficiency
            t3_buffer = self.worker.get_t3_buffer()
            temp_data = self.worker.get_d3_buffer()
            self._curve_temperature.setData(x=t3_buffer, y=temp_data)
            # Set start time for elapsed time axis from first valid (non-NaN) data point
            if len(t3_buffer) > 0:
                # Find first non-NaN value
                valid_mask = ~np.isnan(t3_buffer)
                if np.any(valid_mask):
                    first_valid = t3_buffer[valid_mask][0]
                    self._xaxis_temp.set_start_time(first_valid)
            # Enforce minimum Y-axis scale for temperature
            self._apply_min_scale(self._plt4, temp_data, MIN_TEMP_RANGE)

    ###########################################################################################################################################

    ###########################################################################
    # AUTO-TRACKING: Handle tracking state changes and update GUI
    ###########################################################################
    def _handle_auto_tracking(self):
        """
        Check if auto-tracking has been triggered and update the GUI accordingly.
        Updates the X-axis of the Amplitude/Phase plot and shows notifications.
        Also handles the "tracking disabled by errors" state.
        """
        # Check tracking safety state (disable/re-enable by edge errors)
        # Only update the persistent flag here — the message is composed later
        # in _update_plot together with the cut-off warning (which otherwise
        # overwrites it on every sweep).
        (disabled, first_disabled, reenabled) = self.worker.get_tracking_disabled()
        if disabled:
            self._tracking_stopped_active = True
            if first_disabled:
                print("[MainWindow] Auto-tracking disabled")
        if reenabled:
            self._tracking_stopped_active = False
            print("[MainWindow] Auto-tracking re-enabled automatically")

        (activated, start_freq, stop_freq, ref_freq, count) = self.worker.get_tracking_state()

        if activated and start_freq is not None and stop_freq is not None:
            # Update internal frequency range
            samples = Constants.argument_default_samples
            fStep = (stop_freq - start_freq) / (samples - 1)
            self._readFREQ = np.arange(samples) * fStep + start_freq

            # Update the Device Information panel
            _set_data_value(self.ui.info3, "{:.0f} Hz".format(start_freq))
            _set_data_value(self.ui.info4, "{:.0f} Hz".format(stop_freq))
            _set_data_value(self.ui.info4a, "{:.0f} Hz".format(stop_freq - start_freq))
            _set_data_value(self.ui.info6, "{:.0f} Hz".format(ref_freq))

            # Show GUI notification (brief, yellow background)
            self.ui.infostatus.setStyleSheet('background: #ffff00; padding: 1px; border: 1px solid #cccccc')
            self.ui.infostatus.setText("Auto-Tracking #{}".format(count))
            self.ui.infobar.setStyleSheet('background-color: #fff3e0; color: #e65100; padding: 8px; border-radius: 4px;')
            self.ui.infobar.setText("Auto-tracking activated: new sweep window {:.0f} - {:.0f} Hz".format(start_freq, stop_freq))

            # Log to System Log tab
            print("AUTO-TRACKING #{}: Sweep window updated to {:.0f} - {:.0f} Hz (ref: {:.0f} Hz)".format(
                count, start_freq, stop_freq, ref_freq))


    ###########################################################################
    # Updates the source and depending boxes on change
    ###########################################################################
    def _source_changed(self):
        """
        Called when measurement mode changes.
        If serial is connected, preserve the port selection.
        """
        # Log the source change
        if self._get_source() == SourceType.serial:
            print(TAG, "Mode: {}".format(Constants.app_sources[0]))
            Log.i(TAG, "Mode: {}".format(Constants.app_sources[0]))
        elif self._get_source() == SourceType.calibration:
            print(TAG, "Mode: {}".format(Constants.app_sources[1]))
            Log.i(TAG, "Mode: {}".format(Constants.app_sources[1]))

        # In calibration mode, hide the dropdown and overtone buttons
        # In measurement mode, show them (user selects overtone frequency)
        if self._get_source() == SourceType.calibration:
            self.ui.cBox_Speed.hide()
            for btn in self.ui.overtone_buttons.values():
                btn.hide()
        else:
            self.ui.cBox_Speed.show()
            for btn in self.ui.overtone_buttons.values():
                btn.show()

        # If serial is connected, don't change port selection
        if self._serial_connected:
            # Only update speed options, keep port unchanged
            if self._get_source() != SourceType.calibration:
                self.ui.cBox_Speed.clear()
                source = self._get_source()
                speeds = self.worker.get_source_speeds(source)
                if speeds is not None:
                    self.ui.cBox_Speed.addItems(speeds)
                if self._get_source() == SourceType.serial:
                    self.ui.cBox_Speed.setCurrentIndex(len(speeds) - 1)
                self._update_overtone_buttons()
            return

        # Not connected - populate both port and speed
        self.ui.cBox_Port.clear()
        self.ui.cBox_Speed.clear()

        source = self._get_source()
        ports = self.worker.get_source_ports(source)

        if ports is not None:
            self.ui.cBox_Port.addItems(ports)

        # Only populate speed dropdown in measurement mode
        if self._get_source() != SourceType.calibration:
            speeds = self.worker.get_source_speeds(source)
            if speeds is not None:
                self.ui.cBox_Speed.addItems(speeds)
            if self._get_source() == SourceType.serial:
                self.ui.cBox_Speed.setCurrentIndex(len(speeds) - 1)
            self._update_overtone_buttons()

    ###########################################################################
    # Overtone quick-select buttons
    ###########################################################################

    # Mapping: button label → index in PeakFrequencies.txt (file order)
    OVERTONE_MAP = {'F0': 0, 'F3': 1, 'F5': 2, 'F7': 3, 'F9': 4}
    INDEX_TO_LABEL = {0: 'F0', 1: 'F3', 2: 'F5', 3: 'F7', 4: 'F9'}

    def _update_overtone_buttons(self):
        """Enable overtone buttons based on calibration results (PeakFrequencies.txt)."""
        try:
            peak_data = np.loadtxt(Constants.cvs_peakfrequencies_path)
            peak_freqs = peak_data[:, 0]
        except Exception:
            # No calibration data — disable all buttons
            for btn in self.ui.overtone_buttons.values():
                btn.setEnabled(False)
                btn.setChecked(False)
                btn.setProperty('calibrated', False)
            return

        # Enable buttons for detected peaks (frequency > 0)
        for label, btn in self.ui.overtone_buttons.items():
            idx = self.OVERTONE_MAP[label]
            if idx < len(peak_freqs) and peak_freqs[idx] > 0:
                btn.setEnabled(True)
                btn.setProperty('calibrated', True)
            else:
                btn.setEnabled(False)
                btn.setChecked(False)
                btn.setProperty('calibrated', False)

        # Sync with current dropdown selection
        self._sync_overtone_buttons()

    def _on_overtone_button_clicked(self, label):
        """Handle click on an overtone button — update dropdown to match."""
        idx = self.OVERTONE_MAP[label]
        try:
            peak_data = np.loadtxt(Constants.cvs_peakfrequencies_path)
            peak_freqs = peak_data[:, 0]
            if idx < len(peak_freqs):
                target_freq = str(peak_freqs[idx])
                # Find this frequency in the dropdown (which is in reverse order)
                for i in range(self.ui.cBox_Speed.count()):
                    if self.ui.cBox_Speed.itemText(i) == target_freq:
                        self.ui.cBox_Speed.setCurrentIndex(i)
                        break
        except Exception:
            pass
        # Update checked state
        for l, btn in self.ui.overtone_buttons.items():
            btn.setChecked(l == label)

    def _sync_overtone_buttons(self):
        """Sync overtone buttons with current dropdown selection."""
        current_text = self.ui.cBox_Speed.currentText()
        if not current_text:
            return
        try:
            current_freq = float(current_text)
            peak_data = np.loadtxt(Constants.cvs_peakfrequencies_path)
            peak_freqs = peak_data[:, 0]
            # Find which index matches the selected frequency
            for i, pf in enumerate(peak_freqs):
                if abs(pf - current_freq) < 1.0:  # float comparison tolerance
                    label = self.INDEX_TO_LABEL.get(i)
                    for l, btn in self.ui.overtone_buttons.items():
                        btn.setChecked(l == label)
                    return
        except Exception:
            pass
        # No match — uncheck all
        for btn in self.ui.overtone_buttons.values():
            btn.setChecked(False)

    ###########################################################################
    # Refresh available serial ports
    ###########################################################################
    def _refresh_ports(self):
        """
        Refresh the list of available serial ports.
        """
        if self._serial_connected:
            # Don't refresh if already connected
            return

        self.ui.cBox_Port.clear()
        source = self._get_source()
        ports = self.worker.get_source_ports(source)
        if ports is not None:
            self.ui.cBox_Port.addItems(ports)
        print(TAG, "Ports refreshed: {} found".format(len(ports) if ports else 0))
        Log.i(TAG, "Ports refreshed")

    ###########################################################################
    # Serial port lock file management (cross-platform exclusive access)
    ###########################################################################
    def _get_lock_file_path(self, port):
        """
        Get the path to the lock file for a given serial port.
        Lock files are stored in a temp directory with a sanitized port name.
        """
        import tempfile
        import re
        # Sanitize port name for use as filename (replace / and \ with _)
        safe_port_name = re.sub(r'[/\\:]', '_', port)
        lock_dir = os.path.join(tempfile.gettempdir(), 'openqcm_locks')
        os.makedirs(lock_dir, exist_ok=True)
        return os.path.join(lock_dir, f'{safe_port_name}.lock')

    def _acquire_port_lock(self, port):
        """
        Try to acquire an exclusive lock on the serial port using a lock file.
        Returns True if lock acquired, False if port is already locked.
        On Windows: skipped (COM ports are natively exclusive).
        On Unix: uses fcntl.flock() for file-based locking.
        """
        # Windows COM ports are natively exclusive — no file lock needed
        if sys.platform == 'win32':
            return True

        import fcntl
        lock_path = self._get_lock_file_path(port)

        try:
            # Open (or create) the lock file
            self._lock_file = open(lock_path, 'w')
            # Try to acquire exclusive lock (non-blocking)
            fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            # Write PID to lock file for debugging
            self._lock_file.write(str(os.getpid()))
            self._lock_file.flush()
            return True
        except (IOError, OSError) as e:
            # Lock acquisition failed - port is locked by another process
            if self._lock_file:
                self._lock_file.close()
                self._lock_file = None
            return False

    def _release_port_lock(self):
        """
        Release the exclusive lock on the serial port.
        On Windows: no-op (no file lock was acquired).
        On Unix: releases fcntl.flock().
        """
        # Windows: nothing to release
        if sys.platform == 'win32':
            return

        if hasattr(self, '_lock_file') and self._lock_file:
            try:
                import fcntl
                fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
                self._lock_file.close()
            except Exception as e:
                print(TAG, "Warning: Error releasing lock file: {}".format(str(e)))
            self._lock_file = None

    ###########################################################################
    # Toggle serial port connection (exclusive lock)
    ###########################################################################
    def _toggle_serial_connection(self):
        """
        Connect or disconnect from the selected serial port.
        Uses file-based locking to ensure exclusive access across all instances.
        """
        import serial

        if not self._serial_connected:
            # CONNECT
            port = self.ui.cBox_Port.currentText()
            if not port:
                PopUp.warning(self, Constants.app_title, "No port selected!")
                return

            # First, try to acquire the lock file
            if not self._acquire_port_lock(port):
                # Lock acquisition failed - another instance has the port
                self.ui.set_connection_state(False)
                self.ui.infostatus.setText("Disconnected")
                self.ui.infobar.setText("Port locked by another instance")
                PopUp.warning(self, Constants.app_title,
                    "Port [{}] is already in use!\n\nAnother instance of openQCM is connected to this port.\nPlease disconnect from the other instance first.".format(port))
                print(TAG, "Connection failed: port locked by another instance")
                Log.e(TAG, "Connection failed: port locked by another instance")
                return

            # Lock acquired, now try to open the serial port
            try:
                # Open serial port and keep it open
                try:
                    self._serial_lock = serial.Serial(port, timeout=1, exclusive=True)
                except TypeError:
                    # exclusive parameter not supported on older pyserial versions
                    self._serial_lock = serial.Serial(port, timeout=1)

                # Connection successful - port is now locked
                self._serial_connected = True
                self._connected_port = port
                self.ui.pButton_Connect.setText("Disconnect")
                self._set_button_role(self.ui.pButton_Connect, "btnDisconnect")
                self.ui.cBox_Port.setEnabled(False)
                self.ui.pButton_Refresh.setEnabled(False)
                self.ui.pButton_StartStop.setEnabled(True)
                # Update status indicator to yellow (connected + standby)
                self.ui.set_connection_state(True)
                self.ui.infostatus.setText("Standby")
                self.ui.infobar.setText("Connected to {} (exclusive)".format(port))
                print(TAG, "Connected to port: {} (exclusive lock)".format(port))
                Log.i(TAG, "Connected to port: {} (exclusive lock)".format(port))

                # Auto-check firmware version after connection
                self._check_firmware_version(auto_mode=True)

            except serial.SerialException as e:
                # Connection failed - release the lock file
                self._release_port_lock()
                self._serial_connected = False
                self._connected_port = None
                self._serial_lock = None
                self.ui.pButton_StartStop.setEnabled(False)
                # Update status indicator to gray (disconnected)
                self.ui.set_connection_state(False)
                self.ui.infostatus.setText("Disconnected")
                self.ui.infobar.setText("Port busy or unavailable")
                PopUp.warning(self, Constants.app_title,
                    "Failed to connect to port [{}]!\n\nThe port may be in use by another application.\n\nError: {}".format(port, str(e)))
                print(TAG, "Connection failed: {}".format(str(e)))
                Log.e(TAG, "Connection failed: {}".format(str(e)))
            except Exception as e:
                # Other connection errors - release the lock file
                self._release_port_lock()
                self._serial_connected = False
                self._connected_port = None
                self._serial_lock = None
                self.ui.pButton_StartStop.setEnabled(False)
                self.ui.set_connection_state(False)
                self.ui.infostatus.setText("Disconnected")
                self.ui.infobar.setText("Connection failed")
                PopUp.warning(self, Constants.app_title,
                    "Failed to connect to port [{}]!\nError: {}".format(port, str(e)))
                print(TAG, "Connection failed: {}".format(str(e)))
                Log.e(TAG, "Connection failed: {}".format(str(e)))

        else:
            # DISCONNECT - release the serial port and lock file
            if self._serial_lock is not None:
                try:
                    self._serial_lock.close()
                    print(TAG, "Serial port closed")
                    Log.i(TAG, "Serial port closed")
                except Exception as e:
                    print(TAG, "Warning: Error closing serial port: {}".format(str(e)))
                    Log.w(TAG, "Error closing serial port: {}".format(str(e)))
                self._serial_lock = None

            # Release the lock file
            self._release_port_lock()

            self._serial_connected = False
            self._connected_port = None
            self.ui.pButton_Connect.setText("Connect")
            self._set_button_role(self.ui.pButton_Connect, "btnConnect")
            self.ui.cBox_Port.setEnabled(True)
            self.ui.pButton_Refresh.setEnabled(True)
            self.ui.pButton_StartStop.setEnabled(False)
            # Update status indicator to gray (disconnected)
            self.ui.set_connection_state(False)
            self.ui.infostatus.setText("Disconnected")
            self.ui.infobar.setText("Ready to connect")
            print(TAG, "Disconnected from serial port")
            Log.i(TAG, "Disconnected from serial port")

    ###########################################################################
    # Gets the current source type
    ###########################################################################
    def _get_source(self):
        #:rtype: SourceType.
        return SourceType(self.ui.cBox_Source.currentIndex())

    ###########################################################################
    # Resize event handling - pause updates during resize for better performance
    ###########################################################################
    def resizeEvent(self, event):
        """
        Override resize event to pause plot updates during window resize.
        This prevents GUI lag caused by continuous plot redraws.
        """
        # Guard against early resize events before __init__ completes
        if hasattr(self, '_resize_timer'):
            self._is_resizing = True
            # Restart the debounce timer (150ms after last resize event)
            self._resize_timer.start(150)
        # Call parent implementation
        super(MainWindow, self).resizeEvent(event)

    def _on_resize_finished(self):
        """
        Called when resize operation is complete (debounced).
        Resumes normal plot updates.
        """
        self._is_resizing = False

    ###########################################################################
    # Switch between dark and light theme
    ###########################################################################
    def _switch_theme(self, theme):
        """
        Switch the application theme between 'dark' and 'light'.
        Updates both the Qt stylesheet and the pyqtgraph plot backgrounds.
        """
        if theme == 'dark':
            # Apply dark stylesheet
            self.setStyleSheet(self.ui._get_dark_stylesheet())
            self.ui._current_theme = 'dark'

            # Update plot backgrounds to dark
            plot_bg = '#2b2b2b'
            axis_color = '#ffffff'  # White axes/labels for dark mode
            title_color = '#ffffff'  # White titles for dark mode
            legend_bg = '#3c3c3c80'
            legend_border = '#555555'
            self.ui.plt.setBackground(plot_bg)
            self.ui.pltB.setBackground(plot_bg)

        elif theme == 'light':
            # Apply light stylesheet
            self.setStyleSheet(self.ui._get_light_stylesheet())
            self.ui._current_theme = 'light'

            # Update plot backgrounds to light
            plot_bg = '#ffffff'
            axis_color = '#666666'
            title_color = '#333333'
            legend_bg = '#f0f0f0e0'  # Light gray with some transparency
            legend_border = '#cccccc'
            self.ui.plt.setBackground(plot_bg)
            self.ui.pltB.setBackground(plot_bg)

        # Update axis colors for all plots
        axis_pen = pg.mkPen(color=axis_color, width=1)

        # Update plt0 (Amplitude/Phase)
        for axis_name in ['left', 'right', 'bottom']:
            axis = self._plt0.getAxis(axis_name)
            if axis:
                axis.setPen(axis_pen)
                axis.setTextPen(axis_color)
        self._plt0.setTitle("Amplitude / Phase", color=title_color)

        # Update plt2 (Frequency/Dissipation)
        for axis_name in ['left', 'right', 'bottom']:
            axis = self._plt2.getAxis(axis_name)
            if axis:
                axis.setPen(axis_pen)
                axis.setTextPen(axis_color)
        self._plt2.setTitle("Resonance Frequency / Dissipation", color=title_color)

        # Update plt4 (Temperature)
        for axis_name in ['left', 'bottom']:
            axis = self._plt4.getAxis(axis_name)
            if axis:
                axis.setPen(axis_pen)
                axis.setTextPen(axis_color)
        self._plt4.setTitle("Temperature", color=title_color)

        # Update axis labels
        self._plt0.setLabel('bottom', 'Frequency', units='Hz', color=axis_color)
        self._plt0.setLabel('left', 'Amplitude', units='dB', color=axis_color)
        self._plt0.setLabel('right', 'Phase', units='deg', color=axis_color)

        self._plt2.setLabel('bottom', 'Time (hh:mm:ss)', units='', color=axis_color)
        self._plt2.setLabel('left', 'Resonance Frequency', units='Hz', color=axis_color)
        self._plt2.setLabel('right', 'Dissipation', units='', color=axis_color)

        self._plt4.setLabel('bottom', 'Time (hh:mm:ss)', units='', color=axis_color)
        self._plt4.setLabel('left', 'Temperature', units='°C', color=axis_color)

        # Update legend backgrounds
        self._legend0.setBrush(pg.mkBrush(legend_bg))
        self._legend0.setPen(pg.mkPen(legend_border))
        self._legend2.setBrush(pg.mkBrush(legend_bg))
        self._legend2.setPen(pg.mkPen(legend_border))
        self._legend4.setBrush(pg.mkBrush(legend_bg))
        self._legend4.setPen(pg.mkPen(legend_border))

        # Update theme-dependent curve colors
        # Frequency (#008EC0), Dissipation (#DD8E6B), Phase (#008EC0) remain constant
        if theme == 'light':
            self._theme_amp_color = '#000000'       # Black for amplitude in light mode
            self._theme_temp_color = '#000000'      # Black for temperature in light mode
        else:
            self._theme_amp_color = '#ffffff'       # White for amplitude in dark mode
            self._theme_temp_color = '#ffffff'      # White for temperature in dark mode

        self._curve_amplitude.setPen(self._theme_amp_color)
        self._curve_temperature.setPen(self._theme_temp_color)

        print(TAG, f"Theme switched to: {theme}", end='\r')
    
    
    ###########################################################################
    # Clear history plot data (frequency / dissipation / temperature traces).
    # Uses setData([], []) on the persistent curve objects so the plot scene
    # is preserved (cheaper than clear() + replot at every cycle).
    ###########################################################################
    def clear(self):
        support = self.worker.get_d1_buffer()
        if support.any and str(support[0]) != 'nan':
            print(TAG, "All Plots Cleared!", end='\r')
            self._update_sample_size()
            if self._curve_frequency is not None:
                self._curve_frequency.setData(x=[], y=[])
            if self._curve_dissipation is not None:
                self._curve_dissipation.setData(x=[], y=[])
            if self._curve_temperature is not None:
                self._curve_temperature.setData(x=[], y=[])
        
        
    ###########################################################################
    # Reference set/reset
    ###########################################################################     
    def reference(self):
        import numpy as np
        #import sys
        support=self.worker.get_d1_buffer()
        if support.any:
            if str(support[0])!='nan':
                ref_vector1 = [c for c in self.worker.get_d1_buffer() if ~np.isnan(c)]
                ref_vector2 = [c for c in self.worker.get_d2_buffer() if ~np.isnan(c)]
                self._reference_value_frequency = ref_vector1[0]
                self._reference_value_dissipation = ref_vector2[0]
                #sys.stdout.write("\033[K") #clear line
                if self._reference_flag:
                    # Clear reference
                    self._reference_flag = False
                    self.ui.pButton_Reference.setText("Set Reference")
                    print(TAG, "Reference cleared!", end='\r')
                    self._labelref1 = "not set"
                    self._labelref2 = "not set"
                else:
                    # Set reference
                    self._reference_flag = True
                    self.ui.pButton_Reference.setText("Clear Reference")
                    d1=float("{0:.2f}".format(self._reference_value_frequency))
                    d2=float("{0:.1f}".format(self._reference_value_dissipation*1e6))
                    self._labelref1 = str(d1)+ "Hz"
                    self._labelref2 = str(d2)+ "e-06"
                    print(TAG, "Reference set!     ", end='\r')
                    self._vector_reference_frequency[:] = [s - self._reference_value_frequency for s in self._readFREQ]
                    xs = np.array(np.linspace(0, ((self._readFREQ[-1]-self._readFREQ[0])/self._readFREQ[0]), len(self._readFREQ)))
                    self._vector_reference_dissipation = xs-self._reference_value_dissipation

                # Force Y-axis autoscale when toggling reference
                # (values jump from absolute to relative or vice versa)
                if self._plt2 is not None:
                    self._plt2.enableAutoRange(axis='y', enable=True)
                if self._plt3 is not None:
                    self._plt3.enableAutoRange(axis='y', enable=True)

    ###########################################################################
    # Minimum Y-axis scale enforcement
    ###########################################################################
    def _apply_min_scale(self, plot_or_vb, y_data, min_range):
        """Enforce minimum Y-axis display range centered on data.
        If data range < min_range, set range to min_range centered on data.
        If data range >= min_range, let autoscale handle it normally.
        Works with both PlotItem and ViewBox objects.
        """
        if not self._min_scale_enabled or len(y_data) == 0:
            return
        valid = y_data[~np.isnan(y_data)]
        if len(valid) == 0:
            return
        y_min, y_max = np.min(valid), np.max(valid)
        data_range = y_max - y_min
        if data_range < min_range:
            center = (y_min + y_max) / 2.0
            half = min_range / 2.0
            lo, hi = center - half, center + half
            # ViewBox uses setRange(), PlotItem uses setYRange()
            if isinstance(plot_or_vb, pg.ViewBox):
                plot_or_vb.disableAutoRange(axis='y')
                plot_or_vb.setRange(yRange=(lo, hi), padding=0)
            else:
                plot_or_vb.setYRange(lo, hi, padding=0)
        else:
            plot_or_vb.enableAutoRange(axis='y', enable=True)

    def _on_logo_context_menu(self, pos):
        """Easter egg: right-click on logo to toggle min axis scale limits."""
        menu = QtWidgets.QMenu()
        if self._min_scale_enabled:
            action = menu.addAction("Unlock Axes")
        else:
            action = menu.addAction("Lock Axes")
        result = menu.exec_(self.ui.lblLogo.mapToGlobal(pos))
        if result == action:
            self._min_scale_enabled = not self._min_scale_enabled
            state = "locked" if self._min_scale_enabled else "unlocked"
            print(TAG, f"Axis scale limits {state}", end='\r')
            self.autoscale()

    ###########################################################################
    # Autoscale all plots (X and Y axes)
    ###########################################################################
    def autoscale(self):
        # Enable auto range on all plots (both X and Y axes)
        # Plot 0: Amplitude/Phase
        if self._plt0 is not None:
            self._plt0.enableAutoRange(axis='xy', enable=True)
        if self._plt1 is not None:
            self._plt1.enableAutoRange(axis='xy', enable=True)
        # Plot 2/3: Resonance Frequency/Dissipation
        if self._plt2 is not None:
            self._plt2.enableAutoRange(axis='xy', enable=True)
        if self._plt3 is not None:
            self._plt3.enableAutoRange(axis='xy', enable=True)
        # Plot 4: Temperature
        if self._plt4 is not None:
            self._plt4.enableAutoRange(axis='xy', enable=True)
        print(TAG, "Autoscale enabled on all plots!", end='\r')

    ###########################################################################
    # CURSORS: Toggle visibility of measurement cursors
    ###########################################################################
    def _toggle_cursors(self, checked=None):
        """
        Show or hide the measurement cursors on the Frequency/Dissipation plot.
        :param checked: If provided, set visibility directly. Otherwise toggle.
        """
        if checked is None:
            # Toggle from current state (called from menu action)
            checked = self.ui.actionToggleCursors.isChecked()

        self._cursors_visible = checked

        # Sync menu checkbox
        self.ui.actionToggleCursors.blockSignals(True)
        self.ui.actionToggleCursors.setChecked(checked)
        self.ui.actionToggleCursors.blockSignals(False)

        if checked:
            # Show cursors - position them at 1/3 and 2/3 of current view range
            view_range = self._plt2.viewRange()
            x_min, x_max = view_range[0]
            x_range = x_max - x_min
            pos1 = x_min + x_range * 0.33
            pos2 = x_min + x_range * 0.66

            self._cursor1.setValue(pos1)
            self._cursor2.setValue(pos2)

            # Add cursors to plot (ignoreBounds prevents them from affecting autoscale)
            self._plt2.addItem(self._cursor1, ignoreBounds=True)
            self._plt2.addItem(self._cursor2, ignoreBounds=True)
            self._plt2.addItem(self._cursor1_text, ignoreBounds=True)
            self._plt2.addItem(self._cursor2_text, ignoreBounds=True)

            # Delta text: parent to ViewBox for fixed pixel positioning (always visible top-left)
            self._cursor_delta_text.setParentItem(self._plt2.getViewBox())
            self._cursor_delta_text.setPos(8, 8)  # 8px from top-left corner

            # Update cursor values
            self._on_cursor_moved()
            print(TAG, "Cursors enabled", end='\r')
        else:
            # Hide cursors
            self._plt2.removeItem(self._cursor1)
            self._plt2.removeItem(self._cursor2)
            self._plt2.removeItem(self._cursor1_text)
            self._plt2.removeItem(self._cursor2_text)
            # Remove delta text from ViewBox parent
            if self._cursor_delta_text.parentItem() is not None:
                self._cursor_delta_text.setParentItem(None)
                self._cursor_delta_text.scene().removeItem(self._cursor_delta_text) if self._cursor_delta_text.scene() else None
            print(TAG, "Cursors disabled", end='\r')

    def _on_cursor_moved(self):
        """
        Called when a cursor is dragged. Updates the delta display.
        """
        if not self._cursors_visible:
            return

        # Get cursor positions (time values)
        t1 = self._cursor1.value()
        t2 = self._cursor2.value()

        # Get data from buffers
        t_buffer = self.worker.get_t1_buffer() if self.worker else np.array([])
        freq_buffer = self.worker.get_d1_buffer() if self.worker else np.array([])
        diss_buffer = self.worker.get_d2_buffer() if self.worker else np.array([])

        # Find nearest data points for each cursor
        f1, d1 = self._get_values_at_time(t1, t_buffer, freq_buffer, diss_buffer)
        f2, d2 = self._get_values_at_time(t2, t_buffer, freq_buffer, diss_buffer)

        # Calculate deltas
        TS_MULT_us = 1e6
        delta_t = abs(t2 - t1) / TS_MULT_us  # convert from microseconds to seconds
        delta_f = f2 - f1 if not (np.isnan(f1) or np.isnan(f2)) else float('nan')
        delta_d = (d2 - d1) * 1e6 if not (np.isnan(d1) or np.isnan(d2)) else float('nan')

        # Update cursor 1 label
        if not np.isnan(f1):
            if self._reference_flag:
                f1_display = f1 - self._reference_value_frequency
                d1_display = (d1 - self._reference_value_dissipation) * 1e6
            else:
                f1_display = f1
                d1_display = d1 * 1e6
            self._cursor1_text.setText(f"C1: F={f1_display:.1f} Hz, D={d1_display:.2f}e-06")
        else:
            self._cursor1_text.setText("C1: ---")

        # Update cursor 2 label
        if not np.isnan(f2):
            if self._reference_flag:
                f2_display = f2 - self._reference_value_frequency
                d2_display = (d2 - self._reference_value_dissipation) * 1e6
            else:
                f2_display = f2
                d2_display = d2 * 1e6
            self._cursor2_text.setText(f"C2: F={f2_display:.1f} Hz, D={d2_display:.2f}e-06")
        else:
            self._cursor2_text.setText("C2: ---")

        # Update delta label (time in seconds)
        if not np.isnan(delta_f):
            self._cursor_delta_text.setText(
                f"Δt: {delta_t:.1f} s   ΔF: {delta_f:.1f} Hz   ΔD: {delta_d:.2f}e-06"
            )
        else:
            self._cursor_delta_text.setText("Δt: ---   ΔF: ---   ΔD: ---")

        # Position C1/C2 labels near top of their respective cursor lines
        view_range = self._plt2.viewRange()
        y_max = view_range[1][1]
        y_range = view_range[1][1] - view_range[1][0]
        self._cursor1_text.setPos(t1, y_max - y_range * 0.05)
        self._cursor2_text.setPos(t2, y_max - y_range * 0.05)
        # Delta text is parented to ViewBox with fixed pixel position (no repositioning needed)

    def _get_values_at_time(self, t, t_buffer, freq_buffer, diss_buffer):
        """
        Get frequency and dissipation values at a given time by finding the nearest data point.
        Returns (frequency, dissipation) or (nan, nan) if no data.
        """
        if t_buffer is None or len(t_buffer) == 0:
            return float('nan'), float('nan')

        # Find nearest index
        valid_mask = ~np.isnan(t_buffer)
        if not np.any(valid_mask):
            return float('nan'), float('nan')

        valid_times = t_buffer[valid_mask]
        valid_freq = freq_buffer[valid_mask] if freq_buffer is not None and len(freq_buffer) == len(t_buffer) else None
        valid_diss = diss_buffer[valid_mask] if diss_buffer is not None and len(diss_buffer) == len(t_buffer) else None

        if len(valid_times) == 0:
            return float('nan'), float('nan')

        # Find nearest time index
        idx = np.argmin(np.abs(valid_times - t))

        freq = valid_freq[idx] if valid_freq is not None and len(valid_freq) > idx else float('nan')
        diss = valid_diss[idx] if valid_diss is not None and len(valid_diss) > idx else float('nan')

        return freq, diss

    ###########################################################################
    # Opens Data View dialog to visualize CSV data files
    ###########################################################################
    def _open_data_viewer(self):
        from PyQt5.QtWidgets import QFileDialog
        from openQCM.ui.mainWindow_ui import DataViewerDialog
        csv_path, _ = QFileDialog.getOpenFileName(
            self, "Open CSV Data File",
            Constants.csv_export_path,
            "CSV Files (*.csv);;All Files (*)")
        if csv_path:
            theme = 'dark' if self.ui.actionDarkTheme.isChecked() else 'light'
            self._data_viewer = DataViewerDialog(None, csv_path=csv_path, theme=theme)
            self._data_viewer.show()

    ###########################################################################
    # Opens Raw Data View dialog showing live amplitude/phase sweep curves
    ###########################################################################
    def _open_raw_data_viewer(self):
        from openQCM.ui.mainWindow_ui import RawDataViewDialog
        theme = 'dark' if self.ui.actionDarkTheme.isChecked() else 'light'
        self._raw_data_viewer = RawDataViewDialog(None, main_window=self, theme=theme)
        self._raw_data_viewer.show()

    ###########################################################################
    # Opens Peak Data View showing calibration amplitude/phase with peaks
    ###########################################################################
    def _open_peak_data_viewer(self):
        # Find the most recently modified calibration file
        calib_path = None
        latest_mtime = 0
        for candidate in [Constants.csv_calibration_path,
                          Constants.csv_calibration_path10]:
            if os.path.exists(candidate):
                mtime = os.path.getmtime(candidate)
                if mtime > latest_mtime:
                    latest_mtime = mtime
                    calib_path = candidate

        peaks_path = Constants.cvs_peakfrequencies_path

        if calib_path is None or not os.path.exists(peaks_path):
            PopUp.warning(self, "Peak Data View",
                          "No calibration data found.\nRun Peak Detection first.")
            return

        theme = 'dark' if self.ui.actionDarkTheme.isChecked() else 'light'
        self._calib_plot_window = CalibrationPlotWindow(None, theme=theme)
        self._calib_plot_window.show_results(calib_path, peaks_path)
        self._calib_plot_window.show()

    ###########################################################################
    # Checking internet connection
    ###########################################################################
    def internet_on(self):
       from urllib.request import urlopen
       try:
           url = "https://openqcm.com/shared/news.html"
           urlopen(url, timeout=10)
           return True
       except: 
           return False
       
    ########################################################################################################
    # Gets information from openQCM webpage and enables download button if new version software is available
    ########################################################################################################
    def get_web_info(self):
        # `pandas` is only needed here to parse the openQCM news/version HTML
        # table. It is excluded from the PyInstaller bundle to keep the
        # standalone executable small (~150 MB saved). When the dependency
        # is missing, the update check is gracefully disabled.
        try:
            import pandas as pd
        except ImportError:
            print(TAG, "pandas not available — update check disabled")
            self._internet_connected = False
            return
        # check if an Internet connection is active
        self._internet_connected = self.internet_on()
        # Get latest info from openQCM webpage
        c_types = {
                   '1': '1',
                   '2': '2',
                   '3': '3',}
        r_types = {
                   '1': 'A',
                   '2': 'B',
                   '3': 'C',}
        if self._internet_connected:
           color = '#00c600'
           labelweb2 = 'ONLINE'
           print (TAG,'Checking your internet connection {} '.format(labelweb2))
           tables = pd.read_html('https://openqcm.com/shared/news.html', index_col=0, header=0, match='1')
           df = tables[0]
           # create empty list of string  
           self._webinfo = ["" for x in range(len(df.columns)*len(df.index))] #len(df.columns)*len(df.index)=9
           # row acess mode to Pandas dataframe
           k=0
           for j in [1,2,3]:
              for i in [1,2,3]:
                  self._webinfo[k]= str(df.loc[r_types[str(j)], c_types[str(i)]])
                  k+=1
            # check for update
           if self._webinfo[0] == Constants.app_version:
              labelweb3 = 'last version installed!' 
           else:
              labelweb3 = 'version {} available!'.format(self._webinfo[0]) 
              self.ui.pButton_Download.setEnabled(True)
        else:
           color = '#ff0000'
           labelweb2 = 'OFFLINE'
           labelweb3 = 'Offline, unable to check'
           print (TAG,'Checking your internet connection {} '.format(labelweb2)) 
           
        _set_data_value(self.ui.lweb2, labelweb2)
        if self._internet_connected:
            if hasattr(self.ui.lweb2, 'valueLabel'):
                self.ui.lweb2.valueLabel.setStyleSheet('color: #2e7d32; font-weight: bold;')
        else:
            if hasattr(self.ui.lweb2, 'valueLabel'):
                self.ui.lweb2.valueLabel.setStyleSheet('color: #c62828; font-weight: bold;')
        _set_data_value(self.ui.lweb3, labelweb3)  

    ###########################################################################
    # Firmware version check
    ###########################################################################
    def _check_firmware_version(self, auto_mode=False):
        """
        Query the device firmware version via serial command 'F'.
        :param auto_mode: If True, runs silently (no popup on success).
        """
        import time

        # Block if acquisition is running
        if self._is_running:
            PopUp.warning(self, Constants.app_title,
                "Cannot check firmware version during an active measurement.\n"
                "Please stop the acquisition first.")
            return

        # Block if serial not connected
        if not self._serial_connected or self._serial_lock is None:
            if not auto_mode:
                PopUp.warning(self, Constants.app_title,
                    "Serial port not connected.\n"
                    "Please connect to the device first.")
            return

        # Send firmware version request
        try:
            # Flush any residual data in the serial buffer
            self._serial_lock.reset_input_buffer()
            self._serial_lock.write(b'F\n')
            time.sleep(0.4)
            bytes_waiting = self._serial_lock.inWaiting()
            response = ""
            if bytes_waiting > 0:
                response = self._serial_lock.read(bytes_waiting).decode(Constants.app_encoding).strip()
            print(TAG, "Firmware version response: '{}'".format(response))
            Log.i(TAG, "Firmware version response: '{}'".format(response))
        except Exception as e:
            print(TAG, "Firmware version check failed: {}".format(e))
            Log.e(TAG, "Firmware version check failed: {}".format(e))
            if not auto_mode:
                PopUp.warning(self, Constants.app_title,
                    "Failed to communicate with device.\n\nError: {}".format(e))
            return

        expected = Constants.fw_version

        if response == "":
            # No response from firmware
            msg = ("The device firmware did not respond to the version request.\n"
                   "Expected firmware version: {}\n\n"
                   "Would you like to update the firmware?".format(expected))
            if PopUp.question(self, Constants.app_title, msg):
                self._run_firmware_updater()
            else:
                # Escalation: critical warning
                msg2 = ("WARNING: Running the software without the correct firmware "
                        "may cause malfunctions or incorrect measurements.\n\n"
                        "Would you like to proceed with the firmware update?")
                if PopUp.question(self, Constants.app_title, msg2):
                    self._run_firmware_updater()

        elif response != expected:
            # Wrong version
            msg = ("Firmware version {} detected.\n"
                   "Expected version: {}\n\n"
                   "Would you like to update the firmware?".format(response, expected))
            if PopUp.question(self, Constants.app_title, msg):
                self._run_firmware_updater()
            else:
                msg2 = ("WARNING: Running with an outdated firmware "
                        "may cause malfunctions or incorrect measurements.\n\n"
                        "Would you like to proceed with the firmware update?")
                if PopUp.question(self, Constants.app_title, msg2):
                    self._run_firmware_updater()

        else:
            # Version matches
            print(TAG, "Firmware version OK: {}".format(response))
            Log.i(TAG, "Firmware version OK: {}".format(response))
            if not auto_mode:
                PopUp.info(self, Constants.app_title,
                    "Firmware is up to date.\n\nInstalled version: {}".format(response))

    def _run_firmware_updater(self):
        """Launch the platform-specific firmware updater tool.
        Releases the serial port first so the updater can access the device."""
        import subprocess

        # Release serial port so the updater can access the device
        if self._serial_lock is not None:
            try:
                self._serial_lock.close()
                print(TAG, "Serial port released for firmware update")
                Log.i(TAG, "Serial port released for firmware update")
            except Exception as e:
                print(TAG, "Warning: Error closing serial port: {}".format(e))
            self._serial_lock = None
        self._release_port_lock()

        # Update UI to disconnected state
        self._serial_connected = False
        self._connected_port = None
        self.ui.pButton_Connect.setText("Connect")
        self._set_button_role(self.ui.pButton_Connect, "btnConnect")
        self.ui.cBox_Port.setEnabled(True)
        self.ui.pButton_Refresh.setEnabled(True)
        self.ui.pButton_StartStop.setEnabled(False)
        self.ui.set_connection_state(False)
        self.ui.infostatus.setText("Disconnected")
        self.ui.infobar.setText("Disconnected for firmware update")

        # firmware_update/ is at OPENQCM/firmware_update/ (sibling of openQCM/ package)
        updater_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "firmware_update")
        os_type = Architecture.get_os()
        try:
            if os_type == OSType.windows:
                updater_path = os.path.join(updater_dir, "TyUploader.exe")
                subprocess.Popen([updater_path])
            elif os_type == OSType.macosx:
                updater_path = os.path.join(updater_dir, "Teensy.app")
                subprocess.Popen(["open", updater_path])
            elif os_type == OSType.linux:
                updater_path = os.path.join(updater_dir, "Teensy")
                subprocess.Popen(["xdg-open", updater_path])
            else:
                PopUp.warning(self, Constants.app_title,
                    "Firmware updater not available for this platform.")
                return
            print(TAG, "Firmware updater launched: {}".format(updater_path))
            Log.i(TAG, "Firmware updater launched: {}".format(updater_path))
        except Exception as e:
            print(TAG, "Failed to launch firmware updater: {}".format(e))
            Log.e(TAG, "Failed to launch firmware updater: {}".format(e))
            PopUp.warning(self, Constants.app_title,
                "Could not launch firmware updater.\n\nError: {}".format(e))

    ###########################################################################
    # Check for updates (triggered from Help menu)
    ###########################################################################
    def _check_for_updates(self):
        """
        Check for software updates and update the Help menu accordingly.
        """
        self.get_web_info()

        # Update menu items based on result
        if self._internet_connected and hasattr(self, '_webinfo'):
            if self._webinfo[0] == Constants.app_version:
                self.ui.actionCheckUpdates.setText("Check for Updates (up to date)")
                self.ui.actionDownloadUpdate.setEnabled(False)
                PopUp.info(self, Constants.app_title,
                    "You have the latest version installed.\n\nCurrent version: {}".format(Constants.app_version))
            else:
                self.ui.actionCheckUpdates.setText("Check for Updates (v{} available)".format(self._webinfo[0]))
                self.ui.actionDownloadUpdate.setEnabled(True)
                self.ui.actionDownloadUpdate.setText("Download v{}".format(self._webinfo[0]))
                PopUp.info(self, Constants.app_title,
                    "New version available!\n\nCurrent: {}\nAvailable: {}\n\nUse Help → Download to get the new version.".format(
                        Constants.app_version, self._webinfo[0]))
        else:
            PopUp.warning(self, Constants.app_title,
                "Unable to check for updates.\nPlease verify your internet connection.")

    ###########################################################################
    # Opens webpage for download
    ###########################################################################
    def start_download(self):
        import webbrowser
        if hasattr(self, '_webinfo') and self._webinfo:
            url_download = 'https://openqcm.com/shared/q-1/openQCM_Q-1_py_v{}.zip '.format(self._webinfo[0])
            webbrowser.open(url_download)
        else:
            # If webinfo not available, go to main download page
            webbrowser.open('https://openqcm.com/downloads')
        
       