class UIManager:
    """
    A helper class to manage UI state, like enabling/disabling widgets.
    (This is a placeholder for more complex UI management logic).
    """
    def __init__(self, main_window):
        self.main_window = main_window

    def set_busy_state(self, busy):
        """
        Disables controls when a routine is running.
        """
        self.main_window.left_panel.setEnabled(not busy)
        # You could add more granular control here, e.g.,
        # self.main_window.start_routine_button.setEnabled(not busy)
        # self.main_window.take_measurement_button.setEnabled(not busy)

    def update_on_connect(self, component_name, status):
        """
        Updates UI elements based on hardware connection status.
        """
        # This is an example of how you might centralize UI updates.
        # In the current implementation, this logic is in MainWindow.
        pass
