"""
gamepad_mapper.py - Maps gamepad / button box inputs to keyboard events on Windows.

Usage:
  python gamepad_mapper.py --list          List all connected gamepads
  python gamepad_mapper.py --learn         Print button events for the target device
  python gamepad_mapper.py --run           Run the mapper using config.json
  python gamepad_mapper.py --init-config   Create an example config.json
"""

import argparse
import ctypes
import json
import os
import sys
import time
import math

import pygame

# Keyboard output: use the 'keyboard' library for sending key events on Windows.
try:
    import keyboard as kb
except ImportError:
    kb = None

CONFIG_FILE = "config.json"

# ---------------------------------------------------------------------------
# Key sending helpers
# ---------------------------------------------------------------------------

# "keyboard": events via the keyboard library (works for normal applications).
# "scancode": hardware scan codes via SendInput - required by many games that
#             read input through DirectInput / Raw Input.
_INPUT_METHOD = "keyboard"


def set_input_method(method: str) -> None:
    """Select how keys are sent: 'keyboard' (default) or 'scancode'."""
    global _INPUT_METHOD
    _INPUT_METHOD = method


# --- SendInput / scan code implementation (Windows) ------------------------

_KEYEVENTF_SCANCODE = 0x0008
_KEYEVENTF_KEYUP = 0x0002
_KEYEVENTF_EXTENDEDKEY = 0x0001


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", _KEYBDINPUT), ("padding", ctypes.c_ubyte * 32)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("union", _INPUTUNION)]


def _send_scancode(key: str, keyup: bool) -> None:
    """Send a key as a hardware scan code via SendInput (DirectInput games)."""
    scan_codes = kb.key_to_scan_codes(key)
    scan = scan_codes[0]
    flags = _KEYEVENTF_SCANCODE
    if scan & 0xE000 == 0xE000:
        flags |= _KEYEVENTF_EXTENDEDKEY
        scan &= 0xFF
    if keyup:
        flags |= _KEYEVENTF_KEYUP
    inp = _INPUT(type=1)  # INPUT_KEYBOARD
    inp.union.ki = _KEYBDINPUT(0, scan, flags, 0, None)
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))


def send_key(key: str) -> None:
    """Press and immediately release a key."""
    if kb is None:
        print(f"[ERROR] 'keyboard' library not installed. Cannot send key: {key}")
        return
    if _INPUT_METHOD == "scancode":
        _send_scancode(key, keyup=False)
        time.sleep(0.02)
        _send_scancode(key, keyup=True)
    else:
        kb.send(key)


def key_down(key: str) -> None:
    """Press (hold down) a key without releasing it."""
    if kb is None:
        print(f"[ERROR] 'keyboard' library not installed. Cannot press key: {key}")
        return
    if _INPUT_METHOD == "scancode":
        _send_scancode(key, keyup=False)
    else:
        kb.press(key)


def key_up(key: str) -> None:
    """Release a previously held key."""
    if kb is None:
        print(f"[ERROR] 'keyboard' library not installed. Cannot release key: {key}")
        return
    if _INPUT_METHOD == "scancode":
        _send_scancode(key, keyup=True)
    else:
        kb.release(key)


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "poll_interval_ms": 5,
    "input_method": "keyboard",
    "devices": [
        {
            "target_guid": "03000000c0160000dc27000000010000",
            "target_name_contains": "Button Box",
            "mappings": {
                "0": {
                    "mode": "press_release",
                    "on_press": "a",
                    "on_release": "b"
                },
                "1": {
                    "mode": "toggle",
                    "sequence": ["a", "b"]
                },
                "2": {
                    "mode": "press",
                    "key": "enter"
                },
                "3": {
                    "mode": "hold",
                    "key": "shift"
                },
                "4": {
                    "mode": "short_long_press",
                    "short_press": "f",
                    "long_press": "g",
                    "threshold_ms": 600
                }
            }
        }
    ]
}


def create_default_config() -> None:
    """Write a default config.json if it does not already exist."""
    if os.path.exists(CONFIG_FILE):
        print(f"[INFO] '{CONFIG_FILE}' already exists. Not overwriting.")
        return
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(DEFAULT_CONFIG, f, indent=2)
    print(f"[INFO] Created '{CONFIG_FILE}' with example configuration.")


