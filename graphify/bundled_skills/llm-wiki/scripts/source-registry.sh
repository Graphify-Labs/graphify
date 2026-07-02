#!/bin/bash
# 统一来源总表读取与验证脚本
# 权威数据文件：source-registry.tsv（来源定义）、source-record-contract.tsv（字段契约）

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONTRACT_FILE="$SCRIPT_DIR/source-record-contract.tsv"
REGISTRY_FILE="$SCRIPT_DIR/source-registry.tsv"

usage() {
  cat <<'EOF'
用法：
  bash scripts/source-registry.sh fields
  bash scripts/source-registry.sh list
  bash scripts/source-registry.sh get <source_id>
  bash scripts/source-registry.sh match-url <url>
  bash scripts/source-registry.sh match-file <path>
  bash scripts/source-registry.sh list-by-category <core_builtin|optional_adapter|manual_only>
  bash scripts/source-registry.sh unique-dependencies <bundled|install_time|none>
  bash scripts/source-registry.sh validate
EOF
}

require_file() {
  local file="$1"

  [ -f "$file" ] || {
    echo "缺少文件：$file" >&2
    exit 1
  }
}

expect_header() {
  local file="$1"
  local expected="$2"
  local actual

  actual="$(head -n 1 "$file")"
  [ "$actual" = "$expected" ] || {
    echo "表头不匹配：$file" >&2
    echo "期望：$expected" >&2
    echo "实际：$actual" >&2
    exit 1
  }
}

validate_contract() {
  require_file "$CONTRACT_FILE"
  expect_header "$CONTRACT_FILE" $'field_name\trequiredness\tfilled_by\tvalue_rule'

  awk -F '\t' '
    BEGIN {
      required["source_id"] = 1
      required["source_label"] = 1
      required["source_category"] = 1
      required["input_mode"] = 1
      required["raw_dir"] = 1
      required["original_ref"] = 1
      required["ingest_text"] = 1
      required["adapter_name"] = 1
      required["fallback_hint"] = 1
    }
    NR == 1 { next }
    {
      if ($1 == "" || $2 == "" || $3 == "" || $4 == "") {
        printf("source-record-contract.tsv 第 %d 行存在空字段\n", NR) > "/dev/stderr"
        failed = 1
      }

      seen[$1] += 1
    }
    END {
      for (field in required) {
        if (seen[field] != 1) {
          printf("source-record-contract.tsv 缺少或重复字段：%s\n", field) > "/dev/stderr"
          failed = 1
        }
      }

      exit failed ? 1 : 0
    }
  ' "$CONTRACT_FILE"
}

validate_registry() {
  require_file "$REGISTRY_FILE"
  expect_header "$REGISTRY_FILE" $'source_id\tsource_label\tsource_category\tinput_mode\tmatch_rule\traw_dir\tadapter_name\tdependency_name\tdependency_type\tfallback_hint'

  awk -F '\t' '
    NR == 1 { next }
    {
      if ($1 == "" || $2 == "" || $3 == "" || $4 == "" || $5 == "" || $6 == "" || $10 == "") {
        printf("source-registry.tsv 第 %d 行存在空字段\n", NR) > "/dev/stderr"
        failed = 1
      }

      if ($3 != "core_builtin" && $3 != "optional_adapter" && $3 != "manual_only") {
        printf("source-registry.tsv 第 %d 行存在未知分类：%s\n", NR, $3) > "/dev/stderr"
        failed = 1
      }

      if ($4 != "url" && $4 != "file" && $4 != "text" && $4 != "asset") {
        printf("source-registry.tsv 第 %d 行存在未知输入模式：%s\n", NR, $4) > "/dev/stderr"
        failed = 1
      }

      if ($4 == "url" && $5 !~ /^url_host:/) {
        printf("source-registry.tsv 第 %d 行 URL 来源必须声明 url_host 规则：%s\n", NR, $5) > "/dev/stderr"
        failed = 1
      }

      if ($4 == "file" && $5 !~ /^file_ext:/) {
        printf("source-registry.tsv 第 %d 行文件来源必须声明 file_ext 规则：%s\n", NR, $5) > "/dev/stderr"
        failed = 1
      }

      if ($4 == "text" && $5 !~ /^text:/) {
        printf("source-registry.tsv 第 %d 行文本来源必须声明 text 规则：%s\n", NR, $5) > "/dev/stderr"
        failed = 1
      }

      if ($4 == "asset" && $5 !~ /^asset:/) {
        printf("source-registry.tsv 第 %d 行附件来源必须声明 asset 规则：%s\n", NR, $5) > "/dev/stderr"
        failed = 1
      }

      if ($6 !~ /^raw\//) {
        printf("source-registry.tsv 第 %d 行 raw_dir 必须位于 raw/ 下：%s\n", NR, $6) > "/dev/stderr"
        failed = 1
      }

      if (seen[$1]++) {
        printf("source-registry.tsv source_id 重复：%s\n", $1) > "/dev/stderr"
        failed = 1
      }

      category_seen[$3] = 1

      if ($3 == "optional_adapter") {
        if ($7 == "-" || $8 == "-" || $9 == "none") {
          printf("source-registry.tsv 第 %d 行 optional_adapter 缺少依赖信息\n", NR) > "/dev/stderr"
          failed = 1
        }
      } else if ($7 != "-" || $8 != "-" || $9 != "none") {
        printf("source-registry.tsv 第 %d 行非外挂来源不应声明依赖\n", NR) > "/dev/stderr"
        failed = 1
      }
    }
    END {
      if (!category_seen["core_builtin"]) {
        print "source-registry.tsv 缺少 core_builtin 来源" > "/dev/stderr"
        failed = 1
      }

      if (!category_seen["optional_adapter"]) {
        print "source-registry.tsv 缺少 optional_adapter 来源" > "/dev/stderr"
        failed = 1
      }

      if (!category_seen["manual_only"]) {
        print "source-registry.tsv 缺少 manual_only 来源" > "/dev/stderr"
        failed = 1
      }

      exit failed ? 1 : 0
    }
  ' "$REGISTRY_FILE"
}

