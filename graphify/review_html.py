"""Offline progressive-disclosure review renderer. No providers or external assets."""
from __future__ import annotations

import hashlib
import html
import json
import textwrap
from urllib.parse import quote, urlsplit

import networkx as nx

from graphify.callflow_html import stable_ascii_id


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _edge_key(edge: dict) -> tuple:
    return edge["source"], edge["target"], edge.get("relation", "")


def _display_label(label: str) -> str:
    # Formatting only; retain the exact symbol in the tooltip and evidence.
    return label.removesuffix("()").replace("_", " ").strip()


def _positions(graphs: list[dict]) -> tuple[dict, int, int]:
    """Reuse NetworkX topology; a bounded shared layout preserves the mental map."""
    union = nx.DiGraph()
    for graph in graphs:
        union.add_nodes_from(sorted(n["id"] for n in graph["nodes"]))
        union.add_edges_from(sorted((e["source"], e["target"]) for e in graph["edges"]))
    if not union:
        return {}, 640, 120
    condensed = nx.condensation(union, sorted(nx.strongly_connected_components(union), key=lambda c: sorted(c)))
    rank = {}
    for level, generation in enumerate(nx.topological_generations(condensed)):
        for component in generation:
            for node_id in sorted(condensed.nodes[component]["members"]):
                rank[node_id] = min(level, 3)
    columns: dict[int, list[str]] = {}
    for node_id in sorted(union):
        columns.setdefault(rank[node_id], []).append(node_id)
    width = max(640, (max(columns) + 1) * 240 + 30)
    height = max(180, max(map(len, columns.values())) * 110 + 40)
    positions = {node_id: (20 + level * 240, 25 + index * 110)
                 for level, nodes in sorted(columns.items()) for index, node_id in enumerate(nodes)}
    return positions, width, height


