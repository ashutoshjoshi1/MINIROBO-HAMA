import os
import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal
import ctypes
import sys

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

import os
import sys
import numpy as np

# 1) RELATIVE IMPORT of your local Hama3 driver
try:
    from .hama3_spectrometer import Hama3_Spectrometer
    print("[spectrometer.py] Imported Hama3_Spectrometer via relative import.")
except ImportError:
    try:
        from drivers.hama3_spectrometer import Hama3_Spectrometer
        print("[spectrometer.py] Imported Hama3_Spectrometer via absolute import.")
    except ImportError:
        Hama3_Spectrometer = None
        print("[spectrometer.py] Could not import Hama3_Spectrometer at all!")

# ... (Avantes imports unchanged) ...


def connect_spectrometer():
    """
    Try Hamamatsu first, then Avantes. Returns (handle, wavelengths, npix, serial_str).
    """
    # === TRY HAMAMATSU ===
    if Hama3_Spectrometer is not None:
        print("[connect_spectrometer] Attempting Hamamatsu connection...")
        try:
            hama = Hama3_Spectrometer()

            # 2) BUILD ABSOLUTE DLL PATH
            base = os.path.dirname(__file__)
            dll_rel = os.path.join("..", "spec_hama3", "DcIcUSB_v1.1.0.7", "x64", "DcIcUSB.dll")
            dll_path = os.path.abspath(os.path.join(base, dll_rel))
            print(f"[connect_spectrometer] Hamamatsu DLL path: {dll_path}")
            hama.dll_path = dll_path

            # 3) PASS SERIAL AS BYTES
            #    If your SN is 46AN0776, do *not* include the b'' inside the string literal!
            hama.sn = b"46AN0776"
            print(f"[connect_spectrometer] Hamamatsu SN set to: {hama.sn!r}")

            hama.debug_mode = 1
            hama.alias = "hama1"
            hama.npix_active = 4096
            hama.initialize_spec_logger()

            res = hama.connect()
            print(f"[connect_spectrometer] Hamamatsu connect() returned: {res!r}")
            if res == "OK":
                it_res = hama.set_it(5.0)
                print(f"[connect_spectrometer] Hamamatsu set_it() returned: {it_res!r}")
                if it_res == "OK":
                    # tag it so upper layers know it’s Hamamatsu
                    setattr(hama, "spec_type", "Hama3")
                    wavelengths = list(range(hama.npix_active))
                    serial_str = hama.sn.decode("ascii", "ignore")
                    return hama, wavelengths, hama.npix_active, serial_str

            print("[connect_spectrometer] Hamamatsu did not connect OK, falling through to Avantes.")

        except Exception as e:
            print(f"[connect_spectrometer] Exception in Hamamatsu block: {e!s}")

    else:
        print("[connect_spectrometer] Hama3_Spectrometer class is None, skipping Hamamatsu.")

    # === TRY AVANTES ===
    print("[connect_spectrometer] Attempting Avantes connection...")
    # … your existing Avantes logic here …

    # If neither connected:
    raise RuntimeError("❌ No spectrometer connected.")


def prepare_measurement(spec_handle, num_pixels, integration_time_ms=50.0, averages=1, cycles=1, repetitions=1):
    """Prepare the measurement configuration for an Avantes spectrometer."""
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
    """Start an Avantes measurement with a callback (non-blocking)."""
    cb_ptr = AVS_MeasureCallbackFunc(callback_func)
    return AVS_MeasureCallback(spec_handle, cb_ptr, num_scans)

def stop_measurement(spec_handle):
    """Stop an ongoing Avantes measurement."""
    AVS_StopMeasure(spec_handle)

def close_spectrometer():
    """Close the spectrometer interface (Avantes)."""
    AVS_Done()

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
            # Store handle and info
            self.handles[spec_id] = {
                'handle': handle,
                'wavelengths': wavelengths,
                'num_pixels': num_pixels,
                'serial': serial_str
            }
            # Initialize status and stats
            self.data_status[spec_id] = 'READY'
            self.recovery_level[spec_id] = 0
            self.recovery_history[spec_id] = []
            self.measurement_stats[spec_id] = {'durations': [], 'avg_time': 0}
            # Optionally, perform a test measurement to verify everything works
            if do_test:
                self.set_it(spec_id, 50.0)  # default integration time 50 ms for test
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
        handle_obj = self.handles[spec_id]['handle']
        try:
            # Check if handle is an Avantes handle (ctypes pointer or int) or a Hama3_Spectrometer instance
            if isinstance(handle_obj, ctypes.c_void_p) or isinstance(handle_obj, int):
                # Avantes spectrometer
                AVS_Deactivate(handle_obj)
                if free_interface:
                    AVS_Done()
            else:
                # Hamamatsu spectrometer
                handle_obj.disconnect(dofree=free_interface)
            # Clean up stored info
            self.handles.pop(spec_id, None)
            self.data_status.pop(spec_id, None)
            self.recovery_level.pop(spec_id, None)
            self.recovery_history.pop(spec_id, None)
            self.measurement_stats.pop(spec_id, None)
            return True
        except Exception as e:
            print(f"Error disconnecting spectrometer: {e}")
            return False


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
