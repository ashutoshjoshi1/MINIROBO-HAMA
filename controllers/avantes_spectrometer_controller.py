from PyQt5.QtCore import QObject, pyqtSignal, QTimer
import numpy as np
from drivers.spectrometer import detect_spectrometer, prepare_measurement, StopMeasureThread

class AvantesSpectrometerController(QObject):
    status = pyqtSignal(str)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.handle=None; self.npix=0; self.data=[]; self._active=False
    def connect(self):
        stype, h = detect_spectrometer()
        if stype!='Avantes': raise RuntimeError("Not Avantes")
        self.handle=h
        self.npix = h.m_Detector_m_NrPixels
        self.status.emit("Avantes connected")
    def start(self, it_ms=50, avg=1, cycles=1):
        code=prepare_measurement(self.handle,self.npix,it_ms,avg,cycles,1)
        self._active=True
        from drivers.spectrometer import AVS_MeasureCallbackFunc, AVS_MeasureCallback, AVS_GetScopeData
        cb=AVS_MeasureCallbackFunc(self._cb)
        AVS_MeasureCallback(self.handle,cb,-1)
    def _cb(self,p,u):
        ok,data=AVS_GetScopeData(self.handle)
        self.data=list(data[:self.npix]); self.status.emit("Frame")
    def stop(self):
        StopMeasureThread(self.handle).start()
    def read(self):
        return np.array(self.data)