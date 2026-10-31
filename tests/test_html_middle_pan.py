"""REQ-QML-021 exercises emitted camera navigation, cleanup and coexistence."""
from __future__ import annotations

import copy
import json
import re
import shutil
import subprocess

import networkx as nx
import pytest

from graphify.export import to_html
from tests.test_html_community_links import export_view
from tests.test_html_initial_view import HARNESS, write_view


# Events and camera setters model only external APIs. The production script
# computes every translation; no controller implementation is copied here.
INPUTS = r"""
const events = [];
const beforeData = JSON.stringify({rawNodes: RAW_NODES, rawEdges: RAW_EDGES,
  nodes: [...nodesDS.map.values()], edges: [...edgesDS.map.values()]});
container.style.cursor = 'crosshair';
container.style.userSelect = 'text';
function emit(target, type, options = {}) {
  const event = new Event(type, {button: 1, buttons: 4, pointerId: 7, pointerType: 'mouse',
    clientX: 10, clientY: 20, ...options});
  target.dispatchEvent(event);
  events.push({type, prevented: event.defaultPrevented, stopped: event.stopped});
  return event;
}
function press(options = {}) { return emit(container, 'pointerdown', options); }
function move(options = {}) { return emit(window, 'pointermove', options); }
"""


def content(tmp_path, aggregate=False):
    """Use actual full-source and community exporters with immutable inputs."""
    if aggregate:
        return export_view(tmp_path)
    graph = nx.Graph()
    graph.add_node("a", label="Public <&>", file_type="code", source_file="view.qml",
                   metadata={"qml": {"contract_version": 1, "kind": "property", "raw_name": "value"}})
    graph.add_node("b", label="Peer")
    graph.add_edge("a", "b", relation="references", confidence="EXTRACTED")
    before = copy.deepcopy(graph)
    path = tmp_path / "source.html"
    assert to_html(graph, {0: ["a", "b"]}, str(path), learning_overlay={})
    assert nx.utils.graphs_equal(graph, before)
    return path.read_text(encoding="utf-8")


def run(content, actions):
    """Execute the emitted production script and observe external camera writes."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for emitted navigation contract tests")
    script = re.search(r"<script>(.*?)</script>\s*<script>", content, re.S)
    assert script
    final = r"""
const afterData = JSON.stringify({rawNodes: RAW_NODES, rawEdges: RAW_EDGES,
  nodes: [...nodesDS.map.values()], edges: [...edgesDS.map.values()]});
console.log(JSON.stringify({moves: network.moves, camera: network.camera, scale: network.scale,
  cursor: container.style.cursor, userSelect: container.style.userSelect,
  captures: [...container.captures], captureLog: container.captureLog,
  events, unchanged: beforeData === afterData, selection: network.selections, focusChecks,
  updates: nodesDS.updates + edgesDS.updates, state: state(), extra: typeof extra === 'undefined' ? null : extra}));
"""
    result = subprocess.run([node], input=HARNESS + script[1] + INPUTS + actions + final,
                            text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize("aggregate", [False, True])
@pytest.mark.parametrize("scale", [0.5, 1, 2, 4])
@pytest.mark.parametrize(("dx", "dy"), [(20, 0), (0, 40), (20, 40)])
def test_req_qml021_ac01_middle_drag_translates_both_axes_at_current_zoom(tmp_path, aggregate, scale, dx, dy):
    """Screen deltas move the camera oppositely, using current zoom on every move."""
    result = run(content(tmp_path, aggregate), f"""
