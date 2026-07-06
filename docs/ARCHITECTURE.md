# ARCHITECTURE

_Last updated: 2026-07-06_

## Layout

```
gamepad_mapper.py     CLI mapper (single file, ~750 lines)
joymapper_gui.py      GUI config editor (single file, customtkinter)
config.json           User config (gitignored intent: user data, do not overwrite)
config.example.json   Full example config (all modes, two devices)
requirements.txt      pygame, keyboard, customtkinter (pinned)
joymapper.spec        PyInstaller spec: both EXEs → one onedir (dist/joymapper/)
start.bat / gui.bat   Bootstrap Python 3.12 venv, then run CLI / GUI
tests/                unittest suite (stubs pygame + keyboard)
.github/workflows/build-windows-exe.yml   CI: test (ubuntu) → build EXEs (windows)
docs/                 AI memory files (this folder)
```

## gamepad_mapper.py (CLI)

Section order in the file:

1. **Key sending helpers** — `set_input_method()`, `_send_scancode()` (ctypes
   `SendInput` with `KEYEVENTF_SCANCODE`/`EXTENDEDKEY`), `send_key()`,
   `key_down()`, `key_up()`. Global `_INPUT_METHOD` selects `keyboard` lib vs
   scancode path.
2. **Configuration helpers** — `DEFAULT_CONFIG`, `create_default_config()`
   (never overwrites), `_load_raw_config()`, `_normalize_config()` (legacy
   single-device → `devices` list), `load_device_config()`, `load_config()`,
   `_validate_mappings()`.
3. **Device handling** — `_init_pygame()` (hidden window; requires
   `SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS=1` set beforehand), `list_devices()`,
   `find_target_device()` (GUID first, name-substring fallback).
4. **Learn mode** — `run_learn_mode(joysticks)` prints button down/up numbers.
5. **`GamepadMapper` class** — per-device state machine implementing the seven
   mapping modes non-blockingly (button-state polling + event fallback,
   debounce, `release_held_keys()` on shutdown).
6. **`run_mapper(config)`** — poll loop over all mappers, Ctrl+C releases held keys.
7. **`main()`** — argparse: mutually exclusive `--list/--learn/--run/--init-config`
   plus `--config FILE` (sets global `CONFIG_FILE`).

## joymapper_gui.py (GUI)

- Independent of `gamepad_mapper.py` by design (starts the CLI exe/script as a
  subprocess instead of importing it).
- `MODE_FIELDS` dict: mode name → list of `(field, label, required)`; drives the
  dynamic mapping editor form. Must stay in sync with CLI validation.
- `_app_dir()` resolves the exe folder when frozen (PyInstaller) vs script dir.
- `_init_pygame()` same hidden-window pattern as CLI; polls joysticks via
  tkinter `after()` every `POLL_MS` (20 ms) to auto-select devices on button press.
- `JoymapperGUI` class holds all UI; sim-racing color constants (`COL_*`) at top.

## Build & CI

- `joymapper.spec`: two `Analysis`/`EXE` blocks (console CLI + windowed GUI)
  collected into one `COLLECT` onedir so the GUI finds the CLI exe next to itself.
  EXE icons use `icon.ico`; GUI bundles `icon.png` + `icon.ico` as data
  (regenerate `icon.ico` from `icon.png` with Pillow when the logo changes).
- CI workflow: test job on ubuntu (no deps needed, tests stub everything),
  then windows build job → artifact + release asset `joymapper-windows.zip`.
