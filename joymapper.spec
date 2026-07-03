# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec: builds both joymapper.exe (CLI) and joymapper-gui.exe (GUI)
# into a single shared onedir folder (dist/joymapper/), so the GUI can find
# the CLI exe right next to itself.

cli_a = Analysis(
    ['gamepad_mapper.py'],
)
cli_pyz = PYZ(cli_a.pure)
cli_exe = EXE(
    cli_pyz,
    cli_a.scripts,
    [],
    exclude_binaries=True,
    name='joymapper',
    console=True,
    icon='icon.png',
)

gui_a = Analysis(
    ['joymapper_gui.py'],
    datas=[('icon.png', '.')],  # window icon, loaded relative to __file__
)
gui_pyz = PYZ(gui_a.pure)
gui_exe = EXE(
    gui_pyz,
    gui_a.scripts,
    [],
    exclude_binaries=True,
    name='joymapper-gui',
    console=False,
    icon='icon.png',
)

coll = COLLECT(
    cli_exe,
    cli_a.binaries,
    cli_a.datas,
    gui_exe,
    gui_a.binaries,
    gui_a.datas,
    name='joymapper',
)
