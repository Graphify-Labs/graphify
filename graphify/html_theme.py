"""Shared theme assets (CSS custom properties, pre-paint init, toggle controls)
for graphify HTML views (graph.html and GRAPH_TREE.html).

Ensures graph.html and GRAPH_TREE.html share identical palettes, typography,
and localStorage persistence without drifting apart (#3894, #5358).
"""
from __future__ import annotations

THEME_CSS_VARS = """  :root {
    --bg: #0f0f1a; --panel: #1a1a2e; --border: #2a2a4e; --input-border: #3a3a5e;
    --text: #e0e0e0; --text-2: #aaa; --text-3: #ccc; --muted: #555; --count: #666;
    --neighbor-border: #333; --node-label: #ffffff;
  }
  [data-theme="light"] {
    --bg: #ffffff; --panel: #f8f9fa; --border: #d9dee5; --input-border: #c3cad4;
    --text: #222222; --text-2: #666666; --text-3: #333333; --muted: #888888; --count: #777777;
    --neighbor-border: #ccc; --node-label: #222222;
  }"""

THEME_INIT_SCRIPT = """<script id="graphify-theme-init">
// Apply the saved theme before first paint (#3894). No saved choice keeps the
// historical dark look; "system" follows prefers-color-scheme.
(function () {
  var pref = null;
  try { pref = localStorage.getItem('graphify-theme'); } catch (e) {}
  var t = pref === 'light' ? 'light'
    : pref === 'system' && window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches ? 'light'
    : 'dark';
  document.documentElement.setAttribute('data-theme', t);
})();
</script>"""

# Switcher chrome shared by both views (#5358): colours and states only. Each
# view owns its own layout (sidebar stack vs inline row) and button sizing.
THEME_TOGGLE_CSS = """  #theme-wrap button {
    background: var(--bg); color: var(--text-2); border: 1px solid var(--input-border);
    border-radius: 4px; font-family: inherit; cursor: pointer;
  }
  #theme-wrap button:hover { color: var(--text); }
  #theme-wrap button[aria-pressed="true"] { background: #4E79A7; border-color: #4E79A7; color: #fff; }"""

THEME_TOGGLE_HTML = """  <div id="theme-wrap" role="group" aria-label="Theme">
    <button type="button" data-theme-choice="light">Light</button>
    <button type="button" data-theme-choice="dark">Dark</button>
    <button type="button" data-theme-choice="system">System</button>
  </div>"""

THEME_TOGGLE_JS = """// Theme toggle (#3894): Light / Dark / System, persisted in localStorage.
const THEME_KEY = 'graphify-theme';
const themeMQ = window.matchMedia ? window.matchMedia('(prefers-color-scheme: light)') : null;
let themeLabelColor = '#ffffff';  // matches the per-node font color set in Python
function themePref() {
  let p = null;
  try { p = localStorage.getItem(THEME_KEY); } catch (e) {}
  return (p === 'light' || p === 'dark' || p === 'system') ? p : null;
}
function applyTheme(pref) {
  const t = pref === 'light' ? 'light' : (pref === 'system' && themeMQ && themeMQ.matches) ? 'light' : 'dark';
  const root = document.documentElement;
  if (!root) return;
  root.setAttribute('data-theme', t);
  document.querySelectorAll('[data-theme-choice]').forEach(b => {
    b.setAttribute('aria-pressed', String(b.dataset.themeChoice === (pref || 'dark')));
  });
  const labelColor = getComputedStyle(root).getPropertyValue('--node-label').trim();
  if (labelColor && labelColor !== themeLabelColor) {
    themeLabelColor = labelColor;
    if (typeof nodesDS !== 'undefined') {
      nodesDS.update(nodesDS.get().map(n => ({ id: n.id, font: Object.assign({}, n.font, { color: labelColor }) })));
    }
  }
}
document.querySelectorAll('[data-theme-choice]').forEach(b => {
  b.addEventListener('click', () => {
    const pref = b.dataset.themeChoice;
    try { localStorage.setItem(THEME_KEY, pref); } catch (e) {}
    applyTheme(pref);
  });
});
if (themeMQ) {
  const onSchemeChange = () => { if (themePref() === 'system') applyTheme('system'); };
  if (themeMQ.addEventListener) themeMQ.addEventListener('change', onSchemeChange);
  else if (themeMQ.addListener) themeMQ.addListener(onSchemeChange);
}
applyTheme(themePref());"""
