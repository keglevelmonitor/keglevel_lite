# keglevel app
# main_kivy.py
import os
import threading
import uuid
import subprocess
import sys

# --- 1. KIVY CONFIGURATION ---
from kivy.config import Config
Config.set('graphics', 'width', '800')
Config.set('graphics', 'height', '417')
Config.set('graphics', 'resizable', '0')

from kivy.app import App
from kivy.clock import Clock
from kivy.lang import Builder
from kivy.uix.screenmanager import ScreenManager, Screen, SlideTransition, NoTransition
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup
from kivy.uix.widget import Widget
from kivy.uix.behaviors import ButtonBehavior
from kivy.properties import StringProperty, NumericProperty, ObjectProperty, ListProperty, BooleanProperty
from kivy.utils import get_color_from_hex

# --- 2. IMPORT BACKEND LOGIC ---
from settings_manager import SettingsManager, UNASSIGNED_KEG_ID, UNASSIGNED_BEVERAGE_ID
from sensor_logic import SensorLogic, FLOW_SENSOR_PINS

# Special flag for the "Keg Kicked" action
KEG_KICKED_ID = "keg_kicked_action"

# Constants for Unit Conversion
KG_TO_LBS = 2.20462
LITERS_TO_GAL = 0.264172

# --- SRM COLOR LOGIC ---
def get_srm_color_rgba(srm):
    """Returns Kivy RGBA tuple for a given SRM (0-40). 0=White/Water."""
    if srm is None or srm < 0: return (1, 0.75, 0, 1) # Default Amber fallback
    srm_hex_map = {
        0: "#FFFFFF", 1: "#FFE699", 2: "#FFD878", 3: "#FFCA5A", 4: "#FFBF42", 5: "#FBB123",
        6: "#F8A600", 7: "#F39C00", 8: "#EA8F00", 9: "#E58500", 10: "#DE7C00", 11: "#D77200",
        12: "#CF6900", 13: "#CB6200", 14: "#C35900", 15: "#BB5100", 16: "#B54C00", 17: "#B04500",
        18: "#A63E00", 19: "#A13700", 20: "#9B3200", 21: "#962D00", 22: "#8F2900", 23: "#882300",
        24: "#821E00", 25: "#7B1A00", 26: "#771900", 27: "#701400", 28: "#6A0E00", 29: "#660D00",
        30: "#5E0B00", 31: "#5A0A02", 32: "#600903", 33: "#520907", 34: "#4C0505", 35: "#470606",
        36: "#440607", 37: "#3F0708", 38: "#3B0607", 39: "#3A070B", 40: "#36080A"
    }
    lookup_val = int(srm)
    if lookup_val > 40: lookup_val = 40
    if lookup_val < 0: lookup_val = 0
    hex_color = srm_hex_map.get(lookup_val, "#E5A128")
    return get_color_from_hex(hex_color)

# --- 3. WIDGET LOGIC CLASSES ---

class LevelGauge(Widget):
    percent = NumericProperty(0)
    liquid_color = ListProperty([1, 0.75, 0, 1])

class TapWidget(ButtonBehavior, BoxLayout):
    tap_index = NumericProperty(0)
    tap_title = StringProperty("Tap ?")
    beverage_name = StringProperty("Empty")
    stats_text = StringProperty("") 
    liquid_color = ListProperty([1, 0.75, 0, 1])
    percent_full = NumericProperty(0)
    remaining_text = StringProperty("-- L")
    status_text = StringProperty("Idle")
    
    def on_release(self):
        app = App.get_running_app()
        app.open_tap_selector(self.tap_index)

class KegListItem(BoxLayout):
    title = StringProperty()
    contents = StringProperty()
    keg_id = StringProperty()
    index = NumericProperty(0)

class BeverageListItem(BoxLayout):
    name = StringProperty()
    bev_id = StringProperty()
    index = NumericProperty(0)

class KegSelectPopup(Popup):
    pass

