@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM Ensure script runs from the project root (location of this .bat file)
cd /d "%~dp0"

set "TARGET_PY=3.12"
set "VENV_DIR=.venv"
set "CREATE_VENV=0"

REM Ensure required Python version is installed via py launcher
py -%TARGET_PY% --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python %TARGET_PY% wurde nicht gefunden.
    echo Installiere es z.B. mit:
    echo   winget install -e --id Python.Python.%TARGET_PY%
    exit /b 1
)

REM Check existing venv version
if not exist "%VENV_DIR%\Scripts\python.exe" (
    set "CREATE_VENV=1"
) else (
    for /f "tokens=2 delims= " %%V in ('"%VENV_DIR%\Scripts\python.exe" --version 2^>^&1') do set "VENV_PY=%%V"
    set "VENV_MM=!VENV_PY:~0,4!"
    if /I not "!VENV_MM!"=="%TARGET_PY%" (
        echo [INFO] Vorhandenes venv nutzt Python !VENV_PY!, erwartet %TARGET_PY%.
        rmdir /s /q "%VENV_DIR%"
        if errorlevel 1 (
            echo [ERROR] Konnte bestehendes venv nicht entfernen.
            exit /b 1
        )
        echo [INFO] Altes venv wurde entfernt.
        set "CREATE_VENV=1"
    )
)

if "%CREATE_VENV%"=="1" (
    echo [INFO] Erstelle %VENV_DIR% mit Python %TARGET_PY%...
    py -%TARGET_PY% -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [ERROR] Konnte venv mit Python %TARGET_PY% nicht erstellen.
        exit /b 1
    )
)

call "%VENV_DIR%\Scripts\activate.bat"
if errorlevel 1 (
    echo [ERROR] Aktivierung von %VENV_DIR% fehlgeschlagen.
    exit /b 1
)

REM Ensure dependencies are installed
if exist "requirements.txt" (
    python -m pip install --upgrade pip
    if errorlevel 1 (
        echo [ERROR] Konnte pip nicht aktualisieren.
        exit /b 1
    )

    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Installation der Requirements fehlgeschlagen.
        exit /b 1
    )
) else (
    echo [WARNUNG] requirements.txt nicht gefunden, ueberspringe Installation.
)

REM Start the mapper in run mode
python gamepad_mapper.py --run

endlocal
