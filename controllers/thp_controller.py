from PyQt5.QtCore import QObject, QTimer, pyqtSignal, Qt
from PyQt5.QtWidgets import QGroupBox, QLabel, QVBoxLayout, QHBoxLayout, QPushButton
from drivers.thp_sensor import read_thp_sensor_data

class THPController(QObject):
    status_signal = pyqtSignal(str)

    def __init__(self, port, parent=None):
        super().__init__(parent)
        self.port = port
        self.groupbox = QGroupBox("THP Sensor")
        self.groupbox.setObjectName("thpGroup")
        
        # Use vertical layout for more compact display
        layout = QVBoxLayout()
        layout.setSpacing(2)  # Reduce spacing
        
        # Top row with port and reconnect button
        top_row = QHBoxLayout()
        
        port_label = QLabel(f"Port: {port}")
        port_label.setStyleSheet("font-weight: bold;")
        top_row.addWidget(port_label)
        
        reconnect_btn = QPushButton("Reconnect")
        reconnect_btn.setMaximumWidth(80)
        reconnect_btn.clicked.connect(self.reconnect)
        top_row.addWidget(reconnect_btn)
        
        layout.addLayout(top_row)
        
        # Readings in a compact format with larger font
        self.readings_label = QLabel("Temp: -- °C | Humidity: -- % | Pressure: -- hPa")
        self.readings_label.setStyleSheet("font-size: 11pt; font-weight: bold;")
        self.readings_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.readings_label)
        
        self.groupbox.setLayout(layout)
        
        self.latest = {
            "temperature": 0.0,
            "humidity": 0.0,
            "pressure": 0.0
        }
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_data)
        self.timer.start(3000)

    def _update_data(self):
        try:
            data = read_thp_sensor_data(self.port)
            if data:
                self.latest = data
                self.readings_label.setText(
                    f"Temp: {data['temperature']:.1f} °C | "
                    f"Humidity: {data['humidity']:.1f} % | "
                    f"Pressure: {data['pressure']:.1f} hPa"
                )
            else:
                # Update the label to show connection issue
                self.readings_label.setText("Sensor not connected - check COM port")
                self.status_signal.emit(f"THP sensor read failed on port {self.port}")
        except Exception as e:
            self.readings_label.setText("Sensor error - check connection")
            self.status_signal.emit(f"THP sensor error: {e}")

    def get_latest(self):
        return self.latest

    def is_connected(self):
        return self.latest["temperature"] != 0.0

    def reconnect(self):
        """Try to reconnect to the THP sensor"""
        self.status_signal.emit(f"Attempting to reconnect THP sensor on {self.port}")
        data = read_thp_sensor_data(self.port)
        if data:
            self.latest = data
            self.readings_label.setText(
                f"Temp: {data['temperature']:.1f} °C | "
                f"Humidity: {data['humidity']:.1f} % | "
                f"Pressure: {data['pressure']:.1f} hPa"
            )
            self.status_signal.emit("THP sensor reconnected successfully")
            return True
        else:
            self.readings_label.setText("Reconnect failed - check COM port")
            self.status_signal.emit(f"THP sensor reconnect failed on port {self.port}")
            return False






