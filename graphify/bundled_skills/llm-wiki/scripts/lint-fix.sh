#!/bin/bash
# lint-fix.sh — 自动修复 lint 发现的低风险问题
# 用法：bash scripts/lint-fix.sh <wiki_root> [--dry-run]
# 修复范围：仅处理确定性修复（补 index 条目），不做高风险操作（删页面、改内容）
# 退出码：0 = 完成，1 = 参数错误

set -u
shopt -s nullglob

WIKI_ROOT="${1:-.}"
DRY_RUN=false
[ "${2:-}" = "--dry-run" ] && DRY_RUN=true

WIKI_DIR="$WIKI_ROOT/wiki"
INDEX_FILE="$WIKI_ROOT/index.md"

if [ ! -d "$WIKI_DIR" ]; then
  echo "ERROR: wiki directory not found: $WIKI_DIR" >&2
  exit 1
fi
if [ ! -f "$INDEX_FILE" ]; then
  echo "ERROR: index.md not found: $INDEX_FILE" >&2
  exit 1
fi

FIXED=0

index_has_entry() {
  local entry="$1"
  grep -ohE "\[\[[^]]+\]\]" "$INDEX_FILE" 2>/dev/null | \
    sed -e 's/\[\[//g' -e 's/\]\]//g' -e 's/|.*//' | \
    grep -Fxq "$entry"
}

# Insert a [[link]] entry after the matching section header in index.md.
# If no matching section is found, appends to end of file as fallback.
insert_under_section() {
  local index_file="$1"
  local section_pattern="$2"
  local entry="$3"

  # Find the line number of the section header
  local line_num
  line_num=$(grep -n -i -E "^#.*($section_pattern)" "$index_file" 2>/dev/null | head -1 | cut -d: -f1)

  if [ -n "$line_num" ]; then
    # Scan from section header to find insert point:
    # last "- [[" line before next "##" header or EOF
    local total_lines last_list_line offset
    total_lines=$(wc -l < "$index_file" | tr -d ' ')
    last_list_line="$line_num"
    offset=$((line_num + 1))
    while [ "$offset" -le "$total_lines" ]; do
      local cur_line
      cur_line=$(sed -n "${offset}p" "$index_file")
      case "$cur_line" in
        "##"*) break ;;
        "- [["*) last_list_line="$offset" ;;
      esac
      offset=$((offset + 1))
    done
    # Insert after the last list item
    local tmp_file
    tmp_file=$(mktemp "${index_file}.tmp.XXXXXX") || return 1
    awk -v insert_after="$last_list_line" -v entry="$entry" '
      { print }
      NR == insert_after { print "- [[" entry "]]" }
    ' "$index_file" > "$tmp_file" && mv "$tmp_file" "$index_file"
  else
    # Fallback: append to end of file
    printf '\n- [[%s]]\n' "$entry" >> "$index_file"
  fi
}

echo "=== lint-fix: low-risk auto-repair ==="
echo ""

# Fix 1: Add unlisted pages to index.md
# Only adds pages that exist in wiki/ but are not referenced in index.md
# Skips derived pages (queries/, sessions/)
echo "--- Checking for unlisted pages ---"
for _subdir in entities topics sources comparisons synthesis; do
  for f in "$WIKI_DIR"/$_subdir/*.md; do
    [ -f "$f" ] || continue
    BASENAME=$(basename "$f" .md)
    # Skip derived pages
    case "$f" in
      */queries/*|*/sessions/*) continue ;;
    esac
    if ! index_has_entry "$BASENAME"; then
      SECTION_PATTERN=""
      case "$_subdir" in
        entities) SECTION_PATTERN="实体页|Entities" ;;
        topics) SECTION_PATTERN="主题页|Topics" ;;
        sources) SECTION_PATTERN="素材摘要|Sources" ;;
        comparisons) SECTION_PATTERN="对比分析|Comparisons" ;;
        synthesis) SECTION_PATTERN="综合分析|Synthesis" ;;
      esac
      if [ "$DRY_RUN" = true ]; then
        echo "  [dry-run] Would add [[$BASENAME]] under $_subdir section"
      else
        insert_under_section "$INDEX_FILE" "$SECTION_PATTERN" "$BASENAME"
        echo "  Fixed: added [[$BASENAME]] under $_subdir section"
      fi
      FIXED=$((FIXED + 1))
    fi
  done
done
[ "$FIXED" -eq 0 ] && echo "  (all pages already listed)"
echo ""

echo "=== lint-fix complete: $FIXED fix(es) applied ==="
[ "$DRY_RUN" = true ] && echo "(dry-run mode — no files were modified)"
exit 0
