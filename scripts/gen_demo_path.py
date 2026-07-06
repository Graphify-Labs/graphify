#!/usr/bin/env python3
"""Generate docs/demo-path.svg: the animated 'path lights up' README hero-companion.

Concept 1 ("The Path Lights Up"): a terminal types `graphify path ...` on the
left; on the right the same answer draws itself as a graph, a pulse igniting
each hop while the rest of the constellation stays dim.

Constraints honored:
- Pure SMIL/CSS inside an <img>-referenced SVG (survives GitHub's sanitizer,
  no JS, no external fonts).
- Brand palette only: muted emerald green (#4db18f family) as the single
  accent on a dark green-black card. No shiny/neon colors.
- One 10s master period; every <animate> is dur=10s repeatCount=indefinite and
  fades back to its start state before the loop point, so the loop is seamless.

Run: python3 scripts/gen_demo_path.py  ->  writes docs/demo-path.svg
"""
import math
import os
import random

STATIC = bool(os.environ.get("STATIC"))  # bake the lit held-frame for visual QA

T = 10.0                      # master loop seconds
HOLD_END = 0.96               # everything fades out over the last 0.4s
FADE = 0.12                   # generic fade-in duration (fraction handled per item)

# ---- brand palette (sampled from docs/logo.png) ----------------------------
BG        = "#0c1712"         # dark green-black card
BG2       = "#0f1e18"         # subtle gradient partner
BORDER    = "#20342b"
DIVIDER   = "#1c2c25"
DIM_NODE  = "#2c3a34"         # unlit nodes
DIM_EDGE  = "#22302a"         # unlit edges
GREEN     = "#4db18f"         # brand green (lit)
GREEN_HI  = "#62c4a2"         # brand green light (accents/caption)
GREEN_DK  = "#41a884"         # brand green deep
TXT       = "#c6d6ce"         # primary terminal text
TXT_DIM   = "#6f8a7f"         # secondary terminal text
PROMPT    = "#4db18f"
DOTS      = ["#ff5f56", "#ffbd2e", "#27c93f"]  # macOS traffic lights: close / minimize / zoom

W, H = 900, 360
CHARW = 6.62                  # mono advance at 11px
FS = 11
LX = 20                       # left text margin
PANEL = 336                   # terminal panel width

def kt(*pairs):
    """pairs of (keyTime, value) -> (values_str, keyTimes_str)."""
    ks = ";".join(f"{k:.4f}".rstrip("0").rstrip(".") if k not in (0, 1) else str(int(k)) for k, _ in pairs)
    vs = ";".join(str(v) for _, v in pairs)
    return vs, ks

def op0():
    """initial opacity for a revealable element (1 when baking a static frame)."""
    return "1" if STATIC else "0"

def reveal(t, hold_val="1", start_val="0"):
    """opacity reveal at time t (s), hold, fade out before loop."""
    if STATIC:
        return ""
    a = t / T
    b = min((t + FADE) / T, HOLD_END - 0.001)
    vs, ks = kt((0, start_val), (a, start_val), (b, hold_val), (HOLD_END, hold_val), (1, start_val))
    return f'<animate attributeName="opacity" values="{vs}" keyTimes="{ks}" dur="{T}s" repeatCount="indefinite"/>'

out = []
def e(s): out.append(s)

# ---------------------------------------------------------------- svg header
e(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
  f'font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" role="img" '
  f'aria-label="graphify path query lighting up a knowledge graph">')
e('<defs>')
e(f'<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">'
  f'<stop offset="0" stop-color="{BG}"/><stop offset="1" stop-color="{BG2}"/></linearGradient>')
e(f'<radialGradient id="glow" cx="0.5" cy="0.5" r="0.5">'
  f'<stop offset="0" stop-color="{GREEN_HI}" stop-opacity="0.35"/>'
  f'<stop offset="1" stop-color="{GREEN_HI}" stop-opacity="0"/></radialGradient>')
e('</defs>')

# card
e(f'<rect x="1" y="1" width="{W-2}" height="{H-2}" rx="14" fill="url(#bg)" stroke="{BORDER}" stroke-width="1.5"/>')
e(f'<line x1="{PANEL}" y1="18" x2="{PANEL}" y2="{H-18}" stroke="{DIVIDER}" stroke-width="1"/>')

# window dots (muted)
for i in range(3):
    e(f'<circle cx="{28+i*18}" cy="30" r="4.5" fill="{DOTS[i]}"/>')
