import json
import logging
import os
import threading
import time

import numpy as np
import pyqtgraph as pg
from PyQt5.QtCore import QDateTime, QObject, QTimer, pyqtSignal
from PyQt5.QtWidgets import (QCheckBox, QGroupBox, QHBoxLayout, QLabel,
                               QPushButton, QSpinBox, QVBoxLayout)
from pyqtgraph import ViewBox

from drivers.spectrometer import SpectrometerDriver

logger = logging.getLogger(__name__)


class SpectrometerController(QObject):
    status_signal = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.groupbox = QGroupBox("Spectrometer")
        self.groupbox.setObjectName("spectrometerGroup")
        main_layout = QVBoxLayout()

        # --- UI Elements ---
        btn_layout = QHBoxLayout()
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setStyleSheet("font-weight: bold; font-size: 11pt;")
        self.connect_btn.clicked.connect(self.connect)
        btn_layout.addWidget(self.connect_btn)

        self.start_stop_btn = QPushButton("Start")
        self.start_stop_btn.setStyleSheet("font-weight: bold; font-size: 11pt;")
        self.start_stop_btn.setCheckable(True)
        self.start_stop_btn.setEnabled(False)
        self.start_stop_btn.clicked.connect(self.toggle_measurement)
        btn_layout.addWidget(self.start_stop_btn)

        self.save_btn = QPushButton("Save")
        self.save_btn.setStyleSheet("font-weight: bold; font-size: 11pt;")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self.save)
        btn_layout.addWidget(self.save_btn)

        self.toggle_btn = QPushButton("Start Saving")
        self.toggle_btn.setStyleSheet("font-weight: bold; font-size: 11pt;")
        self.toggle_btn.setEnabled(False)
        if parent:
            self.toggle_btn.clicked.connect(parent.toggle_data_saving)
        btn_layout.addWidget(self.toggle_btn)

        main_layout.addLayout(btn_layout)

        integ_layout = QHBoxLayout()
        integ_label = QLabel("Integration Time (ms):")
        integ_label.setStyleSheet("font-weight: bold;")
        integ_layout.addWidget(integ_label)
        self.integ_spinbox = QSpinBox()
        self.integ_spinbox.setRange(1, 4000)
        self.integ_spinbox.setValue(50)
        self.integ_spinbox.setSingleStep(10)
        integ_layout.addWidget(self.integ_spinbox)
        main_layout.addLayout(integ_layout)

        cycles_label = QLabel("Cycles (for saving):")
        cycles_label.setStyleSheet("font-weight: bold;")
        cycles_layout = QHBoxLayout()
        cycles_layout.addWidget(cycles_label)
        self.cycles_spinbox = QSpinBox()
        self.cycles_spinbox.setRange(1, 1000)
        self.cycles_spinbox.setValue(1)
        cycles_layout.addWidget(self.cycles_spinbox)
        main_layout.addLayout(cycles_layout)

        # --- Plotting ---
        pg.setConfigOption("background", "#252525")
        pg.setConfigOption("foreground", "#e0e0e0")
        pg.setConfigOption("antialias", False)
        self.plot_px = pg.PlotWidget()
        self.plot_px.setLabel("bottom", "Pixel", "")
        self.plot_px.setLabel("left", "Count", "")
        self.plot_px.getViewBox().enableAutoRange(ViewBox.YAxis, True)
        self.plot_px.showGrid(x=True, y=True, alpha=0.3)
        self.curve_px = self.plot_px.plot([], [], pen=pg.mkPen("#f44336", width=2))
        main_layout.addWidget(self.plot_px)
        self.groupbox.setLayout(main_layout)

        # --- Internal State & Driver ---
        self._ready = False
        self.is_running = False
        self.intens = []
        self.driver = SpectrometerDriver()
        self.driver.initialize_spec_logger()

        # Load config for driver
        try:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            config_path = os.path.join(base_dir, "hardware_config.json")
            with open(config_path, "r") as f:
                config = json.load(f).get("spectrometer", {})
                self.driver.dll_path = config.get("dll_path", "")
                self.driver.sn = config.get("sn", "")
                self.driver.npix_active = config.get("npix_active", 4096)
                if self.driver.dll_path and not os.path.isabs(self.driver.dll_path):
                    self.driver.dll_path = os.path.join(base_dir, self.driver.dll_path)
        except FileNotFoundError:
             self.status_signal.emit(f"ERROR: hardware_config.json not found at {config_path}")
        except Exception as e:
            self.status_signal.emit(f"Error loading spectrometer config: {e}")

        self.csv_dir = "data"
        os.makedirs(self.csv_dir, exist_ok=True)

        self.plot_timer = QTimer(self)
        self.plot_timer.timeout.connect(self._update_plot)
        self.plot_timer.start(50)  # 20 Hz

        QTimer.singleShot(500, self.connect)

    def connect(self):
        if not self.driver.dll_path:
            self.status_signal.emit("ERROR: Spectrometer DLL path not configured!")
            return
        self.status_signal.emit("Connecting to Hamamatsu spectrometer...")
        threading.Thread(target=self._connect_thread, daemon=True).start()

    def _connect_thread(self):
        try:
            res = self.driver.connect()
            if res == "OK":
                self._ready = True
                self.npix = self.driver.npix_active
                self.plot_px.setXRange(0, self.npix)
                self.start_stop_btn.setEnabled(True)
                self.status_signal.emit(f"Hamamatsu Spectrometer ready (SN={self.driver.sn})")
            else:
                self._ready = False
                self.status_signal.emit(f"Hamamatsu connection failed: {res}")
        except Exception as e:
            self._ready = False
            self.status_signal.emit(f"Connection exception: {e}")

    def toggle_measurement(self, checked):
        if checked:
            self.start()
        else:
            self.stop()

    def start(self):
        if not self._ready or self.is_running:
            return

        self.is_running = True
        self.start_stop_btn.setText("Stop")
        self.status_signal.emit("Starting continuous measurement...")
        threading.Thread(target=self._measure_thread, daemon=True).start()
        self.save_btn.setEnabled(True)
        self.toggle_btn.setEnabled(True)


    def stop(self):
        if not self.is_running:
            return

        self.is_running = False
        self.driver.abort() # Abort any waiting measurement
        self.start_stop_btn.setText("Start")
        self.status_signal.emit("Measurement stopped.")


    def _measure_thread(self):
        """Continuously measures, applying settings from the UI in a loop."""
        while self.is_running:
            try:
                # Get current settings from UI for each cycle
                integration_time = float(self.integ_spinbox.value())
                cycles = 1 # Always measure 1 cycle in continuous mode

                res = self.driver.set_it(integration_time)
                if res != "OK":
                    self.status_signal.emit(f"Failed to set IT: {res}")
                    time.sleep(0.1) # Avoid busy-looping on error
                    continue

                res = self.driver.measure(ncy=cycles)
                if res != "OK":
                    self.status_signal.emit(f"Failed to start measurement: {res}")
                    time.sleep(0.1)
                    continue

                # This blocks until one cycle is done
                self.driver.wait_for_measurement()

            except Exception as e:
                self.status_signal.emit(f"Measurement error: {e}")
                self.is_running = False # Stop on error

        # Ensure button is reset on the main thread when loop finishes
        QTimer.singleShot(0, lambda: self.start_stop_btn.setChecked(False))
        QTimer.singleShot(0, self.stop)


    def _update_plot(self):
        if not self._ready:
            return

        # Use the last successfully measured cycle for the plot
        data_to_plot = self.driver.last_cycle_data
        if data_to_plot is not None and len(data_to_plot) > 0:
            try:
                self.intens = data_to_plot.tolist()
                self.curve_px.setData(data_to_plot)
            except Exception as e:
                logger.error(f"Plot update error: {e}")

    def save(self):
        # In continuous mode, save the most recent spectrum
        if self.intens is None or len(self.intens) == 0:
            self.status_signal.emit("No data to save.")
            return

        ts = QDateTime.currentDateTime().toString("yyyyMMdd_hhmmss")
        path = os.path.join(self.csv_dir, f"snapshot_{ts}.csv")
        try:
            data_to_save = np.array(self.intens)
            np.savetxt(
                path,
                np.c_[np.arange(len(data_to_save)), data_to_save],
                delimiter=",",
                header="Pixel,Intensity",
                fmt="%d,%.4f",
            )
            self.status_signal.emit(f"Saved snapshot to {path}")
        except Exception as e:
            self.status_signal.emit(f"Save error: {e}")

    def is_ready(self):
        return self._ready