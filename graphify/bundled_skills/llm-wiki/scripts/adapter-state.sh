#!/bin/bash
# 外挂状态检测脚本：统一判断可选外挂的安装/环境/运行状态
# 五种状态：not_installed / env_unavailable（仅 uv 依赖的来源） / runtime_failed / unsupported / empty_result

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SOURCE_REGISTRY_SCRIPT="$SCRIPT_DIR/source-registry.sh"
# 微信工具 URL 从共享配置读取，与 install.sh 保持一致
source "$SCRIPT_DIR/shared-config.sh"
source "$SCRIPT_DIR/runtime-context.sh"
SKILL_ROOT_OVERRIDE=""
LAYOUT_MODE_OVERRIDE=""

usage() {
  cat <<'EOF'
用法：
  bash scripts/adapter-state.sh [--skill-root <path>] [--layout-mode <source_checkout|installed_skill|upgrade_target>] check <source_id>
  bash scripts/adapter-state.sh [--skill-root <path>] [--layout-mode <source_checkout|installed_skill|upgrade_target>] summary
  bash scripts/adapter-state.sh [--skill-root <path>] [--layout-mode <source_checkout|installed_skill|upgrade_target>] summary-human
  bash scripts/adapter-state.sh [--skill-root <path>] [--layout-mode <source_checkout|installed_skill|upgrade_target>] classify-run <source_id> <exit_code> <output_path>
EOF
}

resolve_optional_root() {
  resolve_optional_adapter_root "$PROJECT_ROOT" "$SKILL_ROOT_OVERRIDE" "$LAYOUT_MODE_OVERRIDE"
}

dependency_installed() {
  local dependency_name="$1"
  local dependency_type="$2"
  local optional_root

  case "$dependency_type" in
    bundled)
      optional_root="$(resolve_optional_root)"
      if [ -d "$optional_root/$dependency_name" ]; then
        return 0
      fi
      return 1
      ;;
    install_time)
      command -v "$dependency_name" >/dev/null 2>&1
      ;;
    none)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

has_uv() {
  command -v uv >/dev/null 2>&1
}

chrome_debug_ready() {
  if command -v lsof >/dev/null 2>&1; then
    lsof -i :9222 -sTCP:LISTEN >/dev/null 2>&1
    return $?
  fi

  return 1
}

print_header() {
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "source_id" \
    "source_label" \
    "state" \
    "state_label" \
    "detail" \
    "recovery_action" \
    "install_hint" \
    "fallback_hint"
}

state_label() {
  case "$1" in
    available)
      printf '%s\n' "可用"
      ;;
    not_installed)
      printf '%s\n' "未安装"
      ;;
    env_unavailable)
      printf '%s\n' "环境不满足"
      ;;
    runtime_failed)
      printf '%s\n' "运行失败"
      ;;
    unsupported)
      printf '%s\n' "不支持自动提取"
      ;;
    empty_result)
      printf '%s\n' "结果为空"
      ;;
    *)
      printf '%s\n' "$1"
      ;;
  esac
}

default_install_hint() {
  local source_id="$1"
  local adapter_name="$2"

  case "$source_id" in
    web_article|x_twitter|zhihu_article)
      printf '%s\n' "重新运行当前平台的 llm-wiki 安装命令，并追加 --with-optional-adapters，确认 ${adapter_name} 已准备到技能目录"
      ;;
    wechat_article)
      printf '%s\n' "先安装 uv，再执行：uv tool install ${WECHAT_TOOL_URL}"
      ;;
    youtube_video)
      printf '%s\n' "重新运行当前平台的 llm-wiki 安装命令，并追加 --with-optional-adapters，确认 ${adapter_name} 已准备到技能目录"
      ;;
    *)
      printf '%s\n' "-"
      ;;
  esac
}

optional_hint() {
  local source_id="$1"

  case "$source_id" in
    web_article|x_twitter|zhihu_article)
      printf '%s\n' '如需复用已登录的浏览器会话，可执行：open -na "Google Chrome" --args --remote-debugging-port=9222'
      ;;
    wechat_article|youtube_video)
      printf '%s\n' "先安装 uv：brew install uv"
      ;;
    *)
      printf '%s\n' "-"
      ;;
  esac
}

