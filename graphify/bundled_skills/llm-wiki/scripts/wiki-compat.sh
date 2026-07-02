#!/bin/bash
# 旧知识库兼容脚本：惰性默认、目录检查、按需创建
# 原则：migration_required=no，只有确实无法兼容时才引入显式迁移

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOURCE_REGISTRY_SCRIPT="$SCRIPT_DIR/source-registry.sh"

LEGACY_REQUIRED_RAW_DIRS=(
  "raw/articles"
  "raw/tweets"
  "raw/wechat"
  "raw/pdfs"
  "raw/notes"
  "raw/assets"
)

REQUIRED_PATHS=(
  ".wiki-schema.md"
  "index.md"
  "log.md"
  "raw"
  "wiki"
  "wiki/entities"
  "wiki/topics"
  "wiki/sources"
  "wiki/comparisons"
  "wiki/synthesis"
  "wiki/overview.md"
)

usage() {
  cat <<'EOF'
用法：
  bash scripts/wiki-compat.sh inspect <wiki_root>
  bash scripts/wiki-compat.sh validate <wiki_root>
  bash scripts/wiki-compat.sh ensure-source-dir <wiki_root> <source_id>
EOF
}

trim() {
  printf '%s' "$1" | awk '{ gsub(/^[[:space:]]+|[[:space:]]+$/, "", $0); printf "%s", $0 }'
}

require_wiki_root() {
  local wiki_root="$1"

  [ -n "$wiki_root" ] || {
    usage
    exit 1
  }

  [ -d "$wiki_root" ] || {
    echo "知识库不存在：$wiki_root" >&2
    exit 1
  }
}

schema_field_value() {
  local wiki_root="$1"
  local field_name="$2"
  local default_value="$3"
  local schema_path value

  schema_path="$wiki_root/.wiki-schema.md"

  if [ ! -f "$schema_path" ]; then
    printf '%s\n' "$default_value"
    return 0
  fi

  value="$(
    awk -v field_name="$field_name" '
      $0 ~ "^-[[:space:]]*" field_name "[：:]" {
        line = $0
        sub("^-[[:space:]]*" field_name "[：:][[:space:]]*", "", line)
        print line
        exit
      }
    ' "$schema_path"
  )"

  value="$(trim "$value")"

  if [ -n "$value" ]; then
    printf '%s\n' "$value"
  else
    printf '%s\n' "$default_value"
  fi
}

resolved_language() {
  local wiki_root="$1"
  local raw_value

  raw_value="$(schema_field_value "$wiki_root" "语言" "")"

  case "$raw_value" in
    English|english|EN|en)
      printf 'en\n'
      ;;
    *)
      printf 'zh\n'
      ;;
  esac
}

resolved_schema_version() {
  local wiki_root="$1"

  schema_field_value "$wiki_root" "版本" "1.0"
}

is_legacy_required_raw_dir() {
  case "$1" in
    raw/articles|raw/tweets|raw/wechat|raw/pdfs|raw/notes|raw/assets)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

missing_optional_raw_dirs() {
  local wiki_root="$1"
  local raw_dir
  local missing=()

  while IFS= read -r raw_dir; do
    [ -n "$raw_dir" ] || continue

    if is_legacy_required_raw_dir "$raw_dir"; then
      continue
    fi

    if [ ! -d "$wiki_root/$raw_dir" ]; then
      missing+=("$raw_dir")
    fi
  done < <(
    bash "$SOURCE_REGISTRY_SCRIPT" list | awk -F '\t' 'NR > 1 { print $6 }' | LC_ALL=C sort -u
  )

  if [ "${#missing[@]}" -eq 0 ]; then
    printf '%s\n' '-'
  else
    local IFS=,
    printf '%s\n' "${missing[*]}"
  fi
}

file_presence() {
  local wiki_root="$1"
  local relative_path="$2"

  if [ -e "$wiki_root/$relative_path" ]; then
    printf 'present\n'
  else
    printf 'missing\n'
  fi
}

validate_layout() {
  local wiki_root="$1"
  local failed=0
  local path

  require_wiki_root "$wiki_root"

  for path in "${REQUIRED_PATHS[@]}"; do
    if [ ! -e "$wiki_root/$path" ]; then
      echo "缺少必要路径：$path" >&2
      failed=1
    fi
  done

  for path in "${LEGACY_REQUIRED_RAW_DIRS[@]}"; do
    if [ ! -d "$wiki_root/$path" ]; then
      echo "缺少必要旧目录：$path" >&2
      failed=1
    fi
  done

  if [ "$failed" -ne 0 ]; then
    exit 1
  fi
}

source_raw_dir() {
  local source_id="$1"
  local record raw_dir

  record="$(
    bash "$SOURCE_REGISTRY_SCRIPT" get "$source_id" 2>/dev/null
  )" || {
    echo "未知来源：$source_id" >&2
    exit 1
  }

  IFS=$'\t' read -r _ _ _ _ _ raw_dir _ _ _ _ <<EOF
$record
EOF

  printf '%s\n' "$raw_dir"
}

print_inspect() {
  local wiki_root="$1"
  local schema_version language optional_dirs legacy_mode purpose_file cache_file

  validate_layout "$wiki_root"

  schema_version="$(resolved_schema_version "$wiki_root")"
  language="$(resolved_language "$wiki_root")"
  optional_dirs="$(missing_optional_raw_dirs "$wiki_root")"
  purpose_file="$(file_presence "$wiki_root" "purpose.md")"
  cache_file="$(file_presence "$wiki_root" ".wiki-cache.json")"

  if [ "$schema_version" = "1.0" ] || [ "$optional_dirs" != "-" ] || [ "$purpose_file" = "missing" ] || [ "$cache_file" = "missing" ]; then
    legacy_mode="yes"
  else
    legacy_mode="no"
  fi

  printf 'wiki_root=%s\n' "$wiki_root"
  printf 'schema_version=%s\n' "$schema_version"
  printf 'language=%s\n' "$language"
  printf 'legacy_mode=%s\n' "$legacy_mode"
  printf 'migration_required=no\n'
  printf 'missing_optional_raw_dirs=%s\n' "$optional_dirs"
  printf 'purpose_file=%s\n' "$purpose_file"
  printf 'cache_file=%s\n' "$cache_file"
}

ensure_source_dir() {
  local wiki_root="$1"
  local source_id="$2"
  local raw_dir

  validate_layout "$wiki_root"
  raw_dir="$(source_raw_dir "$source_id")"

  mkdir -p "$wiki_root/$raw_dir"
  printf '%s\n' "$wiki_root/$raw_dir"
}

command_name="${1:-}"

case "$command_name" in
  inspect)
    [ "$#" -eq 2 ] || { usage; exit 1; }
    print_inspect "$2"
    ;;
  validate)
    [ "$#" -eq 2 ] || { usage; exit 1; }
    print_inspect "$2" > /dev/null
    ;;
  ensure-source-dir)
    [ "$#" -eq 3 ] || { usage; exit 1; }
    ensure_source_dir "$2" "$3"
    ;;
  *)
    usage
    exit 1
    ;;
esac
