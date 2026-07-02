#!/bin/bash
# 验证 ingest Step 1 的 JSON 输出格式
# 用法：bash validate-step1.sh <json_file>
# 返回：0 = 格式正确，1 = 格式有问题（触发回退）

SCRIPT_DIR="${BASH_SOURCE[0]%/*}"
[ "$SCRIPT_DIR" = "${BASH_SOURCE[0]}" ] && SCRIPT_DIR="."
SCRIPT_DIR="$(cd "$SCRIPT_DIR" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/shared-config.sh"

JSON_FILE="$1"

# 参数检查
[ -z "$1" ] && { echo "ERROR: usage: validate-step1.sh <json_file>"; exit 1; }

# 检查 jq 是否可用（必需依赖）
command -v jq >/dev/null 2>&1 || {
  echo "ERROR: jq is not installed. Install it via:" >&2
  print_install_hint jq
  exit 1
}

# 检查文件是否存在
[ -f "$JSON_FILE" ] || { echo "ERROR: file not found: $JSON_FILE"; exit 1; }

# 检查是否是有效 JSON
jq empty "$JSON_FILE" 2>/dev/null || { echo "ERROR: invalid JSON format"; exit 1; }

# 检查必需字段存在且类型正确
jq -e '.entities | type == "array"' "$JSON_FILE" >/dev/null 2>&1 || { echo "ERROR: 'entities' must be an array"; exit 1; }
jq -e '.topics | type == "array"' "$JSON_FILE" >/dev/null 2>&1 || { echo "ERROR: 'topics' must be an array"; exit 1; }
jq -e '.connections | type == "array"' "$JSON_FILE" >/dev/null 2>&1 || { echo "ERROR: 'connections' must be an array"; exit 1; }
jq -e '.contradictions | type == "array"' "$JSON_FILE" >/dev/null 2>&1 || { echo "ERROR: 'contradictions' must be an array"; exit 1; }
jq -e '.new_vs_existing | type == "object"' "$JSON_FILE" >/dev/null 2>&1 || { echo "ERROR: 'new_vs_existing' must be an object"; exit 1; }

# 检查每个 entity 的必需子字段
VALID_CONFIDENCE="EXTRACTED|INFERRED|AMBIGUOUS|UNVERIFIED"