def _load_raw_config() -> dict:
    """Read and JSON-parse config.json, exiting on any file/parse error."""
    if not os.path.exists(CONFIG_FILE):
        print(f"[ERROR] '{CONFIG_FILE}' not found. Run --init-config to create one.")
        sys.exit(1)
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
    except json.JSONDecodeError as exc:
        print(f"[ERROR] Failed to parse '{CONFIG_FILE}': {exc}")
        sys.exit(1)
    return config


def _normalize_config(config: dict) -> dict:
    """Support both config formats: the legacy single-device layout
    (top-level target_guid / target_name_contains / mappings) and the new
    multi-device layout with a 'devices' list. Returns the config with a
    'devices' list in place.
    """
    if "devices" not in config:
        device = {}
        for field in ("target_guid", "target_name_contains", "mappings"):
            if field in config:
                device[field] = config[field]
        config["devices"] = [device] if device else []
    return config


def load_device_config() -> dict:
    """Load config and validate only the device-identification fields.

    Used by --learn, which is run *before* mappings are known, so 'mappings'
    is intentionally not required here.
    """
    config = _normalize_config(_load_raw_config())
    if not any(d.get("target_guid") or d.get("target_name_contains")
               for d in config["devices"]):
        print("[ERROR] Config must contain at least one device with "
              "'target_guid' and/or 'target_name_contains'.")
        sys.exit(1)
    return config


def load_config() -> dict:
    """Load and return the full configuration from the config file."""
    config = _normalize_config(_load_raw_config())

    if not config["devices"]:
        print("[ERROR] Config must contain at least one device "
              "(a 'devices' list or top-level 'target_guid'/'mappings').")
        sys.exit(1)

    input_method = config.get("input_method", "keyboard")
    if input_method not in ("keyboard", "scancode"):
        print(f"[ERROR] Unknown input_method '{input_method}'. "
              "Valid values: keyboard, scancode")
        sys.exit(1)

    for i, device in enumerate(config["devices"]):
        label = (device.get("target_name_contains")
                 or device.get("target_guid") or f"#{i}")
        if not device.get("target_guid") and not device.get("target_name_contains"):
            print(f"[ERROR] Device #{i}: must contain 'target_guid' "
                  "and/or 'target_name_contains'.")
            sys.exit(1)
        if "mappings" not in device or not isinstance(device["mappings"], dict):
            print(f"[ERROR] Device '{label}': must contain a 'mappings' object.")
            sys.exit(1)
        _validate_mappings(device["mappings"])

    return config


def _validate_mappings(mappings: dict) -> None:
    """Validate each mapping entry, exiting with an error message if invalid."""
    valid_modes = {"press_release", "toggle", "press", "hold", "short_long_press",
                   "short_long_press_hold", "press_hold_release"}
    for btn_str, mapping in mappings.items():
        if not btn_str.isdigit():
            print(f"[ERROR] Mapping key '{btn_str}' is not a valid button number.")
            sys.exit(1)
        mode = mapping.get("mode")
        if mode not in valid_modes:
            print(f"[ERROR] Button {btn_str}: unknown mode '{mode}'. "
                  f"Valid modes: {', '.join(sorted(valid_modes))}")
            sys.exit(1)
        if mode == "press_release":
            if "on_press" not in mapping or "on_release" not in mapping:
                print(f"[ERROR] Button {btn_str} (press_release): "
                      "requires 'on_press' and 'on_release'.")
                sys.exit(1)
        elif mode == "toggle":
            if "sequence" not in mapping or not isinstance(mapping["sequence"], list):
                print(f"[ERROR] Button {btn_str} (toggle): requires 'sequence' list.")
                sys.exit(1)
        elif mode == "press":
            if "key" not in mapping:
                print(f"[ERROR] Button {btn_str} (press): requires 'key'.")
                sys.exit(1)
        elif mode == "hold":
            if "key" not in mapping:
                print(f"[ERROR] Button {btn_str} (hold): requires 'key'.")
                sys.exit(1)
        elif mode in ("short_long_press", "short_long_press_hold"):
            if "short_press" not in mapping or "long_press" not in mapping:
                print(f"[ERROR] Button {btn_str} ({mode}): "
                      "requires 'short_press' and 'long_press'.")
                sys.exit(1)
        elif mode == "press_hold_release":
            if ("on_press" not in mapping or "on_hold" not in mapping
                    or "on_release" not in mapping):
                print(f"[ERROR] Button {btn_str} (press_hold_release): "
                      "requires 'on_press', 'on_hold' and 'on_release'.")
                sys.exit(1)


