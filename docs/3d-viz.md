3D visualization is available behind the new --viz flag and can be exported as HTML with the repository's existing export flow.

This document explains how to try the feature manually and how to run a small manual smoke test to verify the 3D renderer is present in the exported HTML.

What this covers
- How to select the renderer when exporting
- A minimal manual smoke test to verify the 3D renderer was exported
- Notes about automated tests and documentation contributions

Quick usage
- CLI flag: pass --viz 3d to the export command (example below).
- Environment: you can also set GRAPHIFY_VIZ_MODE=3d to make 3d the default during an export.

Examples (replace with the repo's export command if different)
- Export with 3D renderer (example):
  ./bin/graphify export --input data/sample.graph --output out/graph.html --viz 3d

- Export with 2D renderer (byte-identical default behavior preserved):
  ./bin/graphify export --input data/sample.graph --output out/graph-2d.html --viz 2d

Manual smoke test (recommended)
1) Create a small sample graph if you don't have one. The project often includes small example datasets in data/ or examples/. If not, use a tiny graph with a few nodes and links.
2) Run the export command with --viz 3d (or set GRAPHIFY_VIZ_MODE=3d and run the export):
   ./bin/graphify export --input data/sample.graph --output out/graph-3d.html --viz 3d
3) Open out/graph-3d.html in a desktop browser (Chrome/Firefox/Safari recommended).
4) Verify the 3D renderer is present:
   - Open the browser's developer tools (F12), then search the page source for either "3d-force-graph" or for a script tag that loads the 3D renderer (the PR pins 3d-force-graph via SRI). Finding the script tag indicates the 3D renderer asset was injected.
   - Interact with the visualization: try search, click-to-inspect, and the "Show" neighbor control mentioned in the PR description. If these features appear and respond, the 3D export is working.

Quick sanity check for 2D byte-identical behavior
1) Export a graph with --viz 2d and compare the result against the existing golden/test fixture if available.
2) If the project has a byte-identical regression test (the PR claims byte-identical 2D output), run the project's test suite to validate that.

Notes for contributors
- If you are adding automation for this smoke test, prefer non-flaky checks such as asserting the presence of the renderer script tag or key DOM hooks rather than pixel/visual diffs.
- Adding a small unit test that verifies to_html() produces a renderer-agnostic view model is another low-risk way to increase coverage.

How to open a PR from this branch (local Git / gh CLI)
1) git fetch origin
2) git checkout -b chore/docs-3d-viz-smoke origin/main
3) git add docs/3d-viz.md && git commit -m "docs: add 3D viz usage and manual smoke-test instructions"
4) git push --set-upstream origin chore/docs-3d-viz-smoke
5) Create a draft PR on GitHub and target the project's main branch; add a short description referencing PR #2235 and label it as docs / chore.

If you'd like, I can draft the PR description and create the pull request for you (draft) — tell me if you want me to proceed with opening the PR on GitHub or keep this branch here for you to review first.
