import os
import time
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget, QLabel, QGroupBox
from PyQt5.QtCore import QThread, pyqtSignal

class RoutineExecutor(QThread):
    """
    Executes a routine in a separate thread.
    """
    log_message = pyqtSignal(str)
    routine_finished = pyqtSignal()

    def __init__(self, routine_path, controllers, data_logger):
        super().__init__()
        self.routine_path = routine_path
        self.controllers = controllers
        self.data_logger = data_logger
        self.running = True

    def run(self):
        self.log_message.emit(f"Starting routine: {os.path.basename(self.routine_path)}")
        try:
            with open(self.routine_path, 'r') as f:
                for line in f:
                    if not self.running:
                        self.log_message.emit("Routine aborted by user.")
                        break
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue

                    parts = line.split()
                    command = parts[0].lower()
                    args = parts[1:]

                    self.log_message.emit(f"Executing: {line}")
                    self.execute_command(command, args)
                    self.msleep(100) # Small delay between commands
        except Exception as e:
            self.log_message.emit(f"Error in routine: {e}")
        
        self.routine_finished.emit()

    def execute_command(self, command, args):
        """Parses and executes a single command from a routine file."""
        spec_controller = self.controllers['spectrometer']
        motor_controller = self.controllers['motor']
        fw_controller = self.controllers['filterwheel']

        if command == 'set_integration_time':
            spec_controller.set_integration_time(float(args[0]))
        elif command == 'measure':
            spec_controller.take_measurement()
            # In a real scenario, you'd wait for the measurement_ready signal.
            # This is a simplified implementation.
            time.sleep(spec_controller.spectrometer.it_ms / 1000 + 0.1) 
        elif command == 'move_abs':
            axis = args[0]
            pos = float(args[1])
            motor_controller.move_absolute(axis, pos)
            # You would need a mechanism to wait for the move to complete.
            time.sleep(2) # Placeholder wait
        elif command == 'set_filter':
            pos = int(args[0])
            fw_controller.set_position(pos)
            time.sleep(1) # Placeholder wait
        elif command == 'wait':
            time.sleep(float(args[0]))
        else:
            self.log_message.emit(f"Unknown command: {command}")
            
    def stop(self):
        self.running = False


class RoutineManager(QWidget):
    """
    UI for managing and running measurement routines and schedules.
    """
    def __init__(self, spec_controller, motor_controller, fw_controller, data_logger):
        super().__init__()
        self.controllers = {
            'spectrometer': spec_controller,
            'motor': motor_controller,
            'filterwheel': fw_controller
        }
        self.data_logger = data_logger
        self.routine_executor = None

        self.init_ui()
        self.load_routines()
        self.load_schedules()

    def init_ui(self):
        main_layout = QHBoxLayout(self)

        # Routines Group
        routines_group = QGroupBox("Routines")
        routines_layout = QVBoxLayout()
        self.routine_list = QListWidget()
        self.start_routine_button = QPushButton("Start Routine")
        self.stop_routine_button = QPushButton("Stop Routine")
        routines_layout.addWidget(self.routine_list)
        routines_layout.addWidget(self.start_routine_button)
        routines_layout.addWidget(self.stop_routine_button)
        routines_group.setLayout(routines_layout)

        # Schedules Group
        schedules_group = QGroupBox("Schedules")
        schedules_layout = QVBoxLayout()
        self.schedule_list = QListWidget()
        self.start_schedule_button = QPushButton("Start Schedule")
        self.stop_schedule_button = QPushButton("Stop Schedule")
        schedules_layout.addWidget(self.schedule_list)
        schedules_layout.addWidget(self.start_schedule_button)
        schedules_layout.addWidget(self.stop_schedule_button)
        schedules_group.setLayout(schedules_layout)

        main_layout.addWidget(routines_group)
        main_layout.addWidget(schedules_group)

        # Button connections
        self.start_routine_button.clicked.connect(self.start_routine)
        self.stop_routine_button.clicked.connect(self.stop_routine)
        # Schedule buttons are placeholders for now
        self.start_schedule_button.setEnabled(False)
        self.stop_schedule_button.setEnabled(False)

    def load_files(self, directory, list_widget):
        """Loads .txt files from a directory into a QListWidget."""
        if not os.path.isdir(directory):
            self.data_logger.log(f"Directory not found: {directory}")
            return
        for file in os.listdir(directory):
            if file.endswith(".txt"):
                list_widget.addItem(file)

    def load_routines(self):
        self.load_files("routines", self.routine_list)

    def load_schedules(self):
        self.load_files("schedules", self.schedule_list)

    def start_routine(self):
        selected_item = self.routine_list.currentItem()
        if not selected_item:
            self.data_logger.log("No routine selected.")
            return
        if self.routine_executor and self.routine_executor.isRunning():
            self.data_logger.log("A routine is already running.")
            return

        routine_path = os.path.join("routines", selected_item.text())
        self.routine_executor = RoutineExecutor(routine_path, self.controllers, self.data_logger)
        self.routine_executor.log_message.connect(self.data_logger.log)
        self.routine_executor.finished.connect(self.on_routine_finished)
        self.routine_executor.start()
        self.start_routine_button.setEnabled(False)
        self.stop_routine_button.setEnabled(True)

    def stop_routine(self):
        if self.routine_executor and self.routine_executor.isRunning():
            self.routine_executor.stop()

    def on_routine_finished(self):
        self.data_logger.log("Routine finished.")
        self.start_routine_button.setEnabled(True)
        self.stop_routine_button.setEnabled(False)
