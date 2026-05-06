"""
SerialProcess — child process driving the openQCM Q-1 acquisition pipeline.

Responsibilities:
    1. Open the serial port and stream sweep commands to the firmware.
    2. Parse the incoming raw amplitude/phase samples from the board.
    3. Apply baseline correction, Savitzky-Golay smoothing and spline
       interpolation to extract the resonance peak.
    4. Compute resonance frequency, -3dB bandwidth, Q-factor and dissipation.
    5. Aggregate `Constants.environment` consecutive sweeps with a trimmed
       mean and push the smoothed values to the GUI via parser queues.
    6. Maintain auto-tracking: recentre the sweep window when the resonance
       drifts more than `Constants.auto_tracking_threshold` Hz, and disable
       tracking automatically when the peak is lost for too many consecutive
       sweeps (with automatic recovery when the peak returns).

The class runs as a `multiprocessing.Process`. Communication with the GUI
goes exclusively through the shared `ParserProcess` queues passed to the
constructor. There is no direct GUI access from this process.
"""
import multiprocessing
from time import time, sleep

import serial
from serial.tools import list_ports
import numpy as np
from numpy import loadtxt
from scipy.interpolate import UnivariateSpline
from scipy.stats import trim_mean
from progressbar import Bar, Percentage, ProgressBar, RotatingMarker, Timer

from openQCM.core.ringBuffer import RingBuffer
from openQCM.core.constants import Constants
from openQCM.common.fileStorage import FileStorage
from openQCM.common.logger import Logger as Log
from openQCM.common.switcher import Overtone_Switcher_5MHz, Overtone_Switcher_10MHz


TAG = ""  # set to "[Serial]" for verbose tagged prints


