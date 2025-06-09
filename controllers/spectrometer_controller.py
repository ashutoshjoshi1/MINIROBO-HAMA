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
        # Store parent reference properly
        self.parent = parent
        
        # Group box UI
        self.groupbox = QGroupBox("Spectrometer")
        self.groupbox.setObjectName("spectrometerGroup")
        main_layout = QVBoxLayout()
        
        # Control buttons with larger font and bold text
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
        
        # Integration time controls with bold labels
        integ_layout = QHBoxLayout()

        integ_label = QLabel("Integration Time (ms):")
        integ_label.setStyleSheet("font-weight: bold;")
        integ_layout.addWidget(integ_label)

        self.integ_spinbox = QSpinBox()
        self.integ_spinbox.setRange(1, 4000)  # 1ms to 4s
        self.integ_spinbox.setValue(50)  # Default 50ms
        self.integ_spinbox.setSingleStep(10)
        integ_layout.addWidget(self.integ_spinbox)

        # Add the Apply Settings button
        self.apply_btn = QPushButton("Apply Settings")
        self.apply_btn.setEnabled(False)
        self.apply_btn.clicked.connect(self.update_measurement_settings)
        integ_layout.addWidget(self.apply_btn)

        main_layout.addLayout(integ_layout)

        # Cycles and repetitions controls with bold labels
        cycles_layout = QHBoxLayout()

        cycles_label = QLabel("Cycles:")
        cycles_label.setStyleSheet("font-weight: bold;")
        cycles_layout.addWidget(cycles_label)

        self.cycles_spinbox = QSpinBox()
        self.cycles_spinbox.setRange(1, 100)  # 1 to 100 cycles
        self.cycles_spinbox.setValue(1)  # Default 1 cycle
        self.cycles_spinbox.setSingleStep(1)
        cycles_layout.addWidget(self.cycles_spinbox)

        repetitions_label = QLabel("Repetitions:")
        repetitions_label.setStyleSheet("font-weight: bold;")
        cycles_layout.addWidget(repetitions_label)

        self.repetitions_spinbox = QSpinBox()
        self.repetitions_spinbox.setRange(1, 100)  # 1 to 100 repetitions
        self.repetitions_spinbox.setValue(1)  # Default 1 repetition
        self.repetitions_spinbox.setSingleStep(1)
        cycles_layout.addWidget(self.repetitions_spinbox)

        main_layout.addLayout(cycles_layout)

        # Optimize graph performance
        pg.setConfigOption('background', '#252525')
        pg.setConfigOption('foreground', '#e0e0e0')
        pg.setConfigOption('antialias', False)  # Disable antialiasing for better performance
        pg.setConfigOption('useOpenGL', True)   # Use OpenGL for rendering if available
        
        # Only show Pixel vs Count plot for better performance
        self.plot_px = pg.PlotWidget()
        # Set fixed range for x-axis (0-2048 pixels)
        self.plot_px.setXRange(0, 2048)
        self.plot_px.setLabel('bottom', 'Pixel', '')
        self.plot_px.setLabel('left', 'Count', '')
        # Enable auto-range only for y-axis
        self.plot_px.getViewBox().enableAutoRange(ViewBox.YAxis, True)
        self.plot_px.getViewBox().setAutoVisible(y=True)
        self.plot_px.showGrid(x=True, y=True, alpha=0.3)

        # Configure x-axis ticks to show 0, 100, 200, etc.
        x_axis = self.plot_px.getAxis('bottom')
        x_ticks = [(i, str(i)) for i in range(0, 2049, 100)]
        x_axis.setTicks([x_ticks])

        # Add a more attractive style with optimized rendering
        self.curve_px = self.plot_px.plot([], [], pen=pg.mkPen('#f44336', width=2),
                                         fillLevel=0, fillBrush=pg.mkBrush(244, 67, 54, 50),
                                         name="Pixel Counts", 
                                         skipFiniteCheck=True,  # Skip finite check for better performance
                                         antialias=False)       # Disable antialiasing for this curve
        
        # Add the plot widget to the groupbox layout
        main_layout.addWidget(self.plot_px)
        self.groupbox.setLayout(main_layout)

        # Internal state
        self._ready = False
        self.handle = None
        self.wls = []
        self.intens = []
        self.npix = 0

        # Ensure parent MainWindow's toggle_data_saving is used if parent exists
        if parent is not None:
            try:
                self.toggle_btn.clicked.disconnect(self.toggle)
            except Exception:
                pass
            self.toggle_btn.clicked.connect(parent.toggle_data_saving)

        # Data directory for snapshots
        self.csv_dir = "data"
        os.makedirs(self.csv_dir, exist_ok=True)

        # Timer for updating plot - increase frequency for faster updates
        self.plot_timer = QTimer(self)
        self.plot_timer.timeout.connect(self._update_plot)
        self.plot_timer.start(50)  # update plot at 20 Hz (was 200ms/5Hz)

        # Add downsampling for plots - reduce for better resolution
        self.downsample_factor = 1  # No downsampling for better resolution (was 2)

        # Add new attributes
        self.driver = SpectrometerDriver()
        self.active_spectrometers = {}  # Track multiple spectrometers
        self.watchdog_timer = QTimer()
        self.watchdog_timer.timeout.connect(self._check_measurement_status)
        self.watchdog_timer.start(1000)  # Check every second
        
        # Add high-resolution ADC mode flag
        self.high_res_adc = True

    def connect(self):
        # Emit status for feedback
        self.status_signal.emit("Connecting to spectrometer...")
        try:
            handle, wavelengths, num_pixels, serial_str = connect_spectrometer()
        except Exception as e:
            self.status_signal.emit(f"Connection failed: {e}")
            return
        self.handle = handle
        # Store wavelength calibration and number of pixels
        self.wls = wavelengths.tolist() if isinstance(wavelengths, np.ndarray) else wavelengths
        self.npix = num_pixels
        self._ready = True
        
        # Enable high-resolution ADC mode if available
        if hasattr(self, 'high_res_adc') and self.high_res_adc:
            try:
                from drivers.avaspec import AVS_UseHighResAdc
                AVS_UseHighResAdc(self.handle, True)
                self.status_signal.emit("High-resolution ADC mode enabled")
            except Exception as e:
                self.status_signal.emit(f"Could not enable high-res ADC: {e}")
        
        # Enable measurement start once connected
        self.start_btn.setEnabled(True)
        self.status_signal.emit(f"Spectrometer ready (SN={serial_str})")

    def start(self):
        if not self._ready:
            self.status_signal.emit("Spectrometer not ready")
            return
        
        # Get integration time from UI
        integration_time = float(self.integ_spinbox.value())
        
        # Get cycles and repetitions from UI
        cycles = self.cycles_spinbox.value()
        repetitions = self.repetitions_spinbox.value()
        
        # Calculate averages based on integration time
        # For shorter integration times, use more averages to improve signal quality
        # For longer integration times, use fewer averages to maintain responsiveness
        if integration_time < 10:
            averages = 10  # More averages for very short integration times
        elif integration_time < 100:
            averages = 5   # Medium averages for short integration times
        elif integration_time < 1000:
            averages = 2   # Few averages for medium integration times
        else:
            averages = 1   # No averaging for long integration times
        
        # Store current integration time for data saving
        self.current_integration_time_us = integration_time
        
        # Update status with current settings
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
        self.apply_btn.setEnabled(True)  # Enable the apply button when measurement starts
        self.status_signal.emit("Measurement started")

    def _cb(self, p_data, p_user):
        # Spectrometer driver callback (on new scan)
        status_code = p_user[0]
        if status_code == 0:
            _, data = AVS_GetScopeData(self.handle)
            # Ensure intensities list has correct length (up to 2048)
            max_pixels = min(2048, self.npix)
            full = [0.0] * max_pixels
            # Copy only the data we need (up to 2048 pixels)
            data_to_use = data[:max_pixels] if len(data) > max_pixels else data
            full[:len(data_to_use)] = data_to_use
            self.intens = full
            
            # Make sure integration time is accessible to MainWindow
            if hasattr(self, 'current_integration_time_us'):
                # Make it accessible to parent (MainWindow)
                if hasattr(self, 'parent') and self.parent is not None:
                    if not callable(self.parent):  # Check if parent is not a method
                        self.parent.current_integration_time_us = self.current_integration_time_us
            
            # Enable snapshot save and continuous save after first data received
            self.save_btn.setEnabled(True)
            self.toggle_btn.setEnabled(True)
        else:
            self.status_signal.emit(f"Spectrometer error code {status_code}")

    def _update_plot(self):
        """Update the plots with intensity data, optimized for performance"""
        if not self.intens:
            return
        
        try:
            # Get the data arrays - use numpy for better performance
            intensities = np.array(self.intens)
            
            # Create pixel indices array
            pixel_indices = np.arange(len(intensities))
            
            # Apply downsampling to reduce points plotted if needed
            if hasattr(self, 'downsample_factor') and self.downsample_factor > 1:
                step = self.downsample_factor
                # Use numpy indexing for consistent slicing
                intensities = intensities[::step]
                pixel_indices = pixel_indices[::step]
            
            # Update pixel plot - this is now the only plot we maintain
            self.curve_px.setData(pixel_indices, intensities)
            
            # Auto-adjust y-axis range less frequently for better performance
            if not hasattr(self, '_range_update_counter'):
                self._range_update_counter = 0
            
            self._range_update_counter += 1
            if self._range_update_counter >= 10:  # Only update range every 10 cycles (was 5)
                self._range_update_counter = 0
                if len(intensities) > 0 and np.max(intensities) > 0:
                    # Add 10% padding to the top of the y-range
                    max_y = np.max(intensities) * 1.1
                    self.plot_px.setYRange(0, max_y)
        
        except Exception as e:
            # Log the error but don't crash
            print(f"Plot update error: {e}")
            # Try to recover by clearing the plots
            try:
                self.curve_px.setData([], [])
            except:
                pass

    def stop(self):
        if not hasattr(self, 'measure_active') or not self.measure_active:
            return
        self.measure_active = False
        th = StopMeasureThread(self.handle, parent=self)
        th.finished_signal.connect(self._on_stop)
        th.start()

    def _on_stop(self):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.apply_btn.setEnabled(False)  # Disable the apply button when measurement stops
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
        # This method is overridden by MainWindow if parent is provided.
        self.status_signal.emit("Continuous-save not yet implemented")

    def is_ready(self):
        return self._ready

    def update_measurement_settings(self):
        """Update measurement settings without stopping the current measurement"""
        if not self._ready:
            self.status_signal.emit("Spectrometer not ready")
            return
        
        # Get all settings from UI
        integration_time = float(self.integ_spinbox.value())
        cycles = self.cycles_spinbox.value()
        repetitions = self.repetitions_spinbox.value()
        
        # Calculate averages based on integration time
        if integration_time < 10:
            averages = 10
        elif integration_time < 100:
            averages = 5
        elif integration_time < 1000:
            averages = 2
        else:
            averages = 1
        
        # Store current integration time for data saving
        self.current_integration_time_us = integration_time
        
        # Update data collection timers if data logging is active
        self._update_data_collection_timers(integration_time)
        
        # If measurement is active, need to stop and restart with new settings
        if hasattr(self, 'measure_active') and self.measure_active:
            self.status_signal.emit("Stopping measurement to update settings...")
            
            # Use StopMeasureThread to properly stop the measurement
            th = StopMeasureThread(self.handle, parent=self)
            th.finished_signal.connect(lambda: self._apply_new_settings(integration_time, averages, cycles, repetitions))
            th.start()
        else:
            # Just prepare the measurement with new settings
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
        """Update data collection timers based on new integration time"""
        # Check if parent window has data logging active
        if hasattr(self, 'parent') and self.parent is not None:
            if hasattr(self.parent, 'data_logger') and hasattr(self.parent.data_logger, 'continuous_saving'):
                if self.parent.data_logger.continuous_saving:
                    # Ensure minimum interval of 100ms
                    collection_interval = max(100, int(integration_time_ms))
                    save_interval = int(integration_time_ms + 200)  # Add 200ms buffer
                    
                    # Update the timers if they exist
                    if hasattr(self.parent, 'data_timer'):
                        self.parent.data_timer.setInterval(collection_interval)
                    if hasattr(self.parent, 'save_timer'):
                        self.parent.save_timer.setInterval(save_interval)
                    
                    # Store the updated intervals
                    self.parent.data_logger.collection_interval = collection_interval
                    self.parent.data_logger.save_interval = save_interval
                    
                    self.status_signal.emit(f"Updated data collection interval to {collection_interval}ms")

    def _apply_new_settings(self, integration_time, averages, cycles, repetitions):
        """Helper to apply new settings after measurement has stopped"""
        # Set flag to indicate integration time is changing
        if hasattr(self, 'parent') and self.parent is not None:
            # Check if parent is actually an object and not a method
            if not callable(self.parent):  # Check if parent is not a method
                if not hasattr(self.parent, '_integration_changing'):
                    setattr(self.parent, '_integration_changing', True)
                else:
                    self.parent._integration_changing = True
            else:
                # Log the issue for debugging
                print("Warning: parent is a callable, not an object")
        
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
        
        # Add a delay before resetting the flag to ensure stable readings
        if hasattr(self, 'parent') and self.parent is not None and not callable(self.parent):
            if hasattr(self.parent, '_integration_changing'):
                # Convert integration_time to integer for QTimer.singleShot
                delay_ms = int(integration_time * 2)
                QTimer.singleShot(delay_ms, 
                                 lambda: setattr(self.parent, '_integration_changing', False))

    def connect_spectrometer(self, ispec=0):
        """Connect to a specific spectrometer by index"""
        success, message = self.driver.reset(ispec, ini=True)
        if success:
            self.active_spectrometers[ispec] = True
            self.status_signal.emit(message)
            # Update UI elements
            self.start_btn.setEnabled(True)
            return True
        else:
            self.status_signal.emit(message)
            return False

    def disconnect_spectrometer(self, ispec=0, free_resources=False):
        """Disconnect from a specific spectrometer"""
        success, message = self.driver.disconnect(ispec, dofree=free_resources)
        if success and ispec in self.active_spectrometers:
            del self.active_spectrometers[ispec]
        self.status_signal.emit(message)
        return success

    def set_integration_time(self, ispec=0, integration_time=50.0):
        """Set integration time for a specific spectrometer"""
        success, message = self.driver.set_it(ispec, integration_time)
        self.status_signal.emit(message)
        return success

    def start_measurement(self, ispec=0, cycles=1):
        """Start measurement on a specific spectrometer"""
        if ispec not in self.active_spectrometers:
            self.status_signal.emit(f"Spectrometer {ispec} not connected")
            return False
            
        # Get integration time from UI
        integration_time = float(self.integ_spinbox.value())
        
        # Set integration time
        self.set_integration_time(ispec, integration_time)
        
        # Start measurement
        success, message = self.driver.measure(ispec, ncy=cycles)
        self.status_signal.emit(message)
        
        if success:
            self.measure_active = True
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.apply_btn.setEnabled(True)
        
        return success

    def stop_measurement(self, ispec=0):
        """Stop measurement on a specific spectrometer"""
        if ispec not in self.active_spectrometers:
            return False
            
        if hasattr(self, 'measure_active') and self.measure_active:
            self.measure_active = False
            th = StopMeasureThread(self.driver.handles[ispec]['handle'], parent=self)
            th.finished_signal.connect(self._on_stop)
            th.start()
            return True
        return False

    def get_temperature(self, ispec=0, board_temp=False):
        """Get temperature from spectrometer"""
        success, message, temp = self.driver.get_temp(ispec, syst8i=board_temp)
        if success:
            self.status_signal.emit(f"Temperature: {temp:.1f}°C")
            return temp
        else:
            self.status_signal.emit(message)
            return None

    def _check_measurement_status(self):
        """Watchdog function to check measurement status"""
        for ispec in self.active_spectrometers:
            if ispec in self.driver.data_status:
                status = self.driver.data_status[ispec]
                
                if status == 'DATA_READY':
                    # Process new data
                    self._process_new_data(ispec)
                    
                elif status == 'ERROR':
                    # Handle error condition
                    error_level = self.driver.recovery_level.get(ispec, 0)
                    self.status_signal.emit(f"Spectrometer {ispec} error (level {error_level})")

    def _process_new_data(self, ispec):
        """Process new data from spectrometer"""
        if ispec in self.driver.handles and 'last_data' in self.driver.handles[ispec]:
            data = self.driver.handles[ispec]['last_data']
            
            # Update the data for plotting
            self.intens = data
            
            # Check for saturation
            if self.driver.handles[ispec].get('saturated', False):
                self.status_signal.emit("Warning: Detector saturation detected")
                
            # Reset data status to prevent reprocessing
            self.driver.data_status[ispec] = 'PROCESSED'
            
            # Enable snapshot save and continuous save after data received
            self.save_btn.setEnabled(True)
            self.toggle_btn.setEnabled(True)

    def enable_high_res_adc(self, enable=True):
        """Enable or disable high-resolution ADC mode"""
        self.high_res_adc = enable
        if self._ready and self.handle:
            try:
                from drivers.avaspec import AVS_UseHighResAdc
                AVS_UseHighResAdc(self.handle, enable)
                self.status_signal.emit(f"High-resolution ADC mode {'enabled' if enable else 'disabled'}")
                return True
            except Exception as e:
                self.status_signal.emit(f"Could not change ADC mode: {e}")
                return False
        return False

    def set_sync_mode(self, enable=False):
        """Enable or disable synchronous measurement mode"""
        if self._ready and self.handle:
            try:
                from drivers.avaspec import AVS_SetSyncMode
                AVS_SetSyncMode(self.handle, enable)
                self.status_signal.emit(f"Synchronous mode {'enabled' if enable else 'disabled'}")
                return True
            except Exception as e:
                self.status_signal.emit(f"Could not change sync mode: {e}")
                return False
        return False

    def plot_final_data(self, data):
        """Plot final data from a completed routine"""
        if not data or not isinstance(data, list):
            self.status_signal.emit("No valid data to plot")
            return
        
        try:
            import numpy as np
            # Create pixel indices array
            pixel_indices = np.arange(len(data))
            
            # Update the plot
            self.curve_px.setData(pixel_indices, data)
            
            # Update y-axis range
            if len(data) > 0 and max(data) > 0:
                max_y = max(data) * 1.1
                self.plot_px.setYRange(0, max_y)
            
            # Add timestamp to the plot title
            from PyQt5.QtCore import QDateTime
            timestamp = QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss")
            self.plot_px.setTitle(f"Final Scan - {timestamp}")
            
            # Enable save button to save this final plot
            self.save_btn.setEnabled(True)
            
            # Store the data as current intensities
            self.intens = data.copy()
            
            self.status_signal.emit(f"Plotted final data with peak value: {max(data):.1f}")
        except Exception as e:
            self.status_signal.emit(f"Error plotting final data: {e}")