emit_state_row() {
  local source_id="$1"
  local source_label="$2"
  local state="$3"
  local detail="$4"
  local recovery_action="$5"
  local install_hint="$6"
  local fallback_hint="$7"

  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$source_id" \
    "$source_label" \
    "$state" \
    "$(state_label "$state")" \
    "$detail" \
    "$recovery_action" \
    "$install_hint" \
    "$fallback_hint"
}

resolve_preflight_state() {
  local source_id="$1"
  local record
  local source_label source_category input_mode match_rule raw_dir adapter_name dependency_name dependency_type fallback_hint
  local state detail recovery_action install_hint

  record="$(bash "$SOURCE_REGISTRY_SCRIPT" get "$source_id")" || {
    echo "未知来源：$source_id" >&2
    exit 1
  }

  IFS=$'\t' read -r source_id source_label source_category input_mode match_rule raw_dir adapter_name dependency_name dependency_type fallback_hint <<EOF
$record
EOF

  case "$source_category" in
    core_builtin)
      state="available"
      detail="核心主线可直接进入，不依赖外挂"
      recovery_action="直接继续主线"
      install_hint="-"
      ;;
    manual_only)
      state="unsupported"
      detail="该来源当前只支持手动进入主线"
      recovery_action="直接走手动入口"
      install_hint="-"
      ;;
    optional_adapter)
      case "$source_id" in
        wechat_article)
          if ! has_uv; then
            state="env_unavailable"
            detail="缺少 uv，当前无法准备微信公众号自动提取环境"
            recovery_action="先补环境；现在也可以直接走手动入口"
            install_hint="$(optional_hint "$source_id")"
          elif ! dependency_installed "$dependency_name" "$dependency_type"; then
            state="not_installed"
            detail="未找到 ${adapter_name}"
            recovery_action="先补安装；现在也可以直接走手动入口"
            install_hint="$(default_install_hint "$source_id" "$adapter_name")"
          else
            state="available"
            detail="${adapter_name} 已可用"
            recovery_action="继续自动提取"
            install_hint="-"
          fi
          ;;
        web_article|x_twitter|zhihu_article)
          if ! dependency_installed "$dependency_name" "$dependency_type"; then
            state="not_installed"
            detail="未找到 ${adapter_name}"
            recovery_action="先补安装；现在也可以直接走手动入口"
            install_hint="$(default_install_hint "$source_id" "$adapter_name")"
          else
            state="available"
            if chrome_debug_ready; then
              detail="${adapter_name} 已可用，且已检测到可复用的 Chrome 调试会话"
              recovery_action="继续自动提取"
              install_hint="-"
            else
              detail="${adapter_name} 已可用；未检测到 9222，将在需要时自动拉起临时浏览器"
              recovery_action="继续自动提取；如需复用已登录会话，可先开启 Chrome 调试端口 9222"
              install_hint="$(optional_hint "$source_id")"
            fi
          fi
          ;;
        youtube_video)
          if ! dependency_installed "$dependency_name" "$dependency_type"; then
            state="not_installed"
            detail="未找到 ${adapter_name}"
            recovery_action="先补安装；现在也可以直接走手动入口"
            install_hint="$(default_install_hint "$source_id" "$adapter_name")"
          elif ! has_uv; then
            state="env_unavailable"
            detail="缺少 uv，当前无法运行 YouTube 字幕提取"
            recovery_action="先补环境；现在也可以直接走手动入口"
            install_hint="$(optional_hint "$source_id")"
          else
            state="available"
            detail="${adapter_name} 已可用"
            recovery_action="继续自动提取"
            install_hint="-"
          fi
          ;;
        *)
          if ! dependency_installed "$dependency_name" "$dependency_type"; then
            state="not_installed"
            detail="未找到 ${adapter_name}"
            recovery_action="先补安装；现在也可以直接走手动入口"
            install_hint="$(default_install_hint "$source_id" "$adapter_name")"
          else
            state="available"
            detail="${adapter_name} 已可用"
            recovery_action="继续自动提取"
            install_hint="-"
          fi
          ;;
      esac
      ;;
    *)
      echo "未知来源分类：$source_category" >&2
      exit 1
      ;;
  esac

  emit_state_row \
    "$source_id" \
    "$source_label" \
    "$state" \
    "$detail" \
    "$recovery_action" \
    "$install_hint" \
    "$fallback_hint"
}

