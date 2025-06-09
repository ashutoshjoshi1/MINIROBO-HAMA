from PyQt5.QtCore import QObject, pyqtSignal, QThread
import time
import logging

class RoutineManager(QObject):
    routine_started_signal = pyqtSignal(str)
    routine_finished_signal = pyqtSignal(str)
    routine_progress_signal = pyqtSignal(int)
    routine_log_signal = pyqtSignal(str)
    routine_graph_signal = pyqtSignal(object, object)

    def __init__(self, ui_manager, spectrometer_controller, motor_controller, filterwheel_controller, temp_controller, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ui_manager = ui_manager
        self.spectrometer_controller = spectrometer_controller
        self.motor_controller = motor_controller
        self.filterwheel_controller = filterwheel_controller
        self.temp_controller = temp_controller
        self.routine_thread = None

    def run_routine(self, routine_name, routine):
        if self.routine_thread is not None and self.routine_thread.isRunning():
            self.routine_log_signal.emit("Routine already running")
            return
        
        self.routine_thread = QThread()
        self.routine_worker = RoutineWorker(routine_name, routine, self)
        self.routine_worker.moveToThread(self.routine_thread)
        self.routine_thread.started.connect(self.routine_worker.run)
        self.routine_worker.finished.connect(self.routine_thread.quit)
        self.routine_worker.finished.connect(self.routine_worker.deleteLater)
        self.routine_thread.finished.connect(self.routine_thread.deleteLater)
        self.routine_worker.progress.connect(self.routine_progress_signal.emit)
        self.routine_worker.log.connect(self.routine_log_signal.emit)
        self.routine_worker.graph.connect(self.routine_graph_signal.emit)
        self.routine_worker.finished.connect(lambda: self.routine_finished_signal.emit(routine_name))
        
        self.routine_started_signal.emit(routine_name)
        self.routine_thread.start()

    def stop_routine(self):
        if self.routine_thread is not None and self.routine_thread.isRunning():
            self.routine_worker.stop()
            self.routine_thread.quit()
            self.routine_thread.wait()
            self.routine_log_signal.emit("Routine stopped by user")
            self.routine_finished_signal.emit("Stopped")

class RoutineWorker(QObject):
    finished = pyqtSignal()
    progress = pyqtSignal(int)
    log = pyqtSignal(str)
    graph = pyqtSignal(object, object)

    def __init__(self, routine_name, routine, manager):
        super().__init__()
        self.routine_name = routine_name
        self.routine = routine
        self.manager = manager
        self.is_running = True

    def run(self):
        self.log.emit(f"Starting routine: {self.routine_name}")
        total_steps = len(self.routine)
        for i, step in enumerate(self.routine):
            if not self.is_running:
                break
            
            self.log.emit(f"Executing step {i+1}/{total_steps}: {step}")
            self.execute_step(step)
            self.progress.emit(int((i + 1) / total_steps * 100))
            time.sleep(0.1) # Small delay between steps
            
        self.finished.emit()

    def execute_step(self, step):
        parts = step.split()
        command = parts[0].lower()
        args = parts[1:]

        try:
            if command == "move_gimbal":
                self.manager.motor_controller.move_gimbal(int(args[0]), int(args[1]))
            elif command == "home_gimbal":
                self.manager.motor_controller.home_gimbal()
            elif command == "get_spectrum":
                # Updated to call controller method
                spectrum, wavelengths = self.manager.spectrometer_controller.get_spectrum()
                if spectrum is not None:
                    self.log.emit("Spectrum acquired.")
                    self.graph.emit(wavelengths, spectrum)
                else:
                    self.log.emit("Failed to acquire spectrum.")
            elif command == "set_integration_time":
                # Updated to call controller method
                self.manager.spectrometer_controller.set_integration_time(float(args[0]))
            elif command == "move_filterwheel":
                self.manager.filterwheel_controller.move_to_position(int(args[0]))
            elif command == "home_filterwheel":
                self.manager.filterwheel_controller.home()
            elif command == "wait":
                time.sleep(float(args[0]))
            elif command == "set_temp":
                self.manager.temp_controller.set_temperature(float(args[0]))
            else:
                self.log.emit(f"Unknown command: {command}")
        except Exception as e:
            self.log.emit(f"Error executing step '{step}': {e}")
            logging.error(f"Routine execution error on step '{step}': {e}")

    def stop(self):
        self.is_running = False
