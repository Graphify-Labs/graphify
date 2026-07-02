#!/bin/bash
# build-graph-data.sh — 扫描 wiki/ 生成交互式图谱所需的 graph-data.json
#
# 用法：bash scripts/build-graph-data.sh <wiki_root> [output_path]
#   wiki_root     包含 wiki/ 子目录的知识库根路径
#   output_path   可选，默认 <wiki_root>/wiki/graph-data.json
#
# 环境变量：
#   LLM_WIKI_TEST_MODE=1   启用稳定输出（nodes/edges 按 id 字典序 + 时间戳固定）
#
# 退出码：0 成功；1 路径/依赖错误；2 wiki 结构不完整

set -eu
shopt -s nullglob

SCRIPT_DIR="${BASH_SOURCE[0]%/*}"
[ "$SCRIPT_DIR" = "${BASH_SOURCE[0]}" ] && SCRIPT_DIR="."
SCRIPT_DIR="$(cd "$SCRIPT_DIR" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/shared-config.sh"

WIKI_ROOT="${1:-.}"
DEFAULT_OUTPUT="$WIKI_ROOT/wiki/graph-data.json"
OUTPUT="${2:-$DEFAULT_OUTPUT}"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
HELPER="$SKILL_DIR/scripts/graph-analysis.js"
MAX_CONTENT_BYTES=$((2 * 1024 * 1024))
MAX_CONTENT_LINES=500
MAX_INSIGHT_NODES=250
MAX_INSIGHT_EDGES=1000

command -v jq >/dev/null 2>&1 || {
  echo "ERROR: jq is not installed. Install it via:" >&2
  print_install_hint jq
  exit 1
}

command -v node >/dev/null 2>&1 || {
  echo "ERROR: node is not installed. Install it via:" >&2
  print_install_hint node
  exit 1
}

[ -f "$HELPER" ] || {
  echo "ERROR: 找不到图谱分析 helper：$HELPER" >&2
  echo "       重装 skill 可修复（bash install.sh --platform claude）" >&2
  exit 1
}

WIKI_DIR="$WIKI_ROOT/wiki"
[ -d "$WIKI_DIR" ] || {
  echo "ERROR: wiki 目录不存在：$WIKI_DIR" >&2
  echo "       请先运行 init-wiki.sh 初始化知识库。" >&2
  exit 2
}
WIKI_ROOT_ABS="$(cd "$WIKI_ROOT" && pwd)"

TMPDIR=$(mktemp -d -t llm-wiki-graph.XXXXXX)
trap 'rm -rf "$TMPDIR"' EXIT

if [ "${LLM_WIKI_TEST_MODE:-0}" = "1" ]; then
  BUILD_DATE="2026-01-01T00:00:00Z"
else
  BUILD_DATE="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
fi

WIKI_TITLE=""
if [ -f "$WIKI_ROOT/purpose.md" ]; then
  WIKI_TITLE=$(awk '/^# / { sub(/^# +/, ""); print; exit }' "$WIKI_ROOT/purpose.md")
fi
[ -n "$WIKI_TITLE" ] || WIKI_TITLE=$(basename "$(cd "$WIKI_ROOT" && pwd)")

NODES_TSV="$TMPDIR/nodes.tsv"
: > "$NODES_TSV"

scan_kind() {
  local subdir="$1" type="$2"
  local dir="$WIKI_DIR/$subdir"
  [ -d "$dir" ] || return 0
  local f id label
  while IFS= read -r f; do
    [ -f "$f" ] || continue
    id=$(basename "$f" .md)
    case "$id" in
      index|log|purpose|.wiki-schema|README) continue ;;
    esac
    label=$(awk '/^# / { sub(/^# +/, ""); gsub(/[[:space:]]+$/, ""); print; exit }' "$f")
    [ -n "$label" ] || label="$id"
    printf '%s\t%s\t%s\t%s\n' "$id" "$label" "$type" "$f" >> "$NODES_TSV"
  done < <(find "$dir" -type f -name '*.md' | LC_ALL=C sort)
}

scan_kind entities entity
scan_kind topics topic
scan_kind sources source
scan_kind comparisons comparison
scan_kind synthesis synthesis
scan_kind queries query

