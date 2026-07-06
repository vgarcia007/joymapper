# AI_CONTEXT — current project understanding

_Last updated: 2026-07-06_

## Purpose

joymapper reads inputs from gamepads / button boxes (identified by GUID, with
name-substring fallback) and sends keyboard events to Windows or the active
application. Target audience includes sim-racing / button-box users.

## Core facts

- Platform: Windows 10/11 only (uses `keyboard` lib and Win32 `SendInput`).
- Python 3.10–3.13 supported; 3.12 is the project standard (CI + `start.bat`).
- Config: `config.json` next to the script/exe. Top-level keys:
  `poll_interval_ms`, `input_method` (`"keyboard"` | `"scancode"`),
  `devices` (list of `{target_guid, target_name_contains, mappings}`).
  Legacy single-device configs are auto-migrated by the GUI.
- Seven mapping modes: `press_release`, `toggle`, `press`, `hold`,
  `short_long_press`, `short_long_press_hold`, `press_hold_release`.
- CLI modes: `--list`, `--learn`, `--run`, `--init-config`, plus `--config FILE`
  (enables one config per device / parallel mapper instances).
- GUI (`joymapper_gui.py`): config editor that can start/stop the mapper;
  auto-selects a device when any button is pressed; sim-racing dark/red theme.

## Known pitfalls (verified during development)

- Hidden pygame window receives no joystick input unless
  `SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS=1` is set before `pygame.init()`.
- `keyboard` lib events reach normal apps but not DirectInput/RawInput games;
  `input_method: "scancode"` (SendInput with `KEYEVENTF_SCANCODE`) fixes that.
  Run as admin if the game is elevated.
- Some devices/drivers do not emit reliable JOYBUTTON events → mapper polls
  button state and uses events as fallback.
- SDL's event pump in the GUI's Tk thread aborts native window dragging
  (steals the move loop's mouse messages) → GUI pauses polling during
  `WM_ENTERSIZEMOVE`/`WM_EXITSIZEMOVE` (see D-011).
- `keyboard` lib may require administrator rights on some Windows setups.
- pygame 2.6.1 fails to install on Python 3.14+ on Windows.

## Distribution

- Prebuilt EXEs (`joymapper.exe` CLI + `joymapper-gui.exe`) built by
  `pyinstaller joymapper.spec` into a shared onedir folder; released as
  `joymapper-windows.zip` via GitHub Actions on release creation.
- Executables are unsigned → SmartScreen/antivirus false positives are expected
  and documented in the README.

## Testing

- `tests/test_gamepad_mapper.py`: unittest suite (~39 tests) covering all
  mapping modes, non-blocking behaviour, config loading, pygame init, and
  debounce. Stubs pygame/keyboard, so it runs anywhere without hardware.
