# DECISIONS

Technical decisions and their reasoning. Append new entries at the bottom.

## D-001: Identify devices by GUID with name-substring fallback

Device index changes across reconnects/reboots; GUID is stable.
`target_name_contains` remains as a human-friendly fallback.

## D-002: Button-state polling with event fallback

Some devices/drivers do not emit reliable JOYBUTTON events. The mapper polls
`get_button()` state each tick and uses pygame events only as fallback.

## D-003: Set `SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS=1` before `pygame.init()`

The hidden pygame window never has focus, so SDL drops joystick input by
default. This env var must be set before init — this was the root cause of
"no buttons detected" and must never be removed.

## D-004: Two key-sending paths (`keyboard` lib vs scancode/SendInput)

The `keyboard` library works for normal applications but many games read
DirectInput/RawInput and ignore it. `input_method: "scancode"` sends hardware
scan codes via Win32 `SendInput` (`KEYEVENTF_SCANCODE`), which games accept.
Default stays `"keyboard"` for compatibility.

## D-005: GUI does not import the CLI

`joymapper_gui.py` is a separate tool that launches the mapper as a
subprocess. Keeps the CLI dependency-light and lets either tool ship/run alone.

## D-006: PyInstaller onedir with both EXEs in one folder

Onefile self-extracting binaries trigger far more antivirus/SmartScreen false
positives (the tool simulates keystrokes, matching keylogger heuristics).
Onedir with both EXEs in `dist/joymapper/` also lets the GUI find
`joymapper.exe` next to itself.

## D-007: Pin Python 3.12 and pygame 2.6.1

pygame 2.6.1 has no Windows wheels for Python 3.14+ (source build fails).
3.12 matches CI; `start.bat`/`gui.bat` recreate `.venv` if the version differs.

## D-008: Tests stub pygame and keyboard

`tests/test_gamepad_mapper.py` injects stub modules so the suite runs without
hardware or installed dependencies — enables the ubuntu CI test job.

## D-009: Multi-device config with legacy migration

Config uses a `devices` list (one GUID + mappings each). Older single-device
configs are auto-normalized (`_normalize_config()` / GUI migration) instead of
breaking users. `--config FILE` additionally allows parallel mapper instances.

## D-010: `--init-config` never overwrites

An existing `config.json` is user data; the example template is only written
when no file exists.

## D-011: Pause GUI joystick polling during window move/resize

SDL's event pump (`pygame.event.pump()`/`get()`) processes the message queue
of the whole thread, including messages belonging to the Tk window's native
Win32 move loop. Pumping during a drag steals mouse messages and aborts the
drag (window "lets go" of the mouse). Fix: subclass the Tk window proc via
ctypes, intercept `WM_ENTERSIZEMOVE`/`WM_EXITSIZEMOVE`, and skip pygame calls
in `_poll_joystick()` while `_in_size_move` is set. Button states are
re-snapshotted afterwards to avoid phantom presses.