if [ ! -s "$NODES_TSV" ]; then
  mkdir -p "$(dirname "$OUTPUT")"
  OUTPUT_TMP="$TMPDIR/graph-data.empty.json"
  jq -n \
    --arg build_date "$BUILD_DATE" \
    --arg wiki_title "$WIKI_TITLE" \
    '{
      meta: {
        build_date: $build_date,
        wiki_title: $wiki_title,
        total_nodes: 0,
        total_edges: 0,
        initial_view: [],
        degraded: false,
        insights_degraded: false
      },
      nodes: [],
      edges: [],
      insights: {
        surprising_connections: [],
        isolated_nodes: [],
        bridge_nodes: [],
        sparse_communities: [],
        meta: {
          degraded: false,
          node_count: 0,
          edge_count: 0,
          max_insight_nodes: 250,
          max_insight_edges: 1000
        }
      },
      learning: {
        version: 1,
        entry: {
          recommended_start_node_id: null,
          recommended_start_reason: null,
          default_mode: "global"
        },
        views: {
          path: { enabled: false, start_node_id: null, node_ids: [], degraded: true },
          community: { enabled: false, community_id: null, label: null, node_ids: [], is_weak: false, degraded: true },
          global: { enabled: true, node_ids: [], degraded: false }
        },
        communities: [],
        degraded: { path_to_community: true, community_to_global: true }
      }
    }' > "$OUTPUT_TMP"
  mv "$OUTPUT_TMP" "$OUTPUT"
  echo "空图谱已写入：${OUTPUT}（wiki/ 下无可纳入节点）"
  exit 0
fi

EDGES_RAW="$TMPDIR/edges_raw.tsv"
: > "$EDGES_RAW"

while IFS=$'\t' read -r id label type path; do
  awk -v src="$id" '
    {
      line = $0
      conf = ""
      rel = ""
      if (match(line, /<!--[[:space:]]*confidence:[[:space:]]*[A-Z]+[[:space:]]*-->/)) {
        kind_str = substr(line, RSTART, RLENGTH)
        if (match(kind_str, /[A-Z]+/)) {
          conf = substr(kind_str, RSTART, RLENGTH)
        }
      }
      if (match(line, /<!--[[:space:]]*relation(_type)?:[[:space:]]*/)) {
        rel_str = substr(line, RSTART + RLENGTH)
        rel_end = index(rel_str, "-->")
        if (rel_end > 0) {
          rel = substr(rel_str, 1, rel_end - 1)
          gsub(/^[[:space:]]+|[[:space:]]+$/, "", rel)
        }
      }
      rest = line
      while (match(rest, /\[\[[^]]+\]\]/)) {
        inner = substr(rest, RSTART + 2, RLENGTH - 4)
        rest  = substr(rest, RSTART + RLENGTH)
        n = index(inner, "|")
        if (n > 0) inner = substr(inner, 1, n - 1)
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", inner)
        if (inner == "" || inner == src) continue
        print src "\t" NR "\t" inner "\t" conf "\t" rel
      }
    }
  ' "$path" >> "$EDGES_RAW"
done < "$NODES_TSV"

VALID_IDS="$TMPDIR/valid_ids.txt"
cut -f1 "$NODES_TSV" | sort -u > "$VALID_IDS"

