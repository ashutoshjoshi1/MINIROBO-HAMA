import os
import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal
import ctypes
import sys

# Force DLL loading from same directory as main.py
try:
    dll_dir = os.path.dirname(os.path.abspath(__file__))
    if dll_dir not in sys.path:
        sys.path.append(dll_dir)
    os.environ['PATH'] = dll_dir + os.pathsep + os.environ['PATH']
    from avaspec import *
except ImportError as e:
    raise ImportError("AvaSpec SDK import failed. Make sure avaspec.pyd and avaspec DLL are in the same directory as main.py.") from e

# Try importing Hamamatsu spectrometer support
try:
    from hama3_spectrometer import Hama3_Spectrometer
except ImportError:
    Hama3_Spectrometer = None

class StopMeasureThread(QThread):
    finished_signal = pyqtSignal()
    def __init__(self, spec_handle, parent=None):
        super().__init__(parent)
        self.spec_handle = spec_handle
    def run(self):
        AVS_StopMeasure(self.spec_handle)
        self.finished_signal.emit()

def connect_spectrometer():
    # Try Hamamatsu spectrometer first
    if Hama3_Spectrometer is not None:
        try:
            print("Trying to connect to Hamamatsu...")
            hama = Hama3_Spectrometer()
            # Configure Hamamatsu spectrometer parameters
            hama.dll_path = r"DcIcUSB.dll"  # Set DLL path for Hamamatsu SDK
            hama.sn = "b'46AN0776'"  # Update serial number if different
            hama.debug_mode = 1
            hama.alias = "1"
            hama.npix_active = 4096
            hama.initialize_spec_logger()
            res = hama.connect()
            if res == "OK":
                # Set a default integration time (e.g., 50 ms)
                set_res = hama.set_it(50.0)
                if set_res != "OK":
                    print(f"Warning: Hamamatsu spectrometer set_it failed: {set_res}")
                spec = hama
                serial_str = spec.sn
                # Clean up serial string for display (remove b' prefix if present)
                if isinstance(serial_str, str) and serial_str.startswith("b'"):
                    serial_str = serial_str[2:-1]
                wavelengths = list(range(spec.npix_active))  # Use pixel indices as wavelengths (no built-in calibration provided)
                num_pixels = spec.npix_active
                return spec, wavelengths, num_pixels, serial_str
            else:
                print(f"Hamamatsu connection failed: {res}")
        except Exception as e:
            print(f"Hamamatsu connection failed: {e}")
    # If Hamamatsu not connected, try Avantes
    try:
        print("[DEBUG] Calling AVS_Init(0)...")
        ret = AVS_Init(0)
    except Exception as e:
        raise Exception(f"Spectrometer initialization failed: {e}")
    if ret <= 0:
        AVS_Done()
        if ret == 0:
            raise Exception("No spectrometer found.")
        elif 'ERR_ETHCONN_REUSE' in globals() and ret == ERR_ETHCONN_REUSE:
            raise Exception("Spectrometer already in use by another program.")
        else:
            raise Exception(f"AVS_Init error (code {ret}).")

    dev_count = AVS_UpdateUSBDevices()
    if dev_count < 1:
        AVS_Done()
        raise Exception("No spectrometer found after update.")

    id_list = AVS_GetList(dev_count)
    if not id_list:
        AVS_Done()
        raise Exception("Failed to retrieve spectrometer list.")

    dev_id = id_list[0]
    serial_str = dev_id.SerialNumber.decode().strip() if hasattr(dev_id.SerialNumber, 'decode') else str(dev_id.SerialNumber)

    avs_id = AvsIdentityType()
    avs_id.SerialNumber = dev_id.SerialNumber
    avs_id.UserFriendlyName = b"\x00"
    avs_id.Status = b'\x01'
    spec_handle = AVS_Activate(avs_id)
    if spec_handle == INVALID_AVS_HANDLE_VALUE:
        AVS_Done()
        raise Exception(f"Error opening spectrometer (Serial: {serial_str})")

    device_data = AVS_GetParameter(spec_handle, 63484)
    if device_data is None:
        AVS_Done()
        raise Exception("Failed to get spectrometer parameters.")

    num_pixels = device_data.m_Detector_m_NrPixels
    start_pixel = getattr(device_data, 'm_StandAlone_m_Meas_m_StartPixel', 0)
    stop_pixel = getattr(device_data, 'm_StandAlone_m_Meas_m_StopPixel', num_pixels - 1)
    if start_pixel < 0:
        start_pixel = 0
    if stop_pixel <= start_pixel or stop_pixel > num_pixels - 1:
        stop_pixel = num_pixels - 1

    wavelengths = AVS_GetLambda(spec_handle)
    if wavelengths:
        wavelengths = np.ctypeslib.as_array(wavelengths)
    else:
        wavelengths = list(range(num_pixels))

    return spec_handle, wavelengths, num_pixels, serial_str

