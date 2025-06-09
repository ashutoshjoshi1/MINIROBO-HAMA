import os
import csv
from datetime import datetime
from PyQt5.QtCore import QObject, pyqtSignal

class DataLogger(QObject):
    """
    Handles logging of messages and data to files.
    """
    log_message = pyqtSignal(str)

    def __init__(self, log_dir="logs", data_dir="data"):
        super().__init__()
        self.log_dir = log_dir
        self.data_dir = data_dir
        os.makedirs(self.log_dir, exist_ok=True)
        os.makedirs(self.data_dir, exist_ok=True)

        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file_path = os.path.join(self.log_dir, f"log_{self.timestamp}.txt")
        self.data_file_path = os.path.join(self.data_dir, f"Scans_{self.timestamp}.csv")
        self.sensor_file_path = os.path.join(self.data_dir, f"Sensors_{self.timestamp}.csv")

        self.log(f"--- Log started at {self.timestamp} ---")

    def log(self, message):
        """Logs a message to the console, the GUI, and a file."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        print(log_entry)
        self.log_message.emit(log_entry)
        with open(self.log_file_path, 'a') as f:
            f.write(log_entry + '\n')

    def log_scan(self, scan_data, metadata):
        """Logs spectrometer scan data to a CSV file."""
        try:
            with open(self.data_file_path, 'a', newline='') as f:
                writer = csv.writer(f)
                # Write header if the file is new/empty
                if f.tell() == 0:
                    header = list(metadata.keys()) + [f"pixel_{i}" for i in range(len(scan_data))]
                    writer.writerow(header)
                
                row = list(metadata.values()) + list(scan_data)
                writer.writerow(row)
            self.log(f"Scan data saved to {self.data_file_path}")
        except Exception as e:
            self.log(f"Error saving scan data: {e}")

    def log_sensor(self, sensor_name, data_dict):
        """Logs generic sensor data to a CSV file."""
        try:
            with open(self.sensor_file_path, 'a', newline='') as f:
                writer = csv.writer(f)
                timestamp = datetime.now().isoformat()
                
                # Write header if file is empty
                if f.tell() == 0:
                    header = ['timestamp', 'sensor_name'] + list(data_dict.keys())
                    writer.writerow(header)
                    
                row = [timestamp, sensor_name] + list(data_dict.values())
                writer.writerow(row)
        except Exception as e:
            self.log(f"Error saving sensor data for {sensor_name}: {e}")
