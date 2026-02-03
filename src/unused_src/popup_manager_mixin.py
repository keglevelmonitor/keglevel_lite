# keglevel app
#
# popup_manager_mixin.py
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import os
import uuid 
import sys      
import re
import threading
import subprocess

# Safe Imports for constants
try:
    from settings_manager import UNASSIGNED_KEG_ID, UNASSIGNED_BEVERAGE_ID
except ImportError:
    UNASSIGNED_KEG_ID = "unassigned_keg_id"
    UNASSIGNED_BEVERAGE_ID = "unassigned_beverage_id"

LITERS_TO_GALLONS = 0.264172
KG_TO_LB = 2.20462
OZ_TO_LITERS = 0.0295735

class PopupManagerMixin:    
    """
    Refactored Mixin class. 
    Retains: Keg/Beverage Management, Calibration, System Settings (Lite), About.
    Removes: Notifications, Workflow, Pour Log, Temp Log, Updates, Help, Wiring, EULA.
    """
    
    def __init__(self, settings_manager_instance, num_sensors, app_version_string=None):
        self.settings_manager = settings_manager_instance
        self.num_sensors = num_sensors
        self.base_dir = os.path.dirname(os.path.abspath(__file__)) 
        
        # --- Version Calculation ---
        version_source = app_version_string if app_version_string else 'Unknown (Script Model)'
        try:
            executable_path = sys.argv[0]
            filename = os.path.basename(executable_path)
            match = re.search(r'KegLevel_Monitor_(\d{12})', filename)
            if match:
                datecode = match.group(1)
                year, month, day, hour, minute = datecode[0:4], datecode[4:6], datecode[6:8], datecode[8:10], datecode[10:12]
                version_source = f"{datecode} (Compiled: {year}-{month}-{day} {hour}:{minute})"
        except Exception:
            version_source = "Unknown (Error during startup parsing)"
        self.app_version_string = version_source 
        
        # --- Settings Popup Variables ---
        self.system_settings_unit_var = tk.StringVar()
        self.system_settings_taps_var = tk.StringVar()
        self.system_settings_ui_mode_var = tk.StringVar()
        
        # Pour Volume Variables
        self.system_settings_pour_ml_var = tk.StringVar()
        self.system_settings_pour_oz_var = tk.StringVar()
        self.system_settings_pour_size_display_var = tk.StringVar() 
        self.system_settings_pour_unit_label_var = tk.StringVar()   
        
        # --- Flow Calibration Variables ---
        self.flow_cal_current_factors = [tk.StringVar() for _ in range(self.num_sensors)]
        self.flow_cal_new_factor_entries = [tk.StringVar() for _ in range(self.num_sensors)]
        self.flow_cal_notes_var = tk.StringVar()
        self.single_cal_target_volume_var = tk.StringVar()
        self.single_cal_measured_flow_var = tk.StringVar(value="0.00 L/min")
        self.single_cal_measured_pour_var = tk.StringVar(value="0.00")
        self.single_cal_unit_label = tk.StringVar()
        self.single_cal_tap_index = -1
        self.single_cal_current_factor_var = tk.StringVar() 
        self.single_cal_new_factor_var = tk.StringVar()      
        self._single_cal_calculated_new_factor = None        
        self.single_cal_deduct_volume_var = tk.BooleanVar(value=False)

        self._single_cal_in_progress = False
        self._single_cal_complete = False
        self._single_cal_pulse_count = 0
        self._single_cal_last_pour = 0.0
        self._single_cal_popup_window = None 
        
        self.support_qr_image = None # For About popup

    def _setup_menu_commands(self):
        """Builds the Reduced Settings menu."""
        
        # --- 1. Configuration ---
        self.settings_menu.add_command(label="Configuration", font=self.menu_heading_font, state="disabled")
        self.settings_menu.add_command(label="Keg Management", command=lambda: self._open_configuration_popup(initial_tab=0))
        self.settings_menu.add_command(label="Beverage Management", command=lambda: self._open_configuration_popup(initial_tab=1))
        self.settings_menu.add_command(label="Flow Sensor Calibration", command=self._open_flow_calibration_popup)
        self.settings_menu.add_command(label="System Settings", command=self._open_system_settings_popup)
        
        self.settings_menu.add_separator()
        
        # --- 2. App Info ---
        self.settings_menu.add_command(label="App Info", font=self.menu_heading_font, state="disabled")
        self.settings_menu.add_command(label="About...", command=self._open_about_popup)

    # =========================================================================
    #  CONFIGURATION MANAGEMENT (KEGS & BEVERAGES)
    # =========================================================================

    def _open_configuration_popup(self, initial_tab=0):
        popup = tk.Toplevel(self.root)
        popup.title("Configuration Manager")
        self._center_popup(popup, 700, 540)
        popup.transient(self.root)
        popup.grab_set()
        
        notebook = ttk.Notebook(popup)
        notebook.pack(expand=True, fill="both", padx=5, pady=5)
        
        self.tab_kegs = ttk.Frame(notebook)
        notebook.add(self.tab_kegs, text="Keg Management")
        
        self.tab_beverages = ttk.Frame(notebook)
        notebook.add(self.tab_beverages, text="Beverage Management")
        
        self._show_keg_list_view(self.tab_kegs, popup)
        self._show_beverage_list_view(self.tab_beverages, popup)
        
        if initial_tab == 1:
            notebook.select(self.tab_beverages)
            
        def on_tab_change(event):
            selected_tab = event.widget.select()
            tab_text = event.widget.tab(selected_tab, "text")
            if tab_text == "Keg Management":
                for widget in self.tab_kegs.winfo_children():
                    if hasattr(widget, 'beverage_combobox'):
                        self._populate_keg_edit_dropdown(widget.beverage_combobox)
                        break
        notebook.bind("<<NotebookTabChanged>>", on_tab_change)

    # --- Beverage List View ---
    def _show_beverage_list_view(self, parent_frame, popup_window=None):
        for widget in parent_frame.winfo_children(): widget.destroy()
        
        list_container = ttk.Frame(parent_frame)
        list_container.pack(fill="both", expand=True, padx=5, pady=5)
        
        canvas = tk.Canvas(list_container, borderwidth=0, highlightthickness=0)
        v_bar = ttk.Scrollbar(list_container, orient="vertical", command=canvas.yview)
        scroll_frame = ttk.Frame(canvas)
        
        v_bar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.configure(yscrollcommand=v_bar.set)
        
        cw = canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind('<Configure>', lambda e: canvas.itemconfig(cw, width=e.width))

        bevs = sorted(self.settings_manager.get_beverage_library().get('beverages', []), key=lambda b: b.get('name', '').lower())
        
        header = ttk.Frame(scroll_frame)
        header.pack(fill="x", pady=0)
        header.grid_columnconfigure(0, weight=3) 
        header.grid_columnconfigure(1, weight=0, minsize=150)
        
        ttk.Label(header, text="Beverage Name", font=('TkDefaultFont', 10, 'bold'), anchor="w").grid(row=0, column=0, sticky="ew", padx=10, pady=5)
        ttk.Label(header, text="Actions", font=('TkDefaultFont', 10, 'bold'), anchor="e").grid(row=0, column=1, sticky="ew", padx=15, pady=5)
        
        ttk.Separator(scroll_frame, orient="horizontal").pack(fill="x", pady=0)
        
        for i, bev in enumerate(bevs):
            row_frame = ttk.Frame(scroll_frame)
            row_frame.pack(fill="x", pady=0)
            row_frame.grid_columnconfigure(0, weight=3)
            row_frame.grid_columnconfigure(1, weight=0, minsize=150)
            
            bg = "#FFFFFF" if i % 2 == 0 else "#F5F5F5"
            tk.Label(row_frame, text=bev.get('name', ''), anchor="w", bg=bg).grid(row=0, column=0, sticky="nsew", padx=(10,0), pady=0, ipady=5)
            
            btns = tk.Frame(row_frame, bg=bg)
            btns.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)
            
            ttk.Button(btns, text="Delete", width=8,
                       command=lambda b=bev: self._delete_beverage_from_view(parent_frame, b)).pack(side="right", padx=5, pady=2)
            ttk.Button(btns, text="Edit", width=8, 
                       command=lambda b=bev: self._show_beverage_edit_view(parent_frame, b)).pack(side="right", padx=2, pady=2)

        footer_frame = ttk.Frame(parent_frame, padding=10)
        footer_frame.pack(fill="x", side="bottom")
        ttk.Button(footer_frame, text="+ Add New Beverage", 
                   command=lambda: self._show_beverage_edit_view(parent_frame, None)).pack(side="left", padx=5)
        if popup_window:
            ttk.Button(footer_frame, text="Close", command=popup_window.destroy).pack(side="right", padx=5)

    # --- Beverage Edit View ---
    def _show_beverage_edit_view(self, parent_frame, bev_data):
        for widget in parent_frame.winfo_children(): widget.destroy()
        
        is_new = bev_data is None
        title = "Add New Beverage" if is_new else "Edit Beverage"
        
        header_frame = ttk.Frame(parent_frame, padding=10)
        header_frame.pack(fill="x", side="top")
        ttk.Label(header_frame, text=title, font=('TkDefaultFont', 14, 'bold')).pack(side="left")
        
        form_frame = ttk.Frame(parent_frame, padding=20)
        form_frame.pack(fill="both", expand=True)
        
        default_bev = {'id': str(uuid.uuid4()), 'name': '', 'bjcp': '', 'abv': '', 'ibu': '', 'srm': '', 'description': ''}
        data = bev_data.copy() if bev_data else default_bev
        
        styles = self.settings_manager.load_bjcp_styles()
        style_list = []
        style_map = {}
        for s in styles:
            display = f"{s.get('code')} {s.get('name')}"
            style_list.append(display)
            style_map[display] = s
            
        current_bjcp = data.get('bjcp', '')
        if current_bjcp and current_bjcp not in style_map: current_bjcp = ""
        
        temp_vars = {
            'id': tk.StringVar(value=data.get('id')),
            'name': tk.StringVar(value=data.get('name')),
            'bjcp': tk.StringVar(value=current_bjcp),
            'abv': tk.StringVar(value=data.get('abv')),
            'ibu': tk.StringVar(value=str(data.get('ibu', '')) if data.get('ibu') is not None else ''),
            'srm': tk.StringVar(value=str(data.get('srm', '')) if data.get('srm') is not None else ''),
        }
        
        def add_row(label, var, width=30):
            f = ttk.Frame(form_frame); f.pack(fill="x", pady=5)
            ttk.Label(f, text=label, width=15, anchor="w").pack(side="left")
            ttk.Entry(f, textvariable=var, width=width).pack(side="left", padx=5, fill="x", expand=True)

        add_row("Beverage Name:", temp_vars['name'])
        
        f_style = ttk.Frame(form_frame); f_style.pack(fill="x", pady=5)
        ttk.Label(f_style, text="BJCP Style:", width=15, anchor="w").pack(side="left")
        cb = ttk.Combobox(f_style, textvariable=temp_vars['bjcp'], values=style_list, state="readonly")
        cb.pack(side="left", padx=5, fill="x", expand=True)
        
        f_stats = ttk.Frame(form_frame); f_stats.pack(fill="x", pady=5)
        ttk.Label(f_stats, text="Vital Statistics:", width=15, anchor="w").pack(side="left")
        stats_group = ttk.Frame(f_stats)
        stats_group.pack(side="left", padx=5, fill="x")
        
        ttk.Label(stats_group, text="ABV:").pack(side="left")
        ttk.Entry(stats_group, textvariable=temp_vars['abv'], width=6).pack(side="left", padx=(5, 15))
        ttk.Label(stats_group, text="IBU:").pack(side="left")
        ttk.Entry(stats_group, textvariable=temp_vars['ibu'], width=6).pack(side="left", padx=(5, 15))
        ttk.Label(stats_group, text="SRM:").pack(side="left")
        ttk.Entry(stats_group, textvariable=temp_vars['srm'], width=6).pack(side="left", padx=(5, 0))
            
        ttk.Label(form_frame, text="Description:").pack(anchor="w", pady=(10,0))
        txt = tk.Text(form_frame, height=5, wrap="word", relief="sunken", borderwidth=1)
        txt.pack(fill="both", expand=True, pady=5)
        txt.insert("1.0", data.get('description', ''))
        
        def on_style(e):
            sel = cb.get()
            if sel in style_map and not txt.get("1.0", "end").strip():
                txt.insert("1.0", style_map[sel].get('impression', ''))
        cb.bind("<<ComboboxSelected>>", on_style)

        btns = ttk.Frame(parent_frame, padding=10)
        btns.pack(fill="x", side="bottom")
        
        ttk.Button(btns, text="Save", 
                   command=lambda: self._save_beverage_from_view(temp_vars, txt, is_new, parent_frame)).pack(side="right", padx=5)
        ttk.Button(btns, text="Cancel", 
                   command=lambda: self._show_beverage_list_view(parent_frame)).pack(side="right", padx=5)

    def _save_beverage_from_view(self, vars, txt_widget, is_new, parent_frame):
        try:
            name = vars['name'].get().strip()
            if not name: messagebox.showerror("Error", "Name required."); return
            ibu = int(vars['ibu'].get()) if vars['ibu'].get().strip() else None
            srm = int(vars['srm'].get()) if vars['srm'].get().strip() else None
            
            new_data = {
                'id': vars['id'].get(),
                'name': name,
                'bjcp': vars['bjcp'].get(),
                'abv': vars['abv'].get(),
                'ibu': ibu,
                'srm': srm,
                'description': txt_widget.get("1.0", "end").strip()
            }
            lib = self.settings_manager.get_beverage_library().get('beverages', [])
            if is_new: lib.append(new_data)
            else:
                for i, b in enumerate(lib):
                    if b['id'] == new_data['id']: lib[i] = new_data; break
            self.settings_manager.save_beverage_library(lib)
            self._show_beverage_list_view(parent_frame)
        except ValueError: messagebox.showerror("Error", "Invalid numeric format for IBU/SRM.")

    def _delete_beverage_from_view(self, parent_frame, bev_data):
        if messagebox.askyesno("Confirm", f"Delete '{bev_data.get('name')}'?"):
            assignments = self.settings_manager.get_sensor_beverage_assignments()
            b_id = bev_data['id']
            for i in range(len(assignments)):
                if assignments[i] == b_id:
                    assignments[i] = UNASSIGNED_BEVERAGE_ID
                    self.settings_manager.save_sensor_beverage_assignment(i, UNASSIGNED_BEVERAGE_ID)
            lib = self.settings_manager.get_beverage_library().get('beverages', [])
            lib = [b for b in lib if b['id'] != b_id]
            self.settings_manager.save_beverage_library(lib)
            self._show_beverage_list_view(parent_frame)
    
    # --- Keg Edit Helper Methods ---
    def _keg_edit_link_weight_to_volume(self, temp_vars, source_var):
        display_units = self.settings_manager.get_display_units()
        volume_conversion = 1.0 if display_units == "metric" else LITERS_TO_GALLONS
        for var_name in ['tare_weight_kg', 'total_weight_kg']:
            trace_id = getattr(temp_vars[var_name], '_trace_id', None)
            if trace_id: 
                 try: temp_vars[var_name].trace_remove("write", trace_id)
                 except tk.TclError: pass
        try:
            empty_kg = float(temp_vars['tare_weight_kg'].get())
            total_kg = float(temp_vars['total_weight_kg'].get())
        except ValueError: 
            temp_vars['starting_volume_display'].set("--.--")
            self._re_add_keg_edit_traces(temp_vars); return
        
        if total_kg >= empty_kg and empty_kg >= 0 and total_kg >= 0:
             new_vol_liters = self.settings_manager._calculate_volume_from_weight(total_kg, empty_kg)
             new_vol_display = new_vol_liters * volume_conversion
             temp_vars['starting_volume_display'].set(f"{new_vol_display:.2f}")
        else:
             temp_vars['starting_volume_display'].set("--.--")
        self._re_add_keg_edit_traces(temp_vars)

    def _re_add_keg_edit_traces(self, temp_vars):
        def trace_handler(var_name):
            return lambda n, i, m, r=temp_vars: self._keg_edit_link_weight_to_volume(r, var_name)
        temp_vars['tare_weight_kg']._trace_id = temp_vars['tare_weight_kg'].trace_add("write", trace_handler('tare_weight_kg'))
        temp_vars['total_weight_kg']._trace_id = temp_vars['total_weight_kg'].trace_add("write", trace_handler('total_weight_kg'))

    # --- Keg List View ---
    def _show_keg_list_view(self, parent_frame, popup_window=None):
        for widget in parent_frame.winfo_children(): widget.destroy()
        
        list_container = ttk.Frame(parent_frame)
        list_container.pack(fill="both", expand=True, padx=5, pady=5)
        canvas = tk.Canvas(list_container, borderwidth=0, highlightthickness=0)
        v_scrollbar = ttk.Scrollbar(list_container, orient="vertical", command=canvas.yview)
        scroll_frame = ttk.Frame(canvas)
        v_scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.configure(yscrollcommand=v_scrollbar.set)
        cw = canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind('<Configure>', lambda e: canvas.itemconfig(cw, width=e.width))

        keg_list = sorted(self.settings_manager.get_keg_definitions(), key=lambda k: k.get('title', '').lower())
        beverage_lib = self.settings_manager.get_beverage_library().get('beverages', [])
        beverage_map = {b['id']: b['name'] for b in beverage_lib}

        header = ttk.Frame(scroll_frame)
        header.pack(fill="x", pady=0)
        header.grid_columnconfigure(0, weight=1) 
        header.grid_columnconfigure(1, weight=2) 
        header.grid_columnconfigure(2, weight=0, minsize=150)

        ttk.Label(header, text="Keg Name", font=('TkDefaultFont', 10, 'bold'), anchor="w").grid(row=0, column=0, sticky="ew", padx=10, pady=5)
        ttk.Label(header, text="Contents", font=('TkDefaultFont', 10, 'bold'), anchor="w").grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        ttk.Label(header, text="Actions", font=('TkDefaultFont', 10, 'bold'), anchor="e").grid(row=0, column=2, sticky="ew", padx=15, pady=5)
        ttk.Separator(scroll_frame, orient="horizontal").pack(fill="x", pady=0)

        for i, keg in enumerate(keg_list):
            row_frame = ttk.Frame(scroll_frame)
            row_frame.pack(fill="x", pady=0)
            row_frame.grid_columnconfigure(0, weight=1)
            row_frame.grid_columnconfigure(1, weight=2)
            row_frame.grid_columnconfigure(2, weight=0, minsize=150)
            
            bg = "#FFFFFF" if i % 2 == 0 else "#F5F5F5"
            title = keg.get('title', 'Unknown')
            bev_name = beverage_map.get(keg.get('beverage_id'), "")
            
            tk.Label(row_frame, text=title, anchor="w", bg=bg).grid(row=0, column=0, sticky="nsew", padx=(10,0), pady=0, ipady=5)
            tk.Label(row_frame, text=bev_name, anchor="w", bg=bg).grid(row=0, column=1, sticky="nsew", padx=0, pady=0, ipady=5)
            
            btn_frame = tk.Frame(row_frame, bg=bg)
            btn_frame.grid(row=0, column=2, sticky="nsew", padx=0, pady=0)
            
            ttk.Button(btn_frame, text="Delete", width=8,
                       command=lambda k=keg: self._delete_keg_from_view(parent_frame, k)).pack(side="right", padx=5, pady=2)
            ttk.Button(btn_frame, text="Edit", width=8,
                       command=lambda k=keg: self._show_keg_edit_view(parent_frame, k)).pack(side="right", padx=2, pady=2)

        footer_frame = ttk.Frame(parent_frame, padding=10)
        footer_frame.pack(fill="x", side="bottom")
        ttk.Button(footer_frame, text="+ Add New Keg", 
                   command=lambda: self._show_keg_edit_view(parent_frame, None)).pack(side="left", padx=5)
        if popup_window:
            ttk.Button(footer_frame, text="Close", command=popup_window.destroy).pack(side="right", padx=5)

    # --- Keg Edit View ---
    def _show_keg_edit_view(self, parent_frame, keg_data):
        for widget in parent_frame.winfo_children(): widget.destroy()
        is_new = keg_data is None
        title_text = "Add New Keg" if is_new else f"Edit {keg_data.get('title')}"
        
        header_frame = ttk.Frame(parent_frame, padding=10)
        header_frame.pack(fill="x", side="top")
        ttk.Label(header_frame, text=title_text, font=('TkDefaultFont', 14, 'bold')).pack(side="left")
        
        form_frame = ttk.Frame(parent_frame, padding=20)
        form_frame.pack(fill="both", expand=True)
        
        default_data = self.settings_manager._get_default_keg_definitions()[0]
        data = keg_data.copy() if keg_data else default_data.copy()
        
        display_units = self.settings_manager.get_display_units()
        weight_unit = "kg" if display_units == "metric" else "lb"
        volume_unit = "Liters" if display_units == "metric" else "Gallons"
        weight_conv = 1.0 if display_units == "metric" else KG_TO_LB
        vol_conv = 1.0 if display_units == "metric" else LITERS_TO_GALLONS
        
        start_vol_l = data.get('calculated_starting_volume_liters', 0.0)
        max_vol_l = data.get('maximum_full_volume_liters', default_data['maximum_full_volume_liters'])
        dispensed_l = data.get('current_dispensed_liters', 0.0)
        current_l = max(0.0, start_vol_l - dispensed_l)
        
        temp_vars = {
            'id': tk.StringVar(value=data.get('id', str(uuid.uuid4()))),
            'title': tk.StringVar(value=data.get('title', '')),
            'max_volume_display': tk.StringVar(value=f"{max_vol_l * vol_conv:.2f}"),
            'tare_weight_kg': tk.StringVar(value=f"{data.get('tare_weight_kg', 0.0):.2f}"),
            'total_weight_kg': tk.StringVar(value=f"{data.get('starting_total_weight_kg', 0.0):.2f}"),
            'starting_volume_display': tk.StringVar(value=f"{start_vol_l * vol_conv:.2f}"),
            'current_volume_display': tk.StringVar(value=f"{current_l * vol_conv:.2f}"),
            'beverage_name_var': tk.StringVar(),
            'original_keg_data': data
        }
        
        temp_vars['tare_entry'] = tk.StringVar(value=f"{data.get('tare_weight_kg', 0.0) * weight_conv:.2f}")
        temp_vars['total_entry'] = tk.StringVar(value=f"{data.get('starting_total_weight_kg', 0.0) * weight_conv:.2f}")

        def add_row(label, var, unit="", readonly=False):
            f = ttk.Frame(form_frame); f.pack(fill="x", pady=5)
            ttk.Label(f, text=label, width=25, anchor="w").pack(side="left")
            e = ttk.Entry(f, textvariable=var, width=15, state='readonly' if readonly else 'normal')
            e.pack(side="left", padx=5)
            if unit: ttk.Label(f, text=unit).pack(side="left")
            return e

        f_bev = ttk.Frame(form_frame); f_bev.pack(fill="x", pady=5)
        ttk.Label(f_bev, text="Contents (Beverage):", width=25, anchor="w").pack(side="left")
        bev_dropdown = ttk.Combobox(f_bev, textvariable=temp_vars['beverage_name_var'], state="readonly", width=30)
        bev_dropdown.pack(side="left", padx=5)
        form_frame.beverage_combobox = bev_dropdown
        self._populate_keg_edit_dropdown(bev_dropdown, data.get('beverage_id'))

        ttk.Separator(form_frame, orient="horizontal").pack(fill="x", pady=10)
        add_row("Keg Title (Max 24 chars):", temp_vars['title'])
        add_row("Maximum Full Volume:", temp_vars['max_volume_display'], volume_unit)
        ttk.Separator(form_frame, orient="horizontal").pack(fill="x", pady=10)
        
        e_tare = add_row("Tare Weight (Empty):", temp_vars['tare_entry'], weight_unit)
        def on_weight_change(var_entry, var_kg):
            try:
                kg = float(var_entry.get()) / weight_conv
                var_kg.set(f"{kg:.2f}")
            except: pass
        e_tare.bind("<FocusOut>", lambda e: on_weight_change(temp_vars['tare_entry'], temp_vars['tare_weight_kg']))
        
        e_total = add_row("Starting Total Weight:", temp_vars['total_entry'], weight_unit)
        e_total.bind("<FocusOut>", lambda e: on_weight_change(temp_vars['total_entry'], temp_vars['total_weight_kg']))
        
        add_row("Starting Volume:", temp_vars['starting_volume_display'], "", readonly=True)
        self._keg_edit_link_weight_to_volume(temp_vars, None)

        f_curr = ttk.Frame(form_frame); f_curr.pack(fill="x", pady=5)
        ttk.Label(f_curr, text="Current (Remaining) Volume:", width=25, anchor="w").pack(side="left")
        ttk.Entry(f_curr, textvariable=temp_vars['current_volume_display'], width=15).pack(side="left", padx=5)
        ttk.Label(f_curr, text=volume_unit).pack(side="left")
        ttk.Button(f_curr, text="Reset to Full", 
                   command=lambda: temp_vars['current_volume_display'].set(temp_vars['starting_volume_display'].get())
                   ).pack(side="left", padx=15)

        btn_frame = ttk.Frame(parent_frame, padding=10)
        btn_frame.pack(fill="x", side="bottom")
        ttk.Button(btn_frame, text="Save", 
                   command=lambda: self._save_keg_from_view(temp_vars, is_new, parent_frame)).pack(side="right", padx=5)
        ttk.Button(btn_frame, text="Cancel", 
                   command=lambda: self._show_keg_list_view(parent_frame)).pack(side="right", padx=5)
                   
    def _populate_keg_edit_dropdown(self, combobox, current_id=None):
        beverage_lib = self.settings_manager.get_beverage_library().get('beverages', [])
        names = ["Empty"] + sorted([b['name'] for b in beverage_lib])
        combobox['values'] = names
        if current_id is not None:
            if current_id == UNASSIGNED_BEVERAGE_ID: combobox.set("Empty")
            else:
                found = next((b for b in beverage_lib if b['id'] == current_id), None)
                combobox.set(found['name'] if found else "Empty")

    def _save_keg_from_view(self, temp_vars, is_new, parent_frame):
        try:
            parent_frame.focus_set()
            display_units = self.settings_manager.get_display_units()
            vol_conv = 1.0 if display_units == "metric" else LITERS_TO_GALLONS
            
            title = temp_vars['title'].get().strip()
            if not title: messagebox.showerror("Error", "Title required."); return
            
            bev_name = temp_vars['beverage_name_var'].get()
            bev_id = UNASSIGNED_BEVERAGE_ID
            if bev_name != "Empty":
                lib = self.settings_manager.get_beverage_library().get('beverages', [])
                found = next((b for b in lib if b['name'] == bev_name), None)
                if found: bev_id = found['id']

            tare = float(temp_vars['tare_weight_kg'].get())
            total = float(temp_vars['total_weight_kg'].get())
            max_v = float(temp_vars['max_volume_display'].get()) / vol_conv
            curr_display = float(temp_vars['current_volume_display'].get())
            
            start_v = self.settings_manager._calculate_volume_from_weight(total, tare)
            current_l = curr_display / vol_conv
            dispensed = max(0.0, start_v - current_l)
            
            new_data = {
                "id": temp_vars['id'].get(), "title": title, "tare_weight_kg": tare, "starting_total_weight_kg": total,
                "maximum_full_volume_liters": max_v, "calculated_starting_volume_liters": start_v,
                "current_dispensed_liters": dispensed, "total_dispensed_pulses": 0, "beverage_id": bev_id, "fill_date": ""
            }
            if not is_new:
                old = temp_vars['original_keg_data']
                if abs(old.get('calculated_starting_volume_liters', 0) - start_v) < 0.1:
                    new_data['total_dispensed_pulses'] = old.get('total_dispensed_pulses', 0)
                    if abs(old.get('current_dispensed_liters', 0) - dispensed) < 0.1:
                         new_data['current_dispensed_liters'] = old.get('current_dispensed_liters', 0)

            kegs = self.settings_manager.get_keg_definitions()
            if is_new: kegs.append(new_data)
            else:
                for i, k in enumerate(kegs):
                    if k['id'] == new_data['id']: kegs[i] = new_data; break
            self.settings_manager.save_keg_definitions(kegs)
            
            if self.sensor_logic: self.sensor_logic.force_recalculation()
            self._refresh_ui_for_settings_or_resume()
            self._show_keg_list_view(parent_frame)
            
        except ValueError: messagebox.showerror("Error", "Invalid numeric input.")
            
    def _delete_keg_from_view(self, parent_frame, keg_data):
        if messagebox.askyesno("Confirm", f"Delete keg '{keg_data.get('title')}'?"):
            self.settings_manager.delete_keg_definition(keg_data['id'])
            if self.sensor_logic: self.sensor_logic.force_recalculation()
            self._refresh_ui_for_settings_or_resume()
            self._show_keg_list_view(parent_frame)

    # =========================================================================
    #  FLOW CALIBRATION
    # =========================================================================

    def _open_flow_calibration_popup(self, initial_tab_index=0, initial_tap_index=None, initial_keg_title=None):
         popup = tk.Toplevel(self.root)
         popup.title("Flow Sensor Calibration"); 
         popup.geometry("500x550");
         popup.transient(self.root); popup.grab_set()

         notebook = ttk.Notebook(popup)
         notebook.pack(expand=True, fill="both", padx=10, pady=10)

         tab1 = ttk.Frame(notebook, padding="10")
         notebook.add(tab1, text='Pour Calibration (Quick)')
         self._create_pour_calibration_tab(tab1, popup)

         tab2 = ttk.Frame(notebook, padding="10")
         notebook.add(tab2, text='Keg Calibration (Accurate)')
         self._create_keg_calibration_tab(tab2, popup)

         buttons_frame = ttk.Frame(popup, padding="10"); 
         buttons_frame.pack(fill="x", side="bottom", pady=(0, 10))
         ttk.Button(buttons_frame, text="Manual Cal Factor", 
                    command=lambda p=popup: self._open_manually_enter_calibration_factor_popup(p)).pack(side="left", padx=5)
         ttk.Button(buttons_frame, text="Close", command=popup.destroy).pack(side="right", padx=5)
         
         if initial_tab_index is not None: notebook.select(initial_tab_index)
         if initial_tap_index is not None:
             self.keg_cal_tap_var.set(f"Tap {initial_tap_index + 1}")
             if initial_keg_title: self.keg_cal_keg_var.set(initial_keg_title)
             self._update_keg_cal_tab_display()

    def _create_pour_calibration_tab(self, parent_frame, popup):
         canvas = tk.Canvas(parent_frame, borderwidth=0)
         v_scrollbar = ttk.Scrollbar(parent_frame, orient="vertical", command=canvas.yview)
         scroll_frame = ttk.Frame(canvas)
         v_scrollbar.pack(side="right", fill="y"); 
         canvas.pack(side="left", fill="both", expand=True)
         canvas.configure(yscrollcommand=v_scrollbar.set)
         cw = canvas.create_window((0, 0), window=scroll_frame, anchor="nw", width=440) 
         scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
         canvas.bind('<Configure>', lambda e: canvas.itemconfig(cw, width=e.width))

         scroll_frame.grid_columnconfigure(0, weight=1); scroll_frame.grid_columnconfigure(1, weight=0); 
         
         header_frame = ttk.Frame(scroll_frame); 
         header_frame.grid(row=0, column=0, columnspan=2, sticky='ew', padx=5, pady=5)
         header_frame.grid_columnconfigure(0, weight=1); header_frame.grid_columnconfigure(1, weight=0);
         
         ttk.Label(header_frame, text="Flow Sensor", font=('TkDefaultFont', 10, 'bold')).grid(row=0, column=0, padx=5, sticky='w')
         ttk.Label(header_frame, text="Action", font=('TkDefaultFont', 10, 'bold')).grid(row=0, column=1, sticky='e', padx=5)

         displayed_taps = self.settings_manager.get_displayed_taps()
         for i in range(displayed_taps):
             tap_name = f"Tap {i+1}"
             row = i + 1; bg = '#F5F5F5' if i % 2 else '#FFFFFF'
             row_frame = tk.Frame(scroll_frame, bg=bg, relief='flat', bd=0); 
             row_frame.grid(row=row, column=0, columnspan=2, sticky='ew', pady=(1, 0))
             row_frame.grid_columnconfigure(0, weight=1); row_frame.grid_columnconfigure(1, weight=0) 
             ttk.Label(row_frame, text=tap_name, anchor='w', background=bg, padding=(5, 5)).grid(row=0, column=0, sticky='ew', padx=5)
             ttk.Button(row_frame, text="Calibrate", width=12, 
                        command=lambda idx=i, p=popup: self._open_single_tap_calibration_popup(idx, p)).grid(row=0, column=1, padx=(5, 5), pady=2, sticky='e')

    def _create_keg_calibration_tab(self, parent_frame, popup):
        self.keg_cal_tap_var = tk.StringVar()
        self.keg_cal_keg_var = tk.StringVar()
        self.keg_cal_vol_var = tk.StringVar(value="--")
        self.keg_cal_pulses_var = tk.StringVar(value="--")
        self.keg_cal_current_k_var = tk.StringVar(value="--")
        self.keg_cal_new_k_var = tk.StringVar(value="--")
        self.keg_cal_validation_var = tk.BooleanVar(value=False)
        
        row_frame = ttk.Frame(parent_frame); row_frame.pack(fill='x', pady=5)
        ttk.Label(row_frame, text="Select Tap:", width=15).pack(side='left')
        tap_options = [f"Tap {i+1}" for i in range(self.settings_manager.get_displayed_taps())]
        self.keg_cal_tap_dropdown = ttk.Combobox(row_frame, textvariable=self.keg_cal_tap_var, values=tap_options, state="readonly")
        self.keg_cal_tap_dropdown.pack(side='left', fill='x', expand=True)
        self.keg_cal_tap_dropdown.bind("<<ComboboxSelected>>", self._update_keg_cal_tab_display)

        row_frame = ttk.Frame(parent_frame); row_frame.pack(fill='x', pady=5)
        ttk.Label(row_frame, text="Select Keg:", width=15).pack(side='left')
        all_kegs = self.settings_manager.get_keg_definitions()
        keg_titles = [k.get('title', 'Unknown') for k in all_kegs]
        self.keg_cal_keg_dropdown = ttk.Combobox(row_frame, textvariable=self.keg_cal_keg_var, values=keg_titles, state="readonly")
        self.keg_cal_keg_dropdown.pack(side='left', fill='x', expand=True)
        self.keg_cal_keg_dropdown.bind("<<ComboboxSelected>>", self._update_keg_cal_tab_display)

        ttk.Separator(parent_frame, orient='horizontal').pack(fill='x', pady=15)
        def add_info_row(label, var):
            r = ttk.Frame(parent_frame); r.pack(fill='x', pady=2)
            ttk.Label(r, text=label, width=25, anchor='w').pack(side='left')
            ttk.Label(r, textvariable=var, width=15, anchor='e', relief='sunken').pack(side='left', padx=5)
        add_info_row("Keg Starting Volume (L):", self.keg_cal_vol_var)
        add_info_row("Total Pulses Recorded:", self.keg_cal_pulses_var)
        add_info_row("Current K-Factor:", self.keg_cal_current_k_var)
        ttk.Separator(parent_frame, orient='horizontal').pack(fill='x', pady=15)
        
        res_frame = ttk.Frame(parent_frame); res_frame.pack(fill='x', pady=5)
        ttk.Label(res_frame, text="Calculated New K-Factor:", width=25, font=('TkDefaultFont', 10, 'bold')).pack(side='left')
        ttk.Label(res_frame, textvariable=self.keg_cal_new_k_var, width=15, anchor='e', relief='sunken', font=('TkDefaultFont', 10, 'bold')).pack(side='left', padx=5)

        chk_frame = ttk.Frame(parent_frame); chk_frame.pack(fill='x', pady=15)
        self.keg_cal_chk = ttk.Checkbutton(chk_frame, variable=self.keg_cal_validation_var)
        self.keg_cal_chk.pack(side='left', anchor='nw')
        ttk.Label(chk_frame, text="I confirm this keg was assigned to and fully dispensed only from this tap.", wraplength=400).pack(side='left', anchor='w', padx=(5, 0))
        self.keg_cal_validation_var.trace_add('write', lambda *args: self._update_keg_cal_save_button())

        self.keg_cal_save_btn = ttk.Button(parent_frame, text="Save Calibration", state='disabled', command=lambda: self._save_keg_calibration(popup))
        self.keg_cal_save_btn.pack(pady=5)

    def _update_keg_cal_tab_display(self, event=None):
        tap_str = self.keg_cal_tap_var.get()
        keg_title = self.keg_cal_keg_var.get()
        if not tap_str: return
        try: tap_idx = int(tap_str.split(" ")[1]) - 1
        except: return

        if event and event.widget == self.keg_cal_tap_dropdown:
            assignments = self.settings_manager.get_sensor_keg_assignments()
            if tap_idx < len(assignments):
                assigned_keg = self.settings_manager.get_keg_by_id(assignments[tap_idx])
                if assigned_keg: 
                    self.keg_cal_keg_var.set(assigned_keg.get('title', ''))
                    keg_title = assigned_keg.get('title', '')

        all_kegs = self.settings_manager.get_keg_definitions()
        keg_data = next((k for k in all_kegs if k.get('title') == keg_title), None)
        current_k = self.settings_manager.get_flow_calibration_factors()[tap_idx]
        self.keg_cal_current_k_var.set(f"{current_k:.2f}")

        if keg_data:
            start_vol = keg_data.get('calculated_starting_volume_liters', 0.0)
            pulses = keg_data.get('total_dispensed_pulses', 0)
            self.keg_cal_vol_var.set(f"{start_vol:.2f}")
            self.keg_cal_pulses_var.set(str(pulses))
            if start_vol > 0 and pulses > 0: self.keg_cal_new_k_var.set(f"{pulses/start_vol:.2f}")
            else: self.keg_cal_new_k_var.set("Invalid Data")
        else:
            self.keg_cal_vol_var.set("--")
            self.keg_cal_pulses_var.set("--")
            self.keg_cal_new_k_var.set("--")
        self._update_keg_cal_save_button()

    def _update_keg_cal_save_button(self):
        if not hasattr(self, 'keg_cal_save_btn') or not self.keg_cal_save_btn: return
        try: valid_math = (float(self.keg_cal_new_k_var.get()) > 0)
        except: valid_math = False
        if self.keg_cal_validation_var.get() and valid_math: self.keg_cal_save_btn.config(state='normal')
        else: self.keg_cal_save_btn.config(state='disabled')

    def _save_keg_calibration(self, popup):
        try:
            new_k = float(self.keg_cal_new_k_var.get())
            tap_idx = int(self.keg_cal_tap_var.get().split(" ")[1]) - 1
            keg_title = self.keg_cal_keg_var.get()
        except ValueError: return
        popup.destroy()

        factors = self.settings_manager.get_flow_calibration_factors()
        factors[tap_idx] = new_k
        self.settings_manager.save_flow_calibration_factors(factors)
        self.settings_manager.save_sensor_keg_assignment(tap_idx, UNASSIGNED_KEG_ID)
        self.settings_manager.save_sensor_beverage_assignment(tap_idx, UNASSIGNED_BEVERAGE_ID)

        all_kegs = self.settings_manager.get_keg_definitions()
        for keg in all_kegs:
            if keg.get('title') == keg_title:
                keg.update({'beverage_id': UNASSIGNED_BEVERAGE_ID, 'fill_date': "", 'current_dispensed_liters': 0.0, 'total_dispensed_pulses': 0})
                break
        self.settings_manager.save_keg_definitions(all_kegs)

        if self.sensor_logic: self.sensor_logic.force_recalculation()
        self._refresh_ui_for_settings_or_resume()
        messagebox.showinfo("Success", f"Tap {tap_idx+1} calibrated.\nNew K-Factor: {new_k:.2f}", parent=self.root)

    def _open_single_tap_calibration_popup(self, tap_index, parent_popup):
        tap_name = f"Tap {tap_index + 1}"
        current_k_factor = self.settings_manager.get_flow_calibration_factors()[tap_index]
        cal_settings = self.settings_manager.get_flow_calibration_settings()
        display_units = self.settings_manager.get_display_units()
        unit_label = "ml" if display_units == "metric" else "oz"
        
        self.single_cal_tap_index = tap_index
        self.single_cal_unit_label.set(unit_label)
        self.single_cal_target_volume_var.set(f"{cal_settings['to_be_poured']:.0f}")
        self.single_cal_deduct_volume_var.set(False)
        self.single_cal_measured_flow_var.set("0.00 L/min")
        self.single_cal_measured_pour_var.set("0.00")
        self.single_cal_current_factor_var.set(f"{current_k_factor:.2f}")
        self.single_cal_new_factor_var.set("")
        self._single_cal_calculated_new_factor = None
        self._single_cal_in_progress = False

        popup = tk.Toplevel(self.root)
        popup.title(f"Calibrate Flow Sensor: {tap_name}")
        popup.geometry("550x410") 
        popup.transient(self.root); popup.grab_set()
        self._single_cal_popup_window = popup 
        popup.protocol("WM_DELETE_WINDOW", lambda p=popup, pp=parent_popup: self._single_cal_check_close(p, pp))

        main_frame = ttk.Frame(popup, padding="15"); main_frame.pack(expand=True, fill="both")
        ttk.Label(main_frame, text=f"Tap to Calibrate: {tap_name}", font=('TkDefaultFont', 12, 'bold')).pack(anchor='w', pady=(0, 10))
        form_frame = ttk.Frame(main_frame); form_frame.pack(fill="x", pady=10)
        
        row = 0
        ttk.Label(form_frame, text=f"Deduct Measured Volume?").grid(row=row, column=0, sticky='w', padx=5, pady=5)
        rf = ttk.Frame(form_frame); rf.grid(row=row, column=1, columnspan=2, sticky='w', padx=5, pady=5)
        tk.Radiobutton(rf, text="No", variable=self.single_cal_deduct_volume_var, value=False).pack(side='left', padx=(0, 15))
        tk.Radiobutton(rf, text="Yes", variable=self.single_cal_deduct_volume_var, value=True).pack(side='left')
        row += 1
        
        ttk.Label(form_frame, text="Volume Poured:").grid(row=row, column=0, sticky='w', padx=5, pady=5)
        self._single_cal_volume_entry = ttk.Entry(form_frame, textvariable=self.single_cal_target_volume_var, width=10, justify='center', state='readonly') 
        self._single_cal_volume_entry.grid(row=row, column=1, sticky='w', padx=5, pady=5)
        ttk.Label(form_frame, textvariable=self.single_cal_unit_label).grid(row=row, column=2, sticky='w'); row += 1

        ttk.Label(form_frame, text="Measured Pour:").grid(row=row, column=0, sticky='w', padx=5, pady=5)
        ttk.Label(form_frame, textvariable=self.single_cal_measured_pour_var, relief='sunken', anchor='w', width=10).grid(row=row, column=1, sticky='w', padx=5, pady=5)
        ttk.Label(form_frame, textvariable=self.single_cal_unit_label).grid(row=row, column=2, sticky='w'); row += 1

        ttk.Label(form_frame, text="Flow Rate:").grid(row=row, column=0, sticky='w', padx=5, pady=5)
        ttk.Label(form_frame, textvariable=self.single_cal_measured_flow_var, relief='sunken', anchor='w', width=10).grid(row=row, column=1, sticky='w', padx=5, pady=5)
        ttk.Label(form_frame, text="L/min").grid(row=row, column=2, sticky='w'); row += 1
        
        ttk.Label(form_frame, text="Current K-Factor:").grid(row=row, column=0, sticky='w', padx=5, pady=5)
        ttk.Label(form_frame, textvariable=self.single_cal_current_factor_var, relief='sunken', anchor='w', width=10).grid(row=row, column=1, sticky='w', padx=5, pady=5); row += 1
        
        ttk.Label(form_frame, text="New Calculated K:").grid(row=row, column=0, sticky='w', padx=5, pady=5)
        ttk.Label(form_frame, textvariable=self.single_cal_new_factor_var, relief='sunken', anchor='w', width=10).grid(row=row, column=1, sticky='w', padx=5, pady=5); row += 1
        
        btn_frame = ttk.Frame(main_frame); btn_frame.pack(fill="x", pady=20)
        self.single_cal_start_btn = ttk.Button(btn_frame, text="Start Cal", width=12, command=self._single_cal_start)
        self.single_cal_start_btn.pack(side='left', padx=5, fill='x', expand=True)
        self.single_cal_stop_btn = ttk.Button(btn_frame, text="Stop Cal", width=12, state=tk.DISABLED, command=self._single_cal_stop)
        self.single_cal_stop_btn.pack(side='left', padx=5, fill='x', expand=True)
        self.single_cal_set_btn = ttk.Button(btn_frame, text="Set New Factor", width=16, state=tk.DISABLED, command=lambda: self._single_cal_set(destroy_on_success=True))
        self.single_cal_set_btn.pack(side='left', padx=5, fill='x', expand=True)

        footer = ttk.Frame(popup, padding="10"); footer.pack(fill="x", side="bottom")
        ttk.Button(footer, text="Close", command=lambda p=popup, pp=parent_popup: self._single_cal_check_close(p, pp)).pack(side="right")

    def _single_cal_start(self):
        try: float(self.single_cal_target_volume_var.get())
        except ValueError: messagebox.showerror("Error", "Invalid target volume."); return
        if self._single_cal_in_progress: return
        
        self.settings_manager.save_flow_calibration_settings(to_be_poured_value=float(self.single_cal_target_volume_var.get()))
        self._single_cal_in_progress = True
        self.single_cal_new_factor_var.set("")
        self._single_cal_calculated_new_factor = None
        
        self.single_cal_start_btn.config(state=tk.DISABLED); self.single_cal_stop_btn.config(state=tk.NORMAL)
        self.single_cal_set_btn.config(state=tk.DISABLED); self._single_cal_volume_entry.config(state='normal')
        self.single_cal_measured_flow_var.set("0.00 L/min"); self.single_cal_measured_pour_var.set("0.00")
        
        if self.sensor_logic: self.sensor_logic.start_flow_calibration(self.single_cal_tap_index, self.single_cal_target_volume_var.get())

    def _single_cal_stop(self):
        if not self._single_cal_in_progress: return
        self._single_cal_in_progress = False
        self._single_cal_volume_entry.config(state='readonly')
        
        if self.sensor_logic:
            total_pulses, final_measured_liters = self.sensor_logic.stop_flow_calibration(self.single_cal_tap_index)
        else: total_pulses, final_measured_liters = 0, 0.0
            
        try: target_pour_user = float(self.single_cal_target_volume_var.get())
        except: target_pour_user = 0.0
        
        target_l = target_pour_user / 1000.0 if self.single_cal_unit_label.get() == "ml" else target_pour_user * OZ_TO_LITERS
        
        if self.single_cal_deduct_volume_var.get() and self.sensor_logic and target_l > 0:
            self.sensor_logic.deduct_volume_from_keg(self.single_cal_tap_index, target_l)
            messagebox.showinfo("Inventory Deduction", f"Deducted {target_l:.2f} L from inventory.", parent=self._single_cal_popup_window)

        if target_l > 0 and total_pulses > 0:
            new_k = total_pulses / target_l
            self._single_cal_calculated_new_factor = new_k
            self.single_cal_new_factor_var.set(f"{new_k:.2f}")
            self.single_cal_set_btn.config(state=tk.NORMAL)
        else:
            self.single_cal_new_factor_var.set("Error")
            self.single_cal_set_btn.config(state=tk.DISABLED)

        self.single_cal_start_btn.config(state=tk.NORMAL); self.single_cal_stop_btn.config(state=tk.DISABLED)

    def _single_cal_set(self, destroy_on_success=False, primary_popup=None):
        if self._single_cal_calculated_new_factor is None: return
        new_k = self._single_cal_calculated_new_factor
        factors = self.settings_manager.get_flow_calibration_factors()
        factors[self.single_cal_tap_index] = new_k
        self.settings_manager.save_flow_calibration_factors(factors)
        self.single_cal_current_factor_var.set(f"{new_k:.2f}")
        self.single_cal_set_btn.config(state=tk.DISABLED)
        
        if self.sensor_logic: self.sensor_logic.force_recalculation()
        messagebox.showinfo("Success", f"New K-Factor saved: {new_k:.2f}", parent=self.single_cal_set_btn.winfo_toplevel())
        
        if destroy_on_success and primary_popup: 
             self._single_cal_popup_window = None; primary_popup.destroy()

    def _single_cal_check_close(self, popup_window, parent_window=None):
        if self._single_cal_in_progress and self.sensor_logic: self._single_cal_stop()
        self._single_cal_popup_window = None
        if parent_window and parent_window.winfo_exists(): parent_window.grab_set()
        popup_window.destroy()

    def _open_manually_enter_calibration_factor_popup(self, parent_popup):
        popup = tk.Toplevel(self.root)
        popup.title("Manual Calibration Factor")
        popup.geometry("550x450"); popup.transient(self.root); popup.grab_set()
        
        frame = ttk.Frame(popup, padding=10); frame.pack(expand=True, fill="both")
        
        factors = self.settings_manager.get_flow_calibration_factors()
        for i in range(self.settings_manager.get_displayed_taps()):
            self.flow_cal_current_factors[i].set(f"{factors[i]:.2f}")
            self.flow_cal_new_factor_entries[i].set("")
            
            row = ttk.Frame(frame); row.pack(fill='x', pady=2)
            ttk.Label(row, text=f"Tap {i+1}", width=10).pack(side='left')
            ttk.Label(row, textvariable=self.flow_cal_current_factors[i], width=10, relief='sunken').pack(side='left')
            e = ttk.Entry(row, textvariable=self.flow_cal_new_factor_entries[i], width=10); e.pack(side='left', padx=5)
            ttk.Button(row, text="Set", command=lambda idx=i, p=popup: self._set_new_calibration_factor(idx, p)).pack(side='left')
        
        ttk.Button(popup, text="Close", command=popup.destroy).pack(side="bottom", pady=10)

    def _set_new_calibration_factor(self, idx, popup):
        try:
            val = float(self.flow_cal_new_factor_entries[idx].get())
            if val <= 0: raise ValueError
            factors = self.settings_manager.get_flow_calibration_factors()
            factors[idx] = val
            self.settings_manager.save_flow_calibration_factors(factors)
            self.flow_cal_current_factors[idx].set(f"{val:.2f}")
            self.flow_cal_new_factor_entries[idx].set("")
            if self.sensor_logic: self.sensor_logic.force_recalculation()
        except ValueError: messagebox.showerror("Error", "Invalid factor.")

    # =========================================================================
    #  SYSTEM SETTINGS (LITE)
    # =========================================================================

    def _open_system_settings_popup(self):
        popup = tk.Toplevel(self.root)
        popup.title("System Settings")
        self._center_popup(popup, 450, 400)
        popup.transient(self.root); popup.grab_set()
        
        frame = ttk.Frame(popup, padding=10); frame.pack(fill="both", expand=True)
        
        # UI Mode
        ttk.Label(frame, text="Display Detail Mode:").pack(anchor="w", pady=5)
        self.system_settings_ui_mode_var.set(self.settings_manager.get_ui_mode())
        ttk.Combobox(frame, textvariable=self.system_settings_ui_mode_var, values=["detailed", "basic"], state="readonly").pack(fill="x")
        
        # Units
        ttk.Label(frame, text="Display Units:").pack(anchor="w", pady=(10, 5))
        self.system_settings_unit_var.set(self.settings_manager.get_display_units())
        ttk.Combobox(frame, textvariable=self.system_settings_unit_var, values=["metric", "imperial"], state="readonly").pack(fill="x")
        
        # Taps
        ttk.Label(frame, text="Number of Visible Taps:").pack(anchor="w", pady=(10, 5))
        self.system_settings_taps_var.set(str(self.settings_manager.get_displayed_taps()))
        ttk.Entry(frame, textvariable=self.system_settings_taps_var).pack(fill="x")

        # Pour Volumes
        ttk.Label(frame, text="Standard Pour Size (for Quick Pour buttons):").pack(anchor="w", pady=(10, 5))
        p_frame = ttk.Frame(frame)
        p_frame.pack(fill='x')
        
        p_settings = self.settings_manager.get_pour_volume_settings()
        self.system_settings_pour_ml_var.set(str(p_settings['metric_pour_ml']))
        self.system_settings_pour_oz_var.set(str(p_settings['imperial_pour_oz']))
        
        ttk.Label(p_frame, text="Metric (ml):").pack(side='left')
        ttk.Entry(p_frame, textvariable=self.system_settings_pour_ml_var, width=6).pack(side='left', padx=5)
        ttk.Label(p_frame, text="Imperial (oz):").pack(side='left', padx=(10, 0))
        ttk.Entry(p_frame, textvariable=self.system_settings_pour_oz_var, width=6).pack(side='left', padx=5)

        ttk.Button(frame, text="Save Settings", command=lambda: self._save_system_settings(popup)).pack(side="bottom", pady=10)

    def _save_system_settings(self, popup):
        self.settings_manager.save_ui_mode(self.system_settings_ui_mode_var.get())
        self.settings_manager.save_display_units(self.system_settings_unit_var.get())
        try: self.settings_manager.save_displayed_taps(int(self.system_settings_taps_var.get()))
        except ValueError: pass
        try:
            self.settings_manager.save_pour_volume_settings(self.system_settings_pour_ml_var.get(), self.system_settings_pour_oz_var.get())
        except ValueError: pass
        
        self._refresh_ui_for_settings_or_resume()
        popup.destroy()

    # =========================================================================
    #  ABOUT
    # =========================================================================

    def _open_about_popup(self):
        popup = tk.Toplevel(self.root)
        popup.title("About")
        self._center_popup(popup, 350, 250)
        popup.transient(self.root); popup.grab_set()
        
        ttk.Label(popup, text="Keg Level Monitor", font=("Arial", 16, "bold")).pack(pady=(20, 10))
        ttk.Label(popup, text="Lite Version", font=("Arial", 10, "italic")).pack()
        ttk.Label(popup, text=self.app_version_string, font=("Arial", 9)).pack(pady=10)
        
        self._load_support_image()
        if self.support_qr_image:
             ttk.Label(popup, image=self.support_qr_image).pack(pady=5)
             
        ttk.Button(popup, text="Close", command=popup.destroy).pack(side="bottom", pady=10)

    def _load_support_image(self):
        if self.support_qr_image: return
        try:
            image_path = os.path.join(self.base_dir, "assets", "support.gif")
            self.support_qr_image = tk.PhotoImage(file=image_path)
        except Exception: self.support_qr_image = None

    def _center_popup(self, popup, width, height):
        popup.withdraw() 
        popup.update_idletasks()
        x = int((popup.winfo_screenwidth()/2) - (width/2))
        y = int((popup.winfo_screenheight()/2) - (height/2))
        popup.geometry(f"{width}x{height}+{max(0,x)}+{max(0,y)}")
        popup.deiconify()
