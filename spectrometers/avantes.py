import ctypes
import sys
from .base import BaseSpectrometer

# --- Paste the Avantes Spec operation functions you provided here ---
# (AVS_SERIAL_LEN, AvsIdentityType, AVS_Init, etc.)

class AvantesSpectrometer(BaseSpectrometer):
    def __init__(self, dll_path):
        self.dll_path = dll_path
        self.lib = None
        self.handle = None
        self.num_pixels = 0
        self.wavelengths = []

    def connect(self):
        try:
            if 'linux' in sys.platform:
                self.lib = ctypes.CDLL(self.dll_path)
            else:
                self.lib = ctypes.WinDLL(self.dll_path)

            AVS_Init(0)
            num_devices = AVS_GetNrOfDevices()
            if num_devices > 0:
                # For simplicity, we activate the first device found.
                # You can extend this to select a specific device by serial number.
                dev_list = AVS_GetList(1)
                self.handle = AVS_Activate(dev_list[0])
                self.num_pixels = AVS_GetNumPixels(self.handle)
                self.wavelengths = AVS_GetLambda(self.handle)
                return "OK"
            else:
                return "No Avantes spectrometer found."
        except Exception as e:
            return str(e)

    def disconnect(self):
        if self.handle:
            AVS_Deactivate(self.handle)
        AVS_Done()
        return "OK"

    def set_integration_time(self, time_ms):
        if not self.handle:
            return "Spectrometer not connected."
        meas_config = MeasConfigType()
        meas_config.m_IntegrationTime = float(time_ms)
        # Set other measurement parameters as needed
        AVS_PrepareMeasure(self.handle, meas_config)
        return "OK"

    def measure(self, ncy=1):
        if not self.handle:
            return None
        # This is a simplified measurement. You may need to handle callbacks
        # or polling for more complex applications.
        ret = AVS_Measure(self.handle, 0, ncy)
        if ret == 0:
            # Wait for data to be ready (this is a blocking call)
            while not AVS_PollScan(self.handle):
                pass
            timestamp, spectrum = AVS_GetScopeData(self.handle)
            return spectrum
        return None

    def get_wavelengths(self):
        return self.wavelengths