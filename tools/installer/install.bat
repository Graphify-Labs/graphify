@echo off
setlocal

rem -- 1. Detect Python --
set "NEED_PATH=0"
where python >nul 2>nul
if %ERRORLEVEL% == 0 (
    set "PYTHON=python"
    echo [1/4] Using system python
) else (
    set "PYTHON=%~dp0python\python.exe"
    set "NEED_PATH=1"
    if not exist "%PYTHON%" (
        echo ERROR: python not found, check python\ subdirectory
        pause
        exit /b 1
    )
    echo [1/4] Using embedded Python: %PYTHON%
)

rem -- 2. Configure PyPI proxy --
set "PIP_INDEX_URL=<INTERNAL_PYPI_PROXY>"
set "PIP_TRUSTED_HOST=<INTERNAL_TRUSTED_HOST>"
echo [2/4] Using PyPI proxy: %PIP_INDEX_URL%

rem -- 3. Install graphifyy --
echo [3/4] Installing graphifyy (~30-60 sec)...
"%PYTHON%" -m pip install ^
    --index-url "%PIP_INDEX_URL%" ^
    --trusted-host "%PIP_TRUSTED_HOST%" ^
    --timeout <INTERNAL_TIMEOUT> ^
    graphifyy
if errorlevel 1 (
    echo ERROR: pip install graphifyy failed
    pause
    exit /b 1
)

rem -- 4. Deploy SKILL.md --
echo [4/4] Deploying SKILL.md to Claude Code...
"%PYTHON%" -m graphify install claude
if errorlevel 1 (
    echo WARNING: SKILL.md deploy failed, but graphifyy is installed
)

rem -- 5. Register PATH (embedded Python only) --
if "%NEED_PATH%"=="1" (
    echo [5/5] Registering PATH...
    setx PATH "%PATH%;%~dp0python\Scripts" >nul
    if errorlevel 1 (
        echo WARNING: PATH registration failed, add this path to user PATH manually:
        echo   %~dp0python\Scripts
    )
)

echo.
echo [OK] Install complete. Open a new cmd window to use graphify.
pause
endlocal
