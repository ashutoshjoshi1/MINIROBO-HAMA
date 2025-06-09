import serial, cv2
from serial.tools import list_ports
from PyQt5.QtCore import QObject, pyqtSignal, QTimer, Qt
from PyQt5.QtWidgets import QGroupBox, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton
from PyQt5.QtGui import QImage, QPixmap
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.pyplot as plt

from drivers.imu import start_imu_read_thread
import utils

class IMUController(QObject):
    status_signal = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.groupbox = QGroupBox("IMU")
        self.groupbox.setObjectName("imuGroup")
        
        # Use a vertical layout for more compact display
        main_layout = QVBoxLayout()
        main_layout.setSpacing(2)  # Reduce spacing
        
        # Port controls in a compact horizontal layout
        port_layout = QHBoxLayout()
        port_layout.addWidget(QLabel("COM:"))
        self.port_combo = QComboBox()
        self.port_combo.setEditable(True)
        self.port_combo.setMaximumWidth(80)
        ports = [p.device for p in list_ports.comports()]
        self.port_combo.addItems(ports or [f"COM{i}" for i in range(1, 10)])
        port_layout.addWidget(self.port_combo)
        
        port_layout.addWidget(QLabel("Baud:"))
        self.baud_combo = QComboBox()
        self.baud_combo.setMaximumWidth(70)
        self.baud_combo.addItems(["9600", "57600", "115200"])
        port_layout.addWidget(self.baud_combo)
        
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setMaximumWidth(70)
        self.connect_btn.clicked.connect(self.connect)
        port_layout.addWidget(self.connect_btn)
        
        main_layout.addLayout(port_layout)
        
        # Data label - compact but readable
        self.data_label = QLabel("Not connected")
        self.data_label.setStyleSheet("font-size: 10pt;")
        self.data_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.data_label)
        
        self.groupbox.setLayout(main_layout)
        
        self._connected = False
        self.serial = None
        self.latest = {
            'rpy': (0, 0, 0),
            'latitude': 0,
            'longitude': 0,
            'temperature': 0,
            'pressure': 0
        }
        
        # Auto-select config port if provided
        if parent is not None and hasattr(parent, 'config'):
            cfg_port = parent.config.get("imu")
            if cfg_port:
                self.port_combo.setCurrentText(cfg_port)
                self.connect()

    def connect(self):
        if self._connected:
            return self.status_signal.emit("Already connected")
        port = self.port_combo.currentText().strip()
        baud = int(self.baud_combo.currentText())
        try:
            self.serial = serial.Serial(port, baud, timeout=1)
        except Exception as e:
            return self.status_signal.emit(f"Fail: {e}")
        self._connected = True
        self.status_signal.emit(f"IMU on {port}@{baud}")
        self.stop_evt = start_imu_read_thread(self.serial, self.latest)
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self._refresh)
        self.update_timer.start(100)

    def _update_cam(self):
        if self.cam.isOpened():
            ret, frame = self.cam.read()
            if ret:
                # Resize the frame to fit the larger display area
                frame = cv2.resize(frame, (640, 480))
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = frame.shape
                img = QImage(frame.data, w, h, ch * w, QImage.Format_RGB888)
                self.cam_label.setPixmap(QPixmap.fromImage(img).scaled(
                    self.cam_label.width(), self.cam_label.height(),
                    Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _refresh(self):
        r, p, y = self.latest['rpy']
        lat = self.latest['latitude']
        lon = self.latest['longitude']
        t = self.latest['temperature']
        pres = self.latest['pressure']
        
        # Format the data with larger text and better formatting
        self.data_label.setText(
            f"<table width='100%' cellspacing='5'>"
            f"<tr><td align='right'><b>Roll:</b></td><td align='left'>{r:.1f}°</td>"
            f"<td align='right'><b>Pitch:</b></td><td align='left'>{p:.1f}°</td>"
            f"<td align='right'><b>Yaw:</b></td><td align='left'>{y:.1f}°</td></tr>"
            f"<tr><td align='right'><b>Temp:</b></td><td align='left'>{t:.1f}°C</td>"
            f"<td align='right'><b>Pressure:</b></td><td align='left'>{pres:.1f}hPa</td></tr>"
            f"<tr><td align='right'><b>Lat:</b></td><td align='left'>{lat:.5f}</td>"
            f"<td align='right'><b>Lon:</b></td><td align='left'>{lon:.5f}</td></tr>"
            f"</table>"
        )

    def is_connected(self):
        return self._connected









