# keglevel app
# ui_manager_base.py
import tkinter as tk
from tkinter import ttk, messagebox
import tkinter.font as tkfont 
import math
import os
import sys      

try:
    from sensor_logic import IS_RASPBERRY_PI_MODE
except ImportError:
    IS_RASPBERRY_PI_MODE = False

try:
    from settings_manager import UNASSIGNED_KEG_ID, UNASSIGNED_BEVERAGE_ID
except ImportError:
    UNASSIGNED_KEG_ID = "unassigned_keg_id"
    UNASSIGNED_BEVERAGE_ID = "unassigned_beverage_id"

APP_REVISION = "V1.0-Lite"

class MainUIBase:
    def __init__(self, root, settings_manager, sensor_logic, notification_service, temp_logic, num_sensors, app_version_string):
        self.root = root
        self.settings_manager = settings_manager
        self.sensor_logic = sensor_logic
        self.num_sensors = num_sensors
        self.app_version = app_version_string
        
        self.root.title(f"Keg Level Monitor {self.app_version}")
        
        # Safe Colors
        self.color_bg = "#212121"
        self.color_fg = "#FFFFFF"
        self.color_accent = "#FFC107" # Amber
        self.color_danger = "#F44336" # Red
        self.color_success = "#4CAF50" # Green
        
        self.root.configure(bg=self.color_bg)
        
        # Queues for Thread Safety
        import queue
        self.ui_update_queue = queue.Queue()
        
        # Build UI
        self._setup_fonts()
        self._setup_ui()
        self._start_ui_update_loop()
        
    def _setup_fonts(self):
        self.font_header = tkfont.Font(family="Arial", size=14, weight="bold")
        self.font_label = tkfont.Font(family="Arial", size=12)
        self.font_value = tkfont.Font(family="Arial", size=16, weight="bold")
        # Added missing font from previous fix
        self.menu_heading_font = tkfont.Font(family="Arial", size=10, weight="bold", slant="italic")
        
    def _setup_ui(self):
        # 1. Menu Bar (Placeholder for child class to populate)
        self.menu_bar = tk.Menu(self.root)
        self.root.config(menu=self.menu_bar)
        self.settings_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label="Menu", menu=self.settings_menu)
        
        # 2. Main Container
        self.main_container = tk.Frame(self.root, bg=self.color_bg)
        self.main_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 3. Sensor Grid
        self.sensor_frames = []
        self.sensor_vars = [] # Stores StringVars for (Title, Amount, Status, Flow)
        
        displayed_taps = self.settings_manager.get_displayed_taps()
        cols = 3 
        rows = math.ceil(displayed_taps / cols)
        
        for i in range(displayed_taps):
            frame = tk.Frame(self.main_container, bg="#333333", relief="raised", bd=2)
            frame.grid(row=i//cols, column=i%cols, padx=5, pady=5, sticky="nsew")
            
            # Allow grid to expand
            self.main_container.grid_columnconfigure(i%cols, weight=1)
            self.main_container.grid_rowconfigure(i//cols, weight=1)
            
            vars_dict = {
                "title": tk.StringVar(value=f"Tap {i+1}"),
                "beverage": tk.StringVar(value="Empty"),
                "remaining": tk.StringVar(value="--"),
                "flow": tk.StringVar(value=""),
                "status": tk.StringVar(value="Idle"),
                "progress": tk.DoubleVar(value=0.0)
            }
            self.sensor_vars.append(vars_dict)
            self.sensor_frames.append(frame)
            
            # --- Draw Sensor Card ---
            tk.Label(frame, textvariable=vars_dict["title"], bg="#333333", fg=self.color_accent, font=self.font_header).pack(pady=(5,0))
            tk.Label(frame, textvariable=vars_dict["beverage"], bg="#333333", fg="white", font=self.font_label).pack()
            
            # Progress Bar
            pb = ttk.Progressbar(frame, variable=vars_dict["progress"], maximum=100)
            pb.pack(fill="x", padx=10, pady=5)
            
            # Stats
            stats_frame = tk.Frame(frame, bg="#333333")
            stats_frame.pack(fill="x", padx=10)
            
            tk.Label(stats_frame, text="Remaining:", bg="#333333", fg="#AAAAAA").pack(anchor="w")
            tk.Label(stats_frame, textvariable=vars_dict["remaining"], bg="#333333", fg="white", font=self.font_value).pack(anchor="w")
            
            tk.Label(stats_frame, textvariable=vars_dict["status"], bg="#333333", fg=self.color_success, font=("Arial", 10, "bold")).pack(anchor="e", pady=(5,0))
            tk.Label(stats_frame, textvariable=vars_dict["flow"], bg="#333333", fg="#AAAAAA", font=("Arial", 9)).pack(anchor="e")
            
            # Initial Data Load
            self._refresh_tap_metadata(i)

    def _start_ui_update_loop(self):
        """Checks the queue for updates from background threads."""
        try:
            while True:
                task = self.ui_update_queue.get_nowait()
                cmd, args = task[0], task[1]
                if cmd == "update_cal_data":
                    pass # Handled by mixin usually, but safe to ignore if popup closed
        except:
            pass
        finally:
            self.root.after(100, self._start_ui_update_loop)

    def update_sensor_data_display(self, sensor_index, flow_rate_lpm, remaining_liters, status, last_pour_vol):
        """Called by SensorLogic via callback."""
        if sensor_index >= len(self.sensor_vars): return
        
        vars_dict = self.sensor_vars[sensor_index]
        
        # 1. Update Numeric
        display_units = self.settings_manager.get_display_units()
        is_metric = (display_units == "metric")
        
        if is_metric:
            rem_str = f"{remaining_liters:.2f} L"
            flow_str = f"{flow_rate_lpm:.2f} L/m" if flow_rate_lpm > 0 else f"Last: {last_pour_vol:.2f} L"
        else:
            rem_gal = remaining_liters * 0.264172
            rem_str = f"{rem_gal:.2f} Gal"
            flow_str = f"{flow_rate_lpm:.2f} L/m" if flow_rate_lpm > 0 else f"Last: {(last_pour_vol * 33.814):.1f} oz"
            
        vars_dict["remaining"].set(rem_str)
        vars_dict["flow"].set(flow_str)
        vars_dict["status"].set(status)
        
        # 2. Update Progress Bar
        keg_id = self.settings_manager.get_sensor_keg_assignments()[sensor_index]
        if keg_id and keg_id != UNASSIGNED_KEG_ID:
            keg = self.settings_manager.get_keg_by_id(keg_id)
            if keg:
                start_vol = keg.get('calculated_starting_volume_liters', 1.0)
                if start_vol <= 0: start_vol = 1.0
                pct = (remaining_liters / start_vol) * 100.0
                vars_dict["progress"].set(max(0, min(100, pct)))
        else:
            vars_dict["progress"].set(0)

    def _refresh_tap_metadata(self, sensor_index):
        if sensor_index >= len(self.sensor_vars): return
        
        assignments = self.settings_manager.get_sensor_keg_assignments()
        beverage_assignments = self.settings_manager.get_sensor_beverage_assignments()
        beverage_lib = self.settings_manager.get_beverage_library().get('beverages', [])
        
        keg_id = assignments[sensor_index]
        beverage_id = beverage_assignments[sensor_index]
        
        beverage = next((b for b in beverage_lib if b['id'] == beverage_id), None)
        beverage_name = beverage['name'] if beverage else "Empty"
        
        self.sensor_vars[sensor_index]["beverage"].set(beverage_name)
        
        if keg_id == UNASSIGNED_KEG_ID:
             self.sensor_vars[sensor_index]["title"].set(f"Tap {sensor_index+1} (OFF)")
        else:
             keg = self.settings_manager.get_keg_by_id(keg_id)
             title = keg['title'] if keg else f"Tap {sensor_index+1}"
             self.sensor_vars[sensor_index]["title"].set(title)

    # --- Stubs for callbacks required by Logic but not used in Lite ---
    def update_sensor_stability_display(self, *args): pass
    def update_header_status(self, *args): pass
    def update_sensor_connection_status(self, *args): pass
    def _refresh_ui_for_settings_or_resume(self):
        # Refresh all cards
        for i in range(len(self.sensor_vars)):
            self._refresh_tap_metadata(i)
            # Re-read last known values from logic if possible, or just wait for next update
            if self.sensor_logic:
                 rem = self.sensor_logic.last_known_remaining_liters[i]
                 last = self.sensor_logic.last_pour_volumes[i]
                 self.update_sensor_data_display(i, 0.0, rem, "Idle", last)

    # --- ADDED: The missing run() method ---
    def run(self):
        """Starts the Tkinter main event loop."""
        self.root.mainloop()
