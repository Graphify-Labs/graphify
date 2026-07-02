#!/bin/bash
# build-graph-html.sh — 生成共享 graph-engine 驱动的离线知识图谱 HTML
#
# 用法：
#   bash scripts/build-graph-html.sh <wiki_root>
#
# 前置：需要先运行 build-graph-data.sh 生成 wiki/graph-data.json
#
# 行为：
#   1. 读取 packages/graph-engine/dist/engine.iife.js
#   2. 内嵌 graph-data.json 与可选 .wiki-graph-layout.json 钉位
#   3. 注入离线启动脚本：创建 graph engine，持久化钉位到 localStorage
#   4. 生成单文件 knowledge-graph.html
#
# 退出码：0 成功；1 依赖/文件缺失/参数错误

set -eu

SCRIPT_DIR="${BASH_SOURCE[0]%/*}"
[ "$SCRIPT_DIR" = "${BASH_SOURCE[0]}" ] && SCRIPT_DIR="."
SCRIPT_DIR="$(cd "$SCRIPT_DIR" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/shared-config.sh"

print_usage() {
  cat <<'USAGE'
用法：
  bash scripts/build-graph-html.sh <wiki_root>

示例：
  bash scripts/build-graph-html.sh /path/to/wiki-root
USAGE
}

die() {
  echo "ERROR: $1" >&2
  exit 1
}

ensure_file() {
  local file="$1"
  local label="${2:-文件}"
  [ -f "$file" ] || {
    echo "ERROR: 找不到${label} $file" >&2
    echo "       请先运行 npm run build -w @llm-wiki/graph-engine，或重装 skill。" >&2
    exit 1
  }
}

json_for_script() {
  perl -pe 's|</script>|<\\/script>|gi' "$1"
}

script_for_inline() {
  perl -pe 's|//# sourceMappingURL=.*$||' "$1"
}

html_escape_text() {
  printf '%s' "$1" | perl -pe 's/&/&amp;/g; s/</&lt;/g; s/>/&gt;/g; s/"/&quot;/g; s/'"'"'/&#39;/g'
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    -h|--help)
      print_usage
      exit 0
      ;;
    --)
      shift
      break
      ;;
    -*)
      die "未知选项: $1"
      ;;
    *)
      break
      ;;
  esac
done

[ "$#" -eq 1 ] || {
  print_usage >&2
  exit 1
}

WIKI_ROOT="$1"

command -v jq >/dev/null 2>&1 || {
  echo "ERROR: jq is not installed. Install it via:" >&2
  print_install_hint jq
  exit 1
}

SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DATA="$WIKI_ROOT/wiki/graph-data.json"
LAYOUT="$WIKI_ROOT/.wiki-graph-layout.json"
ENGINE="$SKILL_DIR/packages/graph-engine/dist/engine.iife.js"
MARKED="$SKILL_DIR/deps/marked.min.js"
PURIFY="$SKILL_DIR/deps/purify.min.js"
OUTPUT="$WIKI_ROOT/wiki/knowledge-graph.html"

[ -f "$DATA" ] || {
  echo "ERROR: 未找到 $DATA" >&2
  echo "       请先运行 build-graph-data.sh 生成图谱数据" >&2
  exit 1
}
ensure_file "$ENGINE" "graph-engine IIFE 产物"
ensure_file "$MARKED" "marked vendor"
ensure_file "$PURIFY" "purify vendor"

WIKI_TITLE=$(jq -r '.meta.wiki_title // "知识库"' "$DATA")
NODE_COUNT=$(jq -r '.meta.total_nodes // 0' "$DATA")
EDGE_COUNT=$(jq -r '.meta.total_edges // 0' "$DATA")
BUILD_DATE=$(jq -r '.meta.build_date // ""' "$DATA")
BUILD_DATE_SHORT="${BUILD_DATE:0:10}"
[ -n "$BUILD_DATE_SHORT" ] || BUILD_DATE_SHORT="未知"
WIKI_TITLE_HTML=$(html_escape_text "$WIKI_TITLE")
NODE_COUNT_HTML=$(html_escape_text "$NODE_COUNT")
EDGE_COUNT_HTML=$(html_escape_text "$EDGE_COUNT")
BUILD_DATE_SHORT_HTML=$(html_escape_text "$BUILD_DATE_SHORT")

