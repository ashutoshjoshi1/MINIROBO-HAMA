import serial
import json
import time

def read_thp_sensor_data(port_name, baud_rate=9600, timeout=1):
    try:
        ser = serial.Serial(port_name, baud_rate, timeout=timeout)
        time.sleep(1)  # Allow time for serial connection to stabilize
        
        # Clear any pending data
        ser.reset_input_buffer()
        
        # Send command to request data
        ser.write(b'p\r\n')

        response = ""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if ser.in_waiting > 0:
                line = ser.readline().decode('utf-8', errors='replace').strip()
                response += line
                try:
                    data = json.loads(response)
                    # If we successfully parsed JSON, break the loop
                    break
                except json.JSONDecodeError:
                    # Continue reading if we don't have complete JSON yet
                    continue
        
        ser.close()
        
        # If we got no response at all
        if not response:
            print(f"THP sensor error: No response from sensor on {port_name}")
            return None
            
        # Try to parse the final response
        try:
            data = json.loads(response)
            sensors = data.get('Sensors', [])
            if sensors:
                s = sensors[0]
                return {
                    'sensor_id': s.get('ID'),
                    'temperature': s.get('Temperature'),
                    'humidity': s.get('Humidity'),
                    'pressure': s.get('Pressure')
                }
            else:
                print(f"THP sensor error: No sensor data in response: {response}")
                return None
        except json.JSONDecodeError as e:
            print(f"THP sensor error: Invalid JSON: {e}")
            print(f"Raw response: {repr(response)}")
            return None
    except Exception as e:
        print(f"THP sensor error: {e}")
        return None

