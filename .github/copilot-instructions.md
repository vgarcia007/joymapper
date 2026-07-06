# Copilot instructions for joymapper

## Project summary

joymapper is a Windows-only Python tool that maps gamepad / button box inputs
to keyboard events. Two entry points:

- `gamepad_mapper.py` — CLI mapper (`--list`, `--learn`, `--run`, `--init-config`, `--config FILE`)
- `joymapper_gui.py` — customtkinter GUI config editor (separate tool, does not import `gamepad_mapper.py`)

## Environment & commands

- Python 3.12 in `.venv` (created by `start.bat` / `gui.bat`; they recreate the venv if the version is wrong).
- Dependencies: `pygame==2.6.1`, `keyboard==0.13.5`, `customtkinter==6.0.0` (see `requirements.txt`).
- Run tests: `.venv\Scripts\python.exe -m unittest discover -s tests`
  (tests stub out pygame/keyboard — they run without hardware or dependencies).
- Build: `pyinstaller joymapper.spec` (builds both EXEs into one onedir folder `dist/joymapper/`).
- CI: `.github/workflows/build-windows-exe.yml` runs tests then builds on release/dispatch.

## Hard-won constraints (do not break these)

- `SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS=1` must be set in the environment
  **before** `pygame.init()`, otherwise the hidden pygame window gets no joystick input.
- Two key-sending paths exist: `keyboard` library (default) and scan codes via
  `SendInput`/ctypes (`input_method: "scancode"` in config) — needed for
  DirectInput/RawInput games. Keep both working.
- Button detection uses button-state polling with event fallback because some
  devices/drivers do not emit reliable JOYBUTTON events.
- PyInstaller uses onedir (not onefile) to reduce antivirus false positives.

## AI memory system (must maintain)

Read these files at the start of a session when context is needed:

- `docs/AI_CONTEXT.md` — current project understanding
- `docs/ARCHITECTURE.md` — structure and modules
- `docs/DECISIONS.md` — technical decisions and reasoning
- `docs/SESSION_LOG.md` — dated session summaries

After every larger task, update them:

- `docs/AI_CONTEXT.md` when project understanding changed
- `docs/ARCHITECTURE.md` when structure changed
- `docs/DECISIONS.md` when a technical/architectural decision was made
- Append to `docs/SESSION_LOG.md`: date, task, changed files, important context

## Style

- Keep the CLI and GUI decoupled (GUI must not import `gamepad_mapper.py`).
- Match existing code style: type-hinted functions, section-divider comments,
  plain `unittest` tests in `tests/`.
- Never overwrite the user's `config.json` with example data; `--init-config`
  does not overwrite an existing file.
