from PyQt5.QtCore import QObject, QThread, pyqtSignal
from drivers.motor import Motor

class MotorController(QObject):
    """
    Controller for the motor.
    """
    motor_response = pyqtSignal(str)
    motor_position = pyqtSignal(dict)
    motor_status = pyqtSignal(str)

    def __init__(self, port):
        super().__init__()
        self.motor = Motor(port)
        self.thread = QThread()
        self.moveToThread(self.thread)
        self.thread.started.connect(self.connect_motor)

    def start(self):
        self.thread.start()

    def connect_motor(self):
        """
        Connects to the motor.
        """
        status = self.motor.connect()
        self.motor_status.emit(status)

    def move_absolute(self, axis, position):
        """
        Moves the motor to an absolute position.
        """
        response = self.motor.move_absolute(axis, position)
        self.motor_response.emit(response)
        self.get_position()

    def move_relative(self, axis, distance):
        """
        Moves the motor by a relative distance.
        """
        response = self.motor.move_relative(axis, distance)
        self.motor_response.emit(response)
        self.get_position()

    def get_position(self):
        """
        Gets the current position of the motor.
        """
        position = self.motor.get_position()
        self.motor_position.emit(position)

    def stop(self):
        """
        Stops the motor.
        """
        response = self.motor.stop()
        self.motor_response.emit(response)
        self.get_position()

    def disconnect(self):
        """
        Disconnects from the motor.
        """
        self.motor.disconnect()
        self.thread.quit()