ENTITY_COUNT=$(jq '.entities | length' "$JSON_FILE" 2>/dev/null)
if [ "$ENTITY_COUNT" -gt 0 ] 2>/dev/null; then
    NON_OBJECT_ENTITY_COUNT=$(jq '[.entities[] | select(type != "object")] | length' "$JSON_FILE" 2>/dev/null)
    if [ "$NON_OBJECT_ENTITY_COUNT" -gt 0 ] 2>/dev/null; then
        echo "ERROR: $NON_OBJECT_ENTITY_COUNT entity/entities must be objects"
        exit 1
    fi

    # name, type, confidence 必须存在且非空
    BAD_ENTITY_COUNT=$(jq '
        [.entities[] | select(
            (.name // "" | length) == 0 or
            (.type // "" | length) == 0 or
            (.confidence // "" | length) == 0
        )] | length
    ' "$JSON_FILE" 2>/dev/null)
    if [ "$BAD_ENTITY_COUNT" -gt 0 ] 2>/dev/null; then
        echo "ERROR: $BAD_ENTITY_COUNT entity/entities missing required fields (name/type/confidence)"
        exit 1
    fi

    # confidence 值必须是四个有效值之一
    INVALID=$(jq -r '.entities[]? | (.confidence // "MISSING")' "$JSON_FILE" 2>/dev/null | \
        grep -v -E "^($VALID_CONFIDENCE)$" | head -3)
    if [ -n "$INVALID" ]; then
        echo "ERROR: invalid entity confidence value(s): $INVALID"
        echo "       Valid values: EXTRACTED | INFERRED | AMBIGUOUS | UNVERIFIED"
        exit 1
    fi

    # EXTRACTED 和 INFERRED 必须提供 evidence 字段
    NO_EVIDENCE_COUNT=$(jq '
        [.entities[] | select(
            (.confidence == "EXTRACTED" or .confidence == "INFERRED") and
            ((.evidence // "" | length) == 0)
        )] | length
    ' "$JSON_FILE" 2>/dev/null)
    if [ "$NO_EVIDENCE_COUNT" -gt 0 ] 2>/dev/null; then
        echo "WARN: $NO_EVIDENCE_COUNT entity/entities with EXTRACTED/INFERRED confidence missing 'evidence' field"
    fi
fi

# 检查每个 topic 的必需子字段
TOPIC_COUNT=$(jq '.topics | length' "$JSON_FILE" 2>/dev/null)
if [ "$TOPIC_COUNT" -gt 0 ] 2>/dev/null; then
    NON_OBJECT_TOPIC_COUNT=$(jq '[.topics[] | select(type != "object")] | length' "$JSON_FILE" 2>/dev/null)
    if [ "$NON_OBJECT_TOPIC_COUNT" -gt 0 ] 2>/dev/null; then
        echo "ERROR: $NON_OBJECT_TOPIC_COUNT topic(s) must be objects"
        exit 1
    fi

    BAD_TOPIC_COUNT=$(jq '
        [.topics[] | select(
            (.name // "" | length) == 0
        )] | length
    ' "$JSON_FILE" 2>/dev/null)
    if [ "$BAD_TOPIC_COUNT" -gt 0 ] 2>/dev/null; then
        echo "ERROR: $BAD_TOPIC_COUNT topic(s) missing required 'name' field"
        exit 1
    fi
fi

# 检查每个 connection 的必需子字段（from, to, confidence）
CONN_COUNT=$(jq '.connections | length' "$JSON_FILE" 2>/dev/null)
if [ "$CONN_COUNT" -gt 0 ] 2>/dev/null; then
    NON_OBJECT_CONN_COUNT=$(jq '[.connections[] | select(type != "object")] | length' "$JSON_FILE" 2>/dev/null)
    if [ "$NON_OBJECT_CONN_COUNT" -gt 0 ] 2>/dev/null; then
        echo "ERROR: $NON_OBJECT_CONN_COUNT connection(s) must be objects"
        exit 1
    fi

    BAD_CONN_COUNT=$(jq '
        [.connections[] | select(
            (.from // "" | length) == 0 or
            (.to // "" | length) == 0 or
            (.confidence // "" | length) == 0
        )] | length
    ' "$JSON_FILE" 2>/dev/null)
    if [ "$BAD_CONN_COUNT" -gt 0 ] 2>/dev/null; then
        echo "ERROR: $BAD_CONN_COUNT connection(s) missing required fields (from/to/confidence)"
        exit 1
    fi

    INVALID_CONN_CONF=$(jq -r '.connections[]? | (.confidence // "MISSING")' "$JSON_FILE" 2>/dev/null | \
        grep -v -E "^($VALID_CONFIDENCE)$" | head -3)
    if [ -n "$INVALID_CONN_CONF" ]; then
        echo "ERROR: invalid connection confidence value(s): $INVALID_CONN_CONF"
        echo "       Valid values: EXTRACTED | INFERRED | AMBIGUOUS | UNVERIFIED"
        exit 1
    fi

    # EXTRACTED 和 INFERRED connections 必须提供 evidence
    NO_CONN_EVIDENCE=$(jq '
        [.connections[] | select(
            (.confidence == "EXTRACTED" or .confidence == "INFERRED") and
            ((.evidence // "" | length) == 0)
        )] | length
    ' "$JSON_FILE" 2>/dev/null)
    if [ "$NO_CONN_EVIDENCE" -gt 0 ] 2>/dev/null; then
        echo "WARN: $NO_CONN_EVIDENCE connection(s) with EXTRACTED/INFERRED confidence missing 'evidence' field"
    fi
fi

echo "OK: Step 1 JSON validation passed"
exit 0
