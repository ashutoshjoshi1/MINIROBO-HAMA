import os
from PyQt5.QtCore import QObject, QDateTime, pyqtSignal

class DataLogger(QObject):
    status_signal = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self.log_file = None
        self.csv_file = None
        self.continuous_saving = False
        
        # Create log directories if they don't exist
        self.log_dir = os.path.join(os.path.dirname(__file__), "..", "..", "logs")
        self.csv_dir = os.path.join(os.path.dirname(__file__), "..", "..", "data")
        os.makedirs(self.log_dir, exist_ok=True)
        os.makedirs(self.csv_dir, exist_ok=True)
        
        # Initialize data collection for averaging
        self._data_collection = []
        self._csv_buffer = []
        self._csv_buffer_count = 0
        self._csv_buffer_max = 5  # Write to disk every 5 samples
        
        # Store collection and save intervals
        self.collection_interval = 1000  # Default 1 second
        self.save_interval = 1200  # Default 1.2 seconds

    def toggle_data_saving(self):
        """Toggle continuous data saving on/off"""
        if not hasattr(self, 'continuous_saving'):
            self.continuous_saving = False
            
        self.continuous_saving = not self.continuous_saving
        
        if self.continuous_saving:
            self._start_data_saving()
        else:
            self._stop_data_saving()
            
        return self.continuous_saving
    
    def _start_data_saving(self):
        """Start continuous data saving"""
        if hasattr(self, 'csv_file') and self.csv_file:
            self.csv_file.close()
        if hasattr(self, 'log_file') and self.log_file:
            self.log_file.close()
            
        ts = QDateTime.currentDateTime().toString("yyyyMMdd_hhmmss")
        self.csv_file_path = os.path.join(self.csv_dir, f"Scans_{ts}_mini.csv")
        self.log_file_path = os.path.join(self.log_dir, f"log_{ts}.txt")
        
        try:
            self.csv_file = open(self.csv_file_path, "w", encoding="utf-8", newline="")
            self.log_file = open(self.log_file_path, "w", encoding="utf-8")
        except Exception as e:
            self.status_signal.emit(f"Cannot open files: {e}")
            return
        
        # Write headers to CSV file
        headers = self._get_csv_headers()
        self.csv_file.write(",".join(headers) + "\n")
        self.csv_file.flush()
        os.fsync(self.csv_file.fileno())
        
        # Initialize data collection for averaging
        self._data_collection = []
        self._collection_start_time = QDateTime.currentDateTime()
        
        # Log the integration time being used
        integration_time_ms = 1000  # Default
        if hasattr(self.main_window, 'spec_ctrl') and hasattr(self.main_window.spec_ctrl, 'current_integration_time_us'):
            integration_time_ms = self.main_window.spec_ctrl.current_integration_time_us
        
        self.status_signal.emit(f"Data saving started with integration time: {integration_time_ms}ms")
        
        # Store the collection and save intervals based on integration time
        self.collection_interval = max(100, integration_time_ms)
        self.save_interval = integration_time_ms + 200  # Add 200ms buffer
    
    def _stop_data_saving(self):
        """Stop continuous data saving"""
        if hasattr(self, 'csv_file') and self.csv_file:
            self.csv_file.close()
            self.csv_file = None
        if hasattr(self, 'log_file') and self.log_file:
            self.log_file.close()
            self.log_file = None
    
    def _get_csv_headers(self):
        """Get CSV headers based on available data"""
        headers = [
            "Timestamp", "MotorAngle_deg", "FilterPos",
            "Roll_deg", "Pitch_deg", "Yaw_deg", "AccelX_g", "AccelY_g", "AccelZ_g",
            "MagX_uT", "MagY_uT", "MagZ_uT",
            "Pressure_hPa", "TempEnv_C", "TempCurr_C", "TempSet_C",
            "Latitude", "Longitude", "IntegTime_us", "THPTemp_C",
            "THPHum_pct", "THPPres_hPa", "Spec_temp_C", "RoutineCode"
        ]
        
        # Add pixel headers if spectrometer data is available
        if hasattr(self.main_window, 'spec_ctrl') and hasattr(self.main_window.spec_ctrl, 'intens'):
            headers += [f"Pixel_{i}" for i in range(len(self.main_window.spec_ctrl.intens))]
            
        return headers
    
    def collect_data_sample(self):
        """Collect a data sample for averaging"""
        if not hasattr(self.main_window, 'spec_ctrl'):
            return
            
        # Create a copy of the current intensity data
        intensities = self.main_window.spec_ctrl.intens.copy()
        
        # Store the sample with timestamp
        sample = {
            'timestamp': QDateTime.currentDateTime(),
            'intensities': intensities
        }
        
        # Add to collection
        self._data_collection.append(sample)
    
    def _debug_controller_values(self):
        """Debug method to print current controller values"""
        debug_info = []
        
        # Motor controller debug
        if hasattr(self.main_window, 'motor_ctrl') and self.main_window.motor_ctrl is not None:
            motor_info = "Motor: "
            if hasattr(self.main_window.motor_ctrl, 'current_angle'):
                motor_info += f"current_angle={self.main_window.motor_ctrl.current_angle}"
            else:
                motor_info += "current_angle=None"
            debug_info.append(motor_info)
        
        # IMU controller debug
        if hasattr(self.main_window, 'imu_ctrl') and self.main_window.imu_ctrl is not None:
            imu_info = "IMU: "
            if hasattr(self.main_window.imu_ctrl, 'data_dict'):
                imu_info += f"data_dict={self.main_window.imu_ctrl.data_dict}"
            else:
                imu_info += "data_dict=None"
            
            if hasattr(self.main_window.imu_ctrl, 'latest_data'):
                imu_info += f", latest_data={self.main_window.imu_ctrl.latest_data}"
            else:
                imu_info += ", latest_data=None"
            debug_info.append(imu_info)
        
        # THP controller debug
        if hasattr(self.main_window, 'thp_ctrl') and self.main_window.thp_ctrl is not None:
            thp_info = "THP: "
            if hasattr(self.main_window.thp_ctrl, 'latest'):
                thp_info += f"latest={self.main_window.thp_ctrl.latest}"
            else:
                thp_info += "latest=None"
            
            if hasattr(self.main_window.thp_ctrl, 'get_latest'):
                try:
                    thp_info += f", get_latest()={self.main_window.thp_ctrl.get_latest()}"
                except:
                    thp_info += ", get_latest()=Error"
            debug_info.append(thp_info)
        
        # Print debug info
        # print("\n".join(debug_info))
        
        # Also log to status
        self.status_signal.emit("Debug info printed to console")

    def save_continuous_data(self):
        """Average collected samples and save to CSV"""
        if not hasattr(self, 'csv_file') or not self.csv_file or not hasattr(self, 'continuous_saving') or not self.continuous_saving:
            return
        
        # If hardware is changing or integration time is being adjusted, don't save data
        if (hasattr(self.main_window, '_hardware_changing') and self.main_window._hardware_changing) or \
           (hasattr(self.main_window, '_integration_changing') and self.main_window._integration_changing):
            return
        
        # Debug controller values occasionally (every 10th save)
        if hasattr(self, '_debug_counter'):
            self._debug_counter += 1
            if self._debug_counter >= 10:
                self._debug_counter = 0
                self._debug_controller_values()
        else:
            self._debug_counter = 0
            
        try:
            # Process collected data
            num_samples = len(self._data_collection)
            if num_samples == 0:
                return
                
            # Get timestamps
            ts_csv = self._data_collection[0]['timestamp'].toString("yyyy-MM-dd HH:mm:ss.zzz")
            ts_txt = self._data_collection[0]['timestamp'].toString("HH:mm:ss.zzz")
            
            # Average intensity values
            avg_intensities = self._calculate_average_intensities()
            
            # Get current values from controllers
            row = self._build_csv_row(ts_csv, avg_intensities)
            
            # Add to buffer
            line = ",".join(row) + "\n"
            self._csv_buffer.append(line)
            self._csv_buffer_count += 1
            
            # Only write to disk when buffer is full
            if self._csv_buffer_count >= self._csv_buffer_max:
                self.csv_file.write(''.join(self._csv_buffer))
                self.csv_file.flush()
                self._csv_buffer = []
                self._csv_buffer_count = 0
            
            # Log file can be written immediately as it's much smaller
            peak = max(avg_intensities) if avg_intensities else 0
            txt_line = f"{ts_txt} | Peak {peak:.1f} (avg of {num_samples} samples)\n"
            self.log_file.write(txt_line)
            self.log_file.flush()
            
            # Clear the data collection for the next interval
            self._data_collection = []
            
        except Exception as e:
            print("save_continuous_data error:", e)
            self.status_signal.emit(f"Save error: {e}")
    
    def _calculate_average_intensities(self):
        """Calculate average intensities from collected samples"""
        if not self._data_collection:
            return []
            
        # Get the first sample to determine array size
        first_sample = self._data_collection[0]['intensities']
        avg_intensities = [0.0] * len(first_sample)
        
        # Sum all samples
        for sample in self._data_collection:
            intensities = sample['intensities']
            for i in range(len(avg_intensities)):
                if i < len(intensities):
                    avg_intensities[i] += intensities[i]
        
        # Divide by number of samples
        num_samples = len(self._data_collection)
        if num_samples > 0:
            avg_intensities = [val / num_samples for val in avg_intensities]
            
        return avg_intensities
    
    def _build_csv_row(self, ts_csv, avg_intensities):
        """Build CSV row with current values from all controllers"""
        # Default values
        motor_angle = 0
        filter_pos = 0
        r, p, y = 0, 0, 0
        ax, ay, az = 0, 0, 0
        mx, my, mz = 0, 0, 0
        pres, temp_env = 0, 0
        tc_curr, tc_set = 0, 0
        lat, lon = 0, 0
        integ_us = 0
        thp_temp, thp_hum, thp_pres = 0, 0, 0
        spec_temp = 0
        routine_code = "XX"
        
        # Get motor angle - fix for MotorAngle_deg
        if hasattr(self.main_window, 'motor_ctrl') and self.main_window.motor_ctrl is not None:
            # Try different attribute names that might contain the angle
            if hasattr(self.main_window.motor_ctrl, 'current_angle_deg'):
                motor_angle = self.main_window.motor_ctrl.current_angle_deg
            elif hasattr(self.main_window.motor_ctrl, 'current_angle'):
                motor_angle = self.main_window.motor_ctrl.current_angle
            elif hasattr(self.main_window.motor_ctrl, 'angle'):
                motor_angle = self.main_window.motor_ctrl.angle
            elif hasattr(self.main_window.motor_ctrl, 'position'):
                motor_angle = self.main_window.motor_ctrl.position
            # Try to get from the UI if available
            elif hasattr(self.main_window.motor_ctrl, 'angle_input'):
                try:
                    motor_angle = float(self.main_window.motor_ctrl.angle_input.text().strip())
                except (ValueError, AttributeError):
                    pass
            elif hasattr(self.main_window.motor_ctrl, 'angle_display'):
                try:
                    motor_angle = float(self.main_window.motor_ctrl.angle_display.text().replace('°', ''))
                except (ValueError, AttributeError):
                    pass
        
        # Get IMU data - fix for Roll, Pitch, Yaw, Accel, Mag, Pressure
        if hasattr(self.main_window, 'imu_ctrl') and self.main_window.imu_ctrl is not None:
            # Try to get data from the latest attribute
            if hasattr(self.main_window.imu_ctrl, 'latest'):
                imu_data = self.main_window.imu_ctrl.latest
                if imu_data:
                    r = imu_data.get('rpy', [0, 0, 0])[0] if 'rpy' in imu_data else imu_data.get('roll', r)
                    p = imu_data.get('rpy', [0, 0, 0])[1] if 'rpy' in imu_data else imu_data.get('pitch', p)
                    y = imu_data.get('rpy', [0, 0, 0])[2] if 'rpy' in imu_data else imu_data.get('yaw', y)
                    
                    if 'accel' in imu_data and isinstance(imu_data['accel'], (list, tuple)) and len(imu_data['accel']) >= 3:
                        ax, ay, az = imu_data['accel']
                    else:
                        ax = imu_data.get('accel_x', ax)
                        ay = imu_data.get('accel_y', ay)
                        az = imu_data.get('accel_z', az)
                    
                    if 'mag' in imu_data and isinstance(imu_data['mag'], (list, tuple)) and len(imu_data['mag']) >= 3:
                        mx, my, mz = imu_data['mag']
                    else:
                        mx = imu_data.get('mag_x', mx)
                        my = imu_data.get('mag_y', my)
                        mz = imu_data.get('mag_z', mz)
                    
                    pres = imu_data.get('pressure', pres)
                    temp_env = imu_data.get('temperature', temp_env)
            
            # Try to get data from the data_label if available
            if (r == 0 or p == 0 or y == 0) and hasattr(self.main_window.imu_ctrl, 'data_label'):
                try:
                    # Try to parse the HTML table in data_label
                    from PyQt5.QtCore import Qt
                    text = self.main_window.imu_ctrl.data_label.text()
                    if "Roll:" in text and "°" in text:
                        import re
                        # Extract roll, pitch, yaw values
                        roll_match = re.search(r'Roll:</b></td><td align=\'left\'>([+-]?\d+\.?\d*)°', text)
                        pitch_match = re.search(r'Pitch:</b></td><td align=\'left\'>([+-]?\d+\.?\d*)°', text)
                        yaw_match = re.search(r'Yaw:</b></td><td align=\'left\'>([+-]?\d+\.?\d*)°', text)
                        
                        if roll_match:
                            r = float(roll_match.group(1))
                        if pitch_match:
                            p = float(pitch_match.group(1))
                        if yaw_match:
                            y = float(yaw_match.group(1))
                except Exception as e:
                    print(f"Error parsing IMU data from label: {e}")
        
        # Get THP sensor data - fix for THPTemp, THPHum, THPPres
        if hasattr(self.main_window, 'thp_ctrl') and self.main_window.thp_ctrl is not None:
            # Try different methods to get THP data
            if hasattr(self.main_window.thp_ctrl, 'get_latest'):
                thp_data = self.main_window.thp_ctrl.get_latest()
                if thp_data:
                    thp_temp = thp_data.get('temperature', thp_temp)
                    thp_hum = thp_data.get('humidity', thp_hum)
                    thp_pres = thp_data.get('pressure', thp_pres)
            
            # Try direct attribute access
            if hasattr(self.main_window.thp_ctrl, 'latest'):
                thp_data = self.main_window.thp_ctrl.latest
                if thp_data:
                    thp_temp = thp_data.get('temperature', thp_temp)
                    thp_hum = thp_data.get('humidity', thp_hum)
                    thp_pres = thp_data.get('pressure', thp_pres)
            
            # Try to get from UI elements if available
            if thp_temp == 0 and hasattr(self.main_window.thp_ctrl, 'temp_display'):
                try:
                    thp_temp = float(self.main_window.thp_ctrl.temp_display.text().replace('°C', ''))
                except (ValueError, AttributeError):
                    pass
        
        if hasattr(self.main_window, 'filter_ctrl') and self.main_window.filter_ctrl is not None:
            if hasattr(self.main_window.filter_ctrl, 'current_position'):
                filter_pos = self.main_window.filter_ctrl.current_position
        
        if hasattr(self.main_window, 'temp_ctrl') and self.main_window.temp_ctrl is not None:
            if hasattr(self.main_window.temp_ctrl, 'current_temp'):
                tc_curr = self.main_window.temp_ctrl.current_temp
            if hasattr(self.main_window.temp_ctrl, 'setpoint'):
                tc_set = self.main_window.temp_ctrl.setpoint
            # New: Get auxiliary temperature (spectrometer temperature)
            if hasattr(self.main_window.temp_ctrl, 'auxiliary_temp'):
                spec_temp = self.main_window.temp_ctrl.auxiliary_temp
        
        if hasattr(self.main_window, 'spec_ctrl') and self.main_window.spec_ctrl is not None:
            if hasattr(self.main_window.spec_ctrl, 'current_integration_time_us'):
                integ_us = self.main_window.spec_ctrl.current_integration_time_us
        
        # New: Get routine code if a routine is running
        if hasattr(self.main_window, 'routine_manager') and self.main_window.routine_manager is not None:
            if hasattr(self.main_window.routine_manager, 'current_routine'):
                current_routine = self.main_window.routine_manager.current_routine
                if current_routine:
                    # Extract first two characters of routine name
                    routine_name = os.path.basename(current_routine)
                    if routine_name.endswith('.txt'):
                        routine_name = routine_name[:-4]  # Remove .txt extension
                    routine_code = routine_name[:2].upper() if len(routine_name) >= 2 else routine_name.upper()
        
        # Create CSV row
        row = [
            ts_csv, str(motor_angle), str(filter_pos),
            f"{r:.2f}", f"{p:.2f}", f"{y:.2f}", f"{ax:.2f}", f"{ay:.2f}", f"{az:.2f}",
            f"{mx:.2f}", f"{my:.2f}", f"{mz:.2f}",
            f"{pres:.2f}", f"{temp_env:.2f}", f"{tc_curr:.2f}", f"{tc_set:.2f}",
            f"{lat:.6f}", f"{lon:.6f}", str(integ_us), f"{thp_temp:.2f}",
            f"{thp_hum:.2f}", f"{thp_pres:.2f}", f"{spec_temp:.2f}", routine_code
        ]
        
        # Add averaged intensity values
        row.extend([f"{val:.4f}" for val in avg_intensities])
        
        return row

    def save_final_data(self, data, metadata=None):
        """Save final data from a completed routine with metadata"""
        if not data:
            return False
        
        try:
            # Create a timestamp for the filename
            ts = QDateTime.currentDateTime().toString("yyyyMMdd_hhmmss")
            final_csv_path = os.path.join(self.csv_dir, f"final_{ts}.csv")
            
            with open(final_csv_path, "w", encoding="utf-8", newline="") as f:
                # Write metadata header if provided
                if metadata and isinstance(metadata, dict):
                    for key, value in metadata.items():
                        f.write(f"# {key}: {value}\n")
                
                # Write column headers
                f.write("Pixel,Intensity\n")
                
                # Write data
                for i, intensity in enumerate(data):
                    f.write(f"{i},{intensity:.4f}\n")
            
            self.status_signal.emit(f"Saved final data to {final_csv_path}")
            return True
        except Exception as e:
            self.status_signal.emit(f"Error saving final data: {e}")
            return False
