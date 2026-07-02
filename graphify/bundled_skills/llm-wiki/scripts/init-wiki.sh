#!/bin/bash
# llm-wiki 初始化脚本
# 自动创建知识库的目录结构
# 用法：bash init-wiki.sh <知识库路径> <主题>

set -e

WIKI_ROOT="${1:-$HOME/Documents/我的知识库}"
TOPIC="${2:-我的知识库}"
LANGUAGE="${3:-中文}"
DATE=$(date +%Y-%m-%d)
SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# 安全的模板变量替换函数（用 perl 替代 sed，避免中文/空格/特殊字符问题）
replace_vars() {
    local input_file="$1"
    local output_file="$2"
    TOPIC_VALUE="$TOPIC" \
    DATE_VALUE="$DATE" \
    WIKI_ROOT_VALUE="$WIKI_ROOT" \
    LANGUAGE_VALUE="$LANGUAGE" \
    perl -pe '
        s/\{\{TOPIC\}\}/$ENV{TOPIC_VALUE}/g;
        s/\{\{DATE\}\}/$ENV{DATE_VALUE}/g;
        s/\{\{WIKI_ROOT\}\}/$ENV{WIKI_ROOT_VALUE}/g;
        s/\{\{LANGUAGE\}\}/$ENV{LANGUAGE_VALUE}/g;
    ' "$input_file" > "$output_file"
}

echo "正在创建知识库..."
echo "   路径：$WIKI_ROOT"
echo "   主题：$TOPIC"
echo "   语言：$LANGUAGE"
echo ""

# 创建目录结构（包含小红书和知乎）
mkdir -p "$WIKI_ROOT"/raw/{articles,tweets,wechat,xiaohongshu,zhihu,pdfs,notes,assets}
mkdir -p "$WIKI_ROOT"/wiki/{entities,topics,sources,comparisons,synthesis,synthesis/sessions,queries}

cat > "$WIKI_ROOT/.gitignore" <<'EOF'
.wiki-tmp/
EOF

echo "[完成] 目录结构已创建"

# 从模板生成文件
replace_vars "$SKILL_DIR/templates/schema-template.md" "$WIKI_ROOT/.wiki-schema.md"
echo "[完成] Schema 文件已生成"

replace_vars "$SKILL_DIR/templates/index-template.md" "$WIKI_ROOT/index.md"
echo "[完成] 索引文件已生成"

replace_vars "$SKILL_DIR/templates/log-template.md" "$WIKI_ROOT/log.md"
echo "[完成] 日志文件已生成"

replace_vars "$SKILL_DIR/templates/overview-template.md" "$WIKI_ROOT/wiki/overview.md"
echo "[完成] 总览文件已生成"

if [ "$LANGUAGE" = "English" ]; then
    replace_vars "$SKILL_DIR/templates/purpose-en-template.md" "$WIKI_ROOT/purpose.md"
else
    replace_vars "$SKILL_DIR/templates/purpose-template.md" "$WIKI_ROOT/purpose.md"
fi
echo "[完成] 研究方向文件已生成"

cat > "$WIKI_ROOT/.wiki-cache.json" <<'EOF'
{
  "version": 1,
  "entries": {}
}
EOF
echo "[完成] 缓存文件已生成"

echo ""
echo "知识库创建完成！"
echo ""
echo "目录结构："
echo "   $WIKI_ROOT/"
echo "   ├── raw/        （原始素材）"
echo "   │   ├── articles/     网页文章"
echo "   │   ├── tweets/       X/Twitter"
echo "   │   ├── wechat/       微信公众号"
echo "   │   ├── xiaohongshu/  小红书"
echo "   │   ├── zhihu/        知乎"
echo "   │   ├── pdfs/         PDF"
echo "   │   ├── notes/        笔记"
echo "   │   └── assets/       图片等附件"
echo "   ├── wiki/       （知识库）"
echo "   ├── index.md    （索引）"
echo "   ├── log.md      （日志）"
echo "   ├── purpose.md  （研究方向）"
echo "   ├── .wiki-cache.json （缓存）"
echo "   └── .wiki-schema.md （配置）"
echo ""
echo "下一步：给 agent 一个链接或文件，开始构建知识库！"
