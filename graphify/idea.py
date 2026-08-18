"""Turn a personal idea into an Obsidian note and clickable Cytoscape graph."""
from __future__ import annotations

import argparse
import base64
import errno
import html
import json
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from graphify.exporters.base import COMMUNITY_COLORS
from graphify.security import build_safe_opener


INFRANODUS_ENDPOINT = "https://infranodus.com/api/v1/graphAndStatements"
_MAX_RESPONSE_BYTES = 20 * 1024 * 1024


def _safe_stem(value: str) -> str:
    stem = re.sub(r'[\\/:*?"<>|#^[\]]', "", value).strip().strip(".")
    stem = re.sub(r"\s+", " ", stem)
    if not any(character.isalnum() for character in stem):
        raise ValueError("Idea title must contain at least one letter or number.")
    encoded = stem.encode("utf-8")
    if len(encoded) > 180:
        stem = encoded[:180].decode("utf-8", "ignore").rstrip()
    return stem


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:80] or "idea"


def _default_title(text: str) -> str:
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "Idea")
    words = first_line.split()
    return " ".join(words[:8]) + ("..." if len(words) > 8 else "")


def _yaml_string(value: str) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def request_infranodus(
    text: str,
    title: str,
    *,
    api_key: str | None = None,
    ai_topics: bool = True,
    save: bool = False,
    timeout: float = 60,
) -> dict[str, Any]:
    """Analyze text with InfraNodus without exposing the API key to generated HTML."""
    query = urllib.parse.urlencode(
        {
            "doNotSave": str(not save).lower(),
            "addStats": "true",
            "includeStatements": "false",
            "includeGraphSummary": "true",
            "extendedGraphSummary": "true",
            "includeGraph": "true",
            "compactGraph": "true",
        }
    )
    payload = json.dumps(
        {"name": _slug(title), "text": text, "aiTopics": ai_topics},
        ensure_ascii=False,
    ).encode("utf-8")
    headers = {"Content-Type": "application/json", "User-Agent": "graphify/idea"}
    if api_key:
        headers["Authorization"] = api_key

    request = urllib.request.Request(
        f"{INFRANODUS_ENDPOINT}?{query}",
        data=payload,
        headers=headers,
        method="POST",
    )
    try:
        with build_safe_opener().open(request, timeout=timeout) as response:
            raw = response.read(_MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"InfraNodus request failed with HTTP {exc.code}.") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"InfraNodus request failed: {exc.reason}") from exc

    if len(raw) > _MAX_RESPONSE_BYTES:
        raise RuntimeError("InfraNodus response exceeded the 20 MiB safety limit.")
    try:
        result = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("InfraNodus returned an invalid JSON response.") from exc
    if not isinstance(result, dict):
        raise RuntimeError("InfraNodus returned an unexpected response shape.")
    return result


def _graphology_graph(response: Mapping[str, Any]) -> Mapping[str, Any]:
    """Locate the Graphology graph across documented InfraNodus response shapes."""
    entry = response.get("entriesAndGraphOfContext", response)
    if not isinstance(entry, Mapping):
        raise ValueError("InfraNodus response has no entriesAndGraphOfContext object.")

    graph = entry.get("graph")
    if not isinstance(graph, Mapping):
        graph = response.get("graph")
    if not isinstance(graph, Mapping):
        raise ValueError("InfraNodus response does not contain a graph.")

    nested = graph.get("graphologyGraph")
    if isinstance(nested, Mapping):
        graph = nested
    if not isinstance(graph.get("nodes"), list) or not isinstance(graph.get("edges"), list):
        raise ValueError("InfraNodus graph must contain nodes and edges arrays.")
    return graph


def _response_metadata(response: Mapping[str, Any]) -> tuple[str, Mapping[str, Any]]:
    entry = response.get("entriesAndGraphOfContext", response)
    if not isinstance(entry, Mapping):
        return "", {}
    graph_url = _safe_infranodus_url(
        str(entry.get("graphUrl") or response.get("graphUrl") or "")
    )
    summary = entry.get("extendedGraphSummary")
    return graph_url, summary if isinstance(summary, Mapping) else {}


