from PyQt5.QtCore import QObject, pyqtSignal, QTimer, QDateTime
from PyQt5.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QPushButton,
    QWidget, QLabel, QSpinBox, QCheckBox
)
import pyqtgraph as pg
from pyqtgraph import ViewBox
import numpy as np
import os

from drivers.spectrometer import (
    connect_spectrometer,
    AVS_MeasureCallback, AVS_MeasureCallbackFunc,
    AVS_GetScopeData, StopMeasureThread,
    prepare_measurement
)

class SpectrometerController(QObject):
    """
    Controller for the spectrometer section of the GUI.
    Handles connecting to the spectrometer, starting/stopping measurements, and live plotting.
    """
    status_signal = pyqtSignal(str)  # Signal to send status messages (to status bar or log in GUI)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent

        # --- UI Setup ---
        self.groupbox = QGroupBox("Spectrometer")
        self.groupbox.setObjectName("spectrometerGroup")
        main_layout = QVBoxLayout()

        # Control buttons layout
        btn_layout = QHBoxLayout()
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setStyleSheet("font-weight: bold; font-size: 11pt;")
        self.connect_btn.clicked.connect(self.connect)
        btn_layout.addWidget(self.connect_btn)

        self.start_btn = QPushButton("Start")
        self.start_btn.setStyleSheet("font-weight: bold; font-size: 11pt;")
        self.start_btn.setEnabled(False)
        self.start_btn.clicked.connect(self.start)
        btn_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setStyleSheet("font-weight: bold; font-size: 11pt;")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop)
        btn_layout.addWidget(self.stop_btn)

        self.save_btn = QPushButton("Save")
        self.save_btn.setStyleSheet("font-weight: bold; font-size: 11pt;")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self.save)
        btn_layout.addWidget(self.save_btn)

        self.toggle_btn = QPushButton("Start Saving")
        self.toggle_btn.setStyleSheet("font-weight: bold; font-size: 11pt;")
        self.toggle_btn.setEnabled(False)
        self.toggle_btn.clicked.connect(self.toggle)
        btn_layout.addWidget(self.toggle_btn)

        main_layout.addLayout(btn_layout)

        # Integration time and settings layout
        integ_layout = QHBoxLayout()
        integ_label = QLabel("Integration Time (ms):")
        integ_label.setStyleSheet("font-weight: bold;")
        integ_layout.addWidget(integ_label)
        self.integ_spinbox = QSpinBox()
        self.integ_spinbox.setRange(1, 4000)
        self.integ_spinbox.setValue(5)  # default integration time = 5 ms
        self.integ_spinbox.setSingleStep(5)
        integ_layout.addWidget(self.integ_spinbox)
        self.apply_btn = QPushButton("Apply Settings")
        self.apply_btn.setEnabled(False)
        self.apply_btn.clicked.connect(self.update_measurement_settings)
        integ_layout.addWidget(self.apply_btn)
        main_layout.addLayout(integ_layout)

        # Cycle count and repetition layout
        cycles_layout = QHBoxLayout()
        cycles_label = QLabel("Cycles:")
        cycles_label.setStyleSheet("font-weight: bold;")
        cycles_layout.addWidget(cycles_label)
        self.cycles_spinbox = QSpinBox()
        self.cycles_spinbox.setRange(1, 100)
        self.cycles_spinbox.setValue(1)
        self.cycles_spinbox.setSingleStep(1)
        cycles_layout.addWidget(self.cycles_spinbox)
        repetitions_label = QLabel("Repetitions:")
        repetitions_label.setStyleSheet("font-weight: bold;")
        cycles_layout.addWidget(repetitions_label)
        self.repetitions_spinbox = QSpinBox()
        self.repetitions_spinbox.setRange(1, 100)
        self.repetitions_spinbox.setValue(1)
        self.repetitions_spinbox.setSingleStep(1)
        cycles_layout.addWidget(self.repetitions_spinbox)
        main_layout.addLayout(cycles_layout)

        # Plot setup using pyqtgraph
        pg.setConfigOption('background', '#252525')    # dark background for plot
        pg.setConfigOption('foreground', '#e0e0e0')    # light gray axes text
        pg.setConfigOption('antialias', False)
        pg.setConfigOption('useOpenGL', True)
        self.plot_px = pg.PlotWidget()
        self.plot_px.setLabel('bottom', 'Pixel')
        self.plot_px.setLabel('left', 'Count')
        # Enable auto-range for Y-axis (auto-scaling)
        self.plot_px.getViewBox().enableAutoRange(ViewBox.YAxis, True)
        self.plot_px.getViewBox().setAutoVisible(y=True)
        # Remove grid from the plot for a cleaner look
        self.plot_px.showGrid(x=False, y=False)
        # Set initial X-axis range (will update after connection)
        self.plot_px.setXRange(0, 2048)
        # Customize X-axis ticks (every 100 pixels for initial default size)
        x_axis = self.plot_px.getAxis('bottom')
        x_ticks = [(i, str(i)) for i in range(0, 2049, 100)]
        x_axis.setTicks([x_ticks])
        # Plot curve for pixel counts
        self.curve_px = self.plot_px.plot([], [], 
                                          pen=pg.mkPen('#f44336', width=2), 
                                          fillLevel=0, 
                                          fillBrush=pg.mkBrush(244, 67, 54, 50),
                                          name="Pixel Counts",
                                          skipFiniteCheck=True)
        main_layout.addWidget(self.plot_px)
        self.groupbox.setLayout(main_layout)

        # Internal state
        self._ready = False
        self.handle = None        # handle to spectrometer (object or handle id)
        self.wls = []            # wavelength calibration (if available)
        self.intens = []         # latest intensity data
        self.npix = 0            # number of pixels in spectrometer

        # If parent (main UI) has a data saving toggle, use it for the toggle button
        if parent is not None:
            try:
                self.toggle_btn.clicked.disconnect(self.toggle)
            except Exception:
                pass
            if hasattr(parent, 'toggle_data_saving'):
                self.toggle_btn.clicked.connect(parent.toggle_data_saving)

        # Ensure data directory exists for saving snapshots
        self.csv_dir = "data"
        os.makedirs(self.csv_dir, exist_ok=True)

        # Timer for refreshing the plot periodically (20 Hz)
        self.plot_timer = QTimer(self)
        self.plot_timer.timeout.connect(self._update_plot)
        self.plot_timer.start(50)  # 50 ms interval

        self.static_curves = []  # list to hold any static/reference curves if needed

        # Attempt auto-connection on startup after a short delay
        QTimer.singleShot(500, self.connect)

    def connect(self):
        """
        Connect to the spectrometer (auto-detects type).
        If connection fails and this was an auto-connect attempt, retries after 5 seconds.
        """
        self.status_signal.emit("Connecting to spectrometer...")
        is_auto_connect = hasattr(self, '_auto_connect') and self._auto_connect
        try:
            handle, wavelengths, num_pixels, serial_str = connect_spectrometer()
        except Exception as e:
            error_msg = f"Connection failed: {e}"
            self.status_signal.emit(error_msg)
            if is_auto_connect:
                # Retry connection after 5 seconds if auto-connecting on startup
                self.status_signal.emit("Will retry connection in 5 seconds...")
                QTimer.singleShot(5000, self.connect)
            return

        # Successfully connected
        self.handle = handle
        # Store wavelength calibration (if numpy array, convert to list for compatibility)
        self.wls = wavelengths.tolist() if isinstance(wavelengths, np.ndarray) else wavelengths
        self.npix = num_pixels
        self._ready = True

        # Update plot X-axis range and ticks for actual pixel count
        self.plot_px.setXRange(0, self.npix)
        x_axis = self.plot_px.getAxis('bottom')
        x_ticks = [(i, str(i)) for i in range(0, self.npix + 1, 100)]
        x_axis.setTicks([x_ticks])

        # Enable the Start button now that a spectrometer is connected
        self.start_btn.setEnabled(True)
        # Determine spectrometer type for status message
        if hasattr(self.handle, 'spec_type') and getattr(self.handle, 'spec_type', "") == 'Hama3':
            # Hamamatsu spectrometer connected
            self.status_signal.emit(f"Spectrometer ready (Hamamatsu SN={serial_str})")
        else:
            # Avantes spectrometer connected
            # Try to enable high-resolution ADC mode if supported (for certain Avantes models)
            if getattr(self, 'high_res_adc', False):
                try:
                    from drivers.avaspec import AVS_UseHighResAdc
                    AVS_UseHighResAdc(self.handle, True)
                    self.status_signal.emit("High-resolution ADC mode enabled")
                except Exception as err:
                    self.status_signal.emit(f"High-res ADC not enabled: {err}")
            self.status_signal.emit(f"Spectrometer ready (SN={serial_str})")

        # Clear any auto-connect flag after first successful connection
        if hasattr(self, '_auto_connect'):
            self._auto_connect = False

    def start(self):
        """
        Start a live measurement with current settings.
        For Hamamatsu, this runs a continuous loop in a background thread.
        For Avantes, it starts the measurement via callback mechanism.
        """
        if not self._ready:
            self.status_signal.emit("Spectrometer not ready")
            return

        # Read user-specified settings from the UI
        integration_time = float(self.integ_spinbox.value())
        cycles = self.cycles_spinbox.value()
        repetitions = self.repetitions_spinbox.value()

        # Hamamatsu spectrometer handling
        if hasattr(self.handle, 'spec_type') and getattr(self.handle, 'spec_type', "") == 'Hama3':
            # Set integration time on device
            res = self.handle.set_it(integration_time)
            if res != "OK":
                self.status_signal.emit(f"Failed to set integration time: {res}")
                return
            # Note: Hamamatsu uses 'cycles' for internal averaging; 'repetitions' controls how many loops to run
            self.status_signal.emit(f"Starting measurement (Int: {integration_time} ms, Cycles: {cycles})")
            self.measure_active = True
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.apply_btn.setEnabled(True)

            # Launch measurement loop in a separate thread to not block the GUI
            import threading
            def _hama_loop():
                count = 0
                total_loops = repetitions if repetitions > 1 else float('inf')
                try:
                    while self.measure_active and count < total_loops:
                        res_meas = self.handle.measure(ncy=cycles)
                        if res_meas != "OK":
                            self.status_signal.emit(f"Measurement error: {res_meas}")
                            break
                        # Wait for data to be ready
                        self.handle.wait_for_measurement()
                        # If data is invalid (e.g., on saturation), skip updating intensities
                        if self.handle.rcm is None or len(self.handle.rcm) != self.handle.npix_active:
                            print("⚠️ Warning: Skipped a frame (invalid data or saturation).")
                        else:
                            # If saturation likely, warn in console (counts >= 65000 for 16-bit ADC)
                            if np.max(self.handle.rcm) >= 65000:
                                print(f"⚠️ Warning: Possible saturation detected (max count = {int(np.max(self.handle.rcm))})")
                            data = self.handle.rcm
                            # Ensure data length matches expected pixel count
                            max_pixels = self.npix
                            full_data = [0.0] * max_pixels
                            data_to_use = data[:max_pixels] if len(data) > max_pixels else data
                            full_data[:len(data_to_use)] = list(data_to_use)
                            # Store intensity data for plotting
                            self.intens = full_data
                            count += 1
                        # If a fixed number of repetitions was set and we've reached it, stop measuring
                        if self.measure_active and repetitions > 1 and count >= total_loops:
                            self.measure_active = False
                            # Use a singleShot QTimer to safely update UI from main thread
                            QTimer.singleShot(0, self._on_stop)
                except Exception as err:
                    print(f"Exception in Hamamatsu measurement loop: {err}")

            self._hama_thread = threading.Thread(target=_hama_loop, daemon=True)
            self._hama_thread.start()
            return

        # Avantes spectrometer handling
        # Choose number of averages based on integration time for performance
        if integration_time < 10:
            averages = 10
        elif integration_time < 100:
            averages = 5
        elif integration_time < 1000:
            averages = 2
        else:
            averages = 1
        self.current_integration_time_us = integration_time  # (store if needed externally in microseconds)

        self.status_signal.emit(
            f"Starting measurement (Int: {integration_time} ms, Avg: {averages}, Cycles: {cycles}, Rep: {repetitions})"
        )
        code = prepare_measurement(self.handle, self.npix,
                                   integration_time_ms=integration_time,
                                   averages=averages, cycles=cycles, repetitions=repetitions)
        if code != 0:
            self.status_signal.emit(f"Prepare error: {code}")
            return

        self.measure_active = True
        # Set up callback for incoming Avantes data
        self.cb = AVS_MeasureCallbackFunc(self._cb)
        err = AVS_MeasureCallback(self.handle, self.cb, -1)  # -1 for infinite measurements until stopped
        if err != 0:
            self.status_signal.emit(f"Callback error: {err}")
            self.measure_active = False
            return

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.apply_btn.setEnabled(True)
        self.status_signal.emit("Measurement started")

    def _cb(self, p_data, p_user):
        """
        Callback function for Avantes measurements. Called automatically when data is ready.
        Retrieves the spectral data and updates internal intensity storage.
        """
        status_code = p_user[0]
        if status_code == 0:
            # Measurement successful, retrieve spectrum data
            _, data = AVS_GetScopeData(self.handle)
            max_pixels = self.npix
            full_data = [0.0] * max_pixels
            data_to_use = data[:max_pixels] if len(data) > max_pixels else data
            full_data[:len(data_to_use)] = data_to_use
            self.intens = full_data
            # If first data received, enable Save and Start Saving buttons
            self.save_btn.setEnabled(True)
            self.toggle_btn.setEnabled(True)
            # (If needed, pass integration time to parent for logging)
            if hasattr(self, 'current_integration_time_us'):
                if hasattr(self, 'parent') and self.parent is not None:
                    # Store current integration time in parent for reference (if parent expects it)
                    self.parent.current_integration_time_us = self.current_integration_time_us
        else:
            # Non-zero status code indicates an error in measurement
            self.status_signal.emit(f"Spectrometer error (code {status_code})")

    def _update_plot(self):
        """Periodic timer callback to refresh the plot with latest data."""
        if not self.intens:
            return  # nothing to plot yet
        try:
            intensities = np.array(self.intens, dtype=float)
            pixel_indices = np.arange(len(intensities))
            # (Optional) Downsample data for performance if needed
            if getattr(self, 'downsample_factor', 1) > 1:
                step = int(self.downsample_factor)
                intensities = intensities[::step]
                pixel_indices = pixel_indices[::step]
            # Update the graph curve with new data
            self.curve_px.setData(pixel_indices, intensities)
            # Occasionally adjust Y-axis range to ensure the data fits
            if not hasattr(self, '_range_update_counter'):
                self._range_update_counter = 0
            self._range_update_counter += 1
            if self._range_update_counter >= 10:
                self._range_update_counter = 0
                if intensities.size > 0:
                    max_val = float(np.max(intensities))
                    if max_val > 0:
                        max_y = max_val * 1.1  # a bit of headroom above max
                        # If any static/reference curves are plotted, include them in range calculation
                        for curve in getattr(self, 'static_curves', []):
                            if hasattr(curve, 'yData') and curve.yData is not None and len(curve.yData) > 0:
                                curve_max = float(np.max(curve.yData))
                                if curve_max > max_y:
                                    max_y = curve_max * 1.1
                        self.plot_px.setYRange(0, max_y)
        except Exception as e:
            print(f"Plot update error: {e}")
            # On error, skip this update but keep timer running

    def stop(self):
        """Stop the ongoing measurement."""
        if not getattr(self, 'measure_active', False):
            return  # nothing to stop
        self.measure_active = False
        # Handle stop for Hamamatsu vs Avantes
        if hasattr(self.handle, 'spec_type') and getattr(self.handle, 'spec_type', "") == 'Hama3':
            # Hamamatsu: abort the ongoing measurement
            try:
                self.handle.abort()
            except Exception as e:
                print(f"Hamamatsu abort error: {e}")
            # Wait for the background thread to finish if it's still running
            if hasattr(self, '_hama_thread'):
                if self._hama_thread.is_alive():
                    self._hama_thread.join(timeout=1.0)
                self._hama_thread = None
            # Reset UI via common stop handler
            self._on_stop()
        else:
            # Avantes: use StopMeasureThread to safely stop measurement from the DLL
            stopper = StopMeasureThread(self.handle, parent=self)
            stopper.finished_signal.connect(self._on_stop)
            stopper.start()

    def _on_stop(self):
        """Internal handler to reset UI state after a measurement stops."""
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.apply_btn.setEnabled(False)
        self.status_signal.emit("Measurement stopped")

    def save(self):
        """Save the current spectrum to a CSV file with a timestamp."""
        if not self.intens:
            return  # nothing to save
        timestamp = QDateTime.currentDateTime().toString("yyyyMMdd_hhmmss")
        filename = os.path.join(self.csv_dir, f"spectrum_{timestamp}.csv")
        try:
            with open(filename, 'w') as f:
                f.write("Pixel,Intensity\n")
                for i, val in enumerate(self.intens):
                    f.write(f"{i},{val}\n")
            self.status_signal.emit(f"Snapshot saved: {filename}")
        except Exception as e:
            self.status_signal.emit(f"Save failed: {e}")

    def toggle(self):
        """
        Placeholder for toggling continuous data saving.
        This can be overridden or connected to a main window method that handles data logging.
        """
        pass

    def update_measurement_settings(self):
        """
        Apply new integration time (and potentially other settings) during an ongoing measurement if supported.
        For Hamamatsu, it can directly set a new integration time on-the-fly.
        For Avantes (callback mode), the new settings apply on the next measurement cycle.
        """
        new_it = float(self.integ_spinbox.value())
        if hasattr(self.handle, 'spec_type') and getattr(self.handle, 'spec_type', "") == 'Hama3':
            # Update integration time immediately for Hamamatsu
            res = self.handle.set_it(new_it)
            if res == "OK":
                self.status_signal.emit(f"Integration time updated to {new_it} ms")
            else:
                self.status_signal.emit(f"Failed to update integration time: {res}")
        else:
            # For Avantes, cannot change integration time mid-run without restarting measurement
            self.status_signal.emit("New settings will apply on the next measurement start")
