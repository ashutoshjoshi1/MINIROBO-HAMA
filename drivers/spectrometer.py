import os
import numpy as np

# Try import Hamamatsu
try:
    from hama3_spectrometer import Hama3_Spectrometer
except ImportError:
    Hama3_Spectrometer = None

# Try import Avantes
try:
    from avantes_spectrometer import Avantes_Spectrometer
except ImportError:
    Avantes_Spectrometer = None

class Spectrometer:
    def __init__(self):
        self.device = None
        self.type = None
        self.npix = 0
        self.connected = False
        self.status = ""
        self.sn = None

    def connect(self):
        # Try Hamamatsu first
        if Hama3_Spectrometer is not None:
            try:
                hama = Hama3_Spectrometer()
                hama.dll_path = r"spec_hama3\DcIcUSB_v1.1.0.7\x64\DcIcUSB.dll"
                hama.sn = "b'46AN0776'"  # Update if needed
                hama.debug_mode = 1
                hama.npix_active = 4096
                hama.initialize_spec_logger()
                res = hama.connect()
                if res == "OK":
                    hama.set_it(5)
                    self.device = hama
                    self.type = "hamamatsu"
                    self.npix = 4096
                    self.connected = True
                    self.sn = hama.sn
                    self.status = "Connected to Hamamatsu"
                    return True
            except Exception as e:
                self.status = f"Hamamatsu error: {e}"
        
        # Try Avantes if Hamamatsu not found
        if Avantes_Spectrometer is not None:
            try:
                ava = Avantes_Spectrometer()
                ava.dll_path = r"/spec_ava1/Avaspec-DLL_9.14.0.9_64bits/avaspecx64.dll"
                ava.sn = "2203162U1"
                ava.npix_active = 2048
                ava.debug_mode = 1
                ava.initialize_spec_logger()
                res = ava.connect()
                if res == "OK":
                    ava.set_it(5)
                    self.device = ava
                    self.type = "avantes"
                    self.npix = 2048
                    self.connected = True
                    self.sn = ava.sn
                    self.status = "Connected to Avantes"
                    return True
            except Exception as e:
                self.status = f"Avantes error: {e}"
        self.status = "No spectrometer connected"
        self.connected = False
        return False

    def set_it(self, it_ms):
        if self.device:
            return self.device.set_it(it_ms)
        return "No device"

    def measure(self, ncy=1):
        if self.device:
            return self.device.measure(ncy)
        return "No device"

    def wait_for_measurement(self):
        if self.device:
            return self.device.wait_for_measurement()
        return None

    def get_counts(self):
        # returns list/array of counts of length npix
        if self.device and hasattr(self.device, 'rcm'):
            # Make sure the returned data is always exactly self.npix long
            data = self.device.rcm
            if data is not None and len(data) == self.npix:
                return list(data)
        return [0]*self.npix

    def disconnect(self):
        if self.device:
            try:
                self.device.disconnect(dofree=True)
            except Exception:
                pass
        self.device = None
        self.type = None
        self.npix = 0
        self.connected = False
