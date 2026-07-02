"""
gamepad_mapper.py - Maps gamepad / button box inputs to keyboard events on Windows.

Usage:
  python gamepad_mapper.py --list          List all connected gamepads
  python gamepad_mapper.py --learn         Print button events for the target device
  python gamepad_mapper.py --run           Run the mapper using config.json
  python gamepad_mapper.py --init-config   Create an example config.json
"""

import argparse
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

def send_key(key: str) -> None:
    """Press and immediately release a key."""
    if kb is None:
        print(f"[ERROR] 'keyboard' library not installed. Cannot send key: {key}")
        return
    kb.send(key)


def key_down(key: str) -> None:
    """Press (hold down) a key without releasing it."""
    if kb is None:
        print(f"[ERROR] 'keyboard' library not installed. Cannot press key: {key}")
        return
    kb.press(key)


def key_up(key: str) -> None:
    """Release a previously held key."""
    if kb is None:
        print(f"[ERROR] 'keyboard' library not installed. Cannot release key: {key}")
        return
    kb.release(key)


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "target_guid": "03000000c0160000dc27000000010000",
    "target_name_contains": "Button Box",
    "poll_interval_ms": 5,
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


def load_device_config() -> dict:
    """Load config and validate only the device-identification fields.

    Used by --learn, which is run *before* mappings are known, so 'mappings'
    is intentionally not required here.
    """
    config = _load_raw_config()
    if "target_guid" not in config and "target_name_contains" not in config:
        print("[ERROR] Config must contain 'target_guid' and/or 'target_name_contains'.")
        sys.exit(1)
    return config


def load_config() -> dict:
    """Load and return the full configuration from config.json."""
    config = _load_raw_config()

    # Validate required fields
    if "target_guid" not in config and "target_name_contains" not in config:
        print("[ERROR] Config must contain 'target_guid' and/or 'target_name_contains'.")
        sys.exit(1)
    if "mappings" not in config or not isinstance(config["mappings"], dict):
        print("[ERROR] Config must contain a 'mappings' object.")
        sys.exit(1)

    # Validate each mapping entry
    valid_modes = {"press_release", "toggle", "press", "hold", "short_long_press",
                   "press_hold_release"}
    for btn_str, mapping in config["mappings"].items():
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
        elif mode == "short_long_press":
            if "short_press" not in mapping or "long_press" not in mapping:
                print(f"[ERROR] Button {btn_str} (short_long_press): "
                      "requires 'short_press' and 'long_press'.")
                sys.exit(1)
        elif mode == "press_hold_release":
            if ("on_press" not in mapping or "on_hold" not in mapping
                    or "on_release" not in mapping):
                print(f"[ERROR] Button {btn_str} (press_hold_release): "
                      "requires 'on_press', 'on_hold' and 'on_release'.")
                sys.exit(1)

    return config


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