class SerialProcess(multiprocessing.Process):

    # ------------------------------------------------------------------
    # Initialisation / lifecycle
    # ------------------------------------------------------------------
    def __init__(self, parser_process):
        """
        :param parser_process: shared ParserProcess used to forward data to the
                               GUI through six dedicated queues plus a tracking
                               notification channel.
        """
        multiprocessing.Process.__init__(self)
        self._exit = multiprocessing.Event()

        # All channels share the same ParserProcess instance; aliases are kept
        # for readability where each one is used.
        self._parser1 = parser_process          # amplitude trace
        self._parser2 = parser_process          # phase trace
        self._parser3 = parser_process          # resonance frequency
        self._parser4 = parser_process          # dissipation
        self._parser5 = parser_process          # temperature
        self._parser6 = parser_process          # error flags / status
        self._parser_tracking = parser_process  # auto-tracking notifications

        self._serial = serial.Serial()

    def stop(self):
        """Request the run loop to exit at the next iteration."""
        self._exit.set()

    # ------------------------------------------------------------------
    # Auto-tracking
    # ------------------------------------------------------------------
    def check_and_update_tracking(self, current_freq, samples):
        """
        Recentre the sweep window if the resonance frequency has drifted more
        than `Constants.auto_tracking_threshold` Hz from the current reference.

        Skipped if tracking has been disabled by the safety logic (peak lost).

        :param current_freq: smoothed resonance frequency (Hz)
        :param samples:      number of samples per sweep
        :return:             True if the window was updated, False otherwise
        """
        if getattr(self, '_tracking_disabled_by_errors', False):
            return False

        freq_drift = abs(current_freq - self._reference_frequency)
        if freq_drift <= Constants.auto_tracking_threshold:
            return False

        old_ref_freq = self._reference_frequency
        old_start = self._startFreq
        old_stop = self._stopFreq

        # Move the reference and rebuild the sweep window around it
        self._reference_frequency = current_freq
        L_interval, R_interval = self._get_overtone_intervals()
        self._startFreq = current_freq - L_interval
        self._stopFreq  = current_freq + R_interval

        # Recompute step, range and spline grid for the new window
        self._fStep = (self._stopFreq - self._startFreq) / (samples - 1)
        self._readFREQ = np.arange(samples) * self._fStep + self._startFreq
        self._spline_points = int((self._stopFreq - self._startFreq)) + 1

        # The baseline polynomial was fit on the full calibration spectrum;
        # we just re-evaluate it on the new frequency points.
        self._recalculate_baseline_for_range()

        self._auto_tracking_count += 1

        print("\n" + "=" * 60)
        print(" AUTO-TRACKING ACTIVATED (#{})".format(self._auto_tracking_count))
        print("=" * 60)
        print(" Frequency drift: {:.2f} Hz (threshold: {} Hz)".format(
            freq_drift, Constants.auto_tracking_threshold))
        print(" Old reference:   {:.2f} Hz".format(old_ref_freq))
        print(" New reference:   {:.2f} Hz".format(current_freq))
        print(" Old window:      {:.0f} - {:.0f} Hz".format(old_start, old_stop))
        print(" New window:      {:.0f} - {:.0f} Hz".format(self._startFreq, self._stopFreq))
        print("=" * 60 + "\n")

        # Notify the GUI; payload format documented in worker._queue_data_tracking
        self._parser_tracking.add_tracking([
            True,                       # activated
            self._startFreq,
            self._stopFreq,
            self._reference_frequency,
            self._auto_tracking_count,
        ])
        return True

    def _get_overtone_intervals(self):
        """
        Return the (L, R) frequency intervals defining the asymmetric sweep
        window around the current reference. The choice of intervals depends on
        the sensor type (5/10 MHz, inferred from the reference frequency) and
        on the selected overtone index `_overtone_int`.

        :return: (L_interval_Hz, R_interval_Hz)
        """
        ref = self._reference_frequency

        # 5 MHz sensor: F0 ≈ 5 MHz; its odd overtones reach up to ~45 MHz.
        # We detect 5 MHz by the *fundamental* range (4–6 MHz). Higher overtones
        # of a 5 MHz sensor live above 9 MHz so we identify them by index.
        if 4e6 < ref < 6e6:
            return {
                0: (Constants.L5_fundamental,  Constants.R5_fundamental),
                1: (Constants.L5_3th_overtone, Constants.R5_3th_overtone),
                2: (Constants.L5_5th_overtone, Constants.R5_5th_overtone),
                3: (Constants.L5_7th_overtone, Constants.R5_7th_overtone),
                4: (Constants.L5_9th_overtone, Constants.R5_9th_overtone),
            }.get(self._overtone_int, (15000, 5000))

        # 10 MHz sensor or higher overtones (covers F0=10 MHz, F3=30 MHz, F5=50 MHz)
        if 9e6 < ref < 51e6:
            return {
                0: (Constants.L10_fundamental,  Constants.R10_fundamental),
                1: (Constants.L10_3th_overtone, Constants.R10_3th_overtone),
                2: (Constants.L10_5th_overtone, Constants.R10_5th_overtone),
            }.get(self._overtone_int, (15000, 5000))

        # Fallback: should not happen if calibration produced a valid F0
        return 15000, 5000

    def _recalculate_baseline_for_range(self):
        """Re-evaluate the calibration baseline polynomial on the new sweep grid."""
        self._polyfitted = np.polyval(self._coeffs_all, self._readFREQ)

    # ------------------------------------------------------------------
    # Baseline correction (LSP — Least-Squares Polynomial fit)
    # ------------------------------------------------------------------
    def baseline_correction(self, x, y, poly_order):
        """Fit `y` with a polynomial of given order over `x`; return (poly_y, coeffs)."""
        coeffs = np.polyfit(x, y, poly_order)
        poly_fitted = np.polyval(coeffs, x)
        return poly_fitted, coeffs

    def baseline_coeffs(self):
        """
        Read the calibration sweep file, fit an 8th-order polynomial to both
        amplitude and phase, store the fits and corrected signals on self,
        and return the amplitude polynomial coefficients (used by `elaborate`
        to subtract the baseline at runtime).
        """
        self.polyfitted_all = None
        self.coeffs_all = None
        self.polyfitted_all_phase = None
        self.coeffs_all_phase = None

        (self.freq_all, self.mag_all, self.phase_all) = self.load_calibration_file()

        (self.polyfitted_all, self.coeffs_all) = self.baseline_correction(
            self.freq_all, self.mag_all, 8)
        self.mag_beseline_corrected_all = self.mag_all - self.polyfitted_all

        (self.polyfitted_all_phase, self.coeffs_all_phase) = self.baseline_correction(
            self.freq_all, self.phase_all, 8)
        self.phase_beseline_corrected_all = self.phase_all - self.polyfitted_all_phase

        return self.coeffs_all

    # ------------------------------------------------------------------
    # Savitzky-Golay smoothing filter
    # ------------------------------------------------------------------
    def savitzky_golay(self, y, window_size, order, deriv=0, rate=1):
        """
        Savitzky-Golay smoothing (or differentiation) filter.

        Fits a polynomial of order `order` over a sliding odd-sized window
        and evaluates it at the central point. Preserves peak shape better
        than a plain moving average. See:
            Savitzky & Golay, Anal. Chem. 36 (1964) 1627–1639.

        :param y:           input 1D array
        :param window_size: odd integer ≥ order + 2
        :param order:       polynomial order
        :param deriv:       derivative order (0 = pure smoothing)
        :param rate:        sampling rate (used only when deriv > 0)
        :return:            smoothed (or differentiated) array, same length as `y`
        """
        from math import factorial
        try:
            window_size = np.abs(np.int(window_size))
            order = np.abs(np.int(order))
        except ValueError:
            raise ValueError("window_size and order must be integers")
        if window_size % 2 != 1 or window_size < 1:
            raise TypeError("window_size must be a positive odd number")
        if window_size < order + 2:
            raise TypeError("window_size is too small for the polynomial order")

        order_range = range(order + 1)
        half_window = (window_size - 1) // 2
        # Filter coefficients via least-squares pseudo-inverse
        b = np.mat([[k**i for i in order_range]
                    for k in range(-half_window, half_window + 1)])
        m = np.linalg.pinv(b).A[deriv] * rate**deriv * factorial(deriv)
        # Mirror padding at the boundaries so the output has the same length
        firstvals = y[0]  - np.abs(y[1:half_window+1][::-1] - y[0])
        lastvals  = y[-1] + np.abs(y[-half_window-1:-1][::-1] - y[-1])
        y = np.concatenate((firstvals, y, lastvals))
        return np.convolve(m[::-1], y, mode='valid')

    # ------------------------------------------------------------------
    # Resonance peak / Q-factor extraction
    # ------------------------------------------------------------------
    def parameters_finder(self, freq, signal, percent):
        """
        Locate the resonance peak and compute its -3dB bandwidth (here at
        `percent` × peak amplitude, by default 0.707 → -3dB / FWHM).

        Walks left and right from the peak sample until the signal drops below
        the threshold, then linearly interpolates to the exact crossing
        frequency. Sets `self._err1` / `self._err2` to 1 if either edge cannot
        be found, or if the resulting Q-factor is below
        `Constants.min_valid_q_factor` (used to detect a disconnected sensor —
        the board still streams amplifier noise, but the noise has Q ≪ 100).

        :param freq:    frequency axis of the (oversampled) signal
        :param signal:  amplitude signal, baseline-corrected and smoothed
        :param percent: amplitude threshold for the bandwidth (0.707 → FWHM)
        :return: (i_peak, peak_amp, bandwidth, i_left, i_right, Q_factor)
        """
        f_max = np.max(signal)
        i_max = np.argmax(signal, axis=0)

        # Walk left from the peak until the signal drops below percent*f_max
        index_m = i_max
        while signal[index_m] > percent * f_max:
            if index_m < 1:
                self._err1 = 1
                break
            index_m -= 1
        # Linear interpolation for the exact left -3dB crossing
        m = (signal[index_m+1] - signal[index_m]) / (freq[index_m+1] - freq[index_m])
        c = signal[index_m] - freq[index_m] * m
        i_leading = (percent * f_max - c) / m

        # Walk right from the peak
        index_M = i_max
        while signal[index_M] > percent * f_max:
            if index_M >= len(signal) - 1:
                self._err2 = 1
                break
            index_M += 1
        # Linear interpolation for the exact right -3dB crossing
        m = (signal[index_M-1] - signal[index_M]) / (freq[index_M-1] - freq[index_M])
        c = signal[index_M] - freq[index_M] * m
        i_trailing = (percent * f_max - c) / m

        bandwidth = abs(i_trailing - i_leading)
        # If both edges collapsed to the peak sample, bandwidth is 0 → let
        # numpy produce +inf (silenced via errstate) so that downstream
        # 1/Qfac = 0 gives dissipation = 0 (no visible spike on the plot).
        with np.errstate(divide='ignore', invalid='ignore'):
            Qfac = freq[i_max] / bandwidth

        # Sensor-disconnect detection: a real QCM resonance has Q ≫ 100;
        # pure amplifier noise gives a tiny Q. Inf passes the check.
        if Qfac < Constants.min_valid_q_factor:
            self._err1 = 1
            self._err2 = 1

        return i_max, f_max, bandwidth, index_m, index_M, Qfac

    # ------------------------------------------------------------------
    # Per-sweep processing pipeline
    # ------------------------------------------------------------------
    def elaborate(self, k, coeffs_all, readFREQ, samples,
                  Xm, Xp, temperature,
                  SG_window_size, Spline_points, Spline_factor, timestamp):
        """
        Process one acquired sweep:
            1. Subtract baseline polynomial from raw amplitude.
            2. Apply Savitzky-Golay smoothing.
            3. Spline-interpolate to oversample the peak region.
            4. Find peak, bandwidth, Q-factor.
            5. Append per-sweep values to the circular buffers.
            6. After the buffer is full (k ≥ environment), aggregate via
               trimmed mean and push to GUI queues. Also runs auto-tracking.
            7. Update the tracking-safety counter (disable / re-enable).

        Per-sweep raw values are appended without filtering; the smoothing
        happens in the buffer aggregation step (trimmed mean) before sending
        to the GUI.
        """
        points = Spline_points
        self._k = k
        self._coeffs_all = coeffs_all
        self._readFREQ = readFREQ
        self._samples = samples
        self._Xm = Xm
        self._Xp = Xp
        self._filtered_mag = np.zeros(samples)

        mag = self._Xm
        phase = self._Xp
        # Reset support vectors for the next sweep
        self._Xm = np.linspace(0, 0, self._samples)
        self._Xp = np.linspace(0, 0, self._samples)

        # 1. Baseline subtraction
        self._polyfitted = np.polyval(self._coeffs_all, self._readFREQ)
        mag_beseline_corrected = mag - self._polyfitted

        # 2. Savitzky-Golay smoothing
        filtered_mag = self.savitzky_golay(
            mag_beseline_corrected,
            window_size=SG_window_size,
            order=Constants.SG_order)

        # 3. Spline interpolation onto a finer grid (oversampling around the peak)
        xrange = range(len(filtered_mag))
        freq_range = np.linspace(self._readFREQ[0], self._readFREQ[-1], points)
        spline = UnivariateSpline(xrange, filtered_mag, s=Spline_factor)
        xs = np.linspace(0, len(filtered_mag) - 1, points)
        mag_result_fit = spline(xs)

        # 4. Resonance peak / bandwidth / Q-factor
        (index_peak_fit, max_peak_fit, bandwidth_fit,
         index_f1_fit, index_f2_fit, Qfac_fit) = self.parameters_finder(
            freq_range, mag_result_fit, percent=0.707)

        # Tracking safety: track how many consecutive sweeps fail to find
        # *both* -3dB frequencies. After enough failures the auto-tracking
        # is disabled to avoid chasing a ghost. As soon as the peak is back
        # with at least one -3dB frequency, tracking re-enables itself.
        both_edges_missing = (self._err1 == 1 and self._err2 == 1)
        if both_edges_missing:
            self._consecutive_edge_errors += 1
            if (self._consecutive_edge_errors >= Constants.auto_tracking_max_edge_errors
                    and not self._tracking_disabled_by_errors):
                self._tracking_disabled_by_errors = True
                self._parser_tracking.add_tracking([
                    False, None, None, None,
                    self._auto_tracking_count,
                    True,   # disabled_by_errors
                ])
                print("\n" + "=" * 60)
                print(" AUTO-TRACKING DISABLED")
                print(" Reason: both -3dB frequencies missing for {} consecutive sweeps"
                      .format(self._consecutive_edge_errors))
                print(" Will auto-resume when peak and at least one -3dB frequency reappear")
                print("=" * 60 + "\n")
        else:
            self._consecutive_edge_errors = 0
            if self._tracking_disabled_by_errors:
                self._tracking_disabled_by_errors = False
                self._parser_tracking.add_tracking([
                    False, None, None, None,
                    self._auto_tracking_count,
                    False,  # disabled_by_errors → re-enabled
                ])
                print("\n" + "=" * 60)
                print(" AUTO-TRACKING RE-ENABLED")
                print(" Peak recovered — resuming resonance tracking")
                print("=" * 60 + "\n")

        # 5. Append per-sweep values to the circular buffers
        self._frequency_buffer.append(freq_range[int(index_peak_fit)])
        self._dissipation_buffer.append(1 / Qfac_fit)
        self._temperature_buffer.append(temperature)

        # 6. Trimmed-mean aggregation (after the warm-up window)
        if self._k >= self._environment:
            trim_fraction = Constants.trim_mean_fraction
            freq_range_mean  = trim_mean(self._frequency_buffer.get_all(),  trim_fraction)
            diss_mean        = trim_mean(self._dissipation_buffer.get_all(), trim_fraction)
            temperature_mean = trim_mean(self._temperature_buffer.get_all(), trim_fraction)

            # Auto-tracking is evaluated on the smoothed value, not the noisy
            # per-sweep frequency, to avoid spurious window updates.
            self.check_and_update_tracking(freq_range_mean, self._samples)

        # 7. Forward filtered traces, smoothed values and timestamp to GUI queues
        import datetime
        epoch = datetime.datetime(1970, 1, 1, 0, 0)
        ts_us = int((datetime.datetime.now() - epoch).total_seconds() * 1e6)

        self._parser1.add1(filtered_mag)
        self._parser2.add2(phase)
        self._parser3.add3([ts_us, freq_range_mean])
        self._parser4.add4([ts_us, diss_mean])
        self._parser5.add5([ts_us, temperature_mean])

    # ------------------------------------------------------------------
    # Serial port lifecycle
    # ------------------------------------------------------------------
    def open(self, port,
             speed=Constants.serial_default_overtone,
             timeout=Constants.serial_timeout_ms,
             writeTimeout=Constants.serial_writetimeout_ms):
        """
        Configure the serial port and select the overtone to acquire.

        :param port:         serial device path / COM name
        :param speed:        overtone frequency (Hz) selected by the user; if
                             not present in PeakFrequencies.txt, falls back to
                             the fundamental
        :param timeout:      read timeout in seconds
        :param writeTimeout: write timeout in seconds
        :return:             True if the port is currently available
        """
        self._serial.port = port
        self._serial.baudrate = Constants.serial_default_speed
        self._serial.stopbits = serial.STOPBITS_ONE
        self._serial.bytesize = serial.EIGHTBITS
        self._serial.timeout = timeout
        self._serial.writetimeout = writeTimeout

        # Match the requested overtone frequency against the calibration peaks.
        peaks_mag = self.load_frequencies_file()
        try:
            self._overtone = float(speed)
        except Exception:
            print(TAG, "Warning: invalid overtone selection, defaulting to fundamental {} Hz"
                  .format(peaks_mag[0]))
            self._overtone = peaks_mag[0]

        self._overtone_int = None
        for i in range(len(peaks_mag)):
            if self._overtone == peaks_mag[i]:
                self._overtone_int = i
        if self._overtone_int is None:
            print(TAG, "Warning: overtone not found in calibration, defaulting to fundamental {} Hz"
                  .format(peaks_mag[0]))
            self._overtone_int = 0

        return self._is_port_available(self._serial.port)

    # ------------------------------------------------------------------
    # Acquisition loop
    # ------------------------------------------------------------------
    def run(self):
        """
        Main acquisition loop. Runs in the child process until `stop()` is
        called. Each iteration:
            1. Sends the current sweep window to the firmware
            2. Reads back the amplitude/phase samples
            3. Calls `elaborate()` to extract resonance parameters
            4. Pushes status flags on parser6 (errors, sample count, period)
        """
        self._flag_error = 0
        self._flag_error_usb = 0
        self._err1 = 0
        self._err2 = 0
        # Tracking-safety state (per-process, reset by spawning a new process)
        self._consecutive_edge_errors = 0
        self._tracking_disabled_by_errors = False

        # Build the baseline polynomial from the calibration file
        coeffs_all = self.baseline_coeffs()
        if not self._is_port_available(self._serial.port):
            return

        samples = Constants.argument_default_samples
        (overtone_name, overtone_value, fStep, readFREQ,
         SG_window_size, Spline_points, Spline_factor) = self.get_frequencies(samples)

        # Auto-tracking state
        self._reference_frequency = overtone_value
        self._readFREQ = readFREQ
        self._spline_points = Spline_points
        self._auto_tracking_count = 0
        self._fStep = fStep
        self._SG_window_size = SG_window_size
        self._Spline_factor = Spline_factor
        self._coeffs_all = coeffs_all

        if self._serial.isOpen():
            return  # Port already open: nothing to do

        self._serial.open()
        k = 0
        print(TAG, 'Capturing raw data...')
        print(TAG, 'Wait, processing early data...')
        timestamp = time()

        # Circular buffers used by the trimmed-mean aggregation in elaborate()
        self._environment = Constants.environment
        self._frequency_buffer   = RingBuffer(self._environment)
        self._dissipation_buffer = RingBuffer(self._environment)
        self._temperature_buffer = RingBuffer(self._environment)

        bar = ProgressBar(
            widgets=[TAG, ' ', Bar(marker='>'), ' ', Percentage(), ' ', Timer()],
            maxval=self._environment).start()
        _prev_cycle_time = None

        # ADC scaling constants (firmware-defined)
        VMAX = 3.3              # ADC reference voltage
        BITMAX = 8192           # 13-bit ADC dynamic range
        ADC_TO_VOLT = VMAX / BITMAX
        VCP = 0.9               # AD8302 reference voltage offset

        while not self._exit.is_set():
            data_mag = np.linspace(0, 0, samples)
            data_ph  = np.linspace(0, 0, samples)

            try:
                # 1. Send sweep command — values may have been updated by auto-tracking
                cmd = "{};{};{}\n".format(
                    self._startFreq, self._stopFreq, int(self._fStep))
                self._serial.write(cmd.encode())

                # 2. Read until the trailer 's' marker
                buffer = ''
                strs = ["" for _ in range(samples + 2)]
                while True:
                    buffer += self._serial.read(self._serial.inWaiting()).decode(
                        Constants.app_encoding)
                    if 's' in buffer:
                        break
                    sleep(0.001)
                data_raw = buffer.split('\n')
                length = len(data_raw)

                # 3. Split each line on ';' and convert ADC values to dB / deg
                for i in range(length):
                    strs[i] = data_raw[i].split(';')
                for i in range(length - 2):
                    data_mag[i] = (float(strs[i][0]) * ADC_TO_VOLT / 2 - VCP) / 0.03
                    data_ph[i]  = (float(strs[i][1]) * ADC_TO_VOLT / 1.5 - VCP) / 0.01

                # Last line before the trailer holds the temperature reading
                data_temp = float(strs[length - 2][0])

            except ValueError:
                print(TAG, "WARNING (ValueError): convert raw to float failed", end='\r')
            except Exception:
                print(TAG, "WARNING: serial read/parse failed", end='\r')
                self._flag_error_usb += 1

            # 4. Elaborate the sweep (baseline, smooth, peak, dissipation)
            try:
                self.elaborate(k, self._coeffs_all, self._readFREQ, samples,
                               data_mag, data_ph, data_temp,
                               self._SG_window_size, self._spline_points,
                               self._Spline_factor, timestamp)
            except Exception:
                self._flag_error = 1

            # 5. Sampling period and status flags
            _now = time()
            _sampling_time = (_now - _prev_cycle_time) if _prev_cycle_time is not None else 0.0
            _prev_cycle_time = _now
            self._parser6.add6([self._err1, self._err2, k,
                                self._flag_error_usb, _sampling_time])

            # Progress reporting
            if k <= self._environment:
                bar.update(k)
            elif k % 50 == 0:
                if k == 100:
                    print('\n')
                print(TAG, "sweep #{}               ".format(k), end='\r')

            # Reset per-sweep error flags before the next iteration
            self._err1 = 0
            self._err2 = 0
            k += 1

        if k == self._environment:
            bar.finish()
        self._serial.close()

    # ------------------------------------------------------------------
    # Static helpers — port discovery and calibration file I/O
    # ------------------------------------------------------------------
    @staticmethod
    def get_ports():
        """
        Return the list of serial ports that look like an openQCM Q-1 device.

        On macOS / Linux this is a shell-glob match; on Windows the USB
        VID:PID identifies the Teensy on the Q-1 board.
        """
        from openQCM.common.architecture import Architecture, OSType
        if Architecture.get_os() is OSType.macosx:
            import glob
            return glob.glob("/dev/tty.usbmodem*")
        if Architecture.get_os() is OSType.linux:
            import glob
            return glob.glob("/dev/ttyACM*")
        # Windows: filter Teensy USB descriptors
        ports_available = list(list_ports.comports())
        connected = [p[0] for p in ports_available
                     if p[2].startswith("USB VID:PID=16C0:0483")]
        return connected

    @staticmethod
    def get_speeds():
        """
        Return the overtone frequencies (Hz) as strings, in descending order.

        Returns an empty list if `PeakFrequencies.txt` is missing or unreadable
        (e.g. on first launch before Peak Detection has been run). The GUI
        handles the empty list by disabling Measurement mode until a
        calibration is generated.
        """
        try:
            data = loadtxt(Constants.cvs_peakfrequencies_path)
            peaks_mag = data[:, 0]
            return [str(v) for v in peaks_mag[::-1]]
        except (OSError, IOError, ValueError, IndexError) as e:
            print(TAG, "PeakFrequencies.txt not available ({}). "
                       "Run Peak Detection first.".format(e))
            return []

    def _is_port_available(self, port):
        """True if `port` is among the discovered openQCM ports."""
        return port in self.get_ports()

    def get_frequencies(self, samples):
        """
        Build the sweep window for the currently selected overtone.

        Auto-detects the sensor type from the fundamental frequency stored in
        PeakFrequencies.txt: 4–6 MHz → 5 MHz sensor, 9–11 MHz → 10 MHz sensor.

        :param samples: number of samples per sweep
        :return: (overtone_name, overtone_value, fStep, readFREQ,
                  SG_window_size, spline_points, spline_factor)
        """
        peaks_mag = self.load_frequencies_file()

        if 4e6 < peaks_mag[0] < 6e6:
            switcher = Overtone_Switcher_5MHz(peak_frequencies=peaks_mag)
            (overtone_name, overtone_value,
             self._startFreq, self._stopFreq,
             SG_window_size, spline_factor) = switcher.overtone5MHz_to_freq_range(self._overtone_int)
            print(TAG, "openQCM Device setup: @5MHz")
        elif 9e6 < peaks_mag[0] < 11e6:
            switcher = Overtone_Switcher_10MHz(peak_frequencies=peaks_mag)
            (overtone_name, overtone_value,
             self._startFreq, self._stopFreq,
             SG_window_size, spline_factor) = switcher.overtone10MHz_to_freq_range(self._overtone_int)
            print(TAG, "openQCM Device setup: @10MHz")
        else:
            raise ValueError(
                "Unsupported fundamental frequency {} Hz — expected 5 MHz or 10 MHz QCM"
                .format(peaks_mag[0]))

        fStep = (self._stopFreq - self._startFreq) / (samples - 1)
        spline_points = int(self._stopFreq - self._startFreq) + 1
        readFREQ = np.arange(samples) * fStep + self._startFreq
        return (overtone_name, overtone_value, fStep, readFREQ,
                SG_window_size, spline_points, spline_factor)

    @staticmethod
    def load_frequencies_file():
        """Return the array of peak frequencies (Hz) from PeakFrequencies.txt."""
        data = loadtxt(Constants.cvs_peakfrequencies_path)
        return data[:, 0]

    def load_calibration_file(self):
        """
        Load the full calibration sweep matching the detected sensor type.

        :return: (frequency, magnitude, phase) arrays from Calibration_*.txt
        """
        peaks_mag = self.load_frequencies_file()
        if 4e6 < peaks_mag[0] < 6e6:
            filename = Constants.csv_calibration_path
        elif 9e6 < peaks_mag[0] < 11e6:
            filename = Constants.csv_calibration_path10
        else:
            raise ValueError(
                "Unsupported fundamental frequency {} Hz — no calibration file"
                .format(peaks_mag[0]))

        data = loadtxt(filename)
        return data[:, 0], data[:, 1], data[:, 2]
