
from openQCM.ui.mainWindow_ui import Ui_Main

from pyqtgraph import AxisItem
import pyqtgraph as pg
from PyQt5 import QtCore, QtGui, QtWidgets
from openQCM.core.worker import Worker
from openQCM.core.constants import Constants, SourceType, DateAxis, NonScientificAxis, OneDecimalAxis, ElapsedTimeAxis
from openQCM.ui.popUp import PopUp
from openQCM.common.logger import Logger as Log
import numpy as np
import sys
import os
from datetime import datetime

TAG = ""#"[MainWindow]"

##########################################################################################
# Stream redirector class to capture print output and send to QTextEdit
##########################################################################################
class LogStream:
    """Redirects stdout/stderr to a QTextEdit widget while preserving original output"""
    def __init__(self, text_widget, original_stream):
        self.text_widget = text_widget
        self.original_stream = original_stream

    def write(self, text):
        # Write to original stream (terminal)
        if self.original_stream:
            self.original_stream.write(text)
        # Write to QTextEdit (skip empty strings and carriage returns)
        if text and text.strip() and text != '\r':
            timestamp = datetime.now().strftime("[%H:%M:%S] ")
            # Use invokeMethod for thread safety
            QtCore.QMetaObject.invokeMethod(
                self.text_widget, "append",
                QtCore.Qt.QueuedConnection,
                QtCore.Q_ARG(str, timestamp + text.rstrip())
            )

    def flush(self):
        if self.original_stream:
            self.original_stream.flush()

##########################################################################################
# Package that handles the UIs elements and connects to worker service to execute processes
# UNIFIED SINGLE WINDOW VERSION - Minimal Scientific Interface
##########################################################################################

def _set_data_value(widget, value):
    """Helper to set value on data row widgets (QWidget with valueLabel attribute)"""
    if hasattr(widget, 'valueLabel'):
        widget.valueLabel.setText(str(value))
    elif hasattr(widget, 'setText'):
        widget.setText(str(value))

def _extract_value(html_text):
    """Extract the value part from HTML formatted text like '<font color=...>Label</font> Value'"""
    if '>' in html_text and '</font>' in html_text:
        # Find text after last </font>
        parts = html_text.split('</font>')
        if len(parts) > 1:
            return parts[-1].strip()
    return html_text


