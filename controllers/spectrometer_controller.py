from PyQt5.QtCore import QObject, QThread, pyqtSignal
from spectrometers.avantes import AvantesSpectrometer
from spectrometers.hamamatsu import HamamatsuSpectrometer
# Import other spectrometer classes here

class SpectrometerController(QObject):
    connection_status = pyqtSignal(str)
    measurement_ready = pyqtSignal(object)
    wavelengths_ready = pyqtSignal(object)

    def __init__(self, spec_type, dll_path, **kwargs):
        super().__init__()
        self.spectrometer = self._create_spectrometer(spec_type, dll_path, **kwargs)
        self.thread = QThread()
        self.moveToThread(self.thread)
        self.thread.started.connect(self.connect_spectrometer)

    def _create_spectrometer(self, spec_type, dll_path, **kwargs):
        spec_type = spec_type.lower()
        if spec_type == 'avantes':
            return AvantesSpectrometer(dll_path)
        elif spec_type == 'hamamatsu':
            return HamamatsuSpectrometer(dll_path, **kwargs)
        # Add other spectrometers here
        else:
            raise ValueError(f"Unknown spectrometer type: {spec_type}")

    def start(self):
        self.thread.start()

    def connect_spectrometer(self):
        status = self.spectrometer.connect()
        self.connection_status.emit(status)
        if status == "OK":
            wavelengths = self.spectrometer.get_wavelengths()
            self.wavelengths_ready.emit(wavelengths)

    def set_integration_time(self, time_ms):
        self.spectrometer.set_integration_time(time_ms)

    def take_measurement(self):
        data = self.spectrometer.measure()
        if data is not None:
            self.measurement_ready.emit(data)

    def disconnect(self):
        self.spectrometer.disconnect()
        self.thread.quit()
        self.thread.wait()