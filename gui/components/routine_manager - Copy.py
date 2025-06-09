import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QFileDialog
from PyQt5.QtCore import QDateTime, QTimer, pyqtSignal, QObject

class ResultsPlotDialog(QDialog):
    """Dialog to display the results plot after routine completion"""
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(800, 600)
        
        # Create layout
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Create matplotlib figure and canvas
        self.figure = plt.figure(figsize=(10, 6))
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(self.canvas)
        
        # Set dialog flags to ensure it's modal and blocks until closed
        self.setModal(True)
    
    def plot_data(self, data_dict, pixel_indices):
        """Plot the data from the dictionary"""
        # Clear the figure
        self.figure.clear()
        
        # Create subplot
        ax = self.figure.add_subplot(111)
        
        # Dark colors for Opaque filter (position 1)
        dark_colors = ['#1a237e', '#311b92', '#4a148c', '#880e4f', '#b71c1c']
        # Light colors for Open filter (position 2)
        light_colors = ['#7986cb', '#9575cd', '#ba68c8', '#f48fb1', '#ef9a9a']
        
        # Print data keys for debugging
        print(f"Data keys: {list(data_dict.keys())}")
        
        # Plot Opaque filter data (position 1)
        for i, angle in enumerate([0, 45, 90, 135, 180]):
            key = f"pos1_angle{angle}"
            if key in data_dict and len(data_dict[key]) > 0:
                print(f"Plotting {key} with {len(data_dict[key])} points, color: {dark_colors[i]}")
                ax.plot(pixel_indices, data_dict[key], 
                        color=dark_colors[i], 
                        linewidth=2, 
                        label=f"Opaque ({angle}°)")
            else:
                print(f"No data for {key}")
        
        # Plot Open filter data (position 2)
        for i, angle in enumerate([0, 45, 90, 135, 180]):
            key = f"pos2_angle{angle}"
            if key in data_dict and len(data_dict[key]) > 0:
                print(f"Plotting {key} with {len(data_dict[key])} points, color: {light_colors[i]}")
                ax.plot(pixel_indices, data_dict[key], 
                        color=light_colors[i], 
                        linewidth=2, 
                        label=f"Open ({angle}°)")
            else:
                print(f"No data for {key}")
        
        # Set labels and title
        ax.set_xlabel('Pixel')
        ax.set_ylabel('Count (Average)')
        ax.set_title('PO Routine Results - Pixel Counts by Position and Angle')
        
        # Add grid
        ax.grid(True, alpha=0.3)
        
        # Add legend
        ax.legend(loc='upper right')
        
        # Update the canvas
        self.canvas.draw()
        
        print("Plot completed and canvas updated")

