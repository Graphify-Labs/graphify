# Handoff: Marble / Gaussian splats / Blender / JEPA research

Written 2026-10-22 from the cloud session so the work can continue in a local (non-cloud) Claude Code session.
Branch: `claude/brave-bardeen-6ey8ys` (repo `hagopjay/graphify`).

## What the user asked

Research World Labs' Marble (Fei-Fei Li): how the technology works, what they have built, the API and roadmap.
Then: bridge Marble's Gaussian splats through Blender to Unreal, Unity, and X3D/web engines (X_ITE, three.js, Babylon.js).
Then: is there a Marble / splats / NeRF / Yann LeCun JEPA connection, and what would AI-enabled X3D look like
(graph agents inside scene graphs, validating and verifying, bridging to JEPA).

## State at handoff

- Seven first-round research notes are done and pushed: `research_notes/Marble splats Blender JEPA bridge/*.md`
  (company_and_products, marble_technology_deep_dive, worldlabs_api, splat_formats_and_standards, blender_hub_tooling,
  jepa_and_world_models, agentic_scene_graphs).
- A single report writer was started from those notes. Target: `reports/Marble splats Blender JEPA bridge.md`.
  Check whether that file exists on the branch. If it does not, re-run a writer over the notes folder
  (instructions: the deep-research skill's `references/report-writer.md`).
- A second-round verification pass (11 verifiers) was cancelled to save usage. NO claim has been independently re-verified.

## Why a local session helps

The cloud sandbox could only reach GitHub. worldlabs.ai, docs.worldlabs.ai, arxiv.org, khronos.org, web3d.org, blender.org
and several news sites failed DNS, so most facts rest on GitHub reads and search-result summaries.
A local machine with normal network access can read the primary sources directly.

## Conflicts and weak spots to resolve first

1. `KHR_gaussian_splatting`: ratified (Khronos registry commit 3 Sep 2026, text edited 13 Oct 2026) vs release candidate only.
2. X_ITE `GaussianSplats` node: implemented since v15.1 (31 May 2026) vs "not implemented" vs the user's fork README
   (`hagopjay/x3d-blender-io`) saying no browser supports it yet.
3. Marble export axis convention: OpenGL (World Labs release notes) vs OpenCV (trade press says negate Y and Z).
   Settle with a test import of an asymmetric marker. Also SPZ version, SH degree, units/scale.
4. Blender 5.3 native splat import/render (no export), stable date 10 Nov 2026, "Apply Transform does not update splats".
5. AMD all-stock acquisition of World Labs (~$8.2B, announced 28 Sep 2026): read AMD's own release; also Atlas model details.
6. Founders' lineage (Johnson scene graphs/CLEVR/Mesh R-CNN, Mildenhall NeRF, Lassner Pulsar) is secondary-source only.
7. JEPA side: AMI Labs facts and arXiv IDs (V-JEPA 2 2506.09985, V-JEPA 2.1 2603.14482, H-JEPA 2610.06805,
   Gaussian-JEPA 2608.15651, LeWM 2603.19312). No direct LeCun/AMI to Li/World Labs link was found; search Li's and
   World Labs' essays for "JEPA", "LeCun", "AMI".
8. Agentic prior art is mostly search summaries: SAGE, SceneSmith, SimWorlds, WorldClaw, REALM; read
   `Web3DConsortium/x3d_mcp` directly.
9. Naming: World Labs' real-time model is RTFM (Real-Time Frame Model), not "RTT".

## Suggested verification tasks (one agent or one pass each)

- World Labs API: read `worldlabsai/worldlabs-api-python`, `worldlabsai/skills` (OpenAPI snapshot), atlas repos;
  endpoints, model/permission enums, asset keys, export cost, webhooks, axis convention.
- Corporate/timeline: AMD release, funding rounds, Atlas, SceniX, Marble 1.1, pricing.
- Blender 5.3: importer source in `blender/blender`, release notes and schedule, add-on last-commit dates and licences.
- X3D/X_ITE and the user's fork: read `hagopjay/x3d-blender-io` and `create3000/x_ite` source; X3D 4.1 draft text.
- Standards: glTF extension README at a pinned commit, OpenUSD 26.03 ParticleField, SPZ v4, SOG v2, renderer support.
- People: Li and co-founder bibliography.
- JEPA relationship and paper IDs (item 7 above).
- Agentic scene graphs (item 8 above).
- Marble architecture disclosures (interviews, launch post, Spark docs) and 3DGS fundamentals against `graphdeco-inria/gaussian-splatting`.
- Conversion recipe: authoritative axis, quaternion-order and SH conventions per format, plus a numerically tested numpy script
  (rotate SH degree 1-2 coefficients and check view-dependent colour is preserved).
- Engine plugins: aras-p/UnityGaussianSplatting, arloopa/UnitySplats, Cesium for Unreal, SplatRenderer, NanoGS; any 2026 first-party Epic/Unity splat support.

Each verifier should write `verify_<topic>.md` into the notes folder with a table of
claim | status (CONFIRMED-PRIMARY / CONFIRMED-INDEPENDENT / SINGLE-SOURCE / CONTRADICTED / UNVERIFIED) | evidence URL.
Then re-run the report writer so verification files override first-round notes.

## Notes

- The repo's `AGENTS.md` (graphify rules) does not apply: no code in this repo was modified.
- Keep web searches frugal; the cloud run hit a shared search budget.
