import logging
import threading
import time
from collections import OrderedDict
from copy import deepcopy
from ctypes import byref, c_bool, c_int, c_ubyte, c_uint, c_uint32, c_ushort, create_string_buffer, windll
from datetime import datetime

import numpy as np

try:
    from queue import Queue
except ImportError:
    from Queue import Queue

# Logger setup
logger = logging.getLogger(__name__)


# --- Helper Functions (from spec_xfus.py) ---
class SpecClock:
    def now(self):
        return time.time()


spec_clock = SpecClock()


def calc_msl(alias, x, sxy, sy, syy):
    """Dummy implementation for calc_msl."""
    logger.debug(f"[{alias}] Calculating MSL.")
    n = len(x)
    if n == 0:
        return "OK", np.array([]), np.array([]), np.array([])
    mean = sy / n
    std_dev = np.sqrt(np.abs(syy / n - mean**2))
    rms = np.zeros_like(mean)
    return "OK", mean, std_dev, rms


def split_cycles(max_ncy_per_meas, ncy):
    """Splits a number of cycles into packs."""
    if ncy <= 0:
        return [], "0x0cy"
    packs = []
    while ncy > 0:
        pack_size = min(ncy, max_ncy_per_meas)
        packs.append(pack_size)
        ncy -= pack_size

    # Create packs info string
    pack_counts = {}
    for p in packs:
        pack_counts[p] = pack_counts.get(p, 0) + 1
    info = "+".join([f"{count}x{size}cy" for size, count in pack_counts.items()])

    return packs, info


# --- Global Variables ---

# Parameters of the camera (roe)
cameras = {
    "C13015-01": {
        "tpi_st_min": {"S13496": 4500},
        "tpi_st_max": 4294967295,
        "thp_st_min": 10,
        "tlp_st_min": 200,
    }
}

# Parameters of the detectors (sensor)
detectors = {
    "S13496": {
        "tpi_st_min": 106,
        "thp_st_min": 6,
        "tlp_st_min": 100,
        "it_offset_clk": 48,
    }
}

# Possible errors of the DcIc dll
errors = {
    0: "OK",
    1: "Unknown error",
    2: "Initialization not done",
    3: "The parameter is illegal",
    4: "The error occurred by the device connection",
    5: "The error occurred by the device disconnection",
    6: "This control doesn't correspond",
    7: "This control doesn't correspond",
    8: "Fails in the data receive",
    9: "Fails in the close",
    10: "Memory allocation error",
    11: "Error in the data measurement",
    12: "Timeout error",
    20: "Error DcIc_ERROR_WRITEPROTECT",
    21: "DcIc_ERROR_ILLEGAL_ACCESS",
    22: "DcIc_ERROR_ILLEGAL_ADDR",
    23: "Non valid parameter value",
}

Hama3_Spectrometer_Instances = {}
Hama3_devs_info = {}


