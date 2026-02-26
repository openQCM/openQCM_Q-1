from openQCM.core.constants import Constants

TAG = "[Switcher]"

###############################################################################
# Switches from overtone frequency to frequency range for 10MHz QC Sensor
# Returns other parameters that are used for processing
###############################################################################
class Overtone_Switcher_10MHz:
    
    def __init__(self,peak_frequencies = None):
        self.peak_frequencies = peak_frequencies
    
    # from fundamental frequency to the 5th overtone  
    def overtone10MHz_to_freq_range(self, argument):
        method_name = 'overtone_' + str(argument)
        # Get the method from 'self'. Default to a lambda.
        method = getattr(self, method_name, lambda: None)
        # Call the method as we return it
        return method()
 
    def overtone_0(self):
        # fundamental frequency
        name = "fundamental"
        start = self.peak_frequencies[0] - Constants.L10_fundamental
        stop  = self.peak_frequencies[0] + Constants.R10_fundamental
        return name ,self.peak_frequencies[0], start, stop, Constants.SG_window_size10_fundamental, Constants.Spline_factor10_fundamental
 
    def overtone_1(self):
        # 3th Overtone
        name = "3th Overtone"
        start = self.peak_frequencies[1] - Constants.L10_3th_overtone
        stop  = self.peak_frequencies[1] + Constants.R10_3th_overtone
        return name, self.peak_frequencies[1], start, stop, Constants.SG_window_size10_3th_overtone, Constants.Spline_factor10_3th_overtone
    
    def overtone_2(self):
        # 5th Overtone
        name = "5th Overtone"
        start = self.peak_frequencies[2] - Constants.L10_5th_overtone
        stop  = self.peak_frequencies[2] + Constants.R10_5th_overtone
        return name, self.peak_frequencies[2], start, stop, Constants.SG_window_size10_5th_overtone, Constants.Spline_factor10_5th_overtone


###############################################################################
# Switches from overtone frequency to frequency range for 5MHz QC Sensor
###############################################################################
class Overtone_Switcher_5MHz:
    
    def __init__(self,peak_frequencies = None):
        self.peak_frequencies = peak_frequencies
    
    # from fundamental frequency to the 9th overtone    
    def overtone5MHz_to_freq_range(self, argument):
        method_name = 'overtone_' + str(argument)
        # Get the method from 'self'. Default to a lambda.
        method = getattr(self, method_name, lambda: None)
        # Call the method as we return it
        return method()
 
    def overtone_0(self):
        # fundamental frequency
        name = "fundamental"
        start = self.peak_frequencies[0] - Constants.L5_fundamental
        stop  = self.peak_frequencies[0] + Constants.R5_fundamental
        return name, self.peak_frequencies[0], start, stop, Constants.SG_window_size5_fundamental, Constants.Spline_factor5_fundamental
 
    def overtone_1(self):
        # 3th Overtone
        name = "3th Overtone"
        start = self.peak_frequencies[1] - Constants.L5_3th_overtone
        stop  = self.peak_frequencies[1] + Constants.R5_3th_overtone
        return name, self.peak_frequencies[1], start, stop, Constants.SG_window_size5_3th_overtone, Constants.Spline_factor5_3th_overtone
    
    def overtone_2(self):
        # 5th Overtone
        name = "5th Overtone"
        start = self.peak_frequencies[2] - Constants.L5_5th_overtone
        stop  = self.peak_frequencies[2] + Constants.R5_5th_overtone
        return name, self.peak_frequencies[2],start,stop, Constants.SG_window_size5_5th_overtone, Constants.Spline_factor5_5th_overtone

    def overtone_3(self):
        # 7th Overtone
        name = "7th Overtone"
        start = self.peak_frequencies[3] - Constants.L5_7th_overtone
        stop  = self.peak_frequencies[3] + Constants.R5_7th_overtone
        return name, self.peak_frequencies[3],start,stop, Constants.SG_window_size5_7th_overtone, Constants.Spline_factor5_7th_overtone

    def overtone_4(self):
        # 9th Overtone
        name = "9th Overtone"
        start = self.peak_frequencies[4] - Constants.L5_9th_overtone
        stop  = self.peak_frequencies[4] + Constants.R5_9th_overtone
        return name, self.peak_frequencies[4], start, stop, Constants.SG_window_size5_9th_overtone, Constants.Spline_factor5_9th_overtone