e(f'<text x="{PANEL-16}" y="34" text-anchor="end" font-size="10" fill="{TXT_DIM}">graphify</text>')

# ---------------------------------------------------------------- terminal
line_y = 74
prompt_x = LX
# static prompt "$"
e(f'<text x="{prompt_x}" y="{line_y}" font-size="{FS}" fill="{PROMPT}" font-weight="600">$</text>')
cmd = 'graphify path "FastAPI" "ModelField"'
cmd_x0 = prompt_x + CHARW * 2
type_start = 0.35
type_iv = 0.058
for i, ch in enumerate(cmd):
    if ch == " ":
        continue
    cx = cmd_x0 + i * CHARW
    t = type_start + i * type_iv
    disp = ch.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    e(f'<text x="{cx:.1f}" y="{line_y}" font-size="{FS}" fill="{TXT}" opacity="{op0()}">{disp}{reveal(t)}</text>')
type_end = type_start + len(cmd) * type_iv

# blinking caret that steps along while typing, then blinks at the end
caret_xs = [cmd_x0 + i * CHARW for i in range(len(cmd) + 1)]
cvals = ";".join(f"{x:.1f}" for x in caret_xs) + f";{caret_xs[-1]:.1f}"
ckeys = ";".join(f"{(type_start + i*type_iv)/T:.4f}" for i in range(len(cmd) + 1)) + ";1"
# prepend a 0 keyframe
cvals = f"{caret_xs[0]:.1f};" + cvals
ckeys = "0;" + ckeys
if not STATIC:
  e(f'<rect y="{line_y-9}" width="7" height="12" fill="{GREEN}" opacity="0.9">'
  f'<animate attributeName="x" values="{cvals}" keyTimes="{ckeys}" calcMode="discrete" dur="{T}s" repeatCount="indefinite"/>'
  f'<animate attributeName="opacity" values="0.9;0.9;0.15;0.9;0.15;0.9;0" '
  f'keyTimes="0;{type_end/T:.3f};{(type_end+0.45)/T:.3f};{(type_end+0.9)/T:.3f};{(type_end+1.35)/T:.3f};{HOLD_END};1" '
  f'dur="{T}s" repeatCount="indefinite"/></rect>')

# output lines: (text, color, appear_time)
oy = line_y + 30
out_lines = [
    ("Shortest path (3 hops):", TXT_DIM, 2.95),
    ("FastAPI", GREEN_HI, 3.25),
    ("  --uses--> DefaultPlaceholder", TXT, 3.95),
    ("  <--references-- get_request_handler()", TXT, 4.65),
    ("  --references--> ModelField", TXT, 5.35),
]
for i, (txt, col, t) in enumerate(out_lines):
    y = oy + i * 22
    disp = txt.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    e(f'<text x="{LX}" y="{y}" font-size="{FS}" fill="{col}" opacity="{op0()}" '
      f'style="white-space:pre">{disp}{reveal(t)}</text>')

# caption in the terminal footer
cap_y = H - 30
e(f'<text x="{LX}" y="{cap_y}" font-size="12" fill="{GREEN_HI}" font-weight="600" opacity="{op0()}">'
  f'3 hops. Zero files opened.{reveal(5.95)}</text>')

# ---------------------------------------------------------------- graph
# path nodes (visiting order, reads left-to-right)
GX0, GY0, GXW, GYH = PANEL, 0, W - PANEL, H
path_nodes = [
    ("FastAPI",                (PANEL + 70, 205), "below"),
    ("DefaultPlaceholder",     (PANEL + 195, 118), "above"),
    ("get_request_handler()",  (PANEL + 335, 210), "below"),
    ("ModelField",             (PANEL + 470, 120), "above"),
]
path_light_t = [3.25, 3.95, 4.65, 5.35]
rel_labels = ["uses", "references", "references"]

# distractor constellation
random.seed(42)
distractors = []
attempts = 0
avoid = [p[1] for p in path_nodes]
while len(distractors) < 26 and attempts < 4000:
    attempts += 1
    x = random.uniform(PANEL + 30, W - 28)
    y = random.uniform(30, H - 26)
    if all((x-ax)**2 + (y-ay)**2 > 44**2 for ax, ay in avoid) and \
       all((x-dx)**2 + (y-dy)**2 > 34**2 for dx, dy in distractors):
        distractors.append((x, y))

