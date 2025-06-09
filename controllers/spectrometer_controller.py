# controllers/spectrometer_controller.py

from PyQt5.QtCore import QObject, pyqtSignal, QTimer, QDateTime
from PyQt5.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QSpinBox
)
import pyqtgraph as pg
from pyqtgraph import ViewBox
import numpy as np
import os
import threading
import time

from drivers.spectrometer import (
    connect_spectrometer,
    AVS_GetScopeData, StopMeasureThread,
    prepare_measurement,
    start_measurement
)

class SpectrometerController(QObject):
    """
    Controller for the spectrometer section of the GUI.
    Handles connecting, starting/stopping measurements, live plotting, and saving data.
    """

    status_signal = pyqtSignal(str)

    @property
    def is_ready(self):
        """True once a spectrometer has been successfully connected."""
        return getattr(self, '_ready', False)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent

        # --- UI Setup ---
        self.groupbox = QGroupBox("Spectrometer")
        main_layout = QVBoxLayout()

        # Buttons: Connect / Start / Stop / Save
        btn_layout = QHBoxLayout()
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.connect)
        btn_layout.addWidget(self.connect_btn)

        self.start_btn = QPushButton("Start")
        self.start_btn.setEnabled(False)
        self.start_btn.clicked.connect(self.start)
        btn_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop)
        btn_layout.addWidget(self.stop_btn)

        self.save_btn = QPushButton("Save Spectrum")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self.save)
        btn_layout.addWidget(self.save_btn)
        main_layout.addLayout(btn_layout)

        # Integration time setting
        integ_layout = QHBoxLayout()
        integ_layout.addWidget(QLabel("Integration Time (ms):"))
        self.integ_spinbox = QSpinBox()
        self.integ_spinbox.setRange(1, 10000)
        self.integ_spinbox.setValue(5)
        self.integ_spinbox.setSingleStep(5)
        integ_layout.addWidget(self.integ_spinbox)
        self.apply_btn = QPushButton("Apply Settings")
        self.apply_btn.setEnabled(False)
        self.apply_btn.clicked.connect(self.update_measurement_settings)
        integ_layout.addWidget(self.apply_btn)
        main_layout.addLayout(integ_layout)

        # Plot setup
        pg.setConfigOption('background', '#252525')
        pg.setConfigOption('foreground', '#e0e0e0')
        self.plot_px = pg.PlotWidget()
        self.plot_px.setLabel('bottom', 'Pixel')
        self.plot_px.setLabel('left', 'Intensity (Counts)')
        self.plot_px.getViewBox().enableAutoRange(ViewBox.YAxis, True)
        self.plot_px.showGrid(x=True, y=True, alpha=0.3)
        self.curve_px = self.plot_px.plot(
            pen=pg.mkPen('#f44336', width=2)
        )
        main_layout.addWidget(self.plot_px)
        self.groupbox.setLayout(main_layout)

        # Internal state
        self._ready = False
        self.handle = None
        self.npix = 0
        self.intens = np.array([])
        self.measure_active = False
        self._auto_connect = True
        self._is_hama = False
        self._measurement_thread = None

        # Ensure data dir exists
        self.csv_dir = "data"
        os.makedirs(self.csv_dir, exist_ok=True)

        # Plot update timer
        self.plot_timer = QTimer(self)
        self.plot_timer.timeout.connect(self._update_plot)
        
        # Auto-connect on startup
        QTimer.singleShot(500, self.connect)


    def connect(self):
        """Auto-detect and connect to a spectrometer."""
        if self.is_ready:
            self.status_signal.emit("Already connected.")
            return
        self.status_signal.emit("Connecting to spectrometer...")
        try:
            handle, wls, num_pixels, serial = connect_spectrometer()
        except Exception as e:
            self.status_signal.emit(f"Connection failed: {e}")
            if self._auto_connect:
                QTimer.singleShot(5000, self.connect) # Retry after 5s
            return

        self.handle = handle
        self.npix = num_pixels
        self._ready = True
        self._auto_connect = False
        self.connect_btn.setText("Disconnect")
        self.connect_btn.clicked.disconnect()
        self.connect_btn.clicked.connect(self.disconnect)

        self._is_hama = hasattr(self.handle, 'spec_type') and self.handle.spec_type == 'hama'

        self.plot_px.setXRange(0, self.npix, padding=0)
        
        self.start_btn.setEnabled(True)
        self.apply_btn.setEnabled(self._is_hama) # Only enable apply for Hamamatsu for now
        spec_type = "Hamamatsu" if self._is_hama else "Avantes"
        self.status_signal.emit(f"{spec_type} spectrometer ready (SN={serial})")


    def start(self):
        """Begin live measurement and plotting."""
        if not self._ready or self.measure_active:
            return

        self.measure_active = True
        self.plot_timer.start(50)

        if self._is_hama:
            self._start_hama()
        else:
            self._start_avantes()

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.apply_btn.setEnabled(False)


    def _start_hama(self):
        """Start measurement loop for Hamamatsu."""
        self.status_signal.emit("Starting Hamamatsu measurement...")
        self.update_measurement_settings()
        
        def measurement_loop():
            while self.measure_active:
                try:
                    res = self.handle.measure(ncy=1)
                    if res != "OK":
                        self.status_signal.emit(f"Hama measure failed: {res}")
                        break
                    self.handle.wait_for_measurement()
                    data = self.handle.rcm
                    if data is not None and len(data) >= self.npix:
                        self.intens = np.array(data[:self.npix], dtype=float)
                        if not self.save_btn.isEnabled():
                            # Use QTimer to safely update UI from thread
                            QTimer.singleShot(0, lambda: self.save_btn.setEnabled(True))
                    time.sleep(0.001) # Small delay to prevent busy-waiting
                except Exception as e:
                    self.status_signal.emit(f"Hama measurement error: {e}")
                    break
            # When loop finishes, signal the main thread to stop
            if self.measure_active:
                 QTimer.singleShot(0, self.stop)

        self._measurement_thread = threading.Thread(target=measurement_loop, daemon=True)
        self._measurement_thread.start()


    def _start_avantes(self):
        """Start measurement loop for Avantes."""
        self.status_signal.emit("Starting Avantes measurement...")
        itime = float(self.integ_spinbox.value())
        averages = 1
        if itime <= 10: averages = 10
        elif itime <= 100: averages = 5
        
        code = prepare_measurement(self.handle, self.npix, itime, averages)
        if code != 0:
            self.status_signal.emit(f"Avantes Prepare error: {code}")
            self.stop()
            return

        err = start_measurement(self.handle, self._avantes_callback, -1)
        if err != 0:
            self.status_signal.emit(f"Avantes start error: {err}")
            self.stop()
            return

    def _avantes_callback(self, handle_ptr, error_code_ptr):
        """Avantes SDK callback—stores latest intensity array."""
        if not self.measure_active:
            return

        if error_code_ptr[0] == 0:
            err, data = AVS_GetScopeData(self.handle)
            if err == 0:
                self.intens = np.array(data[:self.npix], dtype=float)
                if not self.save_btn.isEnabled():
                    QTimer.singleShot(0, lambda: self.save_btn.setEnabled(True))
        else:
            self.status_signal.emit(f"Avantes measurement error code {error_code_ptr[0]}")


    def _update_plot(self):
        """Refresh the pyqtgraph plot with the newest data."""
        if self.intens.size > 0:
            self.curve_px.setData(self.intens)


    def stop(self):
        """Stop any ongoing measurement."""
        if not self.measure_active:
            return
            
        self.measure_active = False
        self.plot_timer.stop()

        if self._is_hama:
            try:
                self.handle.abort()
            except Exception as e:
                print(f"Ignoring error during Hamamatsu abort: {e}")
            # Thread will exit on its own
            self._on_stop_complete()
        else: # Avantes
            stopper = StopMeasureThread(self.handle, parent=self)
            stopper.finished_signal.connect(self._on_stop_complete)
            stopper.start()

    def _on_stop_complete(self):
        """Reset UI once measurement finishes."""
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.apply_btn.setEnabled(self._is_hama)
        self.status_signal.emit("Measurement stopped.")


    def save(self):
        """Save current spectrum to a CSV file."""
        if self.intens.size == 0:
            self.status_signal.emit("No data to save.")
            return
        ts = QDateTime.currentDateTime().toString("yyyyMMdd_hhmmss")
        fn = os.path.join(self.csv_dir, f"spectrum_{ts}.csv")
        try:
            header = "Pixel,Intensity"
            np.savetxt(fn, np.c_[np.arange(self.npix), self.intens], delimiter=',', header=header, comments='')
            self.status_signal.emit(f"Spectrum saved to: {os.path.basename(fn)}")
        except Exception as e:
            self.status_signal.emit(f"Save failed: {e}")


    def update_measurement_settings(self):
        """Apply new integration time (for Hamamatsu)."""
        if not self._ready or not self._is_hama:
            if self.measure_active:
                self.status_signal.emit("Settings can only be changed for Hamamatsu while running.")
            return

        new_it = float(self.integ_spinbox.value())
        try:
            res = self.handle.set_it(new_it)
            if res == "OK":
                self.status_signal.emit(f"Integration time set to {new_it} ms")
            else:
                self.status_signal.emit(f"Failed to set IT: {res}")
        except Exception as e:
            self.status_signal.emit(f"Error setting IT: {e}")


    def disconnect(self):
        """Disconnects the spectrometer and resets the UI."""
        if self.measure_active:
            self.stop()
        
        if self._ready:
            if self._is_hama:
                self.handle.disconnect()
            else: # Avantes
                from drivers.spectrometer import AVS_Deactivate, AVS_Done
                AVS_Deactivate(self.handle)
                AVS_Done()
        
        self.handle = None
        self._ready = False
        self.intens = np.array([])
        
        self.connect_btn.setText("Connect")
        if not self.connect_btn.receivers(self.connect_btn.clicked):
            self.connect_btn.clicked.connect(self.connect)

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.apply_btn.setEnabled(False)
        self.save_btn.setEnabled(False)
        self.status_signal.emit("Spectrometer disconnected.")
