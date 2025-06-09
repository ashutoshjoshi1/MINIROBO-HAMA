import sys
from PyQt5.QtWidgets import (
    QMainWindow, QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QComboBox, QGroupBox, QGridLayout,
    QTextEdit, QTabWidget, QSplitter, QSizePolicy, QAction, QFileDialog
)
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import Qt, QTimer
from pyqtgraph import PlotWidget
import pyqtgraph as pg

from gui.components.camera_manager import CameraManager
from gui.components.data_logger import DataLogger
from gui.components.routine_manager import RoutineManager
from gui.components.ui_manager import UIManager

# Import controllers
from controllers.spectrometer_controller import SpectrometerController
from controllers.motor_controller import MotorController
from controllers.filterwheel_controller import FilterwheelController
from controllers.imu_controller import IMUController
from controllers.temp_controller import TempController
from controllers.thp_controller import THPController

class MainWindow(QMainWindow):
    def __init__(self, spectrometer_type, spectrometer_dll_path, spectrometer_kwargs):
        super().__init__()

        self.setWindowTitle("Mini ROBOHyPO Control")
        self.setGeometry(100, 100, 1600, 900)

        # --- Initialize Controllers ---
        self.spectrometer_controller = SpectrometerController(
            spec_type=spectrometer_type,
            dll_path=spectrometer_dll_path,
            **spectrometer_kwargs
        )
        self.motor_controller = MotorController(port="COM3") # Example port
        self.filterwheel_controller = FilterwheelController(port="COM4") # Example port
        self.imu_controller = IMUController(port="COM5") # Example port
        self.temp_controller = TempController(port="COM6") # Example port
        self.thp_controller = THPController(port="COM7") # Example port


        # --- Initialize UI Managers and Components ---
        self.ui_manager = UIManager(self)
        self.data_logger = DataLogger()
        self.camera_manager = CameraManager()
        self.routine_manager = RoutineManager(
            self.spectrometer_controller,
            self.motor_controller,
            self.filterwheel_controller,
            self.data_logger
        )


        # --- Central Widget and Layout ---
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout(self.central_widget)

        # --- Create UI Sections ---
        self.create_left_panel()
        self.create_main_panel()
        self.create_right_panel()

        # Use a splitter to make panels resizable
        main_splitter = QSplitter(Qt.Horizontal)
        main_splitter.addWidget(self.left_panel)
        main_splitter.addWidget(self.main_panel)
        main_splitter.addWidget(self.right_panel)
        main_splitter.setSizes([250, 1100, 250]) # Initial sizes
        self.main_layout.addWidget(main_splitter)


        # --- Connect Signals and Slots ---
        self.connect_signals()

        # --- Start Controllers ---
        self.spectrometer_controller.start()
        self.motor_controller.start()
        self.filterwheel_controller.start()
        self.imu_controller.start()
        self.temp_controller.start()
        self.thp_controller.start()

        # --- UI Update Timer ---
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_sensor_data)
        self.timer.start(1000) # Update every second

    def create_left_panel(self):
        """Creates the left panel with hardware controls."""
        self.left_panel = QGroupBox("Hardware Control")
        layout = QVBoxLayout()

        # Spectrometer Control
        spec_group = QGroupBox("Spectrometer")
        spec_layout = QGridLayout()
        self.spec_status_label = QLabel("Status: Disconnected")
        self.integration_time_input = QLineEdit("100")
        self.set_int_time_button = QPushButton("Set Integration Time")
        self.take_measurement_button = QPushButton("Take Measurement")
        spec_layout.addWidget(self.spec_status_label, 0, 0, 1, 2)
        spec_layout.addWidget(QLabel("Integration Time (ms):"), 1, 0)
        spec_layout.addWidget(self.integration_time_input, 1, 1)
        spec_layout.addWidget(self.set_int_time_button, 2, 0, 1, 2)
        spec_layout.addWidget(self.take_measurement_button, 3, 0, 1, 2)
        spec_group.setLayout(spec_layout)
        layout.addWidget(spec_group)

        # Motor Control
        motor_group = QGroupBox("Motor Control")
        motor_layout = QGridLayout()
        self.motor_status_label = QLabel("Status: Disconnected")
        self.zenith_pos_label = QLabel("Zenith: N/A")
        self.azimuth_pos_label = QLabel("Azimuth: N/A")
        self.move_za_input = QLineEdit("0")
        self.move_az_input = QLineEdit("0")
        self.move_abs_button = QPushButton("Move Absolute")
        self.stop_motor_button = QPushButton("Stop")
        motor_layout.addWidget(self.motor_status_label, 0, 0, 1, 2)
        motor_layout.addWidget(self.zenith_pos_label, 1, 0)
        motor_layout.addWidget(self.azimuth_pos_label, 1, 1)
        motor_layout.addWidget(QLabel("Zenith:"), 2, 0)
        motor_layout.addWidget(self.move_za_input, 2, 1)
        motor_layout.addWidget(QLabel("Azimuth:"), 3, 0)
        motor_layout.addWidget(self.move_az_input, 3, 1)
        motor_layout.addWidget(self.move_abs_button, 4, 0)
        motor_layout.addWidget(self.stop_motor_button, 4, 1)
        motor_group.setLayout(motor_layout)
        layout.addWidget(motor_group)

        # Filterwheel Control
        fw_group = QGroupBox("Filterwheel")
        fw_layout = QGridLayout()
        self.fw_status_label = QLabel("Status: Disconnected")
        self.fw_pos_label = QLabel("Position: N/A")
        self.fw_pos_combo = QComboBox()
        self.fw_pos_combo.addItems([str(i) for i in range(1, 7)])
        self.set_fw_pos_button = QPushButton("Set Position")
        fw_layout.addWidget(self.fw_status_label, 0, 0, 1, 2)
        fw_layout.addWidget(self.fw_pos_label, 1, 0, 1, 2)
        fw_layout.addWidget(self.fw_pos_combo, 2, 0)
        fw_layout.addWidget(self.set_fw_pos_button, 2, 1)
        fw_group.setLayout(fw_layout)
        layout.addWidget(fw_group)

        layout.addStretch()
        self.left_panel.setLayout(layout)

    def create_main_panel(self):
        """Creates the main central panel with plots and logs."""
        self.main_panel = QWidget()
        layout = QVBoxLayout()

        # Plot Widget for Spectrometer
        self.plot_widget = PlotWidget()
        self.plot_widget.setBackground('w')
        # The following line has been changed to remove the grid
        self.plot_widget.showGrid(x=False, y=False)
        self.plot_widget.setLabel('left', 'Intensity', units='counts')
        self.plot_widget.setLabel('bottom', 'Wavelength', units='nm')
        self.plot_curve = self.plot_widget.plot(pen='b')
        layout.addWidget(self.plot_widget)

        # Tab Widget for Logs, Routines, etc.
        self.tab_widget = QTabWidget()
        self.log_text_edit = QTextEdit()
        self.log_text_edit.setReadOnly(True)
        self.tab_widget.addTab(self.log_text_edit, "Log")
        self.tab_widget.addTab(self.routine_manager, "Routines & Schedules")
        layout.addWidget(self.tab_widget)

        layout.setStretch(0, 2) # Give more space to the plot
        layout.setStretch(1, 1)
        self.main_panel.setLayout(layout)

    def create_right_panel(self):
        """Creates the right panel with sensor data and camera feed."""
        self.right_panel = QWidget()
        layout = QVBoxLayout()

        # Sensor Data
        sensor_group = QGroupBox("Sensor Data")
        sensor_layout = QGridLayout()
        self.imu_status_label = QLabel("IMU: Disconnected")
        self.temp_status_label = QLabel("Temp Ctrl: Disconnected")
        self.thp_status_label = QLabel("THP: Disconnected")
        self.imu_data_label = QLabel("Roll: N/A, Pitch: N/A, Yaw: N/A")
        self.temp_data_label = QLabel("Temp: N/A °C")
        self.thp_data_label = QLabel("T: N/A °C, H: N/A %, P: N/A hPa")
        sensor_layout.addWidget(self.imu_status_label, 0, 0)
        sensor_layout.addWidget(self.temp_status_label, 1, 0)
        sensor_layout.addWidget(self.thp_status_label, 2, 0)
        sensor_layout.addWidget(self.imu_data_label, 3, 0)
        sensor_layout.addWidget(self.temp_data_label, 4, 0)
        sensor_layout.addWidget(self.thp_data_label, 5, 0)
        sensor_group.setLayout(sensor_layout)
        layout.addWidget(sensor_group)

        # Camera Feed
        camera_group = QGroupBox("Camera")
        cam_layout = QVBoxLayout()
        self.camera_view = QLabel("Camera feed disabled.")
        self.camera_view.setAlignment(Qt.AlignCenter)
        self.camera_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.camera_view.setStyleSheet("background-color: black; color: white;")
        cam_layout.addWidget(self.camera_view)
        self.camera_manager.set_view(self.camera_view)
        camera_group.setLayout(cam_layout)
        layout.addWidget(camera_group)

        layout.setStretch(1, 1) # Make camera feed expand
        self.right_panel.setLayout(layout)


    def connect_signals(self):
        """Connect all signals to their respective slots."""
        # Spectrometer signals
        self.spectrometer_controller.connection_status.connect(self.update_spec_status)
        self.spectrometer_controller.wavelengths_ready.connect(self.update_wavelengths)
        self.spectrometer_controller.measurement_ready.connect(self.update_plot)
        self.set_int_time_button.clicked.connect(lambda: self.spectrometer_controller.set_integration_time(float(self.integration_time_input.text())))
        self.take_measurement_button.clicked.connect(self.spectrometer_controller.take_measurement)

        # Motor signals
        self.motor_controller.motor_status.connect(self.update_motor_status)
        self.motor_controller.motor_position.connect(self.update_motor_position)
        self.move_abs_button.clicked.connect(lambda: self.motor_controller.move_absolute('az', float(self.move_az_input.text()))) # Simple example
        self.stop_motor_button.clicked.connect(self.motor_controller.stop)

        # Filterwheel signals
        self.filterwheel_controller.filterwheel_status.connect(self.update_fw_status)
        self.filterwheel_controller.filterwheel_position.connect(self.update_fw_position)
        self.set_fw_pos_button.clicked.connect(lambda: self.filterwheel_controller.set_position(int(self.fw_pos_combo.currentText())))

        # Sensor signals
        self.imu_controller.imu_status.connect(lambda status: self.imu_status_label.setText(f"IMU: {status}"))
        self.imu_controller.imu_data.connect(self.update_imu_data)
        self.temp_controller.temp_status.connect(lambda status: self.temp_status_label.setText(f"Temp Ctrl: {status}"))
        self.temp_controller.temp_data.connect(self.update_temp_data)
        self.thp_controller.thp_status.connect(lambda status: self.thp_status_label.setText(f"THP: {status}"))
        self.thp_controller.thp_data.connect(self.update_thp_data)

        # Data logger
        self.data_logger.log_message.connect(self.log_text_edit.append)


    def update_sensor_data(self):
        """Periodically request data from sensors."""
        self.imu_controller.get_data()
        self.temp_controller.get_data()
        self.thp_controller.get_data()

    def update_spec_status(self, status):
        self.spec_status_label.setText(f"Status: {status}")

    def update_wavelengths(self, wavelengths):
        self.wavelengths = wavelengths

    def update_plot(self, data):
        if self.wavelengths is not None and data is not None:
            if len(self.wavelengths) == len(data):
                self.plot_curve.setData(self.wavelengths, data)
            else:
                self.data_logger.log(f"Wavelength/Data length mismatch: {len(self.wavelengths)} vs {len(data)}")

    def update_motor_status(self, status):
        self.motor_status_label.setText(f"Status: {status}")

    def update_motor_position(self, position):
        self.zenith_pos_label.setText(f"Zenith: {position.get('za', 'N/A')}")
        self.azimuth_pos_label.setText(f"Azimuth: {position.get('az', 'N/A')}")

    def update_fw_status(self, status):
        self.fw_status_label.setText(f"Status: {status}")

    def update_fw_position(self, position):
        self.fw_pos_label.setText(f"Position: {position}")

    def update_imu_data(self, data):
        roll = data.get('roll', 'N/A')
        pitch = data.get('pitch', 'N/A')
        yaw = data.get('yaw', 'N/A')
        self.imu_data_label.setText(f"Roll: {roll:.2f}, Pitch: {pitch:.2f}, Yaw: {yaw:.2f}")
        self.data_logger.log_sensor("IMU", data)


    def update_temp_data(self, data):
        temp = data.get('temp', 'N/A')
        self.temp_data_label.setText(f"Temp: {temp:.2f} °C")
        self.data_logger.log_sensor("TempCtrl", data)


    def update_thp_data(self, data):
        temp = data.get('temp', 'N/A')
        humidity = data.get('humidity', 'N/A')
        pressure = data.get('pressure', 'N/A')
        self.thp_data_label.setText(f"T: {temp:.2f} °C, H: {humidity:.2f} %, P: {pressure:.2f} hPa")
        self.data_logger.log_sensor("THP", data)


    def closeEvent(self, event):
        """Ensure all hardware is disconnected on exit."""
        self.spectrometer_controller.disconnect()
        self.motor_controller.disconnect()
        self.filterwheel_controller.disconnect()
        self.imu_controller.disconnect()
        self.temp_controller.disconnect()
        self.thp_controller.disconnect()
        self.camera_manager.stop_camera()
        event.accept()

if __name__ == '__main__':
    # This part is for testing the main window independently.
    # The main execution is handled by main.py
    app = QApplication(sys.argv)
    # Provide dummy parameters for testing
    window = MainWindow(
        spectrometer_type="avantes",
        spectrometer_dll_path="path/to/your/avaspecx64.dll",
        spectrometer_kwargs={}
    )
    window.show()
    sys.exit(app.exec_())