# dim edges: connect each distractor to a couple of near neighbors / path nodes
allpts = distractors + [p[1] for p in path_nodes]
dim_edges = set()
for i, (x, y) in enumerate(distractors):
    dists = sorted(range(len(allpts)), key=lambda j: (allpts[j][0]-x)**2 + (allpts[j][1]-y)**2)
    for j in dists[1:3]:
        a, b = min(i, j + 0 if j < len(distractors) else j), max(i, j)
        dim_edges.add((i, j))

e('<g>')
for i, j in dim_edges:
    x1, y1 = allpts[i]; x2, y2 = allpts[j]
    e(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{DIM_EDGE}" stroke-width="1"/>')
for (x, y) in distractors:
    e(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.6" fill="{DIM_NODE}"/>')
e('</g>')

# path base (dim) edges + green draw-on overlays
def line_len(p, q):
    return math.hypot(q[0]-p[0], q[1]-p[1])

for i in range(3):
    p = path_nodes[i][1]; q = path_nodes[i+1][1]
    e(f'<line x1="{p[0]}" y1="{p[1]}" x2="{q[0]}" y2="{q[1]}" stroke="{DIM_EDGE}" stroke-width="1.2"/>')

for i in range(3):
    p = path_nodes[i][1]; q = path_nodes[i+1][1]
    L = line_len(p, q)
    start = path_light_t[i] + 0.05
    draw = 0.55
    a = start / T; b = (start + draw) / T
    vs, ks = kt((0, f"{L:.1f}"), (a, f"{L:.1f}"), (b, "0"), (HOLD_END, "0"), (1, f"{L:.1f}"))
    off0 = "0" if STATIC else f"{L:.1f}"
    anim = "" if STATIC else f'<animate attributeName="stroke-dashoffset" values="{vs}" keyTimes="{ks}" dur="{T}s" repeatCount="indefinite"/>'
    e(f'<line x1="{p[0]}" y1="{p[1]}" x2="{q[0]}" y2="{q[1]}" stroke="{GREEN}" stroke-width="2" '
      f'stroke-linecap="round" stroke-dasharray="{L:.1f}" stroke-dashoffset="{off0}">{anim}</line>')
    # relationship label at edge midpoint
    mx, my = (p[0]+q[0])/2, (p[1]+q[1])/2 - 6
    e(f'<text x="{mx:.1f}" y="{my:.1f}" font-size="9" fill="{GREEN_HI}" text-anchor="middle" opacity="{op0()}" '
      f'font-style="italic">{rel_labels[i]}{reveal(start + 0.25)}</text>')

# path nodes: glow + circle pop + label
for (name, (x, y), pos), t in zip(path_nodes, path_light_t):
    a = t / T
    # glow halo
    ga, gb = a, (t + 0.15) / T
    gvs, gks = kt((0, "0"), (ga, "0"), (gb, "1"), (HOLD_END, "1"), (1, "0"))
    ganim = "" if STATIC else f'<animate attributeName="opacity" values="{gvs}" keyTimes="{gks}" dur="{T}s" repeatCount="indefinite"/>'
    e(f'<circle cx="{x}" cy="{y}" r="20" fill="url(#glow)" opacity="{op0()}">{ganim}</circle>')
    # node: fill dim->green, radius pop
    fvs, fks = kt((0, DIM_NODE), (a, DIM_NODE), ((t+0.06)/T, GREEN_HI), ((t+0.2)/T, GREEN), (HOLD_END, GREEN), (1, DIM_NODE))
    rvs, rks = kt((0, "4"), (a, "4"), ((t+0.05)/T, "8"), ((t+0.18)/T, "5.6"), (HOLD_END, "5.6"), (1, "4"))
    nfill = GREEN if STATIC else DIM_NODE
    nr = "5.6" if STATIC else "4"
    nanim = "" if STATIC else (
        f'<animate attributeName="fill" values="{fvs}" keyTimes="{fks}" dur="{T}s" repeatCount="indefinite"/>'
        f'<animate attributeName="r" values="{rvs}" keyTimes="{rks}" dur="{T}s" repeatCount="indefinite"/>')
    e(f'<circle cx="{x}" cy="{y}" fill="{nfill}" r="{nr}">{nanim}</circle>')
    # label
    ly = y - 14 if pos == "above" else y + 22
    e(f'<text x="{x}" y="{ly}" font-size="10.5" fill="{TXT}" text-anchor="middle" opacity="{op0()}" '
      f'font-weight="600">{name}{reveal(t + 0.1)}</text>')

e('</svg>')

with open("docs/demo-path.svg", "w", encoding="utf-8") as f:
    f.write("".join(out))
print("wrote docs/demo-path.svg", sum(len(s) for s in out), "bytes")
