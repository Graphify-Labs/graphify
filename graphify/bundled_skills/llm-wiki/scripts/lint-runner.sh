#!/bin/bash
# lint-runner.sh — wiki 机械健康检查
# 用法：bash scripts/lint-runner.sh <wiki_root>
# 输出：结构化文本报告（供 AI 后续分析使用）
# 退出码：0 = 运行完成，1 = 脚本错误（路径不存在、wiki 结构不完整）

set -u
shopt -s nullglob

WIKI_ROOT="${1:-.}"
WIKI_DIR="$WIKI_ROOT/wiki"
INDEX_FILE="$WIKI_ROOT/index.md"

if [ ! -d "$WIKI_DIR" ]; then
  echo "ERROR: wiki 目录不存在：$WIKI_DIR" >&2
  echo "       请确认路径正确，或先运行 init 工作流初始化知识库。" >&2
  exit 1
fi
if [ ! -f "$INDEX_FILE" ]; then
  echo "ERROR: index.md 不存在：$INDEX_FILE" >&2
  exit 1
fi

index_has_entry() {
  local entry="$1"
  grep -ohE "\[\[[^]]+\]\]" "$INDEX_FILE" 2>/dev/null | \
    sed -e 's/\[\[//g' -e 's/\]\]//g' -e 's/|.*//' | \
    grep -Fxq "$entry"
}

echo "=== llm-wiki lint 报告 ==="
echo "时间：$(date '+%Y-%m-%d %H:%M')"
echo "检查路径：$WIKI_DIR"
echo ""

# 检查 1：孤立页面
# 定义：entities/、topics/、sources/ 下的页面，除了自己之外没有任何其他 wiki 页面用 [[名称]] 引用它
echo "--- 孤立页面（没有被其他页面引用） ---"
_ORPHANS=0
for _subdir in entities topics sources; do
  for f in "$WIKI_DIR"/$_subdir/*.md; do
    [ -f "$f" ] || continue
    BASENAME=$(basename "$f" .md)
    if ! grep -rlF "[[$BASENAME]]" "$WIKI_DIR" 2>/dev/null | grep -vxF "$f" | grep -q .; then
      echo "  孤立: $_subdir/$BASENAME"
      _ORPHANS=$((_ORPHANS + 1))
    fi
  done
done
[ "$_ORPHANS" -eq 0 ] && echo "  （无孤立页面）"
echo ""

# 检查 2：断链
# 定义：wiki/ 下的页面里有 [[X]] 链接（支持 [[X|别名]] 语法），但 wiki/ 任意子目录找不到 X.md
echo "--- 断链（被链接但不存在的页面） ---"
_TMP_BROKEN=$(mktemp)
grep -rohE "\[\[[^]]+\]\]" "$WIKI_DIR" 2>/dev/null | \
  sed -e 's/\[\[//g' -e 's/\]\]//g' -e 's/|.*//' | \
  sort -u | \
  while read -r LINK; do
    [ -z "$LINK" ] && continue
    if ! find "$WIKI_DIR" -name "$LINK.md" 2>/dev/null | grep -q .; then
      echo "  断链: [[$LINK]]"
      echo "$LINK" >> "$_TMP_BROKEN"
    fi
  done
if [ ! -s "$_TMP_BROKEN" ]; then
  echo "  （无断链）"
fi
rm -f "$_TMP_BROKEN"
echo ""

# 检查 3：index 一致性
# 定义：index.md 里有 [[X]] 记录（去掉别名），但 wiki/ 任意子目录都找不到 X.md
echo "--- index 一致性（index.md 有记录但文件缺失） ---"
_TMP_MISSING=$(mktemp)
grep -ohE "\[\[[^]]+\]\]" "$INDEX_FILE" 2>/dev/null | \
  sed -e 's/\[\[//g' -e 's/\]\]//g' -e 's/|.*//' | \
  sort -u | \
  while read -r ENTRY; do
    [ -z "$ENTRY" ] && continue
    if ! find "$WIKI_DIR" -name "$ENTRY.md" 2>/dev/null | grep -q .; then
      echo "  index 有但文件缺失: $ENTRY"
      echo "$ENTRY" >> "$_TMP_MISSING"
    fi
  done
if [ ! -s "$_TMP_MISSING" ]; then
  echo "  （index 与文件一致）"
fi
rm -f "$_TMP_MISSING"
echo ""

