@echo off
setlocal

set "PYTHON=%~dp0python\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"

echo [1/3] 卸载 SKILL.md...
"%PYTHON%" -m graphify uninstall claude

echo [2/3] 卸载 graphifyy...
"%PYTHON%" -m pip uninstall -y graphifyy

echo [3/3] 删除安装目录...
cd /d "%~dp0\.."
rmdir /s /q "%~dp0." 2>nul
echo.
echo ✓ 卸载完成。
endlocal