@echo off
setlocal

rem ── 1. 探测 Python ──
set "NEED_PATH=0"
where python >nul 2>nul
if %ERRORLEVEL% == 0 (
    set "PYTHON=python"
    echo [1/4] 使用系统已有的 python
) else (
    set "PYTHON=%~dp0python\python.exe"
    set "NEED_PATH=1"
    if not exist "%PYTHON%" (
        echo 错误: 未找到 python，请确认 python\ 子目录完整
        exit /b 1
    )
    echo [1/4] 使用内嵌 Python: %PYTHON%
)

rem ── 2. 配置内网 PyPI 代理 ──
set "PIP_INDEX_URL=<INTERNAL_PYPI_PROXY>"
set "PIP_TRUSTED_HOST=<INTERNAL_TRUSTED_HOST>"
echo [2/4] 使用内网 PyPI 代理: %PIP_INDEX_URL%

rem ── 3. 安装 graphifyy ──
echo [3/4] 安装 graphifyy（约 30-60 秒）...
"%PYTHON%" -m pip install ^
    --index-url "%PIP_INDEX_URL%" ^
    --trusted-host "%PIP_TRUSTED_HOST%" ^
    --timeout <INTERNAL_TIMEOUT> ^
    graphifyy
if errorlevel 1 (
    echo 错误: pip install graphifyy 失败
    exit /b 1
)

rem ── 4. 部署 SKILL.md ──
echo [4/4] 部署 SKILL.md 到 Claude Code...
"%PYTHON%" -m graphify install claude
if errorlevel 1 (
    echo 警告: SKILL.md 部署失败，但 graphifyy 已安装
)

rem ── 5. 注册 PATH（仅内嵌 Python 场景） ──
if "%NEED_PATH%"=="1" (
    echo [5/5] 注册 PATH...
    setx PATH "%PATH%;%~dp0python\Scripts" >nul
    if errorlevel 1 (
        echo 警告: PATH 注册失败，请手动将以下路径添加到用户 PATH:
        echo   %~dp0python\Scripts
    )
)

echo.
echo ✓ 安装完成。新开一个 cmd 窗口即可使用 graphify 命令。
endlocal
