@echo off
setlocal

rem -- Detect Python (same logic as install.bat: prefer system, fall back to embedded) --
where python >nul 2>nul
if %ERRORLEVEL% == 0 (
    set "PYTHON=python"
    echo Using system python
) else (
    set "PYTHON=%~dp0python\python.exe"
    if not exist "%PYTHON%" (
        echo ERROR: python not found, check python\ subdirectory
        pause
        exit /b 1
    )
    echo Using embedded Python: %PYTHON%
)

echo.
echo [1/2] Uninstalling SKILL.md and bundled skills (all platforms)...
"%PYTHON%" -m graphify uninstall
if errorlevel 1 (
    echo WARNING: graphify uninstall had errors (may already be uninstalled)
    pause
)

echo.
echo [2/2] Uninstalling graphifyy package...
"%PYTHON%" -m pip uninstall -y graphifyy
if errorlevel 1 (
    echo WARNING: pip uninstall graphifyy failed (may already be uninstalled)
    pause
)

echo.
echo [OK] Uninstall complete. Installer files kept for future use.
pause
endlocal