class SettingsConfigTab(BoxLayout):
    """Logic for the Configuration Tab."""
    def init_ui(self):
        app = App.get_running_app()
        units = app.settings_manager.get_display_units()
        if units == 'imperial':
            self.ids.btn_imperial.state = 'down'
            self.ids.btn_metric.state = 'normal'
        else:
            self.ids.btn_metric.state = 'down'
            self.ids.btn_imperial.state = 'normal'
        taps = app.settings_manager.get_displayed_taps()
        self.ids.spin_taps.text = str(taps)

    def save_config(self):
        app = App.get_running_app()
        # Use button state, not checkbox active
        new_units = 'imperial' if self.ids.btn_imperial.state == 'down' else 'metric'
        app.settings_manager.save_display_units(new_units)
        try:
            new_taps = int(self.ids.spin_taps.text)
            app.settings_manager.save_displayed_taps(new_taps)
        except ValueError: pass
        app.apply_config_changes()
        app.root.current = 'dashboard'

class SettingsUpdatesTab(BoxLayout):
    """Logic for System Updates."""
    log_text = StringProperty("Ready to check for updates.\n")
    is_working = BooleanProperty(False)
    install_enabled = BooleanProperty(False)

    def check_updates(self):
        self.log_text = "Checking for updates...\n"
        self.is_working = True
        self.install_enabled = False
        threading.Thread(target=self._run_update_process, args=(["--check"], True)).start()

    def install_updates(self):
        self.log_text += "\nStarting Install Process...\n"
        self.is_working = True
        self.install_enabled = False
        threading.Thread(target=self._run_update_process, args=([], False)).start()

    def restart_app(self):
        """Safely restarts the application."""
        app = App.get_running_app()
        print("[System] Restarting application...")
        
        # 1. Stop background threads
        if hasattr(app, 'sensor_logic') and app.sensor_logic:
            app.sensor_logic.stop_monitoring()
            app.sensor_logic.cleanup_gpio()
            
        # 2. Exec new process
        python = sys.executable
        script = os.path.abspath(sys.argv[0])
        args = sys.argv[1:]
        # This replaces the current process with a new one
        os.execv(python, [python, script] + args)

    def _run_update_process(self, flags, is_check_mode):
        """Runs the bash script in background."""
        # Locate update.sh in project root (one level up from src)
        src_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(src_dir)
        script_path = os.path.join(project_root, "update.sh")

        if not os.path.exists(script_path):
            self._append_log(f"Error: Script not found at {script_path}\n")
            self._finish_work(False)
            return

        cmd = ["bash", script_path] + flags
        try:
            # Run process and capture output line-by-line
            process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT, 
                text=True, 
                bufsize=1
            )
            
            update_available = False
            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None: break
                if line:
                    self._append_log(line)
                    # Heuristic to detect availability based on script output
                    if "Update Available!" in line: update_available = True

            return_code = process.poll()

            if is_check_mode:
                if update_available:
                    self._append_log("\n[Result] Update Available! Click Install.")
                    self._finish_work(True)
                else:
                    self._append_log("\n[Result] Up to date.")
                    self._finish_work(False)
            else:
                if return_code == 0:
                    self._append_log("\n[Complete] Update Installed. Please Restart.")
                else:
                    self._append_log(f"\n[Error] Update failed with code {return_code}.")
                self._finish_work(False)

        except Exception as e:
            self._append_log(f"\n[Error] {e}\n")
            self._finish_work(False)

    def _append_log(self, text):
        Clock.schedule_once(lambda dt: setattr(self, 'log_text', self.log_text + text))

    def _finish_work(self, enable_install):
        def _reset(dt):
            self.is_working = False
            self.install_enabled = enable_install
        Clock.schedule_once(_reset)

class InventoryScreen(Screen):
    def show_kegs(self):
        self.ids.tab_manager.current = 'tab_kegs'
    def show_bevs(self):
        self.ids.tab_manager.current = 'tab_bevs'
    def add_new_item(self):
        app = App.get_running_app()
        current = self.ids.tab_manager.current
        if current == 'tab_kegs': app.open_keg_edit(None)
        else: app.open_beverage_edit(None)

