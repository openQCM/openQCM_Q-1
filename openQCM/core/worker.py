"""
Worker — bridge between the Qt GUI (main process) and the acquisition
child process (SerialProcess or CalibrationProcess).

The Worker:
    1. Owns the multiprocessing queues that the child process writes into.
    2. Polls those queues from the GUI timer (via `consume_queue*`) and
       updates internal ring buffers consumed by the plot widgets.
    3. Manages the lifecycle of the child process (start / stop / join).
    4. Owns the persistent CSV log file: opens it on START, writes one row
       per sweep, flushes periodically, closes on STOP.
    5. Handles auto-tracking notifications coming from the Serial process
       (window-update events and disable/re-enable safety transitions).
"""
import os
import csv
from multiprocessing import Queue
from time import strftime, localtime

import numpy as np

from openQCM.core.constants import Constants, SourceType
from openQCM.core.ringBuffer import RingBuffer
from openQCM.processors.Parser import ParserProcess
from openQCM.processors.Serial import SerialProcess
from openQCM.processors.SocketClient import SocketProcess
from openQCM.processors.Calibration import CalibrationProcess
from openQCM.common.fileStorage import FileStorage
from openQCM.common.fileManager import FileManager
from openQCM.common.logger import Logger as Log


TAG = ""  # set to "[Worker]" for verbose tagged prints


