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
    connect_spectrometer, AVS_MeasureCallback, AVS_MeasureCallbackFunc, 
    AVS_GetScopeData, StopMeasureThread, prepare_measurement, SpectrometerDriver
)

class SpectrometerController(QObject):
    status_signal = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent

        # Setup UI components
        self.groupbox = QGroupBox("Spectrometer")
        self.groupbox.setObjectName("spectrometerGroup")
        main_layout = QVBoxLayout()

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

        # Integration time control
        integ_layout = QHBoxLayout()
        integ_label = QLabel("Integration Time (ms):")
        integ_label.setStyleSheet("font-weight: bold;")
        integ_layout.addWidget(integ_label)
        self.integ_spinbox = QSpinBox()
        self.integ_spinbox.setRange(1, 4000)
        self.integ_spinbox.setValue(50)
        self.integ_spinbox.setSingleStep(10)
        integ_layout.addWidget(self.integ_spinbox)

        self.apply_btn = QPushButton("Apply Settings")
        self.apply_btn.setEnabled(False)
        self.apply_btn.clicked.connect(self.update_measurement_settings)
        integ_layout.addWidget(self.apply_btn)
        main_layout.addLayout(integ_layout)

        # Cycles and repetitions controls
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

        # Initialize the plot
        pg.setConfigOption('background', '#252525')
        pg.setConfigOption('foreground', '#e0e0e0')
        pg.setConfigOption('antialias', False)
        pg.setConfigOption('useOpenGL', True)
        self.plot_px = pg.PlotWidget()
        self.plot_px.setXRange(0, 2048)  # default range, will adjust after connect
        self.plot_px.setLabel('bottom', 'Pixel', '')
        self.plot_px.setLabel('left', 'Count', '')
        self.plot_px.getViewBox().enableAutoRange(ViewBox.YAxis, True)
        self.plot_px.getViewBox().setAutoVisible(y=True)
        self.plot_px.showGrid(x=True, y=True, alpha=0.3)
        x_axis = self.plot_px.getAxis('bottom')
        x_ticks = [(i, str(i)) for i in range(0, 2049, 100)]
        x_axis.setTicks([x_ticks])
        self.curve_px = self.plot_px.plot([], [], pen=pg.mkPen('#f44336', width=2),
                                          fillLevel=0, fillBrush=pg.mkBrush(244, 67, 54, 50),
                                          name="Pixel Counts", skipFiniteCheck=True, antialias=False)
        main_layout.addWidget(self.plot_px)
        self.groupbox.setLayout(main_layout)

        # Internal state variables
        self._ready = False
        self.handle = None
        self.wls = []
        self.intens = []
        self.npix = 0

        # Rewire toggle button if parent provides a data saving method
        if parent is not None:
            try:
                self.toggle_btn.clicked.disconnect(self.toggle)
            except Exception:
                pass
            if hasattr(parent, 'toggle_data_saving'):
                self.toggle_btn.clicked.connect(parent.toggle_data_saving)

        # Ensure data directory exists
        self.csv_dir = "data"
        os.makedirs(self.csv_dir, exist_ok=True)

        # Start timer for live plot updates
        self.plot_timer = QTimer(self)
        self.plot_timer.timeout.connect(self._update_plot)
        self.plot_timer.start(50)  # 20 Hz updates

        self.static_curves = []

        # Automatically attempt connect on startup (after a short delay)
        QTimer.singleShot(500, self.connect)

    def connect(self):
        # Indicate connection attempt in UI
        self.status_signal.emit("Connecting to spectrometer...")
        is_auto_connect = hasattr(self, '_auto_connect') and self._auto_connect
        try:
            handle, wavelengths, num_pixels, serial_str = connect_spectrometer()
        except Exception as e:
            error_msg = f"Connection failed: {e}"
            self.status_signal.emit(error_msg)
            if is_auto_connect:
                self.status_signal.emit("Will retry connection in 5 seconds...")
                QTimer.singleShot(5000, self.connect)
            return

        self.handle = handle
        # Save wavelengths (if numpy array, convert to list)
        self.wls = wavelengths.tolist() if isinstance(wavelengths, np.ndarray) else wavelengths
        self.npix = num_pixels
        self._ready = True

        # Adjust x-axis range and ticks to match the spectrometer pixel count
        self.plot_px.setXRange(0, self.npix)
        x_axis = self.plot_px.getAxis('bottom')
        x_ticks = [(i, str(i)) for i in range(0, self.npix + 1, 100)]
        x_axis.setTicks([x_ticks])

        # Check if connected spectrometer is Hamamatsu or Avantes
        if hasattr(self.handle, 'spec_type') and getattr(self.handle, 'spec_type', "") == 'Hama3':
            # Hamamatsu connected – no high-res ADC toggle available
            self.start_btn.setEnabled(True)
            self.status_signal.emit(f"Spectrometer ready (Hamamatsu SN={serial_str})")
        else:
            # Avantes connected – attempt to enable high-res ADC if supported
            if hasattr(self, 'high_res_adc') and self.high_res_adc:
                try:
                    from drivers.avaspec import AVS_UseHighResAdc
                    AVS_UseHighResAdc(self.handle, True)
                    self.status_signal.emit("High-resolution ADC mode enabled")
                except Exception as e:
                    self.status_signal.emit(f"Could not enable high-res ADC: {e}")
            self.start_btn.setEnabled(True)
            self.status_signal.emit(f"Spectrometer ready (SN={serial_str})")

        # Clear auto-connect flag after a successful connection
        if hasattr(self, '_auto_connect'):
            self._auto_connect = False

    def start(self):
        if not self._ready:
            self.status_signal.emit("Spectrometer not ready")
            return

        # Fetch current settings from UI
        integration_time = float(self.integ_spinbox.value())
        cycles = self.cycles_spinbox.value()
        repetitions = self.repetitions_spinbox.value()

        # If using Hamamatsu spectrometer:
        if hasattr(self.handle, 'spec_type') and getattr(self.handle, 'spec_type', "") == 'Hama3':
            # Apply integration time to device
            res = self.handle.set_it(integration_time)
            if res != "OK":
                self.status_signal.emit(f"Failed to set integration time: {res}")
                return
            # Note: Hamamatsu uses cycles for internal averaging; we use `repetitions` for loop count
            self.status_signal.emit(f"Starting measurement (Int: {integration_time}ms, Cycles: {cycles})")
            self.measure_active = True
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.apply_btn.setEnabled(True)
            # Run measurement loop in background thread
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
                        self.handle.wait_for_measurement()
                        if self.handle.rcm is None or len(self.handle.rcm) != self.handle.npix_active:
                            print("⚠️ Warning: Skipped a frame due to empty or invalid data (possible saturation).")
                        else:
                            # Check for saturation
                            if np.max(self.handle.rcm) >= 65000:
                                print(f"⚠️ Warning: Possible saturation detected (max count = {int(np.max(self.handle.rcm))})")
                            data = self.handle.rcm
                            max_pixels = self.npix
                            full = [0.0] * max_pixels
                            data_to_use = data[:max_pixels] if len(data) > max_pixels else data
                            full[:len(data_to_use)] = list(data_to_use)
                            self.intens = full
                        count += 1
                    # If a finite number of repetitions were set and completed, stop measurement
                    if self.measure_active and repetitions > 1 and count >= total_loops:
                        self.measure_active = False
                        QTimer.singleShot(0, self._on_stop)
                except Exception as e:
                    print(f"Exception in Hamamatsu measurement loop: {e}")
            self._hama_thread = threading.Thread(target=_hama_loop, daemon=True)
            self._hama_thread.start()
            return

        # If using Avantes spectrometer:
        # Determine averages for Avantes based on integration time
        if integration_time < 10:
            averages = 10
        elif integration_time < 100:
            averages = 5
        elif integration_time < 1000:
            averages = 2
        else:
            averages = 1

        self.current_integration_time_us = integration_time
        self.status_signal.emit(f"Starting measurement (Int: {integration_time}ms, Avg: {averages}, Cycles: {cycles}, Rep: {repetitions})")

        code = prepare_measurement(self.handle, self.npix,
                                   integration_time_ms=integration_time,
                                   averages=averages,
                                   cycles=cycles,
                                   repetitions=repetitions)
        if code != 0:
            self.status_signal.emit(f"Prepare error: {code}")
            return

        self.measure_active = True
        self.cb = AVS_MeasureCallbackFunc(self._cb)
        err = AVS_MeasureCallback(self.handle, self.cb, -1)
        if err != 0:
            self.status_signal.emit(f"Callback error: {err}")
            self.measure_active = False
            return

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.apply_btn.setEnabled(True)
        self.status_signal.emit("Measurement started")

    def _cb(self, p_data, p_user):
        # Callback for Avantes spectrometer data
        status_code = p_user[0]
        if status_code == 0:
            _, data = AVS_GetScopeData(self.handle)
            # Copy data up to the number of pixels
            max_pixels = self.npix
            full = [0.0] * max_pixels
            data_to_use = data[:max_pixels] if len(data) > max_pixels else data
            full[:len(data_to_use)] = data_to_use
            self.intens = full
            # Pass integration time to parent if needed
            if hasattr(self, 'current_integration_time_us'):
                if hasattr(self, 'parent') and self.parent is not None and not callable(self.parent):
                    self.parent.current_integration_time_us = self.current_integration_time_us
            # Enable saving buttons after first data arrives
            self.save_btn.setEnabled(True)
            self.toggle_btn.setEnabled(True)
        else:
            self.status_signal.emit(f"Spectrometer error code {status_code}")

    def _update_plot(self):
        """Refresh the plot with latest intensity data."""
        if not hasattr(self, 'intens') or not self.intens:
            return
        try:
            intensities = np.array(self.intens)
            pixel_indices = np.arange(len(intensities))
            # Downsample if needed for performance
            if hasattr(self, 'downsample_factor') and self.downsample_factor > 1:
                step = self.downsample_factor
                intensities = intensities[::step]
                pixel_indices = pixel_indices[::step]
            self.curve_px.setData(pixel_indices, intensities)
            # Adjust Y-axis range occasionally to fit new data
            if not hasattr(self, '_range_update_counter'):
                self._range_update_counter = 0
            self._range_update_counter += 1
            if self._range_update_counter >= 10:
                self._range_update_counter = 0
                if intensities.size > 0 and np.max(intensities) > 0:
                    max_y = float(np.max(intensities)) * 1.1
                    if hasattr(self, 'static_curves') and self.static_curves:
                        for curve in self.static_curves:
                            if curve.yData is not None and len(curve.yData) > 0:
                                curve_max = float(np.max(curve.yData))
                                if curve_max > max_y:
                                    max_y = curve_max * 1.1
                    self.plot_px.setYRange(0, max_y)
        except Exception as e:
            print(f"Plot update error: {e}")
            # In case of error, skip this update

    def stop(self):
        if not hasattr(self, 'measure_active') or not self.measure_active:
            return
        self.measure_active = False
        # Handle stopping based on spectrometer type
        if hasattr(self.handle, 'spec_type') and getattr(self.handle, 'spec_type', "") == 'Hama3':
            try:
                self.handle.abort()
            except Exception as e:
                print(f"Hamamatsu abort error: {e}")
            if hasattr(self, '_hama_thread'):
                if self._hama_thread.is_alive():
                    self._hama_thread.join(timeout=1.0)
                self._hama_thread = None
            # Reset UI states via common handler
            self._on_stop()
            return
        # For Avantes, use StopMeasureThread to stop the callback-based measurement
        th = StopMeasureThread(self.handle, parent=self)
        th.finished_signal.connect(self._on_stop)
        th.start()

    def _on_stop(self):
        # Called when a measurement loop has stopped (either manually or via callback)
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.apply_btn.setEnabled(False)
        self.status_signal.emit("Measurement stopped")

    def save(self):
        ts = QDateTime.currentDateTime().toString("yyyyMMdd_hhmmss")
        path = os.path.join(self.csv_dir, f"snapshot_{ts}.csv")
        try:
            with open(path, 'w') as f:
                f.write("Pixel,Intensity\n")
                for i, inten in enumerate(self.intens):
                    if inten != 0:
                        f.write(f"{i},{inten:.4f}\n")
            self.status_signal.emit(f"Saved snapshot to {path}")
        except Exception as e:
            self.status_signal.emit(f"Save error: {e}")

    def toggle(self):
        # This is overridden by MainWindow if a parent is provided; default behavior toggles button text
        if hasattr(self, 'toggle_btn'):
            current_text = self.toggle_btn.text()
            if current_text == "Start Saving":
                self.toggle_btn.setText("Stop Saving")
            else:
                self.toggle_btn.setText("Start Saving")
        self.status_signal.emit("Continuous-save not yet implemented")

    def is_ready(self):
        return self._ready

    def update_measurement_settings(self):
        """Apply new integration time/cycle settings. If measuring, restart measurement with new settings."""
        if not self._ready:
            self.status_signal.emit("Spectrometer not ready")
            return

        # Read new settings from UI
        integration_time = float(self.integ_spinbox.value())
        cycles = self.cycles_spinbox.value()
        repetitions = self.repetitions_spinbox.value()

        # Compute averages for Avantes (for informational message)
        if integration_time < 10:
            averages = 10
        elif integration_time < 100:
            averages = 5
        elif integration_time < 1000:
            averages = 2
        else:
            averages = 1

        # Update any data logging timers based on new integration time
        self._update_data_collection_timers(integration_time)

        if hasattr(self, 'measure_active') and self.measure_active:
            self.status_signal.emit("Stopping measurement to update settings...")
            # If currently measuring:
            if hasattr(self.handle, 'spec_type') and getattr(self.handle, 'spec_type', "") == 'Hama3':
                # Stop Hamamatsu measurement loop
                self.measure_active = False
                try:
                    self.handle.abort()
                except Exception as e:
                    print(f"Hamamatsu abort error (update settings): {e}")
                if hasattr(self, '_hama_thread'):
                    if self._hama_thread.is_alive():
                        self._hama_thread.join(timeout=1.0)
                    self._hama_thread = None
                # Apply new integration time on device
                res = self.handle.set_it(integration_time)
                if res != "OK":
                    self.status_signal.emit(f"Settings update error: {res}")
                    return
                # Restart measurement with updated settings
                self.status_signal.emit(f"Settings updated (Int: {integration_time}ms, Avg: {averages}, Cycles: {cycles}, Rep: {repetitions})")
                self.start()
                return
            else:
                # For Avantes, stop current measurement and then apply settings
                th = StopMeasureThread(self.handle, parent=self)
                th.finished_signal.connect(lambda: self._apply_new_settings(integration_time, averages, cycles, repetitions))
                th.start()
        else:
            # If not currently measuring, just update the integration time (and prepare Avantes if needed)
            if hasattr(self.handle, 'spec_type') and getattr(self.handle, 'spec_type', "") == 'Hama3':
                res = self.handle.set_it(integration_time)
                if res != "OK":
                    self.status_signal.emit(f"Settings update error: {res}")
                    return
                self.status_signal.emit(f"Settings updated (Int: {integration_time}ms, Cycles: {cycles}, Rep: {repetitions})")
            else:
                code = prepare_measurement(self.handle, self.npix,
                                           integration_time_ms=integration_time,
                                           averages=averages,
                                           cycles=cycles,
                                           repetitions=repetitions)
                if code != 0:
                    self.status_signal.emit(f"Settings update error: {code}")
                    return
                self.status_signal.emit(f"Settings updated (Int: {integration_time}ms, Avg: {averages}, Cycles: {cycles}, Rep: {repetitions})")

    def _update_data_collection_timers(self, integration_time_ms):
        """Adjust data collection intervals if continuous saving is active."""
        if hasattr(self, 'parent') and self.parent is not None:
            if hasattr(self.parent, 'data_logger') and getattr(self.parent.data_logger, 'continuous_saving', False):
                # Ensure at least 100ms collection interval
                collection_interval = max(100, int(integration_time_ms))
                save_interval = int(integration_time_ms + 200)
                if hasattr(self.parent, 'data_timer'):
                    self.parent.data_timer.setInterval(collection_interval)
                if hasattr(self.parent, 'save_timer'):
                    self.parent.save_timer.setInterval(save_interval)
                if hasattr(self.parent, 'data_logger'):
                    self.parent.data_logger.collection_interval = collection_interval
                    self.parent.data_logger.save_interval = save_interval
                self.status_signal.emit(f"Updated data collection interval to {collection_interval}ms")

    def _apply_new_settings(self, integration_time, averages, cycles, repetitions):
        """(Avantes only) Callback to restart measurement with new settings after stopping."""
        if hasattr(self, 'parent') and self.parent is not None and not callable(self.parent):
            setattr(self.parent, '_integration_changing', True)
        code = prepare_measurement(self.handle, self.npix,
                                   integration_time_ms=integration_time,
                                   averages=averages,
                                   cycles=cycles,
                                   repetitions=repetitions)
        if code != 0:
            self.status_signal.emit(f"Settings update error: {code}")
            return
        self.cb = AVS_MeasureCallbackFunc(self._cb)
        err = AVS_MeasureCallback(self.handle, self.cb, -1)
        if err != 0:
            self.status_signal.emit(f"Callback error on restart: {err}")
            self.measure_active = False
            return
        self.measure_active = True
        self.stop_btn.setEnabled(True)
        self.status_signal.emit(f"Settings updated (Int: {integration_time}ms, Avg: {averages}, Cycles: {cycles}, Rep: {repetitions})")
        if hasattr(self, 'parent') and self.parent is not None and not callable(self.parent):
            if hasattr(self.parent, '_integration_changing'):
                QTimer.singleShot(int(integration_time * 2),
                                  lambda: setattr(self.parent, '_integration_changing', False))