class SettingsScreen(Screen):
    def show_cal(self):
        self.ids.settings_manager.current = 'tab_cal'
    def show_conf(self):
        self.ids.settings_manager.current = 'tab_conf'
        self.ids.tab_conf_content.init_ui()
    def show_upd(self):
        self.ids.settings_manager.current = 'tab_upd'
    def show_about(self):
        self.ids.settings_manager.current = 'tab_about'

class KegEditScreen(Screen):
    screen_title = StringProperty("Edit Keg")
    keg_id = StringProperty("")
    beverage_name = StringProperty("Select Beverage")
    beverage_list = ListProperty([])
    max_volume_liters = NumericProperty(19.0)
    tare_weight_kg = NumericProperty(4.5)
    total_weight_kg = NumericProperty(23.5)
    ui_max_vol_text = StringProperty("")
    ui_tare_text = StringProperty("")
    ui_total_text = StringProperty("")
    ui_calculated_text = StringProperty("")
    is_metric = True

    def on_pre_enter(self):
        app = App.get_running_app()
        if app:
            units = app.settings_manager.get_display_units()
            self.is_metric = (units == "metric")
            self.update_display_labels()

    def update_display_labels(self, *args):
        app = App.get_running_app()
        if not app: return
        vol_liters = app.settings_manager._calculate_volume_from_weight(
            self.total_weight_kg, self.tare_weight_kg
        )
        if self.is_metric:
            self.ui_max_vol_text = f"{self.max_volume_liters:.1f} L"
            self.ui_tare_text = f"{self.tare_weight_kg:.2f} kg"
            self.ui_total_text = f"{self.total_weight_kg:.2f} kg"
            self.ui_calculated_text = f"{vol_liters:.2f} L"
        else:
            self.ui_max_vol_text = f"{(self.max_volume_liters * LITERS_TO_GAL):.1f} Gal"
            self.ui_tare_text = f"{(self.tare_weight_kg * KG_TO_LBS):.1f} lb"
            self.ui_total_text = f"{(self.total_weight_kg * KG_TO_LBS):.1f} lb"
            self.ui_calculated_text = f"{(vol_liters * LITERS_TO_GAL):.2f} Gal"

    def set_max_volume_from_slider(self, value):
        self.max_volume_liters = value
        self.update_display_labels()
    def set_tare_from_slider(self, value):
        self.tare_weight_kg = value
        if self.total_weight_kg < self.tare_weight_kg: self.total_weight_kg = self.tare_weight_kg
        self.update_display_labels()
    def set_total_from_slider(self, value):
        self.total_weight_kg = value
        if self.total_weight_kg < self.tare_weight_kg: self.tare_weight_kg = self.total_weight_kg
        self.update_display_labels()

class BeverageEditScreen(Screen):
    screen_title = StringProperty("Edit Beverage")
    bev_id = StringProperty("")
    bev_name = StringProperty("")
    bev_style = StringProperty("")
    bev_abv = StringProperty("")
    bev_ibu = StringProperty("")
    bev_srm = NumericProperty(5)
    preview_color = ListProperty([1, 0.75, 0, 1])
    def on_bev_srm(self, instance, value):
        self.preview_color = get_srm_color_rgba(int(value))

class DashboardScreen(Screen): pass

# --- 4. MAIN APP CLASS ---