EDGES_TSV="$TMPDIR/edges.tsv"
# 合并同一 from+to 的多条 raw edges：
#   - 第一次遇到时记录（有 conf 就用 conf，无 conf 就留空 → 最终默认 EXTRACTED）
#   - 后续遇到带显式 conf 的条目时 **升级**（覆盖之前的空值或 EXTRACTED 默认）
#   - 若后续遇到多条不同的非空 conf，保留首个非空（按首次显式标注优先）
#
# 这解决了"同一对节点被多次 [[]] 引用（正文 + 相关页面列表）时，
#  首次出现的空 conf 会永久锁定 edge type 为 EXTRACTED"的问题。
awk -F'\t' -v valids="$VALID_IDS" '
  BEGIN {
    while ((getline line < valids) > 0) valid[line] = 1
    close(valids)
  }
  {
    from = $1; to = $3; conf = $4; rel = $5
    if (!(to in valid)) next
    if (from == to) next
    key = from "\t" to
    if (!(key in seen)) {
      seen[key] = 1
      saved_conf[key] = conf  # 可能为空，在 END 中兜底为 EXTRACTED
      saved_rel[key] = rel    # 可能为空，在 END 中兜底为依赖
      order[++count] = key
    } else if (conf != "" && saved_conf[key] == "") {
      # 升级：之前未见显式 conf（留空），现在有，采用
      saved_conf[key] = conf
    }
    if (rel != "" && saved_rel[key] == "") {
      # 升级：之前未见显式 relation type，现在有，采用
      saved_rel[key] = rel
    }
  }
  END {
    for (i = 1; i <= count; i++) {
      split(order[i], parts, "\t")
      t = saved_conf[order[i]]
      if (t != "EXTRACTED" && t != "INFERRED" && t != "AMBIGUOUS") t = "EXTRACTED"
      r = saved_rel[order[i]]
      if (r == "") r = "依赖"
      print parts[1] "\t" parts[2] "\t" t "\t" r
    }
  }
' "$EDGES_RAW" > "$EDGES_TSV"

TOTAL_SIZE=0
while IFS=$'\t' read -r id label type path; do
  sz=$(wc -c < "$path" 2>/dev/null || echo 0)
  TOTAL_SIZE=$((TOTAL_SIZE + sz))
done < "$NODES_TSV"

DEGRADE=0
if [ "$TOTAL_SIZE" -gt "$MAX_CONTENT_BYTES" ]; then
  DEGRADE=1
fi

NODES_JSONL="$TMPDIR/nodes.jsonl"
: > "$NODES_JSONL"
while IFS=$'\t' read -r id label type path; do
  abs_path=$(cd "$(dirname "$path")" && pwd)/$(basename "$path")
  rel_path="${abs_path#"$WIKI_ROOT_ABS"/}"
  jq -n \
    --arg id "$id" \
    --arg label "$label" \
    --arg type "$type" \
    --arg source_path "$abs_path" \
    --arg rel_path "$rel_path" \
    '{
      id: $id,
      label: $label,
      type: $type,
      source_path: $rel_path,
      _file_path: $source_path
    }' >> "$NODES_JSONL"
done < "$NODES_TSV"

EDGES_JSONL="$TMPDIR/edges.jsonl"
: > "$EDGES_JSONL"
idx=0
while IFS=$'\t' read -r from to etype relation_type; do
  idx=$((idx + 1))
  jq -n \
    --arg id "e$idx" \
    --arg from "$from" \
    --arg to "$to" \
    --arg etype "$etype" \
    --arg relation_type "$relation_type" \
    '{id: $id, from: $from, to: $to, type: $etype, confidence: $etype, relation_type: $relation_type}' >> "$EDGES_JSONL"
done < "$EDGES_TSV"

if [ "${LLM_WIKI_TEST_MODE:-0}" = "1" ]; then
  jq -s 'sort_by(.id)' "$NODES_JSONL" > "$TMPDIR/nodes.raw.json"
  jq -s 'sort_by(.from, .to, .type)
         | to_entries
         | map(.value + {id: ("e" + ((.key + 1) | tostring))})' \
    "$EDGES_JSONL" > "$TMPDIR/edges.raw.json"
else
  jq -s '.' "$NODES_JSONL" > "$TMPDIR/nodes.raw.json"
  jq -s '.' "$EDGES_JSONL" > "$TMPDIR/edges.raw.json"
fi

ANALYSIS_JSON="$TMPDIR/analysis.json"
if ! node "$HELPER" \
  "$TMPDIR/nodes.raw.json" \
  "$TMPDIR/edges.raw.json" \
  "$ANALYSIS_JSON" \
  "$DEGRADE" \
  "$MAX_CONTENT_LINES" \
  "$MAX_INSIGHT_NODES" \
  "$MAX_INSIGHT_EDGES"; then
  echo "ERROR: 图谱分析 helper 执行失败：$HELPER" >&2
  exit 1
fi