# ---------------------------------------------------------------------------
# Device discovery helpers
# ---------------------------------------------------------------------------

def _init_pygame() -> None:
    """Initialize pygame and the joystick subsystem.

    A display surface must exist on Windows so that SDL2's message pump runs
    and joystick events are actually delivered to the event queue.  We create
    a hidden 1×1 window to satisfy that requirement without showing any GUI.

    pygame.HIDDEN (available since pygame 2.0.0) keeps the window invisible.
    On older builds it degrades gracefully to a borderless window.
    """
    # SDL ignores joystick input when the window has no focus - and our
    # hidden window never gets focus. This hint must be set BEFORE
    # pygame.init() so joystick events are delivered in the background.
    os.environ.setdefault("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1")
    pygame.init()
    pygame.joystick.init()
    if not pygame.display.get_surface():
        flags = pygame.NOFRAME
        if hasattr(pygame, "HIDDEN"):
            flags |= pygame.HIDDEN
        pygame.display.set_mode((1, 1), flags)


def list_devices() -> None:
    """Print all connected gamepads / joysticks with their details."""
    _init_pygame()
    count = pygame.joystick.get_count()
    if count == 0:
        print("No gamepads / joysticks found.")
        return
    print(f"Found {count} device(s):\n")
    for i in range(count):
        joy = pygame.joystick.Joystick(i)
        joy.init()
        print(f"  Index : {i}")
        print(f"  Name  : {joy.get_name()}")
        print(f"  GUID  : {joy.get_guid()}")
        print(f"  Buttons: {joy.get_numbuttons()}")
        print(f"  Axes   : {joy.get_numaxes()}")
        print(f"  Hats   : {joy.get_numhats()}")
        print()


def find_target_device(config: dict):
    """
    Locate the target joystick using GUID (preferred) or name substring (fallback).

    Returns a pygame.joystick.Joystick instance or None.
    """
    _init_pygame()
    target_guid = config.get("target_guid", "").lower()
    target_name = config.get("target_name_contains", "").lower()

    count = pygame.joystick.get_count()
    if count == 0:
        return None

    # First pass: match by GUID
    if target_guid:
        for i in range(count):
            joy = pygame.joystick.Joystick(i)
            joy.init()
            if joy.get_guid().lower() == target_guid:
                return joy

    # Second pass: match by name substring
    if target_name:
        for i in range(count):
            joy = pygame.joystick.Joystick(i)
            joy.init()
            if target_name in joy.get_name().lower():
                return joy

    return None


# ---------------------------------------------------------------------------
# Learn mode
# ---------------------------------------------------------------------------

