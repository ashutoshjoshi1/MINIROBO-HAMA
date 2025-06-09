import os
import numpy as np
from PyQt5.QtCore import QObject, QTimer, pyqtSignal, QDateTime
from PyQt5.QtWidgets import QFileDialog, QMessageBox

class RoutineManager(QObject):
    status_signal = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self.routine_commands = []
        self.current_command_index = 0
        self.routine_running = False
        self.routine_timer = QTimer(self)
        self.routine_timer.timeout.connect(self._execute_next_command)
        
        # Create routines directory if it doesn't exist
        self.routines_dir = os.path.join(os.path.dirname(__file__), "..", "..", "routines")
        os.makedirs(self.routines_dir, exist_ok=True)
        
        # Preset routines
        self.presets = {
            "Standard Scan": os.path.join(self.routines_dir, "standard_scan.txt"),
            "Dark Reference": os.path.join(self.routines_dir, "dark_reference.txt"),
            "White Reference": os.path.join(self.routines_dir, "white_reference.txt"),
            "Filter Sequence": os.path.join(self.routines_dir, "filter_sequence.txt"),
            "Temperature Test": os.path.join(self.routines_dir, "temperature_test.txt")
        }
        
        # Flag to track if data saving was started by the routine
        self.data_saving_started_by_routine = False
        
        # Store final data for plotting
        self.final_data = None
    
    def load_routine_file(self):
        """Load a routine file from disk"""
        file_path, _ = QFileDialog.getOpenFileName(
            self.main_window,
            "Open Routine File",
            self.routines_dir,
            "Text Files (*.txt);;All Files (*)"
        )
        
        if file_path:
            self._load_routine_from_file(file_path)
    
    def load_preset_routine(self, preset_name):
        """Load a preset routine by name"""
        if preset_name in self.presets:
            file_path = self.presets[preset_name]
            if os.path.exists(file_path):
                self._load_routine_from_file(file_path)
            else:
                self.main_window.statusBar().showMessage(f"Preset file not found: {file_path}")
                if hasattr(self.main_window, 'routine_status'):
                    self.main_window.routine_status.setText(f"Preset file not found")
        else:
            self.main_window.statusBar().showMessage(f"Unknown preset: {preset_name}")
    
    def _load_routine_from_file(self, file_path):
        """Load and parse a routine file"""
        try:
            with open(file_path, 'r') as f:
                content = f.read()
            
            # Parse the routine
            self.routine_commands = []
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                self.routine_commands.append(line)
            
            # Update UI
            self.main_window.statusBar().showMessage(f"Loaded routine with {len(self.routine_commands)} commands")
            if hasattr(self.main_window, 'routine_status'):
                self.main_window.routine_status.setText(f"Loaded: {os.path.basename(file_path)}")
            if hasattr(self.main_window, 'run_routine_btn'):
                self.main_window.run_routine_btn.setEnabled(len(self.routine_commands) > 0)
        
        except Exception as e:
            self.main_window.statusBar().showMessage(f"Error loading routine: {e}")
            if hasattr(self.main_window, 'routine_status'):
                self.main_window.routine_status.setText("Error loading routine")
    
    def run_routine(self):
        """Start running the loaded routine"""
        if not self.routine_commands:
            self.main_window.statusBar().showMessage("No routine loaded")
            return
        
        if self.routine_running:
            self.stop_routine()
            return
        
        # Start the routine
        self.routine_running = True
        self.current_command_index = 0
        if hasattr(self.main_window, 'run_routine_btn'):
            self.main_window.run_routine_btn.setText("Stop")
        if hasattr(self.main_window, 'routine_status'):
            self.main_window.routine_status.setText(f"Running command 1/{len(self.routine_commands)}")
        
        # Start continuous data saving if not already active
        if hasattr(self.main_window, 'data_logger') and hasattr(self.main_window.data_logger, 'continuous_saving'):
            if not self.main_window.data_logger.continuous_saving:
                self.data_saving_started_by_routine = True
                self.main_window.toggle_data_saving()
                self.main_window.statusBar().showMessage("Started continuous data saving for routine")
        
        # Execute the first command
        self._execute_next_command()
    
    def stop_routine(self):
        """Stop the currently running routine"""
        self.routine_running = False
        self.routine_timer.stop()
        
        # Stop data saving if it was started by the routine
        if self.data_saving_started_by_routine:
            if hasattr(self.main_window, 'data_logger') and hasattr(self.main_window.data_logger, 'continuous_saving'):
                if self.main_window.data_logger.continuous_saving:
                    self.main_window.toggle_data_saving()
                    self.main_window.statusBar().showMessage("Stopped continuous data saving")
            self.data_saving_started_by_routine = False
        
        if hasattr(self.main_window, 'run_routine_btn'):
            self.main_window.run_routine_btn.setText("Run Code")
        if hasattr(self.main_window, 'routine_status'):
            self.main_window.routine_status.setText("Routine stopped")
        self.main_window.statusBar().showMessage("Routine execution stopped")
    
    def _execute_next_command(self):
        """Execute the next command in the routine"""
        if not self.routine_running or self.current_command_index >= len(self.routine_commands):
            self._routine_complete()
            return
        
        # Get the current command
        command = self.routine_commands[self.current_command_index]
        self.main_window.statusBar().showMessage(f"Executing: {command}")
        if hasattr(self.main_window, 'routine_status'):
            self.main_window.routine_status.setText(f"Running {self.current_command_index+1}/{len(self.routine_commands)}: {command}")
        
        # Parse and execute the command
        parts = command.split()
        if not parts:
            self.current_command_index += 1
            self._execute_next_command()
            return
        
        cmd_type = parts[0].lower()
        
        if cmd_type == "wait":
            # Wait command - pause execution for specified milliseconds
            if len(parts) > 1:
                try:
                    wait_time = int(parts[1])
                    self.routine_timer.start(wait_time)
                    self.current_command_index += 1
                    return  # Return here to wait for timer
                except ValueError:
                    self.main_window.statusBar().showMessage(f"Invalid wait time: {parts[1]}")
        
        elif cmd_type == "motor" and len(parts) > 2 and parts[1].lower() == "move":
            # Motor move command
            try:
                angle = float(parts[2])
                if hasattr(self.main_window, 'motor_ctrl'):
                    self.main_window.motor_ctrl.move_to(angle)
            except (ValueError, AttributeError) as e:
                self.main_window.statusBar().showMessage(f"Motor move error: {e}")
        
        elif cmd_type == "filter" and len(parts) > 2 and parts[1].lower() == "position":
            # Filter position command
            try:
                position = int(parts[2])
                if hasattr(self.main_window, 'filter_ctrl'):
                    self.main_window.filter_ctrl.move_to_position(position)
            except (ValueError, AttributeError) as e:
                self.main_window.statusBar().showMessage(f"Filter position error: {e}")
        
        elif cmd_type == "spectrometer":
            # Spectrometer commands
            if len(parts) > 1:
                spec_cmd = parts[1].lower()
                if spec_cmd == "start" and hasattr(self.main_window, 'spec_ctrl'):
                    self.main_window.spec_ctrl.start()
                elif spec_cmd == "stop" and hasattr(self.main_window, 'spec_ctrl'):
                    self.main_window.spec_ctrl.stop()
                elif spec_cmd == "save" and hasattr(self.main_window, 'spec_ctrl'):
                    # Save current data
                    self.main_window.spec_ctrl.save()
                    # Also store the data for final plotting
                    if hasattr(self.main_window.spec_ctrl, 'intens'):
                        self.final_data = self.main_window.spec_ctrl.intens.copy()
        
        elif cmd_type == "temperature" and len(parts) > 2 and parts[1].lower() == "set":
            # Temperature setpoint command
            try:
                setpoint = float(parts[2])
                if hasattr(self.main_window, 'temp_ctrl'):
                    self.main_window.temp_ctrl.set_temperature(setpoint)
            except (ValueError, AttributeError) as e:
                self.main_window.statusBar().showMessage(f"Temperature set error: {e}")
        
        elif cmd_type == "log":
            # Log message command
            log_msg = " ".join(parts[1:])
            self.main_window.statusBar().showMessage(log_msg)
            if hasattr(self.main_window, 'handle_status_message'):
                self.main_window.handle_status_message(log_msg)
        
        # Move to the next command
        self.current_command_index += 1
        self._execute_next_command()
    
    def _routine_complete(self):
        """Handle routine completion"""
        self.routine_running = False
        self.routine_timer.stop()
        
        # Stop data saving if it was started by the routine
        if self.data_saving_started_by_routine:
            if hasattr(self.main_window, 'data_logger') and hasattr(self.main_window.data_logger, 'continuous_saving'):
                if self.main_window.data_logger.continuous_saving:
                    self.main_window.toggle_data_saving()
                    self.main_window.statusBar().showMessage("Stopped continuous data saving")
            self.data_saving_started_by_routine = False
        
        # Plot the final data if available
        if self.final_data is not None and hasattr(self.main_window, 'spec_ctrl'):
            # Update the plot with the final data
            try:
                # Create pixel indices array
                pixel_indices = np.arange(len(self.final_data))
                
                # Update the plot
                self.main_window.spec_ctrl.curve_px.setData(pixel_indices, self.final_data)
                
                # Update y-axis range
                if len(self.final_data) > 0 and max(self.final_data) > 0:
                    max_y = max(self.final_data) * 1.1
                    self.main_window.spec_ctrl.plot_px.setYRange(0, max_y)
                
                # Add timestamp to the plot title
                timestamp = QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss")
                self.main_window.spec_ctrl.plot_px.setTitle(f"Final Scan - {timestamp}")
                
                # Log the completion with peak value
                peak = max(self.final_data) if self.final_data else 0
                self.main_window.handle_status_message(f"Routine completed - Peak value: {peak:.1f}")
            except Exception as e:
                self.main_window.statusBar().showMessage(f"Error plotting final data: {e}")
        
        # Stop the spectrometer measurement
        if hasattr(self.main_window, 'spec_ctrl'):
            self.main_window.spec_ctrl.stop()
        
        # Update UI
        if hasattr(self.main_window, 'run_routine_btn'):
            self.main_window.run_routine_btn.setText("Run Code")
        if hasattr(self.main_window, 'routine_status'):
            self.main_window.routine_status.setText("Routine completed")
        
        self.main_window.statusBar().showMessage("Routine execution completed")
