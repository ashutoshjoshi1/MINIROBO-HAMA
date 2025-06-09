import os
import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal, QDateTime
import ctypes
import sys
import traceback

# Ensure the directory of this file is on the Python path, so it can find sibling modules.
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.append(script_dir)
os.environ['PATH'] = script_dir + os.pathsep + os.environ.get('PATH', '')

# Import Avantes spectrometer SDK (AvaSpec)
try:
    from avaspec import *
except ImportError as e:
    raise ImportError(
        "AvaSpec SDK import failed. Make sure avaspec.pyd and the Avaspec DLL are in the same directory."
    ) from e

# Import Hamamatsu spectrometer support if available
try:
    from hama3_spectrometer import Hama3_Spectrometer
except ImportError as e:
    # --- KEY CHANGE: Added detailed error logging ---
    # This will print the exact reason the import is failing, which is crucial for debugging.
    print("CRITICAL: Failed to import 'hama3_spectrometer'. Hamamatsu support is disabled.")
    print(f"--> Detailed Error: {e}")
    print(f"--> This script's directory, which was added to the path: {script_dir}")
    Hama3_Spectrometer = None

class StopMeasureThread(QThread):
    """Thread to stop an ongoing Avantes measurement (calls AVS_StopMeasure)."""
    finished_signal = pyqtSignal()

    def __init__(self, spec_handle, parent=None):
        super().__init__(parent)
        self.spec_handle = spec_handle

    def run(self):
        AVS_StopMeasure(self.spec_handle)
        self.finished_signal.emit()

def connect_spectrometer():
    """
    Attempt to connect to a spectrometer.
    Tries Hamamatsu first, then Avantes if Hamamatsu is not found or fails.
    Returns a tuple: (handle, wavelengths, num_pixels, serial_str).
    """
    # Try Hamamatsu spectrometer first
    if Hama3_Spectrometer is not None:
        try:
            print("Trying to connect to Hamamatsu spectrometer...")
            hama = Hama3_Spectrometer()

            # --- KEY CHANGE: Construct an absolute path to the DLL ---
            # This makes the path independent of the script's working directory.
            # It assumes a project structure like: /project_root/drivers/spectrometer.py
            # and /project_root/spec_hama3/...
            project_root = os.path.dirname(script_dir)
            dll_path = os.path.join(project_root, "spec_hama3", "DcIcUSB_v1.1.0.7", "x64", "DcIcUSB.dll")
            
            print(f"INFO: Attempting to load Hamamatsu DLL from: {dll_path}")

            if not os.path.exists(dll_path):
                print(f"ERROR: Hamamatsu DLL not found at the expected path. Please check the file location.")
                raise FileNotFoundError(f"DLL not found: {dll_path}")

            hama.dll_path = dll_path
            hama.sn = "46AN0776"
            
            hama.debug_mode = 1
            hama.npix_active = 4096

            hama.initialize_spec_logger()
            res = hama.connect()

            if res == "OK":
                print("Hamamatsu spectrometer connected successfully.")
                set_res = hama.set_it(5.0)
                if set_res != "OK":
                    print(f"Warning: Hamamatsu spectrometer set_it failed: {set_res}")

                spec = hama
                serial_str = getattr(spec, 'sn', 'N/A')

                if isinstance(serial_str, bytes):
                    serial_str = serial_str.decode('utf-8', 'ignore')
                
                wavelengths = np.arange(spec.npix_active)
                num_pixels = spec.npix_active
                
                spec.spec_type = 'hama'

                return spec, wavelengths, num_pixels, serial_str
            else:
                print(f"Hamamatsu connection failed. Device message: '{res}'. Falling back to Avantes.")
        except Exception as e:
            print(f"An unexpected error occurred while connecting to Hamamatsu: {e}")
            traceback.print_exc()
            print("Falling back to Avantes spectrometer.")
    else:
        print("Hamamatsu support not available. Trying Avantes only.")

    # --- Fallback to Avantes Spectrometer ---
    print("Trying to connect to Avantes...")
    try:
        ret = AVS_Init(0)
    except Exception as e:
        raise Exception(f"Spectrometer initialization failed: {e}")

    if ret <= 0:
        AVS_Done()
        if ret == 0:
            raise Exception("No Avantes spectrometer found.")
        if 'ERR_ETHCONN_REUSE' in globals() and ret == ERR_ETHCONN_REUSE:
            raise Exception("Avantes spectrometer is already in use by another program.")
        else:
            raise Exception(f"AVS_Init error (code {ret}). No spectrometer connected.")

    dev_count = AVS_UpdateUSBDevices()
    if dev_count < 1:
        AVS_Done()
        raise Exception("No spectrometer found after USB device update.")

    id_list = AVS_GetList(dev_count)
    if not id_list:
        AVS_Done()
        raise Exception("Failed to retrieve spectrometer list.")

    dev_id = id_list[0]
    serial_str = dev_id.SerialNumber.decode('utf-8').strip()
    
    avs_id = AvsIdentityType()
    avs_id.SerialNumber = dev_id.SerialNumber
    avs_id.UserFriendlyName = b"\x00"
    avs_id.Status = b'\x01'

    spec_handle = AVS_Activate(avs_id)
    if spec_handle == INVALID_AVS_HANDLE_VALUE:
        AVS_Done()
        raise Exception(f"Error opening Avantes spectrometer (Serial: {serial_str})")
        
    device_data_p = ctypes.c_void_p()
    ret = AVS_GetParameter(spec_handle, 63484, ctypes.byref(ctypes.c_ushort()), ctypes.byref(device_data_p))
    if ret != 0 or not device_data_p:
        AVS_Done()
        raise Exception("Failed to get Avantes spectrometer parameters.")
    
    device_data = ctypes.cast(device_data_p, ctypes.POINTER(DeviceData)).contents
    num_pixels = device_data.m_Detector_m_NrPixels

    wavelengths_p = ctypes.c_double()
    ret = AVS_GetLambda(spec_handle, ctypes.byref(wavelengths_p))
    if ret == 0:
        wavelengths = np.ctypeslib.as_array(wavelengths_p, shape=(num_pixels,))
    else:
        print("Warning: Could not get wavelength calibration from Avantes spec. Using pixel indices.")
        wavelengths = np.arange(num_pixels)
        
    return spec_handle, wavelengths, num_pixels, serial_str