class Worker:
    """Coordinator that ties together the GUI and the acquisition processes."""

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def __init__(self, QCS_on=None,
                 port=None,
                 speed=Constants.serial_default_overtone,
                 samples=Constants.argument_default_samples,
                 source=SourceType.serial,
                 export_enabled=False):
        """
        :param QCS_on:         Quartz Crystal Sensor type label (informational)
        :param port:           Serial port to open at start
        :param speed:          Overtone frequency (Hz) for measurement, or
                               sensor-type label for calibration
        :param samples:        Samples per sweep (for measurement mode)
        :param source:         SourceType.serial | calibration | SocketClient
        :param export_enabled: When True, raw sweep dumps are also written
                               to disk in addition to the CSV log
        """
        # Inter-process queues (one per data channel + one for tracking events)
        self._queue1 = Queue()           # raw amplitude trace
        self._queue2 = Queue()           # raw phase trace
        self._queue3 = Queue()           # smoothed resonance frequency
        self._queue4 = Queue()           # smoothed dissipation
        self._queue5 = Queue()           # smoothed temperature
        self._queue6 = Queue()           # error flags / status
        self._queue_tracking = Queue()   # auto-tracking notifications

        # Per-sweep buffers (overwritten on each push from the queue)
        self._data1_buffer = None        # latest amplitude trace
        self._data2_buffer = None        # latest phase trace

        # Long-history ring buffers feeding the time-series plots
        self._d1_buffer = self._d2_buffer = self._d3_buffer = None
        self._t1_buffer = self._t2_buffer = self._t3_buffer = None

        # Status / error mirrors of the Serial process state
        self._ser_error1 = 0
        self._ser_error2 = 0
        self._ser_err_usb = 0
        self._control_k = 0
        self._sampling_time = 0.0
        self._calibration_cancelled = False

        # Auto-tracking state mirrored from SerialProcess
        self._tracking_activated = False
        self._tracking_start_freq = None
        self._tracking_stop_freq = None
        self._tracking_ref_freq = None
        self._tracking_count = 0
        self._tracking_disabled_by_errors = False
        self._tracking_disabled_notified = False
        self._tracking_reenabled_pending = False

        # Child process handles
        self._acquisition_process = None
        self._parser_process = None

        # Configuration set by the constructor
        self._QCS_on = QCS_on
        self._port = port
        self._speed = speed                  # overtone (Hz) or sensor label
        self._samples = samples
        self._source = source
        self._export = export_enabled

        # Per-sweep latest values (also forwarded to the CSV log)
        self._d1_store = self._d2_store = None
        self._t1_store = self._t2_store = self._t3_store = 0
        self._readFREQ = None
        self._fStep = None
        self._overtone_name = None
        self._overtone_value = None
        self._count = 0                      # raw-sweep dump counter
        self._flag = True                    # latches the start time on first valid sample
        self._timestart = 0
        self._csv_filename = None            # built at start() with current timestamp
        self._spline_factor = None           # spline smoothing factor of selected overtone

        # Persistent CSV log: opened once at start, flushed periodically
        self._csv_file = None
        self._csv_writer = None
        self._flush_counter = 0
        self._flush_interval = 30            # ≈30 sweeps ≈ a few seconds between disk syncs

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self):
        """
        Start the parser process and the chosen acquisition process.

        Generates a fresh CSV filename with the current timestamp and opens
        the persistent log file (measurement mode only).

        :return: True if the acquisition started successfully
        """
        # Fresh log filename per START press: YYYY-MM-DD_hh-mm-ss
        self._csv_filename = strftime(Constants.csv_default_prefix, localtime())

        # Measurement mode requires a previous Peak Detection. Bail out early
        # with a clear log message instead of crashing when the calibration
        # files are missing (typical first-run state of a fresh install).
        if self._source == SourceType.serial:
            import os
            if not os.path.isfile(Constants.cvs_peakfrequencies_path):
                print(TAG, "Cannot start Measurement: PeakFrequencies.txt is missing. "
                           "Run Peak Detection first.")
                Log.w(TAG, "Cannot start Measurement: PeakFrequencies.txt is missing")
                return False

        if self._source == SourceType.serial:
            self._samples = Constants.argument_default_samples
        elif self._source == SourceType.calibration:
            self._samples = Constants.calibration_default_samples
            self._readFREQ = Constants.calibration_readFREQ
        self.reset_buffers(self._samples)

        self._parser_process = ParserProcess(
            self._queue1, self._queue2, self._queue3,
            self._queue4, self._queue5, self._queue6,
            self._queue_tracking)

        if self._source == SourceType.serial:
            self._acquisition_process = SerialProcess(self._parser_process)
        elif self._source == SourceType.calibration:
            self._acquisition_process = CalibrationProcess(self._parser_process)
        elif self._source == SourceType.SocketClient:
            self._acquisition_process = SocketProcess(self._parser_process)

        if not self._acquisition_process.open(port=self._port, speed=self._speed):
            print(TAG, 'Warning: port is not available')
            Log.i(TAG, "Warning: Port is not available")
            return False

        if self._source == SourceType.serial:
            (self._overtone_name, self._overtone_value,
             self._fStep, self._readFREQ,
             SG_window_size, spline_points,
             spline_factor) = self._acquisition_process.get_frequencies(self._samples)
            self._spline_factor = spline_factor
            print("")
            print(TAG, "DATA MAIN INFORMATION")
            print(TAG, "Selected frequency: {} - {}Hz".format(self._overtone_name, self._overtone_value))
            print(TAG, "Frequency start: {}Hz".format(self._readFREQ[0]))
            print(TAG, "Frequency stop:  {}Hz".format(self._readFREQ[-1]))
            print(TAG, "Frequency range: {}Hz".format(self._readFREQ[-1] - self._readFREQ[0]))
            print(TAG, "Number of samples: {}".format(self._samples - 1))
            print(TAG, "Sample rate: {}Hz".format(self._fStep))
            print(TAG, "MAIN PROCESSING INFORMATION")
            print(TAG, "Method for baseline estimation and correction:")
            print(TAG, "Least Squares Polynomial Fit (LSP)")
            print(TAG, "Savitzky-Golay Filtering")
            print(TAG, "Order of the polynomial fit: {}".format(Constants.SG_order))
            print(TAG, "Size of data window (in samples): {}".format(SG_window_size))
            print(TAG, "Oversampling using spline interpolation")
            print(TAG, "Spline points (in samples): {}".format(spline_points - 1))
            print(TAG, "Resolution after oversampling: {}Hz".format(
                (self._readFREQ[-1] - self._readFREQ[0]) / (spline_points - 1)))
        elif self._source == SourceType.calibration:
            print("")
            print(TAG, "MAIN PEAK DETECTION INFORMATION")
            print(TAG, "Peak Detection frequency start:  {}Hz".format(Constants.calibration_frequency_start))
            print(TAG, "Peak Detection frequency stop:   {}Hz".format(Constants.calibration_frequency_stop))
            print(TAG, "Frequency range: {}Hz".format(
                Constants.calibration_frequency_stop - Constants.calibration_frequency_start))
            print(TAG, "Number of samples: {}".format(Constants.calibration_default_samples - 1))
            print(TAG, "Sample rate: {}Hz".format(Constants.calibration_fStep))

        print(TAG, 'Training for plot...\n')
        self._acquisition_process.start()
        self._parser_process.start()

        # Open the CSV log only for measurement mode
        if self._source == SourceType.serial:
            self._open_csv_file()

        return True

    def stop(self):
        """Stop both processes and close the CSV log."""
        self._acquisition_process.stop()
        self._parser_process.stop()
        self._close_csv_file()
        print(TAG, 'Running processes stopped...')
        print(TAG, 'Processes finished')
        Log.i(TAG, "Running processes stopped...")
        Log.i(TAG, "Processes finished")

    def wait_for_process(self, timeout=5.0):
        """
        Wait up to `timeout` seconds for the acquisition process to finish.
        Force-terminate if it does not exit cleanly.
        """
        if self._acquisition_process is None or not self._acquisition_process.is_alive():
            return
        print(TAG, "Waiting for acquisition process to terminate...")
        self._acquisition_process.join(timeout=timeout)
        if self._acquisition_process.is_alive():
            print(TAG, "WARNING: Process did not terminate, forcing...")
            Log.w(TAG, "Acquisition process did not terminate, forcing...")
            self._acquisition_process.terminate()
            self._acquisition_process.join(timeout=2.0)
        print(TAG, "Acquisition process terminated")
        Log.i(TAG, "Acquisition process terminated")

    def is_running(self):
        return self._acquisition_process is not None and self._acquisition_process.is_alive()

    # ------------------------------------------------------------------
    # Queue draining (called from the GUI timer on each plot update)
    # ------------------------------------------------------------------
    def consume_queue1(self):
        """Drain the amplitude queue."""
        while not self._queue1.empty():
            self._queue_data1(self._queue1.get(False))

    def consume_queue2(self):
        """Drain the phase queue."""
        while not self._queue2.empty():
            self._queue_data2(self._queue2.get(False))

    def consume_queue3(self):
        """Drain the resonance-frequency queue."""
        while not self._queue3.empty():
            self._queue_data3(self._queue3.get(False))

    def consume_queue4(self):
        """Drain the dissipation queue."""
        while not self._queue4.empty():
            self._queue_data4(self._queue4.get(False))

    def consume_queue5(self):
        """Drain the temperature queue."""
        while not self._queue5.empty():
            self._queue_data5(self._queue5.get(False))

    def consume_queue6(self):
        """Drain the status / error queue."""
        while not self._queue6.empty():
            self._queue_data6(self._queue6.get(False))

    def consume_queue_tracking(self):
        """Drain the auto-tracking notifications queue."""
        while not self._queue_tracking.empty():
            self._queue_data_tracking(self._queue_tracking.get(False))

    # Per-channel handlers (invoked by the consume_queue* loops above).
    def _queue_data1(self, data):
        self._data1_buffer = data

    def _queue_data2(self, data):
        self._data2_buffer = data

    def _queue_data3(self, data):
        self._t1_store = data[0]
        self._d1_store = data[1]
        self._t1_buffer.append(data[0])
        self._d1_buffer.append(data[1])

    def _queue_data4(self, data):
        self._t2_store = data[0]
        self._d2_store = data[1]
        self._t2_buffer.append(data[0])
        self._d2_buffer.append(data[1])

    def _queue_data5(self, data):
        # CalibrationProcess uses time = -1 as a "user cancelled" sentinel
        if data[0] == -1:
            self._calibration_cancelled = True
        self._t3_store = data[0]
        self._d3_store = data[1]
        self._t3_buffer.append(data[0])
        self._d3_buffer.append(data[1])
        # Latch the acquisition start timestamp on the first valid sample
        if self._flag and ~np.isnan(self._d3_store):
            self._timestart = data[0]
            self._flag = False
        # Persist the row to the CSV log (measurement mode only)
        self.store_data()

    def _queue_data6(self, data):
        self._ser_error1 = data[0]
        self._ser_error2 = data[1]
        self._control_k = data[2]
        self._ser_err_usb = data[3]
        if len(data) > 4:
            self._sampling_time = data[4]

    def _queue_data_tracking(self, data):
        """
        Process an auto-tracking notification.

        Payload format:
            [activated, start_freq, stop_freq, ref_freq, count,
             disabled_by_errors?]

        - activated=True   → window updated, refresh the GUI display
        - disabled_by_errors transitions are detected by comparing the
          incoming flag with the locally cached state, so the GUI can show
          a one-shot "Tracking Stopped" / "Tracking Resumed" message.
        """
        self._tracking_activated = data[0]
        self._tracking_start_freq = data[1]
        self._tracking_stop_freq = data[2]
        self._tracking_ref_freq = data[3]
        self._tracking_count = data[4]

        if len(data) > 5:
            new_disabled = bool(data[5])
            if new_disabled and not self._tracking_disabled_by_errors:
                # Transition: enabled → disabled
                self._tracking_disabled_by_errors = True
                self._tracking_disabled_notified = False
            elif (not new_disabled) and self._tracking_disabled_by_errors:
                # Transition: disabled → re-enabled (automatic recovery)
                self._tracking_disabled_by_errors = False
                self._tracking_reenabled_pending = True

        # When tracking activates, rebuild the local frequency axis so that
        # raw-sweep storage and Raw Data View use the new window.
        if self._tracking_activated:
            samples = self._samples
            fStep = (self._tracking_stop_freq - self._tracking_start_freq) / (samples - 1)
            self._readFREQ = np.arange(samples) * fStep + self._tracking_start_freq
            self._fStep = fStep

    # ------------------------------------------------------------------
    # Buffer accessors used by the GUI plots
    # ------------------------------------------------------------------
    def get_value1_buffer(self):
        """Last full amplitude trace (one sweep)."""
        return self._data1_buffer

    def get_value2_buffer(self):
        """Last full phase trace (one sweep)."""
        return self._data2_buffer

    def get_d1_buffer(self):
        """Resonance-frequency time series (ring buffer)."""
        return self._d1_buffer.get_all()

    def get_t1_buffer(self):
        """Timestamps matching `get_d1_buffer()`."""
        return self._t1_buffer.get_all()

    def get_d2_buffer(self):
        """Dissipation time series (ring buffer)."""
        return self._d2_buffer.get_all()

    def get_t2_buffer(self):
        """Timestamps matching `get_d2_buffer()`."""
        return self._t2_buffer.get_all()

    def get_d3_buffer(self):
        """Temperature time series (ring buffer)."""
        return self._d3_buffer.get_all()

    def get_t3_buffer(self):
        """Timestamps matching `get_d3_buffer()`."""
        return self._t3_buffer.get_all()

    def get_ser_error(self):
        """Latest -3dB / status flags from SerialProcess."""
        return self._ser_error1, self._ser_error2, self._control_k, self._ser_err_usb

    def get_sampling_time(self):
        """Last measured sweep period in seconds."""
        return self._sampling_time

    def is_calibration_cancelled(self):
        return self._calibration_cancelled

    def get_tracking_state(self):
        """
        One-shot snapshot of the latest auto-tracking event.

        The `activated` flag self-clears after each read so the GUI
        notification flashes only once per event.

        :return: (activated, start_freq, stop_freq, ref_freq, count)
        """
        activated = self._tracking_activated
        self._tracking_activated = False
        return (activated,
                self._tracking_start_freq,
                self._tracking_stop_freq,
                self._tracking_ref_freq,
                self._tracking_count)

    def get_tracking_disabled(self):
        """
        Auto-tracking safety state for GUI notifications.

        :return: (disabled, first_disabled, reenabled)
            - disabled       — True while tracking is currently disabled
            - first_disabled — True only on the first read after the disable
                               transition (one-shot for the GUI)
            - reenabled      — True only on the first read after the
                               automatic re-enable transition
        """
        disabled = self._tracking_disabled_by_errors
        first_disabled = disabled and not self._tracking_disabled_notified
        if first_disabled:
            self._tracking_disabled_notified = True
        reenabled = self._tracking_reenabled_pending
        if reenabled:
            self._tracking_reenabled_pending = False
        return disabled, first_disabled, reenabled

    def reset_tracking_disabled(self):
        """Reset tracking-safety state (called when the user presses START)."""
        self._tracking_disabled_by_errors = False
        self._tracking_disabled_notified = False
        self._tracking_reenabled_pending = False

    def get_frequency_range(self):
        """Current sweep frequency axis (Hz array)."""
        return self._readFREQ

    def get_overtone(self):
        """(name, value, fStep) of the currently selected overtone."""
        return self._overtone_name, self._overtone_value, self._fStep

    def get_spline_factor(self):
        """Spline smoothing factor used for the current overtone."""
        return self._spline_factor

    # ------------------------------------------------------------------
    # CSV log persistence
    # ------------------------------------------------------------------
    def store_data(self):
        """
        Append the latest sample to the persistent CSV log and, if raw
        sweep export is enabled, dump the current sweep to a TXT file too.

        Called from `_queue_data5()` once per sweep (data on temperature
        queue arrives last, so all values are available at this point).
        """
        if self._source != SourceType.serial:
            return

        # CSV row: relative time is in seconds since the latched start
        relative_time_s = (self._t3_store - self._timestart) / 1e6
        self._write_csv_row(relative_time_s, self._d3_store,
                            self._d1_store, self._d2_store, self._t3_store)

        if self._export:
            filename = "{}_{}_{}".format(
                Constants.csv_sweeps_filename, self._overtone_name, self._count)
            sweep_export_path = os.path.join(Constants.csv_export_path, self._csv_filename)
            path = "{}_{}".format(sweep_export_path, self._overtone_name)
            FileStorage.TXT_sweeps_save(filename, path,
                                        self._readFREQ,
                                        self._data1_buffer,
                                        self._data2_buffer)
        self._count += 1

    def _open_csv_file(self):
        """
        Open the persistent CSV log at acquisition start.

        The file is kept open for the whole acquisition to avoid the cost
        of repeated open/close on every sample (Windows is particularly
        slow with this pattern).
        """
        try:
            filenameCSV = "{}_{}".format(self._csv_filename, self._overtone_name)
            full_path = FileManager.create_full_path(
                filenameCSV,
                extension=Constants.csv_extension,
                path=Constants.csv_export_path)

            print("\n")
            print(TAG, "PERSISTENT FILE: Opening CSV for data logging...")
            print(TAG, "Storing in: {}".format(full_path))
            Log.i(TAG, "PERSISTENT FILE: Storing in: {}".format(full_path))

            self._csv_file = open(full_path, 'w', newline='')
            self._csv_writer = csv.writer(self._csv_file)
            self._csv_writer.writerow([
                "Date", "Time", "Relative_time",
                "Temperature", "Resonance_Frequency", "Dissipation"])
            self._csv_file.flush()
            self._flush_counter = 0

        except Exception as e:
            print(TAG, "ERROR: Failed to open CSV file: {}".format(e))
            Log.e(TAG, "Failed to open CSV file: {}".format(e))
            self._csv_file = None
            self._csv_writer = None

    def _write_csv_row(self, relative_time, temperature, frequency, dissipation,
                       acq_timestamp_us=None):
        """
        Append one data row to the open CSV log and flush to disk every
        `_flush_interval` writes.

        :param acq_timestamp_us: acquisition timestamp (microseconds since
                                 epoch) used to format the Date/Time columns.
                                 If None, falls back to wall-clock time.
        """
        if self._csv_file is None or self._csv_writer is None:
            return

        try:
            if acq_timestamp_us is not None:
                import datetime
                acq_dt = datetime.datetime.fromtimestamp(acq_timestamp_us / 1e6)
                csv_date = acq_dt.strftime("%Y-%m-%d")
                csv_time = acq_dt.strftime("%H:%M:%S") + ".{:03d}".format(acq_dt.microsecond // 1000)
            else:
                csv_date = strftime("%Y-%m-%d", localtime())
                csv_time = strftime("%H:%M:%S", localtime())

            d0 = float("{0:.2f}".format(relative_time))
            d1 = float("{0:.2f}".format(temperature))
            d2 = float("{0:.2f}".format(frequency))
            self._csv_writer.writerow([csv_date, csv_time, d0, d1, d2, dissipation])

            # Periodic disk sync to bound the loss in case of a crash
            self._flush_counter += 1
            if self._flush_counter >= self._flush_interval:
                self._csv_file.flush()
                os.fsync(self._csv_file.fileno())
                self._flush_counter = 0

        except Exception as e:
            print(TAG, "ERROR: Failed to write CSV row: {}".format(e))
            Log.e(TAG, "Failed to write CSV row: {}".format(e))

    def _close_csv_file(self):
        """Flush and close the persistent CSV log."""
        if self._csv_file is None:
            return
        try:
            self._csv_file.flush()
            os.fsync(self._csv_file.fileno())
            self._csv_file.close()
            print(TAG, "PERSISTENT FILE: CSV file closed successfully")
            Log.i(TAG, "PERSISTENT FILE: CSV file closed successfully")
        except Exception as e:
            print(TAG, "ERROR: Failed to close CSV file: {}".format(e))
            Log.e(TAG, "Failed to close CSV file: {}".format(e))
        finally:
            self._csv_file = None
            self._csv_writer = None
            self._flush_counter = 0

    # ------------------------------------------------------------------
    # Static helpers — port and overtone enumeration
    # ------------------------------------------------------------------
    @staticmethod
    def get_source_ports(source):
        """Return the list of available ports for the given SourceType."""
        if source == SourceType.serial:
            print(TAG, 'Port connected:', SerialProcess.get_ports())
            return SerialProcess.get_ports()
        if source == SourceType.calibration:
            print(TAG, 'Port connected:', CalibrationProcess.get_ports())
            return CalibrationProcess.get_ports()
        if source == SourceType.SocketClient:
            return SocketProcess.get_default_host()
        print(TAG, 'Warning: unknown source selected')
        Log.w(TAG, "Unknown source selected")
        return None

    @staticmethod
    def get_source_speeds(source):
        """Return the list of available overtone choices for the given SourceType."""
        if source == SourceType.serial:
            return SerialProcess.get_speeds()
        if source == SourceType.calibration:
            return CalibrationProcess.get_speeds()
        if source == SourceType.SocketClient:
            return SocketProcess.get_default_port()
        print(TAG, 'Unknown source selected')
        Log.w(TAG, "Unknown source selected")
        return None

    # ------------------------------------------------------------------
    # Buffer (re)initialisation
    # ------------------------------------------------------------------
    def reset_buffers(self, samples):
        """
        Allocate / clear all per-channel buffers.

        Per-sweep arrays (`_data1_buffer`, `_data2_buffer`) are sized to
        the sweep length. Time-series ring buffers are sized to
        `Constants.ring_buffer_samples` (a fixed history length).
        """
        self._data1_buffer = np.zeros(samples)   # amplitude
        self._data2_buffer = np.zeros(samples)   # phase

        self._d1_store = self._d2_store = self._d3_store = 0
        self._t1_store = self._t2_store = self._t3_store = 0
        self._ser_error1 = self._ser_error2 = self._ser_err_usb = 0
        self._sampling_time = 0.0
        self._calibration_cancelled = False

        n = Constants.ring_buffer_samples
        self._d1_buffer = RingBuffer(n)   # resonance frequency
        self._d2_buffer = RingBuffer(n)   # dissipation
        self._d3_buffer = RingBuffer(n)   # temperature
        self._t1_buffer = RingBuffer(n)   # time (resonance frequency)
        self._t2_buffer = RingBuffer(n)   # time (dissipation)
        self._t3_buffer = RingBuffer(n)   # time (temperature)