class KegLevelApp(App):
    def build(self):
        self.title = "KegLevel Lite"
        self.settings_manager = SettingsManager(len(FLOW_SENSOR_PINS))
        self.num_sensors = self.settings_manager.get_displayed_taps()
        Builder.load_file('keglevel_ui.kv')
        self.sm = ScreenManager(transition=SlideTransition())
        self.dashboard_screen = DashboardScreen(name='dashboard')
        self.inventory_screen = InventoryScreen(name='inventory')
        self.keg_edit_screen = KegEditScreen(name='keg_edit')
        self.bev_edit_screen = BeverageEditScreen(name='bev_edit')
        self.settings_screen = SettingsScreen(name='settings')
        
        self.sm.add_widget(self.dashboard_screen)
        self.sm.add_widget(self.inventory_screen)
        self.sm.add_widget(self.keg_edit_screen)
        self.sm.add_widget(self.bev_edit_screen)
        self.sm.add_widget(self.settings_screen)
        
        self.tap_widgets = []
        tap_container = self.dashboard_screen.ids.tap_container
        tap_container.clear_widgets()
        for i in range(self.num_sensors):
            widget = TapWidget()
            widget.tap_index = i
            tap_container.add_widget(widget)
            self.tap_widgets.append(widget)
        return self.sm

    def on_start(self):
        def bridge_callback(idx, rate, rem, status, pour_vol):
            Clock.schedule_once(lambda dt: self.update_tap_ui(idx, rate, rem, status, pour_vol))
        callbacks = {"update_sensor_data_cb": bridge_callback, "update_cal_data_cb": lambda x, y: None}
        self.sensor_logic = SensorLogic(self.num_sensors, callbacks, self.settings_manager)
        self.refresh_dashboard_metadata()
        self.refresh_keg_list()
        self.refresh_beverage_list()
        self.sensor_logic.start_monitoring()

    def update_tap_ui(self, idx, rate, rem, status, pour_vol):
        if idx >= len(self.tap_widgets): return
        widget = self.tap_widgets[idx]
        keg_id = self.sensor_logic.keg_ids_assigned[idx]
        is_offline = (not keg_id) or (keg_id == UNASSIGNED_KEG_ID)
        
        if is_offline:
            widget.status_text = "OFFLINE"
            widget.remaining_text = "--"
            widget.percent_full = 0
            return
            
        units = self.settings_manager.get_display_units()
        if units == "metric": widget.remaining_text = f"{rem:.2f} L"
        else: widget.remaining_text = f"{(rem * LITERS_TO_GAL):.2f} Gal"
        
        if rate > 0: widget.status_text = "Pouring"
        else: widget.status_text = "Idle"

        keg = self.settings_manager.get_keg_by_id(keg_id)
        max_vol = keg.get('maximum_full_volume_liters', 19.0) if keg else 19.0
        if max_vol <= 0: max_vol = 19.0
        percent = (rem / max_vol) * 100.0
        widget.percent_full = max(0, min(100, percent))

    def refresh_dashboard_metadata(self):
        assignments = self.settings_manager.get_sensor_keg_assignments()
        bev_assigns = self.settings_manager.get_sensor_beverage_assignments()
        bev_lib = self.settings_manager.get_beverage_library().get('beverages', [])
        
        for i, widget in enumerate(self.tap_widgets):
            widget.tap_title = f"Tap {i+1}"
            k_id = assignments[i] if i < len(assignments) else None
            
            if not k_id or k_id == UNASSIGNED_KEG_ID:
                widget.beverage_name = "No Keg"
                widget.stats_text = ""
                widget.liquid_color = (0.2, 0.2, 0.2, 1) # Dark grey for empty
            else:
                found_keg = self.settings_manager.get_keg_by_id(k_id)
                b_id = bev_assigns[i] if i < len(bev_assigns) else None
                found_bev = next((b for b in bev_lib if b['id'] == b_id), None)
                
                if found_bev:
                    widget.beverage_name = found_bev['name']
                    abv = found_bev.get('abv', '?')
                    ibu = found_bev.get('ibu', '?')
                    widget.stats_text = f"{abv}% ABV  •  {ibu} IBU"
                    
                    srm = found_bev.get('srm')
                    try: srm = int(srm)
                    except: srm = 5
                    widget.liquid_color = get_srm_color_rgba(srm)
                else:
                    widget.beverage_name = "Empty"
                    widget.stats_text = ""
                    widget.liquid_color = (1, 0.75, 0, 1)

    def refresh_keg_list(self):
        kegs = self.settings_manager.get_keg_definitions()
        bev_lib = self.settings_manager.get_beverage_library().get('beverages', [])
        bev_map = {b['id']: b['name'] for b in bev_lib}
        data_list = []
        for i, keg in enumerate(kegs):
            b_id = keg.get('beverage_id')
            b_name = bev_map.get(b_id, "Empty")
            data_list.append({
                'title': keg.get('title', 'Unknown'),
                'contents': b_name,
                'keg_id': keg.get('id'),
                'index': i
            })
        self.inventory_screen.ids.kegs_tab.ids.rv_kegs.data = data_list

    def refresh_beverage_list(self):
        bevs = self.settings_manager.get_beverage_library().get('beverages', [])
        bevs = sorted(bevs, key=lambda x: x.get('name', '').lower())
        data_list = []
        for i, b in enumerate(bevs):
            data_list.append({
                'name': b.get('name', 'Unknown'),
                'bev_id': b.get('id'),
                'index': i
            })
        self.inventory_screen.ids.bevs_tab.ids.rv_bevs.data = data_list

    def open_tap_selector(self, tap_index):
        popup = KegSelectPopup(title=f"Select Keg for Tap {tap_index+1}")
        all_kegs = self.settings_manager.get_keg_definitions()
        assignments = self.settings_manager.get_sensor_keg_assignments()
        assigned_set = set(assignments)
        
        data_list = []
        current_keg = assignments[tap_index]
        if current_keg and current_keg != UNASSIGNED_KEG_ID:
            data_list.append({
                'text': "[ ! ]  KEG KICKED (CALIBRATE)  [ ! ]",
                'background_color': (0.35, 0.35, 0.35, 1),
                'on_release': lambda: self.select_keg_for_tap(tap_index, KEG_KICKED_ID, popup)
            })
        data_list.append({
            'text': "[ Disconnect Tap ]",
            'background_color': (0.2, 0.2, 0.2, 1),
            'on_release': lambda: self.select_keg_for_tap(tap_index, UNASSIGNED_KEG_ID, popup)
        })
        for keg in all_kegs:
            k_id = keg['id']
            if (k_id not in assigned_set) or (assignments[tap_index] == k_id):
                b_id = keg.get('beverage_id')
                bev_lib = self.settings_manager.get_beverage_library().get('beverages', [])
                found_bev = next((b for b in bev_lib if b['id'] == b_id), None)
                b_name = found_bev['name'] if found_bev else "Empty"
                
                start = keg.get('maximum_full_volume_liters', 0)
                disp = keg.get('current_dispensed_liters', 0)
                rem = max(0, start - disp)
                
                units = self.settings_manager.get_display_units()
                vol_str = f"{rem:.1f}L" if units == "metric" else f"{(rem * LITERS_TO_GAL):.1f}Gal"
                
                data_list.append({
                    'text': f"{keg['title']} ({b_name}) - {vol_str}",
                    'background_color': (0.2, 0.2, 0.2, 1),
                    'on_release': lambda x=k_id: self.select_keg_for_tap(tap_index, x, popup)
                })
        popup.ids.rv_select.data = data_list
        popup.open()

    def select_keg_for_tap(self, tap_index, keg_id, popup_instance):
        popup_instance.dismiss()
        if keg_id == KEG_KICKED_ID:
            print(f"TODO: Trigger Calibration for Tap {tap_index}")
            keg_id = UNASSIGNED_KEG_ID
        self.settings_manager.save_sensor_keg_assignment(tap_index, keg_id)
        if keg_id == UNASSIGNED_KEG_ID:
            self.settings_manager.save_sensor_beverage_assignment(tap_index, UNASSIGNED_BEVERAGE_ID)
        else:
            keg = self.settings_manager.get_keg_by_id(keg_id)
            b_id = keg.get('beverage_id', UNASSIGNED_BEVERAGE_ID)
            self.settings_manager.save_sensor_beverage_assignment(tap_index, b_id)
        self.sensor_logic.force_recalculation()
        self.refresh_dashboard_metadata()
        self.update_tap_ui(tap_index, 0, 0, "Idle", 0)

    # --- Actions: KEGS ---
    def open_keg_edit(self, keg_id):
        self.inventory_screen.show_kegs()
        bev_lib = self.settings_manager.get_beverage_library().get('beverages', [])
        bev_names = sorted([b['name'] for b in bev_lib])
        self.keg_edit_screen.beverage_list = ["Empty"] + bev_names
        
        if keg_id:
            self.keg_edit_screen.screen_title = "Edit Keg"
            self.keg_edit_screen.keg_id = keg_id
            keg = self.settings_manager.get_keg_by_id(keg_id)
            b_id = keg.get('beverage_id')
            found_bev = next((b for b in bev_lib if b['id'] == b_id), None)
            self.keg_edit_screen.beverage_name = found_bev['name'] if found_bev else "Empty"
            self.keg_edit_screen.max_volume_liters = float(keg.get('maximum_full_volume_liters', 19.0))
            self.keg_edit_screen.tare_weight_kg = float(keg.get('tare_weight_kg', 4.5))
            self.keg_edit_screen.total_weight_kg = float(keg.get('starting_total_weight_kg', 4.5))
        else:
            self.keg_edit_screen.screen_title = "Add New Keg"
            self.keg_edit_screen.keg_id = "" 
            self.keg_edit_screen.beverage_name = "Empty"
            self.keg_edit_screen.max_volume_liters = 19.0
            self.keg_edit_screen.tare_weight_kg = 4.5
            self.keg_edit_screen.total_weight_kg = 23.5
        self.keg_edit_screen.update_display_labels()
        self.root.current = 'keg_edit'

    def save_keg_edit(self):
        scr = self.keg_edit_screen
        bev_name = scr.beverage_name
        bev_id = UNASSIGNED_BEVERAGE_ID
        if bev_name != "Empty":
            bev_lib = self.settings_manager.get_beverage_library().get('beverages', [])
            found = next((b for b in bev_lib if b['name'] == bev_name), None)
            if found: bev_id = found['id']
        vol_liters = self.settings_manager._calculate_volume_from_weight(scr.total_weight_kg, scr.tare_weight_kg)
        is_new = (scr.keg_id == "")
        new_keg_id = scr.keg_id if not is_new else str(uuid.uuid4())
        if is_new:
            existing_count = len(self.settings_manager.get_keg_definitions())
            title = f"Keg {existing_count + 1:02}"
        else:
            old_keg = self.settings_manager.get_keg_by_id(new_keg_id)
            title = old_keg['title']
        keg_data = {
            "id": new_keg_id,
            "title": title,
            "tare_weight_kg": float(scr.tare_weight_kg),
            "starting_total_weight_kg": float(scr.total_weight_kg),
            "maximum_full_volume_liters": float(scr.max_volume_liters),
            "calculated_starting_volume_liters": vol_liters,
            "beverage_id": bev_id,
            "current_dispensed_liters": 0.0, 
            "total_dispensed_pulses": 0,
            "fill_date": ""
        }
        all_kegs = self.settings_manager.get_keg_definitions()
        if is_new: all_kegs.append(keg_data)
        else:
            for i, k in enumerate(all_kegs):
                if k['id'] == new_keg_id: all_kegs[i] = keg_data; break
        self.settings_manager.save_keg_definitions(all_kegs)
        self.refresh_keg_list()
        self.refresh_dashboard_metadata()
        self.sensor_logic.force_recalculation()
        self.root.current = 'inventory'

    def delete_keg(self, keg_id):
        self.settings_manager.delete_keg_definition(keg_id)
        self.refresh_keg_list()
        self.refresh_dashboard_metadata()
        self.sensor_logic.force_recalculation()

    def add_new_keg(self): self.open_keg_edit(None)

    # --- Actions: BEVERAGES ---
    def open_beverage_edit(self, bev_id):
        self.inventory_screen.show_bevs()
        if bev_id:
            self.bev_edit_screen.screen_title = "Edit Beverage"
            self.bev_edit_screen.bev_id = bev_id
            lib = self.settings_manager.get_beverage_library().get('beverages', [])
            found = next((b for b in lib if b['id'] == bev_id), None)
            if found:
                self.bev_edit_screen.bev_name = found.get('name', '')
                self.bev_edit_screen.bev_abv = str(found.get('abv', ''))
                self.bev_edit_screen.bev_ibu = str(found.get('ibu', ''))
                srm_val = found.get('srm')
                try: self.bev_edit_screen.bev_srm = int(srm_val)
                except: self.bev_edit_screen.bev_srm = 5
        else:
            self.bev_edit_screen.screen_title = "Add New Beverage"
            self.bev_edit_screen.bev_id = ""
            self.bev_edit_screen.bev_name = ""
            self.bev_edit_screen.bev_abv = ""
            self.bev_edit_screen.bev_ibu = ""
            self.bev_edit_screen.bev_srm = 5
        self.root.current = 'bev_edit'

    def save_beverage_edit(self):
        scr = self.bev_edit_screen
        try: ibu = int(scr.bev_ibu) if scr.bev_ibu else None
        except ValueError: ibu = None
        is_new = (scr.bev_id == "")
        new_id = scr.bev_id if not is_new else str(uuid.uuid4())
        new_data = {
            'id': new_id,
            'name': scr.bev_name,
            'bjcp': "", 
            'abv': scr.bev_abv,
            'ibu': ibu,
            'srm': int(scr.bev_srm),
            'description': ''
        }
        lib = self.settings_manager.get_beverage_library().get('beverages', [])
        if is_new: lib.append(new_data)
        else:
            for i, b in enumerate(lib):
                if b['id'] == new_id: lib[i] = new_data; break
        self.settings_manager.save_beverage_library(lib)
        self.refresh_beverage_list()
        self.refresh_dashboard_metadata()
        self.root.current = 'inventory'

    def delete_beverage(self, bev_id):
        lib = self.settings_manager.get_beverage_library().get('beverages', [])
        new_lib = [b for b in lib if b['id'] != bev_id]
        self.settings_manager.save_beverage_library(new_lib)
        kegs = self.settings_manager.get_keg_definitions()
        for k in kegs:
            if k.get('beverage_id') == bev_id: k['beverage_id'] = UNASSIGNED_BEVERAGE_ID
        self.settings_manager.save_keg_definitions(kegs)
        assigns = self.settings_manager.get_sensor_beverage_assignments()
        for i, bid in enumerate(assigns):
            if bid == bev_id:
                self.settings_manager.save_sensor_beverage_assignment(i, UNASSIGNED_BEVERAGE_ID)
        self.refresh_beverage_list()
        self.refresh_keg_list()
        self.refresh_dashboard_metadata()

    def apply_config_changes(self):
        print("Applying Configuration Changes...")
        
        if hasattr(self, 'sensor_logic') and self.sensor_logic:
            self.sensor_logic.stop_monitoring()
            self.sensor_logic.cleanup_gpio()
            
        self.num_sensors = self.settings_manager.get_displayed_taps()
        
        tap_container = self.dashboard_screen.ids.tap_container
        tap_container.clear_widgets()
        self.tap_widgets = []
        
        for i in range(self.num_sensors):
            widget = TapWidget()
            widget.tap_index = i
            tap_container.add_widget(widget)
            self.tap_widgets.append(widget)
            
        def bridge_callback(idx, rate, rem, status, pour_vol):
            Clock.schedule_once(lambda dt: self.update_tap_ui(idx, rate, rem, status, pour_vol))
            
        callbacks = {
            "update_sensor_data_cb": bridge_callback,
            "update_cal_data_cb": lambda x, y: None 
        }

        self.sensor_logic = SensorLogic(
            num_sensors_from_config=self.num_sensors,
            ui_callbacks=callbacks,
            settings_manager=self.settings_manager
        )
        
        self.refresh_dashboard_metadata()
        self.sensor_logic.start_monitoring()

    def on_stop(self):
        if hasattr(self, 'sensor_logic') and self.sensor_logic:
            self.sensor_logic.cleanup_gpio()

if __name__ == '__main__':
    KegLevelApp().run()
