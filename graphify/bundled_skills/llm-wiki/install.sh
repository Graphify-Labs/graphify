#!/bin/bash
# llm-wiki unified installer
set -euo pipefail

SKILL_NAME="llm-wiki"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOURCE_REGISTRY_SCRIPT="$SCRIPT_DIR/scripts/source-registry.sh"
ADAPTER_STATE_SCRIPT="$SCRIPT_DIR/scripts/adapter-state.sh"
PLATFORM="auto"
PLATFORM_EXPLICIT=0
DRY_RUN=0
TARGET_DIR=""
INSTALL_HOOKS=0
UNINSTALL_HOOKS=0
UPGRADE=0
WITH_OPTIONAL_ADAPTERS=0

# 这些项目都在运行时会被读取或链接：
# - 入口与说明文件：README / CLAUDE / AGENTS / CHANGELOG
# - 安装入口：install.sh / setup.sh
# - 实际执行内容：SKILL.md / scripts / templates / deps
# - 平台薄入口：platforms（README、CLAUDE、AGENTS 都会引用）
MANAGED_ITEMS=(
  "SKILL.md"
  "README.md"
  "CLAUDE.md"
  "AGENTS.md"
  "HERMES.md"
  "CHANGELOG.md"
  "install.sh"
  "setup.sh"
  "install.ps1"
  "scripts"
  "templates"
  "deps"
  "platforms"
)

DEP_SKILLS=()

list_companion_skill_sources() {
  case "$1" in
    claude)
      printf '%s\n' "platforms/claude/companions/llm-wiki-upgrade"
      ;;
  esac
}

# 微信工具 URL 从共享配置读取，与 adapter-state.sh 保持一致
source "$SCRIPT_DIR/scripts/shared-config.sh"
source "$SCRIPT_DIR/scripts/runtime-context.sh"

info()  { printf '\033[36m[信息]\033[0m %s\n' "$1"; }
ok()    { printf '\033[32m[完成]\033[0m %s\n' "$1"; }
warn()  { printf '\033[33m[警告]\033[0m %s\n' "$1"; }
err()   { printf '\033[31m[错误]\033[0m %s\n' "$1" >&2; }

usage() {
  cat <<'EOF'
用法：
  bash install.sh --platform <claude|codex|openclaw|hermes|auto> [--dry-run]
  bash install.sh --platform claude --install-hooks
  bash install.sh --install-hooks
  bash install.sh --uninstall-hooks
  bash install.sh --upgrade [--platform <claude|codex|openclaw|hermes|auto>]
  bash install.sh --platform codex --with-optional-adapters

选项：
  --platform         目标平台。默认 auto；只有检测到唯一平台时才会自动安装。
  --dry-run          只打印安装计划，不写入文件。
  --target-dir       指定技能目标目录（直接传最终的 llm-wiki 目录）。
  --with-optional-adapters  显式启用网页 / X / YouTube / 公众号等可选提取器安装。
  --install-hooks    注册 Claude Code 的 SessionStart hook。
  --uninstall-hooks  移除 Claude Code 的 SessionStart hook。
  --upgrade          拉取最新代码并更新已安装的 llm-wiki（保留 hook 配置）。
  -h, --help         显示帮助。
EOF
}

hook_command_for_skill_dir() {
  printf 'bash %s/scripts/hook-session-start.sh\n' "$1"
}

require_jq() {
  if ! command -v jq >/dev/null 2>&1; then
    err "注册或移除 hook 需要 jq"
    exit 1
  fi
}