print_contract() {
  validate_contract
  cat "$CONTRACT_FILE"
}

print_registry() {
  validate_registry
  cat "$REGISTRY_FILE"
}

get_source() {
  local source_id="$1"

  validate_registry

  awk -F '\t' -v source_id="$source_id" '
    NR == 1 { next }
    $1 == source_id {
      print
      found = 1
    }
    END {
      exit found ? 0 : 1
    }
  ' "$REGISTRY_FILE"
}

extract_url_host() {
  local url="$1"
  local rest host

  rest="${url#*://}"
  if [ "$rest" = "$url" ]; then
    rest="$url"
  fi

  rest="${rest#*@}"
  host="${rest%%/*}"
  host="${host%%\?*}"
  host="${host%%#*}"
  host="${host%%:*}"

  printf '%s\n' "$host" | tr '[:upper:]' '[:lower:]'
}

host_matches_pattern() {
  local host="$1"
  local pattern="$2"

  case "$host" in
    "$pattern"|*."$pattern")
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

match_url() {
  local url="$1"
  local host row source_id source_label source_category input_mode match_rule raw_dir adapter_name dependency_name dependency_type fallback_hint
  local fallback_row=""
  local pattern pattern_list

  validate_registry
  host="$(extract_url_host "$url")"

  while IFS=$'\t' read -r source_id source_label source_category input_mode match_rule raw_dir adapter_name dependency_name dependency_type fallback_hint; do
    [ "$source_id" = "source_id" ] && continue
    [ "$input_mode" = "url" ] || continue

    pattern_list="${match_rule#url_host:}"
    if [ "$pattern_list" = "*" ]; then
      fallback_row="$(printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$source_id" "$source_label" "$source_category" "$input_mode" "$match_rule" "$raw_dir" "$adapter_name" "$dependency_name" "$dependency_type" "$fallback_hint")"
      continue
    fi

    for pattern in ${pattern_list//,/ }; do
      if host_matches_pattern "$host" "$pattern"; then
        printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$source_id" "$source_label" "$source_category" "$input_mode" "$match_rule" "$raw_dir" "$adapter_name" "$dependency_name" "$dependency_type" "$fallback_hint"
        return 0
      fi
    done
  done < "$REGISTRY_FILE"

  [ -n "$fallback_row" ] || return 1
  printf '%s\n' "$fallback_row"
}

match_file() {
  local path="$1"
  local lowered_path source_id source_label source_category input_mode match_rule raw_dir adapter_name dependency_name dependency_type fallback_hint
  local extension_list extension

  validate_registry
  lowered_path="$(printf '%s\n' "$path" | tr '[:upper:]' '[:lower:]')"

  while IFS=$'\t' read -r source_id source_label source_category input_mode match_rule raw_dir adapter_name dependency_name dependency_type fallback_hint; do
    [ "$source_id" = "source_id" ] && continue
    [ "$input_mode" = "file" ] || continue

    extension_list="${match_rule#file_ext:}"
    for extension in ${extension_list//,/ }; do
      case "$lowered_path" in
        *"$extension")
          printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$source_id" "$source_label" "$source_category" "$input_mode" "$match_rule" "$raw_dir" "$adapter_name" "$dependency_name" "$dependency_type" "$fallback_hint"
          return 0
          ;;
      esac
    done
  done < "$REGISTRY_FILE"

  return 1
}

list_by_category() {
  local category="$1"

  validate_registry

  awk -F '\t' -v category="$category" '
    NR == 1 { next }
    $3 == category { print }
  ' "$REGISTRY_FILE"
}

list_unique_dependencies() {
  local dependency_type="$1"

  validate_registry

  awk -F '\t' -v dependency_type="$dependency_type" '
    NR == 1 { next }
    $9 == dependency_type && $8 != "-" { print $8 }
  ' "$REGISTRY_FILE" | sort -u
}

command_name="${1:-}"

case "$command_name" in
  fields)
    [ "$#" -eq 1 ] || { usage; exit 1; }
    print_contract
    ;;
  list)
    [ "$#" -eq 1 ] || { usage; exit 1; }
    print_registry
    ;;
  get)
    [ "$#" -eq 2 ] || { usage; exit 1; }
    get_source "$2"
    ;;
  match-url)
    [ "$#" -eq 2 ] || { usage; exit 1; }
    match_url "$2"
    ;;
  match-file)
    [ "$#" -eq 2 ] || { usage; exit 1; }
    match_file "$2"
    ;;
  list-by-category)
    [ "$#" -eq 2 ] || { usage; exit 1; }
    list_by_category "$2"
    ;;
  unique-dependencies)
    [ "$#" -eq 2 ] || { usage; exit 1; }
    list_unique_dependencies "$2"
    ;;
  validate)
    [ "$#" -eq 1 ] || { usage; exit 1; }
    validate_contract
    validate_registry
    ;;
  *)
    usage
    exit 1
    ;;
esac
