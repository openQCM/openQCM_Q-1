from multiprocessing import Queue

from openQCM.core.constants import Constants, SourceType
from openQCM.processors.Parser import ParserProcess
from openQCM.processors.Serial import SerialProcess
from openQCM.processors.SocketClient import SocketProcess
from openQCM.processors.Calibration import CalibrationProcess
from openQCM.common.fileStorage import FileStorage
from openQCM.common.fileManager import FileManager
from openQCM.common.logger import Logger as Log
from openQCM.core.ringBuffer import RingBuffer
import numpy as np
from time import time, strftime, localtime
import csv
import os
#import pywt

TAG = ""#"[Worker]"

###############################################################################
# Service that creates and concentrates all processes to run the application
###############################################################################
class Worker:

    ###########################################################################
    # Creates all processes involved in data acquisition and processing
    ###########################################################################
    def __init__(self,QCS_on = None,
                      port = None,
                      speed = Constants.serial_default_overtone,
                      samples = Constants.argument_default_samples,
                      source = SourceType.serial,
                      export_enabled = False):
        """
        :param port: Port to open on start :type port: str.
        :param speed: Speed for the specified port :type speed: float.
        :param samples: Number of samples :type samples: int.
        :param source: Source type :type source: SourceType.
        :param export_enabled: If true, data will be stored or exported in a file :type export_enabled: bool.
        :param export_path: If specified, defines where the data will be exported :type export_path: str.
        """
        # data queues
        self._queue1 = Queue()
        self._queue2 = Queue()
        self._queue3 = Queue()
        self._queue4 = Queue()
        self._queue5 = Queue()
        self._queue6 = Queue()
        self._queue_tracking = Queue()  # AUTO-TRACKING queue
        
        # data buffers
        self._data1_buffer = None 
        self._data2_buffer = None 
        self._d1_buffer = None 
        self._d2_buffer = None
        self._d3_buffer = None
        self._t1_buffer = None 
        self._t2_buffer = None
        self._t3_buffer = None
        self._ser_error1 = 0
        self._ser_error2 = 0
        self._ser_err_usb= 0
        self._control_k = 0
        self._sampling_time = 0.0
        self._calibration_cancelled = False

        # AUTO-TRACKING variables
        self._tracking_activated = False
        self._tracking_start_freq = None
        self._tracking_stop_freq = None
        self._tracking_ref_freq = None
        self._tracking_count = 0

        # instances of the processes
        self._acquisition_process = None
        self._parser_process = None
        
        # others
        self._QCS_on = QCS_on # QCS installed on device (unused now)
        self._port = port     # serial port 
        # overtones (str) if 'serial' is called
        # QCS (str) if 'calibration' is called 
        self._speed = speed 
        self._samples = samples
        self._source = source
        self._export = export_enabled
        
        # Supporting variables
        self._d1_store = None # data storing
        self._d2_store = None # data storing
        self._readFREQ = None # frequency range
        self._fStep    = None # sample rate
        self._overtone_name  = None # fundamental/overtones name (str)
        self._overtone_value = None # fundamental/overtones value(float)
        self._count = 0 # sweep counter
        self._flag = True
        self._timestart = 0
        self._csv_filename = None # CSV filename with timestamp (generated at start)
        self._spline_factor = None # Spline smoothing factor for current overtone

        # PERSISTENT FILE: File handle for CSV data (kept open during acquisition)
        self._csv_file = None
        self._csv_writer = None
        self._flush_counter = 0
        self._flush_interval = 30  # Flush to disk every N writes (approx 30 seconds)
        
        
    ###########################################################################
    # Starts all processes, based on configuration given in constructor.
    ###########################################################################
    def start(self):

        # Generate new CSV filename with current timestamp each time START is pressed
        self._csv_filename = strftime(Constants.csv_default_prefix, localtime())

        if self._source == SourceType.serial:
           self._samples = Constants.argument_default_samples
        elif self._source == SourceType.calibration:
           self._samples = Constants.calibration_default_samples
           self._readFREQ = Constants.calibration_readFREQ
        # Setup/reset the internal buffers
        self.reset_buffers(self._samples)
        # Instantiates process
        self._parser_process = ParserProcess(self._queue1,self._queue2,self._queue3,self._queue4,self._queue5,self._queue6,self._queue_tracking)
        # Checks the type of source
        if self._source == SourceType.serial:
            self._acquisition_process = SerialProcess(self._parser_process)
        elif self._source == SourceType.calibration:
            self._acquisition_process = CalibrationProcess(self._parser_process)
        elif self._source == SourceType.SocketClient:
            self._acquisition_process = SocketProcess(self._parser_process)
            
        if self._acquisition_process.open(port=self._port, speed=self._speed):
            if self._source == SourceType.serial:
               (self._overtone_name,self._overtone_value, self._fStep, self._readFREQ, SG_window_size, spline_points, spline_factor) = self._acquisition_process.get_frequencies(self._samples)
               self._spline_factor = spline_factor
               #print(TAG, "Quartz Crystal Sensor installed: {}".format(self._QCS_on))
               print("")
               print(TAG, "DATA MAIN INFORMATION")
               print(TAG, "Selected frequency: {} - {}Hz".format(self._overtone_name,self._overtone_value))
               print(TAG, "Frequency start: {}Hz".format(self._readFREQ[0]))
               print(TAG, "Frequency stop:  {}Hz".format(self._readFREQ[-1]))
               print(TAG, "Frequency range: {}Hz".format(self._readFREQ[-1]-self._readFREQ[0]))
               print(TAG, "Number of samples: {}".format(self._samples-1))
               print(TAG, "Sample rate: {}Hz".format(self._fStep))
               print(TAG, "History buffer size: 180 min\n")
               print(TAG, "MAIN PROCESSING INFORMATION")
               print(TAG, "Method for baseline estimation and correction:")
               print(TAG, "Least Squares Polynomial Fit (LSP)")
               #print(TAG, "Degree of the fitting polynomial: 8")
               print(TAG, "Savitzky-Golay Filtering")
               print(TAG, "Order of the polynomial fit: {}".format(Constants.SG_order))
               print(TAG, "Size of data window (in samples): {}".format(SG_window_size))
               print(TAG, "Oversampling using spline interpolation")
               print(TAG, "Spline points (in samples): {}".format(spline_points-1))
               print(TAG, "Resolution after oversampling: {}Hz".format((self._readFREQ[-1]-self._readFREQ[0])/(spline_points-1)))
               
            elif self._source == SourceType.calibration:
               print("")
               print(TAG, "MAIN PEAK DETECTION INFORMATION")
               print(TAG, "Peak Detection frequency start:  {}Hz".format(Constants.calibration_frequency_start))
               print(TAG, "Peak Detection frequency stop:  {}Hz".format(Constants.calibration_frequency_stop))
               print(TAG, "Frequency range: {}Hz".format(Constants.calibration_frequency_stop-Constants.calibration_frequency_start))
               print(TAG, "Number of samples: {}".format(Constants.calibration_default_samples-1))
               print(TAG, "Sample rate: {}Hz".format(Constants.calibration_fStep))
            print(TAG, 'Training for plot...\n')
            # Starts processes
            self._acquisition_process.start()
            self._parser_process.start()

            # PERSISTENT FILE: Open CSV file for data logging (stays open during acquisition)
            if self._source == SourceType.serial:
                self._open_csv_file()

            return True
        else:
            print(TAG, 'Warning: port is not available')
            Log.i(TAG, "Warning: Port is not available")
            return False


    ###########################################################################
    # Stops all running processes
    ###########################################################################    
    def stop(self):

        self._acquisition_process.stop()
        self._parser_process.stop()
        '''
        for process in [self._acquisition_process, self._parser_process]:
            if process is not None and process.is_alive():
                process.stop()
                process.join(Constants.process_join_timeout_ms)
        '''

        # PERSISTENT FILE: Close CSV file when stopping acquisition
        self._close_csv_file()

        print(TAG, 'Running processes stopped...')
        print(TAG, 'Processes finished')
        Log.i(TAG, "Running processes stopped...")
        Log.i(TAG, "Processes finished")


    ###########################################################################
    # Waits for the acquisition process to fully terminate
    ###########################################################################
    def wait_for_process(self, timeout=5.0):
        """
        Waits for the acquisition process to terminate.
        If it doesn't terminate within timeout, forces termination.
        :param timeout: Maximum seconds to wait :type timeout: float.
        """
        if self._acquisition_process is not None and self._acquisition_process.is_alive():
            print(TAG, "Waiting for acquisition process to terminate...")
            self._acquisition_process.join(timeout=timeout)
            if self._acquisition_process.is_alive():
                print(TAG, "WARNING: Process did not terminate, forcing...")
                Log.w(TAG, "Acquisition process did not terminate, forcing...")
                self._acquisition_process.terminate()
                self._acquisition_process.join(timeout=2.0)
            print(TAG, "Acquisition process terminated")
            Log.i(TAG, "Acquisition process terminated")
        
        
    ###########################################################################
    # Empties the internal queues, updating data to consumers
    ###########################################################################    
    def consume_queue1(self):
        # queue1 for serial data: amplitude
        while not self._queue1.empty():
            self._queue_data1(self._queue1.get(False))
    
    def consume_queue2(self):
        # queue2 for serial data: phase
        while not self._queue2.empty():
            self._queue_data2(self._queue2.get(False))

    def consume_queue3(self):
        # queue3 for elaborated data: resonance frequency
        while not self._queue3.empty():
            self._queue_data3(self._queue3.get(False))
            
    def consume_queue4(self):
        # queue3 for elaborated data: Q-factor/Dissipation
        while not self._queue4.empty():
            self._queue_data4(self._queue4.get(False))    
           
    def consume_queue5(self):
        # queue3 for elaborated data: Temperature
        while not self._queue5.empty():
            self._queue_data5(self._queue5.get(False)) 
    
    def consume_queue6(self):
        # queue3 for elaborated data: errors
        while not self._queue6.empty():
            self._queue_data6(self._queue6.get(False))

    def consume_queue_tracking(self):
        # queue for auto-tracking notifications
        while not self._queue_tracking.empty():
            self._queue_data_tracking(self._queue_tracking.get(False))

    ###########################################################################
    # Adds data to internal buffers.
    ###########################################################################    
    def _queue_data1(self,data):
        #:param data: values to add for serial data: amplitude :type data: float.
        self._data1_buffer = data
    
    #####    
    def _queue_data2(self,data):
        #:param data: values to add for serial data phase :type data: float.
        self._data2_buffer = data
        # Additional function: exports calibration data in a file if export box is checked.
        '''
        self.store_data_calibration()
        '''
    #####
    def _queue_data3(self,data):
        #:param data: values to add for Resonance frequency :type data: float.
        self._t1_store = data[0] # time (unused)
        self._d1_store = data[1] # data
        self._t1_buffer.append(data[0])
        self._d1_buffer.append(data[1])
        
    #####
    def _queue_data4(self,data):
        # Additional function: exports processed data in a file if export box is checked.
        #:param data: values to add for Q-factor/dissipation :type data: float.
        self._t2_store = data[0] # time (unused)
        self._d2_store = data[1] # data
        self._t2_buffer.append(data[0])
        self._d2_buffer.append(data[1])
    
    #####
    def _queue_data5(self,data):
        # Additional function: exports processed data in a file if export box is checked.
        #:param data: values to add for temperature :type data: float.
        # Check for user cancellation flag from CalibrationProcess
        if data[0] == -1:
            self._calibration_cancelled = True
        self._t3_store = data[0] # time (unused)
        self._d3_store = data[1] # data
        self._t3_buffer.append(data[0])
        self._d3_buffer.append(data[1])
        # for storing relative time (use acquisition timestamp, not queue-drain time)
        if  self._flag and ~np.isnan(self._d3_store):
            self._timestart = data[0]  # microsecond timestamp from SerialProcess
            self._flag = False
        # Data Storage in csv and/or txt file 
        self.store_data()
    
        #####
    def _queue_data6(self,data):
        #:param data: values to add for serial error :type data: float.
        self._ser_error1 = data[0]
        self._ser_error2 = data[1]
        self._control_k = data[2]
        self._ser_err_usb = data[3]
        if len(data) > 4:
            self._sampling_time = data[4]

    #####
    def _queue_data_tracking(self, data):
        """
        AUTO-TRACKING: Process tracking notification data
        :param data: [activated, start_freq, stop_freq, ref_freq, count]
        """
        self._tracking_activated = data[0]
        self._tracking_start_freq = data[1]
        self._tracking_stop_freq = data[2]
        self._tracking_ref_freq = data[3]
        self._tracking_count = data[4]
        # Update the frequency range for sweep storage and display
        if self._tracking_activated:
            samples = self._samples
            fStep = (self._tracking_stop_freq - self._tracking_start_freq) / (samples - 1)
            self._readFREQ = np.arange(samples) * fStep + self._tracking_start_freq
            self._fStep = fStep

    ###########################################################################
    # Gets data buffers for plot (Amplitude,Phase,Frequency and Dissipation) 
    ###########################################################################        
    def get_value1_buffer(self):
        #:return: float list.
        return self._data1_buffer
    
    #####
    def get_value2_buffer(self):
        #:return: float list.
        return self._data2_buffer

    #####
    def get_d1_buffer(self):
        #:return: float list.
        return self._d1_buffer.get_all()
        
    ##### Gets time buffers
    def get_t1_buffer(self):
        #:return: float list.
        return self._t1_buffer.get_all()
    
    #####
    def get_d2_buffer(self):
        #:return: float list.
        return self._d2_buffer.get_all()
    
    ##### Gets time buffers
    def get_t2_buffer(self):
        #:return: float list.
        return self._t2_buffer.get_all()
    
    #####
    def get_d3_buffer(self):
        #:return: float list.
        return self._d3_buffer.get_all()
    
    ##### Gets time buffers
    def get_t3_buffer(self):
        #:return: float list.
        return self._t3_buffer.get_all()
    
    ##### Gets serial error
    def get_ser_error(self):
        #:return: float list.
        return self._ser_error1,self._ser_error2, self._control_k, self._ser_err_usb

    def get_sampling_time(self):
        #:return: sampling time in seconds between consecutive sweep cycles.
        return self._sampling_time

    def is_calibration_cancelled(self):
        return self._calibration_cancelled

    ##### AUTO-TRACKING: Gets tracking state
    def get_tracking_state(self):
        """
        Returns the current auto-tracking state.
        :return: (activated, start_freq, stop_freq, ref_freq, count)
        """
        activated = self._tracking_activated
        # Reset flag after reading (one-shot notification)
        self._tracking_activated = False
        return (activated,
                self._tracking_start_freq,
                self._tracking_stop_freq,
                self._tracking_ref_freq,
                self._tracking_count)
    

    ###########################################################################
    # Exports data in csv and/or txt file if export box is checked
    ###########################################################################
    def store_data(self):
        # Checks the type of source
        if self._source == SourceType.serial:
          # PERSISTENT FILE: Write to open CSV file instead of opening/closing each time
          # Use acquisition timestamps (microseconds) for accurate relative time
          relative_time_s = (self._t3_store - self._timestart) / 1e6
          self._write_csv_row(relative_time_s, self._d3_store, self._d1_store, self._d2_store, self._t3_store)

          if self._export:
              # Storing acquired sweeps - use _csv_filename for sweep export path too
              filename = "{}_{}_{}".format(Constants.csv_sweeps_filename, self._overtone_name,self._count)
              #filename = "{}_{}".format(Constants.csv_sweeps_filename,self._count)
              sweep_export_path = "{}{}{}".format(Constants.csv_export_path, Constants.slash, self._csv_filename)
              path = "{}_{}".format(sweep_export_path, self._overtone_name)
              #FileStorage.CSV_sweeps_save(filename, path, self._readFREQ, self._data1_buffer, self._data2_buffer)
              FileStorage.TXT_sweeps_save(filename, path, self._readFREQ, self._data1_buffer, self._data2_buffer)
          self._count+=1


    ###########################################################################
    # PERSISTENT FILE: Opens CSV file for data logging (called at START)
    ###########################################################################
    def _open_csv_file(self):
        """
        Opens CSV file once at acquisition start. The file stays open during
        the entire acquisition to avoid Windows file I/O limitations.
        """
        try:
            # Create the full filename with overtone name
            filenameCSV = "{}_{}".format(self._csv_filename, self._overtone_name)
            full_path = FileManager.create_full_path(filenameCSV, extension=Constants.csv_extension, path=Constants.csv_export_path)

            print("\n")
            print(TAG, "PERSISTENT FILE: Opening CSV for data logging...")
            print(TAG, "Storing in: {}".format(full_path))
            Log.i(TAG, "PERSISTENT FILE: Storing in: {}".format(full_path))

            # Open file in write mode (new file each time START is pressed)
            self._csv_file = open(full_path, 'w', newline='')
            self._csv_writer = csv.writer(self._csv_file)

            # Write header
            self._csv_writer.writerow(["Date", "Time", "Relative_time", "Temperature", "Resonance_Frequency", "Dissipation"])
            self._csv_file.flush()  # Ensure header is written immediately

            # Reset flush counter
            self._flush_counter = 0

        except Exception as e:
            print(TAG, "ERROR: Failed to open CSV file: {}".format(e))
            Log.e(TAG, "Failed to open CSV file: {}".format(e))
            self._csv_file = None
            self._csv_writer = None


    ###########################################################################
    # PERSISTENT FILE: Writes a row to the open CSV file with periodic flush
    ###########################################################################
    def _write_csv_row(self, relative_time, temperature, frequency, dissipation, acq_timestamp_us=None):
        """
        Writes a single data row to the open CSV file.
        Flushes to disk every _flush_interval writes (~30 seconds).
        :param acq_timestamp_us: Acquisition timestamp in microseconds since epoch (from SerialProcess).
        """
        if self._csv_file is None or self._csv_writer is None:
            return

        try:
            # Format timestamp from acquisition time (not write time)
            if acq_timestamp_us is not None:
                import datetime
                acq_dt = datetime.datetime.fromtimestamp(acq_timestamp_us / 1e6)
                csv_date = acq_dt.strftime("%Y-%m-%d")
                csv_time = acq_dt.strftime("%H:%M:%S") + ".{:03d}".format(acq_dt.microsecond // 1000)
            else:
                csv_date = strftime("%Y-%m-%d", localtime())
                csv_time = strftime("%H:%M:%S", localtime())

            # Format data values
            d0 = float("{0:.2f}".format(relative_time))
            d1 = float("{0:.2f}".format(temperature))
            d2 = float("{0:.2f}".format(frequency))

            # Write row
            self._csv_writer.writerow([csv_date, csv_time, d0, d1, d2, dissipation])

            # Periodic flush to disk (every ~30 seconds to prevent data loss)
            self._flush_counter += 1
            if self._flush_counter >= self._flush_interval:
                self._csv_file.flush()
                os.fsync(self._csv_file.fileno())  # Force OS to write to disk
                self._flush_counter = 0

        except Exception as e:
            print(TAG, "ERROR: Failed to write CSV row: {}".format(e))
            Log.e(TAG, "Failed to write CSV row: {}".format(e))


    ###########################################################################
    # PERSISTENT FILE: Closes the CSV file (called at STOP)
    ###########################################################################
    def _close_csv_file(self):
        """
        Closes the CSV file when acquisition stops.
        Ensures all data is flushed to disk before closing.
        """
        if self._csv_file is not None:
            try:
                self._csv_file.flush()
                os.fsync(self._csv_file.fileno())  # Force final write to disk
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


    ###########################################################################
    # Checks if processes are running
    ###########################################################################
    def is_running(self):  
        #:return: True if a process is running :rtype: bool.
        return self._acquisition_process is not None and self._acquisition_process.is_alive()


    ###########################################################################
    # Gets the available ports for specified source
    ###########################################################################
    @staticmethod
    def get_source_ports(source):
        
        """
        :param source: Source to get available ports :type source: SourceType.
        :return: List of available ports :rtype: str list.
        """
        if source == SourceType.serial:
            print(TAG,'Port connected:',SerialProcess.get_ports())
            return SerialProcess.get_ports()
        elif source == SourceType.calibration:
            print(TAG,'Port connected:',CalibrationProcess.get_ports())
            return CalibrationProcess.get_ports()
        elif source == SourceType.SocketClient:
            return SocketProcess.get_default_host()
        else:
            print(TAG,'Warning: unknown source selected')
            Log.w(TAG,"Unknown source selected")
            return None
        
        
    ###########################################################################
    # Gets the available speeds for specified source
    ###########################################################################
    @staticmethod
    def get_source_speeds(source):
        
        """
        :param source: Source to get available speeds :type source: SourceType.
        :return: List of available speeds :rtype: str list.
        """
        if source == SourceType.serial:
            return SerialProcess.get_speeds()
        elif source == SourceType.calibration:
            return CalibrationProcess.get_speeds()
        elif source == SourceType.SocketClient:
            return SocketProcess.get_default_port()
        else:
            print(TAG,'Unknown source selected')
            Log.w(TAG, "Unknown source selected")
            return None
        
    
    ###########################################################################
    # Setup/Clear the internal buffers
    ###########################################################################
    def reset_buffers(self, samples):
        #:param samples: Number of samples for the buffers :type samples: int.
        
        # Initialises data buffers
        self._data1_buffer = np.zeros(samples) # amplitude
        self._data2_buffer = np.zeros(samples) # phase
        #self._d1_buffer = []  # Resonance frequency 
        #self._d2_buffer = []  # Dissipation
        #self._d3_buffer = []  # temperature
        #self._t1_buffer = []  # time (Resonance frequency)
        #self._t2_buffer = []  # time (Dissipation)
        #self._t3_buffer = []  # time (temperature)

        # Initialises supporting variables
        self._d1_store = 0
        self._d2_store = 0
        self._d3_store = 0
        self._t1_store = 0
        self._t2_store = 0
        self._t3_store = 0
        self._ser_error1 = 0
        self._ser_error2 = 0
        self._ser_err_usb= 0
        self._sampling_time = 0.0
        self._calibration_cancelled = False
        #self._control_k = 0
        
        self._d1_buffer = RingBuffer(Constants.ring_buffer_samples)  # Resonance frequency 
        self._d2_buffer = RingBuffer(Constants.ring_buffer_samples)  # Dissipation
        self._d3_buffer = RingBuffer(Constants.ring_buffer_samples)  # temperature
        self._t1_buffer = RingBuffer(Constants.ring_buffer_samples)  # time (Resonance frequency)
        self._t2_buffer = RingBuffer(Constants.ring_buffer_samples)  # time (Dissipation)
        self._t3_buffer = RingBuffer(Constants.ring_buffer_samples)  # time (temperature)
        #print(TAG,'Buffers cleared')
        #Log.i(TAG, "Buffers cleared") 

    ############################################################################
    # Gets frequency range
    ############################################################################
    
    def get_frequency_range(self):
        
        """
        :param samples: Number of samples for the buffers :type samples: int.
        :return: overtone :type overtone: float.
        :return: frequency range :type readFREQ: float list.
        """
        return self._readFREQ
    
    
    ############################################################################
    # Gets overtones name, value and frequency step
    ############################################################################
    
    def get_overtone(self):
        
        """
        :param samples: Number of samples for the buffers :type samples: int.
        :return: overtone :type overtone: float.
        :return: frequency range :type readFREQ: float list.
        """
        return self._overtone_name,self._overtone_value, self._fStep

    ############################################################################
    # Gets spline smoothing factor for current overtone
    ############################################################################

    def get_spline_factor(self):
        """
        :return: Spline smoothing factor for current overtone :rtype: float.
        """
        return self._spline_factor
