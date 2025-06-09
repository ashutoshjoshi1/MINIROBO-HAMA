import serial
import time

class Motor:
    """
    Driver for a generic 2-axis motor controller.
    """
    def __init__(self, port, baudrate=9600):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.position = {'za': 0.0, 'az': 0.0}

    def connect(self):
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=2)
            time.sleep(2)
            return "Connected" if self.ser.is_open else "Failed"
        except serial.SerialException as e:
            return f"Error: {e}"

    def send_command(self, command):
        if not self.ser or not self.ser.is_open:
            return "Not connected"
        try:
            self.ser.write(command.encode())
            # Wait for and read response
            response = self.ser.read_until().decode().strip()
            return response
        except Exception as e:
            return f"Command error: {e}"

    def move_absolute(self, axis, position):
        # Example command: ">AZ=180.0"
        cmd = f">{axis.upper()}={position:.2f}\r"
        return self.send_command(cmd)

    def move_relative(self, axis, distance):
        # This might require getting current position first
        # or a specific relative move command
        return "Not implemented"

    def get_position(self):
        # Example command: ">P"
        # Expected response: "ZA=XXX.XX,AZ=YYY.YY"
        response = self.send_command(">P\r")
        try:
            parts = response.split(',')
            za_part = parts[0].split('=')
            az_part = parts[1].split('=')
            self.position['za'] = float(za_part[1])
            self.position['az'] = float(az_part[1])
        except Exception:
             pass # Keep old values on error
        return self.position

    def stop(self):
        return self.send_command(">S\r")

    def disconnect(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
