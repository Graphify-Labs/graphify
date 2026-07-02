#!/bin/bash
# 共享配置：被 install.sh / hook-session-start.sh / cache.sh / delete-helper.sh 等引用
# 微信公众号提取工具的 Git 仓库地址
WECHAT_TOOL_URL="git+https://github.com/jackwener/wechat-article-to-markdown.git"

# Python 命令检测：Windows 默认安装为 python.exe，不存在 python3 命令
# （Microsoft Store 的 python3 是安装提示 stub，运行会失败）
_python_version_check='import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)'

_python_cmd_is_valid() {
  local candidate="$1"

  command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c "$_python_version_check" >/dev/null 2>&1
}

_detect_python_cmd() {
  # 要求 Python 3.8+（见 README Windows 小节与下方错误消息）
  if _python_cmd_is_valid python3; then
    echo "python3"
  elif _python_cmd_is_valid python; then
    echo "python"
  else
    echo ""
  fi
}

require_python_cmd() {
  local detected_cmd

  if [ "${PYTHON_CMD_READY:-0}" = "1" ]; then
    return 0
  fi

  if [ -n "${PYTHON_CMD:-}" ] && _python_cmd_is_valid "$PYTHON_CMD"; then
    export PYTHON_CMD
    PYTHON_CMD_READY=1
    return 0
  fi

  detected_cmd="$(_detect_python_cmd)"
  if [ -z "$detected_cmd" ]; then
    echo "[llm-wiki] 错误：找不到可用的 Python 3，请先安装 Python 3.8+ 并加入 PATH" >&2
    return 1
  fi

  PYTHON_CMD="$detected_cmd"
  export PYTHON_CMD
  PYTHON_CMD_READY=1
}

# 统一 Python 子进程 stdout/stderr 编码为 UTF-8
# Windows 中文环境下 Python 无 TTY 时 sys.stdout.encoding 默认 gbk (cp936)，
# 会导致 Agent 通过 subprocess 读取的 JSON / 输出出现乱码 (issue #16)
export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"

# 输出指定工具的跨平台安装提示，缩进 2 空格便于嵌套在 ERROR 消息下；
# 输出走 stderr，与 ERROR 消息保持同一通道。
print_install_hint() {
  local tool="$1"
  case "$tool" in
    jq)
      echo "  macOS:        brew install jq" >&2
      echo "  Linux/WSL:    sudo apt-get install jq   (Debian/Ubuntu)" >&2
      echo "                sudo dnf install jq       (RHEL/Fedora)" >&2
      echo "  Windows:      winget install jqlang.jq  (or choco install jq)" >&2
      ;;
    node)
      echo "  macOS:        brew install node" >&2
      echo "  Linux/WSL:    sudo apt-get install nodejs npm" >&2
      echo "  Windows:      winget install OpenJS.NodeJS  (or choco install nodejs)" >&2
      ;;
    uv)
      echo "  macOS/Linux:  curl -LsSf https://astral.sh/uv/install.sh | sh    (official)" >&2
      echo "                brew install uv                                    (alternative)" >&2
      echo "  Windows:      powershell -c \"irm https://astral.sh/uv/install.ps1 | iex\"   (official)" >&2
      echo "                winget install --id=astral-sh.uv -e                (alternative)" >&2
      ;;
    *)
      echo "  unknown tool: $tool" >&2
      return 1
      ;;
  esac
}