def prepare_measurement(spec_handle, num_pixels, integration_time_ms=50.0, averages=1, cycles=1, repetitions=1):
    """Prepare the measurement configuration for an Avantes spectrometer."""
    meas_cfg = MeasConfigType()
    meas_cfg.m_StartPixel = 0
    meas_cfg.m_StopPixel = num_pixels - 1
    meas_cfg.m_IntegrationTime = float(integration_time_ms)
    meas_cfg.m_IntegrationDelay = 0
    meas_cfg.m_NrAverages = int(averages)
    meas_cfg.m_CorDynDark_m_Enable = 0
    meas_cfg.m_CorDynDark_m_ForgetPercentage = 100
    meas_cfg.m_Smoothing_m_SmoothPix = 0
    meas_cfg.m_Smoothing_m_SmoothModel = 0
    meas_cfg.m_SaturationDetection = 0
    meas_cfg.m_Trigger_m_Mode = 0
    meas_cfg.m_Trigger_m_Source = 0
    meas_cfg.m_Trigger_m_SourceType = 0
    meas_cfg.m_Control_m_StrobeControl = 0
    meas_cfg.m_Control_m_LaserDelay = 0
    meas_cfg.m_Control_m_LaserWidth = 0
    meas_cfg.m_Control_m_LaserWaveLength = 0.0
    meas_cfg.m_Control_m_StoreToRam = 0
    return AVS_PrepareMeasure(spec_handle, meas_cfg)

def start_measurement(spec_handle, callback_func, num_scans=-1):
    """Start an Avantes measurement with a callback (non-blocking)."""
    global avantes_callback
    avantes_callback = AVS_MeasureCallbackFunc(callback_func)
    return AVS_MeasureCallback(spec_handle, avantes_callback, num_scans)

def stop_measurement(spec_handle):
    """Stop an ongoing Avantes measurement."""
    AVS_StopMeasure(spec_handle)

def close_spectrometer():
    """Close the spectrometer interface (Avantes)."""
    AVS_Done()
