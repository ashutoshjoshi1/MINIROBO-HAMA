import json
import importlib
from utils import get_project_root
import logging

class SpectrometerController:
    """
    Controller to manage different spectrometer devices.
    It acts as a factory to load the correct driver based on the hardware configuration.
    """
    def __init__(self, *args, **kwargs):
        self._spectrometer = None
        self.config = self._load_config()
        self._load_driver()

    def _load_config(self):
        """Loads the spectrometer configuration from the main hardware config file."""
        root = get_project_root()
        config_path = f"{root}/hardware_config.json"
        try:
            with open(config_path) as f:
                config = json.load(f)
            return config.get("spectrometer", {})
        except FileNotFoundError:
            logging.error(f"Hardware config file not found at {config_path}")
            return {}

    def _load_driver(self):
        """Dynamically imports and instantiates the spectrometer driver."""
        spec_type = self.config.get("type")
        if not spec_type:
            logging.error("Spectrometer 'type' not specified in hardware_config.json")
            return

        # Mapping of spectrometer types to their driver module and class names
        spec_map = {
            "hamamatsu": ("drivers.hamamatsu_spectrometer", "HamaSpectrometer"),
            "avantes": ("drivers.avantes_spectrometer", "AvantesSpectrometer"),
            "xfus": ("drivers.xfus_spectrometer", "XfusSpectrometer")
        }

        if spec_type not in spec_map:
            logging.error(f"Unknown spectrometer type '{spec_type}' in config.")
            return

        try:
            module_name, class_name = spec_map[spec_type]
            spec_module = importlib.import_module(module_name)
            SpecClass = getattr(spec_module, class_name)
            
            # Instantiate the driver, passing its specific config
            self._spectrometer = SpecClass(config=self.config)
            logging.info(f"Successfully loaded '{spec_type}' spectrometer driver.")

        except ImportError as e:
            logging.error(f"Error importing spectrometer driver for '{spec_type}': {e}")
        except AttributeError:
            logging.error(f"Class '{class_name}' not found in module '{module_name}'.")
        except Exception as e:
            logging.error(f"An unexpected error occurred while loading the spectrometer: {e}")

    # --- Delegate methods to the loaded driver ---

    def connect(self):
        """Connects to the loaded spectrometer."""
        if self._spectrometer:
            return self._spectrometer.connect()
        logging.warning("Cannot connect: no spectrometer driver loaded.")
        return False

    def disconnect(self):
        """Disconnects from the loaded spectrometer."""
        if self._spectrometer:
            self._spectrometer.disconnect()
        else:
            logging.warning("Cannot disconnect: no spectrometer driver loaded.")
    
    def get_spectrum(self, *args, **kwargs):
        """Gets a spectrum from the loaded spectrometer."""
        if self._spectrometer:
            return self._spectrometer.get_spectrum(*args, **kwargs)
        logging.warning("Cannot get spectrum: no spectrometer driver loaded.")
        return None, None

    def set_integration_time(self, time_ms):
        """Sets integration time on the loaded spectrometer."""
        if self._spectrometer:
            self.config['integration_time'] = time_ms
            self._spectrometer.set_integration_time(time_ms)
        else:
            logging.warning("Cannot set integration time: no spectrometer driver loaded.")
    
    def get_wavelengths(self):
        """Gets wavelengths from the loaded spectrometer."""
        if self._spectrometer:
            return self._spectrometer.get_wavelengths()
        logging.warning("Cannot get wavelengths: no spectrometer driver loaded.")
        return []

    @property
    def is_connected(self):
        """Returns the connection status of the loaded spectrometer."""
        if self._spectrometer:
            return self._spectrometer.is_connected
        return False

