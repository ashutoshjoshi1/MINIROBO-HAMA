import sys
from PyQt5.QtWidgets import QApplication, QSplashScreen, QMessageBox
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import QTimer, Qt
from gui.main_window import MainWindow

def main():
    # Set high DPI attributes BEFORE creating QApplication
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    
    # Enable automatic scaling based on screen DPI
    QApplication.setAttribute(Qt.AA_UseDesktopOpenGL)
    
    # Now create the application
    app = QApplication(sys.argv)
    
    # Set application style for better cross-platform appearance
    app.setStyle('Fusion')  # Fusion style works well with custom stylesheets
    
    # Disable complex animations for better performance
    app.setEffectEnabled(Qt.UI_AnimateCombo, False)
    app.setEffectEnabled(Qt.UI_AnimateTooltip, False)
    
    # Set up exception handling for clean exit
    sys._excepthook = sys.excepthook
    def exception_hook(exctype, value, traceback):
        """Handle uncaught exceptions and show error message"""
        sys._excepthook(exctype, value, traceback)
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Critical)
        msg.setText("An unexpected error occurred")
        msg.setInformativeText(str(value))
        msg.setWindowTitle("Error")
        msg.exec_()
    sys.excepthook = exception_hook
    
    # Splash screen
    splash_pix = QPixmap("asset/splash.jpg")
    if not splash_pix.isNull():
        splash = QSplashScreen(splash_pix)
        splash.show()
        app.processEvents()
    
    # Create main window
    win = MainWindow()
    
    # Override the close behavior at the application level
    def confirm_exit():
        # This function will be called when the application is about to quit
        reply = QMessageBox.question(
            win, 'Exit Confirmation',
            'Do you want to quit?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # Stop spectrometer if active
            if hasattr(win, 'spec_ctrl') and win.spec_ctrl is not None:
                try:
                    if hasattr(win.spec_ctrl, 'measure_active') and win.spec_ctrl.measure_active:
                        win.statusBar().showMessage("Stopping spectrometer before exit...")
                        win.spec_ctrl.stop()
                except Exception as e:
                    print(f"Error stopping spectrometer: {e}")
            
            # Clean up resources
            if hasattr(win, 'continuous_saving') and win.continuous_saving:
                win.toggle_data_saving()
            
            if hasattr(win, 'csv_file') and win.csv_file:
                win.csv_file.close()
            if hasattr(win, 'log_file') and win.log_file:
                win.log_file.close()
            
            # Allow the application to quit
            QTimer.singleShot(500, app.quit)
        else:
            # Prevent the application from quitting
            app.setQuitOnLastWindowClosed(False)
            QTimer.singleShot(0, lambda: app.setQuitOnLastWindowClosed(True))
    
    # Connect the aboutToQuit signal to our handler
    app.aboutToQuit.connect(confirm_exit)
    
    win.show()
    
    if 'splash' in locals():
        splash.finish(win)
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()






