# spec_xfus.py

"""
This stub satisfies the `import spec_xfus` in hama3_spectrometer.py
and lets you load the Hamamatsu DLL without touching the original file.
"""

import os
import ctypes

class HamaDLL:
    def __init__(self, dll_path):
        if not os.path.isfile(dll_path):
            raise FileNotFoundError(f"No such DLL: {dll_path}")
        # On Windows use WinDLL (stdcall), otherwise generic CDLL
        loader = ctypes.WinDLL if os.name == 'nt' else ctypes.CDLL
        self._dll = loader(dll_path)

    def __getattr__(self, name):
        try:
            return getattr(self._dll, name)
        except AttributeError:
            raise AttributeError(f"Function '{name}' not found in DLL")

def Initialize(dll_path):
    """
    Load the Hamamatsu Hama3 DLL and return a wrapper with all its functions.
    Called by hama3_spectrometer.py as:
        dll = spec_xfus.Initialize(self.dll_path)
    """
    return HamaDLL(dll_path)
