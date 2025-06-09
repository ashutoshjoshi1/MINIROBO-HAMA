from PyQt5.QtCore import QObject, pyqtSignal, QTimer
import numpy as np
from drivers.spectrometer import detect_spectrometer, StopMeasureThread

class Hama3SpectrometerController(QObject):
    status = pyqtSignal(str)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.handle = None
        self.npix = 0
        self.data = []
        self._active = False
    def connect(self):
        spec_type, inst = detect_spectrometer()
        if spec_type!='Hama3': raise RuntimeError("Not Hamamatsu")
        self.handle = inst
        self.npix = inst.npix_active
        self.status.emit("Hamamatsu connected")
    def start(self, it_ms=5, cycles=1):
        self.handle.set_it(it_ms)
        self._active=True
        def loop():
            while self._active:
                self.handle.measure(ncy=cycles)
                self.handle.wait_for_measurement()
                r = self.handle.rcm
                self.data = list(r[:self.npix])
        import threading; threading.Thread(target=loop,daemon=True).start()
    def stop(self):
        self._active=False
    def read(self):
        return np.array(self.data)