def run_learn_mode(joysticks) -> None:
    """
    Print button / axis / hat events from the given joystick(s) so the user
    can identify which physical control corresponds to which button number.
    Accepts a single joystick or a list of joysticks.
    """
    if not isinstance(joysticks, (list, tuple)):
        joysticks = [joysticks]
    multi = len(joysticks) > 1
    states = []
    for joystick in joysticks:
        name = joystick.get_name()
        print(f"[LEARN] Listening to: {name}  (GUID: {joystick.get_guid()})")
        print(f"[LEARN]   Buttons: {joystick.get_numbuttons()}  "
              f"Axes: {joystick.get_numaxes()}  Hats: {joystick.get_numhats()}")
        states.append({
            "joy": joystick,
            "prefix": f"  [{name}] " if multi else "  ",
            "buttons": [0] * max(0, joystick.get_numbuttons()),
            "axes": [0.0] * max(0, joystick.get_numaxes()),
            "hats": [(0, 0)] * max(0, joystick.get_numhats()),
        })
    print("[LEARN] Press buttons on your device(s). Press Ctrl+C to stop.\n")

    clock = pygame.time.Clock()
    last_activity = time.monotonic()
    try:
        while True:
            # Pump SDL once per tick so joystick state is refreshed even when
            # JOYBUTTON events are not delivered reliably by the driver stack.
            pygame.event.pump()

            for st in states:
                joy = st["joy"]
                prefix = st["prefix"]
                for btn in range(len(st["buttons"])):
                    current = 1 if joy.get_button(btn) else 0
                    if current != st["buttons"][btn]:
                        state = "DOWN" if current else "UP  "
                        print(f"{prefix}BUTTON {state}  button={btn}")
                        st["buttons"][btn] = current
                        last_activity = time.monotonic()
                for axis in range(len(st["axes"])):
                    current = float(joy.get_axis(axis))
                    if math.fabs(current - st["axes"][axis]) >= 0.05:
                        print(f"{prefix}AXIS STATE   axis={axis}  value={current:.4f}")
                        st["axes"][axis] = current
                        last_activity = time.monotonic()
                for hat in range(len(st["hats"])):
                    current = joy.get_hat(hat)
                    if current != st["hats"][hat]:
                        print(f"{prefix}HAT STATE    hat={hat}  value={current}")
                        st["hats"][hat] = current
                        last_activity = time.monotonic()

            pygame.event.get()  # drain queue

            if time.monotonic() - last_activity >= 5:
                print("  [HINWEIS] Keine Eingabe erkannt. Pruefe, ob das richtige "
                      "Geraet in der Config gewaehlt ist.")
                last_activity = time.monotonic()
            clock.tick(200)
    except KeyboardInterrupt:
        print("\n[LEARN] Stopped.")


# ---------------------------------------------------------------------------
# GamepadMapper class
# ---------------------------------------------------------------------------

