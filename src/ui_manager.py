# keglevel app
# ui_manager.py
import tkinter as tk
from ui_manager_base import MainUIBase, APP_REVISION
from popup_manager_mixin import PopupManagerMixin

try:
    from sensor_logic import IS_RASPBERRY_PI_MODE
except ImportError:
    IS_RASPBERRY_PI_MODE = False

class UIManager(MainUIBase, PopupManagerMixin):
    def __init__(self, root, settings_manager, sensor_logic, num_sensors, app_version_string):
        
        real_version = APP_REVISION
        
        # Initialize Main Dashboard
        # Note: MainUIBase expects (root, settings, sensor_logic, notif_svc, temp_logic, num_sensors, version)
        # We pass None for the removed services.
        MainUIBase.__init__(self, root, settings_manager, sensor_logic, None, None, num_sensors, real_version)
        
        # Initialize Popups
        PopupManagerMixin.__init__(self, settings_manager, num_sensors, real_version)

        # Setup Menu
        self._setup_menu_commands()

        # Link Callbacks
        if self.sensor_logic:
            self.sensor_logic.ui_callbacks = {
                "update_sensor_data_cb": self.update_sensor_data_display,
                "update_sensor_stability_cb": self.update_sensor_stability_display,
                "update_header_status_cb": self.update_header_status,
                "update_sensor_connection_status_cb": self.update_sensor_connection_status,
                "update_cal_data_cb": self.update_cal_popup_display 
            }
            
    def update_cal_popup_display(self, flow_rate_lpm, dispensed_pour_liters):
        self.ui_update_queue.put(("update_cal_data", (flow_rate_lpm, dispensed_pour_liters)))