def _safe_infranodus_url(value: str) -> str:
    if not value:
        return ""
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        return ""
    parsed = urllib.parse.urlparse(value)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (
        hostname == "infranodus.com" or hostname.endswith(".infranodus.com")
    ):
        return ""
    return value


def _safe_obsidian_uri(value: str) -> str:
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        return ""
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme.lower() != "obsidian" or not value.lower().startswith("obsidian://"):
        return ""
    return value


def _obsidian_uri(vault: Path, note_path: Path) -> str:
    relative = note_path.relative_to(vault).with_suffix("").as_posix()
    query = urllib.parse.urlencode({"vault": vault.name, "file": relative})
    return f"obsidian://open?{query}"


def _identifier(value: Any) -> str:
    return "" if value is None else str(value).strip()


def cytoscape_elements(
    response: Mapping[str, Any],
    *,
    title: str,
    idea_text: str,
    note_uri: str,
) -> list[dict[str, Any]]:
    """Convert an InfraNodus Graphology graph to Cytoscape elements."""
    if not _safe_obsidian_uri(note_uri):
        raise ValueError("Node note URI must use the obsidian:// scheme.")
    graph = _graphology_graph(response)
    graph_url, _summary = _response_metadata(response)
    elements: list[dict[str, Any]] = [
        {
            "data": {
                "id": "idea",
                "label": title,
                "kind": "idea",
                "content": idea_text,
                "community": -1,
                "color": "#f59e0b",
                "note_uri": note_uri,
                "graph_url": graph_url,
            }
        }
    ]

    concept_ids: set[str] = set()
    ranked: list[tuple[float, str]] = []
    for item in graph["nodes"]:
        if not isinstance(item, Mapping):
            continue
        key_value = item.get("key")
        if key_value is None:
            key_value = item.get("id")
        key = _identifier(key_value)
        if not key:
            continue
        attrs = item.get("attributes")
        attrs = attrs if isinstance(attrs, Mapping) else {}
        concept_id = f"concept:{key}"
        concept_ids.add(concept_id)
        try:
            community = int(attrs.get("community", 0))
        except (TypeError, ValueError):
            community = 0
        degree = attrs.get(
            "weighedDegree",
            attrs.get("weightedDegree", attrs.get("degree", 0)),
        )
        try:
            rank = float(degree)
        except (TypeError, ValueError):
            rank = 0.0
        ranked.append((rank, concept_id))
        elements.append(
            {
                "data": {
                    "id": concept_id,
                    "label": key,
                    "kind": "concept",
                    "community": community,
                    "degree": rank,
                    "color": COMMUNITY_COLORS[community % len(COMMUNITY_COLORS)],
                    "note_uri": note_uri,
                    "graph_url": graph_url,
                }
            }
        )

    edge_index = 0
    for item in graph["edges"]:
        if not isinstance(item, Mapping):
            continue
        source_key = _identifier(item.get("source"))
        target_key = _identifier(item.get("target"))
        source = f"concept:{source_key}"
        target = f"concept:{target_key}"
        if source not in concept_ids or target not in concept_ids:
            continue
        attrs = item.get("attributes")
        attrs = attrs if isinstance(attrs, Mapping) else {}
        elements.append(
            {
                "data": {
                    "id": f"edge:{edge_index}",
                    "source": source,
                    "target": target,
                    "weight": attrs.get("weight", 1),
                    "kind": "infranodus",
                }
            }
        )
        edge_index += 1

    # Make the original thought a visible graph participant, not just a page title.
    for index, (_rank, concept_id) in enumerate(sorted(ranked, reverse=True)[:8]):
        elements.append(
            {
                "data": {
                    "id": f"idea-edge:{index}",
                    "source": "idea",
                    "target": concept_id,
                    "weight": 1,
                    "kind": "idea-context",
                }
            }
        )
    return elements