class GamepadMapper:
    """
    Handles event processing and key dispatch for a single target joystick.
    """

    def __init__(self, joystick, config: dict) -> None:
        self.joystick = joystick
        self.config = config
        self.mappings = config.get("mappings", {})
        self.poll_interval_ms = config.get("poll_interval_ms", 5)
        # Contact bounce filter: a state change must persist this long before
        # it is accepted. Prevents e.g. short_long_press firing the short key
        # because the switch bounced while being pressed down.
        self.debounce_ms = config.get("debounce_ms", 20)

        # State per button
        self._pressed_buttons: set[int] = set()     # buttons currently held down
        self._toggle_indices: dict[int, int] = {}   # current sequence index for toggle mode
        self._held_keys: dict[int, str] = {}        # held key: hold / short_long_press_hold
        self._hold_deadlines: dict[int, float] = {} # press_hold_release: when on_hold fires
        self._long_deadlines: dict[int, float] = {} # short_long_press(_hold): when long_press fires
        self._long_fired: set[int] = set()          # buttons whose long_press already fired
        self._last_buttons: list | None = None      # polled button states (lazy init)
        self._pending: dict[int, tuple] = {}        # btn -> (state, since) debounce candidates

    def _handle_button_down(self, button: int) -> None:
        if button in self._pressed_buttons:
            return
        self._pressed_buttons.add(button)
        key = str(button)
        if key not in self.mappings:
            return
        mapping = self.mappings[key]
        mode = mapping["mode"]

        if mode == "press_release":
            send_key(mapping["on_press"])

        elif mode == "toggle":
            sequence = mapping["sequence"]
            idx = self._toggle_indices.get(button, 0)
            send_key(sequence[idx])
            self._toggle_indices[button] = (idx + 1) % len(sequence)

        elif mode == "press":
            send_key(mapping["key"])

        elif mode == "hold":
            k = mapping["key"]
            self._held_keys[button] = k
            key_down(k)

        elif mode in ("short_long_press", "short_long_press_hold"):
            threshold_ms = mapping.get("threshold_ms", 500)
            self._long_deadlines[button] = time.monotonic() + threshold_ms / 1000.0

        elif mode == "press_hold_release":
            send_key(mapping["on_press"])
            threshold_ms = mapping.get("threshold_ms", 500)
            self._hold_deadlines[button] = time.monotonic() + threshold_ms / 1000.0

    def _process_hold_thresholds(self) -> None:
        """Fire threshold-based keys while a button is still held down:
        press_hold_release on_hold and short_long_press long_press."""
        if not self._hold_deadlines and not self._long_deadlines:
            return
        now = time.monotonic()
        for button, deadline in list(self._hold_deadlines.items()):
            if now >= deadline:
                del self._hold_deadlines[button]
                mapping = self.mappings.get(str(button))
                if mapping is not None:
                    send_key(mapping["on_hold"])
        for button, deadline in list(self._long_deadlines.items()):
            if now >= deadline:
                del self._long_deadlines[button]
                self._long_fired.add(button)
                mapping = self.mappings.get(str(button))
                if mapping is not None:
                    if mapping["mode"] == "short_long_press_hold":
                        # Hold the long key until the button is released.
                        self._held_keys[button] = mapping["long_press"]
                        key_down(mapping["long_press"])
                    else:
                        send_key(mapping["long_press"])

    def _handle_button_up(self, button: int) -> None:
        if button not in self._pressed_buttons:
            return
        self._pressed_buttons.discard(button)
        key = str(button)
        if key not in self.mappings:
            return
        mapping = self.mappings[key]
        mode = mapping["mode"]

        if mode == "press_release":
            send_key(mapping["on_release"])

        elif mode == "hold":
            held = self._held_keys.pop(button, None)
            if held is not None:
                key_up(held)

        elif mode == "short_long_press":
            if button in self._long_fired:
                # long_press already fired while the button was held down.
                self._long_fired.discard(button)
            else:
                deadline = self._long_deadlines.pop(button, None)
                if deadline is None:
                    return
                if time.monotonic() >= deadline:
                    # Threshold elapsed in the same tick as the release.
                    send_key(mapping["long_press"])
                else:
                    send_key(mapping["short_press"])
            # Optional third key: always sent on release, after short/long.
            if "on_release" in mapping:
                send_key(mapping["on_release"])

        elif mode == "short_long_press_hold":
            if button in self._long_fired:
                # long_press is currently held down - release it.
                self._long_fired.discard(button)
                held = self._held_keys.pop(button, None)
                if held is not None:
                    key_up(held)
            else:
                deadline = self._long_deadlines.pop(button, None)
                if deadline is None:
                    return
                if time.monotonic() >= deadline:
                    # Threshold elapsed in the same tick as the release:
                    # press and release the long key immediately.
                    send_key(mapping["long_press"])
                else:
                    send_key(mapping["short_press"])

        elif mode == "press_hold_release":
            # Cancel a pending on_hold if released before the threshold.
            self._hold_deadlines.pop(button, None)
            send_key(mapping["on_release"])

    def poll(self) -> None:
        """Process one tick: detect button transitions and fire hold thresholds.

        A state change is only accepted after it persisted for debounce_ms,
        which filters out mechanical contact bounce.

        The caller is responsible for pygame.event.pump() so that several
        mappers can share a single event loop.
        """
        if self._last_buttons is None:
            self._last_buttons = [0] * max(0, self.joystick.get_numbuttons())
        now = time.monotonic()
        for btn in range(len(self._last_buttons)):
            current = 1 if self.joystick.get_button(btn) else 0
            if current == self._last_buttons[btn]:
                # Bounced back to the accepted state - discard the candidate.
                self._pending.pop(btn, None)
                continue
            if self.debounce_ms > 0:
                pending = self._pending.get(btn)
                if pending is None or pending[0] != current:
                    self._pending[btn] = (current, now)
                    continue
                if (now - pending[1]) * 1000 < self.debounce_ms:
                    continue
                del self._pending[btn]
            if current:
                self._handle_button_down(btn)
            else:
                self._handle_button_up(btn)
            self._last_buttons[btn] = current
        self._process_hold_thresholds()

    def release_held_keys(self) -> None:
        """Release any held keys (used on shutdown)."""
        for _btn, held_key in list(self._held_keys.items()):
            key_up(held_key)
        self._held_keys.clear()
        self._pressed_buttons.clear()

    def run(self) -> None:
        """Standalone event loop for this single device. Blocks until Ctrl+C."""
        name = self.joystick.get_name()
        guid = self.joystick.get_guid()
        print(f"[RUN] Using device: {name}  (GUID: {guid})")
        print("[RUN] Mapper running. Press Ctrl+C to stop.\n")

        clock = pygame.time.Clock()
        try:
            while True:
                # Keep SDL joystick state current even if event delivery is spotty.
                pygame.event.pump()
                self.poll()
                pygame.event.get()  # drain queue
                clock.tick(1000 / max(1, self.poll_interval_ms))
        except KeyboardInterrupt:
            self.release_held_keys()
            print("\n[RUN] Stopped.")