layout_json='{"version":2,"pins":{},"updatedAt":""}'
if [ -f "$LAYOUT" ]; then
  if layout_json_candidate=$(jq -c '{version:(.version // 1), pins:(.pins // {}), updatedAt:(.updatedAt // "")}' "$LAYOUT" 2>/dev/null); then
    layout_json="$layout_json_candidate"
  else
    echo "WARN: 忽略损坏的钉位文件：$LAYOUT" >&2
  fi
fi

output_dir="$(dirname "$OUTPUT")"
mkdir -p "$output_dir"
output_tmp="$OUTPUT.partial"
output_next="$OUTPUT.next"
rm -f "$output_tmp" "$output_next"

cat > "$output_tmp" <<HTML_HEAD
<!doctype html>
<html lang="zh-Hans">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>知识图谱 · ${WIKI_TITLE_HTML}</title>
  <style>
    :root {
      color-scheme: light;
      --page-bg: #f7f1e5;
      --panel: rgba(255, 252, 244, .86);
      --ink: #2f2924;
      --muted: #766b5f;
      --rule: rgba(79, 64, 46, .2);
      --accent: #a83f35;
    }
    * { box-sizing: border-box; }
    html, body { margin: 0; min-height: 100%; }
    body {
      min-height: 100vh;
      color: var(--ink);
      background: var(--page-bg);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    .offline-shell {
      display: grid;
      grid-template-rows: auto minmax(0, 1fr);
      min-height: 100vh;
    }
    .offline-header {
      position: relative;
      z-index: 20;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      min-height: 64px;
      padding: 12px 18px;
      border-bottom: 1px solid var(--rule);
      background: var(--panel);
      backdrop-filter: blur(10px);
    }
    .offline-title { min-width: 0; }
    .offline-title h1 {
      margin: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-family: Georgia, "Times New Roman", serif;
      font-size: 20px;
      letter-spacing: 0;
    }
    .offline-title p {
      margin: 4px 0 0;
      color: var(--muted);
      font-size: 12px;
    }
    .offline-badges {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: flex-end;
      color: var(--muted);
      font-size: 12px;
    }
    .offline-badges span {
      display: inline-flex;
      align-items: center;
      min-height: 26px;
      padding: 4px 9px;
      border: 1px solid var(--rule);
      border-radius: 999px;
      background: rgba(255, 255, 255, .46);
    }
    .offline-theme-toggle {
      display: inline-flex;
      align-items: center;
      min-height: 26px;
      border: 1px solid var(--rule);
      border-radius: 999px;
      background: rgba(255, 255, 255, .52);
      color: var(--ink);
      padding: 4px 10px;
      font: inherit;
      cursor: pointer;
    }
    .offline-theme-toggle:hover {
      background: rgba(168, 63, 53, .08);
    }
    .offline-toolbar-host {
      position: relative;
      z-index: 5;
      flex: 1 1 320px;
      min-width: 240px;
      min-height: 38px;
    }
    .offline-toolbar-host .graph-toolbar {
      position: static;
      inset: auto;
      justify-items: center;
    }
    .offline-toolbar-host .graph-toolbar-panel {
      position: absolute;
      top: 38px;
      left: 50%;
      transform: translateX(-50%);
    }
    .offline-main {
      position: relative;
      z-index: 1;
      min-height: 0;
      padding: 0;
    }
    #graph-root {
      width: 100%;
      height: 100%;
      min-height: 560px;
    }
    .offline-error {
      margin: 24px;
      padding: 16px;
      border: 1px solid rgba(168, 63, 53, .35);
      border-radius: 8px;
      background: rgba(168, 63, 53, .08);
      color: #7b2b24;
      font-size: 14px;
      line-height: 1.6;
    }
    @media (max-width: 720px) {
      .offline-header { align-items: flex-start; flex-direction: column; }
      .offline-toolbar-host { width: 100%; flex-basis: auto; }
      .offline-toolbar-host .graph-toolbar { justify-items: start; }
      .offline-toolbar-host .graph-toolbar-panel { left: 0; transform: none; }
      .offline-badges { justify-content: flex-start; }
      #graph-root { min-height: 520px; }
    }
  </style>