network.scale = {scale}; press();
if (network.moves.length) throw Error('press jumped the camera');
move({{clientX: {10 + dx}, clientY: {20 + dy}}});
container.addEventListener('wheel', () => {{ network.scale = 0.5; }});
emit(container, 'wheel', {{button: 0, deltaY: -1}});
move({{clientX: {20 + dx}, clientY: {15 + dy}}});
emit(window, 'pointerup', {{buttons: 0}});
""")
    first = {"x": 100 - dx / scale, "y": -50 - dy / scale}
    assert len(result["moves"]) == 2
    assert result["moves"][0] == {"position": first, "scale": scale, "animation": False}
    assert result["moves"][1] == {"position": {"x": first["x"] - 20, "y": first["y"] + 10},
                                   "scale": 0.5, "animation": False}
    assert result["scale"] == 0.5 and result["cursor"] == "crosshair" and result["userSelect"] == "text"
    assert not next(event for event in result["events"] if event["type"] == "wheel")["prevented"]
    assert not result["captures"] and result["unchanged"] and result["updates"] == 0
    assert not result["selection"] and not result["focusChecks"]


@pytest.mark.parametrize("finish", ["pointerup", "pointercancel", "blur", "pagehide", "lostpointercapture", "buttons"])
def test_req_qml021_ac02_release_cancel_blur_and_lost_buttons_end_drag(tmp_path, finish):
    """Every exit restores transient ownership; a new drag has no stale anchor."""
    end = ("move({buttons: 0, clientX: 200});" if finish == "buttons" else
           f"emit({'container' if finish == 'lostpointercapture' else 'window'}, '{finish}', {{buttons: 0}});")
    if finish == "lostpointercapture":
        end = "container.captures.delete(7);" + end
    result = run(content(tmp_path), "press(); move({clientX: 20});" + end + """
move({clientX: 500, clientY: 500});
if (network.moves.length !== 1 || container.style.cursor !== 'crosshair') throw Error('drag lingered');
press({clientX: 100, clientY: 200}); move({clientX: 110, clientY: 220});
emit(window, 'pointerup', {buttons: 0});
""")
    assert len(result["moves"]) == 2 and result["camera"] == {"x": 90, "y": -60}
    assert result["cursor"] == "crosshair" and result["userSelect"] == "text" and result["unchanged"]
    assert not result["captures"]


@pytest.mark.parametrize("failure", ["capture", "release", "absent"])
def test_req_qml021_ac02_capture_failure_has_window_fallback_and_no_lingering_drag(tmp_path, failure):
    """Optional capture API errors cannot break window movement or subsequent cleanup."""
    setup = ("container.setPointerCapture = container.releasePointerCapture = undefined;" if failure == "absent" else
             f"container.{'failCapture' if failure == 'capture' else 'failRelease'} = true;")
    result = run(content(tmp_path), setup + """
press(); move({clientX: 30, clientY: 60}); emit(window, 'pointerup', {buttons: 0});
move({clientX: 90, clientY: 120});
""")
    assert len(result["moves"]) == 1 and result["camera"] == {"x": 90, "y": -70}
    assert result["cursor"] == "crosshair" and result["userSelect"] == "text" and result["unchanged"]


@pytest.mark.parametrize("invalid", ["zero_scale", "negative_scale", "nan_scale", "infinite_scale", "invalid_view", "invalid_input",
                                      "view_exception", "scale_exception", "move_exception", "overflow"])
def test_req_qml021_ac02_invalid_camera_or_input_aborts_without_jump(tmp_path, invalid):
    """Invalid arithmetic/API state ends navigation before any camera write."""
    damage = {"zero_scale": "network.scale = 0;", "nan_scale": "network.scale = NaN;",
              "negative_scale": "network.scale = -1;",
              "infinite_scale": "network.scale = Infinity;", "invalid_view": "network.camera.x = NaN;",
              "invalid_input": "", "view_exception": "network.failView = true;",
              "scale_exception": "network.failScale = true;", "move_exception": "network.failMove = true;",
              "overflow": "network.scale = Number.MIN_VALUE;"}[invalid]
    event = "move({clientX: NaN});" if invalid == "invalid_input" else "move({clientX: 30, clientY: 60});"
    result = run(content(tmp_path), "press();" + damage + event + """
network.scale = 2; network.camera = {x: 100, y: -50};
network.failView = network.failScale = network.failMove = false;
move({clientX: 200});
if (network.moves.length) throw Error('invalid drag resumed');
press(); move({clientX: 20}); emit(window, 'pointerup', {buttons: 0});
""")
    assert len(result["moves"]) == 1 and result["camera"] == {"x": 95, "y": -50}
    assert result["cursor"] == "crosshair" and result["userSelect"] == "text" and not result["captures"]


@pytest.mark.parametrize("invalid", ["negative_scale", "missing_scale", "missing_view", "nan_x", "infinite_y",
                                      "negative_id", "fractional_id", "released_middle"])
def test_req_qml021_ac02_invalid_press_cannot_capture_or_resume_after_repair(tmp_path, invalid):
    """Invalid initial state leaves no transient ownership, even after external API recovery."""
    setup = {"negative_scale": "network.scale = -1;", "missing_scale": "network.getScale = undefined;",
             "missing_view": "network.getViewPosition = undefined;"}.get(invalid, "")
    options = {"nan_x": "{clientX: NaN}", "infinite_y": "{clientY: Infinity}",
               "negative_id": "{pointerId: -1}", "fractional_id": "{pointerId: 0.5}",
               "released_middle": "{buttons: 0}"}.get(invalid, "{}")
    result = run(content(tmp_path), """
