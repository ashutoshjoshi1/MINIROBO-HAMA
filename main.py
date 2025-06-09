import sys
import json
from PyQt5.QtWidgets import QApplication
from gui.main_window import MainWindow

def main():
    # Load hardware configuration
    try:
        with open('hardware_config.json', 'r') as f:
            config = json.load(f)
    except FileNotFoundError:
        print("Error: hardware_config.json not found.")
        # Create a default config for the user
        config = {
            "spectrometer": {
                "type": "avantes",
                "dll_path": "path/to/your/avaspecx64.dll",
                "sn": "your_serial_number"
            }
        }
        with open('hardware_config.json', 'w') as f:
            json.dump(config, f, indent=4)
        print("A default hardware_config.json has been created. Please edit it with your hardware details.")
        return

    spectrometer_config = config.get('spectrometer', {})
    spec_type = spectrometer_config.get('type', 'avantes')
    dll_path = spectrometer_config.get('dll_path')
    # Get other spectrometer-specific parameters
    spec_kwargs = {k: v for k, v in spectrometer_config.items() if k not in ['type', 'dll_path']}


    app = QApplication(sys.argv)
    main_window = MainWindow(
        spectrometer_type=spec_type,
        spectrometer_dll_path=dll_path,
        spectrometer_kwargs=spec_kwargs
    )
    main_window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()