class RoutineManager(QObject):
    status_signal = pyqtSignal(str)
    
    def __init__(self, main_window):
        super().__init__(main_window)  # Initialize QObject with parent
        self.main_window = main_window
        self.routine_running = False
        self.routine_commands = []
        self.current_command_index = 0
        self.routine_timer = QTimer()
        self.routine_timer.timeout.connect(self._execute_next_command)
        self.data_saving_started_by_routine = False
        self.final_data = None
        
        # Set up routines directory
        self.routines_dir = os.path.join(os.path.dirname(__file__), "..", "..", "routines")
        os.makedirs(self.routines_dir, exist_ok=True)
        
        # Set up presets
        self.presets = {
            "Standard Scan": os.path.join(self.routines_dir, "standard_scan.txt"),
            "Dark Reference": os.path.join(self.routines_dir, "dark_reference.txt"),
            "White Reference": os.path.join(self.routines_dir, "white_reference.txt"),
            "Filter Sequence": os.path.join(self.routines_dir, "filter_sequence.txt"),
            "Temperature Test": os.path.join(self.routines_dir, "temperature_test.txt")
        }
        
        # Create default routines if they don't exist
        self._create_default_routines()

    def _create_default_routines(self):
        """Create default routine files if they don't exist"""
        # Standard Scan routine
        standard_scan = os.path.join(self.routines_dir, "standard_scan.txt")
        if not os.path.exists(standard_scan):
            with open(standard_scan, 'w') as f:
                f.write("# Standard Scan Routine\n")
                f.write("log Starting Standard Scan\n")
                f.write("filter position 2\n")
                f.write("wait 1000\n")
                f.write("motor move 0\n")
                f.write("wait 2000\n")
                f.write("spectrometer start\n")
                f.write("wait 5000\n")
                f.write("spectrometer save\n")
                f.write("log Standard Scan Complete\n")
    
        # PO Routine (Position-Optics)
        po_routine = os.path.join(self.routines_dir, "po_routine.txt")
        if not os.path.exists(po_routine):
            with open(po_routine, 'w') as f:
                f.write("# Position-Optics (PO) Routine\n")
                f.write("log Starting PO Routine\n")
                
                # Loop through filter positions
                for filter_pos in [1, 2]:  # 1=Opaque, 2=Open
                    f.write(f"filter position {filter_pos}\n")
                    f.write("wait 1000\n")
                    
                    # Loop through motor angles
                    for angle in [0, 45, 90, 135, 180]:
                        f.write(f"motor move {angle}\n")
                        f.write("wait 2000\n")  # Wait for motor to move
                        f.write("spectrometer start\n")
                        f.write("wait 3000\n")  # Collect data for 3 seconds
                        f.write("spectrometer save\n")
                        f.write("wait 1000\n")  # Wait before next position
        
            f.write("log PO Routine Complete\n")
    
        # Create other default routines as needed
        self._create_simple_routine("dark_reference.txt", "Dark Reference", 1)
        self._create_simple_routine("white_reference.txt", "White Reference", 2)

    def _create_simple_routine(self, filename, name, filter_pos):
        """Create a simple routine file with the given name and filter position"""
        filepath = os.path.join(self.routines_dir, filename)
        if not os.path.exists(filepath):
            with open(filepath, 'w') as f:
                f.write(f"# {name} Routine\n")
                f.write(f"log Starting {name}\n")
                f.write(f"filter position {filter_pos}\n")
                f.write("wait 1000\n")
                f.write("motor move 0\n")
                f.write("wait 2000\n")
                f.write("spectrometer start\n")
                f.write("wait 5000\n")
                f.write("spectrometer save\n")
                f.write(f"log {name} Complete\n")

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
            # Store the current routine path
            self.current_routine = file_path

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
        
        # Update status
        if hasattr(self.main_window, 'routine_status'):
            self.main_window.routine_status.setText(f"Running command {self.current_command_index + 1}/{len(self.routine_commands)}: {command}")
        
        # Execute the command
        self._execute_command(command)
        
        # Move to the next command
        self.current_command_index += 1

    def _routine_complete(self):
        """Handle routine completion"""
        # Check if we're already in the completion process to prevent infinite loops
        if hasattr(self, '_completion_in_progress') and self._completion_in_progress:
            print("Routine completion already in progress, preventing infinite loop")
            return
        
        # Set flag to prevent multiple calls
        self._completion_in_progress = True
        
        self.routine_running = False
        self.current_command_index = 0
        
        # Update UI
        if hasattr(self.main_window, 'routine_status'):
            self.main_window.routine_status.setText("Routine completed")
        
        # Stop data saving if it was started by the routine
        if self.data_saving_started_by_routine:
            if hasattr(self.main_window, 'data_logger') and hasattr(self.main_window.data_logger, 'continuous_saving'):
                if self.main_window.data_logger.continuous_saving:
                    self.main_window.toggle_data_saving()
            self.data_saving_started_by_routine = False
        
        # Process the data and create the plot
        self.main_window.statusBar().showMessage("Processing routine data for plotting...")
        print("Routine completed, processing data for plotting...")
        
        # Add a small delay to ensure data is saved before processing
        QTimer.singleShot(1000, self._process_and_plot_routine_data)
        
        # Enable the start button
        if hasattr(self.main_window, 'run_routine_btn'):
            self.main_window.run_routine_btn.setText("Run")
        
        # Log completion
        self.main_window.statusBar().showMessage("Routine completed")
        
        # Reset completion flag after a delay to allow for any pending operations
        QTimer.singleShot(5000, lambda: setattr(self, '_completion_in_progress', False))

    def _process_and_plot_routine_data(self):
        """Process the data from the routine and create a plot"""
        try:
            # Check if we already have a plot dialog open to prevent duplicates
            if hasattr(self, '_plot_dialog_open') and self._plot_dialog_open:
                print("Plot dialog already open, skipping duplicate processing")
                return
            
            self._plot_dialog_open = True
            self.main_window.statusBar().showMessage("Starting data processing...")
            
            # Find the most recent CSV file in the data directory
            csv_dir = "data"
            if not os.path.exists(csv_dir):
                self.main_window.statusBar().showMessage("Data directory not found")
                self._plot_dialog_open = False
                return
            
            # Get list of CSV files
            csv_files = [f for f in os.listdir(csv_dir) if f.endswith('.csv') and not f.startswith('final_')]
            if not csv_files:
                self.main_window.statusBar().showMessage("No CSV files found")
                self._plot_dialog_open = False
                return
            
            # Sort by modification time (most recent first)
            csv_files.sort(key=lambda x: os.path.getmtime(os.path.join(csv_dir, x)), reverse=True)
            
            # Get the most recent file
            latest_csv = os.path.join(csv_dir, csv_files[0])
            self.main_window.statusBar().showMessage(f"Processing data from {latest_csv}")
            
            # Read the CSV file
            df = pd.read_csv(latest_csv)
            
            # Print column names for debugging
            print(f"CSV columns: {df.columns.tolist()}")
            
            # Check for required columns with different possible names
            motor_angle_col = None
            filter_pos_col = None
            
            # Check for motor angle column
            for col_name in ['MotorAngle', 'MotorAngle_deg', 'Motor_Angle']:
                if col_name in df.columns:
                    motor_angle_col = col_name
                    break
            
            # Check for filter position column
            for col_name in ['FilterPosition', 'FilterPos', 'Filter_Position']:
                if col_name in df.columns:
                    filter_pos_col = col_name
                    break
            
            if not motor_angle_col or not filter_pos_col:
                self.main_window.statusBar().showMessage(f"CSV file missing required columns. Found: {', '.join(df.columns)}")
                self._plot_dialog_open = False
                return
            
            # Find the intensity columns (they start with 'Pixel_')
            intensity_cols = [col for col in df.columns if col.startswith('Pixel_')]
            
            # If no columns start with 'Pixel_', try other patterns
            if not intensity_cols:
                intensity_cols = [col for col in df.columns if 'Pixel' in col]
            
            # If still no intensity columns, try numeric columns after the metadata columns
            if not intensity_cols:
                # Assume all numeric columns after standard metadata are pixel data
                metadata_cols = ['Timestamp', motor_angle_col, filter_pos_col, 
                                'Roll_deg', 'Pitch_deg', 'Yaw_deg', 
                                'AccelX_g', 'AccelY_g', 'AccelZ_g',
                                'MagX_uT', 'MagY_uT', 'MagZ_uT',
                                'Pressure_hPa', 'TempEnv_C', 'TempCurr_C', 'TempSet_C',
                                'Latitude', 'Longitude', 'IntegTime_us', 'THPTemp_C',
                                'THPHum_pct', 'THPPres_hPa', 'Spec_temp_C', 'RoutineCode']
                
                # Get columns that are not in metadata_cols
                remaining_cols = [col for col in df.columns if col not in metadata_cols]
                
                # Try to convert these to numeric and use those that succeed
                for col in remaining_cols:
                    try:
                        pd.to_numeric(df[col])
                        intensity_cols.append(col)
                    except:
                        pass
            
            if not intensity_cols:
                self.main_window.statusBar().showMessage("No intensity columns found in CSV file")
                self._plot_dialog_open = False
                return
            
            self.main_window.statusBar().showMessage(f"Found {len(intensity_cols)} intensity columns")
            print(f"Using intensity columns: {intensity_cols[:5]}... (total: {len(intensity_cols)})")
            
            # Create a dictionary to store the averaged data
            data_dict = {}
            
            # Process data for each filter position and angle
            for filter_pos in [1, 2]:  # 1=Opaque, 2=Open
                for angle in [0, 45, 90, 135, 180]:
                    # Filter the data
                    filtered_df = df[(df[filter_pos_col] == filter_pos) & 
                                    (df[motor_angle_col] == angle)]
                    
                    if not filtered_df.empty:
                        # Calculate the average intensity for each pixel
                        avg_intensities = filtered_df[intensity_cols].mean().values
                        
                        # Store in the dictionary
                        key = f"pos{filter_pos}_angle{angle}"
                        data_dict[key] = avg_intensities
                        print(f"Processed data for position {filter_pos}, angle {angle}: {len(filtered_df)} rows, avg: {avg_intensities.mean():.2f}")
                    else:
                        print(f"No data found for position {filter_pos}, angle {angle}")
            
            if not data_dict:
                self.main_window.statusBar().showMessage("No matching data found in CSV file")
                self._plot_dialog_open = False
                return
            
            # Create pixel indices
            pixel_indices = np.arange(len(intensity_cols))
            
            # Create and show the plot dialog
            self.main_window.statusBar().showMessage("Creating plot dialog...")
            plot_dialog = ResultsPlotDialog("PO Routine Results", self.main_window)
            plot_dialog.plot_data(data_dict, pixel_indices)
            
            # Connect the dialog's close event to reset the flag
            plot_dialog.finished.connect(lambda: setattr(self, '_plot_dialog_open', False))
            
            plot_dialog.show()
            
            # Also update the spectrometer plot if available
            if hasattr(self.main_window, 'spec_ctrl') and hasattr(self.main_window.spec_ctrl, 'curve_px'):
                # Create a combined plot for the spectrometer view
                # Use position 2 (Open) data as it's more interesting
                combined_data = np.zeros(len(intensity_cols))
                count = 0
                
                for angle in [0, 45, 90, 135, 180]:
                    key = f"pos2_angle{angle}"
                    if key in data_dict and len(data_dict[key]) > 0:
                        combined_data += data_dict[key]
                        count += 1
                
                if count > 0:
                    combined_data /= count
                    
                    # Update the spectrometer plot
                    self.main_window.spec_ctrl.curve_px.setData(pixel_indices, combined_data)
                    
                    # Update y-axis range
                    if np.max(combined_data) > 0:
                        max_y = np.max(combined_data) * 1.1
                        self.main_window.spec_ctrl.plot_px.setYRange(0, max_y)
                    
                    # Add timestamp to the plot title
                    timestamp = QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss")
                    self.main_window.spec_ctrl.plot_px.setTitle(f"PO Routine Results - {timestamp}")
                    
                    self.main_window.statusBar().showMessage("Updated spectrometer plot with routine data")
        
        except Exception as e:
            import traceback
            self.main_window.statusBar().showMessage(f"Error processing routine data: {str(e)}")
            print(f"Error processing routine data: {str(e)}")
            print(traceback.format_exc())
            self._plot_dialog_open = False

    def _execute_command(self, command):
        """Execute a single command from the routine"""
        try:
            # Split the command into parts
            parts = command.split()
            cmd_type = parts[0].lower()
            
            # Log command
            if cmd_type == "log":
                message = " ".join(parts[1:])
                self.main_window.statusBar().showMessage(message)
                if hasattr(self, 'status_signal'):
                    self.status_signal.emit(message)
                print(f"Routine log: {message}")
                # Continue to next command immediately
                QTimer.singleShot(100, self._execute_next_command)
            
            # Wait command
            elif cmd_type == "wait":
                if len(parts) > 1:
                    try:
                        wait_time = int(parts[1])
                        self.main_window.statusBar().showMessage(f"Waiting for {wait_time} ms")
                        # Set timer for next command
                        self.routine_timer.start(wait_time)
                    except ValueError:
                        print(f"Invalid wait time: {parts[1]}")
                        # Continue to next command
                        QTimer.singleShot(100, self._execute_next_command)
                else:
                    # No wait time specified, continue immediately
                    QTimer.singleShot(100, self._execute_next_command)
            
            # Motor command
            elif cmd_type == "motor":
                if len(parts) > 2 and parts[1].lower() == "move":
                    try:
                        angle = float(parts[2])
                        if hasattr(self.main_window, 'motor_ctrl'):
                            self.main_window.statusBar().showMessage(f"Moving motor to {angle} degrees")
                            # Use the correct method from MotorController
                            self.main_window.motor_ctrl.move_to(angle)
                            print(f"Motor move command sent: {angle} degrees")
                        else:
                            self.main_window.statusBar().showMessage("Motor controller not available")
                            print("Motor controller not available")
                        # Continue to next command after a longer delay to allow motor to move
                        QTimer.singleShot(2000, self._execute_next_command)
                    except ValueError:
                        print(f"Invalid motor angle: {parts[2]}")
                        QTimer.singleShot(100, self._execute_next_command)
                else:
                    print(f"Invalid motor command: {command}")
                    QTimer.singleShot(100, self._execute_next_command)
            
            # Filter command
            elif cmd_type == "filter":
                if len(parts) > 2 and parts[1].lower() == "position":
                    try:
                        position = int(parts[2])
                        if hasattr(self.main_window, 'filter_ctrl'):
                            self.main_window.statusBar().showMessage(f"Moving filter wheel to position {position}")
                            # Use the correct method from FilterWheelController
                            self.main_window.filter_ctrl.set_position(position)
                            print(f"Filter wheel position command sent: {position}")
                        else:
                            self.main_window.statusBar().showMessage("Filter controller not available")
                            print("Filter controller not available")
                        # Continue to next command after a longer delay to allow filter wheel to move
                        QTimer.singleShot(2000, self._execute_next_command)
                    except ValueError:
                        print(f"Invalid filter position: {parts[2]}")
                        QTimer.singleShot(100, self._execute_next_command)
                else:
                    print(f"Invalid filter command: {command}")
                    QTimer.singleShot(100, self._execute_next_command)
            
            # Spectrometer command
            elif cmd_type == "spectrometer":
                if len(parts) > 1:
                    if parts[1].lower() == "start":
                        if hasattr(self.main_window, 'spec_ctrl'):
                            self.main_window.statusBar().showMessage("Starting spectrometer measurement")
                            self.main_window.spec_ctrl.start_measurement()
                        else:
                            self.main_window.statusBar().showMessage("Spectrometer controller not available")
                    elif parts[1].lower() == "stop":
                        if hasattr(self.main_window, 'spec_ctrl'):
                            self.main_window.statusBar().showMessage("Stopping spectrometer measurement")
                            self.main_window.spec_ctrl.stop_measurement()
                        else:
                            self.main_window.statusBar().showMessage("Spectrometer controller not available")
                    elif parts[1].lower() == "save":
                        if hasattr(self.main_window, 'spec_ctrl'):
                            self.main_window.statusBar().showMessage("Saving spectrometer data")
                            # Trigger a save in the data logger
                            if hasattr(self.main_window, 'data_logger'):
                                self.main_window.data_logger.save_data_point()
                        else:
                            self.main_window.statusBar().showMessage("Spectrometer controller not available")
                    else:
                        print(f"Invalid spectrometer command: {command}")
                else:
                    print(f"Invalid spectrometer command: {command}")
                
                # Continue to next command after a short delay
                QTimer.singleShot(500, self._execute_next_command)
            
            # Data command
            elif cmd_type == "data":
                if len(parts) > 1:
                    if parts[1].lower() == "start":
                        if hasattr(self.main_window, 'data_logger') and not self.main_window.data_logger.continuous_saving:
                            self.main_window.statusBar().showMessage("Starting data saving")
                            self.main_window.toggle_data_saving()
                    elif parts[1].lower() == "stop":
                        if hasattr(self.main_window, 'data_logger') and self.main_window.data_logger.continuous_saving:
                            self.main_window.statusBar().showMessage("Stopping data saving")
                            self.main_window.toggle_data_saving()
                    else:
                        print(f"Invalid data command: {command}")
                else:
                    print(f"Invalid data command: {command}")
                
                # Continue to next command after a short delay
                QTimer.singleShot(500, self._execute_next_command)
            
            # Unknown command
            else:
                print(f"Unknown command: {command}")
                # Continue to next command
                QTimer.singleShot(100, self._execute_next_command)
        
        except Exception as e:
            import traceback
            print(f"Error executing command '{command}': {e}")
            print(traceback.format_exc())
            # Try to continue to next command
            QTimer.singleShot(100, self._execute_next_command)