register_claude_session_hook() {
  local skill_dir="$1"
  local settings_dir settings_path backup_path hook_command tmp_file

  [ -d "$skill_dir" ] || {
    err "未找到已安装的 llm-wiki：$skill_dir"
    exit 1
  }

  require_jq

  settings_dir="$HOME/.claude"
  settings_path="$settings_dir/settings.json"
  backup_path="$settings_dir/settings.json.bak.llm-wiki"
  hook_command="$(hook_command_for_skill_dir "$skill_dir")"

  if [ "$DRY_RUN" -eq 1 ]; then
    printf '[dry-run] register SessionStart hook: %s\n' "$hook_command"
    return 0
  fi

  mkdir -p "$settings_dir"
  [ -f "$settings_path" ] || printf '{}\n' > "$settings_path"
  cp "$settings_path" "$backup_path"

  if jq -e --arg cmd "$hook_command" '[ (.hooks.SessionStart // [])[]? | (.hooks // [])[]? | .command ] | index($cmd) != null' "$settings_path" > /dev/null; then
    ok "Claude Code SessionStart hook 已存在，跳过"
    return 0
  fi

  tmp_file="$(mktemp)"
  jq --arg cmd "$hook_command" '
    .hooks = (.hooks // {}) |
    .hooks.SessionStart = ((.hooks.SessionStart // []) + [{"hooks":[{"type":"command","command":$cmd}]}])
  ' "$settings_path" > "$tmp_file"
  mv "$tmp_file" "$settings_path"

  ok "Claude Code SessionStart hook 已注册"
}

uninstall_claude_session_hook() {
  local skill_dir="$1"
  local settings_dir settings_path backup_path hook_command tmp_file

  require_jq

  settings_dir="$HOME/.claude"
  settings_path="$settings_dir/settings.json"
  backup_path="$settings_dir/settings.json.bak.llm-wiki"
  hook_command="$(hook_command_for_skill_dir "$skill_dir")"

  if [ ! -f "$settings_path" ]; then
    if [ "$DRY_RUN" -eq 1 ]; then
      printf '[dry-run] uninstall SessionStart hook: %s\n' "$hook_command"
      return 0
    fi
    ok "未找到 Claude Code settings.json，跳过 hook 移除"
    return 0
  fi

  if [ "$DRY_RUN" -eq 1 ]; then
    printf '[dry-run] uninstall SessionStart hook: %s\n' "$hook_command"
    return 0
  fi

  cp "$settings_path" "$backup_path"

  tmp_file="$(mktemp)"
  jq --arg cmd "$hook_command" '
    .hooks = (.hooks // {}) |
    .hooks.SessionStart = (
      (.hooks.SessionStart // [])
      | map(.hooks = ((.hooks // []) | map(select(.command != $cmd))))
      | map(select((.hooks // []) | length > 0))
    ) |
    if ((.hooks.SessionStart // []) | length) == 0 then del(.hooks.SessionStart) else . end |
    if (.hooks | length) == 0 then del(.hooks) else . end
  ' "$settings_path" > "$tmp_file"
  mv "$tmp_file" "$settings_path"

  ok "Claude Code SessionStart hook 已移除"
}

load_dependency_skills() {
  local dep

  DEP_SKILLS=()

  while IFS= read -r dep; do
    [ -n "$dep" ] && DEP_SKILLS+=("$dep")
  done < <(bash "$SOURCE_REGISTRY_SCRIPT" unique-dependencies bundled)
}

join_source_labels() {
  local category="$1"

  bash "$SOURCE_REGISTRY_SCRIPT" list-by-category "$category" \
    | awk -F '\t' '
      BEGIN { separator = "" }
      NF {
        printf "%s%s", separator, $2
        separator = "、"
      }
      END {
        if (separator == "") {
          printf "-"
        }
        printf "\n"
      }
    '
}

run_cmd() {
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '[dry-run] %s\n' "$*"
    return 0
  fi
  "$@"
}

copy_item() {
  local source_path="$1"
  local target_path="$2"

  if [ "$DRY_RUN" -eq 1 ]; then
    printf '[dry-run] copy %s -> %s\n' "$source_path" "$target_path"
    return 0
  fi

  rm -rf "$target_path"
  cp -R "$source_path" "$target_path"
}

detect_available_platforms() {
  local found=()

  if [ -d "$HOME/.claude" ] || [ -d "$HOME/.claude/skills" ]; then
    found+=("claude")
  fi

  if [ -d "$HOME/.codex" ] || [ -d "$HOME/.codex/skills" ] || [ -d "$HOME/.Codex" ] || [ -d "$HOME/.Codex/skills" ]; then
    found+=("codex")
  fi

  if [ -d "$HOME/.openclaw" ] || [ -d "$HOME/.openclaw/skills" ]; then
    found+=("openclaw")
  fi

  if [ -d "$HOME/.hermes" ] || [ -d "$HOME/.hermes/skills" ]; then
    found+=("hermes")
  fi

  printf '%s\n' "${found[@]}"
}

install_dependency_skills() {
  local skill_root="$1"
  local dep dep_target dep_source

  for dep in "${DEP_SKILLS[@]}"; do
    dep_source="$SCRIPT_DIR/deps/$dep"
    dep_target="$skill_root/$dep"

    if [ ! -d "$dep_source" ]; then
      warn "$dep：deps/ 中未找到源文件，跳过"
      continue
    fi

    copy_item "$dep_source" "$dep_target"
    ok "$dep 已准备到 $dep_target"
  done
}

install_companion_skills() {
  local platform="$1"
  local skill_root="$2"
  local skill_rel skill_source skill_target skill_name

  while IFS= read -r skill_rel; do
    [ -n "$skill_rel" ] || continue

    skill_source="$SCRIPT_DIR/$skill_rel"
    skill_name="$(basename "$skill_rel")"
    skill_target="$skill_root/$skill_name"

    if [ ! -d "$skill_source" ]; then
      warn "$skill_name：仓库中未找到源文件，跳过"
      continue
    fi

    copy_item "$skill_source" "$skill_target"
    ok "$skill_name 已安装到 $skill_target"
  done < <(list_companion_skill_sources "$platform")
}

install_bundle() {
  local target_dir="$1"
  local item source_path target_path

  for item in "${MANAGED_ITEMS[@]}"; do
    source_path="$SCRIPT_DIR/$item"
    target_path="$target_dir/$item"

    if [ ! -e "$source_path" ]; then
      warn "$item：安装源文件缺失，跳过"
      continue
    fi

    if [ "$source_path" = "$target_path" ] && [ -e "$target_path" ]; then
      continue
    fi

    copy_item "$source_path" "$target_path"
  done

  # 安装后校验：确保清单文件都已就位（Windows install.ps1 尤其重要）
  if [ "$DRY_RUN" -ne 1 ]; then
    for item in "${MANAGED_ITEMS[@]}"; do
      source_path="$SCRIPT_DIR/$item"
      target_path="$target_dir/$item"
      if [ -e "$source_path" ] && [ ! -e "$target_path" ]; then
        err "$item：已列入安装清单但未出现在目标目录，拷贝可能失败"
        exit 1
      fi
    done
    ok "已校验全部 ${#MANAGED_ITEMS[@]} 项安装清单文件"
  fi
}

install_node_deps() {
  local skill_root="$1"
  local baoyu_dir="$skill_root/baoyu-url-to-markdown/scripts"

  if [ ! -d "$baoyu_dir" ] || [ ! -f "$baoyu_dir/package.json" ]; then
    return 0
  fi

  if [ -d "$baoyu_dir/node_modules" ]; then
    ok "baoyu-url-to-markdown 的 Node 依赖已存在"
    return 0
  fi

  info "安装 baoyu-url-to-markdown 的 Node 依赖..."

  if [ "$DRY_RUN" -eq 1 ]; then
    if command -v bun >/dev/null 2>&1; then
      printf '[dry-run] (cd %s && bun install)\n' "$baoyu_dir"
    elif command -v npm >/dev/null 2>&1; then
      printf '[dry-run] (cd %s && npm install)\n' "$baoyu_dir"
    else
      printf '[dry-run] 未找到 bun 或 npm，无法安装 Node 依赖\n'
    fi
    return 0
  fi

  if command -v bun >/dev/null 2>&1; then
    (cd "$baoyu_dir" && bun install) || warn "bun install 失败，跳过（可手动粘贴文本作为替代）"
  elif command -v npm >/dev/null 2>&1; then
    (cd "$baoyu_dir" && npm install) || warn "npm install 失败，跳过（可手动粘贴文本作为替代）"
  else
    warn "未找到 bun 或 npm，无法安装 Node 依赖"
    echo "  推荐安装 bun：curl -fsSL https://bun.sh/install | bash"
    return 0
  fi

  [ -d "$baoyu_dir/node_modules" ] && ok "baoyu-url-to-markdown 的 Node 依赖安装完成"
}

install_uv_tools() {
  if ! command -v uv >/dev/null 2>&1; then
    warn "未找到 uv，跳过 wechat-article-to-markdown 安装"
    echo "  安装 uv：curl -LsSf https://astral.sh/uv/install.sh | sh"
    return 0
  fi

  if command -v wechat-article-to-markdown >/dev/null 2>&1; then
    ok "wechat-article-to-markdown 已安装"
    return 0
  fi

  info "安装 wechat-article-to-markdown..."

  if [ "$DRY_RUN" -eq 1 ]; then
    printf '[dry-run] uv tool install %s\n' "${WECHAT_TOOL_URL}"
    return 0
  fi

  uv tool install "${WECHAT_TOOL_URL}" \
    || warn "wechat-article-to-markdown 安装失败（可手动安装：uv tool install ${WECHAT_TOOL_URL}）"

  if command -v wechat-article-to-markdown >/dev/null 2>&1; then
    ok "wechat-article-to-markdown 安装完成"
  fi
}

bootstrap_optional_adapters() {
  local skill_root="$1"

  if [ "$WITH_OPTIONAL_ADAPTERS" -ne 1 ]; then
    return 0
  fi

  load_dependency_skills
  install_dependency_skills "$skill_root"
  install_node_deps "$skill_root"
  install_uv_tools
}

check_environment() {
  echo ""
  echo "================================"
  echo "  环境检查"
  echo "================================"
  echo ""

  if command -v uv >/dev/null 2>&1; then
    ok "uv 已安装（可安装 wechat-article-to-markdown，并运行 youtube-transcript）"
  else
    warn "未找到 uv。wechat-article-to-markdown 和 youtube-transcript 需要 uv"
    echo "  可用 Homebrew 安装：brew install uv"
  fi

  if command -v wechat-article-to-markdown >/dev/null 2>&1; then
    ok "wechat-article-to-markdown 已可用"
  else
    warn "未找到 wechat-article-to-markdown。无法自动提取微信公众号"
    echo "  可手动安装：uv tool install ${WECHAT_TOOL_URL}"
  fi

  if command -v lsof >/dev/null 2>&1 && lsof -i :9222 -sTCP:LISTEN >/dev/null 2>&1; then
    ok "Chrome 调试端口 9222 已监听（可复用已登录会话）"
  else
    info "未检测到 Chrome 调试端口 9222。baoyu-url-to-markdown 仍可自动拉起临时浏览器"
    echo "  如需复用已登录会话，再执行：open -na \"Google Chrome\" --args --remote-debugging-port=9222"
  fi

  echo ""
  echo "提示：即使部分外挂不可用，PDF / 本地文件 / 纯文本仍可直接进入主线。"
}

print_source_boundary() {
  local core_sources optional_sources manual_sources

  core_sources="$(join_source_labels core_builtin)"
  optional_sources="$(join_source_labels optional_adapter)"
  manual_sources="$(join_source_labels manual_only)"

  echo ""
  echo "================================"
  echo "  来源边界"
  echo "================================"
  echo ""
  echo "核心主线：$core_sources"
  echo "可选外挂：$optional_sources"
  echo "手动入口：$manual_sources"
}

print_adapter_states() {
  local output

  echo ""
  echo "================================"
  echo "  外挂状态"
  echo "================================"
  echo ""

  output="$(
    bash "$ADAPTER_STATE_SCRIPT" --skill-root "$SKILL_ROOT" --layout-mode installed_skill summary-human 2>&1
  )" || {
    warn "无法生成外挂状态摘要"
    printf '%s\n' "$output"
    return 0
  }

  printf '%s\n' "$output"
}

print_optional_adapter_hint() {
  local command

  command="bash install.sh"
  if [ "$UPGRADE" -eq 1 ]; then
    command="$command --upgrade"
  fi
  command="$command --platform ${PLATFORM}"
  if [ -n "$TARGET_DIR" ]; then
    command="$command --target-dir ${TARGET_DIR}"
  fi
  command="$command --with-optional-adapters"

  echo ""
  echo "提示：当前只准备了知识库核心主线。"
  echo "如需网页 / X / 微信公众号 / YouTube / 知乎自动提取，再运行："
  echo "  $command"
}

print_claude_upgrade_hint() {
  local platform="$1"

  if [ "$platform" != "claude" ]; then
    return 0
  fi

  echo ""
  echo "提示：Claude Code 安装完成后，还可以直接用 /llm-wiki-upgrade 更新核心主线。"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --platform)
      [ $# -ge 2 ] || { err "--platform 需要一个值"; usage; exit 1; }
      PLATFORM="$2"
      PLATFORM_EXPLICIT=1
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --target-dir)
      [ $# -ge 2 ] || { err "--target-dir 需要一个值"; usage; exit 1; }
      TARGET_DIR="$2"
      shift 2
      ;;
    --with-optional-adapters)
      WITH_OPTIONAL_ADAPTERS=1
      shift
      ;;
    --install-hooks)
      INSTALL_HOOKS=1
      shift
      ;;
    --uninstall-hooks)
      UNINSTALL_HOOKS=1
      shift
      ;;
    --upgrade)
      UPGRADE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      err "未知参数：$1"
      usage
      exit 1
      ;;
  esac
done

if [ "$INSTALL_HOOKS" -eq 1 ] && [ "$UNINSTALL_HOOKS" -eq 1 ]; then
  err "--install-hooks 和 --uninstall-hooks 不能同时使用"
  exit 1
fi

if [ "$UPGRADE" -eq 1 ]; then
  if [ -n "$TARGET_DIR" ] && [ "$PLATFORM" = "auto" ]; then
    err "自定义目标目录升级时请显式传入 --platform"
    exit 1
  fi

  if [ "$PLATFORM" = "auto" ]; then
    detected_platforms=()
    for p in claude codex openclaw hermes; do
      skill_root_candidate="$(resolve_platform_skill_root "$p")"
      [ -d "$skill_root_candidate/$SKILL_NAME" ] && detected_platforms+=("$p")
    done

    if [ "${#detected_platforms[@]}" -eq 0 ]; then
      err "没有检测到已安装的 llm-wiki，请先运行安装"
      exit 1
    fi

    if [ "${#detected_platforms[@]}" -gt 1 ]; then
      err "检测到多个已安装平台：${detected_platforms[*]}。升级时请显式传入 --platform"
      exit 1
    fi

    PLATFORM="${detected_platforms[0]}"
    UPGRADE_PLATFORMS=("${detected_platforms[@]}")
  else
    UPGRADE_PLATFORMS=("$PLATFORM")
  fi

  echo ""
  echo "================================"
  echo "  llm-wiki 升级"
  echo "================================"
  echo ""

  if [ -d "$SCRIPT_DIR/.git" ]; then
    info "从远程拉取最新代码..."
    if [ "$DRY_RUN" -eq 1 ]; then
      printf '[dry-run] git -C %s pull\n' "$SCRIPT_DIR"
    else
      git -C "$SCRIPT_DIR" pull || {
        err "git pull 失败，请检查网络或手动拉取后重试"
        exit 1
      }
    fi
    ok "代码已拉取到最新"
  else
    warn "当前目录不是 git 仓库，跳过 git pull"
  fi

  upgrade_failures=0

  for upgrade_platform in "${UPGRADE_PLATFORMS[@]}"; do
    upgrade_root="$(resolve_platform_skill_root "$upgrade_platform")"
    if [ -n "$TARGET_DIR" ]; then
      upgrade_target="$TARGET_DIR"
      upgrade_root="$(dirname "$upgrade_target")"
    else
      upgrade_target="$upgrade_root/$SKILL_NAME"
    fi

    echo ""
    info "更新 $upgrade_platform 的 llm-wiki..."
    echo "  目标目录：$upgrade_target"

    if [ ! -d "$upgrade_target" ]; then
      err "$upgrade_platform 尚未安装 llm-wiki：$upgrade_target"
      upgrade_failures=$((upgrade_failures + 1))
      continue
    fi

    run_cmd mkdir -p "$upgrade_target"
    install_bundle "$upgrade_target"
    install_companion_skills "$upgrade_platform" "$upgrade_root"
    bootstrap_optional_adapters "$upgrade_root"
    ok "$upgrade_platform 的 llm-wiki 已更新"
  done

  if [ "$upgrade_failures" -gt 0 ]; then
    echo ""
    err "llm-wiki 升级失败，请先确认目标目录存在且已完成安装"
    exit 1
  fi

  print_source_boundary
  if [ "$WITH_OPTIONAL_ADAPTERS" -eq 1 ]; then
    check_environment
  else
    print_optional_adapter_hint
  fi
  print_claude_upgrade_hint "$PLATFORM"

  echo ""
  ok "llm-wiki 升级完成"
  exit 0
fi

if [ "$PLATFORM" = "auto" ] && { [ "$INSTALL_HOOKS" -eq 1 ] || [ "$UNINSTALL_HOOKS" -eq 1 ]; }; then
  PLATFORM="claude"
fi

if [ "$PLATFORM" = "auto" ]; then
  detected_platforms=()
  while IFS= read -r platform_name; do
    [ -n "$platform_name" ] && detected_platforms+=("$platform_name")
  done < <(detect_available_platforms)
  if [ "${#detected_platforms[@]}" -eq 1 ]; then
    PLATFORM="${detected_platforms[0]}"
  elif [ "${#detected_platforms[@]}" -eq 0 ]; then
    err "没有检测到受支持的平台目录。请显式传入 --platform claude|codex|openclaw|hermes"
    exit 1
  else
    err "检测到多个可用平台：${detected_platforms[*]}。请显式传入 --platform"
    exit 1
  fi
fi

SKILL_ROOT="$(resolve_platform_skill_root "$PLATFORM")"

if { [ "$INSTALL_HOOKS" -eq 1 ] || [ "$UNINSTALL_HOOKS" -eq 1 ]; } && [ "$PLATFORM" != "claude" ]; then
  err "只有 Claude Code 支持 SessionStart hook"
  exit 1
fi

if [ -n "$TARGET_DIR" ]; then
  TARGET_SKILL_DIR="$TARGET_DIR"
  SKILL_ROOT="$(dirname "$TARGET_SKILL_DIR")"
else
  TARGET_SKILL_DIR="$SKILL_ROOT/$SKILL_NAME"
fi

if [ "$UNINSTALL_HOOKS" -eq 1 ]; then
  uninstall_claude_session_hook "$TARGET_SKILL_DIR"
  echo ""
  ok "llm-wiki hook 已移除"
  exit 0
fi

if [ "$INSTALL_HOOKS" -eq 1 ] && [ "$PLATFORM_EXPLICIT" -eq 0 ] && [ -z "$TARGET_DIR" ]; then
  register_claude_session_hook "$TARGET_SKILL_DIR"
  echo ""
  ok "llm-wiki hook 已准备完成"
  exit 0
fi

echo ""
echo "================================"
echo "  llm-wiki 安装"
echo "================================"
echo ""
echo "平台：$PLATFORM"
echo "技能根目录：$SKILL_ROOT"
echo "目标目录：$TARGET_SKILL_DIR"

run_cmd mkdir -p "$SKILL_ROOT"
run_cmd mkdir -p "$TARGET_SKILL_DIR"

install_bundle "$TARGET_SKILL_DIR"
install_companion_skills "$PLATFORM" "$SKILL_ROOT"
bootstrap_optional_adapters "$SKILL_ROOT"
print_source_boundary
if [ "$WITH_OPTIONAL_ADAPTERS" -eq 1 ]; then
  check_environment
  print_adapter_states
else
  print_optional_adapter_hint
fi
print_claude_upgrade_hint "$PLATFORM"

if [ "$INSTALL_HOOKS" -eq 1 ]; then
  register_claude_session_hook "$TARGET_SKILL_DIR"
fi

echo ""
ok "llm-wiki 已准备完成"
