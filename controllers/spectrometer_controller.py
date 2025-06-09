from PyQt5.QtCore import QObject, pyqtSignal, QTimer, QDateTime
from PyQt5.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QSpinBox
)
import pyqtgraph as pg
import numpy as np
import os
from drivers.spectrometer import Spectrometer

class SpectrometerController(QObject):
    status_signal = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.spec = Spectrometer()
        self.connected = False
        self.npix = 2048  # Default, will update after connect
        self.intens = [0] * self.npix

        # --- UI Setup ---
        self.groupbox = QGroupBox("Spectrometer")
        main_layout = QVBoxLayout()

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

        self.save_btn = QPushButton("Save")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self.save)
        btn_layout.addWidget(self.save_btn)

        main_layout.addLayout(btn_layout)

        integ_layout = QHBoxLayout()
        integ_layout.addWidget(QLabel("Integration Time (ms):"))
        self.integ_spinbox = QSpinBox()
        self.integ_spinbox.setRange(1, 4000)
        self.integ_spinbox.setValue(50)
        integ_layout.addWidget(self.integ_spinbox)
        self.apply_btn = QPushButton("Apply")
        self.apply_btn.setEnabled(False)
        self.apply_btn.clicked.connect(self.update_settings)
        integ_layout.addWidget(self.apply_btn)
        main_layout.addLayout(integ_layout)

        # --- Plot Setup ---
        pg.setConfigOption('background', '#252525')
        pg.setConfigOption('foreground', '#e0e0e0')
        self.plot_px = pg.PlotWidget()
        self.curve_px = self.plot_px.plot([], [], pen=pg.mkPen('#f44336', width=2))
        self.plot_px.setLabel('bottom', 'Pixel')
        self.plot_px.setLabel('left', 'Count')
        self.plot_px.setXRange(0, self.npix)
        self.plot_px.showGrid(x=True, y=True, alpha=0.3)
        main_layout.addWidget(self.plot_px)
        self.groupbox.setLayout(main_layout)

        # --- Timer for live plotting ---
        self.plot_timer = QTimer(self)
        self.plot_timer.timeout.connect(self._update_plot)
        self.plot_timer.start(50)  # 20 FPS

        # --- Measurement polling timer ---
        self.meas_timer = QTimer(self)
        self.meas_timer.timeout.connect(self.poll_spectrum)

        # Data dir for saves
        self.csv_dir = "data"
        os.makedirs(self.csv_dir, exist_ok=True)

    def connect(self):
        self.status_signal.emit("Connecting...")
        ok = self.spec.connect()
        if ok:
            self.npix = self.spec.npix
            self.intens = [0] * self.npix
            self.plot_px.setXRange(0, self.npix)
            x_axis = self.plot_px.getAxis('bottom')
            x_ticks = [(i, str(i)) for i in range(0, self.npix + 1, 256)]
            x_axis.setTicks([x_ticks])
            self.connected = True
            self.start_btn.setEnabled(True)
            self.status_signal.emit(self.spec.status)
        else:
            self.status_signal.emit(self.spec.status)

    def start(self):
        if not self.connected:
            self.status_signal.emit("Not connected!")
            return
        integration_time = int(self.integ_spinbox.value())
        res = self.spec.set_it(integration_time)
        if res != "OK":
            self.status_signal.emit(f"Failed to set integration time: {res}")
            return
        self.status_signal.emit("Starting measurement...")
        self.save_btn.setEnabled(True)
        self.stop_btn.setEnabled(True)
        self.start_btn.setEnabled(False)
        self.apply_btn.setEnabled(False)
        self.meas_timer.start(100)

    def poll_spectrum(self):
        if not self.connected:
            return
        self.spec.measure()
        self.spec.wait_for_measurement()
        counts = self.spec.get_counts()
        if counts is not None and len(counts) == self.npix:
            self.intens = counts
        else:
            self.intens = [0] * self.npix

    def stop(self):
        self.meas_timer.stop()
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_signal.emit("Measurement stopped.")

    def _update_plot(self):
        if self.intens is not None and len(self.intens) == self.npix:
            x = np.arange(self.npix)
            y = np.array(self.intens)
            self.curve_px.setData(x, y)

    def save(self):
        ts = QDateTime.currentDateTime().toString("yyyyMMdd_hhmmss")
        path = os.path.join(self.csv_dir, f"spectrum_{ts}.csv")
        try:
            with open(path, 'w') as f:
                f.write("Pixel,Intensity\n")
                for i, inten in enumerate(self.intens):
                    f.write(f"{i},{inten:.4f}\n")
            self.status_signal.emit(f"Saved to {path}")
        except Exception as e:
            self.status_signal.emit(f"Save error: {e}")

    def update_settings(self):
        if not self.connected:
            return
        integration_time = int(self.integ_spinbox.value())
        res = self.spec.set_it(integration_time)
        if res != "OK":
            self.status_signal.emit(f"Failed to set integration time: {res}")
        else:
            self.status_signal.emit(f"Integration time set: {integration_time} ms")

    def is_ready(self):
        return self.connected
