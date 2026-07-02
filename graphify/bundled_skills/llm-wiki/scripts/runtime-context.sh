#!/bin/bash
# 共享运行场景解析：供 install.sh 和 adapter-state.sh 复用

resolve_platform_skill_root() {
  case "$1" in
    claude)
      printf '%s\n' "$HOME/.claude/skills"
      ;;
    codex)
      if [ -d "$HOME/.codex/skills" ] || [ ! -d "$HOME/.Codex/skills" ]; then
        printf '%s\n' "$HOME/.codex/skills"
      else
        printf '%s\n' "$HOME/.Codex/skills"
      fi
      ;;
    openclaw)
      printf '%s\n' "$HOME/.openclaw/skills"
      ;;
    hermes)
      printf '%s\n' "$HOME/.hermes/skills"
      ;;
    *)
      echo "不支持的平台：$1" >&2
      return 1
      ;;
  esac
}

detect_layout_mode() {
  local bundle_root="$1"

  if [ -e "$bundle_root/.git" ]; then
    printf '%s\n' "source_checkout"
    return 0
  fi

  printf '%s\n' "installed_skill"
}

resolve_layout_mode() {
  local bundle_root="$1"
  local override_mode="${2:-}"

  if [ -n "$override_mode" ]; then
    printf '%s\n' "$override_mode"
    return 0
  fi

  detect_layout_mode "$bundle_root"
}

resolve_optional_adapter_root() {
  local bundle_root="$1"
  local skill_root_override="${2:-}"
  local override_mode="${3:-}"
  local layout_mode

  if [ -n "$skill_root_override" ]; then
    printf '%s\n' "$skill_root_override"
    return 0
  fi

  layout_mode="$(resolve_layout_mode "$bundle_root" "$override_mode")"

  case "$layout_mode" in
    source_checkout)
      printf '%s\n' "$bundle_root/deps"
      ;;
    installed_skill|upgrade_target)
      printf '%s\n' "$(dirname "$bundle_root")"
      ;;
    *)
      echo "未知运行模式：$layout_mode" >&2
      return 1
      ;;
  esac
}