def _svg(graph: dict, positions: dict, width: int, height: int, *, title: str,
         other: dict | None = None, side: str = "head", identifier: str = "graph") -> str:
    if not graph["nodes"]:
        return '<p class="empty">No supported structural nodes in this view. Source changes remain available.</p>'
    marker = stable_ascii_id(identifier, prefix="arrow")
    other_nodes = {n["id"] for n in other["nodes"]} if other is not None else set()
    other_edges = {_edge_key(e) for e in other["edges"]} if other is not None else set()
    output = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-label="{_esc(title)}">',
              f'<title>{_esc(title)}</title><defs><marker id="{marker}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="context-stroke"/></marker></defs>']
    present = {n["id"] for n in graph["nodes"]}
    for edge in graph["edges"]:
        source, target = edge["source"], edge["target"]
        if source not in present or target not in present:
            continue
        x0, y0 = positions[source]
        x1, y1 = positions[target]
        changed = other is not None and _edge_key(edge) not in other_edges
        color = "#bc3546" if changed and side == "base" else "#16805f" if changed else "#52647a"
        if x0 < x1:
            start, stop = (x0 + 200, y0 + 36), (x1 - 3, y1 + 36)
        elif x0 > x1:
            start, stop = (x0, y0 + 36), (x1 + 203, y1 + 36)
        else:
            start, stop = (x0 + 100, y0 + 72), (x1 + 100, y1 - 3)
        if source == target:
            path = f'M {x0 + 160} {y0} C {x0 + 250} {y0 - 25}, {x0 + 250} {y0 + 75}, {x0 + 203} {y0 + 36}'
        else:
            middle = (start[0] + stop[0]) / 2
            path = f'M {start[0]} {start[1]} C {middle} {start[1]}, {middle} {stop[1]}, {stop[0]} {stop[1]}'
        confidence = edge.get("confidence", "AMBIGUOUS")
        dashed = ' stroke-dasharray="5 4"' if confidence != "EXTRACTED" else ""
        evidence = edge.get("evidence_id")
        tooltip = f'{edge.get("relation", "relationship")} · {confidence}'
        if evidence:
            output.append(f'<a href="#{_esc(evidence)}" aria-label="{_esc(tooltip)} source">')
        output.append(f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2"{dashed} marker-end="url(#{marker})"><title>{_esc(tooltip)}</title></path>')
        relation = edge.get("relation", "")
        short_label = "import" if relation in ("imports", "imports_from", "dynamic_import") else relation
        output.append(f'<text x="{(start[0] + stop[0]) / 2}" y="{(start[1] + stop[1]) / 2 - 7}" text-anchor="middle" class="edge-label">{_esc(short_label)}</text>')
        if evidence:
            output.append("</a>")
    for node in graph["nodes"]:
        x, y = positions[node["id"]]
        changed = other is not None and node["id"] not in other_nodes
        color = "#bc3546" if changed and side == "base" else "#16805f" if changed else "#42618a"
        status = "REMOVED" if changed and side == "base" else "ADDED" if changed else "CONTEXT"
        if "depth" in node:
            status = "DIRECT SEED" if node["depth"] == 0 else f'DEPENDENT · DEPTH {node["depth"]}'
        elif node.get("context_bridge"):
            status = "MEMBER CONTEXT"
        evidence = node.get("evidence_id")
        if evidence:
            output.append(f'<a href="#{_esc(evidence)}" aria-label="{_esc(node["label"])} source">')
        output.append(f'<g><title>{_esc(node["label"])} · {_esc(node.get("source_file", "Source unavailable"))} {_esc(node.get("source_location", ""))}</title><rect x="{x}" y="{y}" width="200" height="72" rx="10" fill="#fff" stroke="{color}" stroke-width="2"/>')
        lines = textwrap.wrap(_display_label(str(node["label"])), width=26, break_long_words=True)[:2]
        for index, label in enumerate(lines):
            output.append(f'<text x="{x + 12}" y="{y + 23 + index * 17}" class="node-label">{_esc(label)}</text>')
        output.append(f'<text x="{x + 12}" y="{y + 60}" fill="{color}" class="node-status">{status}</text></g>')
        if evidence:
            output.append("</a>")
    output.append("</svg>")
    return '<div class="diagram">' + "".join(output) + "</div>"


def _relationships(graph: dict) -> str:
    labels = {n["id"]: n["label"] for n in graph["nodes"]}
    rows = "".join(f'<li>{_esc(labels.get(e["source"], e["source"]))} → {_esc(labels.get(e["target"], e["target"]))}: <b>{_esc(e.get("relation", ""))}</b> <span class="badge">{_esc(e.get("confidence", "AMBIGUOUS"))}</span>' + (f' <a href="#{_esc(e["evidence_id"])}">Source</a>' if e.get("evidence_id") else "") + '</li>' for e in graph["edges"])
    nodes = "".join('<li>' + (f'<a href="#{_esc(n["evidence_id"])}">{_esc(n["label"])}</a>' if n.get("evidence_id") else _esc(n["label"])) + '</li>' for n in graph["nodes"])
    return '<details class="subdetail"><summary>Relationships, confidence and source details</summary><ul>' + (rows or "<li>No supported relationships in this selected view.</li>") + "</ul><h3>Symbols</h3><ul>" + nodes + "</ul></details>"


def _source_links(ids: list[str]) -> str:
    return '<div class="source-links">' + "".join(f'<a href="#{_esc(i)}">Evidence {index + 1}</a>' for index, i in enumerate(ids)) + "</div>"


def _story(story: dict, index: int, analysis: dict) -> str:
    behavior = story["behavior"]
    title = behavior["summary"] if behavior else f'Changes in {story["title"]}'
    pseudocode = ""
    if behavior:
        pseudocode = '<span class="badge inferred">INFERRED · BEHAVIOR INTERPRETATION</span><div class="pair">' + "".join(
            f'<div class="pseudocode"><h3>{side.upper()}</h3><pre><code>{_esc(behavior[f"{side}_pseudocode"])}</code></pre></div>' for side in ("before", "after")) + "</div>"
        pseudocode += _source_links(behavior["evidence_ids"])
        if behavior["uncertainties"]:
            pseudocode += '<ul class="uncertainty">' + "".join(f'<li>{_esc(u)}</li>' for u in behavior["uncertainties"]) + "</ul>"
    else:
        pseudocode = f'<p class="empty">Behavioral pseudocode unavailable for this story. Analysis: {_esc(analysis["status"])}. Structural graphs and source evidence are available below.</p>'
    pair = story["graphs"]
    positions, width, height = _positions([pair["base"], pair["head"]])
    diagrams = '<div class="pair graph-pair">' + "".join(
        f'<div><h3>{"BEFORE" if side == "base" else "AFTER"} DEPENDENCIES</h3>' + _svg(pair[side], positions, width, height, title=f'{side} dependencies for {story["title"]}', other=pair["head" if side == "base" else "base"], side=side, identifier=f'{story["id"]}-{side}') + _relationships(pair[side]) + "</div>" for side in ("base", "head")) + "</div>"
    coverage = story["source"]
    warning = ""
    if coverage.get("diff_limited"):
        warning += '<p class="warning">Detailed line matching exceeded its work budget. The changed middle region is shown conservatively; excerpts may be truncated.</p>'
    if "unavailable" in coverage["sides"].values():
        warning += '<p class="warning">Source coverage is incomplete: an excluded, binary, oversized, or unsupported side is unavailable.</p>'
    change = story["change"]
    modes = {"000000": "not present", "100644": "regular file", "100755": "executable file",
             "120000": "symbolic link", "160000": "submodule"}
    if change.get("base_mode") != change.get("head_mode"):
        warning += '<p class="caption">File type/mode: ' + _esc(modes.get(change.get("base_mode"), change.get("base_mode"))) + ' → ' + _esc(modes.get(change.get("head_mode"), change.get("head_mode"))) + '</p>'
    if coverage["omitted_hunks"] or any(coverage["sides"][side] == "available" for side in coverage["sides"]) and not story["evidence_ids"]:
        warning += f'<p class="warning">Source excerpts: {len(story["evidence_ids"])}. Omitted hunks: {coverage["omitted_hunks"]}. Empty/unchanged source may have no excerpt.</p>'
    method = {"python_ast_span": "matched to changed Python symbol ranges",
              "changed_file_membership": "all supported symbols in the changed file",
              "insertion_after_existing_source": "no existing source at the insertion point"}.get(story["seed_methods"]["head"], "source mapping unavailable")
    return f'<details class="story" id="{_esc(story["id"])}" {"open" if index == 0 else ""}><summary><span class="story-number">{index + 1:02}</span><span><strong>{_esc(title)}</strong><small>{_esc(story["change"]["status"])} · {_esc(story["title"])}</small></span></summary><div class="story-body">{warning}{pseudocode}<h3>Focused before/after graph</h3><p class="caption">Arrows show dependency direction. Green: added; red: removed; gray/blue: context. Dashed edges carry inferred or ambiguous confidence. Follow node/edge links, then expand the cited source card.</p>{diagrams}<p class="caption">Graph coverage: {pair["omitted_candidates"]} candidates omitted. Direct seeds are {_esc(method)}. Unchanged context and shared positions are retained.</p>{_source_links(story["evidence_ids"])}<details class="subdetail"><summary>Inspect source diff and coverage</summary><p>Base: {_esc(coverage["sides"]["base"])} · Head: {_esc(coverage["sides"]["head"])} · Patch truncated: {_esc(coverage["patch_truncated"])}</p><pre><code>{_esc(coverage["patch"])}</code></pre></details></div></details>'


def _blast(review: dict) -> str:
    graphs = [review["blast_radius"][side]["graph"] for side in ("base", "head")]
    positions, width, height = _positions(graphs)
    output = ['<section id="impact"><h2>Explore the blast radius</h2><p>Potential structural impact: direct seeds and incoming dependents, bounded by depth and relation filters. Communities are snapshot-local groupings.</p><div class="pair">']
    for side in ("base", "head"):
        radius = review["blast_radius"][side]
        output.append(f'<div class="impact-card"><h3>{side.upper()}</h3><p><b>{radius["direct_count"]}</b> direct seeds · <b>{radius["indirect_count"]}</b> upstream dependents · depth {radius["depth"]}</p>')
        if radius["omitted_seeds"]:
            output.append(f'<p class="warning">Only the first {radius["direct_count"] - radius["omitted_seeds"]} seeds were traversed; dependent counts are partial.</p>')
        output.append(_svg(radius["graph"], positions, width, height, title=f'{side} blast radius', identifier=f'impact-{side}'))
        output.append(_relationships(radius["graph"]))
        output.append(f'<p class="caption">Diagram omits {radius["graph"]["omitted_nodes"]} affected nodes. Detail lists omit {radius["omitted_direct"]} direct / {radius["omitted_indirect"]} indirect nodes.</p>')
        output.append('<details class="subdetail"><summary>Affected communities and dependency details</summary><ul>')
        output.extend(f'<li>{_esc(c["label"])}: {c["affected_nodes"]} represented affected / {c["total_nodes"]} total nodes</li>' for c in radius["communities"])
        output.append('</ul><div class="table-wrap"><table><thead><tr><th>Dependent</th><th>Depth</th><th>Relationship</th></tr></thead><tbody>')
        output.extend(f'<tr><td>{_esc(h["id"])}</td><td>{h["depth"]}</td><td>{_esc(h["via_relation"])}</td></tr>' for h in radius["indirect"])
        output.append('</tbody></table></div><p class="caption">Relations: ' + _esc(", ".join(radius["relations"])) + '</p></details></div>')
    output.append('</div></section>')
    return "".join(output)


def _evidence(review: dict) -> str:
    output = ['<section id="evidence"><h2>Verify in source</h2><p>Every excerpt identifies its side and fixed revision. Open a card to inspect the cited details.</p>']
    target = review["target"]
    repository = str(target.get("repository", ""))
    remote = urlsplit(str(target.get("url", "")))
    authority = remote.netloc if remote.scheme == "https" and remote.hostname and remote.username is None and remote.password is None else None
    for evidence in review["evidence"]:
        link = ""
        if authority and len(repository.split("/")) == 2:
            url = f'https://{authority}/{quote(repository, safe="/")}/blob/{evidence["revision"]}/{quote(evidence["source_file"], safe="/")}#L{evidence["line_start"]}-L{evidence["line_end"]}'
            link = f' · <a href="{_esc(url)}" target="_blank" rel="noopener noreferrer">Pinned source ↗</a>'
        lines = "\n".join(f'{number:4}  {line}' for number, line in enumerate(evidence["snippet"].split("\n"), evidence["line_start"]))
        output.append(f'<details class="evidence" id="{_esc(evidence["id"])}"><summary><span class="badge">SOURCE · {_esc(evidence["side"].upper())}</span> {_esc(evidence["source_file"])}:L{evidence["line_start"]}–L{evidence["line_end"]}</summary><div class="evidence-body"><p>Revision <code>{_esc(evidence["revision"])}</code>{link}</p><pre><code>{_esc(lines)}</code></pre>')
        if evidence.get("truncated"):
            output.append('<p class="warning">This excerpt is truncated; full hunk coverage is unavailable.</p>')
        output.append('</div></details>')
    output.append('</section>')
    return "".join(output)


STYLE = """
:root{color-scheme:light;--ink:#162536;--muted:#52647a;--line:#dbe3ec;--blue:#245db4}
*{box-sizing:border-box}body{margin:0;background:#f5f7fa;color:var(--ink);font:16px/1.6 system-ui,-apple-system,sans-serif;overflow-wrap:anywhere}
main{max-width:1400px;margin:auto;padding:35px 35px 75px}h1{font-size:clamp(30px,4vw,46px);line-height:1.18;letter-spacing:-.035em;margin:16px 0}h2{font-size:25px;letter-spacing:-.02em;margin:0 0 14px}h3{font-size:14px;margin:16px 0 10px}p{margin:10px 0}a{color:var(--blue)}section{margin:35px 0;scroll-margin-top:20px}.eyebrow{font-size:12px;color:var(--blue);letter-spacing:.1em;font-weight:750;text-transform:uppercase}.revisions,.caption{font-size:12px;color:var(--muted)}nav{display:flex;gap:24px;flex-wrap:wrap;border-bottom:1px solid var(--line);padding:18px 0}nav a{text-decoration:none;font-weight:650;font-size:14px}.stats{display:flex;gap:12px;flex-wrap:wrap;margin:20px 0}.stat{background:#fff;border:1px solid var(--line);border-radius:9px;padding:12px 20px;min-width:150px}.stat b{display:block;font-size:25px}.stat span{font-size:12px;color:var(--muted)}.warning{background:#fff4dc;border-left:3px solid #bc8b22;padding:10px 14px;font-size:13px}.uncertainty{background:#fff4dc;padding:12px 30px;font-size:13px}.badge{display:inline-block;font-size:10px;font-weight:750;letter-spacing:.05em;background:#e5edf7;color:#3c5573;padding:3px 7px;border-radius:5px}.inferred{background:#eee8fb;color:#6345a2}.story{background:white;border:1px solid var(--line);border-radius:12px;margin:15px 0;overflow:hidden}.story>summary{display:flex;gap:16px;align-items:start;padding:22px;cursor:pointer}.story-number{font-size:17px;color:var(--blue);font-weight:700}.story summary strong{font-size:17px}.story summary small{display:block;color:var(--muted);font-size:12px;margin-top:5px}.story-body{padding:0 24px 24px}.pair{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:20px}.pair>*{min-width:0}.pseudocode{border:1px solid var(--line);border-radius:9px;overflow:hidden;margin-top:15px}.pseudocode h3{margin:0;padding:11px 16px;background:#edf2f8;font-size:11px;letter-spacing:.08em}.pseudocode:nth-child(2) h3{background:#eaf5f0}.pseudocode pre{white-space:pre-wrap;overflow-wrap:anywhere}pre{font:12px/1.8 ui-monospace,SFMono-Regular,Consolas,monospace;overflow:auto;tab-size:4;padding:17px;background:#f7f9fc;margin:0}code{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:.9em}.diagram{overflow:auto;background:#f9fbfd;border:1px solid var(--line);border-radius:9px}.diagram svg{display:block;width:100%;min-width:540px}.node-label{font:13px system-ui,sans-serif;fill:#162536}.node-status{font:9px system-ui,sans-serif;font-weight:750}.edge-label{font:10px system-ui,sans-serif;fill:#52647a;paint-order:stroke;stroke:#f9fbfd;stroke-width:3px}.source-links{display:flex;gap:9px;flex-wrap:wrap;margin:16px 0}.source-links a{padding:4px 9px;background:#edf2f8;border-radius:5px;text-decoration:none;font-size:12px}.subdetail,.evidence{border:1px solid var(--line);border-radius:8px;margin:12px 0;background:#fff;overflow:hidden}.subdetail summary,.evidence summary{padding:13px 16px;cursor:pointer;font-size:13px}.subdetail>p,.subdetail>ul{margin:12px 18px}.impact-card{background:#fff;border:1px solid var(--line);padding:20px;border-radius:12px}.evidence-body{padding:0 16px 16px}.evidence-body p{font-size:12px;color:var(--muted)}.evidence:target{outline:2px solid #759cd5;outline-offset:2px}.empty{color:var(--muted);font-size:13px;padding:12px 16px;background:#eef2f7;border-radius:7px}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;font-size:12px}td,th{padding:9px 12px;text-align:left;border-bottom:1px solid var(--line)}footer{margin-top:40px;padding-top:18px;border-top:1px solid var(--line);font-size:12px;color:var(--muted)}
@media(max-width:760px){main{padding:22px 15px 50px}.pair{grid-template-columns:1fr}.story-body{padding:0 15px 18px}.story>summary{padding:17px}.stats{gap:8px}.stat{min-width:130px;flex:1}.diagram svg{min-width:480px}}
@media print{details{display:block}details>*,details:not([open])>*{display:block}nav{display:none}.diagram svg{min-width:0}.pair{break-inside:avoid}}
"""


def render_review(review: dict) -> str:
    """Render trusted structure with all source/model text escaped as inert data."""
    from graphify.review import validate_review

    validate_review(review)
    target = review["target"]
    analysis = review["behavior_analysis"]
    digest = hashlib.sha256(json.dumps(review, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    behavior_count = sum(bool(s["behavior"]) for s in review["stories"])
    warnings = []
    if review.get("omitted_change_stories"):
        warnings.append(f'{review["omitted_change_stories"]} of {review["changed_file_count"]} changed-file stories were omitted by the review budget. Blast radius covers the retained stories only.')
    for side, coverage in review["coverage"].items():
        unmapped = coverage.get("unmapped_failed_sources", 0)
        if coverage["omitted_files"] or coverage["failed_sources"] or unmapped:
            failures = len(coverage["failed_sources"]) + unmapped
            detail = f" {unmapped} failure diagnostics could not be mapped to snapshot source." if unmapped else ""
            warnings.append(f'{side.upper()} coverage: {len(coverage["omitted_files"])} omitted files; {failures} failed extractions.{detail} Impact may be incomplete.')
        if coverage.get("path_dependent_nodes"):
            warnings.append(f'{side.upper()} coverage: {coverage["path_dependent_nodes"]} records with snapshot-dependent identities were excluded from comparison.')
    if analysis["status"] != "complete":
        warnings.append(f'Behavior analysis: {analysis["status"]}. {analysis.get("reason", "Interpretations require --infer and usable evidence.")}')
    if analysis.get("omitted_stories"):
        warnings.append(f'{analysis["omitted_stories"]} stories were outside the inference context.')
    if analysis.get("illustrative"):
        warnings.append("Demonstration: behavioral pseudocode uses a mocked, authored model response. Structural graphs and blast radius were generated from the committed example source.")
    stats = ((len(review["stories"]), "Retained change stories"), (behavior_count, "Behavior explanations"),
             (review["blast_radius"]["head"]["indirect_count"], "Head upstream dependents"),
             (len(review["blast_radius"]["head"]["communities"]), "Represented head communities"))
    body = f'<div class="eyebrow">Graphify / Human review</div><h1>{_esc(target["title"])}</h1><p>Understand the change, explore its impact, and follow the evidence.</p><p class="revisions">Fixed comparison: <code>{_esc(target["comparison_base"][:12])}</code> → <code>{_esc(target["head"][:12])}</code></p><details class="subdetail"><summary>Revision details</summary><p>Comparison base <code>{_esc(target["comparison_base"])}</code><br>Head <code>{_esc(target["head"])}</code><br>Base tip <code>{_esc(target.get("base_tip", target["comparison_base"]))}</code> · {_esc(target["comparison_kind"])}</p></details><nav aria-label="Review sections"><a href="#changes">Change stories</a><a href="#impact">Blast radius</a><a href="#evidence">Source evidence</a></nav>'
    body += '<div class="stats">' + "".join(f'<div class="stat"><b>{value}</b><span>{_esc(label)}</span></div>' for value, label in stats) + "</div>"
    body += "".join(f'<p class="warning">{_esc(w)}</p>' for w in warnings)
    if target.get("description"):
        body += '<details class="subdetail"><summary>PR author’s description</summary><pre>' + _esc(target["description"]) + '</pre></details>'
    body += '<section id="changes"><h2>Review the change stories</h2><p>Start with pseudocode and the focused graphs. Expand a story when you need more context; graph relationships and source details remain attached.</p>'
    body += "".join(_story(story, index, analysis) for index, story in enumerate(review["stories"])) or '<p class="empty">No changed files in this fixed comparison.</p>'
    body += '</section>' + _blast(review) + _evidence(review)
    body += '<section><h2>Coverage and uncertainty</h2><ul>' + "".join(f'<li>{_esc(limit)}</li>' for limit in review["limitations"]) + '</ul><details class="subdetail"><summary>Raw structural comparison, omitted records, and extraction coverage</summary><pre><code>' + _esc(json.dumps({"graph_diff": review["graph_diff"], "omitted_records": review["omitted_graph_records"], "coverage": review["coverage"]}, indent=2)) + '</code></pre></details></section>'
    body += f'<footer>Graphify review · Explanations are INFERRED; citation validation does not prove semantic correctness. Required content works offline. External source links require a network connection.<br>Review model SHA-256: <code>{digest}</code></footer>'
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'"><title>' + _esc(target["title"]) + '</title><style>' + STYLE + '</style></head><body><main>' + body + '</main></body></html>'
