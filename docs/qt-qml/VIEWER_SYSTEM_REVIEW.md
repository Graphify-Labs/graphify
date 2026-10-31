# Native graph navigation review

Status: procedure defined; execution remains unverified. Owner: HTML exporter
maintainer, with the reviewer operating the physical device. Acceptance:
REQ-QML-021-AC01–AC03 and REQ-QML-019-AC04. Emitted-script automation remains in
[traceability](../../tests/TRACEABILITY.md); it does not substitute for this check.

## Fixture and evidence

Export the public Graphify repository graph using the reviewed installed wheel.
Retain the source commit, wheel SHA-256, graph/HTML SHA-256, export command/result,
browser/version, operating system, display scale and mouse/device model. Use a
physical mouse with a middle button. Repeat with a source-node export and a
community aggregate export, and at normal, zoomed-in and zoomed-out camera scales.
Do not use private source or account pages as retained evidence.

## Action and expected result

1. Open the exported HTML in each declared browser/platform lane. Every exported
   community starts selected, the graph is visible, and no Overview control exists.
2. Hold the middle button and drag horizontally, vertically and diagonally.
   The camera follows smoothly in both directions at each scale. Nodes and zoom
   remain unchanged; browser autoscroll and text selection do not activate.
3. While holding the button, move outside the canvas and release. Return and move
   without pressing: the camera must stay still. Repeat with focus loss, tab change
   and page exit; each fresh middle press starts an independent gesture.
4. Use wheel zoom, left-button node selection, the inspector, community filters,
   Select All/None and a search that reveals a filtered node. They remain usable
   after the middle gesture. Confirm raw graph and HTML input hashes are unchanged.
5. Where supported, repeat with right-button and touch interaction. Record an
   explicit applicability reason for any unavailable input or platform lane.

Record criterion-by-criterion results, screenshots or a short capture, and relevant
browser console errors. A visible graph alone does not establish gesture cleanup,
input coexistence or all platforms. A lane is Verified only when its applicable
steps pass with the recorded artifact identity.

## Failure, cleanup and retry

Failure signatures include unwanted autoscroll, wrong-axis or zoom-dependent jumps,
continued panning after release/focus loss, stuck cursor/selection suppression,
broken filters/inspection or changed data. Preserve the first failure and its
artifact/environment evidence; add a production regression at the faithful boundary.
Do not edit the exported payload or expected behavior to clear the result.

Release all buttons, restore focus and close the test tab. If capture or cursor
state remains stuck, reload the unchanged artifact and record that recovery was
required. Remove only the reviewer's explicitly created temporary exports after
retaining safe evidence. There is no server or persistent camera state to roll
back. Retry after identifying the owning failure and cleanup; report unavailable
device/browser access as an open system gap, not a pass.
