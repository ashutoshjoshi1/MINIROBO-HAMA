from PyQt5.QtCore import QObject, QThread, pyqtSignal
from drivers.filterwheel import Filterwheel

class FilterwheelController(QObject):
    """
    Controller for the filterwheel.
    """
    filterwheel_response = pyqtSignal(str)
    filterwheel_position = pyqtSignal(int)
    filterwheel_status = pyqtSignal(str)

    def __init__(self, port):
        super().__init__()
        self.filterwheel = Filterwheel(port)
        self.thread = QThread()
        self.moveToThread(self.thread)
        self.thread.started.connect(self.connect_filterwheel)

    def start(self):
        self.thread.start()

    def connect_filterwheel(self):
        """
        Connects to the filterwheel.
        """
        status = self.filterwheel.connect()
        self.filterwheel_status.emit(status)
        if status == "Connected":
            self.get_position()

    def set_position(self, position):
        """
        Sets the position of the filterwheel.
        """
        response = self.filterwheel.set_position(position)
        self.filterwheel_response.emit(response)
        self.get_position()

    def get_position(self):
        """
        Gets the current position of the filterwheel.
        """
        position = self.filterwheel.get_position()
        self.filterwheel_position.emit(position)

    def disconnect(self):
        """
        Disconnects from the filterwheel.
        """
        self.filterwheel.disconnect()
        self.thread.quit()