jq -e '
  (.nodes | type) == "array" and
  (.edges | type) == "array" and
  (.insights | type) == "object" and
  (.insights.surprising_connections | type) == "array" and
  (.insights.isolated_nodes | type) == "array" and
  (.insights.bridge_nodes | type) == "array" and
  (.insights.sparse_communities | type) == "array" and
  (.learning | type) == "object"
' "$ANALYSIS_JSON" > /dev/null 2>&1 || {
  echo "ERROR: 图谱分析 helper 返回坏 JSON：$ANALYSIS_JSON" >&2
  exit 1
}

if [ "${LLM_WIKI_TEST_MODE:-0}" = "1" ]; then
  jq '.nodes | sort_by(.id)' "$ANALYSIS_JSON" > "$TMPDIR/nodes.sorted.json"
  jq '.edges | sort_by(.from, .to, .type)
       | to_entries
       | map(.value + {id: ("e" + ((.key + 1) | tostring))})' "$ANALYSIS_JSON" > "$TMPDIR/edges.sorted.json"
else
  jq '.nodes' "$ANALYSIS_JSON" > "$TMPDIR/nodes.sorted.json"
  jq '.edges' "$ANALYSIS_JSON" > "$TMPDIR/edges.sorted.json"
fi

INITIAL_VIEW=$(jq \
  --argjson nodes "$(cat "$TMPDIR/nodes.sorted.json")" \
  '
  . as $edges
  | (
      reduce $edges[] as $e (
        {};
        .[$e.from] = (.[$e.from] // 0) + 1 |
        .[$e.to] = (.[$e.to] // 0) + 1
      )
    ) as $deg
  | ($nodes | group_by(.community // "_")) as $groups
  | ([ $groups[] | max_by(($deg[.id] // 0)) | .id ]) as $reps
  | (
      $nodes
      | sort_by(- ($deg[.id] // 0))
      | map(.id)
      | map(select(. as $x | $reps | index($x) | not))
    ) as $rest
  | ($reps + $rest)[0:30]
  ' \
  "$TMPDIR/edges.sorted.json")

NODE_COUNT=$(jq 'length' "$TMPDIR/nodes.sorted.json")
EDGE_COUNT=$(jq 'length' "$TMPDIR/edges.sorted.json")
INSIGHTS_DEGRADED=$(jq '.insights.meta.degraded == true' "$ANALYSIS_JSON")

mkdir -p "$(dirname "$OUTPUT")"
OUTPUT_TMP="$TMPDIR/graph-data.final.json"

jq -n \
  --arg build_date "$BUILD_DATE" \
  --arg wiki_title "$WIKI_TITLE" \
  --argjson total_nodes "$NODE_COUNT" \
  --argjson total_edges "$EDGE_COUNT" \
  --argjson initial_view "$INITIAL_VIEW" \
  --argjson nodes "$(cat "$TMPDIR/nodes.sorted.json")" \
  --argjson edges "$(cat "$TMPDIR/edges.sorted.json")" \
  --argjson insights "$(jq '.insights' "$ANALYSIS_JSON")" \
  --argjson learning "$(jq '.learning' "$ANALYSIS_JSON")" \
  --argjson degraded "$DEGRADE" \
  --argjson insights_degraded "$INSIGHTS_DEGRADED" \
  '{
    meta: {
      build_date: $build_date,
      wiki_title: $wiki_title,
      total_nodes: $total_nodes,
      total_edges: $total_edges,
      initial_view: $initial_view,
      degraded: ($degraded == 1),
      insights_degraded: $insights_degraded
    },
    nodes: $nodes,
    edges: $edges,
    insights: $insights,
    learning: $learning
  }' > "$OUTPUT_TMP"

mv "$OUTPUT_TMP" "$OUTPUT"

echo "图谱数据已生成：$OUTPUT"
echo "  节点：$NODE_COUNT"
echo "  关联：$EDGE_COUNT"
echo "  初始视图：$(echo "$INITIAL_VIEW" | jq 'length') 个节点"
[ "$DEGRADE" = "1" ] && echo "  ⚠ 降级模式：内嵌内容 > 2MB，每节点仅保留前 ${MAX_CONTENT_LINES} 行"
[ "$INSIGHTS_DEGRADED" = "true" ] && echo "  ⚠ 洞察降级：图规模超出预算，仅保留基础权重与社区"
exit 0
