# SESSION_LOG

Short dated summaries of development sessions. Append new entries at the bottom.
Format: date — task — changed files — key context.

## 2026-07-06 — Create AI memory system

- **Task:** Analyzed the repository and set up persistent AI memory files for
  future Copilot sessions.
- **Changed files:** `.github/copilot-instructions.md`, `AGENTS.md`,
  `docs/AI_CONTEXT.md`, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`,
  `docs/SESSION_LOG.md` (all new).
- **Context:** Content documented strictly from verified sources: README,
  source files, `config.example.json`, `joymapper.spec`, batch scripts, test
  suite, and CI workflow. Decisions D-001…D-010 back-filled from code comments
  and known development history (SDL background events fix, scancode input
  method, onedir build rationale). No application features were changed.

## 2026-07-06 — Fix: window drag aborts in GUI

- **Task:** GUI window dragging stopped intermittently ("as if a refresh
  happened"). Root cause: `pygame.event.pump()/get()` in the 20 ms
  `_poll_joystick()` tick pumps the whole thread's Win32 message queue and
  steals mouse messages from the native modal move loop of the Tk window.
- **Changed files:** `joymapper_gui.py` (new `_install_move_hook()` subclasses
  the window proc via ctypes; `_poll_joystick()` skips pygame calls while
  `_in_size_move` is true; button states re-snapshotted on `WM_EXITSIZEMOVE`),
  `docs/DECISIONS.md` (D-011), `docs/AI_CONTEXT.md`.
- **Context:** 44 tests pass. Actual drag behaviour needs manual verification
  on real hardware/desktop (cannot be tested in CI).

## 2026-07-06 — GUI window made resizable

- **Task:** Window could not be resized (`root.resizable(False, False)` was
  set deliberately). Removed the lock, added grid weights (columns 0/1 and the
  cards row grow; MAPPINGS listbox stretches) and set `minsize` to the initial
  layout size so the window cannot shrink below its content.
- **Changed files:** `joymapper_gui.py`.
- **Context:** Resize behaviour needs a quick manual check (drag edges, verify
  listbox grows and nothing overlaps). Follow-up: only the MAPPINGS card is
  responsive now (column 0 has weight); EDIT MAPPING keeps its fixed size
  (column 1 weight 0, card sticky "new").

## 2026-07-06 — New GUI color scheme (design tokens)

- **Task:** Applied user-provided design tokens to the GUI colors:
  primary `#B00202` → `COL_RED`, accent-1 `#D66A6B` → new `COL_RED_HOVER`,
  accent-2 `#6A1214` → new `COL_DARKRED` (dropdown hover), background
  `#212529` → `COL_BG`, text `#FFFFFF` → `COL_WHITE`, neutral `#000000` →
  `COL_FIELD`. Derived (not in tokens): `COL_CARBON #2B3035` (card shade),
  `COL_BTN #343A40` (button bg); `COL_LIGHT`/`COL_DISABLED` unchanged.
- **Changed files:** `joymapper_gui.py` (color constants, `make_button`,
  `make_combo`).
- **Context:** Appearance needs manual verification.

## 2026-07-06 — Fix: taskbar icon not shown

- **Task:** New icon.png (1254×1254) did not appear in the Windows taskbar.
  Cause: `iconphoto` with one huge PNG — Windows wants a multi-size .ico for
  the taskbar. Generated `icon.ico` (16–256 px, via Pillow, one-off) and the
  GUI now prefers `root.iconbitmap(default=icon.ico)` with the PNG/iconphoto
  path as fallback. CTk overrides the icon ~200 ms after startup, so ours is
  re-applied at 300 ms (as before).
- **Changed files:** `joymapper_gui.py`, `joymapper.spec` (EXE icons now
  `icon.ico`; `icon.ico` added to GUI datas), new file `icon.ico`.
- **Context:** Pillow was installed into the local venv only for the one-off
  conversion (not a runtime dependency, not in requirements.txt). If the icon
  still looks stale in the taskbar, it's the Windows icon cache (restart
  Explorer). Regenerate icon.ico after changing icon.png:
  `python -c "from PIL import Image; Image.open('icon.png').convert('RGBA').save('icon.ico', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])"`

## 2026-07-06 — GUI footer with logo and links

- **Task:** Added a footer to the GUI: logo (left) plus clickable links to
  garcias-garage.de and the GitHub repo (right), opened via `webbrowser`.
- **Changed files:** `joymapper_gui.py` (footer row 5, `WEBSITE_URL`/
  `GITHUB_URL` constants), `joymapper.spec` (bundle `logo_small.png`),
  new file `logo_small.png` (36 px high, generated from `logo.png` 1106×354
  via Pillow — regenerate when logo.png changes:
  `python -c "from PIL import Image; i=Image.open('logo.png').convert('RGBA'); h=36; i.resize((round(i.width*h/i.height), h), Image.LANCZOS).save('logo_small.png')"`).
- **Context:** Original logo.png stays at full resolution and is not bundled.
  Follow-up: footer restyled — black background (`COL_FIELD` #000000,
  full-width, no corner radius), links in primary color (`COL_RED`).
  Status bar text centered.

## 2026-07-06 — Mappings list as table

- **Task:** Replaced the raw-JSON `tk.Listbox` in the MAPPINGS card with a
  `ttk.Treeview` table (columns: Button | Mode | Keys). Keys column is a
  compact summary built from `MODE_FIELDS` order (threshold shown as
  "(600 ms)" suffix). Rows use the button number as iid, so selection/removal
  no longer parse display strings.
- **Changed files:** `joymapper_gui.py` (`_build_widgets` incl. dark
  "Mappings.Treeview" ttk style on clam theme, `_select_mapping_in_list`,
  `_remove_mapping`, new `_mapping_keys_text`, `_refresh_mapping_list`,
  `_on_mapping_selected`, `_set_ui_enabled` locks the tree via
  `selectmode="none"`).
- **Context:** ttk widgets need `theme_use("clam")` for background colors to
  apply on Windows. Needs manual UI check.

## 2026-07-06 — README restructured (GUI-first)

- **Task:** README now leads with the GUI: intro rewritten (GUI does the work,
  CLI for purists), download paragraph + release link in the intro, GUI
  screenshot in the download section, new "Quick start (GUI)" section
  (5 steps + multi-device/config hints), features list starts with the GUI.
  Requirements/installation-from-source moved into "Using the command line",
  which wraps the old CLI quick start (steps 1–6, mode docs unchanged).
- **Changed files:** `README.md`.
- **Context:** Anchor links used: #5-configure-mappings, #windows-caveats,
  #download-prebuilt-windows-binaries — keep them stable when renaming
  headings.
