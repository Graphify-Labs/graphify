# 已废弃：请使用 bash install.sh --platform claude
#!/bin/bash
# Claude 旧入口兼容包装
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

exec bash "$SCRIPT_DIR/install.sh" --platform claude "$@"
