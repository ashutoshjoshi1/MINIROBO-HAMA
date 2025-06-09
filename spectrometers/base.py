from abc import ABC, abstractmethod

class BaseSpectrometer(ABC):
    """
    Abstract base class for all spectrometers.
    """

    @abstractmethod
    def connect(self):
        """Connects to the spectrometer."""
        pass

    @abstractmethod
    def disconnect(self):
        """Disconnects from the spectrometer."""
        pass

    @abstractmethod
    def set_integration_time(self, time_ms):
        """Sets the integration time in milliseconds."""
        pass

    @abstractmethod
    def measure(self, ncy=1):
        """
        Performs a measurement.

        :param ncy: Number of cycles to measure.
        :return: Measured data.
        """
        pass

    @abstractmethod
    def get_wavelengths(self):
        """
        Returns the wavelength calibration for the spectrometer.
        :return: A list or numpy array of wavelengths.
        """
        pass