def _summary_markdown(summary: Mapping[str, Any]) -> list[str]:
    lines: list[str] = []
    for key, heading in (
        ("mainTopics", "Main topics"),
        ("mainConcepts", "Main concepts"),
        ("contentGaps", "Content gaps"),
        ("conceptualGateways", "Conceptual gateways"),
    ):
        values = summary.get(key)
        if not isinstance(values, list) or not values:
            continue
        lines.extend(["", f"## {heading}"])
        for value in values[:12]:
            if isinstance(value, Mapping):
                label = value.get("name") or value.get("label") or value.get("text")
                value = label if label is not None else json.dumps(value, ensure_ascii=False)
            lines.append(f"- {value}")
    return lines


def render_note(
    *,
    title: str,
    idea_text: str,
    html_path: Path,
    graph_url: str,
    summary: Mapping[str, Any],
) -> str:
    lines = [
        "---",
        "type: graphify-idea",
        f"cytoscape_graph: {_yaml_string(html_path.resolve().as_uri())}",
        f"infranodus_graph: {_yaml_string(graph_url)}",
        "tags:",
        "  - graphify/idea",
        "  - infranodus",
        "---",
        "",
        f"# {title}",
        "",
        idea_text.strip(),
        "",
        "## Explore",
        f"- [Open the clickable Cytoscape graph]({html_path.resolve().as_uri()})",
    ]
    if graph_url:
        lines.append(f"- [Open this analysis in InfraNodus]({graph_url})")
    lines.extend(_summary_markdown(summary))
    return "\n".join(lines).rstrip() + "\n"


def render_cytoscape_html(title: str, elements: list[dict[str, Any]]) -> str:
    safe_title = html.escape(title)
    safe_elements: list[dict[str, Any]] = []
    for element in elements:
        safe_element = dict(element)
        data = element.get("data")
        if isinstance(data, Mapping):
            safe_data = dict(data)
            if "note_uri" in safe_data:
                safe_data["note_uri"] = _safe_obsidian_uri(str(data.get("note_uri") or ""))
            if "graph_url" in safe_data:
                safe_data["graph_url"] = _safe_infranodus_url(str(data.get("graph_url") or ""))
            safe_element["data"] = safe_data
        safe_elements.append(safe_element)
    # Keep untrusted graph content entirely out of executable script syntax.
    elements_payload = base64.b64encode(json.dumps(safe_elements).encode("utf-8")).decode("ascii")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{safe_title} - idea graph</title>
<script src="https://unpkg.com/cytoscape@3.33.1/dist/cytoscape.min.js"
        integrity="sha384-lXrzMjLDk3q9l0I/kjqjMcDgfFnHvWTDeWP3DmMqoeOq49/qa8drmlP3OBWN9dQ3"
        crossorigin="anonymous"></script>
