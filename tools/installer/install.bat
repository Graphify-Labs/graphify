@echo off
setlocal

rem -- 1. Detect Python --
set "NEED_PATH=0"
where python >nul 2>nul
if %ERRORLEVEL% == 0 (
    set "PYTHON=python"
    echo [1/5] Using system python
) else (
    set "PYTHON=%~dp0python\python.exe"
    set "NEED_PATH=1"
    if not exist "%PYTHON%" (
        echo ERROR: python not found, check python\ subdirectory
        pause
        exit /b 1
    )
    echo [1/5] Using embedded Python: %PYTHON%
)

rem -- 2. Pre-clean: uninstall old skill if graphify is already installed --
"%PYTHON%" -c "import graphify" >nul 2>nul
if %ERRORLEVEL% == 0 (
    echo [2/5] Existing graphify found, cleaning up previous skill...
    "%PYTHON%" -m graphify uninstall claude 2>nul
)

rem -- 3. Configure PyPI proxy --
set "PIP_INDEX_URL=<INTERNAL_PYPI_PROXY>"
set "PIP_TRUSTED_HOST=<INTERNAL_TRUSTED_HOST>"
echo [3/5] Using PyPI proxy: %PIP_INDEX_URL%

rem -- 4. Install graphifyy --
echo [4/5] Installing graphifyy (~30-60 sec)...

rem Resolve the wheel filename with CMD's native wildcard expansion.
rem Passing a glob directly to pip is fragile: pip's internal glob may
rem fail on paths containing parentheses or other special characters.
set "WHEEL_FILE="
for %%f in ("%~dp0wheels\graphifyy-*.whl") do set "WHEEL_FILE=%%f"
if not defined WHEEL_FILE (
    echo ERROR: graphify wheel not found in wheels\ directory
    echo   Expected: wheels\graphifyy-*.whl
    pause
    exit /b 1
)

"%PYTHON%" -m pip install ^
    --upgrade ^
    --index-url "%PIP_INDEX_URL%" ^
    --trusted-host "%PIP_TRUSTED_HOST%" ^
    --timeout <INTERNAL_TIMEOUT> ^
    "%WHEEL_FILE%"
if errorlevel 1 (
    echo ERROR: pip install graphifyy failed
    pause
    exit /b 1
)

rem -- 5. Deploy SKILL.md --
echo [5/5] Deploying SKILL.md to Claude Code...
"%PYTHON%" -m graphify install claude
if errorlevel 1 (
    echo WARNING: SKILL.md deploy failed, but graphifyy is installed
)

rem -- 6. Register PATH (embedded Python only) --
if "%NEED_PATH%"=="1" (
    echo [6/6] Registering PATH...
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