const getScale = network.getScale, getView = network.getViewPosition;
""" + setup + "press(" + options + ");" + """
if (network.moves.length || container.captureLog.length || container.style.cursor !== 'crosshair'
    || container.style.userSelect !== 'text') throw Error('invalid press acquired ownership');
network.scale = 2; network.getScale = getScale; network.getViewPosition = getView;
move({clientX: 200});
if (network.moves.length) throw Error('invalid press resumed after repair');
press(); move({clientX: 20}); emit(window, 'pointerup', {buttons: 0});
""")
    assert len(result["moves"]) == 1 and result["camera"] == {"x": 95, "y": -50}
    assert result["userSelect"] == "text" and not result["captures"] and result["unchanged"]


def test_req_qml021_ac02_unrelated_pointer_and_nonmiddle_release_preserve_owned_drag(tmp_path):
    """Another pointer and a left-button release cannot change the active anchor."""
    result = run(content(tmp_path), """
press(); move({pointerId: 9, clientX: 900});
emit(window, 'pointerup', {button: 0, buttons: 4});
move({clientX: 30, clientY: 60}); emit(window, 'pointerup', {buttons: 0});
""")
    assert len(result["moves"]) == 1 and result["camera"] == {"x": 90, "y": -70}


def test_req_qml021_ac03_other_inputs_and_source_datasets_remain_unchanged(tmp_path):
    """Left/right/touch/wheel controls remain native; middle suppresses browser autoscroll."""
    result = run(content(tmp_path, True), """
const native = [];
['pointerdown', 'pointermove', 'wheel', 'mousedown', 'auxclick'].forEach(type =>
  container.addEventListener(type, e => native.push([type, e.pointerType, e.button])));
emit(container, 'pointerdown', {button: 0, buttons: 1});
emit(container, 'pointermove', {button: 0, buttons: 1, clientX: 40});
emit(container, 'pointerdown', {button: 2, buttons: 2});
emit(container, 'pointerdown', {pointerType: 'touch', button: 1});
emit(container, 'wheel', {deltaY: 2});
if (native.length !== 5 || network.moves.length) throw Error('native controls intercepted');
emit(container, 'mousedown'); emit(container, 'auxclick', {buttons: 0});
press(); emit(container, 'selectstart'); move({clientX: 30});
emit(window, 'pointerup', {buttons: 0}); emit(container, 'selectstart');
const extra = native;
""")
    assert all(not event["prevented"] for event in result["events"][:5])
    assert all(event["prevented"] for event in result["events"] if event["type"] in {"mousedown", "auxclick"})
    assert [event["prevented"] for event in result["events"] if event["type"] == "selectstart"] == [True, False]
    assert len(result["extra"]) == 5
    assert len(result["moves"]) == 1 and result["unchanged"] and result["updates"] == 0
    assert result["state"]["checked"] and not result["selection"]


def test_req_qml021_ac03_filters_and_search_work_after_middle_drag(tmp_path):
    """Navigation does not install duplicate controls or strand filtered source evidence."""
    result = run(write_view(tmp_path)[0], """
press(); move({clientX: 30}); emit(window, 'pointerup', {buttons: 0});
toggleAllCommunities(true); toggleAllCommunities(false);
legendControls.get(0).cb.checked = false; legendControls.get(0).cb.handlers.change();
searchInput.value = '<Widget>'; searchInput.handlers.input(); searchResults.children[0].onclick();
const extra = nodesDS.get('n0');
""")
    assert result["focusChecks"] == [{"id": "n0", "present": True}]
    assert result["extra"]["metadata"]["qml"]["raw_name"] == "deferred"
    assert result["state"]["checked"] and len(result["moves"]) == 1
