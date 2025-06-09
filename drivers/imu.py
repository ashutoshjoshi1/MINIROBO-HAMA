import serial
import time
import random # For placeholder data

class IMU:
    """
    Driver for a generic IMU.
    """
    def __init__(self, port, baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self.ser = None

    def connect(self):
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=1)
            if self.ser.is_open:
                return "Connected"
        except serial.SerialException as e:
            return f"Error: {e}"
        return "Connected" # Placeholder

    def get_data(self):
        """
        Reads and parses data from the IMU.
        Expected format: "roll,pitch,yaw"
        """
        # Placeholder data generation
        return {
            "roll": random.uniform(-90, 90),
            "pitch": random.uniform(-90, 90),
            "yaw": random.uniform(0, 360)
        }

        # Real implementation
        if not self.ser or not self.ser.is_open:
            return {}
        try:
            # Send command to request data if needed
            # self.ser.write(b'data?\n')
            line = self.ser.readline().decode().strip()
            parts = line.split(',')
            if len(parts) == 3:
                return {
                    "roll": float(parts[0]),
                    "pitch": float(parts[1]),
                    "yaw": float(parts[2]),
                }
        except Exception as e:
            print(f"IMU read error: {e}")
            return {}
        return {}


    def disconnect(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
