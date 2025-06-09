from PyQt5.QtCore import QObject, QThread, pyqtSignal
from drivers.thp_sensor import THPSensor

class THPController(QObject):
    """
    Controller for the THP sensor.
    """
    thp_data = pyqtSignal(dict)
    thp_status = pyqtSignal(str)

    def __init__(self, port):
        super().__init__()
        self.thp_sensor = THPSensor(port)
        self.thread = QThread()
        self.moveToThread(self.thread)
        self.thread.started.connect(self.connect_thp_sensor)

    def start(self):
        self.thread.start()

    def connect_thp_sensor(self):
        """
        Connects to the THP sensor.
        """
        status = self.thp_sensor.connect()
        self.thp_status.emit(status)

    def get_data(self):
        """
        Gets data from the THP sensor.
        """
        data = self.thp_sensor.get_data()
        self.thp_data.emit(data)

    def disconnect(self):
        """
        Disconnects from the THP sensor.
        """
        self.thp_sensor.disconnect()
        self.thread.quit()