</head>
<body>
  <div class="offline-shell" data-llm-wiki-offline-graph="engine">
    <header class="offline-header">
      <div class="offline-title">
        <h1>${WIKI_TITLE_HTML} 知识舆图</h1>
        <p>国风知识库·数字山水图</p>
      </div>
      <div class="offline-toolbar-host" data-testid="offline-toolbar-host"></div>
      <div class="offline-badges" aria-label="图谱统计">
        <span>${NODE_COUNT_HTML} 节点</span>
        <span>${EDGE_COUNT_HTML} 关联</span>
        <span>${BUILD_DATE_SHORT_HTML}</span>
        <button class="offline-theme-toggle" type="button" data-testid="offline-theme-toggle" aria-label="切换墨夜主题">墨夜</button>
      </div>
    </header>
    <main class="offline-main">
      <div id="graph-root" data-testid="offline-graph-root"></div>
    </main>
  </div>
  <script id="graph-data" type="application/json">
HTML_HEAD
json_for_script "$DATA" >> "$output_tmp"
cat >> "$output_tmp" <<'HTML_MID'
  </script>
  <script id="graph-layout" type="application/json">
HTML_MID
printf '%s\n' "$layout_json" | perl -pe 's|</script>|<\/script>|gi' >> "$output_tmp"
cat >> "$output_tmp" <<'HTML_ENGINE'
  </script>
  <script>