# 检查 4：反向 index 一致性
# 定义：wiki/ 下实际存在的页面，但 index.md 里没有 [[页面名]] 记录
# 排除 derived 页面（queries/、synthesis/sessions/）
echo "--- 反向 index 一致性（文件存在但 index.md 未收录） ---"
_TMP_UNLISTED=$(mktemp)
for _subdir in entities topics sources comparisons synthesis; do
  for f in "$WIKI_DIR"/$_subdir/*.md; do
    [ -f "$f" ] || continue
    BASENAME=$(basename "$f" .md)
    # 跳过 derived 页面
    case "$f" in
      */queries/*|*/sessions/*) continue ;;
    esac
    if ! index_has_entry "$BASENAME"; then
      echo "  未收录: $_subdir/$BASENAME"
      echo "$BASENAME" >> "$_TMP_UNLISTED"
    fi
  done
done
if [ ! -s "$_TMP_UNLISTED" ]; then
  echo "  （所有页面均已收录）"
fi
rm -f "$_TMP_UNLISTED"
echo ""

# 检查 5：图片资产一致性
# 定义：source 页面 frontmatter 中 image_paths 列出的文件，在知识库中是否实际存在
# 支持 block list 格式和 inline array 格式
echo "--- 图片资产一致性（image_paths 声明但文件缺失） ---"
_IMG_ISSUES=0
for f in "$WIKI_DIR"/sources/*.md; do
  [ -f "$f" ] || continue
  _BASENAME=$(basename "$f" .md)
  # 提取 frontmatter 中 image_paths 的值
  _IN_FM=false
  _IN_IMG=false
  _INLINE_VAL=""
  while IFS= read -r line; do
    case "$line" in
      "---")
        if [ "$_IN_FM" = true ]; then break; fi
        _IN_FM=true
        continue
        ;;
    esac
    [ "$_IN_FM" = true ] || continue
    case "$line" in
      image_paths:*)
        # 检查是否有 inline value（如 image_paths: ["a.png", "b.jpg"]）
        _INLINE_VAL=$(echo "$line" | sed 's/^image_paths:[[:space:]]*//')
        if [ -n "$_INLINE_VAL" ] && [ "$_INLINE_VAL" != "[]" ]; then
          # 解析 inline array：去掉 []，按逗号分割
          echo "$_INLINE_VAL" | tr -d '[]' | tr ',' '\n' | while IFS= read -r _ITEM; do
            _PATH=$(echo "$_ITEM" | sed 's/^[[:space:]]*//' | sed 's/[[:space:]]*$//' | tr -d '"' | tr -d "'")
            [ -z "$_PATH" ] && continue
            if [ ! -f "$WIKI_ROOT/$_PATH" ]; then
              echo "  缺失: $_BASENAME → $_PATH"
            fi
          done
          _INLINE_COUNT=$(echo "$_INLINE_VAL" | tr -d '[]' | tr ',' '\n' | while IFS= read -r _ITEM; do
            _P=$(echo "$_ITEM" | sed 's/^[[:space:]]*//' | sed 's/[[:space:]]*$//' | tr -d '"' | tr -d "'")
            [ -z "$_P" ] && continue
            [ ! -f "$WIKI_ROOT/$_P" ] && echo "x"
          done | wc -l | tr -d ' ')
          _IMG_ISSUES=$((_IMG_ISSUES + _INLINE_COUNT))
          _IN_IMG=false
        else
          _IN_IMG=true
        fi
        continue
        ;;
      "  - "*)
        if [ "$_IN_IMG" = true ]; then
          _PATH=$(echo "$line" | sed 's/^[[:space:]]*- //' | sed 's/^[[:space:]]*//' | sed 's/[[:space:]]*$//' | tr -d '"' | tr -d "'")
          [ -z "$_PATH" ] && continue
          if [ ! -f "$WIKI_ROOT/$_PATH" ]; then
            echo "  缺失: $_BASENAME → $_PATH"
            _IMG_ISSUES=$((_IMG_ISSUES + 1))
          fi
        fi
        ;;
      *) _IN_IMG=false ;;
    esac
  done < "$f"
done
[ "$_IMG_ISSUES" -eq 0 ] && echo "  （无缺失图片）"
echo ""

# 检查 6：source-signal 覆盖情况
echo "--- source-signal 覆盖情况 ---"
_COVERAGE_SCRIPT="$(cd "$(dirname "$0")" && pwd)/source-signal-coverage.js"
if [ -f "$_COVERAGE_SCRIPT" ] && command -v node >/dev/null 2>&1; then
  _COVERAGE_JSON=$(node "$_COVERAGE_SCRIPT" "$WIKI_ROOT" 2>/dev/null)
  if [ $? -eq 0 ] && [ -n "$_COVERAGE_JSON" ]; then
    node -e '
      const data = JSON.parse(require("fs").readFileSync("/dev/stdin", "utf8"));
      const s = data.summary;
      console.log("  已参与：" + s.ok);
      console.log("  缺少 sources 字段：" + s.missing_sources);
      console.log("  sources 为空：" + s.empty_sources);
      console.log("  sources 格式无效：" + s.invalid_sources);
      console.log("  当前不参与：" + s.not_applicable);
      const issues = data.pages.filter(p => p.reason !== "ok" && p.reason !== "not_applicable");
      if (issues.length > 0) {
        const byReason = { missing_sources: [], empty_sources: [], invalid_sources: [] };
        for (const p of issues) { if (byReason[p.reason]) byReason[p.reason].push(p.path); }
        for (const [reason, paths] of Object.entries(byReason)) {
          if (paths.length === 0) continue;
          const label = { missing_sources: "缺少 sources 字段", empty_sources: "sources 为空", invalid_sources: "sources 格式无效" }[reason];
          console.log("");
          console.log("  " + label + "：");
          for (const p of paths) console.log("  - " + p);
        }
      }
    ' <<< "$_COVERAGE_JSON"
  else
    echo "  （coverage 脚本执行失败，跳过覆盖检查）"
  fi
else
  echo "  （coverage 脚本或 node 不可用，跳过覆盖检查）"
fi
echo ""

echo "=== 机械检查完成。矛盾检测、交叉引用、置信度抽查由 AI 继续执行 ==="
exit 0
