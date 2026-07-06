# AGENTS.md — agent mode guide for joymapper

## What this repo is

Windows-only Python tool mapping gamepad/button-box input to keyboard events.
Two independent entry points: `gamepad_mapper.py` (CLI) and `joymapper_gui.py`
(customtkinter GUI). Config lives in `config.json` (multi-device `devices` list).

## Before you start

1. Read `docs/AI_CONTEXT.md` for the current project understanding.
2. Read `docs/ARCHITECTURE.md` before changing structure or modules.
3. Check `docs/DECISIONS.md` before reversing an existing technical choice.

## Working rules

- Environment: Python 3.12 venv at `.venv` (bootstrapped by `start.bat`/`gui.bat`).
- Tests: `.venv\Scripts\python.exe -m unittest discover -s tests`
  — run them after any change to `gamepad_mapper.py`. Tests stub pygame/keyboard,
  so no hardware is needed.
- Do not make the GUI import `gamepad_mapper.py`; they are deliberately decoupled
  (the GUI launches the CLI as a subprocess / neighbouring exe).
- Set `SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS=1` before `pygame.init()` — removing
  this silently breaks joystick input for hidden windows.
- Preserve both input methods (`keyboard` lib and scancode/SendInput) and all
  seven mapping modes; the GUI's `MODE_FIELDS` must stay in sync with the CLI's
  mapping validation.
- Build with `pyinstaller joymapper.spec` (onedir; both EXEs share one folder).
- Hardware-dependent behaviour (`--list`, `--learn`, `--run`) cannot be verified
  in CI/agent runs — say so instead of claiming it works.

## After every larger task (mandatory)

Update the memory files:

- `docs/AI_CONTEXT.md` — if project understanding changed
- `docs/ARCHITECTURE.md` — if structure/modules changed
- `docs/DECISIONS.md` — if a technical decision was made (with reasoning)
- `docs/SESSION_LOG.md` — always append: date, task, changed files, key context

Also keep this file and `.github/copilot-instructions.md` accurate when
workflows or rules change.
