from PyQt5.QtCore import QObject
from PyQt5.QtWidgets import QApplication

class UIManager(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
    
    def setup_ui_style(self):
        """Set up the application style"""
        # Dark theme with blue accents
        self.main_window.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #2d2d30;
                color: #e0e0e0;
            }
            
            QGroupBox {
                border: 1px solid #3f3f46;
                border-radius: 5px;
                margin-top: 1ex;
                font-weight: bold;
                font-size: 11pt;
            }
            
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 5px;
                color: #e0e0e0;
            }
            
            QPushButton {
                background-color: #0078d7;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 5px 10px;
                font-size: 10pt;
            }
            
            QPushButton:hover {
                background-color: #1c86e0;
            }
            
            QPushButton:pressed {
                background-color: #005a9e;
            }
            
            QPushButton:disabled {
                background-color: #3f3f46;
                color: #9d9d9d;
            }
            
            QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox {
                background-color: #3f3f46;
                color: #e0e0e0;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 2px 5px;
                min-height: 20px;
            }
            
            QComboBox:hover, QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover {
                border: 1px solid #0078d7;
            }
            
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            
            QComboBox QAbstractItemView {
                background-color: #3f3f46;
                color: #e0e0e0;
                selection-background-color: #0078d7;
                selection-color: white;
            }
            
            QLabel {
                color: #e0e0e0;
            }
            
            QStatusBar {
                background-color: #1e1e1e;
                color: #e0e0e0;
                border-top: 1px solid #3f3f46;
            }
            
            QSplitter::handle {
                background-color: #3f3f46;
            }
            
            QSplitter::handle:horizontal {
                width: 2px;
            }
            
            QSplitter::handle:vertical {
                height: 2px;
            }
            
            QScrollBar:vertical {
                border: none;
                background: #2d2d30;
                width: 10px;
                margin: 0px;
            }
            
            QScrollBar::handle:vertical {
                background: #3f3f46;
                min-height: 20px;
                border-radius: 5px;
            }
            
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            
            QScrollBar:horizontal {
                border: none;
                background: #2d2d30;
                height: 10px;
                margin: 0px;
            }
            
            QScrollBar::handle:horizontal {
                background: #3f3f46;
                min-width: 20px;
                border-radius: 5px;
            }
            
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
            }
        """)
    
    def update_status_indicators(self, controller, connected):
        """Update the status indicators for a controller"""
        if not hasattr(controller, 'groupbox'):
            return
            
        color = "#4caf50" if connected else "#f44336"  # Green if connected, red if not
        title = controller.groupbox.title().replace("●", "").strip()
        controller.groupbox.setTitle(f"● {title}")
        controller.groupbox.setStyleSheet(f"""
            QGroupBox::title {{
                color: {color};
                font-weight: bold;
            }}
        """)
    
    def show_error_message(self, title, message):
        """Show an error message dialog"""
        from PyQt5.QtWidgets import QMessageBox
        error_box = QMessageBox(self.main_window)
        error_box.setIcon(QMessageBox.Critical)
        error_box.setWindowTitle(title)
        error_box.setText(message)
        error_box.setStandardButtons(QMessageBox.Ok)
        error_box.exec_()
    
    def show_info_message(self, title, message):
        """Show an information message dialog"""
        from PyQt5.QtWidgets import QMessageBox
        info_box = QMessageBox(self.main_window)
        info_box.setIcon(QMessageBox.Information)
        info_box.setWindowTitle(title)
        info_box.setText(message)
        info_box.setStandardButtons(QMessageBox.Ok)
        info_box.exec_()
    
    def show_confirmation_dialog(self, title, message):
        """Show a confirmation dialog and return True if confirmed"""
        from PyQt5.QtWidgets import QMessageBox
        confirm_box = QMessageBox(self.main_window)
        confirm_box.setIcon(QMessageBox.Question)
        confirm_box.setWindowTitle(title)
        confirm_box.setText(message)
        confirm_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        confirm_box.setDefaultButton(QMessageBox.No)
        return confirm_box.exec_() == QMessageBox.Yes