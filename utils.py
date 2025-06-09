import math, datetime, numpy as np
from astral import LocationInfo
from astral.sun import azimuth, elevation
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

def compute_sun_vector(lat,lon):
    now=datetime.datetime.now(datetime.timezone.utc)
    city=LocationInfo(latitude=lat,longitude=lon)
    az=azimuth(city.observer,now); el=elevation(city.observer,now)
    azr,elr=math.radians(az),math.radians(el)
    return math.cos(elr)*math.sin(azr), math.cos(elr)*math.cos(azr), math.sin(elr)

def draw_device_orientation(ax, roll, pitch, yaw, lat, lon):
    """
    Draw a speed camera-like object in 3D space with the given orientation
    """
    # Clear previous plot
    ax.clear()
    
    # Set axis limits and labels
    ax.set_xlim(-1, 1)
    ax.set_ylim(-1, 1)
    ax.set_zlim(-1, 1)
    ax.set_xlabel('X')
    ax.set_ylabel('Y')
    ax.set_zlabel('Z')
    
    # Create rotation matrices using NumPy
    import numpy as np
    
    # Convert degrees to radians
    roll_rad = np.radians(roll)
    pitch_rad = np.radians(pitch)
    yaw_rad = np.radians(yaw)
    
    # Create rotation matrices
    def rotation_matrix_x(angle):
        return np.array([
            [1, 0, 0],
            [0, np.cos(angle), -np.sin(angle)],
            [0, np.sin(angle), np.cos(angle)]
        ])
    
    def rotation_matrix_y(angle):
        return np.array([
            [np.cos(angle), 0, np.sin(angle)],
            [0, 1, 0],
            [-np.sin(angle), 0, np.cos(angle)]
        ])
    
    def rotation_matrix_z(angle):
        return np.array([
            [np.cos(angle), -np.sin(angle), 0],
            [np.sin(angle), np.cos(angle), 0],
            [0, 0, 1]
        ])
    
    # Combine rotations (roll, pitch, yaw)
    R_x = rotation_matrix_x(roll_rad)
    R_y = rotation_matrix_y(pitch_rad)
    R_z = rotation_matrix_z(yaw_rad)
    R = np.dot(R_z, np.dot(R_y, R_x))
    
    # Define speed camera shape (simplified)
    # Main body - rectangular prism
    l, w, h = 0.5, 0.3, 0.2  # length, width, height
    
    # Define the corners of the camera body
    corners = np.array([
        [-l/2, -w/2, -h/2],  # bottom rectangle
        [l/2, -w/2, -h/2],
        [l/2, w/2, -h/2],
        [-l/2, w/2, -h/2],
        [-l/2, -w/2, h/2],   # top rectangle
        [l/2, -w/2, h/2],
        [l/2, w/2, h/2],
        [-l/2, w/2, h/2]
    ])
    
    # Lens - small cylinder at front
    lens_center = np.array([l/2 + 0.1, 0, 0])
    
    # Apply rotation to all points
    rotated_corners = np.array([np.dot(R, corner) for corner in corners])
    rotated_lens_center = np.dot(R, lens_center)
    
    # Draw the camera body (connect the corners)
    # Bottom face
    ax.plot3D(rotated_corners[[0, 1, 2, 3, 0], 0], 
              rotated_corners[[0, 1, 2, 3, 0], 1], 
              rotated_corners[[0, 1, 2, 3, 0], 2], 'b-')
    # Top face
    ax.plot3D(rotated_corners[[4, 5, 6, 7, 4], 0], 
              rotated_corners[[4, 5, 6, 7, 4], 1], 
              rotated_corners[[4, 5, 6, 7, 4], 2], 'b-')
    # Connect top and bottom
    for i in range(4):
        ax.plot3D(rotated_corners[[i, i+4], 0], 
                  rotated_corners[[i, i+4], 1], 
                  rotated_corners[[i, i+4], 2], 'b-')
    
    # Draw lens (simplified as a point)
    ax.scatter(rotated_lens_center[0], rotated_lens_center[1], rotated_lens_center[2], 
               color='black', s=50)
    
    # Add direction indicator (arrow pointing forward)
    arrow_start = np.array([0, 0, 0])
    arrow_end = np.array([0.4, 0, 0])  # Forward direction
    rotated_arrow_start = np.dot(R, arrow_start)
    rotated_arrow_end = np.dot(R, arrow_end)
    
    ax.quiver(rotated_arrow_start[0], rotated_arrow_start[1], rotated_arrow_start[2],
              rotated_arrow_end[0]-rotated_arrow_start[0], 
              rotated_arrow_end[1]-rotated_arrow_start[1], 
              rotated_arrow_end[2]-rotated_arrow_start[2],
              color='r', arrow_length_ratio=0.2)
    
    # Set title with orientation info
    ax.set_title(f"R:{roll:.1f}° P:{pitch:.1f}° Y:{yaw:.1f}°", fontsize=8)
    
    # Equal aspect ratio
    ax.set_box_aspect([1, 1, 1])


try:
    import libscrc
    def modbus_crc16(data: bytes) -> int:
        return libscrc.modbus(data)
except ImportError:
    def modbus_crc16(data: bytes) -> int:
        crc = 0xFFFF
        for b in data:
            crc ^= b
            for _ in range(8):
                if crc & 1:
                    crc = (crc >> 1) ^ 0xA001
                else:
                    crc >>= 1
        return crc & 0xFFFF

