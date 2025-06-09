from PyQt5.QtCore import QObject, QThread, pyqtSignal
from drivers.tc36_25_driver import TC36_25

class TempController(QObject):
    """
    Controller for the temperature controller.
    """
    temp_data = pyqtSignal(dict)
    temp_status = pyqtSignal(str)

    def __init__(self, port):
        super().__init__()
        self.temp_controller = TC36_25(port)
        self.thread = QThread()
        self.moveToThread(self.thread)
        self.thread.started.connect(self.connect_temp_controller)

    def start(self):
        self.thread.start()

    def connect_temp_controller(self):
        """
        Connects to the temperature controller.
        """
        status = self.temp_controller.connect()
        self.temp_status.emit(status)

    def get_data(self):
        """
        Gets data from the temperature controller.
        """
        data = self.temp_controller.get_data()
        self.temp_data.emit(data)

    def set_temperature(self, temp):
        """
        Sets the temperature of the controller.
        """
        self.temp_controller.set_temperature(temp)

    def disconnect(self):
        """
        Disconnects from the temperature controller.
        """
        self.temp_controller.disconnect()
        self.thread.quit()