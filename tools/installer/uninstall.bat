@echo off
setlocal

set "PYTHON=%~dp0python\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"

echo [1/3] Uninstalling SKILL.md...
"%PYTHON%" -m graphify uninstall claude

echo [2/3] Uninstalling graphifyy...
"%PYTHON%" -m pip uninstall -y graphifyy

echo [3/3] Removing install directory...
cd /d "%~dp0\.."
rmdir /s /q "%~dp0." 2>nul
echo.
echo [OK] Uninstall complete.
pause
endlocal
