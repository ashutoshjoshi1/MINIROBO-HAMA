
import os
import sys
import ctypes
import numpy as np
import importlib.util
from PyQt5.QtCore import QThread, pyqtSignal

# Avantes SDK imports
from avaspec import (
    AVS_Init, AVS_Done, AVS_UpdateUSBDevices, AVS_GetList,
    AvsIdentityType, AVS_Activate, AVS_GetParameter, AVS_GetLambda,
    AVS_PrepareMeasure, AVS_MeasureCallbackFunc, AVS_MeasureCallback,
    AVS_StopMeasure, AVS_Deactivate
)

# Dynamic Hamamatsu driver loader
Hama3_Spectrometer = None
hama_paths = [
    os.path.join(os.path.dirname(__file__), 'hama3_spectrometer.py'),
    os.path.join(os.path.dirname(__file__), '..', 'hama3_spectrometer.py'),
    os.path.join(os.path.dirname(__file__), '..', 'spec_hama3', 'hama3_spectrometer.py')
]
for p in hama_paths:
    try:
        if os.path.isfile(p):
            spec = importlib.util.spec_from_file_location('hama3', p)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            Hama3_Spectrometer = mod.Hama3_Spectrometer
            print(f"Loaded Hamamatsu driver from {p}")
            break
    except Exception:
        continue

class StopMeasureThread(QThread):
    finished_signal = pyqtSignal()
    def __init__(self, handle, parent=None):
        super().__init__(parent)
        self.handle = handle
    def run(self):
        try:
            AVS_StopMeasure(self.handle)
        except Exception:
            pass
        self.finished_signal.emit()


def detect_spectrometer():
    # Try Hamamatsu first
    if Hama3_Spectrometer:
        try:
            inst = Hama3_Spectrometer()
            return 'Hama3', inst
        except Exception:
            pass
    # Fallback to Avantes
    try:
        ret = AVS_Init(0)
        if ret <= 0:
            AVS_Done()
            raise RuntimeError
        devs = AVS_UpdateUSBDevices()
        if devs < 1:
            AVS_Done()
            raise RuntimeError
        lst = AVS_GetList(devs)
        if not lst:
            AVS_Done()
            raise RuntimeError
        aid = AvsIdentityType()
        aid.SerialNumber = lst[0].SerialNumber
        aid.UserFriendlyName = b"\x00"
        aid.Status = b"\x01"
        handle = AVS_Activate(aid)
        return 'Avantes', handle
    except Exception:
        raise RuntimeError("No spectrometer found.")