<style>
* {{ box-sizing: border-box; }}
body {{ margin: 0; height: 100vh; display: grid; grid-template-columns: 1fr 320px;
  background: #0f172a; color: #e2e8f0; font: 14px system-ui, sans-serif; }}
#cy {{ min-width: 0; }}
aside {{ padding: 20px; background: #111827; border-left: 1px solid #334155; overflow: auto; }}
h1 {{ font-size: 17px; margin: 0 0 16px; }}
#details {{ color: #cbd5e1; line-height: 1.55; }}
.meta {{ color: #94a3b8; margin: 8px 0; }}
a {{ display: inline-block; margin: 12px 8px 0 0; padding: 8px 10px; border-radius: 6px;
  background: #2563eb; color: white; text-decoration: none; }}
.hint {{ color: #64748b; font-size: 12px; margin-top: 20px; }}
</style>
</head>
<body>
<div id="cy"></div>
<aside>
  <h1>{safe_title}</h1>
  <div id="details">Click a node to inspect it.</div>
  <div class="hint">The gold diamond is your original idea. Its strongest InfraNodus concepts
  are connected directly. Use the Obsidian button to return to the source note.</div>
</aside>
<script>
const elements = JSON.parse(atob('{elements_payload}'));
const cy = cytoscape({{
  container: document.getElementById('cy'),
  elements,
  style: [
    {{ selector: 'node', style: {{
      'background-color': 'data(color)', 'label': 'data(label)', 'color': '#e2e8f0',
      'font-size': 11, 'text-valign': 'bottom', 'text-margin-y': 7,
      'width': 'mapData(degree, 0, 20, 18, 48)', 'height': 'mapData(degree, 0, 20, 18, 48)'
    }} }},
    {{ selector: 'node[kind = "idea"]', style: {{
      'shape': 'diamond', 'width': 64, 'height': 64, 'font-size': 14, 'font-weight': 'bold'
    }} }},
    {{ selector: 'edge', style: {{
      'line-color': '#475569', 'width': 'mapData(weight, 1, 10, 1, 5)',
      'curve-style': 'bezier', 'opacity': 0.65
    }} }},
    {{ selector: 'edge[kind = "idea-context"]', style: {{
      'line-color': '#f59e0b', 'width': 2, 'opacity': 0.85
    }} }},
    {{ selector: ':selected', style: {{ 'border-width': 4, 'border-color': '#f8fafc' }} }}
  ],
  layout: {{ name: 'cose', animate: false, randomize: true, nodeRepulsion: 8500 }}
}});

function esc(value) {{
  return String(value ?? '').replace(/[&<>"']/g, ch => ({{
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }})[ch]);
}}
cy.on('tap', 'node', event => {{
  const data = event.target.data();
  const content = data.content ? `<p>${{esc(data.content)}}</p>` : '';
  const degree = data.kind === 'concept' ? `<div class="meta">Weighted degree: ${{esc(data.degree)}}</div>` : '';
  const infra = data.graph_url
    ? `<a href="${{esc(data.graph_url)}}" target="_blank" rel="noopener">Open InfraNodus</a>` : '';
  document.getElementById('details').innerHTML = `
    <strong>${{esc(data.label)}}</strong>${{content}}${{degree}}
    <a href="${{esc(data.note_uri)}}">Open in Obsidian</a>${{infra}}`;
}});
</script>
</body>
</html>
"""


def _write_new(path: Path, content: str, *, force: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if force:
            os.replace(temporary, path)
        else:
            try:
                # Hard-linking commits the staged file without overwriting a
                # concurrently created target. The link operation is atomic.
                os.link(temporary, path)
            except FileExistsError:
                raise FileExistsError(f"Refusing to overwrite existing file: {path}") from None
            except OSError as error:
                unsupported = {
                    errno.EPERM,
                    errno.EXDEV,
                    getattr(errno, "ENOTSUP", errno.EOPNOTSUPP),
                    errno.EOPNOTSUPP,
                }
                if error.errno not in unsupported:
                    raise
                raise OSError(
                    error.errno,
                    "Filesystem does not support atomic no-overwrite publication; "
                    "rerun with --force to allow atomic replacement.",
                    path,
                ) from error
    finally:
        temporary.unlink(missing_ok=True)


def create_idea_graph(
    *,
    text: str,
    title: str,
    vault: Path,
    folder: str = "Ideas",
    output_path: Path | None = None,
    response: Mapping[str, Any] | None = None,
    api_key: str | None = None,
    ai_topics: bool = True,
    save_infranodus: bool = False,
    force: bool = False,
) -> tuple[Path, Path]:
    """Create an Obsidian source note and local Cytoscape graph for one idea."""
    if not text.strip():
        raise ValueError("Idea text cannot be empty.")
    if response is not None and not isinstance(response, Mapping):
        raise ValueError("InfraNodus response must be a JSON object.")
    vault = vault.expanduser().resolve()
    if not vault.is_dir():
        raise ValueError(f"Obsidian vault does not exist or is not a directory: {vault}")

    safe_title = _safe_stem(title)
    folder_path = Path(folder)
    if folder_path.is_absolute():
        raise ValueError("Obsidian folder must be relative to the vault.")
    note_dir = (vault / folder_path).resolve()
    try:
        note_dir.relative_to(vault)
    except ValueError:
        raise ValueError("Obsidian folder must stay inside the vault.") from None
    note_path = note_dir / f"{safe_title}.md"
    output_path = (
        output_path.expanduser()
        if output_path is not None
        else Path("graphify-out") / "ideas" / f"{_slug(safe_title)}.html"
    )
    output_path = output_path.resolve()
    if note_path.exists() and not force:
        raise FileExistsError(f"Refusing to overwrite existing file: {note_path}")
    if output_path.exists() and not force:
        raise FileExistsError(f"Refusing to overwrite existing file: {output_path}")

    result = dict(response) if response is not None else request_infranodus(
        text,
        safe_title,
        api_key=api_key,
        ai_topics=ai_topics,
        save=save_infranodus,
    )
    note_uri = _obsidian_uri(vault, note_path)
    graph_url, summary = _response_metadata(result)
    elements = cytoscape_elements(
        result,
        title=safe_title,
        idea_text=text.strip(),
        note_uri=note_uri,
    )
    html_content = render_cytoscape_html(safe_title, elements)
    note_content = render_note(
        title=safe_title,
        idea_text=text,
        html_path=output_path,
        graph_url=graph_url,
        summary=summary,
    )
    # The note is the durable source of truth. Publish it first so a later HTML
    # filesystem failure never loses the captured idea or requires racy rollback.
    _write_new(note_path, note_content, force=force)
    _write_new(output_path, html_content, force=force)
    return note_path, output_path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="graphify idea",
        description="Turn an idea into an Obsidian note and clickable InfraNodus/Cytoscape graph.",
    )
    parser.add_argument("text", nargs="?", help="idea text (or use --file)")
    parser.add_argument("--file", type=Path, help="read idea text from a UTF-8 file")
    parser.add_argument("--title", help="note and graph title (defaults to the first eight words)")
    parser.add_argument(
        "--vault",
        type=Path,
        help="Obsidian vault path (or set GRAPHIFY_OBSIDIAN_VAULT)",
    )
    parser.add_argument("--folder", default="Ideas", help="folder inside the vault (default: Ideas)")
    parser.add_argument("--output", type=Path, help="Cytoscape HTML output path")
    parser.add_argument("--response", type=Path, help="use an existing InfraNodus JSON response")
    parser.add_argument("--api-key-env", default="INFRANODUS_API_KEY")
    parser.add_argument("--no-ai-topics", action="store_true")
    parser.add_argument("--save-infranodus", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    if (args.text is None) == (args.file is None):
        parser.error("provide exactly one of idea text or --file")
    text = args.text
    if args.file:
        try:
            text = args.file.expanduser().read_text(encoding="utf-8")
        except OSError as exc:
            parser.error(f"could not read idea file: {exc}")
    assert text is not None

    vault = args.vault or (
        Path(os.environ["GRAPHIFY_OBSIDIAN_VAULT"])
        if os.environ.get("GRAPHIFY_OBSIDIAN_VAULT")
        else None
    )
    if vault is None:
        parser.error("--vault is required unless GRAPHIFY_OBSIDIAN_VAULT is set")

    response = None
    if args.response:
        try:
            response = json.loads(args.response.expanduser().read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            parser.error(f"could not read InfraNodus response: {exc}")

    title = args.title or _default_title(text)
    try:
        note_path, html_path = create_idea_graph(
            text=text,
            title=title,
            vault=vault,
            folder=args.folder,
            output_path=args.output,
            response=response,
            api_key=os.environ.get(args.api_key_env),
            ai_topics=not args.no_ai_topics,
            save_infranodus=args.save_infranodus,
            force=args.force,
        )
    except (ValueError, OSError, RuntimeError) as exc:
        parser.error(str(exc))

    print(f"Obsidian note: {note_path}")
    print(f"Clickable graph: {html_path}")
