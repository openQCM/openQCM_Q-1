import multiprocessing
from openQCM.core.ringBuffer import RingBuffer
from openQCM.core.constants import Constants
from openQCM.common.fileStorage import FileStorage
from openQCM.common.logger import Logger as Log
from openQCM.common.switcher import Overtone_Switcher_5MHz, Overtone_Switcher_10MHz
from time import time
import serial
from serial.tools import list_ports
import numpy as np
from numpy import loadtxt
from scipy.interpolate import UnivariateSpline

from progressbar import Bar, Percentage, ProgressBar, RotatingMarker,Timer

TAG = ""#"[Serial]"

###############################################################################
# Process for the serial package and the communication with the serial port
# Processes incoming data and calculates outgoing data by the algorithms
###############################################################################
class SerialProcess(multiprocessing.Process):
    
    
    ###########################################################################
    # AUTO-TRACKING: Recalculates sweep window when frequency drift exceeds threshold
    ###########################################################################
    def check_and_update_tracking(self, current_freq, samples):
        """
        Checks if frequency drift exceeds threshold and triggers sweep window recalculation.

        :param current_freq: Current measured frequency (Hz)
        :param samples: Number of samples for sweep
        :return: True if tracking was updated, False otherwise
        """
        # Calculate frequency drift from reference
        freq_drift = abs(current_freq - self._reference_frequency)

        # Check if drift exceeds threshold
        if freq_drift > Constants.auto_tracking_threshold:
            # Store old values for logging
            old_ref_freq = self._reference_frequency
            old_start = self._startFreq
            old_stop = self._stopFreq

            # Update reference frequency to current measured frequency
            self._reference_frequency = current_freq

            # Get the L and R intervals for current overtone
            L_interval, R_interval = self._get_overtone_intervals()

            # Recalculate sweep window with new reference frequency
            self._startFreq = current_freq - L_interval
            self._stopFreq = current_freq + R_interval

            # Recalculate frequency step and range
            self._fStep = (self._stopFreq - self._startFreq) / (samples - 1)
            self._readFREQ = np.arange(samples) * self._fStep + self._startFreq

            # Recalculate spline points
            self._spline_points = int((self._stopFreq - self._startFreq)) + 1

            # Recalculate baseline coefficients for new frequency range
            self._recalculate_baseline_for_range()

            # Increment auto-tracking counter
            self._auto_tracking_count += 1

            # Print detailed notification to terminal
            print("\n" + "=" * 60)
            print(" AUTO-TRACKING ACTIVATED (#{})".format(self._auto_tracking_count))
            print("=" * 60)
            print(" Frequency drift detected: {:.2f} Hz (threshold: {} Hz)".format(
                freq_drift, Constants.auto_tracking_threshold))
            print(" Old reference frequency: {:.2f} Hz".format(old_ref_freq))
            print(" New reference frequency: {:.2f} Hz".format(current_freq))
            print(" Old sweep window: {:.0f} - {:.0f} Hz".format(old_start, old_stop))
            print(" New sweep window: {:.0f} - {:.0f} Hz".format(self._startFreq, self._stopFreq))
            print(" Baseline recalculated for new frequency range")
            print("=" * 60 + "\n")

            # Signal GUI to update (via parser queue)
            # Format: [tracking_activated, new_start_freq, new_stop_freq, new_reference_freq, tracking_count]
            self._parser_tracking.add_tracking([
                True,
                self._startFreq,
                self._stopFreq,
                self._reference_frequency,
                self._auto_tracking_count
            ])

            return True

        return False

    ###########################################################################
    # AUTO-TRACKING: Gets L and R intervals for current overtone
    ###########################################################################
    def _get_overtone_intervals(self):
        """
        Returns the left and right frequency intervals for the current overtone.
        These intervals define the asymmetric sweep window around the reference frequency.

        :return: (L_interval, R_interval) in Hz
        """
        # Check QCS type (5MHz or 10MHz) based on reference frequency
        if self._reference_frequency > 4e+06 and self._reference_frequency < 6e+06:
            # 5 MHz sensor - fundamental
            if self._overtone_int == 0:
                return Constants.L5_fundamental, Constants.R5_fundamental
            elif self._overtone_int == 1:
                return Constants.L5_3th_overtone, Constants.R5_3th_overtone
            elif self._overtone_int == 2:
                return Constants.L5_5th_overtone, Constants.R5_5th_overtone
            elif self._overtone_int == 3:
                return Constants.L5_7th_overtone, Constants.R5_7th_overtone
            elif self._overtone_int == 4:
                return Constants.L5_9th_overtone, Constants.R5_9th_overtone
        elif self._reference_frequency > 9e+06 and self._reference_frequency < 51e+06:
            # 10 MHz sensor or higher overtones
            if self._overtone_int == 0:
                return Constants.L10_fundamental, Constants.R10_fundamental
            elif self._overtone_int == 1:
                return Constants.L10_3th_overtone, Constants.R10_3th_overtone
            elif self._overtone_int == 2:
                return Constants.L10_5th_overtone, Constants.R10_5th_overtone

        # Default fallback (should not happen)
        return 15000, 5000

    ###########################################################################
    # AUTO-TRACKING: Recalculates baseline for new frequency range
    ###########################################################################
    def _recalculate_baseline_for_range(self):
        """
        Recalculates baseline polynomial coefficients for the new sweep window.
        Uses the calibration data to extract coefficients for the new frequency range.
        """
        # Evaluate baseline polynomial at new frequency range
        # The baseline coefficients were calculated during calibration for the full range
        # We just need to evaluate the polynomial at the new frequency points
        self._polyfitted = np.polyval(self._coeffs_all, self._readFREQ)

    ###########################################################################
    # BASELINE CORRECTION
    ###########################################################################
    def baseline_correction(self,x,y,poly_order):
        
        # Estimate Baseline with Least Squares Polynomial Fit (LSP)
        coeffs = np.polyfit(x,y,poly_order) 
        # Evaluate a polynomial at specific values
        poly_fitted = np.polyval(coeffs,x) 
        return poly_fitted,coeffs       
      
    ###########################################################################
    # BASELINE - Evaluates polynomial coefficients - Sweep over all frequencies
    ###########################################################################
    def baseline_coeffs(self):
        
        # initializations
        self.polyfitted_all = None
        self.coeffs_all = None
        self.polyfitted_all_phase = None
        self.coeffs_all_phase = None
        
        # loads Calibration (baseline correction) from file
        (self.freq_all,self.mag_all,self.phase_all) = self.load_calibration_file()
        
        # Baseline correction: input signal Amplitude (sweep all frequencies)
        (self.polyfitted_all,self.coeffs_all)=self.baseline_correction(self.freq_all,self.mag_all,8)
        self.mag_beseline_corrected_all= self.mag_all-self.polyfitted_all
        
        # Baseline correction: input signal Phase (sweep all frequencies)
        (self.polyfitted_all_phase,self.coeffs_all_phase)=self.baseline_correction(self.freq_all,self.phase_all,8)
        self.phase_beseline_corrected_all= self.phase_all-self.polyfitted_all_phase 
        return self.coeffs_all
    
    
    ###########################################################################
    # Savitzky-Golay (Smoothing/Denoising Filter)
    ###########################################################################
    def savitzky_golay(self,y, window_size, order, deriv=0, rate=1):
        
        """Smooth (and optionally differentiate) data with a Savitzky-Golay filter.
        The Savitzky-Golay filter removes high frequency noise from data.
        It has the advantage of preserving the original shape and
        features of the signal better than other types of filtering
        approaches, such as moving averages techniques.
        Parameters
        ----------
        y : array_like, shape (N,) the values of the time history of the signal.
        window_size : int the length of the window. Must be an odd integer number.
        order : int the order of the polynomial used in the filtering.
                Must be less then `window_size` - 1.
        deriv: int the order of the derivative to compute (default = 0 means only smoothing)
        Returns
        -------
        ys : ndarray, shape (N) the smoothed signal (or it's n-th derivative).
        Notes
        -----
        The Savitzky-Golay is a type of low-pass filter, particularly
        suited for smoothing noisy data. The main idea behind this
        approach is to make for each point a least-square fit with a
        polynomial of high order over a odd-sized window centered at
        the point.
        Examples
        --------
        t = np.linspace(-4, 4, 500)
        y = np.exp( -t**2 ) + np.random.normal(0, 0.05, t.shape)
        ysg = savitzky_golay(y, window_size=31, order=4)
        import matplotlib.pyplot as plt
        plt.plot(t, y, label='Noisy signal')
        plt.plot(t, np.exp(-t**2), 'k', lw=1.5, label='Original signal')
        plt.plot(t, ysg, 'r', label='Filtered signal')
        plt.legend()
        plt.show()
        References
        ----------
        .. [1] A. Savitzky, M. J. E. Golay, Smoothing and Differentiation of
           Data by Simplified Least Squares Procedures. Analytical
           Chemistry, 1964, 36 (8), pp 1627-1639.
        .. [2] Numerical Recipes 3rd Edition: The Art of Scientific Computing
           W.H. Press, S.A. Teukolsky, W.T. Vetterling, B.P. Flannery
           Cambridge University Press ISBN-13: 9780521880688
        """
        import numpy as np
        from math import factorial
        try:
            window_size = np.abs(np.int(window_size))
            order = np.abs(np.int(order)) 
        except ValueError as msg:
            raise ValueError("WARNING: window size and order have to be of type int!")
        if window_size % 2 != 1 or window_size < 1:
            raise TypeError("WARNING: window size must be a positive odd number!")
        if window_size < order + 2:
            raise TypeError("WARNING: window size is too small for the polynomials order!")
        order_range = range(order+1)
        half_window = (window_size -1) // 2
        # precompute coefficients
        b = np.mat([[k**i for i in order_range] for k in range(-half_window, half_window+1)])
        m = np.linalg.pinv(b).A[deriv] * rate**deriv * factorial(deriv)
        # pad the signal at the extremes with values taken from the signal itself
        firstvals = y[0] - np.abs( y[1:half_window+1][::-1] - y[0] )
        lastvals = y[-1] + np.abs(y[-half_window-1:-1][::-1] - y[-1])
        y = np.concatenate((firstvals, y, lastvals))
        return np.convolve( m[::-1], y, mode='valid')
     
        
    ###########################################################################
    # Resonance Frequency, Resonance Peak, Bandwidth and Q-factor/Dissipation 
    ###########################################################################
    def parameters_finder(self,freq,signal,percent):
        f_max = np.max(signal)          # Find maximum
        i_max= np.argmax(signal,axis=0) # Find index of maximum
        # setup the index for finding the leading edge
        index_m = i_max
        # loop until the index at FWHM/others is found
        while signal[index_m] > percent*f_max:
            if index_m < 1:
               #print(TAG, 'WARNING: Left value not found')
               self._err1 = 1
               break
            index_m = index_m-1     
        #linearly interpolate between the previous values to find the value of freq at the leading edge
        m = (signal[index_m+1] - signal[index_m])/(freq[index_m+1] - freq[index_m])
        c = signal[index_m] - freq[index_m]*m
        i_leading = (percent*f_max - c)/m
        # setup index for finding the trailing edge
        index_M = i_max
        # loop until the index at FWHM/others is found
        while signal[index_M] > percent*f_max:
            if index_M >= len(signal)-1:
                #print(TAG, 'WARNING: Right value not found')
                self._err2 = 1
                break
            index_M = index_M+1;
        # linearly interpolate between the previous values to find the value of freq at the trailing edge
        m = (signal[index_M-1] - signal[index_M])/(freq[index_M-1] - freq[index_M])
        c = signal[index_M] - freq[index_M]*m
        i_trailing = (percent*f_max - c)/m
        #compute the FWHM/others
        bandwidth = abs(i_trailing - i_leading)
        Qfac=freq[i_max]/bandwidth
        return i_max, f_max, bandwidth, index_m, index_M, Qfac  
    
    
    ###########################################################################
    # Processes incoming data and calculates outcoming data
    ###########################################################################    
    def elaborate(self, k, coeffs_all, readFREQ, samples, Xm, Xp, temperature, SG_window_size, Spline_points, Spline_factor, timestamp):
        
        ###################
        def waveletSmooth(x, wavelet="db4", level=1, title=None):
            import pywt
            from statsmodels.robust import mad
            # calculate the wavelet coefficients
            coeff = pywt.wavedec( x, wavelet, mode="per")
            # calculate a threshold
            sigma = mad(coeff[-level])
            # changing this threshold also changes the behavior
            uthresh = sigma * np.sqrt( 2*np.log(len(x)))
            coeff[1:] = (pywt.threshold(i, value=uthresh, mode="soft") for i in coeff[1:])
            # reconstruct the signal using the thresholded coefficients
            y = pywt.waverec( coeff, wavelet, mode="per")
            return y
        ###################
        # Number of spline points
        points = Spline_points
        # sweep counter
        self._k= k
        # evaluated polynomial coefficients
        self._coeffs_all = coeffs_all
        # frequency range, samples number
        self._readFREQ = readFREQ
        self._samples = samples
        # support vectors
        self._Xm = Xm
        self._Xp = Xp
        self._filtered_mag = np.zeros(samples)
        # save current data 
        mag   = self._Xm
        phase = self._Xp ############################
        # Initializations of support vectors for later storage
        self._Xm = np.linspace(0,0,self._samples)
        self._Xp = np.linspace(0,0,self._samples)
        
        # Evaluate a polynomial at specific values based on the coefficients and frequency range
        self._polyfitted = np.polyval(self._coeffs_all,self._readFREQ)
        
        # BASELINE CORRECTION ROI (raw data)
        mag_beseline_corrected = mag-self._polyfitted
        
        # FILTERING - Savitzky-Golay
        filtered_mag = self.savitzky_golay(mag_beseline_corrected, window_size = SG_window_size, order = Constants.SG_order)
        
        # peak, index e frequency of max detection baseline corrected (filtering optional)
        #self._vector_max_baseline_corrected.append(max(mag_beseline_corrected))   #Z axis (max)
        #self._index_max_baseline_corrected.append(np.argmax(mag_beseline_corrected, axis=0)) # X axis (max position)
        #h=self._index_max_baseline_corrected.append(np.argmax(mag_beseline_corrected, axis=0))
        #self._freq_max_baseline_corrected.append(readFREQ[int(h)])
        
        # FITTING/INTERPOLATING - SPLINE
        xrange = range(len(filtered_mag))
        freq_range = np.linspace(self._readFREQ[0], self._readFREQ[-1], points)
        s = UnivariateSpline(xrange, filtered_mag, s= Spline_factor)
        xs = np.linspace(0, len(filtered_mag)-1, points)
        mag_result_fit = s(xs)
        
        # PARAMETERS FINDER
        (index_peak_fit, max_peak_fit, bandwidth_fit,index_f1_fit,index_f2_fit, Qfac_fit)= self.parameters_finder(freq_range, mag_result_fit, percent=0.707)
        
        # BANDWIDTH 70.7% of MAX
        #self._bw3.append(bandwidth_fit)
        # Q FACTOR/DISSIPATION
        #self._q_factor.append (1/Qfac_fit)
        # Index of MAX fitted signals ()
        #self._index_max_fit[k]= int(index_peak_fit)
        # Frequency of MAX fitted signals ()
        #self._freq_max_fit.append(freq_range[int(index_peak_fit)])
        #self._temperature.append(temperature)
        #######################################################
        
        self._frequency_buffer.append(freq_range[int(index_peak_fit)])
        self._dissipation_buffer.append(1/Qfac_fit)
        self._temperature_buffer.append(temperature)
        
        if self._k>=self._environment:
           #FREQUENCY
           vec_app1 = self.savitzky_golay(self._frequency_buffer.get_all(), window_size = Constants.SG_window_environment, order = Constants.SG_order_environment)
           freq_range_mean = np.average(vec_app1)
           #DISSIPATION
           vec_app1d = self.savitzky_golay(self._dissipation_buffer.get_all(), window_size = Constants.SG_window_environment, order = Constants.SG_order_environment)
           diss_mean = np.average(vec_app1d)
           #TEMPERATURE
           vec_app1t = self.savitzky_golay(self._temperature_buffer.get_all(), window_size = Constants.SG_window_environment, order = Constants.SG_order_environment)
           temperature_mean = np.average(vec_app1t)

           # AUTO-TRACKING: Check for frequency drift and update sweep window if needed
           # This is checked after the environment averaging for stable measurements
           self.check_and_update_tracking(freq_range_mean, self._samples)
           
        #else:
           #freq_range_mean = freq_range[int(index_peak_fit)]
           #temperature_mean = temperature
           #diss_mean = 1/Qfac_fit
           #freq_range_mean = freq_range[int(index_peak_fit)]
           #diss_mean = 1/Qfac_fit
           #temperature_mean = temperature
        # vector of MAX fitted signals ()
        #self._vector_max_fit.append(max_peak_fit)
        
        #######################################################
        ##############
        import datetime
        epoch= datetime.datetime(1970, 1, 1, 0, 0) #offset-naive datetime
        ts_mult=1e6
        w = (int((datetime.datetime.now() - epoch).total_seconds()*ts_mult)) #datetime.datetime.utcnow()
        ##############
        ## ADDS new serial data to internal queue
        self._parser1.add1(filtered_mag) ##############
        self._parser2.add2(phase)        ##############
        # Adds new calculated data (resonance frequency and dissipation) to internal queues
        #self._parser3.add3([time()-timestamp,freq_range[int(index_peak_fit)]])
        self._parser3.add3([w,freq_range_mean]) #time()-timestamp - time in seconds
        #self._parser4.add4([time()-timestamp,1/Qfac_fit])
        self._parser4.add4([w,diss_mean]) #time()-timestamp - time in seconds
        #self._parser5.add5([time()-timestamp,temperature])
        self._parser5.add5([w,temperature_mean]) #time()-timestamp - time in seconds
        '''
        ##############################
        # DATA STORING in CSV/TXT FILE
        ##############################
        import csv
        from time import strftime, localtime
        # STORING DATA (CSV) in main folder: Time,resonance Frequency,Dissipation
        filename = 'data_q.csv'
        with open(filename,'a', newline='') as tempFile:
         tempFileWriter = csv.writer(tempFile)
         tempFileWriter.writerow([strftime(Constants.csv_default_filename, localtime()),freq_range[int(index_peak_fit)],1/Qfac_fit])
        tempFile.close() 
        '''
        '''
        import csv
        # STORING DATA (CSV) in main folder: Time,resonance Frequency,Dissipation
        filename = 'bw3.csv'
        with open(filename,'a', newline='') as tempFile:
         tempFileWriter = csv.writer(tempFile)
         tempFileWriter.writerow(self._bw3)
        tempFile.close()
        
        filename1 = 'vector_max.csv'
        with open(filename1,'a', newline='') as tempFile1:
         tempFileWriter = csv.writer(tempFile1)
         tempFileWriter.writerow(self._vector_max_fit)
        tempFile.close()
        '''
        # STORING DATA (CSV/TXT) in 'data' folder: frequency, amplitude
        #np.savetxt(r"logged_data\sweep_%d_mag_raw.txt"%(k,), np.column_stack([readFREQ,mag]))
        #np.savetxt(r"logged_data\data\sweep_%d_mag_baseline_corrected.txt"%(k,), np.column_stack([readFREQ,mag_beseline_corrected]))
        #np.savetxt(r"data\sweep_%d_mag_baseline_corrected.csv"%(k,), np.column_stack([readFREQ,globals()["Af_baseline_" + str(k)]]), delimiter=',')
        #np.savetxt(r"logged_data\data\sweep_%d_mag_filtered.txt"%(k,), np.column_stack([readFREQ,filtered_mag]))
        #np.savetxt(r"logged_data\data\sweep_%d_mag_fitted.txt"%(k,), np.column_stack([freq_range,mag_result_fit]))
        ##############
        

    ###########################################################################
    # Initializing values for process
    ###########################################################################
    def __init__(self, parser_process):
        """
        :param parser_process: Reference to a ParserProcess instance.
        :type parser_process: ParserProcess.
        """
        multiprocessing.Process.__init__(self)
        self._exit = multiprocessing.Event()
        
        # Instantiate a ParserProcess class for each communication channels
        self._parser1 = parser_process
        self._parser2 = parser_process
        self._parser3 = parser_process
        self._parser4 = parser_process
        self._parser5 = parser_process
        self._parser6 = parser_process
        self._parser_tracking = parser_process  # AUTO-TRACKING: for GUI notifications
        self._serial = serial.Serial()
        
    ###########################################################################
    # Opens a specified serial port
    ###########################################################################    
    def open(self, port, 
                   speed = Constants.serial_default_overtone, 
                   timeout = Constants.serial_timeout_ms, 
                   writeTimeout = Constants.serial_writetimeout_ms):
        """
        :param port: Serial port name :type port: str.
        :param speed: Overtone selected for the analysis :type speed: str.
        :param timeout: Sets current read timeout :type timeout: float (seconds).
        :param writetTimeout: Sets current write timeout :type writeTimeout: float (seconds).
        :return: True if the port is available :rtype: bool.
        """
    
        self._serial.port = port
        self._serial.baudrate = Constants.serial_default_speed #115200
        self._serial.stopbits = serial.STOPBITS_ONE
        self._serial.bytesize = serial.EIGHTBITS
        self._serial.timeout = timeout
        self._serial.writetimeout = writeTimeout
        
        #self._overtone = float(speed)
        # Loads frequencies from file
        peaks_mag = self.load_frequencies_file()
        
        # handles the exceptions
        try:
           self._overtone = float(speed)
        except:   
           print(TAG, "Warning: wrong frequency selection, set default to {} Hz Fundamental".format(peaks_mag[0]))
           self._overtone = peaks_mag[0]
    
        self._overtone_int = None
        for i in range(len(peaks_mag)):
            if self._overtone == peaks_mag[i]:
               self._overtone_int = i
        # Checks for correct frequency selection
        if self._overtone_int == None:
           print(TAG, "Warning: wrong frequency selection, set default to {} Hz Fundamental".format(peaks_mag[0])) 
           self._overtone_int = 0

        return self._is_port_available(self._serial.port)
    
    ###########################################################################
    # Reads the serial port,processes and adds all the data to internal queues
    ###########################################################################
    def run(self):
        """
        The expected format is a buffer (sweep) and a new buffer as a new sweep. 
        The method parses data, converts each value to float and adds to a queue. 
        If incoming data can't be converted to float,the data will be discarded.
        """  
        # initializations
        #self._vector_max_baseline_corrected = []
        #self._index_max_baseline_corrected = []
        #self._freq_max_baseline_corrected = []
        #self._vector_max_fit = []
        #self._index_max_fit = []
        #self._bw3 = []
        #self._q_factor = []
        #self._freq_max_fit = []
        #self._temperature = []
        self._flag_error = 0
        self._flag_error_usb = 0
        self._err1 = 0
        self._err2 = 0
              
        # CALLS baseline_coeffs method
        coeffs_all = self.baseline_coeffs()
        
        # Checks if the serial port is currently connected
        if self._is_port_available(self._serial.port):

            samples = Constants.argument_default_samples 
            # Calls get_frequencies method:
            # ACQUIRES overtone, sets start and stop frequencies, the step and range frequency according to the number of samples
            (overone_name,overtone_value,fStep,readFREQ,SG_window_size,Spline_points,Spline_factor) = self.get_frequencies(samples)

            # AUTO-TRACKING: Initialize reference frequency and tracking variables
            self._reference_frequency = overtone_value  # Initial reference from calibration
            self._readFREQ = readFREQ  # Store for later updates
            self._spline_points = Spline_points
            self._auto_tracking_count = 0  # Counter for tracking activations
            self._fStep = fStep  # Store for later updates
            self._SG_window_size = SG_window_size  # Store for later updates
            self._Spline_factor = Spline_factor  # Store for later updates
            self._coeffs_all = coeffs_all  # Store baseline coefficients for updates
            
            # Gets the state of the serial port
            if not self._serial.isOpen(): 
                # OPENS the serial port
                self._serial.open() 
                # Initializes the sweep counter
                k=0 
                print(TAG,'Capturing raw data...')
                print(TAG,'Wait, processing early data...')
                # creates a timestamp
                timestamp = time()
                
                self._environment = Constants.environment
                self._frequency_buffer   = RingBuffer(self._environment)
                self._dissipation_buffer = RingBuffer(self._environment)
                self._temperature_buffer = RingBuffer(self._environment)
                # Initializes the progress bar  
                bar = ProgressBar(widgets=[TAG,' ', Bar(marker='>'),' ',Percentage(),' ', Timer()], maxval=self._environment).start() #
                _prev_cycle_time = None
                #### SWEEPS LOOP ####
                while not self._exit.is_set():
                    # data reset for new sweep 
                    data_mag = np.linspace(0,0,samples)   
                    data_ph  = np.linspace(0,0,samples)
                    
                    try:
                        # amplitude/phase convert bit to dB/Deg parameters
                        vmax = 3.3
                        bitmax = 8192 
                        ADCtoVolt = vmax / bitmax
                        VCP = 0.9
                        
                        # WRITES encoded command to the serial port
                        # AUTO-TRACKING: Use instance variables that get updated when tracking activates
                        cmd = str(self._startFreq) + ';' + str(self._stopFreq) + ';' + str(int(self._fStep)) + '\n'
                        self._serial.write(cmd.encode())
                        
                        # Initializes buffer and strs record
                        buffer = ''
                        strs = ["" for x in range(samples + 2)]
                        
                        # READS and decodes sweep from the serial port
                        while 1:
                         buffer += self._serial.read(self._serial.inWaiting()).decode(Constants.app_encoding)
                         #if '\n' in buffer:
                         if 's' in buffer:
                              break
                        data_raw = buffer.split('\n')
                        length = len(data_raw)
                        
                        # PERFORMS split with the semicolon delimiter
                        for i in range (length):
                            strs[i] = data_raw[i].split(';')

                        # CONVERTS the sweep samples before adding to queue
                        for i in range (length - 2):
                            data_mag[i] = float(strs[i][0]) * ADCtoVolt / 2
                            data_mag[i] = (data_mag[i]-VCP) / 0.03
                            data_ph[i] = float(strs[i][1]) * ADCtoVolt / 1.5
                            data_ph[i] = (data_ph[i]-VCP) / 0.01
                        
                        # ACQUIRES the temperature value from the buffer 
                        data_temp = float((strs[length - 2][0]))
                            
                    # specify handlers for different exceptions        
                    except ValueError:
                        print(TAG, "WARNING (ValueError): convert raw to float failed", end='\r')
                        #Log.w(TAG, "Warning (ValueError): convert Raw to float failed")
                    except:
                        #if self._flag_error_usb == 1:
                        print(TAG, "WARNING (ValueError): convert raw to float failed", end='\r')
                        self._flag_error_usb += 1
                        #Log.w(TAG, "Warning (ValueError): convert Raw to float failed")
                        
                    ## ADDS new serial data to internal queue
                    #self._parser1.add1(data_mag)
                    #self._parser2.add2(data_ph)
                    
                    # Calls elaborate method to performs results
                    # AUTO-TRACKING: Use instance variables that get updated when tracking activates
                    try:
                        self.elaborate(k, self._coeffs_all, self._readFREQ, samples, data_mag, data_ph, data_temp, self._SG_window_size, self._spline_points, self._Spline_factor, timestamp)
                    except ValueError:
                        self._flag_error = 1
                        #if k > self._environment:
                        #   print(TAG, "WARNING (ValueError): miscalculation")
                    except:
                        self._flag_error = 1
                        #if k > self._environment:
                        #   print(TAG, "WARNING (ValueError): miscalculation")
                    _now = time()
                    _sampling_time = (_now - _prev_cycle_time) if _prev_cycle_time is not None else 0.0
                    _prev_cycle_time = _now
                    self._parser6.add6([self._err1,self._err2,k,self._flag_error_usb,_sampling_time])
                    if k<= self._environment:
                       bar.update(k)
                    elif k/50 == k//50:
                      if k==100:
                         print('\n')
                      print(TAG,"sweep #{}               ".format(k), end='\r')
                    # refreshes error variables at each sweep
                    self._err1 = 0
                    self._err2 = 0
                    # Increases sweep counter 
                    k+=1
                if k== self._environment:
                   bar.finish()
                #### END SWEEPS LOOP ####    
                # CLOSES serial port
                self._serial.close()
          
    ###########################################################################
    # Stops acquiring data
    ###########################################################################
    def stop(self):
        #Signals the process to stop acquiring data.
        self._exit.set()
        
        
    ###########################################################################    
    # Automatically selects the serial ports for Teensy (macox/windows)
    ###########################################################################
    @staticmethod
    def get_ports(): 
        from openQCM.common.architecture import Architecture,OSType
        if Architecture.get_os() is OSType.macosx:
            import glob
            return glob.glob("/dev/tty.usbmodem*")
        elif Architecture.get_os() is OSType.linux:
            import glob
            return glob.glob("/dev/ttyACM*")
        else:
            found_ports = []
            port_connected = []
            found = False
            ports_avaiable = list(list_ports.comports())
            for port in ports_avaiable:
                if port[2].startswith("USB VID:PID=16C0:0483"):
                    found = True
                    port_connected.append(port[0])
                #else:
                #    Gets a list of the available serial ports.
                #    found_ports.append(port[0])
            if found:
               found_ports = port_connected 
            return found_ports


    ###########################################################################
    # Gets a list of the Overtones reading from file
    ###########################################################################

    @staticmethod
    def get_speeds():
        #:return: List of the Overtones :rtype: str list.
        # Loads frequencies from  file (path: 'common\')
        data  = loadtxt(Constants.cvs_peakfrequencies_path)
        peaks_mag = data[:,0]
        reversed_peaks_mag = peaks_mag[::-1]
        return [str(v) for v in reversed_peaks_mag]

    ###########################################################################
    # Checks if the serial port is currently connected
    ###########################################################################
    def _is_port_available(self, port):
        """
        :param port: Port name to be verified.
        :return: True if the port is connected to the host :rtype: bool.
        """
        for p in self.get_ports():
            if p == port:
                return True
        return False

    ###########################################################################
    # Sets frequency range for the corresponding overtone 
    ###########################################################################
    def get_frequencies(self, samples):
        """
        :param samples: Number of samples :type samples: int.
        :return: overtone :rtype: float.
        :return: fStep, frequency step  :rtype: float.
        :return: readFREQ, frequency range :rtype: float list.
        """
        # Loads frequencies from file
        peaks_mag = self.load_frequencies_file()
        
        #################################################
        # TODO CHECK QCM FUNDAMENTAL FREQ 5 MHz or 10 MHz
        #################################################
        '''
        # Checks QCS type 5Mhz or 10MHz
        # Sets start and stop frequencies for the corresponding overtone
        if len(peaks_mag) == 5:
            switch = Overtone_Switcher_5MHz(peak_frequencies = peaks_mag)
            # 0=fundamental, 1=3th overtone and so on
            (overtone_name,overtone_value, self._startFreq,self._stopFreq,SG_window_size,spline_factor) = switch.overtone5MHz_to_freq_range(self._overtone_int)
            print(TAG,"openQCM Device setup: @5MHz")
        elif len(peaks_mag) == 3:
            switch = Overtone_Switcher_10MHz(peak_frequencies = peaks_mag)
            (overtone_name, overtone_value, self._startFreq,self._stopFreq,SG_window_size,spline_factor) = switch.overtone10MHz_to_freq_range(self._overtone_int)
            print(TAG,"openQCM Device setup: @10MHz")
        '''
        # Checks QCS type 5Mhz or 10MHz
        # Sets start and stop frequencies for the corresponding overtone
        if (peaks_mag[0] >4e+06 and peaks_mag[0]<6e+06):
            switch = Overtone_Switcher_5MHz(peak_frequencies = peaks_mag)
            # 0=fundamental, 1=3th overtone and so on
            (overtone_name,overtone_value, self._startFreq,self._stopFreq,SG_window_size,spline_factor) = switch.overtone5MHz_to_freq_range(self._overtone_int)
            print(TAG,"openQCM Device setup: @5MHz")
        elif (peaks_mag[0] >9e+06 and peaks_mag[0]<11e+06):
            switch = Overtone_Switcher_10MHz(peak_frequencies = peaks_mag)
            (overtone_name, overtone_value, self._startFreq,self._stopFreq,SG_window_size,spline_factor) = switch.overtone10MHz_to_freq_range(self._overtone_int)
            print(TAG,"openQCM Device setup: @10MHz")
        
        # Sets the frequency step 
        fStep = (self._stopFreq-self._startFreq)/(samples-1)
        
        # Sets spline points for fitting
        spline_points = int((self._stopFreq-self._startFreq))+1
        
        # Sets the frequency range for the corresponding overtone
        readFREQ = np.arange(samples) * (fStep) + self._startFreq 
        return overtone_name, overtone_value, fStep, readFREQ,SG_window_size, spline_points, spline_factor
    
    
    ###########################################################################
    # Loads Fundamental frequency and Overtones from file
    ###########################################################################
    @staticmethod
    def load_frequencies_file():
        data  = loadtxt(Constants.cvs_peakfrequencies_path)
        peaks_mag = data[:,0]
        #peaks_phase = data[:,1] #unused at the moment
        return peaks_mag
        
    
    ###########################################################################
    # Loads Calibration (baseline correction) from file
    ###########################################################################
    def load_calibration_file(self):
        # Loads Fundamental frequency and Overtones from file
        peaks_mag = self.load_frequencies_file()
        
        ############################### 
        # TODO check the damn QCM type 
        ###############################
        
        '''
        # Checks QCS type 5Mhz or 10MHz
        if len(peaks_mag) == 5:
           filename = Constants.csv_calibration_path
        elif len(peaks_mag) == 3:
           filename = Constants.csv_calibration_path10 
        '''
        
        # Checks QCS type 5Mhz or 10MHz
        if (peaks_mag[0] >4e+06 and peaks_mag[0]<6e+06):
           filename = Constants.csv_calibration_path
        elif (peaks_mag[0] >9e+06 and peaks_mag[0]<11e+06):
           filename = Constants.csv_calibration_path10 
        
        
        data  = loadtxt(filename)
        freq_all  = data[:,0]
        mag_all   = data[:,1]
        phase_all = data[:,2]
        return freq_all, mag_all, phase_all
      
    
# Instantiate the process and run the method 'run' of the class
#a=SerialProcess(multiprocessing.Process)
#a.run()