class MainWindow(QtGui.QMainWindow):

    ###########################################################################
    # Initializes methods, values and sets the UI
    ###########################################################################
    def __init__(self, samples=Constants.argument_default_samples):

        #:param samples: Default samples shown in the plot :type samples: int.
        # to be always placed at the beginning, initializes some important methods
        QtGui.QMainWindow.__init__(self)

        # Sets up the unified user interface
        self.ui = Ui_Main()
        self.ui.setupUi(self)
        self.show()

        # =============================================================================
        # SYSTEM LOG: Redirect stdout/stderr to System Log tab
        # This captures all print() statements and displays them in the GUI
        # =============================================================================
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

        # =============================================================================
        # CPU OPTIMIZATION: Persistent curve objects for efficient plot updates
        # Development note: Instead of calling clear() + plot() on each timer tick,
        # we create curve objects once and reuse them with setData(). This avoids
        # continuous memory allocation/deallocation and significantly reduces CPU usage.
        # See _configure_plot() for initialization and _update_plot() for usage.
        # =============================================================================
        self._curve_amplitude = None      # Amplitude curve (plt0)
        self._curve_phase = None          # Phase curve (plt1)
        self._curve_frequency = None      # Resonance frequency curve (plt2)
        self._curve_dissipation = None    # Dissipation curve (plt3)
        self._curve_temperature = None    # Temperature curve (plt4)

        # Theme-specific curve color (only temperature changes with theme)
        self._theme_temp_color = None

        # =============================================================================
        # RESIZE OPTIMIZATION: Pause plot updates during window resize
        # This prevents GUI lag by temporarily stopping expensive redraw operations
        # =============================================================================
        self._is_resizing = False
        self._resize_timer = QtCore.QTimer()
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._on_resize_finished)

        # internet connection variable
        self._internet_connected = False

        # =============================================================================
        # SERIAL CONNECTION: State management for Connect/Disconnect button
        # The serial port is now explicitly connected/disconnected by user action,
        # independent of the measurement mode selection.
        # The serial port is kept open (locked) until Disconnect is pressed.
        # =============================================================================
        self._serial_connected = False
        self._connected_port = None
        self._serial_lock = None  # Serial object to keep port open
        self._lock_file = None    # File lock for exclusive access

        # Reference variables
        self._reference_flag = False
        self._vector_reference_frequency = None
        self._vector_reference_dissipation = None
        self._vector_1 = None
        self._vector_2 = None

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
        self.ui.cBox_Source.setCurrentIndex(SourceType.serial.value)
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
        self.worker = Worker(QCS_on = self._QCS_installed,
                             port = port,
                             speed = self.ui.cBox_Speed.currentText(),
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
                overtones_number = len(self.worker.get_source_speeds(SourceType.serial))
                # TODO set the quartz sensor 
                '''
                if overtones_number==5:
                   label_quartz = "5 MHz QCM"
                elif overtones_number==3:
                   label_quartz = "10 MHz QCM"
                '''
                if ( float(self.worker.get_source_speeds(SourceType.serial)[overtones_number-1])>4e+06 and float(self.worker.get_source_speeds(SourceType.serial)[overtones_number-1])<6e+06):
                   label_quartz = "5 MHz QCM"
                elif (float(self.worker.get_source_speeds(SourceType.serial)[overtones_number-1])>9e+06 and float(self.worker.get_source_speeds(SourceType.serial)[overtones_number-1])<11e+06):
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
                label_quartz = self.ui.cBox_Speed.currentText()
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
        #:param evnt: QT evnt.

        # Prevent double close dialog - check if already closing
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
            evnt.accept()
        else:
            evnt.ignore()
    
          
    ###########################################################################
    # Enables or disables the UI elements of the window.
    ###########################################################################
    def _enable_ui(self, enabled):

        #:param enabled: The value to be set for the UI elements :type enabled: bool
        # Port and Refresh are controlled by Connect button state
        # Only enable if not connected AND ui is enabled
        if not self._serial_connected:
            self.ui.cBox_Port.setEnabled(enabled)
            self.ui.pButton_Refresh.setEnabled(enabled)
        self.ui.cBox_Speed.setEnabled(enabled)
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
        # Amplitude curve (will be updated with setData in _update_plot)
        self._curve_amplitude = self._plt0.plot(pen=Constants.plot_colors[0], name='Amplitude')
        # Phase curve (ViewBox item) - added to legend manually
        self._curve_phase = pg.PlotCurveItem(pen=Constants.plot_colors[1], name='Phase')
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
        # Help menu actions (Check for Updates, Download Update)
        self.ui.actionCheckUpdates.triggered.connect(self._check_for_updates)
        self.ui.actionDownloadUpdate.triggered.connect(self.start_download)
        #--------
        # Cursors toggle (View menu)
        self.ui.actionToggleCursors.triggered.connect(self._toggle_cursors)
        #--------
        # Data menu actions
        self.ui.actionDataView.triggered.connect(self._open_data_viewer)
        self.ui.actionRawDataView.triggered.connect(self._open_raw_data_viewer)

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
            #print(self._ser_err_usb, end='\r')
            #if self._ser_err_usb <=1:
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
                      if self._ser_error1 and self._ser_error2:
                        label1= ""
                        label2= ""
                        label3= ""
                        labelstatus = 'Warning'
                        color_err = '#ff0000'
                        labelbar = 'Warning: unable to apply half-power bandwidth method, lower and upper cut-off frequency not found'
                        self.ui.infostatus.setStyleSheet('background: #ff0000; padding: 1px; border: 1px solid #cccccc')
                      elif self._ser_error1:
                        label1= ""
                        label2= ""
                        label3= ""
                        labelstatus = 'Warning'
                        color_err = '#ff0000'
                        labelbar = 'Warning: unable to apply half-power bandwidth method, lower cut-off frequency (left side) not found'
                        self.ui.infostatus.setStyleSheet('background: #ff0000; padding: 1px; border: 1px solid #cccccc')
                      elif self._ser_error2:
                        label1= ""
                        label2= ""
                        label3= ""
                        labelstatus = 'Warning'
                        color_err = '#ff0000'
                        labelbar = 'Warning: unable to apply half-power bandwidth method, upper cut-off frequency (right side) not found'
                        self.ui.infostatus.setStyleSheet('background: #ff0000; padding: 1px; border: 1px solid #cccccc')
               else:
                  if not self._ser_error1 and not self._ser_error2:
                      if not self._reference_flag:
                          d1=float("{0:.1f}".format(vector1[0]))
                          d2=float("{0:.2f}".format(vector2[0]*1e6))
                          d3=float("{0:.1f}".format(vectortemp[0]))
                      else:
                          a1= vector1[0]-self._reference_value_frequency
                          a2= vector2[0]-self._reference_value_dissipation
                          d1=float("{0:.1f}".format(a1))
                          d2=float("{0:.2f}".format(a2*1e6))
                          d3=float("{0:.1f}".format(vectortemp[0]))
                      label1= str(d1)+ " Hz"
                      label2= str(d2)+ "e-06"
                      label3= str(d3)+ " °C" 
                      labelstatus = 'Monitoring'
                      color_err = '#000000'
                      labelbar = 'Monitoring!'
                      self.ui.infostatus.setStyleSheet('background: #00ff72; padding: 1px; border: 1px solid #cccccc')
                  else:
                      if self._ser_error1 and self._ser_error2:
                        label1= "-"
                        label2= "-"
                        label3= "-"
                        labelstatus = 'Warning'
                        color_err = '#ff0000'
                        labelbar = 'Warning: unable to apply half-power bandwidth method, lower and upper cut-off frequency not found'
                        self.ui.infostatus.setStyleSheet('background: #ff0000; padding: 1px; border: 1px solid #cccccc')
                      elif self._ser_error1:
                        label1= "-"
                        label2= "-"
                        label3= "-"
                        labelstatus = 'Warning'
                        color_err = '#ff0000'
                        labelbar = 'Warning: unable to apply half-power bandwidth method, lower cut-off frequency (left side) not found'
                        self.ui.infostatus.setStyleSheet('background: #ff0000; padding: 1px; border: 1px solid #cccccc')
                      elif self._ser_error2:
                        label1= "-"
                        label2= "-"
                        label3= "-"
                        labelstatus = 'Warning'
                        color_err = '#ff0000'
                        labelbar = 'Warning: unable to apply half-power bandwidth method, upper cut-off frequency (right side) not found'
                        self.ui.infostatus.setStyleSheet('background: #ff0000; padding: 1px; border: 1px solid #cccccc')
                         
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
               # progressbar 
               self.ui.progressBar.setValue(self._completed+2)
            
            #elif self._ser_err_usb >1:
                # PopUp.warning(self, Constants.app_title, "Warning: USB cable device disconnected!")  
                # self.stop() 
        
        # CALIBRATION: dynamic info in infobar at run-time
        ##################################################
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

            # progressbar
            error1,error2,error3,self._ser_control = self.worker.get_ser_error()
            if self._ser_control< (Constants.calib_sections):
                      self._completed = (self._ser_control/(Constants.calib_sections))*100
            # calibration buffer empty
            #if vector1[0]== 0 and vector3[0]==1:
            if error1== 1 and vector3[0]==1:
              label1 = 'not available'
              label2 = 'not available'
              label3 = 'not available'
              color_err = '#ff0000'
              labelstatus = 'Peak Detection Warning'
              self.ui.infostatus.setStyleSheet('background: #ff0000; padding: 1px; border: 1px solid #cccccc')
              labelbar = 'empty buffer — Reconnect device and retry.'
              stop_flag=1
            # calibration buffer empty and ValueError from the serial port
            #elif vector1[0]== 0 and vector2[0]==1:
            elif error1== 1 and vector2[0]==1:
              label1 = 'not available'
              label2 = 'not available'
              label3 = 'not available'
              color_err = '#ff0000'
              labelstatus = 'Peak Detection Warning'
              self.ui.infostatus.setStyleSheet('background: #ff0000; padding: 1px; border: 1px solid #cccccc')
              labelbar = 'empty buffer / value error — Reconnect device and retry.'
              stop_flag=1
            # calibration buffer not empty
            #elif vector1[0]!= 0:
            elif error1==0:
              label1 = 'not available'
              label2 = 'not available'
              label3 = 'not available'
              labelstatus = 'Peak Detection Processing'
              color_err = '#000000'
              labelbar = 'please wait...'
              if vector2[0]== 0 and vector3[0]== 0:
                 labelstatus = 'Peak Detection Success'
                 self.ui.infostatus.setStyleSheet('background: #00ff72; padding: 1px; border: 1px solid #cccccc')
                 color_err = '#000000'
                 labelbar = 'peak detection completed — ready for baseline correction'
                 stop_flag=1
                 #print(self._k) #progressbar value 143
              elif vector2[0]== 1 or vector3[0]== 1:
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
                       freq_list = "\n".join(["{:.0f} Hz".format(f) for f in peaks])
                       msg = "{} peak frequencies found:\n\n{}".format(len(peaks), freq_list)
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
        '''
        # Amplitude plot
        self._plt0.clear()
        #self._plt0.plot(list(self._xdict.keys()),self.worker.get_value1_buffer(),pen=Constants.plot_colors[0])
        self._plt0.plot(self.worker.get_value1_buffer(),pen=Constants.plot_colors[0])
        
        # Phase plot
        self._plt1.clear()
        self._plt1.plot(self.worker.get_value2_buffer(),pen=Constants.plot_colors[1])
        '''
        ############################################################################################################################
        # REFERENCE SET
        # =============================================================================
        # CPU OPTIMIZATION: Using setData() on persistent curve objects instead of
        # clear() + plot(). This reuses existing curve objects, avoiding continuous
        # memory allocation/deallocation on each timer tick (every 200ms).
        # =============================================================================
        ############################################################################################################################
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

            ###################################################################
            # Temperature plot - using setData() for efficiency
            t3_buffer = self.worker.get_t3_buffer()
            self._curve_temperature.setData(x=t3_buffer, y=self.worker.get_d3_buffer())
            # Set start time for elapsed time axis from first valid (non-NaN) data point
            if len(t3_buffer) > 0:
                # Find first non-NaN value
                valid_mask = ~np.isnan(t3_buffer)
                if np.any(valid_mask):
                    first_valid = t3_buffer[valid_mask][0]
                    self._xaxis_temp.set_start_time(first_valid)
            # Temperature color: always use theme color (white for dark, black for light)
            # Does NOT change when Reference is pressed
            temp_color = self._theme_temp_color if self._theme_temp_color else '#ffffff'
            self._curve_temperature.setPen(temp_color)

        ###########################################################################################################################
        # REFERENCE NOT SET
        # =============================================================================
        # CPU OPTIMIZATION: Using setData() on persistent curve objects instead of
        # clear() + plot(). This reuses existing curve objects, avoiding continuous
        # memory allocation/deallocation on each timer tick (every 200ms).
        # =============================================================================
        ###########################################################################################################################
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
            self._curve_dissipation.setData(x=self.worker.get_t2_buffer(), y=self.worker.get_d2_buffer())

            ##############################
            # Add  lines with labels
            #inf1 = pg.InfiniteLine(movable=True, angle=90, label='x={value:0.2f}',
            #self._plt2.addItem(self._inf1)
            #self._plt2.addItem(self._lr)
            ##############################
            '''
            # Resonance frequency plot
            self._plt2.clear()
            self._plt2.plot(x= self.worker.get_t1_buffer(),y=self.worker.get_d1_buffer(),pen=Constants.plot_colors[2])
            # dissipation plot
            self._plt3.clear()
            self._plt3.plot(x= self.worker.get_t2_buffer(),y=self.worker.get_d2_buffer(),pen=Constants.plot_colors[3])
            '''
            ###################################################################
            # Temperature plot - using setData() for efficiency
            t3_buffer = self.worker.get_t3_buffer()
            self._curve_temperature.setData(x=t3_buffer, y=self.worker.get_d3_buffer())
            # Set start time for elapsed time axis from first valid (non-NaN) data point
            if len(t3_buffer) > 0:
                # Find first non-NaN value
                valid_mask = ~np.isnan(t3_buffer)
                if np.any(valid_mask):
                    first_valid = t3_buffer[valid_mask][0]
                    self._xaxis_temp.set_start_time(first_valid)     
          
    ###########################################################################################################################################

    ###########################################################################
    # AUTO-TRACKING: Handle tracking state changes and update GUI
    ###########################################################################
    def _handle_auto_tracking(self):
        """
        Check if auto-tracking has been triggered and update the GUI accordingly.
        Updates the X-axis of the Amplitude/Phase plot and shows notifications.
        """
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

        # If serial is connected, don't change port selection
        if self._serial_connected:
            # Only update speed options, keep port unchanged
            self.ui.cBox_Speed.clear()
            source = self._get_source()
            speeds = self.worker.get_source_speeds(source)
            if speeds is not None:
                self.ui.cBox_Speed.addItems(speeds)
            if self._get_source() == SourceType.serial:
                self.ui.cBox_Speed.setCurrentIndex(len(speeds) - 1)
            return

        # Not connected - populate both port and speed
        self.ui.cBox_Port.clear()
        self.ui.cBox_Speed.clear()

        source = self._get_source()
        ports = self.worker.get_source_ports(source)
        speeds = self.worker.get_source_speeds(source)

        if ports is not None:
            self.ui.cBox_Port.addItems(ports)
        if speeds is not None:
            self.ui.cBox_Speed.addItems(speeds)
        if self._get_source() == SourceType.serial:
            self.ui.cBox_Speed.setCurrentIndex(len(speeds) - 1)

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

        # Update temperature curve color based on theme
        # Frequency and Dissipation colors remain constant across themes
        if theme == 'light':
            self._theme_temp_color = '#000000'      # Black for temperature in light mode
        else:
            self._theme_temp_color = '#ffffff'      # White for temperature in dark mode

        self._curve_temperature.setPen(self._theme_temp_color)

        print(TAG, f"Theme switched to: {theme}", end='\r')
    
    
    ###########################################################################
    # Cleans history plot
    # CPU OPTIMIZATION: Clear curves by setting empty data instead of
    # recreating the entire plot structure with clear()
    ###########################################################################
    def clear(self):
        support=self.worker.get_d1_buffer()
        if support.any:
            if str(support[0])!='nan':
                print(TAG, "All Plots Cleared!", end='\r')
                self._update_sample_size()
                # CPU OPTIMIZATION: Reset curve data instead of clearing entire plots
                # This preserves the persistent curve objects for reuse
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
                    d2=float("{0:.4f}".format(self._reference_value_dissipation*1e6))
                    self._labelref1 = str(d1)+ "Hz"
                    self._labelref2 = str(d2)+ "e-06"
                    print(TAG, "Reference set!     ", end='\r')
                    self._vector_reference_frequency[:] = [s - self._reference_value_frequency for s in self._readFREQ]
                    xs = np.array(np.linspace(0, ((self._readFREQ[-1]-self._readFREQ[0])/self._readFREQ[0]), len(self._readFREQ)))
                    self._vector_reference_dissipation = xs-self._reference_value_dissipation
                    
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
        delta_t = abs(t2 - t1)
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
            viewer = DataViewerDialog(self, csv_path=csv_path, theme=theme)
            viewer.show()

    ###########################################################################
    # Opens Raw Data View dialog showing live amplitude/phase sweep curves
    ###########################################################################
    def _open_raw_data_viewer(self):
        from openQCM.ui.mainWindow_ui import RawDataViewDialog
        theme = 'dark' if self.ui.actionDarkTheme.isChecked() else 'light'
        viewer = RawDataViewDialog(self, main_window=self, theme=theme)
        viewer.show()

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
        import pandas as pd
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
        
       