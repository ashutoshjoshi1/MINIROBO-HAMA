import cv2
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtGui import QImage, QPixmap

class CameraManager(QThread):
    """
    Manages the camera feed in a separate thread.
    """
    frame_ready = pyqtSignal(QImage)

    def __init__(self, camera_index=0):
        super().__init__()
        self.camera_index = camera_index
        self.running = False
        self.view = None

    def set_view(self, label):
        """Sets the QLabel to display the camera feed."""
        self.view = label
        self.frame_ready.connect(self.update_frame)

    def run(self):
        """Starts the camera feed."""
        self.running = True
        cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            print(f"Error: Could not open camera {self.camera_index}.")
            self.running = False
            return

        while self.running:
            ret, frame = cap.read()
            if ret:
                # Convert the image to RGB
                rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                # Convert to QImage
                h, w, ch = rgb_image.shape
                bytes_per_line = ch * w
                qt_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
                self.frame_ready.emit(qt_image)
            self.msleep(30)  # ~30 FPS

        cap.release()

    def update_frame(self, image):
        """Updates the QLabel with a new frame."""
        if self.view:
            pixmap = QPixmap.fromImage(image)
            self.view.setPixmap(pixmap.scaled(self.view.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def stop_camera(self):
        """Stops the camera feed."""
        self.running = False
        self.wait()

