import serial
import time

class Filterwheel:
    """
    Driver for a generic filterwheel.
    """
    def __init__(self, port, baudrate=9600):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.position = -1

    def connect(self):
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=1)
            time.sleep(2) # Wait for device to initialize
            if self.ser.is_open:
                # Optionally send a command to verify connection
                # self.ser.write(b'ID?\n')
                # response = self.ser.readline().decode().strip()
                # if "Filterwheel" in response:
                return "Connected"
            else:
                return "Failed to open port"
        except serial.SerialException as e:
            return f"Error: {e}"
        return "Connected" # Placeholder

    def send_command(self, command):
        if not self.ser or not self.ser.is_open:
            return "Not connected"
        try:
            self.ser.write(command.encode() + b'\n')
            response = self.ser.readline().decode().strip()
            return response
        except Exception as e:
            return f"Command error: {e}"

    def set_position(self, position):
        # Example command: "pos=1"
        response = self.send_command(f"pos={position}")
        if "OK" in response:
            self.position = position
        return response

    def get_position(self):
        # Example command: "pos?"
        response = self.send_command("pos?")
        try:
            # Assuming response is "pos=X"
            self.position = int(response.split('=')[1])
            return self.position
        except:
            return -1

    def disconnect(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