classify_run_state() {
  local source_id="$1"
  local exit_code="$2"
  local output_path="$3"

  # 校验 exit_code 为整数，防止 set -e 下非数字参数导致脚本崩溃
  case "$exit_code" in
    ''|*[!0-9-]*) echo "exit_code 必须是整数，收到：$exit_code" >&2; exit 1 ;;
  esac

  local row
  local source_label state state_label_value detail recovery_action install_hint fallback_hint

  row="$(resolve_preflight_state "$source_id")"
  IFS=$'\t' read -r _ source_label state state_label_value detail recovery_action install_hint fallback_hint <<EOF
$row
EOF

  if [ "$state" != "available" ]; then
    emit_state_row \
      "$source_id" \
      "$source_label" \
      "$state" \
      "$detail" \
      "$recovery_action" \
      "$install_hint" \
      "$fallback_hint"
    return 0
  fi

  if [ "$exit_code" -ne 0 ]; then
    emit_state_row \
      "$source_id" \
      "$source_label" \
      "runtime_failed" \
      "自动提取执行失败" \
      "可以先重试一次；如果还不行，就改走手动入口" \
      "-" \
      "$fallback_hint"
    return 0
  fi

  if [ ! -f "$output_path" ] || ! grep -q '[^[:space:]]' "$output_path" 2>/dev/null; then
    emit_state_row \
      "$source_id" \
      "$source_label" \
      "empty_result" \
      "自动提取完成，但没有拿到有效正文" \
      "请手动补全文本后继续主线" \
      "-" \
      "$fallback_hint"
    return 0
  fi

  emit_state_row \
    "$source_id" \
    "$source_label" \
    "available" \
    "自动提取已拿到有效正文" \
    "继续进入主线" \
    "-" \
    "$fallback_hint"
}

print_summary() {
  local source_id

  print_header

  while IFS=$'\t' read -r source_id _; do
    [ -n "$source_id" ] || continue
    resolve_preflight_state "$source_id"
  done <<EOF
$(bash "$SOURCE_REGISTRY_SCRIPT" list | awk -F '\t' 'NR > 1 && ($3 == "optional_adapter" || $3 == "manual_only") { print $1 "\t" $2 }')
EOF
}

print_summary_human() {
  local row
  local source_id source_label state state_label_value detail recovery_action install_hint fallback_hint

  while IFS= read -r row; do
    [ -n "$row" ] || continue

    IFS=$'\t' read -r source_id source_label state state_label_value detail recovery_action install_hint fallback_hint <<EOF
$row
EOF

    printf '%s\n' "- ${source_label}：${state_label_value}。${detail}。"
    printf '%s\n' "  下一步：${recovery_action}。"
    if [ "$install_hint" != "-" ]; then
      if [ "$state" = "available" ]; then
        printf '%s\n' "  补充说明：${install_hint}。"
      else
        printf '%s\n' "  安装提示：${install_hint}。"
      fi
    fi
    printf '%s\n' "  回退方式：${fallback_hint}。"
  done <<EOF
$(print_summary | tail -n +2)
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --skill-root)
      [ $# -ge 2 ] || { usage; exit 1; }
      SKILL_ROOT_OVERRIDE="$2"
      shift 2
      ;;
    --layout-mode)
      [ $# -ge 2 ] || { usage; exit 1; }
      LAYOUT_MODE_OVERRIDE="$2"
      shift 2
      ;;
    *)
      break
      ;;
  esac
done

command_name="${1:-}"

case "$command_name" in
  check)
    [ "$#" -eq 2 ] || { usage; exit 1; }
    print_header
    resolve_preflight_state "$2"
    ;;
  summary)
    [ "$#" -eq 1 ] || { usage; exit 1; }
    print_summary
    ;;
  summary-human)
    [ "$#" -eq 1 ] || { usage; exit 1; }
    print_summary_human
    ;;
  classify-run)
    [ "$#" -eq 4 ] || { usage; exit 1; }
    print_header
    classify_run_state "$2" "$3" "$4"
    ;;
  *)
    usage
    exit 1
    ;;
esac