# ---------------------------------------------------------------------------
# Top-level run helper
# ---------------------------------------------------------------------------

def run_mapper(config: dict) -> None:
    """Find all configured devices and run one shared mapper loop."""
    config = _normalize_config(config)
    set_input_method(config.get("input_method", "keyboard"))
    poll_interval_ms = config.get("poll_interval_ms", 5)

    mappers = []
    used_instance_ids = set()
    for i, device in enumerate(config["devices"]):
        joystick = find_target_device(device)
        if joystick is None or joystick.get_instance_id() in used_instance_ids:
            guid = device.get("target_guid", "(none)")
            name = device.get("target_name_contains", "(none)")
            print(f"[WARN] Device #{i} not found (or already in use).")
            print(f"       target_guid          : {guid}")
            print(f"       target_name_contains : {name}")
            continue
        used_instance_ids.add(joystick.get_instance_id())
        device_config = {
            "mappings": device.get("mappings", {}),
            "poll_interval_ms": poll_interval_ms,
            "debounce_ms": config.get("debounce_ms", 20),
        }
        mappers.append(GamepadMapper(joystick, device_config))
        print(f"[RUN] Using device: {joystick.get_name()}  "
              f"(GUID: {joystick.get_guid()})")

    if not mappers:
        print("[ERROR] None of the configured devices were found.")
        print("        Run --list to see connected devices.")
        sys.exit(1)

    print("[RUN] Mapper running. Press Ctrl+C to stop.\n")
    clock = pygame.time.Clock()
    try:
        while True:
            pygame.event.pump()
            for mapper in mappers:
                mapper.poll()
            pygame.event.get()  # drain queue
            clock.tick(1000 / max(1, poll_interval_ms))
    except KeyboardInterrupt:
        for mapper in mappers:
            mapper.release_held_keys()
        print("\n[RUN] Stopped.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    global CONFIG_FILE

    parser = argparse.ArgumentParser(
        description="Map gamepad / button box inputs to keyboard events on Windows."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true",
                       help="List all connected gamepads / joysticks.")
    group.add_argument("--learn", action="store_true",
                       help="Print button events for the configured target device.")
    group.add_argument("--run", action="store_true",
                       help="Run the mapper using the config file.")
    group.add_argument("--init-config", action="store_true",
                       help="Create an example config.json if it does not exist.")
    parser.add_argument("--config", default="config.json", metavar="FILE",
                        help="Path to the config file (default: config.json). "
                             "Allows one config per device, e.g. for running "
                             "multiple mapper instances in parallel.")

    args = parser.parse_args()

    CONFIG_FILE = args.config

    if args.list:
        list_devices()

    elif args.init_config:
        create_default_config()

    elif args.learn:
        config = load_device_config()
        joysticks = []
        used_instance_ids = set()
        for device in config["devices"]:
            joy = find_target_device(device)
            if joy is not None and joy.get_instance_id() not in used_instance_ids:
                used_instance_ids.add(joy.get_instance_id())
                joysticks.append(joy)
        if not joysticks:
            print("[ERROR] None of the configured devices were found.")
            for i, device in enumerate(config["devices"]):
                print(f"        Device #{i}:")
                print(f"          target_guid          : {device.get('target_guid', '(none)')}")
                print(f"          target_name_contains : {device.get('target_name_contains', '(none)')}")
            print("        Run --list to see connected devices.")
            sys.exit(1)
        run_learn_mode(joysticks)

    elif args.run:
        config = load_config()
        run_mapper(config)


if __name__ == "__main__":
    main()