def run_learn_mode(joystick) -> None:
    """
    Print button / axis / hat events from the given joystick so the user can
    identify which physical control corresponds to which button number.
    """
    name = joystick.get_name()
    guid = joystick.get_guid()
    num_buttons = joystick.get_numbuttons()
    num_axes = joystick.get_numaxes()
    num_hats = joystick.get_numhats()
    print(f"[LEARN] Listening to: {name}  (GUID: {guid})")
    print(f"[LEARN] Buttons reported by device: {num_buttons}")
    print(f"[LEARN] Axes reported by device: {num_axes}")
    print(f"[LEARN] Hats reported by device: {num_hats}")
    print("[LEARN] Press buttons on your device. Press Ctrl+C to stop.\n")

    clock = pygame.time.Clock()
    last_buttons = [0] * max(0, num_buttons)
    last_axes = [0.0] * max(0, num_axes)
    last_hats = [(0, 0)] * max(0, num_hats)
    instance_id = joystick.get_instance_id()
    last_activity = time.monotonic()

    try:
        while True:
            # Pump SDL once per tick so joystick state is refreshed even when
            # JOYBUTTON events are not delivered reliably by the driver stack.
            pygame.event.pump()

            # Poll button states directly from the joystick as robust fallback.
            for btn in range(num_buttons):
                current = 1 if joystick.get_button(btn) else 0
                previous = last_buttons[btn]
                if current != previous:
                    if current:
                        print(f"  BUTTON DOWN  button={btn}")
                    else:
                        print(f"  BUTTON UP    button={btn}")
                    last_buttons[btn] = current
                    last_activity = time.monotonic()

            # Poll axis states directly; print only meaningful changes.
            for axis in range(num_axes):
                current = float(joystick.get_axis(axis))
                previous = last_axes[axis]
                if math.fabs(current - previous) >= 0.05:
                    print(f"  AXIS STATE   axis={axis}  value={current:.4f}")
                    last_axes[axis] = current
                    last_activity = time.monotonic()

            # Poll hat states directly.
            for hat in range(num_hats):
                current = joystick.get_hat(hat)
                previous = last_hats[hat]
                if current != previous:
                    print(f"  HAT STATE    hat={hat}  value={current}")
                    last_hats[hat] = current
                    last_activity = time.monotonic()

            for event in pygame.event.get():
                event_joy = getattr(event, "joy", None)
                event_instance = getattr(event, "instance_id", None)
                same_device = (event_instance == instance_id) or (event_joy == instance_id)
                if event.type == pygame.JOYAXISMOTION and same_device:
                    print(f"  AXIS MOTION  axis={event.axis}  value={event.value:.4f}")
                    last_activity = time.monotonic()
                elif event.type == pygame.JOYHATMOTION and same_device:
                    print(f"  HAT MOTION   hat={event.hat}  value={event.value}")
                    last_activity = time.monotonic()

            if time.monotonic() - last_activity >= 5:
                print("  [HINWEIS] Keine Eingabe erkannt. Pruefe, ob das richtige Geraet in config.json gewaehlt ist.")
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

        # State per button
        self._pressed_buttons: set[int] = set()     # buttons currently held down
        self._toggle_indices: dict[int, int] = {}   # current sequence index for toggle mode
        self._press_times: dict[int, float] = {}    # button-down timestamp for short_long_press
        self._held_keys: dict[int, str] = {}        # currently held key for hold mode
        self._hold_deadlines: dict[int, float] = {} # press_hold_release: when on_hold fires

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

        elif mode == "short_long_press":
            self._press_times[button] = time.monotonic()

        elif mode == "press_hold_release":
            send_key(mapping["on_press"])
            threshold_ms = mapping.get("threshold_ms", 500)
            self._hold_deadlines[button] = time.monotonic() + threshold_ms / 1000.0

    def _process_hold_thresholds(self) -> None:
        """Fire on_hold keys for press_hold_release buttons whose threshold elapsed."""
        if not self._hold_deadlines:
            return
        now = time.monotonic()
        for button, deadline in list(self._hold_deadlines.items()):
            if now >= deadline:
                del self._hold_deadlines[button]
                mapping = self.mappings.get(str(button))
                if mapping is not None:
                    send_key(mapping["on_hold"])

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
            down_time = self._press_times.pop(button, None)
            if down_time is None:
                return
            elapsed_ms = (time.monotonic() - down_time) * 1000
            threshold_ms = mapping.get("threshold_ms", 500)
            if elapsed_ms >= threshold_ms:
                send_key(mapping["long_press"])
            else:
                send_key(mapping["short_press"])
            # Optional third key: always sent on release, after short/long.
            if "on_release" in mapping:
                send_key(mapping["on_release"])

        elif mode == "press_hold_release":
            # Cancel a pending on_hold if released before the threshold.
            self._hold_deadlines.pop(button, None)
            send_key(mapping["on_release"])

    def run(self) -> None:
        """Start the event loop. Blocks until Ctrl+C is pressed."""
        name = self.joystick.get_name()
        guid = self.joystick.get_guid()
        print(f"[RUN] Using device: {name}  (GUID: {guid})")
        print("[RUN] Mapper running. Press Ctrl+C to stop.\n")

        instance_id = self.joystick.get_instance_id()
        clock = pygame.time.Clock()
        num_buttons = self.joystick.get_numbuttons()
        last_buttons = [0] * max(0, num_buttons)

        try:
            while True:
                # Keep SDL joystick state current even if event delivery is spotty.
                pygame.event.pump()

                # Primary path: poll physical button states and detect transitions.
                for btn in range(num_buttons):
                    current = 1 if self.joystick.get_button(btn) else 0
                    previous = last_buttons[btn]
                    if current != previous:
                        if current:
                            self._handle_button_down(btn)
                        else:
                            self._handle_button_up(btn)
                        last_buttons[btn] = current

                for event in pygame.event.get():
                    event_joy = getattr(event, "joy", None)
                    event_instance = getattr(event, "instance_id", None)
                    same_device = (event_instance == instance_id) or (event_joy == instance_id)
                    if event.type == pygame.JOYBUTTONDOWN:
                        if same_device:
                            self._handle_button_down(event.button)
                    elif event.type == pygame.JOYBUTTONUP:
                        if same_device:
                            self._handle_button_up(event.button)

                # Fire pending on_hold keys for press_hold_release buttons.
                self._process_hold_thresholds()
                clock.tick(1000 / max(1, self.poll_interval_ms))
        except KeyboardInterrupt:
            # Release any held keys before exiting
            for btn, held_key in list(self._held_keys.items()):
                key_up(held_key)
            self._pressed_buttons.clear()
            print("\n[RUN] Stopped.")


# ---------------------------------------------------------------------------
# Top-level run helper
# ---------------------------------------------------------------------------

def run_mapper(config: dict) -> None:
    """Find the target device and start the GamepadMapper."""
    joystick = find_target_device(config)
    if joystick is None:
        guid = config.get("target_guid", "(none)")
        name = config.get("target_name_contains", "(none)")
        print(f"[ERROR] Target device not found.")
        print(f"        target_guid          : {guid}")
        print(f"        target_name_contains : {name}")
        print("        Run --list to see connected devices.")
        sys.exit(1)
    mapper = GamepadMapper(joystick, config)
    mapper.run()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Map gamepad / button box inputs to keyboard events on Windows."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true",
                       help="List all connected gamepads / joysticks.")
    group.add_argument("--learn", action="store_true",
                       help="Print button events for the configured target device.")
    group.add_argument("--run", action="store_true",
                       help="Run the mapper using config.json.")
    group.add_argument("--init-config", action="store_true",
                       help="Create an example config.json if it does not exist.")

    args = parser.parse_args()

    if args.list:
        list_devices()

    elif args.init_config:
        create_default_config()

    elif args.learn:
        config = load_device_config()
        joystick = find_target_device(config)
        if joystick is None:
            guid = config.get("target_guid", "(none)")
            name = config.get("target_name_contains", "(none)")
            print("[ERROR] Target device not found.")
            print(f"        target_guid          : {guid}")
            print(f"        target_name_contains : {name}")
            print("        Run --list to see connected devices.")
            sys.exit(1)
        run_learn_mode(joystick)

    elif args.run:
        config = load_config()
        run_mapper(config)


if __name__ == "__main__":
    main()
