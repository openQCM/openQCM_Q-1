"""
CalibrationProcess — child process that performs the QCM peak detection.

The calibration is run in 10 concatenated frequency sections covering 1 MHz
to 51 MHz with 1 kHz step. After the full sweep is acquired, the data is
baseline-corrected (8th-order polynomial), then a two-phase peak-detection
algorithm extracts:
    1. The fundamental resonance frequency (1–12 MHz range).
    2. The odd overtones (3×, 5×, 7×, 9× fundamental) inside narrow
       windows centred on the expected positions.

Each overtone candidate is cross-validated against its phase peak: if the
magnitude/phase peaks are too far apart, or the phase peak is too small,
the overtone is discarded.

Output files (written to `Constants.csv_calibration_export_path`):
    - `Calibration_<N>MHz.txt` — raw acquired sweep (frequency, mag, phase)
    - `PeakFrequencies.txt`    — detected peak frequencies (one per row)

If the new two-phase algorithm fails for any reason, the process falls
back to the legacy `FindPeak` algorithm based on `scipy.signal.argrelextrema`
on the full spectrum.
"""
import time
import multiprocessing

import serial
from serial.tools import list_ports
import numpy as np
import scipy.signal
from numpy import loadtxt
from progressbar import Bar, Percentage, ProgressBar, RotatingMarker, Timer

from openQCM.core.constants import Constants
from openQCM.common.fileStorage import FileStorage
from openQCM.common.logger import Logger as Log


TAG = ""  # set to "[Calibration]" for verbose tagged prints


