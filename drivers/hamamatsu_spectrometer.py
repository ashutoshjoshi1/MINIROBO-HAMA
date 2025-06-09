import ctypes
import numpy as np
import os
from drivers.spectrometer import Spectrometer
from utils import get_project_root

class HamaSpectrometer(Spectrometer):
    """
    Driver for Hamamatsu C12880-01 spectrometer.
    """
    def __init__(self, config, *args, **kwargs):
        super().__init__(config, *args, **kwargs)
        
        # Determine library path
        root = get_project_root()
        lib_path = os.path.join(root, "spec_hama3", "Hama.so")
        if not os.path.exists(lib_path):
             raise FileNotFoundError(f"Hamamatsu library not found at {lib_path}")

        # Load the shared library
        self.hama = ctypes.cdll.LoadLibrary(lib_path)
        
        # Define function prototypes
        self.hama.hama_init.restype = ctypes.c_int
        self.hama.hama_get_spectrum.argtypes = [ctypes.POINTER(ctypes.c_double)]
        self.hama.hama_get_spectrum.restype = ctypes.c_int
        self.hama.hama_set_integration_time.argtypes = [ctypes.c_int]
        self.hama.hama_set_integration_time.restype = ctypes.c_int
        self.hama.hama_get_wavelengths.argtypes = [ctypes.POINTER(ctypes.c_double)]
        self.hama.hama_get_wavelengths.restype = ctypes.c_int
        self.hama.hama_close.restype = ctypes.c_int
        
        self.spectrum_buffer = (ctypes.c_double * 288)()
        self.wavelength_buffer = (ctypes.c_double * 288)()

    def connect(self):
        if self.hama.hama_init() == 0:
            self.is_connected = True
            print("Hamamatsu Spectrometer Connected")
            self.set_integration_time(self.config.get("integration_time", 100))
            self.get_wavelengths() # Pre-load wavelengths
            return True
        else:
            self.is_connected = False
            print("Failed to connect to Hamamatsu Spectrometer")
            return False

    def disconnect(self):
        self.hama.hama_close()
        self.is_connected = False
        print("Hamamatsu Spectrometer Disconnected")

    def get_spectrum(self):
        if not self.is_connected:
            return None, None
        
        result = self.hama.hama_get_spectrum(self.spectrum_buffer)
        if result == 0:
            spectrum = np.array(self.spectrum_buffer)
            wavelengths = np.array(self.wavelength_buffer)
            return spectrum, wavelengths
        return None, None

    def set_integration_time(self, time_ms):
        if not self.is_connected:
            return
        self.hama.hama_set_integration_time(int(time_ms))

    def get_wavelengths(self):
        if not self.is_connected:
            return []
        result = self.hama.hama_get_wavelengths(self.wavelength_buffer)
        if result == 0:
            return np.array(self.wavelength_buffer)
        return []

