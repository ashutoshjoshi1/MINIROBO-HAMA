import serial
from serial.tools import list_ports
from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import QGroupBox, QHBoxLayout, QVBoxLayout, QLabel, QComboBox, QLineEdit, QPushButton

from drivers.filterwheel import FilterWheelConnectThread, FilterWheelCommandThread

class FilterWheelController(QObject):
    status_signal = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.groupbox = QGroupBox("Filter Wheel")
        self.groupbox.setObjectName("filterwheelGroup")
        main_layout = QVBoxLayout()

        # Connection controls
        conn_layout = QHBoxLayout()
        
        port_label = QLabel("COM:")
        port_label.setStyleSheet("font-weight: bold;")
        conn_layout.addWidget(port_label)
        
        self.port_combo = QComboBox()
        self.port_combo.setEditable(True)
        ports = [p.device for p in list_ports.comports()]
        self.port_combo.addItems(ports or [f"COM{i}" for i in range(1, 10)])

        default_port = "COM17"
        if parent is not None and hasattr(parent, 'config'):
            default_port = parent.config.get("filterwheel", default_port)
        self.port_combo.setCurrentText(default_port)
        conn_layout.addWidget(self.port_combo)

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.connect)
        conn_layout.addWidget(self.connect_btn)

        pos_label = QLabel("Pos:")
        pos_label.setStyleSheet("font-weight: bold;")
        conn_layout.addWidget(pos_label)
        
        self.pos_label = QLabel("--")
        self.pos_label.setStyleSheet("font-size: 11pt;")
        conn_layout.addWidget(self.pos_label)

        main_layout.addLayout(conn_layout)

        # Filter type buttons - make them larger and more prominent
        filter_layout = QHBoxLayout()
        
        # Open filter button (positions 2, 3, 4)
        self.open_btn = QPushButton("Open")
        self.open_btn.setStyleSheet("font-weight: bold; font-size: 11pt; padding: 6px 10px;")
        self.open_btn.setEnabled(False)
        self.open_btn.clicked.connect(self.set_open_filter)
        filter_layout.addWidget(self.open_btn)
        
        # Opaque filter button (positions 1, reset)
        self.opaque_btn = QPushButton("Opaque")
        self.opaque_btn.setStyleSheet("font-weight: bold; font-size: 11pt; padding: 6px 10px;")
        self.opaque_btn.setEnabled(False)
        self.opaque_btn.clicked.connect(self.set_opaque_filter)
        filter_layout.addWidget(self.opaque_btn)
        
        # Diffuser filter button (positions 5, 6)
        self.diff_btn = QPushButton("Diff")
        self.diff_btn.setStyleSheet("font-weight: bold; font-size: 11pt; padding: 6px 10px;")
        self.diff_btn.setEnabled(False)
        self.diff_btn.clicked.connect(self.set_diff_filter)
        filter_layout.addWidget(self.diff_btn)
        
        main_layout.addLayout(filter_layout)

        # Manual command input
        cmd_layout = QHBoxLayout()
        cmd_layout.addWidget(QLabel("Cmd:"))
        self.cmd_input = QLineEdit()
        cmd_layout.addWidget(self.cmd_input)

        self.send_btn = QPushButton("Send")
        self.send_btn.setEnabled(False)
        self.send_btn.clicked.connect(self.send)
        cmd_layout.addWidget(self.send_btn)
        
        main_layout.addLayout(cmd_layout)

        self.groupbox.setLayout(main_layout)

        self._connected = False
        self.serial = None
        self.last = None
        self.current_position = None

        # Auto-connect on startup
        self.connect()

    def connect(self):
        """Connect to the filter wheel"""
        self.connect_btn.setEnabled(False)
        th = FilterWheelConnectThread(self.port_combo.currentText(), parent=self)
        th.result_signal.connect(self._on_connect)
        th.start()

    def _on_connect(self, ser, msg):
        self.status_signal.emit(msg)
        self.connect_btn.setEnabled(True)
        if ser:
            self.serial = ser
            self._connected = True
            self.send_btn.setEnabled(True)
            self.open_btn.setEnabled(True)
            self.opaque_btn.setEnabled(True)
            self.diff_btn.setEnabled(True)
            self._send("F1r")  # Reset to position 1
        else:
            self._connected = False
            self.send_btn.setEnabled(False)
            self.open_btn.setEnabled(False)
            self.opaque_btn.setEnabled(False)
            self.diff_btn.setEnabled(False)

    def set_open_filter(self):
        """Set filter wheel to an open filter position (2, 3, or 4)"""
        self._send("F12")  # Default to position 2
        self.status_signal.emit("Setting Open filter (position 2)")

    def set_opaque_filter(self):
        """Set filter wheel to an opaque filter position (1 or reset)"""
        self._send("F1r")  # Reset to position 1
        self.status_signal.emit("Setting Opaque filter (position 1)")

    def set_diff_filter(self):
        """Set filter wheel to a diffuser filter position (5 or 6)"""
        self._send("F15")  # Default to position 5
        self.status_signal.emit("Setting Diffuser filter (position 5)")

    def set_position(self, position):
        """Set filter wheel to a specific position (1-6)"""
        if position < 1 or position > 6:
            self.status_signal.emit(f"Invalid position: {position}")
            return
        cmd = f"F1{position}"
        self._send(cmd)

    def send(self):
        cmd = self.cmd_input.text().strip()
        self._send(cmd)

    def _send(self, cmd):
        if not self._connected:
            return self.status_signal.emit("Not connected")
        self.send_btn.setEnabled(False)
        self.open_btn.setEnabled(False)
        self.opaque_btn.setEnabled(False)
        self.diff_btn.setEnabled(False)
        self.last = cmd
        th = FilterWheelCommandThread(self.serial, cmd, parent=self)
        th.result_signal.connect(self._on_result)
        th.start()

    def _on_result(self, pos, msg):
        self.send_btn.setEnabled(True)
        self.open_btn.setEnabled(True)
        self.opaque_btn.setEnabled(True)
        self.diff_btn.setEnabled(True)
        self.status_signal.emit(msg)

        if self.last:
            if self.last == "F1r":
                self.pos_label.setText("1")
                self.current_position = 1
            elif self.last.startswith("F1") and len(self.last) == 3 and self.last[2].isdigit():
                position = int(self.last[2])
                self.pos_label.setText(str(position))
                self.current_position = position
            else:
                if pos is not None:
                    self.pos_label.setText(str(pos))
                    self.current_position = pos
        self.last = None

    def get_position(self):
        try:
            return int(self.pos_label.text())
        except:
            return self.current_position or 0

    def is_connected(self):
        return self._connected

