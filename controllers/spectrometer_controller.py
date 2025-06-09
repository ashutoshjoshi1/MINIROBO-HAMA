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

from drivers.spectrometer import (
    connect_spectrometer,
    AVS_MeasureCallback, AVS_MeasureCallbackFunc,
    AVS_GetScopeData, StopMeasureThread,
    prepare_measurement
)


class SpectrometerController(QObject):
    """
    Controller for the spectrometer section of the GUI.
    Handles connecting, starting/stopping measurements, live plotting, and saving data.
    """

    status_signal = pyqtSignal(str)

    def is_ready(self):
        """Return True once a spectrometer has been successfully connected."""
        return getattr(self, '_ready', False)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent

        # --- UI Setup ---
        self.groupbox = QGroupBox("Spectrometer")
        # Apply a minimal valid stylesheet to avoid parse errors
        self.groupbox.setStyleSheet(
            "QGroupBox { color: white; }"
            "QGroupBox::title { color: white; }"
            "QLabel { color: white; }"
            "QSpinBox { color: white; }"
            "QPushButton { color: white; }"
        )

        main_layout = QVBoxLayout()

        # Buttons: Connect / Start / Stop / Save / Toggle
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

        self.toggle_btn = QPushButton("Start Saving")
        self.toggle_btn.setEnabled(False)
        self.toggle_btn.clicked.connect(self.toggle)
        btn_layout.addWidget(self.toggle_btn)

        main_layout.addLayout(btn_layout)

        # Integration time setting
        integ_layout = QHBoxLayout()
        integ_layout.addWidget(QLabel("Integration Time (ms):"))
        self.integ_spinbox = QSpinBox()
        self.integ_spinbox.setRange(1, 4000)
        self.integ_spinbox.setValue(5)
        self.integ_spinbox.setSingleStep(5)
        integ_layout.addWidget(self.integ_spinbox)
        self.apply_btn = QPushButton("Apply Settings")
        self.apply_btn.setEnabled(False)
        self.apply_btn.clicked.connect(self.update_measurement_settings)
        integ_layout.addWidget(self.apply_btn)
        main_layout.addLayout(integ_layout)

        # Cycles & Repetitions
        cycles_layout = QHBoxLayout()
        cycles_layout.addWidget(QLabel("Cycles:"))
        self.cycles_spinbox = QSpinBox()
        self.cycles_spinbox.setRange(1, 100)
        self.cycles_spinbox.setValue(1)
        cycles_layout.addWidget(self.cycles_spinbox)
        cycles_layout.addWidget(QLabel("Repetitions:"))
        self.repetitions_spinbox = QSpinBox()
        self.repetitions_spinbox.setRange(1, 100)
        self.repetitions_spinbox.setValue(1)
        cycles_layout.addWidget(self.repetitions_spinbox)
        main_layout.addLayout(cycles_layout)

        # Plot setup
        pg.setConfigOption('background', '#252525')
        pg.setConfigOption('foreground', '#e0e0e0')
        pg.setConfigOption('antialias', False)
        pg.setConfigOption('useOpenGL', True)

        self.plot_px = pg.PlotWidget()
        self.plot_px.setLabel('bottom', 'Pixel')
        self.plot_px.setLabel('left', 'Count')
        self.plot_px.getViewBox().enableAutoRange(ViewBox.YAxis, True)
        self.plot_px.getViewBox().setAutoVisible(y=True)
        self.plot_px.showGrid(x=False, y=False)
        self.plot_px.setXRange(0, 2048)
        x_axis = self.plot_px.getAxis('bottom')
        ticks = [(i, str(i)) for i in range(0, 2049, 100)]
        x_axis.setTicks([ticks])

        self.curve_px = self.plot_px.plot(
            [], [],
            pen=pg.mkPen('#f44336', width=2),
            fillLevel=0,
            fillBrush=pg.mkBrush(244, 67, 54, 50),
            skipFiniteCheck=True
        )
        main_layout.addWidget(self.plot_px)

        self.groupbox.setLayout(main_layout)

        # Internal state
        self._ready = False
        self.handle = None
        self.npix = 0
        self.intens = []

        # Ensure data dir exists
        self.csv_dir = "data"
        os.makedirs(self.csv_dir, exist_ok=True)

        # Plot update timer
        self.plot_timer = QTimer(self)
        self.plot_timer.timeout.connect(self._update_plot)
        self.plot_timer.start(50)

        # Auto-connect on startup
        self._auto_connect = True
        QTimer.singleShot(500, self.connect)


    def connect(self):
        """Auto-detect and connect to Hamamatsu or Avantes spectrometer."""
        self.status_signal.emit("Connecting to spectrometer...")
        try:
            handle, wls, num_pixels, serial = connect_spectrometer()
        except Exception as e:
            self.status_signal.emit(f"Connection failed: {e}")
            if self._auto_connect:
                QTimer.singleShot(5000, self.connect)
            return

        self.handle = handle
        self.npix = num_pixels
        self._ready = True

        # Update X-axis
        self.plot_px.setXRange(0, self.npix)
        x_axis = self.plot_px.getAxis('bottom')
        ticks = [(i, str(i)) for i in range(0, self.npix+1, 100)]
        x_axis.setTicks([ticks])

        self.start_btn.setEnabled(True)
        self.apply_btn.setEnabled(True)
        self.status_signal.emit(f"Spectrometer ready (SN={serial})")
        self._auto_connect = False


    def start(self):
        """Begin live measurement and plotting."""
        if not self.is_ready():
            self.status_signal.emit("Spectrometer not ready")
            return

        itime = float(self.integ_spinbox.value())
        cycles = self.cycles_spinbox.value()
        reps = self.repetitions_spinbox.value()

        # Hamamatsu vs Avantes auto-detect by handle type
        if hasattr(self.handle, 'set_it'):
            # Hamamatsu
            if self.handle.set_it(itime) != "OK":
                self.status_signal.emit("Failed to set integration time")
                return
            self.status_signal.emit("Starting Hamamatsu measurement")
            self.measure_active = True
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)

            import threading
            def loop():
                count = 0
                while self.measure_active and (reps < 0 or count < reps):
                    if self.handle.measure(ncy=cycles) != "OK":
                        break
                    self.handle.wait_for_measurement()
                    data = self.handle.rcm
                    if data is not None and len(data) == self.handle.npix_active:
                        self.intens = list(data[:self.npix])
                    count += 1
                QTimer.singleShot(0, self._on_stop)

            self._thread = threading.Thread(target=loop, daemon=True)
            self._thread.start()
            return

        # Avantes
        averages = 1
        if itime < 10: averages = 10
        elif itime < 100: averages = 5
        elif itime < 1000: averages = 2

        self.status_signal.emit("Starting Avantes measurement")
        code = prepare_measurement(self.handle, self.npix, itime, averages, cycles, reps)
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


    def _cb(self, p_data, p_user):
        """Avantes callback—stores latest intensity array."""
        if p_user[0] == 0:
            _, data = AVS_GetScopeData(self.handle)
            arr = data[:self.npix] if len(data) >= self.npix else data + [0]*(self.npix-len(data))
            self.intens = list(arr)
            self.save_btn.setEnabled(True)
            self.toggle_btn.setEnabled(True)
        else:
            self.status_signal.emit(f"Measurement error code {p_user[0]}")


    def _update_plot(self):
        """Refresh the pyqtgraph plot with the newest data."""
        if not self.intens:
            return
        y = np.array(self.intens, dtype=float)
        x = np.arange(len(y))
        self.curve_px.setData(x, y)
        # Auto-scale Y occasionally
        if hasattr(self, '_yrange_counter'):
            self._yrange_counter += 1
        else:
            self._yrange_counter = 1
        if self._yrange_counter >= 10:
            self._yrange_counter = 0
            m = float(np.max(y)) * 1.1
            if m > 0:
                self.plot_px.setYRange(0, m)


    def stop(self):
        """Stop any ongoing measurement."""
        if not getattr(self, 'measure_active', False):
            return
        self.measure_active = False

        # Hamamatsu abort
        if hasattr(self.handle, 'abort'):
            try:
                self.handle.abort()
            except Exception:
                pass
            if hasattr(self, '_thread') and self._thread.is_alive():
                self._thread.join(timeout=1)
            self._on_stop()
            return

        # Avantes stop thread
        stopper = StopMeasureThread(self.handle, parent=self)
        stopper.finished_signal.connect(self._on_stop)
        stopper.start()


    def _on_stop(self):
        """Reset UI once measurement finishes."""
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_signal.emit("Measurement stopped")


    def save(self):
        """Save current spectrum to CSV."""
        if not self.intens:
            return
        ts = QDateTime.currentDateTime().toString("yyyyMMdd_hhmmss")
        fn = os.path.join(self.csv_dir, f"spectrum_{ts}.csv")
        try:
            with open(fn, 'w') as f:
                f.write("Pixel,Intensity\n")
                for i, v in enumerate(self.intens):
                    f.write(f"{i},{v}\n")
            self.status_signal.emit(f"Saved: {fn}")
        except Exception as e:
            self.status_signal.emit(f"Save failed: {e}")


    def toggle(self):
        """Placeholder for continuous saving toggle (connect to parent handler)."""
        pass


    def update_measurement_settings(self):
        """Apply new integration time or other settings mid-run if supported."""
        new_it = float(self.integ_spinbox.value())
        if hasattr(self.handle, 'set_it'):
            res = self.handle.set_it(new_it)
            if res == "OK":
                self.status_signal.emit(f"Integration time set to {new_it} ms")
            else:
                self.status_signal.emit(f"Failed to update IT: {res}")
        else:
            self.status_signal.emit("New settings will apply on next start")
