#!/bin/bash
# llm-wiki source 页面写入脚本
# 原子写入 source 页面 + 自动更新缓存，绑定为一项操作

set -euo pipefail

usage() {
  cat <<'EOF'
用法：
  bash scripts/create-source-page.sh <raw_file> <output_path> <content_file>

参数：
  raw_file     : 原始素材文件路径（绝对或相对路径）
  output_path  : 目标页面路径（相对于知识库根目录，如 wiki/sources/2026-04-16-rlhf.md）
  content_file : 包含待写入内容的临时文件路径
EOF
}

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 参数校验
if [ "$#" -ne 3 ]; then
  usage
  exit 1
fi

raw_file="$1"
output_path="$2"
content_file="$3"

# raw_file 和 content_file 必须存在
if [ ! -f "$raw_file" ]; then
  echo "ERROR: 原始素材文件不存在：$raw_file" >&2
  exit 1
fi

if [ ! -f "$content_file" ]; then
  echo "ERROR: 内容文件不存在：$content_file" >&2
  exit 1
fi

# 通过 cache.sh 的 find_wiki_root 逻辑找到知识库根目录
# 复用 cache.sh 里的函数
source_cache_helpers() {
  # 内联 find_wiki_root（与 cache.sh 保持一致）
  find_wiki_root() {
    local file_path="$1"
    local dir parent

    dir="$(cd "$(dirname "$file_path")" && pwd)"

    while true; do
      if [ -f "$dir/.wiki-cache.json" ] || [ -f "$dir/.wiki-schema.md" ]; then
        printf '%s\n' "$dir"
        return 0
      fi

      parent="$(dirname "$dir")"
      [ "$parent" = "$dir" ] && return 1
      dir="$parent"
    done
  }
}

source_cache_helpers

wiki_root="$(find_wiki_root "$raw_file")" || {
  echo "ERROR: 未找到知识库根目录：$raw_file" >&2
  exit 1
}

# 拼接完整目标路径
full_output="$wiki_root/$output_path"

# 确保目标目录存在
mkdir -p "$(dirname "$full_output")"

# 第一步：原子写入（临时文件 + rename，防止写一半崩溃）
tmp_output="${full_output}.tmp.$$"
if ! cp "$content_file" "$tmp_output"; then
  rm -f "$tmp_output" 2>/dev/null || true
  echo "ERROR: 写入临时文件失败" >&2
  exit 1
fi

if ! mv "$tmp_output" "$full_output"; then
  rm -f "$tmp_output" 2>/dev/null || true
  echo "ERROR: 原子重命名失败" >&2
  exit 1
fi

# 第二步：更新缓存
if ! bash "$SCRIPT_DIR/cache.sh" update "$raw_file" "$output_path"; then
  # 缓存更新失败 → 回滚：删除已写入的文件
  rm -f "$full_output"
  echo "ERROR: 缓存更新失败，已回滚写入" >&2
  exit 1
fi

echo "SUCCESS"
