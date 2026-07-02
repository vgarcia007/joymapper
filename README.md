# joymapper

A small Windows command-line tool written in Python that reads inputs from a
specific gamepad or button box and sends keyboard events to Windows or the
currently active application.

---

## Features

- Identifies the target device by **GUID** (reliable across reconnections and
  reorders) with an optional name-substring fallback.
- Five button mapping **modes**:
  | Mode | Behaviour |
  |---|---|
  | `press_release` | Send one key on button-down and another on button-up |
  | `toggle` | Cycle through a sequence of keys on each press |
  | `press` | Send a key on each button-down |
  | `hold` | Hold a key while the button is held |
  | `short_long_press` | Send different keys for short vs. long press |
- Configurable poll interval and long-press threshold.
- Graceful Ctrl+C shutdown (releases any held keys).

---

## Requirements

- Windows 10 / 11
- Python 3.10-3.13 (recommended for `pygame==2.6.1` on Windows)
- A connected gamepad, button box, or joystick

> On Python 3.14+, `pygame==2.6.1` may try to build from source and fail on
> Windows. Use Python 3.10-3.13 for this project.

---

## Installation

```bash
# 1. Clone or download the repository
git clone https://github.com/vgarcia007/joymapper.git
cd joymapper

# 2. (Recommended) Create a virtual environment
python -m venv .venv
.venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
```

> **Note:** The `keyboard` library sends low-level keyboard events and may
> require **administrator rights** on some Windows configurations.  
> Run your terminal as Administrator if keys are not being received.

---

## Quick start

### 1. List connected devices

```bash
python gamepad_mapper.py --list
```

Sample output:

```
Found 2 device(s):

  Index  : 0
  Name   : USB Gamepad
  GUID   : 03000000c0160000dc27000000010000
  Buttons: 12
  Axes   : 4
  Hats   : 1

  Index  : 1
  Name   : Button Box Pro
  GUID   : 030000005e040000dd02000000010000
  Buttons: 32
  Axes   : 0
  Hats   : 0
```

Copy the **GUID** of your target device and paste it into `config.json`.

### 2. Create a default configuration

```bash
python gamepad_mapper.py --init-config
```

This creates `config.json` in the current directory (does **not** overwrite an
existing file).  See `config.example.json` for the full example.

### 3. Edit config.json

Open `config.json` and set the correct `target_guid` (and optionally
`target_name_contains` as a fallback):

```json
{
  "target_guid": "03000000c0160000dc27000000010000",
  "target_name_contains": "Button Box",
  "poll_interval_ms": 5,
  "mappings": { "...": "..." }
}
```

### 4. Learn button numbers

```bash
python gamepad_mapper.py --learn
```

Press each physical button on your device.  The tool prints the button number
for every button-down and button-up event so you can map physical buttons to
the correct numbers in `config.json`.

### 5. Configure mappings

Button numbers are the **string keys** inside `"mappings"`.  Each entry needs
a `"mode"` and mode-specific fields:

#### `press_release` – different key on down and up

```json
"0": {
  "mode": "press_release",
  "on_press": "a",
  "on_release": "b"
}
```

#### `toggle` – cycle through a sequence of keys

```json
"1": {
  "mode": "toggle",
  "sequence": ["a", "b"]
}
```

#### `press` – send a key on each button-down

```json
"2": {
  "mode": "press",
  "key": "enter"
}
```

#### `hold` – hold a key while the button is held

```json
"3": {
  "mode": "hold",
  "key": "shift"
}
```

#### `short_long_press` – short press vs. long press

```json
"4": {
  "mode": "short_long_press",
  "short_press": "f",
  "long_press": "g",
  "threshold_ms": 600
}
```

Key names follow the [`keyboard` library conventions][kb-keys] (e.g. `"a"`,
`"enter"`, `"shift"`, `"ctrl"`, `"f1"`, `"space"`, `"left arrow"`, etc.).

[kb-keys]: https://github.com/boppreh/keyboard#api

### 6. Run the mapper

```bash
python gamepad_mapper.py --run
```

The tool prints the device name and GUID it found, then starts forwarding
button events as keyboard input.  Press **Ctrl+C** to stop.

---

## CLI reference

| Command | Description |
|---|---|
| `python gamepad_mapper.py --list` | List all connected gamepads/joysticks |
| `python gamepad_mapper.py --init-config` | Create a default `config.json` |
| `python gamepad_mapper.py --learn` | Print button events for the target device |
| `python gamepad_mapper.py --run` | Run the mapper |

---

## Configuration reference

| Field | Type | Description |
|---|---|---|
| `target_guid` | string | GUID of the target device (from `--list`) |
| `target_name_contains` | string | Fallback: match any device whose name contains this substring |
| `poll_interval_ms` | integer | Event-loop tick in milliseconds (default `5`) |
| `mappings` | object | Map of button number (string) → mapping object |

---

## Windows caveats

- **Administrator rights**: The `keyboard` library injects events at the
  driver level.  If simulated keystrokes are not received by the target
  application, try running the terminal (or your IDE) **as Administrator**.

- **Games with anti-cheat**: Many competitive games (and some simulators) use
  anti-cheat or input-protection drivers that block or ignore simulated
  keyboard events.  In those cases you may need a hardware-level HID emulator
  (e.g. vJoy + x360ce) or a different injection method (e.g. `SendInput` via
  `pywin32`).

- **UAC / elevated processes**: Windows does not allow a normal-privilege
  process to send input to an elevated (Administrator) window.  If the target
  window is elevated, joymapper must also run elevated.

- **pygame display requirement**: pygame's joystick subsystem works without a
  visible window, but it does require that `pygame.init()` has been called.
  The tool handles this internally.