class SpectrometerDriver:
    def __init__(self):
        self.spec_type = "Hama3"
        self.debug_mode = 1
        self.simulation_mode = False
        self.dll_logging = False
        self.dll_path = "DcIcUSB_v1.1.0.7\x64\DcIcUSB.dll"
        self.sn = "1102185U1"
        self.sensor_model = "S13496"
        self.camera_model = "C13015-01"
        self.clock_frequency_mhz = 10
        self.alias = "1"
        self.npix_active = 4096
        self.npix_vert = 1
        self.nbits = 16
        self.max_it_ms = 4000.0
        self.min_it_ms = 2.4
        self.discriminator_factor = 1.0
        self.gain_detector = -1
        self.gain_roe = -1
        self.offset_roe = -1
        self.eff_saturation_limit = 2**self.nbits - 1
        self.cycle_timeout_ms = 4000
        self.abort_on_saturation = True
        self.max_ncy_per_meas = 100
        self.dll_handler = None
        self.spec_id = None
        self.parlist = None
        self.it_ms = None
        self.logger = None
        self.product_id = None
        self.devtype = None
        self.measuring = False
        self.recovering = False
        self.docatch = False
        self.ncy_requested = 0
        self.ncy_per_meas = [1]
        self.ncy_read = 0
        self.ncy_saturated = 0
        self.internal_meas_done_event = threading.Event()
        self.rcm = np.array([])
        self.rcs = np.array([])
        self.rcl = np.array([])
        self.last_cycle_data = np.array([])  # For live plotting
        self.external_meas_done_event = None
        self.read_data_queue = Queue()
        self.handle_data_queue = Queue()
        self.data_arrival_watchdog_thread = None
        self.data_handling_watchdog_thread = None
        self.error = "OK"
        self.last_errcode = 0

    def initialize_spec_logger(self):
        self.logger = logging.getLogger("spec" + self.alias)
        # Basic config if no handlers exist
        if not self.logger.handlers:
            logging.basicConfig(level=logging.INFO)

    def connect(self):
        ndev = 0
        self.reset_spec_data()

        if self.simulation_mode:
            self.logger.info(f"--- Connecting spectrometer {self.alias}... (Simulation Mode ON) ---")
            self.spec_id = 1
            res = self.set_it(self.min_it_ms)
        else:
            self.logger.info(f"--- Connecting spectrometer {self.alias}... ---")
            res = self.load_spec_dll()
            if res == "OK":
                res = self.initialize_dll()
            if res == "OK":
                res, ndev = self.get_number_of_devices()
            if res == "OK":
                self.logger.info("Getting " + self.spec_type + " spectrometers info...")
                for i in range(ndev):
                    if i not in Hama3_devs_info:
                        spec_id_temp = self.dll_handler.DcIc_Connect(c_uint(i))
                        if spec_id_temp <= 0:
                            res = f"Cannot connect to spectrometer of type {self.spec_type}. Connection error code: {spec_id_temp}"
                            self.logger.warning(res)
                            continue
                        res, dev_info = self.get_dev_info(spec_id_temp)
                        if res != "OK":
                            self.logger.warning(f"Could not get device info for spec {self.alias}, error: {res}")
                            self.dll_handler.DcIc_Disconnect(spec_id_temp)
                            continue

                        self.logger.info(f"Found spec device : {', '.join([k + '=' + str(v) for k, v in dev_info.items()])}")
                        Hama3_devs_info[i] = dev_info
                        self.dll_handler.DcIc_Disconnect(spec_id_temp)

            dev_index = None
            if res == "OK":
                for idx, info in Hama3_devs_info.items():
                    if info["sn"] == self.sn:
                        dev_index = idx
                        break
                if dev_index is None:
                    res = f"Could not find spectrometer with SN {self.sn}"

            if res == "OK":
                self.spec_id = self.dll_handler.DcIc_Connect(c_uint(dev_index))
                if self.spec_id <= 0:
                    res = f"Cannot connect to spectrometer {self.sn}. Error code: {self.spec_id}"

            if res == "OK":
                Hama3_Spectrometer_Instances[self.spec_id] = self
                res = self.abort(ignore_errors=True)

            if res == "OK":
                npix_c = c_ushort()
                resdll = self.dll_handler.DcIc_GetHorizontalPixel(self.spec_id, byref(npix_c))
                res = self.get_error(resdll)
                if res == "OK" and self.npix_active != npix_c.value:
                    res = f"Pixel count mismatch. Expected {self.npix_active}, got {npix_c.value}"

            if res == "OK":
                for it in [self.min_it_ms * 2, self.min_it_ms]:
                    res = self.set_it(it)
                    if res != "OK":
                        break
                    time.sleep(0.2)

            if res == "OK":
                resdll = self.dll_handler.DcIc_SetDataTimeout(self.spec_id, c_int(int(self.cycle_timeout_ms)))
                res = self.get_error(resdll)
                if res != "OK":
                    res = f"connect, could not set cycle timeout. error:{res}"

        if res == "OK":
            if self.data_arrival_watchdog_thread is None:
                self.logger.info("Starting data arrival watchdog thread...")
                self.data_arrival_watchdog_thread = threading.Thread(target=self.data_arrival_watchdog, daemon=True)
                self.data_arrival_watchdog_thread.start()
            if self.data_handling_watchdog_thread is None:
                self.logger.info("Starting data handling watchdog thread...")
                self.data_handling_watchdog_thread = threading.Thread(target=self.data_handling_watchdog, daemon=True)
                self.data_handling_watchdog_thread.start()
            self.logger.info("Spectrometer connected.")

        self.error = res
        return res

    def set_it(self, it_ms):
        res, high_period, _, line_cycle = self.compute_st_pulses(
            it_ms,
            clock_frequency_mhz=self.clock_frequency_mhz,
            camera=self.camera_model,
            sensor=self.sensor_model,
        )

        if res == "OK":
            thp_st = c_uint32(high_period)
            tpi_st = c_uint32(line_cycle)

            if self.simulation_mode:
                if self.debug_mode >= 2:
                    self.logger.debug(f"Setting IT to {it_ms}ms (simulated)")
                res = "OK"
            else:
                if self.debug_mode >= 2:
                    self.logger.debug(f"Setting IT to {it_ms}ms")

                preliminar_thp_st = c_uint32(cameras[self.camera_model]["thp_st_min"])
                resdll = self.dll_handler.DcIc_SetStartPulseTime(self.spec_id, preliminar_thp_st)
                res = self.get_error(resdll)
                if res != "OK":
                    res = f"set_it, Could not set preliminary Start Pulse Time, error: {res}"
                else:
                    resdll = self.dll_handler.DcIc_SetLineTime(self.spec_id, tpi_st)
                    res = self.get_error(resdll)
                    if res != "OK":
                        res = f"set_it, Could not set Line Time, error: {res}"
                    else:
                        resdll = self.dll_handler.DcIc_SetStartPulseTime(self.spec_id, thp_st)
                        res = self.get_error(resdll)
                        if res != "OK":
                            res = f"set_it, Could not set Start Pulse Time, error: {res}"
        else:
            res = "Cannot set IT because it is out of limits."

        if res == "OK":
            self.it_ms = it_ms

        self.error = res
        return res

    def measure(self, ncy=1):
        self.internal_meas_done_event.clear()
        self.measuring = True
        self.docatch = True
        self.error = "OK"
        self.read_data_queue.put(ncy)
        return self.error

    def abort(self, ignore_errors=False, log=True, disable_docatch=True):
        if disable_docatch:
            self.docatch = False
        res = "OK"
        if self.simulation_mode:
            if log:
                self.logger.info("abort, stopping any ongoing measurement (simulation mode)...")
        else:
            if log:
                self.logger.info("abort, stopping any ongoing measurement...")
            if self.spec_id is not None and self.dll_handler is not None:
                try:
                    resdll = self.dll_handler.DcIc_Abort(self.spec_id)
                    res = self.get_error(resdll)
                    if res != "OK":
                        res = f"Spec {self.alias}, could not stop measurement. Error: {res}"
                        if ignore_errors:
                            self.logger.warning(f"abort, {res}")
                            res = "OK"
                        else:
                            self.logger.error(f"abort, {res}")
                except Exception as e:
                    res = f"Exception while stopping measurement: {e}"
                    if ignore_errors:
                        self.logger.warning(res)
                        res = "OK"
                    else:
                        self.logger.exception(e)
        self.measuring = False
        self.error = res
        return res

    def wait_for_measurement(self):
        self.internal_meas_done_event.wait()
        return self.error

    def disconnect(self, dofree=False, ignore_errors=False):
        res = "OK"
        if self.spec_id in Hama3_Spectrometer_Instances:
            del Hama3_Spectrometer_Instances[self.spec_id]

        if self.simulation_mode:
            self.logger.info(f"Disconnecting spectrometer {self.alias}... (Simulation mode)")
        elif self.dll_handler is not None and self.spec_id is not None:
            self.logger.info(f"Disconnecting spectrometer {self.alias}, dofree={dofree}")
            resdll = self.dll_handler.DcIc_Disconnect(self.spec_id)
            if not ignore_errors:
                r = self.get_error(resdll)
                if r != "OK":
                    self.logger.error(f"disconnect, Could not disconnect device, error: {r}")
            if dofree:
                self.logger.info("Terminating dll session...")
                resdll = self.dll_handler.DcIc_Terminate()
                if not ignore_errors:
                    r = self.get_error(resdll)
                    if r != "OK":
                        self.logger.error(f"disconnect, Could not terminate dll, error: {r}")

        if self.data_arrival_watchdog_thread is not None:
            self.logger.info(f"Closing data arrival watchdog thread of spectrometer {self.alias}.")
            self.read_data_queue.put(None)
            self.data_arrival_watchdog_thread.join()
            self.data_arrival_watchdog_thread = None

        if self.data_handling_watchdog_thread is not None:
            self.logger.info(f"Closing data handling watchdog thread of spectrometer {self.alias}.")
            self.handle_data_queue.put((None, None, (None, None, None)))
            self.data_handling_watchdog_thread.join()
            self.data_handling_watchdog_thread = None

        self.logger.info(f"Spectrometer {self.alias} disconnected.")
        self.error = res
        return res

    # --- Helper methods ---
    def measure_blocking(self, ncy=10):
        res = "OK"
        _ = self.abort(ignore_errors=True, log=False)
        self.internal_meas_done_event.clear()
        self.measuring = True
        self.docatch = True
        self.ncy_requested = ncy
        self.reset_spec_data()
        self.ncy_per_meas, packs_info = split_cycles(self.max_ncy_per_meas, ncy)
        ncalls = len(self.ncy_per_meas)

        if self.debug_mode > 0:
            self.logger.info(f"Starting measurement, ncy={ncy}, IT={self.it_ms} ms, npacks={packs_info}")

        self.meas_start_time = spec_clock.now()

        for call_index in range(ncalls):
            if not self.docatch:
                break
            ncy_pack = self.ncy_per_meas[call_index]
            res, raw_data, arrival_time = self.measure_pack(ncy_pack)
            if res == "OK":
                self.handle_data_queue.put((call_index, arrival_time, (deepcopy(raw_data), [], [])))
            else:
                if not self.docatch:
                    res = "OK"
                    break
                else:
                    res = f"Error at measurement call {call_index + 1}/{ncalls}: {res}"
                    self.logger.error(res)
                    break
        if res == "OK":
            _ = self.wait_for_measurement()
        else:
            while not self.handle_data_queue.empty():
                _ = self.handle_data_queue.get()

        self.measuring = False
        self.error = res
        if self.external_meas_done_event is not None and not self.recovering:
            self.external_meas_done_event.set()
        return res

    def measure_pack(self, ncy_pack):
        npix_pack = ncy_pack * self.npix_vert * self.npix_active
        if self.simulation_mode:
            time.sleep((ncy_pack * self.it_ms) / 1000.0)
            simulated_data = np.random.randint(2, 1000, (npix_pack,))
            return "OK", simulated_data, spec_clock.now()

        _ = self.abort(ignore_errors=True, log=False, disable_docatch=False)
        meas_buff = (c_ushort * npix_pack)()
        meas_buff_len_bytes = c_uint(npix_pack * 2)

        resdll = self.dll_handler.DcIc_Capture(self.spec_id, byref(meas_buff), meas_buff_len_bytes)
        res = self.get_error(resdll)
        if res != "OK":
            return f"Could not start measurement, {res}.", None, None

        while True:
            if not self.docatch:
                _ = self.abort(ignore_errors=True, log=False, disable_docatch=False)
                return "Measurement has been aborted.", None, None

            status = self.dll_handler.DcIc_Wait(self.spec_id)
            if status == 2:  # Completed
                return "OK", meas_buff, spec_clock.now()
            elif status == 0:  # Error
                res = self.get_error("")
                return f"Error while waiting for data, {res}.", None, None
            elif status == 1:  # Measuring
                time.sleep((self.it_ms / 10.0) / 1000.0)

    def data_arrival_watchdog(self):
        self.logger.info("Started data arrival watchdog..")
        while True:
            ncy = self.read_data_queue.get()
            if ncy is None:
                self.logger.info("Exiting data arrival watchdog thread...")
                break
            else:
                res = self.measure_blocking(ncy)
                self.error = res
                if res != "OK":
                    self.internal_meas_done_event.set()
        self.logger.info("Exited data arrival watchdog")

    def data_handling_watchdog(self):
        self.logger.info("Started data handling watchdog..")
        while True:
            call_index, arrival_time, data = self.handle_data_queue.get()
            if call_index is None:
                self.logger.info(f"Exiting data handling watchdog thread of spectrometer {self.alias}...")
                break
            elif not self.docatch:
                continue
            else:
                rc = np.ctypeslib.as_array(data[0]).astype(np.float64)
                ncy_pack = self.ncy_per_meas[call_index]
                rc_cycles = np.split(rc, ncy_pack)
                for cycle_data in rc_cycles:
                    self.ncy_read += 1
                    issat, data_ok = self.handle_cycle_data(self.ncy_read, cycle_data, [], [])
                    if (issat and self.abort_on_saturation) or not data_ok:
                        if issat:
                            self.logger.info("Saturation detected. Aborting...")
                        self.docatch = False
                        while not self.handle_data_queue.empty():
                            self.handle_data_queue.get()
                        self.measurement_done()
                        break
                    elif self.ncy_handled == self.ncy_requested:
                        self.measurement_done()
                        break
        self.logger.info(f"Exited data handling watchdog of spectrometer {self.alias}")

    def handle_cycle_data(self, ncy_read, rc, rc_blind_left, rc_blind_right):
        self.last_cycle_data = rc  # Update for live plot
        rcmax = rc.max()
        rcmin = rc.min()
        data_ok = True
        if rcmin < 0:
            self.logger.warning("handle_cycle_data, negative counts detected !!!")
            data_ok = False
        elif np.isnan(rcmax) or np.isnan(rcmin):
            self.logger.warning("handle_cycle_data, NaN counts detected !!!")
            data_ok = False

        issat = rcmax >= self.eff_saturation_limit
        if (issat and self.abort_on_saturation) or not data_ok:
            return issat, data_ok

        self.sy += rc
        self.syy += rc**2
        self.sxy += (ncy_read - 1) * rc
        self.ncy_handled += 1
        if issat:
            self.ncy_saturated += 1
        return issat, data_ok

    def measurement_done(self):
        x = np.arange(self.ncy_handled)
        res, self.rcm, self.rcs, self.rcl = calc_msl(self.alias, x, self.sxy, self.sy, self.syy)
        if res != "OK":
            self.logger.warning(f"Error at function calc_msl: {res}")
        if self.debug_mode >= 1:
            self.logger.debug(f"Measurement done for spec {self.alias}")
        self.internal_meas_done_event.set()

    def reset_spec_data(self):
        while not self.read_data_queue.empty():
            self.read_data_queue.get()
        while not self.handle_data_queue.empty():
            self.handle_data_queue.get()
        self.ncy_read = 0
        self.ncy_handled = 0
        self.ncy_saturated = 0
        self.sy = np.zeros(self.npix_active, dtype=np.float64)
        self.syy = np.zeros(self.npix_active, dtype=np.float64)
        self.sxy = np.zeros(self.npix_active, dtype=np.float64)
        self.rcm = np.array([])
        self.last_cycle_data = np.array([])

    def compute_st_pulses(self, it_ms, clock_frequency_mhz=10.0, camera="C13015-01", sensor="S13496"):
        f_clk = clock_frequency_mhz * 1.0e6
        integration_time_s = float(it_ms) / 1000.0
        high_period = int(round(integration_time_s * f_clk)) - int(detectors[sensor]["it_offset_clk"])
        if high_period < cameras[camera]["thp_st_min"]:
            high_period = cameras[camera]["thp_st_min"]
        if high_period < detectors[sensor]["thp_st_min"]:
            high_period = detectors[sensor]["thp_st_min"]
        low_period = int(detectors[sensor]["tlp_st_min"])
        line_cycle = high_period + low_period
        if line_cycle < cameras[camera]["tpi_st_min"][sensor]:
            line_cycle = cameras[camera]["tpi_st_min"][sensor]
        elif line_cycle > cameras[camera]["tpi_st_max"]:
            line_cycle = cameras[camera]["tpi_st_max"]
        if line_cycle < detectors[sensor]["tpi_st_min"]:
            line_cycle = detectors[sensor]["tpi_st_min"]
        low_period = line_cycle - high_period
        if low_period < cameras[camera]["tlp_st_min"]:
            low_period = cameras[camera]["tlp_st_min"]
        return "OK", high_period, low_period, line_cycle

    def get_error(self, resdll):
        self.last_errcode = resdll
        if isinstance(resdll, int) and resdll > 0:
            return "OK"
        if isinstance(resdll, bool) and resdll:
            return "OK"
        if self.dll_handler is not None:
            try:
                errcode = self.dll_handler.DcIc_GetLastError()
                return errors.get(errcode, "Unknown error")
            except Exception as e:
                return f"Exception while reading last error: {e}"
        return "Cannot check error, no dll handler."

    def load_spec_dll(self):
        self.logger.info(f"Loading dll: {self.dll_path}")
        try:
            self.dll_handler = windll.LoadLibrary(self.dll_path)
            return "OK"
        except Exception as e:
            self.logger.exception(e)
            return f"Exception while loading dll: {e}"

    def initialize_dll(self):
        self.logger.info(f"Initializing spec {self.alias} dll...")
        try:
            resdll = self.dll_handler.DcIc_Initialize()
            res = self.get_error(resdll)
            if res != "OK":
                return f"Could not initialize dll, error: {res}"
            return "OK"
        except Exception as e:
            self.logger.exception(e)
            return f"Exception while initializing dll: {e}"

    def get_number_of_devices(self):
        device_count = c_int()
        try:
            resdll = self.dll_handler.DcIc_CreateDeviceInfo(byref(device_count))
            res = self.get_error(resdll)
            if res != "OK":
                return f"Could not get number of devices, error: {res}", 0
            ndev = device_count.value
            if ndev == 0:
                return f"No {self.spec_type} spectrometer found.", 0
            return "OK", ndev
        except Exception as e:
            self.logger.exception(e)
            return f"Exception while getting number of devices: {e}", 0

    def get_dev_info(self, dev_id):
        dev_info = OrderedDict()
        dev_info["dev_id"] = dev_id
        # Get Serial Number
        buff = create_string_buffer(17)
        resdll = self.dll_handler.DcIc_GetSerialNumber(c_int(dev_id), byref(buff))
        res = self.get_error(resdll)
        if res != "OK":
            return f"Cannot get serial number, error: {res}", dev_info
        dev_info["sn"] = buff.value.decode('utf-8')
        return "OK", dev_info