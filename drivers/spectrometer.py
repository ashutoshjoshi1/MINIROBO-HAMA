import os
import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal, QDateTime
import ctypes
import sys
import traceback

# Ensure DLL loading from the same directory as this file
dll_dir = os.path.dirname(os.path.abspath(__file__))
if dll_dir not in sys.path:
    sys.path.append(dll_dir)
os.environ['PATH'] = dll_dir + os.pathsep + os.environ.get('PATH', '')

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
except ImportError:
    print("Warning: 'hama3_spectrometer' library not found. Hamamatsu spectrometer support is disabled.")
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

            # --- KEY CHANGE ---
            # Do not specify a serial number (hama.sn) or DLL path.
            # This allows the driver to find the first available Hamamatsu device
            # and its necessary files automatically.
            
            # These settings might be device-specific.
            hama.debug_mode = 1
            hama.npix_active = 4096

            hama.initialize_spec_logger()
            res = hama.connect()

            if res == "OK":
                print("Hamamatsu spectrometer connected successfully.")
                # Set a default integration time (5 ms for fast update)
                set_res = hama.set_it(5.0)
                if set_res != "OK":
                    print(f"Warning: Hamamatsu spectrometer set_it failed: {set_res}")

                spec = hama
                # Get the serial number from the connected device
                serial_str = getattr(spec, 'sn', 'N/A')

                # Clean up serial string for display
                if isinstance(serial_str, bytes):
                    serial_str = serial_str.decode('utf-8', 'ignore')
                if isinstance(serial_str, str) and serial_str.startswith("b'"):
                    serial_str = serial_str[2:-1]
                
                # Use numpy arange for pixel indices as wavelength calibration is not available
                wavelengths = np.arange(spec.npix_active)
                num_pixels = spec.npix_active
                
                # Add a spec_type attribute for easier identification
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
        # Check for a specific error if the constant is defined in avaspec
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

    # Activate the first available spectrometer
    dev_id = id_list[0]
    serial_str = dev_id.SerialNumber.decode('utf-8').strip()
    
    avs_id = AvsIdentityType()
    avs_id.SerialNumber = dev_id.SerialNumber
    avs_id.UserFriendlyName = b"\x00"
    avs_id.Status = b'\x01' # Status 1 means activate this device

    spec_handle = AVS_Activate(avs_id)
    if spec_handle == INVALID_AVS_HANDLE_VALUE:
        AVS_Done()
        raise Exception(f"Error opening Avantes spectrometer (Serial: {serial_str})")
        
    # Get device parameters to find the number of pixels
    device_data_p = ctypes.c_void_p() # Pointer to receive the data struct
    ret = AVS_GetParameter(spec_handle, 63484, ctypes.byref(ctypes.c_ushort()), ctypes.byref(device_data_p))
    if ret != 0 or not device_data_p:
        AVS_Done()
        raise Exception("Failed to get Avantes spectrometer parameters.")
    
    # Cast the void pointer to the actual DeviceData struct
    device_data = ctypes.cast(device_data_p, ctypes.POINTER(DeviceData)).contents
    num_pixels = device_data.m_Detector_m_NrPixels

    # Get wavelength calibration data
    wavelengths_p = ctypes.c_double()
    ret = AVS_GetLambda(spec_handle, ctypes.byref(wavelengths_p))
    if ret == 0:
        # Convert C array to numpy array
        wavelengths = np.ctypeslib.as_array(wavelengths_p, shape=(num_pixels,))
    else:
        # Fallback to pixel indices if calibration is not available
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
    meas_cfg.m_CorDynDark_m_Enable = 0  # 1 = Correct for dynamic dark
    meas_cfg.m_CorDynDark_m_ForgetPercentage = 100 # 100 = new dark every time
    meas_cfg.m_Smoothing_m_SmoothPix = 0
    meas_cfg.m_Smoothing_m_SmoothModel = 0
    meas_cfg.m_SaturationDetection = 0
    meas_cfg.m_Trigger_m_Mode = 0  # 0 = software trigger
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
    # The callback function must be stored in a variable to prevent it from being garbage collected
    global avantes_callback
    avantes_callback = AVS_MeasureCallbackFunc(callback_func)
    return AVS_MeasureCallback(spec_handle, avantes_callback, num_scans)

def stop_measurement(spec_handle):
    """Stop an ongoing Avantes measurement."""
    AVS_StopMeasure(spec_handle)

def close_spectrometer():
    """Close the spectrometer interface (Avantes)."""
    AVS_Done()

# The SpectrometerDriver class below seems to be unused by the controller.
# It's kept here for potential future use but is not part of the active code path.
class SpectrometerDriver:
    """
    High-level driver to manage multiple spectrometers (if needed in future).
    Currently manages connecting, disconnecting, and resetting one or more spectrometers.
    """
    def __init__(self):
        self.handles = {}        # Store spectrometer handles by an ID or alias
        self.data_status = {}    # Measurement status for each spectrometer
        self.recovery_level = {}
        self.recovery_history = {}
        self.measurement_stats = {}

    def reset(self, spec_id, do_test=True):
        """
        Initialize or reinitialize the spectrometer with identifier `spec_id`.
        If `do_test` is True, performs a test measurement after connecting.
        """
        # If already connected, disconnect first
        if spec_id in self.handles:
            self.disconnect(spec_id)
        # Auto-connect to an available spectrometer
        success, message = False, ""
        try:
            handle, wavelengths, num_pixels, serial_str = connect_spectrometer()
            self.handles[spec_id] = {
                'handle': handle,
                'wavelengths': wavelengths,
                'num_pixels': num_pixels,
                'serial': serial_str,
                'type': 'hama' if hasattr(handle, 'spec_type') else 'avantes'
            }
            # Initialize status and stats
            self.data_status[spec_id] = 'READY'
            self.recovery_level[spec_id] = 0
            self.recovery_history[spec_id] = []
            self.measurement_stats[spec_id] = {'durations': [], 'avg_time': 0}
            if do_test:
                self.set_it(spec_id, 50.0)
                self.measure(spec_id)
            success = True
            message = f"Spectrometer {serial_str} initialized successfully."
        except Exception as e:
            success = False
            message = f"Spectrometer reset failed: {e}"
        return success, message

    def disconnect(self, spec_id, free_interface=False):
        """
        Disconnect the spectrometer identified by `spec_id`.
        If `free_interface` is True, also free the underlying interface/driver.
        """
        if spec_id not in self.handles:
            return True
        spec_info = self.handles[spec_id]
        handle_obj = spec_info['handle']
        try:
            if spec_info['type'] == 'avantes':
                AVS_Deactivate(handle_obj)
                if free_interface:
                    AVS_Done()
            else: # Hamamatsu
                handle_obj.disconnect(dofree=free_interface)
            # Clean up stored info
            self.handles.pop(spec_id, None)
            return True
        except Exception as e:
            print(f"Error disconnecting spectrometer: {e}")
            return False