HTML_ENGINE
script_for_inline "$MARKED" >> "$output_tmp"
printf '\n' >> "$output_tmp"
script_for_inline "$PURIFY" >> "$output_tmp"
printf '\n' >> "$output_tmp"
script_for_inline "$ENGINE" >> "$output_tmp"
cat >> "$output_tmp" <<'HTML_BOOT'
  </script>
  <script>
    (function () {
      var root = document.getElementById("graph-root");
      var toolbarHost = document.querySelector("[data-testid='offline-toolbar-host']");
      var dataEl = document.getElementById("graph-data");
      var layoutEl = document.getElementById("graph-layout");
      function showError(message) {
        if (!root) return;
        root.innerHTML = "";
        var box = document.createElement("div");
        box.className = "offline-error";
        box.textContent = message;
        root.appendChild(box);
      }
      function parseJson(el, fallback) {
        try { return el && el.textContent ? JSON.parse(el.textContent) : fallback; }
        catch (err) { return fallback; }
      }
      function normalizeStorageSegment(value) {
        return String(value == null ? "" : value).trim().toLowerCase()
          .replace(/[^a-z0-9一-鿿]+/g, "-")
          .replace(/^-+|-+$/g, "")
          .slice(0, 48);
      }
      function hashString(value) {
        var input = String(value == null ? "" : value);
        var hash = 0;
        for (var i = 0; i < input.length; i++) {
          hash = ((hash << 5) - hash + input.charCodeAt(i)) >>> 0;
        }
        return hash.toString(36);
      }
      function storageNamespace(meta, pathname) {
        var title = normalizeStorageSegment(meta && meta.wiki_title ? meta.wiki_title : "");
        var basis = typeof pathname === "string" && pathname ? pathname : (meta && meta.wiki_title) || title || "default";
        return "llm-wiki:" + (title || "default") + ":" + hashString(basis);
      }
      function readStoredPins(key) {
        try {
          var raw = window.localStorage && window.localStorage.getItem(key);
          var parsed = raw ? JSON.parse(raw) : null;
          return parsed && typeof parsed === "object" ? parsed : {};
        } catch (_) {
          return {};
        }
      }
      function writeStoredPins(key, pins) {
        try {
          if (window.localStorage) window.localStorage.setItem(key, JSON.stringify(pins || {}));
        } catch (_) {}
      }
      function normalizeBakedPins(layout) {
        return window.LlmWikiGraphEngine.normalizeGraphLayoutFile(layout).pins;
      }
      function normalizeStoredPins(rawPins) {
        return window.LlmWikiGraphEngine.normalizeGraphPinMap(rawPins);
      }
      if (!root || !dataEl || !window.LlmWikiGraphEngine || !window.LlmWikiGraphEngine.createGraphEngine) {
        showError("图谱引擎加载失败。请确认 HTML 文件完整生成。");
        return;
      }
      var graphData = parseJson(dataEl, null);
      if (!graphData || !Array.isArray(graphData.nodes) || !Array.isArray(graphData.edges)) {
        showError("图谱数据格式不完整。请重新运行 build-graph-data.sh 与 build-graph-html.sh。");
        return;
      }
      var bakedLayout = parseJson(layoutEl, { pins: {} });
      var key = storageNamespace(graphData.meta || {}, window.location && window.location.pathname) + ":graph-pins";
      var themeKey = storageNamespace(graphData.meta || {}, window.location && window.location.pathname) + ":graph-theme";
      var pins = Object.assign({}, normalizeBakedPins(bakedLayout), normalizeStoredPins(readStoredPins(key)));
      var themeToggle = document.querySelector("[data-testid='offline-theme-toggle']");
      function readStoredTheme() {
        try {
          var value = window.localStorage && window.localStorage.getItem(themeKey);
          return value === "mo-ye" ? "mo-ye" : "shan-shui";
        } catch (_) {
          return "shan-shui";
        }
      }
      function writeStoredTheme(theme) {
        try {
          if (window.localStorage) window.localStorage.setItem(themeKey, theme);
        } catch (_) {}
      }
      function syncThemeToggle(theme) {
        if (!themeToggle) return;
        var next = theme === "mo-ye" ? "shan-shui" : "mo-ye";
        themeToggle.textContent = theme === "mo-ye" ? "山水" : "墨夜";
        themeToggle.setAttribute("aria-label", next === "mo-ye" ? "切换墨夜主题" : "切换山水主题");
      }
      var currentTheme = readStoredTheme();
      var engine = window.LlmWikiGraphEngine.createGraphEngine(root, {
        data: graphData,
        pins: pins,
        theme: currentTheme,
        toolbarContainer: toolbarHost,
        capabilities: window.LlmWikiGraphEngine.createGraphOfflineCapabilities({
          persistPins: function (nextPins) {
            writeStoredPins(key, nextPins || {});
            return Promise.resolve();
          }
        }).capabilities
      });
      syncThemeToggle(currentTheme);
      if (themeToggle) {
        themeToggle.addEventListener("click", function () {
          currentTheme = currentTheme === "mo-ye" ? "shan-shui" : "mo-ye";
          engine.setTheme(currentTheme);
          writeStoredTheme(currentTheme);
          syncThemeToggle(currentTheme);
        });
      }
      window.__LLM_WIKI_GRAPH_ENGINE__ = engine;
      window.__LLM_WIKI_GRAPH_PINS_KEY__ = key;
      window.__LLM_WIKI_GRAPH_THEME_KEY__ = themeKey;
    })();
  </script>
</body>
</html>
HTML_BOOT

mv "$output_tmp" "$output_next"
mv "$output_next" "$OUTPUT"

rm -f \
  "$output_dir/d3.min.js" \
  "$output_dir/rough.min.js" \
  "$output_dir/marked.min.js" \
  "$output_dir/purify.min.js" \
  "$output_dir/graph-wash.js" \
  "$output_dir/graph-wash-helpers.js" \
  "$output_dir/LICENSE-d3.txt" \
  "$output_dir/LICENSE-roughjs.txt" \
  "$output_dir/LICENSE-marked.txt" \
  "$output_dir/LICENSE-purify.txt"

output_size=$(wc -c < "$OUTPUT" | tr -d ' ')
output_kb=$((output_size / 1024))

echo "交互式图谱已生成："
echo "  - $OUTPUT (${output_kb} KB)"
echo "  节点 $NODE_COUNT · 关联 $EDGE_COUNT"
echo ""
echo "查看方式："
echo "  双击 $OUTPUT"
