"""
joymapper_gui.py - GUI for building the joymapper config.json.

Separate tool: does not modify or import gamepad_mapper.py.

Features:
  - List / select connected gamepads (device GUID is stored in the config)
  - Press a button on ANY connected device: the device is selected
    automatically and its mapping is created / highlighted
  - Multiple devices per config file ('devices' list)
  - Add / edit / remove mappings for all supported modes
  - Load and save config files (legacy single-device format is auto-migrated)

Usage:
  python joymapper_gui.py
"""

import ctypes
import json
import os
import subprocess
import sys
import tkinter as tk
import webbrowser
from ctypes import wintypes
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

# Deliver joystick input even though the pygame window is hidden / unfocused.
os.environ.setdefault("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

CONFIG_FILE = "config.json"
POLL_MS = 20  # tkinter after() interval for joystick polling

WEBSITE_URL = "https://garcias-garage.de"
GITHUB_URL = "https://github.com/vgarcia007/joymapper"

# --- Color scheme (design tokens) -----------------------------------------
COL_BG = "#212529"        # token: background
COL_CARBON = "#2B3035"    # card shade (background, slightly lightened)
COL_RED = "#B00202"       # token: primary (accents, selection)
COL_RED_HOVER = "#D66A6B" # token: accent-1 (hover on primary elements)
COL_DARKRED = "#6A1214"   # token: accent-2 (subtle hover, e.g. dropdowns)
COL_LIGHT = "#D9D9D9"     # secondary text
COL_WHITE = "#FFFFFF"     # token: text
COL_DISABLED = "#666666"
COL_FIELD = "#000000"     # token: neutral (input field background)
COL_BTN = "#343A40"       # default button background (derived from background)

# Mode name -> list of (field, label, required)
MODE_FIELDS = {
    "press_release": [
        ("on_press", "Key on press", True),
        ("on_release", "Key on release", True),
    ],
    "toggle": [
        ("sequence", "Key sequence (comma separated)", True),
    ],
    "press": [
        ("key", "Key", True),
    ],
    "hold": [
        ("key", "Key (held)", True),
    ],
    "short_long_press": [
        ("short_press", "Key short press", True),
        ("long_press", "Key long press", True),
        ("on_release", "Key on release (optional)", False),
        ("threshold_ms", "Threshold (ms)", False),
    ],
    "short_long_press_hold": [
        ("short_press", "Key short press", True),
        ("long_press", "Key long press (held)", True),
        ("threshold_ms", "Threshold (ms)", False),
    ],
    "press_hold_release": [
        ("on_press", "Key on press", True),
        ("on_hold", "Key after threshold", True),
        ("on_release", "Key on release", True),
        ("threshold_ms", "Threshold (ms)", False),
    ],
}


def _app_dir() -> str:
    """Directory of the application: the exe folder when frozen (PyInstaller),
    otherwise the folder containing this script."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _init_pygame() -> None:
    pygame.init()
    pygame.joystick.init()
    if not pygame.display.get_surface():
        flags = pygame.NOFRAME
        if hasattr(pygame, "HIDDEN"):
            flags |= pygame.HIDDEN
        pygame.display.set_mode((1, 1), flags)


class JoymapperGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("joymapper config editor")
        # Let the MAPPINGS card grow when the window is resized; the
        # EDIT MAPPING column stays at its fixed size.
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(2, weight=1)
        icon_dir = os.path.dirname(os.path.abspath(__file__))
        ico_path = os.path.join(icon_dir, "icon.ico")
        png_path = os.path.join(icon_dir, "icon.png")
        try:
            if os.path.exists(ico_path):
                # .ico (multi-size) is what the Windows taskbar needs; a big
                # PNG via iconphoto alone often ends up as the generic icon.
                root.iconbitmap(default=ico_path)
                # CTk sets its own icon ~200ms after startup - re-apply ours.
                root.after(300, lambda: root.iconbitmap(default=ico_path))
            elif os.path.exists(png_path):
                self._icon = tk.PhotoImage(file=png_path)
                root.iconphoto(True, self._icon)
                root.after(300, lambda: root.iconphoto(True, self._icon))
        except tk.TclError:
            pass

        self.joystick = None
        self.devices: list = []
        self.prev_states: dict[int, list[int]] = {}   # per-device button snapshots
        self.device_entries: dict[str, dict] = {}     # guid/name -> config entry
        self.mappings: dict[str, dict] = {}            # mappings of selected device
        self.loaded_config: dict = {}
        self.mapper_proc: subprocess.Popen | None = None
        self.config_path = os.path.join(_app_dir(), CONFIG_FILE)

        self._build_widgets()
        # Don't allow shrinking below the initial layout size.
        root.update_idletasks()
        root.minsize(root.winfo_reqwidth(), root.winfo_reqheight())
        _init_pygame()
        self._refresh_devices()
        if os.path.exists(self.config_path):
            self._load_config_file(self.config_path)
        self._update_title()
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._in_size_move = False
        self._install_move_hook()
        self.root.after(POLL_MS, self._poll_joystick)

    def _install_move_hook(self) -> None:
        """Pause joystick polling while the window is dragged or resized.

        SDL's event pump (pygame.event.pump/get) processes the message queue
        of the WHOLE thread - including messages that belong to the native
        Win32 move loop of the Tk window. That steals mouse messages and
        aborts dragging. Windows signals the move loop via WM_ENTERSIZEMOVE /
        WM_EXITSIZEMOVE, which we intercept by subclassing the window proc."""
        WM_ENTERSIZEMOVE = 0x0231
        WM_EXITSIZEMOVE = 0x0232
        GWL_WNDPROC = -4
        GA_ROOT = 2
        LRESULT = ctypes.c_ssize_t
        WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT,
                                     wintypes.WPARAM, wintypes.LPARAM)
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.GetAncestor(self.root.winfo_id(), GA_ROOT)
            set_long = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
            set_long.restype = ctypes.c_void_p
            set_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
            call_proc = user32.CallWindowProcW
            call_proc.restype = LRESULT
            call_proc.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT,
                                  wintypes.WPARAM, wintypes.LPARAM]

            def wndproc(h, msg, wparam, lparam):
                if msg == WM_ENTERSIZEMOVE:
                    self._in_size_move = True
                elif msg == WM_EXITSIZEMOVE:
                    self._in_size_move = False
                    self._reset_button_states()  # skipped ticks -> re-snapshot
                return call_proc(self._orig_wndproc, h, msg, wparam, lparam)

            self._wndproc_ref = WNDPROC(wndproc)  # keep a reference (GC!)
            self._orig_wndproc = set_long(
                hwnd, GWL_WNDPROC,
                ctypes.cast(self._wndproc_ref, ctypes.c_void_p).value)
        except (AttributeError, OSError):
            pass  # non-Windows / unexpected failure: polling just stays active

    def _update_title(self) -> None:
        self.root.title(f"joymapper config editor - {os.path.basename(self.config_path)}")

    def _on_close(self) -> None:
        if self.mapper_proc is not None and self.mapper_proc.poll() is None:
            self.mapper_proc.terminate()
        self.root.destroy()

    # ------------------------------------------------------------------ UI

    def _build_widgets(self) -> None:
        self.root.configure(fg_color=COL_BG)
        self._lockable: list = []
        self._field_entries: list = []
        pad = {"padx": 10, "pady": 6}
        head_font = ctk.CTkFont(size=12, weight="bold")

        def card(row, column, title, columnspan=1, sticky="ew"):
            frame = ctk.CTkFrame(self.root, corner_radius=12, fg_color=COL_CARBON)
            frame.grid(row=row, column=column, columnspan=columnspan, sticky=sticky, **pad)
            ctk.CTkLabel(frame, text=title, text_color=COL_RED, font=head_font)\
                .grid(row=0, column=0, columnspan=4, sticky="w", padx=12, pady=(8, 0))
            return frame

        def make_entry(parent, var, width):
            return ctk.CTkEntry(parent, textvariable=var, width=width,
                                fg_color=COL_FIELD, border_color=COL_BTN,
                                text_color=COL_WHITE)

        def make_combo(parent, width, **kwargs):
            return ctk.CTkComboBox(parent, width=width, state="readonly",
                                   fg_color=COL_FIELD, border_color=COL_BTN,
                                   button_color=COL_BTN, button_hover_color=COL_RED_HOVER,
                                   dropdown_fg_color=COL_CARBON,
                                   dropdown_hover_color=COL_DARKRED,
                                   text_color=COL_WHITE, **kwargs)

        def make_button(parent, text, command, width=140, accent=False):
            return ctk.CTkButton(parent, text=text, command=command, width=width,
                                 fg_color=COL_RED if accent else COL_BTN,
                                 hover_color=COL_RED_HOVER if accent else COL_RED,
                                 text_color=COL_WHITE)

        # --- Device -----------------------------------------------------
        dev = card(0, 0, "DEVICE", columnspan=2)
        self.device_values: list[str] = []
        self.device_box = make_combo(dev, 440, values=[], command=self._on_device_selected)
        self.device_box.set("")
        self.device_box.grid(row=1, column=0, sticky="w", padx=12, pady=(4, 12))
        self.refresh_btn = make_button(dev, "Refresh", self._refresh_devices, width=90)
        self.refresh_btn.grid(row=1, column=1, padx=(0, 12), pady=(4, 12))
        self._lockable += [self.device_box, self.refresh_btn]

        # --- Settings ----------------------------------------------------
        settings = card(1, 0, "SETTINGS", columnspan=2)
        ctk.CTkLabel(settings, text="Poll interval (ms):").grid(
            row=1, column=0, sticky="w", padx=12, pady=(4, 12))
        self.poll_var = tk.StringVar(value="5")
        self.poll_entry = make_entry(settings, self.poll_var, 60)
        self.poll_entry.grid(row=1, column=1, sticky="w", padx=6, pady=(4, 12))
        ctk.CTkLabel(settings, text="Input method:").grid(
            row=1, column=2, sticky="w", padx=12, pady=(4, 12))
        self.input_method_var = tk.StringVar(value="keyboard")
        self.input_combo = make_combo(settings, 130, values=["keyboard", "scancode"],
                                      variable=self.input_method_var)
        self.input_combo.grid(row=1, column=3, sticky="w", padx=(6, 12), pady=(4, 12))
        self._lockable += [self.poll_entry, self.input_combo]

        # --- Mapping list --------------------------------------------------
        left = card(2, 0, "MAPPINGS", sticky="nsew")
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)
        style = ttk.Style(self.root)
        style.theme_use("clam")  # required so background/fieldbackground apply
        style.configure("Mappings.Treeview", background=COL_FIELD,
                        fieldbackground=COL_FIELD, foreground=COL_LIGHT,
                        borderwidth=0, rowheight=22, font=("Segoe UI", 9))
        style.configure("Mappings.Treeview.Heading", background=COL_BTN,
                        foreground=COL_WHITE, borderwidth=0,
                        font=("Segoe UI", 9, "bold"))
        style.map("Mappings.Treeview",
                  background=[("selected", COL_RED)],
                  foreground=[("selected", COL_WHITE)])
        style.map("Mappings.Treeview.Heading", background=[("active", COL_BTN)])
        self.mapping_list = ttk.Treeview(left, columns=("button", "mode", "keys"),
                                         show="headings", height=15,
                                         style="Mappings.Treeview",
                                         selectmode="browse")
        self.mapping_list.heading("button", text="Button", anchor="center")
        self.mapping_list.heading("mode", text="Mode", anchor="w")
        self.mapping_list.heading("keys", text="Keys", anchor="w")
        self.mapping_list.column("button", width=60, anchor="center", stretch=False)
        self.mapping_list.column("mode", width=150, stretch=False)
        self.mapping_list.column("keys", width=220, stretch=True)
        self.mapping_list.grid(row=1, column=0, sticky="nsew", padx=12, pady=6)
        self.mapping_list.bind("<<TreeviewSelect>>", self._on_mapping_selected)
        self.remove_btn = make_button(left, "Remove selected", self._remove_mapping)
        self.remove_btn.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
        self._lockable += [self.mapping_list, self.remove_btn]

        # --- Editor --------------------------------------------------------
        right = card(2, 1, "EDIT MAPPING", sticky="new")
        ctk.CTkLabel(right, text="Button number:").grid(row=1, column=0, sticky="w", padx=12, pady=4)
        self.button_var = tk.StringVar()
        self.button_entry = make_entry(right, self.button_var, 60)
        self.button_entry.grid(row=1, column=1, sticky="w", padx=6, pady=4)
        ctk.CTkLabel(right, text="(press a button on the device)",
                     text_color=COL_DISABLED).grid(row=1, column=2, sticky="w", padx=(6, 12), pady=4)

        ctk.CTkLabel(right, text="Mode:").grid(row=2, column=0, sticky="w", padx=12, pady=4)
        self.mode_var = tk.StringVar(value="press")
        self.mode_box = make_combo(right, 190, values=list(MODE_FIELDS.keys()),
                                   variable=self.mode_var,
                                   command=lambda _v: self._rebuild_fields())
        self.mode_box.grid(row=2, column=1, columnspan=2, sticky="w", padx=6, pady=4)

        self.fields_frame = ctk.CTkFrame(right, fg_color="transparent")
        self.fields_frame.grid(row=3, column=0, columnspan=3, sticky="ew", padx=6)
        self.field_vars: dict[str, tk.StringVar] = {}
        self._rebuild_fields()

        self.apply_btn = make_button(right, "Add / update mapping", self._apply_mapping)
        self.apply_btn.grid(row=4, column=0, columnspan=3, sticky="ew", padx=12, pady=(6, 12))
        self._lockable += [self.button_entry, self.mode_box, self.apply_btn]

        # --- Bottom ---------------------------------------------------------
        bottom = ctk.CTkFrame(self.root, fg_color="transparent")
        bottom.grid(row=3, column=0, columnspan=2, sticky="ew", **pad)
        self.load_btn = make_button(bottom, "Load config...", self._load_config_dialog, width=110)
        self.load_btn.grid(row=0, column=0, padx=(0, 6))
        self.save_btn = make_button(bottom, "Save", self._save_config, width=80)
        self.save_btn.grid(row=0, column=1, padx=6)
        self.save_as_btn = make_button(bottom, "Save as...", self._save_config_as, width=100)
        self.save_as_btn.grid(row=0, column=2, padx=6)
        self.run_btn = make_button(bottom, "Start mapper", self._toggle_mapper, accent=True)
        self.run_btn.grid(row=0, column=3, padx=6)
        self._lockable += [self.load_btn, self.save_btn, self.save_as_btn]

        self.status_var = tk.StringVar(value="Ready.")
        self.status_label = ctk.CTkLabel(self.root, textvariable=self.status_var,
                                         anchor="center", fg_color=COL_CARBON,
                                         text_color=COL_LIGHT, corner_radius=0)
        self.status_label.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(6, 0))

        # --- Footer: logo + links ---------------------------------------
        footer = ctk.CTkFrame(self.root, fg_color=COL_FIELD, corner_radius=0)
        footer.grid(row=5, column=0, columnspan=2, sticky="ew")
        footer.grid_columnconfigure(1, weight=1)

        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "logo_small.png")
        if os.path.exists(logo_path):
            try:
                self._logo = tk.PhotoImage(file=logo_path)
                tk.Label(footer, image=self._logo, bg=COL_FIELD, bd=0)\
                    .grid(row=0, column=0, sticky="w", padx=10, pady=4)
            except tk.TclError:
                pass

        def make_link(text, url, column):
            link = ctk.CTkLabel(footer, text=text, text_color=COL_RED,
                                cursor="hand2", font=ctk.CTkFont(size=11, underline=True))
            link.grid(row=0, column=column, sticky="e", padx=(12, 10), pady=4)
            link.bind("<Button-1>", lambda _e: webbrowser.open(url))

        make_link("garcias-garage.de", WEBSITE_URL, 2)
        make_link("GitHub", GITHUB_URL, 3)

    def _rebuild_fields(self) -> None:
        for child in self.fields_frame.winfo_children():
            child.destroy()
        self.field_vars = {}
        self._field_entries = []
        mode = self.mode_var.get()
        for i, (field, label, _required) in enumerate(MODE_FIELDS[mode]):
            ctk.CTkLabel(self.fields_frame, text=label + ":").grid(
                row=i, column=0, sticky="w", padx=6, pady=3)
            var = tk.StringVar()
            field_entry = ctk.CTkEntry(self.fields_frame, textvariable=var, width=190,
                                       fg_color=COL_FIELD, border_color=COL_BTN,
                                       text_color=COL_WHITE)
            field_entry.grid(row=i, column=1, sticky="w", padx=6, pady=3)
            self.field_vars[field] = var
            self._field_entries.append(field_entry)

    # ------------------------------------------------------------- Devices

    def _refresh_devices(self) -> None:
        pygame.joystick.quit()
        pygame.joystick.init()
        self._reset_button_states()
        self.devices = []
        entries = []
        for i in range(pygame.joystick.get_count()):
            joy = pygame.joystick.Joystick(i)
            joy.init()
            self.devices.append(joy)
            entries.append(f"{i}: {joy.get_name()}  [{joy.get_guid()}]")
        self.device_values = entries
        self.device_box.configure(values=entries)
        if entries:
            self.device_box.set(entries[0])
            self._on_device_selected()
            self.status_var.set(f"{len(entries)} device(s) found.")
        else:
            self.device_box.set("")
            self.joystick = None
            self.status_var.set("No devices found.")

    def _on_device_selected(self, _choice=None) -> None:
        try:
            idx = self.device_values.index(self.device_box.get())
        except ValueError:
            return
        if 0 <= idx < len(self.devices):
            self.joystick = self.devices[idx]
            self.mappings = self._device_entry(self.joystick)["mappings"]
            self._refresh_mapping_list()

    def _device_entry(self, joy) -> dict:
        """Return (or create) the config entry for the given joystick."""
        guid = joy.get_guid().lower()
        entry = self.device_entries.get(guid)
        if entry is not None:
            return entry
        # Fallback: match a loaded name-only entry.
        name = joy.get_name().lower()
        for e in self.device_entries.values():
            sub = e.get("target_name_contains", "").lower()
            if not e.get("target_guid") and sub and sub in name:
                return e
        entry = {"target_guid": joy.get_guid(),
                 "target_name_contains": joy.get_name(),
                 "mappings": {}}
        self.device_entries[guid] = entry
        return entry

    def _reset_button_states(self) -> None:
        """Forget polled button states; they are re-snapshotted from the REAL
        current state on the next poll tick (avoids phantom presses)."""
        self.prev_states = {}

    def _poll_joystick(self) -> None:
        if self._in_size_move:
            # Window is being dragged/resized: pumping SDL events now would
            # abort the native move loop. Skip this tick entirely.
            self.root.after(POLL_MS, self._poll_joystick)
            return
        if self.mapper_proc is not None:
            if self.mapper_proc.poll() is not None:
                self._on_mapper_stopped()
            else:
                pygame.event.get()  # keep queue drained, ignore input
                self.root.after(POLL_MS, self._poll_joystick)
                return
        if self.devices:
            pygame.event.pump()
            event_device = None
            event_button = None
            for i, joy in enumerate(self.devices):
                num = joy.get_numbuttons()
                prev = self.prev_states.get(i)
                if prev is None or len(prev) != num:
                    # First tick after start/refresh: snapshot the REAL state
                    # so already-held buttons don't fire phantom presses.
                    self.prev_states[i] = [1 if joy.get_button(b) else 0
                                           for b in range(num)]
                    continue
                for b in range(num):
                    current = 1 if joy.get_button(b) else 0
                    if current and not prev[b] and event_device is None:
                        event_device, event_button = i, b
                    prev[b] = current

            if event_device is not None:
                # Auto-select the device that sent the button press.
                if self.devices[event_device] is not self.joystick:
                    self.device_box.set(self.device_values[event_device])
                    self._on_device_selected()
                self._focus_button_mapping(event_button)

            pygame.event.get()  # drain queue
        self.root.after(POLL_MS, self._poll_joystick)

    # -------------------------------------------------------------- Mapper

    def _toggle_mapper(self) -> None:
        if self.mapper_proc is not None:
            self.mapper_proc.terminate()
            self.status_var.set("Stopping mapper...")
            return
        if self._has_unsaved_changes():
            if messagebox.askyesno("joymapper",
                                   "Mappings have unsaved changes.\nSave config first?"):
                self._save_config()
        if not os.path.exists(self.config_path):
            messagebox.showwarning("joymapper",
                                   f"{self.config_path} not found. Save the config first.")
            return
        app_dir = _app_dir()
        if getattr(sys, "frozen", False):
            # Frozen exe: launch joymapper.exe sitting next to this exe.
            mapper_exe = os.path.join(app_dir, "joymapper.exe")
            if not os.path.exists(mapper_exe):
                messagebox.showerror(
                    "joymapper",
                    "joymapper.exe not found next to the GUI.\n"
                    "Both files must stay in the same folder.")
                return
            cmd = [mapper_exe, "--run", "--config", self.config_path]
        else:
            cmd = [sys.executable, os.path.join(app_dir, "gamepad_mapper.py"),
                   "--run", "--config", self.config_path]
        try:
            self.mapper_proc = subprocess.Popen(cmd, cwd=app_dir)
        except OSError as exc:
            messagebox.showerror("joymapper", f"Failed to start mapper:\n{exc}")
            self.mapper_proc = None
            return
        self.run_btn.configure(text="Stop mapper")
        self._set_ui_enabled(False)
        self.status_var.set("Mapper running - editing disabled. Click 'Stop mapper' to edit again.")

    def _on_mapper_stopped(self) -> None:
        self.mapper_proc = None
        self.run_btn.configure(text="Start mapper")
        self._set_ui_enabled(True)
        self._reset_button_states()  # avoid phantom presses after re-enable
        self.status_var.set("Mapper stopped - editing enabled.")

    def _set_ui_enabled(self, enabled: bool) -> None:
        for widget in self._lockable + self._field_entries:
            try:
                if isinstance(widget, ttk.Treeview):
                    widget.configure(selectmode="browse" if enabled else "none")
                elif isinstance(widget, ctk.CTkComboBox):
                    widget.configure(state="readonly" if enabled else "disabled")
                else:
                    widget.configure(state="normal" if enabled else "disabled")
            except tk.TclError:
                pass

    # ------------------------------------------------------------- Mappings

    def _focus_button_mapping(self, btn: int) -> None:
        """Pressing a device button jumps to its mapping: create a new set if
        none exists yet, otherwise highlight the existing one."""
        key = str(btn)
        if key in self.mappings:
            status = f"Button {btn}: existing mapping selected."
        else:
            self.mappings[key] = {"mode": "press", "key": ""}
            self._refresh_mapping_list()
            status = f"Button {btn}: new mapping created - fill in the fields and click Add / update."
        self._select_mapping_in_list(key)
        self._load_mapping_into_editor(key)
        self.status_var.set(status)

    def _select_mapping_in_list(self, key: str) -> None:
        if self.mapping_list.exists(key):
            self.mapping_list.selection_set(key)
            self.mapping_list.see(key)

    def _load_mapping_into_editor(self, key: str) -> None:
        mapping = self.mappings.get(key)
        if mapping is None:
            return
        self.button_var.set(key)
        self.mode_var.set(mapping["mode"])
        self._rebuild_fields()
        for field, var in self.field_vars.items():
            value = mapping.get(field, "")
            if isinstance(value, list):
                value = ", ".join(value)
            var.set(str(value))

    def _apply_mapping(self) -> None:
        btn = self.button_var.get().strip()
        if not btn.isdigit():
            messagebox.showwarning("joymapper", "Button number must be a number.")
            return
        mode = self.mode_var.get()
        mapping: dict = {"mode": mode}
        for field, label, required in MODE_FIELDS[mode]:
            value = self.field_vars[field].get().strip()
            if not value:
                if required:
                    messagebox.showwarning("joymapper", f"'{label}' is required.")
                    return
                continue
            if field == "sequence":
                mapping[field] = [k.strip() for k in value.split(",") if k.strip()]
            elif field == "threshold_ms":
                if not value.isdigit():
                    messagebox.showwarning("joymapper", "Threshold must be a number (ms).")
                    return
                mapping[field] = int(value)
            else:
                mapping[field] = value
        self.mappings[btn] = mapping
        self._refresh_mapping_list()
        self.status_var.set(f"Mapping for button {btn} saved.")

    def _remove_mapping(self) -> None:
        selection = self.mapping_list.selection()
        if not selection:
            return
        btn = selection[0]
        self.mappings.pop(btn, None)
        self._refresh_mapping_list()
        self.status_var.set(f"Mapping for button {btn} removed.")

    @staticmethod
    def _mapping_keys_text(mapping: dict) -> str:
        """Compact, human-readable summary of a mapping's keys for the table."""
        parts = []
        for field, _label, _required in MODE_FIELDS.get(mapping["mode"], []):
            if field == "threshold_ms":
                continue
            value = mapping.get(field)
            if not value:
                continue
            if isinstance(value, list):
                value = ", ".join(value)
            parts.append(str(value))
        text = " / ".join(parts)
        threshold = mapping.get("threshold_ms")
        if threshold:
            text += f"  ({threshold} ms)"
        return text

    def _refresh_mapping_list(self) -> None:
        self.mapping_list.delete(*self.mapping_list.get_children())
        for btn in sorted(self.mappings, key=int):
            mapping = self.mappings[btn]
            self.mapping_list.insert("", "end", iid=btn,
                                     values=(btn, mapping["mode"],
                                             self._mapping_keys_text(mapping)))

    def _on_mapping_selected(self, _event=None) -> None:
        selection = self.mapping_list.selection()
        if not selection:
            return
        self._load_mapping_into_editor(selection[0])

    # --------------------------------------------------------------- Config

    def _load_config_dialog(self) -> None:
        path = filedialog.askopenfilename(
            title="Load config",
            initialdir=os.path.dirname(self.config_path),
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if not path:
            return
        self._load_config_file(path)

    def _load_config_file(self, path: str) -> None:
        if not os.path.exists(path):
            messagebox.showinfo("joymapper", f"{path} not found.")
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except json.JSONDecodeError as exc:
            messagebox.showerror("joymapper", f"Failed to parse {path}:\n{exc}")
            return
        self.config_path = os.path.abspath(path)
        self.loaded_config = config
        self.poll_var.set(str(config.get("poll_interval_ms", 5)))
        self.input_method_var.set(config.get("input_method", "keyboard"))
        # Build device entries (supports legacy single-device format).
        self.device_entries = {}
        for e in self._config_device_list(config):
            key = (e.get("target_guid") or e.get("target_name_contains", "")).lower()
            if not key:
                continue
            self.device_entries[key] = {
                "target_guid": e.get("target_guid", ""),
                "target_name_contains": e.get("target_name_contains", ""),
                "mappings": dict(e.get("mappings", {})),
            }
        # Select the first configured device that is connected.
        selected = False
        for i, joy in enumerate(self.devices):
            if joy.get_guid().lower() in self.device_entries:
                self.device_box.set(self.device_values[i])
                self._on_device_selected()
                selected = True
                break
        if not selected and self.joystick is not None:
            self.mappings = self._device_entry(self.joystick)["mappings"]
        self._refresh_mapping_list()
        self._update_title()
        self.status_var.set(f"Loaded {os.path.basename(self.config_path)}.")

    @staticmethod
    def _config_device_list(config: dict) -> list:
        """Return the devices list; supports the legacy single-device format."""
        if "devices" in config:
            return list(config.get("devices") or [])
        if config.get("target_guid") or config.get("target_name_contains"):
            return [{"target_guid": config.get("target_guid", ""),
                     "target_name_contains": config.get("target_name_contains", ""),
                     "mappings": config.get("mappings", {})}]
        return []

    def _has_unsaved_changes(self) -> bool:
        saved = {}
        for e in self._config_device_list(self.loaded_config):
            key = (e.get("target_guid") or e.get("target_name_contains", "")).lower()
            if key and e.get("mappings"):
                saved[key] = e["mappings"]
        current = {k: e["mappings"] for k, e in self.device_entries.items()
                   if e["mappings"]}
        return saved != current

    def _save_config_as(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save config as",
            initialdir=os.path.dirname(self.config_path),
            initialfile=os.path.basename(self.config_path),
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if not path:
            return
        self.config_path = os.path.abspath(path)
        self._update_title()
        self._save_config()

    def _save_config(self) -> None:
        if not self.poll_var.get().strip().isdigit():
            messagebox.showwarning("joymapper", "Poll interval must be a number (ms).")
            return
        incomplete = set()
        labels = []
        for key, entry in self.device_entries.items():
            name = entry.get("target_name_contains") or key
            for btn in sorted(entry["mappings"], key=int):
                mapping = entry["mappings"][btn]
                for field, label, required in MODE_FIELDS[mapping["mode"]]:
                    if required and not mapping.get(field):
                        incomplete.add((key, btn))
                        labels.append(f"{name}: btn {btn}")
                        break
        if incomplete:
            if not messagebox.askyesno(
                    "joymapper",
                    "These mappings are incomplete and will NOT be saved:\n"
                    + "\n".join(labels) + "\nSave anyway?"):
                return
        devices = []
        for key, entry in self.device_entries.items():
            mappings = {b: m for b, m in entry["mappings"].items()
                        if (key, b) not in incomplete}
            if mappings:
                devices.append({"target_guid": entry.get("target_guid", ""),
                                "target_name_contains": entry.get("target_name_contains", ""),
                                "mappings": mappings})
        # Keep unknown top-level fields, but drop legacy single-device keys.
        config = {k: v for k, v in self.loaded_config.items()
                  if k not in ("target_guid", "target_name_contains",
                               "mappings", "devices")}
        config["poll_interval_ms"] = int(self.poll_var.get().strip())
        config["input_method"] = self.input_method_var.get()
        config["devices"] = devices
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        self.loaded_config = config
        self.status_var.set(f"Saved {os.path.basename(self.config_path)}.")


def main() -> None:
    if sys.platform == "win32":
        import ctypes
        # Give the app its own taskbar identity so Windows shows our window
        # icon instead of the generic Python icon.
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("joymapper.gui")
    ctk.set_appearance_mode("dark")
    root = ctk.CTk()
    JoymapperGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
