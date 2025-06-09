from PyQt5.QtCore import QObject, QThread, pyqtSignal
from drivers.imu import IMU

class IMUController(QObject):
    """
    Controller for the IMU.
    """
    imu_data = pyqtSignal(dict)
    imu_status = pyqtSignal(str)

    def __init__(self, port):
        super().__init__()
        self.imu = IMU(port)
        self.thread = QThread()
        self.moveToThread(self.thread)
        self.thread.started.connect(self.connect_imu)

    def start(self):
        self.thread.start()

    def connect_imu(self):
        """
        Connects to the IMU.
        """
        status = self.imu.connect()
        self.imu_status.emit(status)

    def get_data(self):
        """
        Gets data from the IMU.
        """
        data = self.imu.get_data()
        self.imu_data.emit(data)

    def disconnect(self):
        """
        Disconnects from the IMU.
        """
        self.imu.disconnect()
        self.thread.quit()