class CalibrationProcess(multiprocessing.Process):

    # ------------------------------------------------------------------
    # Construction / lifecycle
    # ------------------------------------------------------------------
    def __init__(self, parser_process):
        """
        :param parser_process: shared ParserProcess that forwards data to the GUI.
        """
        multiprocessing.Process.__init__(self)
        self._exit = multiprocessing.Event()

        # Aliased channels — only a subset is used during calibration
        self._parser1 = parser_process     # baseline-corrected magnitude
        self._parser2 = parser_process     # baseline-corrected phase
        self._parser5 = parser_process     # error / status flags + cancel signal
        self._parser6 = parser_process     # progress flags

        self._serial = serial.Serial()

    def stop(self):
        """Request the run loop to exit at the next iteration."""
        self._exit.set()

    # ------------------------------------------------------------------
    # Baseline correction (LSP — Least-Squares Polynomial fit)
    # ------------------------------------------------------------------
    def baseline_estimation(self, x, y, poly_order):
        """Fit `y` with a polynomial of the given order; return (poly_y, coeffs)."""
        coeffs = np.polyfit(x, y, poly_order)
        poly_fitted = np.polyval(coeffs, x)
        return poly_fitted, coeffs

    def baseline_correction(self, readFREQ, data_mag, data_ph):
        """
        Apply baseline subtraction to magnitude and phase.

        Stores the polynomial fits and corrected signals as attributes
        (used by the calling code for eventual debug exports).
        """
        (self._polyfitted_all, self._coeffs_all) = self.baseline_estimation(
            readFREQ, data_mag, 8)
        self._mag_beseline_corrected_all = data_mag - self._polyfitted_all

        (self._polyfitted_all_phase, self._coeffs_all_phase) = self.baseline_estimation(
            readFREQ, data_ph, 8)
        self._phase_beseline_corrected_all = data_ph - self._polyfitted_all_phase

        return self._mag_beseline_corrected_all, self._phase_beseline_corrected_all

    # ------------------------------------------------------------------
    # Peak detection (two-phase algorithm)
    # ------------------------------------------------------------------
    def peak_detection_fundamental(self, freq, mag, phase):
        """
        Phase 1 — locate the fundamental QCM resonance in 1–12 MHz.

        Uses `scipy.signal.argrelextrema` with a large `order` so that only
        peaks well separated from each other (≥ 6 MHz) are kept. Returns the
        candidate with the highest magnitude (or 0 if none is found).
        """
        freq_arr = np.array(freq)
        mag_arr = np.array(mag)

        idx_min = np.abs(freq_arr - Constants.peak_freq_sweep_min).argmin()
        idx_max = np.abs(freq_arr - Constants.peak_freq_sweep_max).argmin()
        freq_arr_sub = freq_arr[idx_min:idx_max]
        mag_arr_sub = mag_arr[idx_min:idx_max]

        idx_mag_max_arr = scipy.signal.argrelextrema(
            data=mag_arr_sub, comparator=np.greater,
            order=Constants.peak_points_fundamental)
        if len(idx_mag_max_arr[0]) == 0:
            print(TAG, "WARNING: no peaks found in fundamental range 1-12 MHz")
            return 0

        idx_mag_max = np.argmax(mag_arr_sub[idx_mag_max_arr])
        f_mag_max = freq_arr_sub[idx_mag_max_arr][idx_mag_max]
        print(TAG, "Fundamental frequency detected: {:.0f} Hz".format(f_mag_max))
        return f_mag_max

    def auto_detect_qcm_type(self, freq_fundamental):
        """
        Map the detected fundamental frequency to the corresponding sensor
        type and the file paths used for output.

        :return: (qcm_label, path_peaks, path_calib, filename_calib, distance)
        """
        if 2e6 < freq_fundamental < 4e6:
            return ("3 MHz QCM",
                    Constants.cvs_peakfrequencies_path,
                    Constants.csv_calibration_path3,
                    Constants.csv_calibration_filename3,
                    Constants.dist5)
        if 4e6 < freq_fundamental < 6e6:
            return ("5 MHz QCM",
                    Constants.cvs_peakfrequencies_path,
                    Constants.csv_calibration_path,
                    Constants.csv_calibration_filename,
                    Constants.dist5)
        if 9e6 < freq_fundamental < 11e6:
            return ("10 MHz QCM",
                    Constants.cvs_peakfrequencies_path,
                    Constants.csv_calibration_path10,
                    Constants.csv_calibration_filename10,
                    Constants.dist10)
        # Unrecognised — return default 5 MHz paths so the caller can warn the user
        print(TAG, "WARNING: unrecognized fundamental frequency {:.0f} Hz, "
                   "using default paths".format(freq_fundamental))
        return ("Unknown ({:.0f} Hz)".format(freq_fundamental),
                Constants.cvs_peakfrequencies_path,
                Constants.csv_calibration_path,
                Constants.csv_calibration_filename,
                Constants.dist5)

    def peak_detection_overtones(self, freq, mag, phase, freq_fundamental):
        """
        Phase 2 — locate the odd overtones (3×, 5×, 7×, 9× fundamental).

        Each overtone is searched in a ±400 kHz window around its expected
        position. Both magnitude and phase peaks are extracted and
        cross-validated:
            - the frequency offset between the two peaks must stay within
              `diff_threshold` (parametrised by `peak_freq_diff_divisor`);
            - the phase peak must exceed `peak_phase_threshold` degrees.
        Overtones that fail either check are discarded.

        :return: array of accepted overtone frequencies (Hz)
        """
        freq_arr = np.array(freq)
        mag_arr = np.array(mag)
        phase_arr = np.array(phase)

        overtones_n = np.array(Constants.peak_overtone_multipliers)
        overtones_f = overtones_n * freq_fundamental
        overtones_f = overtones_f[overtones_f <= Constants.peak_max_frequency_limit]

        frequency_overtones = np.zeros(len(overtones_f))
        freq_diff_arr = np.zeros(len(overtones_f))
        phase_max_arr = np.zeros(len(overtones_f))

        calib_fStep = freq_arr[1] - freq_arr[0]
        diff_threshold = (calib_fStep * Constants.peak_points_overtone) / Constants.peak_freq_diff_divisor

        for i in range(len(overtones_f)):
            n = (Constants.peak_overtone_multipliers[i]
                 if i < len(Constants.peak_overtone_multipliers) else '?')

            # Window indices around the expected overtone position
            idx_min = np.abs(freq_arr - (overtones_f[i] - Constants.peak_freq_range_half)).argmin()
            idx_max = np.abs(freq_arr - (overtones_f[i] + Constants.peak_freq_range_half)).argmin()
            freq_arr_sub = freq_arr[idx_min:idx_max]
            mag_arr_sub = mag_arr[idx_min:idx_max]
            phase_arr_sub = phase_arr[idx_min:idx_max]

            # Magnitude peak (best within the window, if any)
            idx_mag_max_arr = scipy.signal.argrelextrema(
                data=mag_arr_sub, comparator=np.greater,
                order=Constants.peak_points_overtone)
            f_mag_max = None
            if len(idx_mag_max_arr[0]) > 0:
                idx_mag_max = np.argmax(mag_arr_sub[idx_mag_max_arr])
                f_mag_max = freq_arr_sub[idx_mag_max_arr][idx_mag_max]
                frequency_overtones[i] = f_mag_max
            else:
                print(TAG, "WARNING: overtone {}x magnitude peak not found "
                           "(expected ~{:.0f} Hz)".format(n, overtones_f[i]))
                frequency_overtones[i] = 0

            # Phase peak (best within the window, if any)
            idx_phase_max_arr = scipy.signal.argrelextrema(
                data=phase_arr_sub, comparator=np.greater,
                order=Constants.peak_points_overtone)[0]
            f_phase_max = None
            if len(idx_phase_max_arr) > 0:
                idx_phase_max = np.argmax(phase_arr_sub[idx_phase_max_arr])
                f_phase_max = freq_arr_sub[idx_phase_max_arr][idx_phase_max]
                idx_phase_max_global = idx_phase_max_arr[idx_phase_max]
                phase_max_arr[i] = phase_arr_sub[idx_phase_max_global]

            # Cross-validation distance (only meaningful if both peaks exist)
            if f_mag_max is not None and f_phase_max is not None:
                freq_diff_arr[i] = np.abs(f_mag_max - f_phase_max)

            if f_mag_max is not None:
                print(TAG, "Overtone {}x detected: {:.0f} Hz "
                           "(phase max: {:.1f} deg, freq diff: {:.0f} Hz)".format(
                    n, f_mag_max, phase_max_arr[i], freq_diff_arr[i]))

        # Filtering pass — drop overtones that fail either check
        indices_to_discard = []
        for i in range(len(overtones_f)):
            n = (Constants.peak_overtone_multipliers[i]
                 if i < len(Constants.peak_overtone_multipliers) else '?')
            if freq_diff_arr[i] > diff_threshold:
                print(TAG, "DISCARD overtone {}x: freq difference {:.0f} Hz "
                           "exceeds threshold {:.0f} Hz".format(
                    n, freq_diff_arr[i], diff_threshold))
                indices_to_discard.append(i)
            if phase_max_arr[i] <= Constants.peak_phase_threshold:
                print(TAG, "DISCARD overtone {}x: phase max {:.1f} deg below "
                           "threshold {} deg".format(
                    n, phase_max_arr[i], Constants.peak_phase_threshold))
                if i not in indices_to_discard:
                    indices_to_discard.append(i)

        frequency_overtones_filtered = np.delete(frequency_overtones, indices_to_discard)
        if indices_to_discard:
            print(TAG, "Overtones after filtering: {} of {} retained".format(
                len(frequency_overtones_filtered), len(overtones_f)))
        return frequency_overtones_filtered

    # ------------------------------------------------------------------
    # Legacy peak detection (fallback)
    # ------------------------------------------------------------------
    def FindPeak(self, freq, mag, phase, dist):
        """
        Legacy peak detection: find local maxima on the full spectrum
        with a minimum spacing of `dist` samples. Used as a fallback when
        the two-phase algorithm fails.

        :return: (max_freq_mag, max_value_mag, max_freq_phase, max_value_phase)
        """
        self.max_indexes_mag = scipy.signal.argrelextrema(
            np.array(mag), comparator=np.greater, order=dist)
        self.max_indexes_phase = scipy.signal.argrelextrema(
            np.array(phase), comparator=np.greater, order=dist)

        self.max_freq_mag = freq[self.max_indexes_mag]
        self.max_value_mag = mag[self.max_indexes_mag]
        self.max_freq_phase = freq[self.max_indexes_phase]
        self.max_value_phase = phase[self.max_indexes_phase]
        return (self.max_freq_mag, self.max_value_mag,
                self.max_freq_phase, self.max_value_phase)

    # ------------------------------------------------------------------
    # Serial port lifecycle
    # ------------------------------------------------------------------
    def open(self, port,
             speed=Constants.serial_default_QCS,
             timeout=Constants.serial_timeout_ms,
             writeTimeout=Constants.serial_writetimeout_ms):
        """
        Configure the serial port and remember the user's QCM-type choice.

        `speed` here is the sensor type label coming from the GUI:
            - 'Auto'        — auto-detect from the fundamental (default)
            - '5 MHz QCM'   — legacy manual selection
            - '10 MHz QCM'  — legacy manual selection
        """
        self._serial.port = port
        self._serial.baudrate = Constants.serial_default_speed
        self._serial.stopbits = serial.STOPBITS_ONE
        self._serial.bytesize = serial.EIGHTBITS
        self._serial.timeout = timeout
        self._serial.writetimeout = writeTimeout
        self._QCStype = speed

        if self._QCStype == 'Auto':
            self._QCStype_int = -1
            print(TAG, "QCM Sensor type: Auto-detect (will be determined during peak detection)")
        elif self._QCStype == '5 MHz QCM':
            self._QCStype_int = 0
            print(TAG, "Selected Quartz Crystal Sensor:", self._QCStype)
        elif self._QCStype == '10 MHz QCM':
            self._QCStype_int = 1
            print(TAG, "Selected Quartz Crystal Sensor:", self._QCStype)
        else:
            self._QCStype_int = -1
            print(TAG, "QCM Sensor type: Auto-detect (will be determined during peak detection)")
        return self._is_port_available(self._serial.port)

    # ------------------------------------------------------------------
    # Calibration loop
    # ------------------------------------------------------------------
    def run(self):
        """
        Acquire 10 concatenated sweep sections covering 1–51 MHz, then run
        baseline correction and peak detection. Exit early (with a `-1`
        cancellation sentinel on parser5) if the user aborts.
        """
        # Reset state
        self._polyfitted_all = None
        self._coeffs_all = None
        self._polyfitted_all_phase = None
        self._coeffs_all_phase = None
        self._mag_beseline_corrected_all = None
        self._phase_beseline_corrected_all = None
        self._flag = 0
        self._flag2 = 0

        if not self._is_port_available(self._serial.port):
            return

        readFREQ = Constants.calibration_readFREQ
        if self._serial.isOpen():
            return  # Port already open — nothing to do

        self._serial.open()
        self._serial.timeout = 0.1   # Short read timeout for responsive cancellation

        # Drain any data left over from an interrupted previous calibration
        drain_deadline = time.time() + 5.0
        while time.time() < drain_deadline:
            stale = self._serial.read(self._serial.inWaiting())
            if not stale:
                time.sleep(0.1)
                stale = self._serial.read(self._serial.inWaiting())
                if not stale:
                    break
        self._serial.flushInput()
        self._serial.flushOutput()

        k = 0
        print(TAG, 'Peak Detection Process Started')
        print(TAG, 'The operation might take just over a minute to complete... please wait...')

        # Buffers that accumulate the concatenated sweep
        temp1 = []
        temp2 = []

        # ADC scaling constants (firmware-defined)
        VMAX = 3.3
        BITMAX = 8192
        ADC_TO_VOLT = VMAX / BITMAX
        VCP = 0.9

        # Acquisition loop — one section per iteration
        while not self._exit.is_set():
            self._flag = 0
            self._flag2 = 0
            fStep = Constants.calib_fStep
            startFreq = Constants.calibration_frequency_start + k * Constants.calib_fRange
            stopFreq = startFreq + Constants.calib_fRange
            samples = Constants.calib_samples
            data_mag = np.linspace(0, 0, samples)
            data_ph = np.linspace(0, 0, samples)

            try:
                cmd = "{};{};{}\n".format(startFreq, stopFreq, int(fStep))
                self._serial.write(cmd.encode())

                buffer = ''
                strs = ["" for _ in range(samples + 2)]

                # Read until the trailer 's' marker, with cancellation polling
                while not self._exit.is_set():
                    buffer += self._serial.read(self._serial.inWaiting()).decode()
                    if 's' in buffer:
                        break
                if self._exit.is_set() and 's' not in buffer:
                    print(TAG, "Peak Detection interrupted by user")
                    break

                data_raw = buffer.split('\n')
                length = len(data_raw)
                for i in range(length):
                    strs[i] = data_raw[i].split(';')
                for i in range(length - 2):
                    data_mag[i] = (float(strs[i][0]) * ADC_TO_VOLT / 2 - VCP) / 0.03
                    data_ph[i]  = (float(strs[i][1]) * ADC_TO_VOLT / 1.5 - VCP) / 0.01

                # Sections k > 0 overlap the first sample with the previous section
                if k > 0:
                    data_mag = data_mag[1:]
                    data_ph = data_ph[1:]
                temp1 = np.append(temp1, data_mag)
                temp2 = np.append(temp2, data_ph)
                print(TAG, "signal section #{}/{} acquired successfully\n".format(
                    k + 1, Constants.calib_sections), end='\r')

            except ValueError:
                print(TAG, "WARNING: ValueError during signal acquisition")
                print(TAG, "Please, repeat Peak Detection")
                self._flag = 1
                self._serial.flushInput()
                self._serial.flushOutput()
                self._serial.close()
                self.stop()
            except Exception:
                print(TAG, "WARNING: generic error during signal acquisition")
                print(TAG, "Please, repeat Peak Detection")
                self._flag = 1
                self._serial.flushInput()
                self._serial.flushOutput()
                self._serial.close()
                self.stop()

            # Forward the concatenated raw sweep to the GUI for live preview
            self._parser1.add1(temp1)
            self._parser2.add2(temp2)
            self._parser6.add6([self._flag, self._flag2, self._flag2, k])

            k += 1
            if k == Constants.calib_sections:
                self.stop()
                break

        # Handle user cancellation: signal it on parser5 and exit
        if self._exit.is_set() and k < Constants.calib_sections:
            print(TAG, "Peak Detection interrupted by user at section {}/{}".format(
                k, Constants.calib_sections))
            self._parser5.add5([-1, 0])
            if self._serial.isOpen():
                self._serial.flushInput()
                self._serial.flushOutput()
                time.sleep(0.2)
                self._serial.flushInput()
                self._serial.close()
            return

        # Baseline correction + peak detection on the full concatenated sweep
        if self._flag == 0:
            print(TAG, "Baseline Correction Process Started")
            (data_mag_baseline, data_ph_baseline) = self.baseline_correction(
                readFREQ, temp1, temp2)
            self._parser1.add1(data_mag_baseline)
            self._parser2.add2(data_ph_baseline)
            print(TAG, "Baseline Correction Process Completed")
            print(TAG, "Peak Detection Process Started")
            print(TAG, "Finding peaks in acquired signals...")

            try:
                # Phase 1: fundamental
                freq_fundamental = self.peak_detection_fundamental(
                    readFREQ, data_mag_baseline, data_ph_baseline)
                if freq_fundamental == 0:
                    raise ValueError("Fundamental frequency not found in 1-12 MHz range")

                (qcm_label, path, path_calib,
                 filename_calib, distance) = self.auto_detect_qcm_type(freq_fundamental)
                print(TAG, "Auto-detected QCM type: {}".format(qcm_label))

                # Phase 2: overtones
                freq_overtones = self.peak_detection_overtones(
                    readFREQ, data_mag_baseline, data_ph_baseline, freq_fundamental)

                # Assemble [fundamental, overtone3, overtone5, ...]
                max_freq_mag = np.zeros(len(freq_overtones) + 1)
                max_freq_mag[0] = freq_fundamental
                max_freq_mag[1:] = freq_overtones
                print(TAG, "Peak detection results: {} Hz".format(max_freq_mag))

                # If every position is zero, the calibration failed
                missing = np.where(max_freq_mag == 0)[0]
                if len(missing) > 0:
                    print(TAG, "WARNING: {} overtone(s) not found at positions: {}".format(
                        len(missing), missing))
                    if len(missing) == len(max_freq_mag):
                        self._flag2 = 1

                # The fundamental must lie in a known QCM range; otherwise the
                # detection is treated as failed (e.g. a spurious noise peak).
                is_valid_qcm = (4e6 < freq_fundamental < 6e6) or (9e6 < freq_fundamental < 11e6)
                if freq_fundamental > 0 and is_valid_qcm:
                    print(TAG, "Saving data in file...")
                    np.savetxt(path, np.column_stack([max_freq_mag, max_freq_mag]))
                    print(TAG, "Peak frequencies for {} saved in: {}".format(qcm_label, path))
                    FileStorage.TXT_sweeps_save(filename_calib,
                                                Constants.csv_calibration_export_path,
                                                readFREQ, temp1, temp2)
                    print(TAG, "Peak Detection for {} saved in: {}".format(qcm_label, path_calib))
                else:
                    print(TAG, "WARNING: unable to identify valid fundamental peak")
                    if freq_fundamental > 0:
                        print(TAG, "Detected frequency {} Hz is not a valid QCM resonance"
                              .format(freq_fundamental))
                    print(TAG, "Please, repeat Peak Detection!")
                    self._flag2 = 1

            except Exception as e:
                # Fallback: legacy `FindPeak` on the full spectrum
                print(TAG, "New algorithm failed ({}), falling back to legacy FindPeak".format(e))
                try:
                    if hasattr(self, '_QCStype_int') and self._QCStype_int == 1:
                        distance = Constants.dist10
                        path = Constants.cvs_peakfrequencies_path
                        path_calib = Constants.csv_calibration_path10
                        filename_calib = Constants.csv_calibration_filename10
                    else:
                        distance = Constants.dist5
                        path = Constants.cvs_peakfrequencies_path
                        path_calib = Constants.csv_calibration_path
                        filename_calib = Constants.csv_calibration_filename

                    (max_freq_mag, max_value_mag,
                     max_freq_phase, max_value_phase) = self.FindPeak(
                        readFREQ, temp1, temp2, dist=distance)
                    print(TAG, "Legacy FindPeak: {} peaks at frequencies: {} Hz"
                          .format(len(max_freq_mag), max_freq_mag))

                    is_valid = (len(max_freq_mag) > 0 and
                                ((4e6 < max_freq_mag[0] < 6e6) or
                                 (9e6 < max_freq_mag[0] < 11e6)))
                    if is_valid:
                        print(TAG, "Saving data in file...")
                        np.savetxt(path, np.column_stack([max_freq_mag, max_freq_mag]))
                        print(TAG, "Peak frequencies saved in: {}".format(path))
                        FileStorage.TXT_sweeps_save(filename_calib,
                                                    Constants.csv_calibration_export_path,
                                                    readFREQ, temp1, temp2)
                        print(TAG, "Peak Detection saved in: {}".format(path_calib))
                    else:
                        print(TAG, "WARNING: unable to identify fundamental peak (legacy)")
                        print(TAG, "Please, repeat Peak Detection!")
                        self._flag2 = 1
                except Exception:
                    print(TAG, "WARNING: unable to apply peak detection algorithm")
                    print(TAG, "Please, repeat Peak Detection!")
                    self._flag2 = 1

        if self._flag == 0 and self._flag2 == 0:
            print(TAG, 'Peak Detection success for baseline correction!')

        # Final status: report flags to the GUI
        self._parser5.add5([self._flag, self._flag2])
        self._serial.close()

    # ------------------------------------------------------------------
    # Static helpers — port and overtone enumeration
    # ------------------------------------------------------------------
    @staticmethod
    def get_ports():
        """Return the serial ports that look like an openQCM Q-1 device."""
        from openQCM.common.architecture import Architecture, OSType
        if Architecture.get_os() is OSType.macosx:
            import glob
            return glob.glob("/dev/tty.usbmodem*")
        if Architecture.get_os() is OSType.linux:
            import glob
            return glob.glob("/dev/ttyACM*")
        ports_available = list(list_ports.comports())
        return [p[0] for p in ports_available
                if p[2].startswith("USB VID:PID=16C0:0483")]

    @staticmethod
    def get_speeds():
        """Return the QCM-type labels offered to the user."""
        return [str(v) for v in ['10 MHz QCM', '5 MHz QCM']]

    def _is_port_available(self, port):
        """True if `port` is among the discovered openQCM ports."""
        return port in self.get_ports()