def prepare_measurement(spec_handle, num_pixels, integration_time_ms=50.0, averages=1, cycles=1, repetitions=1):
    meas_cfg = MeasConfigType()
    meas_cfg.m_StartPixel = 0
    meas_cfg.m_StopPixel = num_pixels - 1
    meas_cfg.m_IntegrationTime = float(integration_time_ms)
    meas_cfg.m_IntegrationDelay = 0
    meas_cfg.m_NrAverages = averages
    meas_cfg.m_CorDynDark_m_Enable = 0
    meas_cfg.m_CorDynDark_m_ForgetPercentage = 0
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
    meas_cfg.m_Control_m_Cycles = cycles
    meas_cfg.m_Control_m_Repetitions = repetitions
    return AVS_PrepareMeasure(spec_handle, meas_cfg)

def start_measurement(spec_handle, callback_func, num_scans=-1):
    cb_ptr = AVS_MeasureCallbackFunc(callback_func)
    return AVS_MeasureCallback(spec_handle, cb_ptr, num_scans)

def stop_measurement(spec_handle):
    AVS_StopMeasure(spec_handle)

def close_spectrometer():
    AVS_Done()

class SpectrometerDriver:
    def __init__(self):
        self.handles = {}         # Store multiple spectrometer handles
        self.data_status = {}     # Track measurement status for each spectrometer
        self.recovery_level = {}  # Track recovery level for each spectrometer
        self.recovery_history = {}
        self.measurement_stats = {}

    def reset(self, ispec, ini=True):
        """Initializes or reinitializes a spectrometer."""
        try:
            # Disconnect if already connected
            if ispec in self.handles:
                self.disconnect(ispec)
            # Connect to spectrometer (auto-select Hamamatsu or Avantes)
            handle, wavelengths, num_pixels, serial_str = connect_spectrometer()
            self.handles[ispec] = {
                'handle': handle,
                'wavelengths': wavelengths,
                'num_pixels': num_pixels,
                'serial': serial_str
            }
            # Initialize status and stats
            self.data_status[ispec] = 'READY'
            self.recovery_level[ispec] = 0
            self.recovery_history[ispec] = []
            self.measurement_stats[ispec] = {'durations': [], 'avg_time': 0}
            # Optionally take a test measurement on init
            if ini:
                self.set_it(ispec, 50.0)  # default integration time 50 ms
                self.measure(ispec)
            return True, f"Spectrometer {serial_str} initialized successfully"
        except Exception as e:
            return False, f"Reset failed: {e}"

    def disconnect(self, ispec, dofree=False):
        """Disconnects from a spectrometer and optionally frees resources."""
        if ispec in self.handles:
            try:
                stop_measurement(self.handles[ispec]['handle'])
                # (For Hamamatsu, its internal disconnect will be handled when the object is deleted or program exits)
                if dofree:
                    # Free additional resources if needed (e.g., AVS_Done for Avantes handled globally)
                    pass
                del self.handles[ispec]
                return True, "Disconnected successfully"
            except Exception as e:
                return False, f"Disconnect error: {e}"
        return False, "No spectrometer connected"

    def set_it(self, ispec, it):
        """Sets the integration time (with bounds checking) for the active spectrometer."""
        if ispec not in self.handles:
            return False, "No spectrometer connected"
        # Clamp integration time to allowed range
        if it < 1.0:
            it = 1.0
        elif it > 10000.0:
            it = 10000.0
        try:
            # If spectrometer is Hamamatsu, also set on device (Avantes will set during prepare_measurement)
            handle = self.handles[ispec]['handle']
            if hasattr(handle, 'spec_type') and getattr(handle, 'spec_type', "") == 'Hama3':
                res = handle.set_it(it)
                if res != "OK":
                    return False, f"Set integration time error (Hamamatsu): {res}"
            # Store current integration time in state
            self.handles[ispec]['integration_time'] = it
            return True, f"Integration time set to {it} ms"
        except Exception as e:
            return False, f"Set integration time error: {e}"

    def access_settings(self, ispec, pars=None):
        """Reads or writes spectrometer settings. `pars` is a dict of settings to set, or None/empty to read."""
        if ispec not in self.handles:
            return False, "No spectrometer connected", None
        if not pars:
            # Read current settings
            settings = {
                'integration_time': self.handles[ispec].get('integration_time', 50.0),
                'num_pixels': self.handles[ispec]['num_pixels'],
                # Add other settings if needed
            }
            return True, "Settings retrieved", settings
        else:
            # Write settings
            try:
                for key, value in pars.items():
                    if key == 'integration_time':
                        self.set_it(ispec, value)
                    # Handle other settings if needed
                return True, "Settings updated", None
            except Exception as e:
                return False, f"Settings update error: {e}", None

    def measure(self, ispec, ncy=1):
        """Initiates a measurement with the specified number of cycles (ncy)."""
        if ispec not in self.handles:
            return False, "No spectrometer connected"
        try:
            device = self.handles[ispec]['handle']
            num_pixels = self.handles[ispec]['num_pixels']
            it = self.handles[ispec].get('integration_time', 50.0)
            # If using Avantes, prepare and start via SDK callback
            if not hasattr(device, 'spec_type'):
                code = prepare_measurement(device, num_pixels, integration_time_ms=it, averages=1, cycles=ncy, repetitions=1)
                if code != 0:
                    return False, f"Prepare measurement error: {code}"
                self.data_status[ispec] = 'MEASURING'
                err = start_measurement(device, self._measurement_callback, -1)
                if err != 0:
                    self.data_status[ispec] = 'ERROR'
                    return False, f"Start measurement error: {err}"
                return True, "Measurement started"
            else:
                # For Hamamatsu, use its internal measure (non-blocking) and wait to retrieve data externally
                res = device.measure(ncy=ncy)
                # (We won't wait here in this driver method; data will be handled by external logic or polling)
                if res != "OK":
                    self.data_status[ispec] = 'ERROR'
                    return False, f"Measurement start error: {res}"
                self.data_status[ispec] = 'MEASURING'
                return True, "Measurement started"
        except Exception as e:
            self.data_status[ispec] = 'ERROR'
            return False, f"Measurement error: {e}"

    def get_temp(self, ispec, syst8i=False):
        """Retrieves temperature readings (if supported). Currently only a placeholder for Avantes."""
        if ispec not in self.handles:
            return False, "No spectrometer connected", None
        try:
            temp = 25.0  # default
            # Only Avantes (with AVS API) has a possibility for temperature; Hamamatsu support can be added if available.
            handle = self.handles[ispec]['handle']
            if not hasattr(handle, 'spec_type'):
                device_type = AVS_GetDeviceType(handle)
                # (Add actual temperature retrieval via AVS_GetTemperature if supported by device_type)
            return True, "Temperature retrieved", temp
        except Exception as e:
            return False, f"Temperature read error: {e}", None

    def get_error(self, ispec, err, ss=""):
        """Translates error codes to human-readable messages (mainly for Avantes errors)."""
        error_codes = {
            0: "Success",
            -1: "Generic error",
            -2: "Communication error",
            -3: "No spectrometer connected",
            -4: "Invalid parameter",
            -5: "Measurement in progress",
            # Add more error codes as needed
        }
        msg = error_codes.get(err, f"Unknown error code: {err}")
        if ss:
            msg = f"{msg} - {ss}"
        return msg

    def _measurement_callback(self, p_data, p_user):
        """Callback function for Avantes measurement data (invoked by the SDK)."""
        status_code = p_user[0]
        # Identify which spectrometer (if multiple)
        ispec = None
        for spec_id, spec_data in self.handles.items():
            if spec_data['handle'] == p_data:
                ispec = spec_id
                break
        if ispec is None:
            return
        if status_code == 0:
            try:
                _, data = AVS_GetScopeData(self.handles[ispec]['handle'])
                # Store latest data and mark as ready
                self.handles[ispec]['last_data'] = data
                self.data_status[ispec] = 'DATA_READY'
                # Flag saturation if counts are near ADC limit
                max_value = max(data) if data else 0
                self.handles[ispec]['saturated'] = True if max_value > 90000 else False
                # (Additional stats or handling can be added here)
            except Exception as e:
                self.data_status[ispec] = 'ERROR'
                self.recovery_level[ispec] += 1
                self._attempt_recovery(ispec)
        else:
            # Non-zero status code indicates an error from the Avantes callback
            self.data_status[ispec] = 'ERROR'
            self.recovery_level[ispec] += 1
            self._attempt_recovery(ispec)

    def _attempt_recovery(self, ispec):
        """Implements multi-stage recovery for Avantes spectrometer errors."""
        level = self.recovery_level.get(ispec, 0)
        # Log the recovery attempt with timestamp
        if ispec not in self.recovery_history:
            self.recovery_history[ispec] = []
        self.recovery_history[ispec].append((level, QDateTime.currentDateTime()))
        if level == 1:
            # Level 1: attempt to restart measurement
            self.measure(ispec)
        elif level == 2:
            # Level 2: further recovery steps (e.g., reconnect) can be implemented here
            pass
