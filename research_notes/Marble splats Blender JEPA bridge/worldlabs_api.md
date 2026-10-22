# World Labs API (Marble World API): endpoints, assets, models, pricing, SDKs, roadmap, as of 22 Oct 2026

> **How to read this note (access limitations and evidence tiers).**
> I could NOT fetch `docs.worldlabs.ai`, `www.worldlabs.ai`, `atlas-beta.worldlabs.ai` or `www.cnbc.com` directly. `WebFetch` returned `getaddrinfo ENOTFOUND` for each, and `curl` through the session proxy returned `CONNECT tunnel failed, response 403` for `docs.worldlabs.ai`. I did not try to bypass this. `github.com` pages and `WebSearch` did work.
> So nothing below is a verbatim fetch of the official docs. Where I say "docs", the content is a search-tool excerpt or paraphrase of the named docs.worldlabs.ai page, shown in the search result as coming from that URL. Exact field names are as relayed by those excerpts. Re-check them against the live OpenAPI spec before coding.
> Tags used on each finding:
> - **[DOCS-via-search]**: official docs page as relayed by the search tool, not read verbatim by me.
> - **[GH-fetched]**: official `worldlabsai` GitHub README that I fetched directly.
> - **[2nd-hand]**: press or third-party repos and blogs.
> - **[UNVERIFIED]**: single-source, conflicting, or only inferred.
> Where the docs and third-party sources conflict, the conflict is stated.

---

## 1. Where is the API documented, how do you authenticate, and what are the endpoints and operations?

### Takeaway
The World API (Marble) launched on 21 Jan 2026. It is a REST API at `https://api.worldlabs.ai/marble/v1/...`, documented at `docs.worldlabs.ai/api` (docs index at `docs.worldlabs.ai/llms.txt` and `llms-full.txt`). It authenticates with a `WLT-Api-Key` header and uses an asynchronous generate-then-poll pattern. Generation takes about 5 minutes. Inputs are text, image, multi-image, video and panorama. Panorama is an image input with a flag, not a separate type. I found no official webhook mechanism, only polling.

### Cited Findings
- The World API was announced on 21 Jan 2026 ("Announcing the World API"). It creates "navigable spatial environments directly from text, images, panoramas, multi-view inputs, and video." Keys, usage, billing and docs live on the World Labs platform (`platform.worldlabs.ai`). [DOCS-via-search / blog] — [Announcing the World API](https://www.worldlabs.ai/blog/announcing-the-world-api); [Quickstart](https://docs.worldlabs.ai/api); X announcement: [World Labs on X](https://x.com/theworldlabs/status/2014046374606639216)
- Docs pages found (not fetched directly): Quickstart `docs.worldlabs.ai/api`, Pricing `/api/pricing`, Models `/api/models`, FAQ `/api/faq`, Rate limits `/api/rate-limits`, Reference `/api/reference/worlds/generate`, `/api/reference/worlds/get`, `/api/reference/worlds/list`, Agent skill `/api/agent-skill`, plus the machine-readable indexes `/llms.txt` and `/llms-full.txt`. [DOCS-via-search] — [Generate](https://docs.worldlabs.ai/api/reference/worlds/generate), [Get](https://docs.worldlabs.ai/api/reference/worlds/get), [List](https://docs.worldlabs.ai/api/reference/worlds/list), [llms-full.txt](https://docs.worldlabs.ai/llms-full.txt)
- Base URL and auth: `POST https://api.worldlabs.ai/marble/v1/worlds:generate` with header `WLT-Api-Key`. [DOCS-via-search] — [Generate reference](https://docs.worldlabs.ai/api/reference/worlds/generate). The same auth header is confirmed in the official Python SDK README. [GH-fetched] — [worldlabs-api-python](https://github.com/worldlabsai/worldlabs-api-python)
- Quickstart flow: (1) get an API key from the platform, (2) buy credits, (3) POST to `/marble/v1/worlds:generate`, (4) poll `/marble/v1/operations/{operation_id}` until done, (5) call `GET /marble/v1/worlds/{world_id}` for the complete, current world. [DOCS-via-search] — [Quickstart](https://docs.worldlabs.ai/api)
- Top-level request body fields: `display_name`, `model`, `permission`, `seed`, `tags`, `world_prompt`. [DOCS-via-search] — [Generate reference](https://docs.worldlabs.ai/api/reference/worlds/generate)
- `world_prompt` variants (discriminated by `"type"`):
  - `"text"` with `text_prompt`. Optional `disable_recaption` (if true, `text_prompt` is used as-is without recaptioning).
  - `"image"` with `image_prompt` (a media asset reference or a URI) plus optional `text_prompt`. Pano handling defaults to `is_pano: "auto"`, so a valid equirectangular image skips the pano-generation step.
  - `"multi-image"` with a `multi_image_prompt` array. Each entry has `content` and an optional `azimuth` (direction). The quickstart example uses front and back images.
  - `"video"` with `video_prompt` (media asset or URI).
  - [DOCS-via-search] — [Generate reference](https://docs.worldlabs.ai/api/reference/worlds/generate), [Pricing](https://docs.worldlabs.ai/api/pricing), [Quickstart](https://docs.worldlabs.ai/api), [llms-full.txt](https://docs.worldlabs.ai/llms-full.txt)
- Panorama input is `"type": "image"` with `"is_pano": true`. This comes from a third-party skill and was NOT confirmed against the official reference; the official pricing text only shows `is_pano: "auto"`. [2nd-hand / UNVERIFIED] — [world-labs-pano-video skill](https://agent-skills.md/skills/cloudai-x/world-labs-skills/world-labs-pano-video)
- Operations and other endpoints seen in docs excerpts:
  - `GET /marble/v1/operations/{operation_id}` polls a generation (free, consumes no credits).
  - `GET /marble/v1/worlds/{world_id}` fetches a world.
  - `GET /marble/v1/credits` checks the balance.
  - `POST /marble/v1/worlds/{world_id}:export` exports (see Q2).
  - A "List worlds" reference page exists. I did not see its exact HTTP path in any excerpt.
  - [DOCS-via-search] — [Rate limits](https://docs.worldlabs.ai/api/rate-limits), [Pricing](https://docs.worldlabs.ai/api/pricing), [Quickstart](https://docs.worldlabs.ai/api), [FAQ](https://docs.worldlabs.ai/api/faq)
- Operations that consume no credits: API key creation, media asset upload and management, and operation polling. [DOCS-via-search] — [Rate limits](https://docs.worldlabs.ai/api/rate-limits)
- Error codes on start: `400` (invalid request, policy violation, or invalid `model` value), `402` (insufficient credits), `429` (rate limit), `500` (could not start). [DOCS-via-search] — [Rate limits](https://docs.worldlabs.ai/api/rate-limits), [FAQ](https://docs.worldlabs.ai/api/faq)
- Official Python SDK usage: `WorldLabsClient(api_key=...)` (sync, context manager) and `AsyncWorldLabsClient`. Calls are `generate_world(request)` (returns an operation) and `poll_operation(op.operation_id)` (finished world in `done.response`). Request type is `WorldsGenerateRequest(display_name=..., world_prompt=WorldTextPrompt(text_prompt=...))`. The env var is `WORLDLABS_API_KEY`. [GH-fetched] — [worldlabs-api-python](https://github.com/worldlabsai/worldlabs-api-python)
- Official example repo uses a different env var name, `WLT_API_KEY`, and registration is at `platform.worldlabs.ai`. [GH-fetched] — [worldlabs-api-examples](https://github.com/worldlabsai/worldlabs-api-examples)
- Webhooks: one press summary says the API is "fully asynchronous, with a callback when the world is ready." Every official excerpt I saw uses polling only. [2nd-hand / UNVERIFIED] — [blockchain.news summary](https://blockchain.news/ainews/world-labs-launches-world-api-to-integrate-marble-ai-into-products-and-workflows)
- An OpenAPI snapshot is published inside World Labs' agent skill ("OpenAPI snapshot for client generation, world generation, uploads, and polling"). [DOCS-via-search] — [Agent skill page](https://docs.worldlabs.ai/api/agent-skill). I could not read the snapshot because `get_file_contents` was denied (repo not allow-listed) and the fetched `worldlabsai/skills` tree showed only `skills/worldlabs` and `skills/atlas-blender`. [GH-fetched] — [worldlabsai/skills](https://github.com/worldlabsai/skills)
- A separate beta surface, "Atlas" (see Q6), uses a different base URL, `https://api.atlas-beta.worldlabs.ai/api/v2`, with task-style endpoints (`tasks:images2PosedRGBD`, `tasks:atlasGenerate`). [GH-fetched] — [atlas-camera-studio](https://github.com/worldlabsai/atlas-camera-studio)

### Inferences
- The `:verb` suffix style (`worlds:generate`, `worlds/{id}:export`, and `tasks:atlasGenerate` in the Atlas API) points to Google-AIP-style custom methods and long-running operations. A generic OpenAPI generator or a poll loop over `operation.done` should fit. This is a style inference, not documented.
- Because polling is free and generation takes about 5 minutes, a pipeline can poll every 10 to 15 seconds without cost. The only throttle to design around is generation starts per minute (see Q4).
- Two env-var names (`WLT_API_KEY` vs `WORLDLABS_API_KEY`) are only client conventions. The wire header is `WLT-Api-Key` in both.

### Gaps
- Exact HTTP path and pagination parameters for "List worlds," the media-asset upload endpoints (needed for image, video and multi-image inputs when not using a URI), and the `permission` field's allowed values and defaults. These were not visible in any excerpt.
- Whether a webhook or callback mechanism exists (only a single press mention).
- The full OpenAPI document. Docs host was unreachable, and the skill repo was not readable with the available tools.
- Max image and video sizes, durations and formats for inputs.

---

## 2. What assets does a generated world return, and what are the formats and coordinate conventions?

### Takeaway
A world returns SPZ Gaussian splats at three densities (100k, 500k, full-res about 2M), a GLB collider mesh, and a panorama image. On-demand `:export` gives a PLY splat conversion and higher-quality GLB meshes. Splats are in arbitrary model units, and `semantics_metadata` (`metric_scale_factor`, `ground_plane_offset`) is the way to get metric, ground-aligned placement. Axis convention is contradictory in the sources I saw: older guidance says OpenCV (+x left, +y down, +z forward); a release note says exports switched to OpenGL. Test an import with a known asset before trusting either. I found nothing on SH degree.

### Cited Findings
- World object assets fields: `assets.imagery.pano_url` (panorama image present on every generation), `assets.splats.spz_urls` (SPZ files at 100k, 500k and full-resolution; keys `100k`, `500k`, `full_res`), `assets.splats.semantics_metadata` (per-world scale and ground-plane values, e.g. `metric_scale_factor`, `ground_plane_offset`), `assets.mesh.collider_mesh_url` (GLB collider mesh). [DOCS-via-search] — [llms-full.txt](https://docs.worldlabs.ai/llms-full.txt), [Quickstart](https://docs.worldlabs.ai/api), [Get a world](https://docs.worldlabs.ai/api/reference/worlds/get)
- The collider mesh is described as roughly 100k to 200k triangles. [DOCS-via-search / 2nd-hand] — [Export file specs](https://docs.worldlabs.ai/marble/export/specs), [mixed-source summary](https://docs.worldlabs.ai/api)
- Export endpoint: `POST /marble/v1/worlds/{world_id}:export`. A PLY request looks like `{"asset_type":"splats","format":"ply","resolution":"full_res"}`. The response is an operation. PLY conversions usually come back already `done: true` with a signed URL in `response.url`. Mesh exports are asynchronous, so poll `/marble/v1/operations/{operation_id}`. The FAQ describes export as converting a world's SPZ splats into a cached `.ply` download. [DOCS-via-search] — [FAQ](https://docs.worldlabs.ai/api/faq), [Exporting from Marble](https://docs.worldlabs.ai/marble/export/gaussian-splat/index)
- `assets.mesh.hq_mesh_url` appears after a mesh export (`asset_type: "mesh"`, `format: "glb"`). A third-party skill lists the option space as `asset_type` splats|mesh, `format` ply|glb, `resolution` full_res|500k|150k|100k, `mesh_variant` textured|vertex_colored. This option list is NOT confirmed by official excerpts, and the splat tiers (150k vs 100k) are inconsistent with `spz_urls` keys. [DOCS-via-search + 2nd-hand] — [FAQ](https://docs.worldlabs.ai/api/faq), [world-labs-export skill](https://agent-skills.md/skills/cloudai-x/world-labs-skills/world-labs-export)
- Export file specs page (Marble app and shared docs):
  - Splats are offered as SPZ and PLY, with full-res about 2M splats and low-res about 500k.
  - SPZ is Marble's native, size-optimised splat format. PLY is uncompressed and works in more splat software.
  - The high-quality mesh comes as two GLBs: about 600k triangles with texture, and about 1M triangles with vertex colours.
  - HQ mesh generation takes up to an hour and is rate limited to 4 requests per hour per user.
  - [DOCS-via-search] — [Export file specs](https://docs.worldlabs.ai/marble/export/specs)
- Scale and units: generated splats are in arbitrary model units, not metres. Use `semantics_metadata` (`metric_scale_factor`, `ground_plane_offset`) to place them in metric, ground-aligned space. One developer write-up, citing World Labs' rendering guide, notes this step is not done by default in every tool. [DOCS-via-search + 2nd-hand] — [Export file specs](https://docs.worldlabs.ai/marble/export/specs), [worldspec](https://github.com/3-rt/worldspec)
- Axis convention, older guidance: "default world labs worlds are in OpenCV coordinate system (+x left, +y down, +z forward)". For OpenGL-style DCC tools, World Labs suggests scaling Y and Z by -1 (X unchanged) if the splat appears upside-down. [DOCS-via-search] — [Exporting from Marble](https://docs.worldlabs.ai/marble/export/gaussian-splat/index)
- Axis convention, newer release note: release notes say worlds now export in the OpenGL coordinate system rather than OpenCV for splats and meshes, and SPZ exports default to SPZ v2 (v3 is opt-in). I could not see the date of that release note. [DOCS-via-search] — [Release notes](https://docs.worldlabs.ai/marble/release-notes)
- Known issue: 500k SPZ files need conversion to PLY before importing into Unity. [DOCS-via-search] — [Export file specs](https://docs.worldlabs.ai/marble/export/specs); Unity export guide: [Exporting to Unity](https://docs.worldlabs.ai/marble/export/gaussian-splat/unity)
- Blender 5.3 (not yet final as of the sources; one source expects 10 Nov 2026) adds native 3D Gaussian splat import and rendering for PLY and SPZ, but not splat export. Blender's release notes describe the splat convention as "Z as the Forward Axis, -Y as Up axis" and say the SPZ importer converts to Blender's convention, though some software does not save SPZ in that convention so manual adjustment may be needed. [2nd-hand, Blender dev docs] — [Blender 5.3 rendering notes](https://developer.blender.org/docs/release_notes/5.3/rendering/), [Cinevva](https://app.cinevva.com/news/2026-09-16-blender-5-3-gaussian-splats), [Digital Production](https://digitalproduction.com/2026/09/22/blender-5-3-brings-gaussian-splats-home/)
- Python SDK repo has local-asset examples: load SPZ into `Gaussian3D` (`examples/load_splat.py`), render a turntable (`examples/render_video.py`, needs CUDA gsplat), export PLY (`examples/export_ply.py`). [GH-fetched] — [worldlabs-api-python](https://github.com/worldlabsai/worldlabs-api-python)
- Asset URLs are signed or expiring. A third-party project relies on stable world IDs to refresh them. [2nd-hand] — [sceneview PR #3751](https://github.com/sceneview/sceneview/pull/3751)
- Isaac Sim import of Marble worlds is covered by a third-party guide, and press tied the World API to Isaac Sim integration. [2nd-hand] — [Medium Isaac Sim guide](https://medium.com/@geedhpruthvi/from-imagination-to-simulation-a-complete-guide-to-importing-world-labs-marble-models-into-nvidia-69dde0ed5d6e), [Announcing summary](https://blockchain.news/ainews/world-labs-launches-world-api-to-integrate-marble-ai-into-products-and-workflows)

### Inferences
- **Axis table for planning (general engine knowledge, not from World Labs; verify with a test import):**

  | Target | Up | Handedness | Unit |
  |---|---|---|---|
  | Blender | Z-up | right-handed | metres |
  | three.js | Y-up | right-handed | by convention metres |
  | Unreal | Z-up | left-handed | cm |
  | Unity | Y-up | left-handed | m |

  If the current export really is OpenGL-style (Y-up, right-handed, camera looks down -Z), then three.js and Spark need no axis change, Blender needs a +90 degrees about X rotation, and Unity needs an X (or Z) mirror for handedness. Unreal needs a Z-up remap, a handedness flip and 100x scale after applying `metric_scale_factor`. If the file is still OpenCV (+y down, +z forward), then apply the documented Y and Z negation first. Because the docs contradict each other, treat the axis convention as something to detect, not assume.
- Metric scale: apply `metric_scale_factor` first (model units to metres), then offset by `ground_plane_offset`, then do the engine axis and unit conversion. Unreal then needs x100.
- The 100k, 500k and full-res SPZ tiers map naturally to a web-streaming LOD ladder (100k for mobile/preview, 500k for default web, full-res for desktop). Spark 2.0 `.RAD` is a streaming format, but I found no evidence that the API returns `.RAD` (see Q5).
- If Blender 5.3 is used for splat import, be aware of the -Y up / +Z forward splat convention in Blender's importer; do the SPZ conversion check there rather than rotating blindly.

### Gaps
- Spherical-harmonics degree, per-splat attribute layout, and compression parameters for Marble's SPZ and PLY files. Not in any excerpt.
- The exact current axis convention of API outputs (OpenCV vs OpenGL), plus the date of the OpenGL switch.
- Thumbnail, depth map and caption/metadata fields on the world object. Only `assets.imagery.pano_url`, `splats`, `mesh` were visible. The `world_prompt` and `semantics_metadata` shape beyond two fields was not visible.
- Whether `:export` is gated by plan or credits on the API. The app docs say HQ mesh and commercial rights need the Pro plan; one third-party source says mesh export costs 3,500 credits ($2.80). Conflicting and unconfirmed (see Q4).
- Whether glTF with `KHR_gaussian_splatting` or USD export exists. Nothing found.
- Equirectangular pano resolution and aspect for `assets.imagery.pano_url`.

---

## 3. Which models are available, and what controls and conditioning exist?

### Takeaway
Valid `model` values are `marble-1.0-draft`, `marble-1.0`, `marble-1.1` and `marble-1.1-plus` (Marble 1.1 and 1.1 Plus launched 2 Apr 2026). `seed` is a top-level integer and `disable_recaption` exists for text prompts. I found no negative prompt, no official camera/pose-conditioning field in the Marble API, and no editing endpoint beyond `:export` and the app-only Expand. The Chisel depth-PNG example in the official repo suggests structured 3D conditioning is possible through the API, but the reference fields for it were not visible.

### Cited Findings
- Valid `model` values per the FAQ: `marble-1.0-draft`, `marble-1.0`, `marble-1.1`, `marble-1.1-plus`. An invalid value is a common cause of HTTP 400. [DOCS-via-search] — [FAQ](https://docs.worldlabs.ai/api/faq)
- Default model conflict. The Models page says the API defaults to `marble-1.0` when `model` is omitted and will change to `marble-1.1` in a future release (so set `model` explicitly). A different excerpt says the generate reference's default is `marble-1.1`. [DOCS-via-search, internally conflicting] — [Models](https://docs.worldlabs.ai/api/models), [Generate reference](https://docs.worldlabs.ai/api/reference/worlds/generate)
- Marble 1.1 (released 2 Apr 2026) improves lighting and contrast and reduces visual artifacts. Marble 1.1-Plus is "built for scale," producing larger, more complex environments. Both were rolled out the same day and are on the API. [2nd-hand, citing official X post] — [World Labs on X](https://x.com/theworldlabs/status/2041554646561677701), [Radiance Fields](https://radiancefields.com/world-labs-releases-marble-1.1-and-marble-1.1-plus)
- 1.1-Plus adds "dynamic cubes," an auto-expansion mechanism that detects when a scene needs more space and adds up to five additional spatial units in one generation pass. [2nd-hand] — [Radiance Fields](https://radiancefields.com/world-labs-releases-marble-1.1-and-marble-1.1-plus), [NYU RITS](https://rits.shanghai.nyu.edu/ai/world-labs-releases-marble-1-1-auto-expanding-3d-world-generation/)
- `marble-1.0-draft` is the fast, cheap tier (150 credits, vs 1,500 for standard). [DOCS-via-search] — [Rate limits](https://docs.worldlabs.ai/api/rate-limits), [Pricing](https://docs.worldlabs.ai/api/pricing)
- Generation time: docs say each accepted world generation usually takes about 5 minutes. I found no per-model time table for 1.1 or 1.1-Plus. [DOCS-via-search] — [Rate limits](https://docs.worldlabs.ai/api/rate-limits)
- `seed` is a top-level integer in the request (docs example uses `seed: 42`). Its documented determinism guarantees were not visible. `tags` and `display_name` are free-form metadata. [DOCS-via-search] — [Generate reference](https://docs.worldlabs.ai/api/reference/worlds/generate)
- Negative prompt: no field found in official docs. A forum post claims Marble has no negative prompt and does not respond to negation in the positive prompt. [2nd-hand / UNVERIFIED] — [Hugging Face forum](https://discuss.huggingface.co/t/suppressing-unwanted-content-without-negative-conditioning-cross-scene-consistency-in-3dgs-and-data-driven-artwork-placement-on-generated-walls/178921)
- Multi-image control is the only documented spatial conditioning in the generate reference: optional `azimuth` per image in `multi_image_prompt`. [DOCS-via-search] — [Quickstart](https://docs.worldlabs.ai/api)
- Chisel (3D blocking tool in the Marble app) has an official API-side example: `web-chisel-depth-png/` "prepares depth pano PNG inputs for Chisel." The README does not say which API field consumes them. [GH-fetched] — [worldlabs-api-examples](https://github.com/worldlabsai/worldlabs-api-examples)
- App-side (not confirmed as API) editing features, from a third-party skill repo: Studio "Compose, Record, Expand" and Chisel. [2nd-hand] — [CloudAI-X/world-labs-skills](https://github.com/CloudAI-X/world-labs-skills). The release notes of one third-party source credit "Expand" and HQ mesh export to the Pro plan. [2nd-hand] — [Export search excerpt](https://docs.worldlabs.ai/marble/export/gaussian-splat/index)
- Official open-source helper for inpainting inputs: `marble-multiview-inpainting` ("tools for preparing consistent multiview inputs for Marble inpainting"), created 15 Sep 2026. This implies an inpainting workflow exists, but it is not documented in the excerpts I saw. [GH-fetched via search_repositories metadata] — [worldlabsai/marble-multiview-inpainting](https://github.com/worldlabsai/marble-multiview-inpainting)

### Inferences
- Plan on `marble-1.0-draft` for iteration loops (about 10x cheaper) and `marble-1.1` or `marble-1.1-plus` for finals. Always pass `model` explicitly because the default is documented inconsistently and scheduled to change.
- Cost is unbounded above 1,500 only for `marble-1.1-plus`. A budget guard should assume 3,000 credits per Plus world (see Q4).
- For camera/pose-conditioned or longer-range control via the Marble API, there is nothing documented. The only such capability found is the separate Atlas beta API (Q6).

### Gaps
- Per-model generation times, output resolution options (splat counts are fixed per tier), and exact `seed` semantics.
- Whether Chisel/depth-pano conditioning, inpainting and Expand are exposed as public API request fields (they are in the app and in official examples, but I did not see request schemas).
- Content-policy details that cause the `400` "policy violation."
- Upload endpoint names for media assets (see Q1).

---

## 4. Pricing, credits, rate limits, licensing, content policy and data retention

### Takeaway
Credits cost $1.00 per 1,250 ($0.0008 each), minimum purchase $5.00 / 6,250 credits, and API credits do not expire and are separate from Marble app credits. Standard worlds cost 1,500 credits (about $1.20); text prompts add an 80-credit pano step; draft is 150; Plus is 1,500 base plus 0 to 1,500 variable (300 per extra cube, per press). Default rate limit is about 3 starts/min and 60/hr. The Terms give paid-account users ownership of outputs with an attribution-on-request clause, but the API-specific commercial terms and retention periods are not confirmed.

### Cited Findings
- Credit price: $1.00 USD per 1,250 credits; minimum purchase 6,250 credits ($5.00). API credits do not expire. Credits bought for the Marble app at marble.worldlabs.ai CANNOT be used with the API. Auto-refill is configurable on the billing page. [DOCS-via-search] — [Pricing](https://docs.worldlabs.ai/api/pricing)
- Per-generation costs (standard `marble-1.0` / `marble-1.1`): the world-generation usage event is 1,500 credits. Table as excerpted: image (pano) = 0 pano + 1,500 world = 1,500 total; text = 80 pano + 1,500 world = 1,580 total. Image prompts skip the pano event when a valid panorama is detected. `marble-1.0-draft` = 150 credits. [DOCS-via-search] — [Pricing](https://docs.worldlabs.ai/api/pricing), [Models](https://docs.worldlabs.ai/marble/models)
- `marble-1.1-plus`: always 1 world-generation event at 1,500 credits, with variable extra cost; the models page describes "1,500 base cost + 0-1,500 variable world generation cost." Press says the variable part is 300 credits per additional dynamic cube (5 cubes x 300 = 1,500). I did not see exact Plus totals for text/image/multi-image/video inputs. [DOCS-via-search + 2nd-hand] — [Pricing](https://docs.worldlabs.ai/api/pricing), [Models](https://docs.worldlabs.ai/marble/models), [Radiance Fields](https://radiancefields.com/world-labs-releases-marble-1.1-and-marble-1.1-plus)
- OUTDATED third-party numbers: the CloudAI-X skills repo lists "Marble 0.1-plus" at ~5 min / 1,500 to 1,600 credits and "Marble 0.1-mini" at 30 to 45 s / 150 to 250 credits, with per-input credit costs (text 1,580/230, image 1,580/230, panorama 1,500/150, multi-image 1,600/250, video 1,600/250). These model names do not match the current official values and should not be used for budgeting. [2nd-hand, stale] — [CloudAI-X/world-labs-skills](https://github.com/CloudAI-X/world-labs-skills)
- Mesh export cost: one secondary source says a mesh export costs 3,500 credits ($2.80). Not confirmed by any official excerpt. [2nd-hand / UNVERIFIED] — [Export search excerpt](https://docs.worldlabs.ai/marble/export/gaussian-splat/index)
- Rate limits: default about 3 world-generation starts per minute and 60 per hour. Approved higher-throughput accounts get about 30 standard starts/min and about 90 draft starts/min. Limits apply per API user or account, not per key, are tracked in rolling windows and are approximate. On 429, pause and honour `Retry-After`. A start that returns 429 was not accepted. A start that succeeds returns an Operation, so poll it and do not resubmit. Higher limits are requested by emailing account email, models, expected starts per minute/hour, and burst vs sustained. [DOCS-via-search] — [Rate limits](https://docs.worldlabs.ai/api/rate-limits)
- HQ mesh exports have their own limit: 4 requests per hour per user, up to 1 hour processing (Marble export specs page). [DOCS-via-search] — [Export file specs](https://docs.worldlabs.ai/marble/export/specs)
- Terms of Service (two versions exist, at `docs.worldlabs.ai/terms-of-service` and `worldlabs.ai/terms-of-service`, with different section numbering):
  - Free accounts get a revocable, non-exclusive licence limited to personal, non-commercial use of outputs.
  - "Paid Account Users own all rights, title, and interest in and to Outputs generated through their use of the Services, excluding World Labs' Products, technology, proprietary or Confidential Information, and intellectual property."
  - Paid users shipping API output in customer-facing apps may license it to end users, subject to restrictions on downstream sublicensing, attribution and usage volume.
  - "upon World Labs' reasonable request, Paid Account Users shall include attribution to World Labs as the service provider for public or commercial distribution."
  - Use of outputs is at the user's own risk with no warranty.
  - The ToS caching clause says caching may not exceed retention periods in the applicable Order Form.
  - [2nd-hand paraphrase of ToS via search; I did not read the ToS verbatim] — [Terms (docs)](https://docs.worldlabs.ai/terms-of-service), [Terms (www)](https://www.worldlabs.ai/terms-of-service)
- Training on user content: one analysis reports ToS section 3.6 grants World Labs a licence to use User Content for "training of World Labs AI Models" (irrevocable for free accounts; paid users can opt out only going forward). Unverified against the ToS text. [2nd-hand / UNVERIFIED] — [Search excerpt of ToS analyses](https://www.worldlabs.ai/terms-of-service)
- Marble app plans (consumer): commercial rights reportedly only from the Pro plan (about $35/mo), not Standard (about $20/mo). This is the app, not the API. [2nd-hand] — [Export docs excerpt](https://docs.worldlabs.ai/marble/export/gaussian-splat/index), [Rundown](https://www.therundown.ai/tools/marble), [App pricing](https://marble.worldlabs.ai/pricing)
- A BERI article claims the terms already allow World Labs to end the service at any time. Unverified. [2nd-hand / UNVERIFIED] — [BERI](https://www.beri.net/article/amd-world-labs-acquisition-marble-world-api-continuity-world-model-hardware-lock-in)

### Inferences
- Dollar math (derived from the official credit rate): 1 credit = $0.0008. Draft 150 = $0.12; standard image 1,500 = $1.20; standard text 1,580 = $1.264; Plus worst case if text-prompted: 80 + 1,500 + 1,500 = 3,080 = about $2.46 (a third party said about $2.48; the small difference is arithmetic or rounding). These are my derivations, not published figures.
- At 3 starts/min and 60/hr, a default account can launch at most 60 worlds an hour, which is about $72/hr at standard cost. A batch pipeline should throttle to about 1 start per 20 s.
- Each `:export` call may add cost. Do not assume splat PLY conversion is free until confirmed against the pricing page.
- Because two ToS versions exist and API commercial language differs from the app tiers, get written confirmation from World Labs for any shipped commercial product, in particular around attribution, sublicensing and the `permission` setting.

### Gaps
- Full Plus pricing table, the cost (if any) of `:export`, and whether polling `GET /worlds/{id}` is free.
- Free tier or trial credits for the API (none found).
- Data retention duration for generated worlds and uploaded inputs, and how long signed asset URLs last.
- Content policy specifics (only "policy violation" 400 mentioned).
- Meaning of the `permission` request field (public vs private worlds?).
- ToS text itself was not read verbatim.

---

## 5. SDKs, clients, Spark, MCP servers, plugins and integrations

### Takeaway
Official: a Python client (`worldlabs-api-python`, MIT), Node.js and Python example scripts, an agent-skills plugin (Codex and Claude Code) that includes an Atlas Blender add-on workflow, and Spark (open-source three.js splat renderer). No official JS/TS SDK, Unity, Unreal or Omniverse plugin found. Third parties have built MCP servers, a Unity editor client, a TanStack AI adapter and Isaac Sim guides.

### Cited Findings
- `worldlabsai/worldlabs-api-python`: Python 3.12+, `uv sync`, sync and async clients, MIT. CUDA GPU only needed for gsplat rendering. 24 stars. [GH-fetched] — [worldlabs-api-python](https://github.com/worldlabsai/worldlabs-api-python)
- `worldlabsai/worldlabs-api-examples`: Node.js and Python CLI scripts for text and image to world (`generate-world-from-text.js|py`, `generate-world-from-image.js|py`, `igloo.jpg`), a web app `web-generate-world/` (port 3000), and `web-chisel-depth-png/` (port 3001). README warns not to embed API keys client-side. MIT. No Spark, three.js or Blender examples mentioned. [GH-fetched] — [worldlabs-api-examples](https://github.com/worldlabsai/worldlabs-api-examples)
- `worldlabsai/skills` ("Agent skills for building with World Labs", Apache-2.0, created 5 Oct 2026): one plugin for Codex and Claude Code with two skills, `worldlabs` (image generation/editing, camera and depth estimation, API task and asset management; uses a CLI that needs Node.js 24+ and an API key, with `worldlabs tasks list --json`) and `atlas-blender` (Blender scene work; requires Blender 5.1+, the Atlas add-on and Python 3.10+; pose and generation need an API key). [GH-fetched] — [worldlabsai/skills](https://github.com/worldlabsai/skills)
- Separate earlier official skill repo name seen in docs search: `worldlabsai/marble-developer-api-skill` (agent skill with API guidance and OpenAPI snapshot). I could not open it. [DOCS-via-search] — [Agent skill page](https://docs.worldlabs.ai/api/agent-skill)
- Spark 2.0 (open source, by World Labs, released about 14 to 15 Apr 2026): three.js / WebGL2 3DGS renderer with a streamable level-of-detail system, a hierarchical splat tree, per-frame splat budget (typically 500K to 2.5M depending on device), GPU memory paging, and a `.RAD` format with precomputed LoD trees and HTTP Range requests for progressive loading. Press claims 100M+ splats in-browser. Developed alongside Marble. Numbers other than the LoD and `.RAD` design come from press, not the repo. [2nd-hand citing official blog] — [Streaming 3DGS worlds on the web (Spark 2.0)](https://www.worldlabs.ai/blog/spark-2.0), [Radiance Fields](https://radiancefields.com/world-labs-previews-spark-2.0), [VP Land](https://www.vp-land.com/p/world-labs-streams-3d-gaussian-splatting-worlds-on-the-web-with-spark-2-0)
- Third-party MCP servers for the Marble API:
  - [sandraschi/worldlabs-mcp](https://github.com/sandraschi/worldlabs-mcp): FastMCP 3.2 server plus web app, with a "DCC Export" pipeline for Blender, Unity3D and Resonite. The completeness of the Blender export was not verified.
  - [jkoets/Marble-WorldLabs-MCP-Server](https://github.com/jkoets/Marble-WorldLabs-MCP-Server): Node MCP server for text/image/video/multi-image generation.
  - [sceneview PR #3751](https://github.com/sceneview/sceneview/pull/3751): adds `generate_world` as a BYOK Marble tool to the SceneView MCP.
  - [2nd-hand]
- Unity: `DakkuaDev/unity-worldlabs.ai-API-client-tool`, a Unity 6 editor tool that generates and imports Gaussian splat environments from a text prompt, with scene hierarchy, collider mesh and coordinate-system correction. [2nd-hand] — [DakkuaDev/unity-worldlabs.ai-API-client-tool](https://github.com/DakkuaDev/unity-worldlabs.ai-API-client-tool)
- TanStack AI has a `worldlabs` adapter (lists Marble model IDs; waits for completion). [2nd-hand] — [TanStack AI adapter](https://tanstack.com/ai/latest/docs/adapters/worldlabs.md)
- Webhooks: none found in official material (see Q1). Isaac Sim: press tied the World API launch to Isaac Sim integration, and a Medium guide covers the manual import. No official Omniverse, Unreal or Roblox plugin found. [2nd-hand / UNVERIFIED for official status]

### Inferences
- For a Blender to engines pipeline, the realistic official-adjacent path is: Python client (or raw REST) to get SPZ/PLY/GLB, then import to Blender 5.3 (native splat import) or via a splat add-on, and use the GLB collider mesh in-engine. The `atlas-blender` skill is the only World Labs-authored Blender integration found, and it targets Atlas, not Marble, so it is not directly usable for Marble worlds without checking.
- No JS/TS SDK means a TS pipeline should generate a client from the OpenAPI snapshot or call REST directly. The poll loop is simple.

### Gaps
- Contents of `worldlabsai/marble-developer-api-skill` and the OpenAPI snapshot (not readable).
- Official Spark docs/repo not checked directly (`sparkjs.dev`, `sparkjsdev/spark`), so the integration path for Marble SPZ to Spark and any `.RAD` conversion is unconfirmed.
- Whether the Atlas Blender add-on has any Marble-world support.
- Existence of any official Unity/Unreal/Omniverse/Roblox plugin (none found).

---

## 6. Roadmap: what World Labs has said about upcoming API features

### Takeaway
There is no published API roadmap. What exists is: (a) Atlas, an "omni world model" announced 1 Sep 2026 with early/beta access (video with camera control, 3D depth/point cloud/splat outputs) on a separate beta API, which press says is expected to power future Marble versions; (b) a planned default-model change to `marble-1.1`; and (c) corporate uncertainty from the AMD acquisition announced 28 Sep 2026. I found no World Labs statements about real-time/RTT streaming, physics, USD or `KHR_gaussian_splatting` in the sources I reached.

### Cited Findings
- Atlas: announced 1 Sep 2026 (per most sources) as an "omni world model," in early access with select partners via a request form, with no announced pricing, partner names, paper or GA date. Camera-controlled generation takes camera geometry as a native input and returns up to one minute of video at 1440p from one or more input images (one source: one to six reference images plus a manually designed camera path). It operates on 2D frames and 3D depth maps, so worlds can be written out as point clouds or splats. Described as a multimodal autoregressive diffusion transformer (rectified flow). Press says it is expected to power future versions of Marble. [2nd-hand] — [Radiance Fields](https://radiancefields.com/world-labs-announces-new-world-model-atlas), [AI Weekly](https://aiweekly.co/alerts/world-labs-debuts-atlas-an-omni-world-model-in-early-access), [Kingy AI](https://kingy.ai/blog/world-labs-atlas-world-model-deep-dive/), [howaiworks](https://howaiworks.ai/blog/world-labs-atlas-world-model-2026)
- Atlas beta rollout reportedly began 15 Oct 2026 via waitlist (emails when access is available). [2nd-hand] — [Spatial Insiders](https://spatialinsiders.com/stories/world-labs-atlas-beta-rollout). Another source dated the announcement October rather than 1 Sep; one search summary said 1 Sep. The rollout date and announcement date are probably different events, but I did not confirm.
- Atlas API surface (beta): base `https://api.atlas-beta.worldlabs.ai/api/v2`; tasks `tasks:images2PosedRGBD` (depth from an image; returns an operation) and `tasks:atlasGenerate` (frames from posed cameras). Keys come from a developer portal with task creation, operation reading and asset creation/reading permissions. Access is gated by waitlist and "API-enabled World Labs beta account." The sample app produces a four-second MP4 from 48 interpolated cameras at 1280x720 (16:9), with outputs expiring after 7 days. [GH-fetched] — [atlas-camera-studio](https://github.com/worldlabsai/atlas-camera-studio)
- "Marble 5" naming: the atlas-camera-studio repo description says "powered by the Marble 5 API." I found no official announcement of a "Marble 5" model, and other analysis says the public API lists only Marble models (no `atlas` entry in the `model` enum). [GH-fetched; naming UNVERIFIED] — [atlas-camera-studio](https://github.com/worldlabsai/atlas-camera-studio), [Search summary](https://kingy.ai/blog/world-labs-atlas-world-model-deep-dive/)
- Marble 1.0 to 1.1 default change: the Models page says omitted `model` currently defaults to `marble-1.0` and "will change to marble-1.1 in a future release." [DOCS-via-search] — [Models](https://docs.worldlabs.ai/api/models)
- AMD acquisition: AMD agreed to buy World Labs in an all-stock deal valued at about $8.2B, announced around 28 Sep 2026 (signing reported 26 Sep in some outlets), expected to close by end of 2026 pending regulatory approval. Fei-Fei Li would become AMD's EVP and chief scientist. Reporting says neither announcement addresses Marble or the World API's future, pricing, shutdown or customer migration. [2nd-hand] — [CNBC](https://www.cnbc.com/2026/09/28/amd-fei-fei-li-world-labs.html), [Yahoo Finance](https://finance.yahoo.com/technology/ai/articles/amd-acquires-ai-legend-fei-093000475.html), [Acquiry](https://www.acquiry.com/deal-intelligence/amd-to-acquire-world-labs-for-8-2-billion/), [AI News](https://www.artificialintelligence-news.com/news/amd-world-labs-world-models-enterprise/)
- Earlier funding context: a $1B raise was reported alongside the World API launch. [2nd-hand] — [IK3D](https://ik3d.fr/world-labs-raises-1b-and-drops-the-world-api-spatial-intelligence-just-became-programmable/)
- One secondary source notes there is "no published roadmap" for further Marble/API releases. [2nd-hand] — [search-result summary of Radiance Fields / release notes](https://docs.worldlabs.ai/marble/release-notes)

### Inferences
- A plausible near-term shape (inference only): Atlas capabilities (camera-conditioned video, depth/point-cloud/splat outputs) may surface in the main World API, and the default model will move to `marble-1.1`. Neither has a date.
- The AMD deal adds vendor and continuity risk for a pipeline. A prudent design keeps the generation call behind an adapter interface and caches all downloaded assets locally, since signed URLs expire and terms or pricing could change after closing (expected by 31 Dec 2026).
- Dynamic scenes, RTT/real-time streaming, physics and robotics-sim items from the brief were not mentioned in any source I reached. That is absence of evidence only; I did not read the World Labs blog index or X feed in full.

### Gaps
- World Labs' own statements on real-time/interactive worlds, dynamic scenes, physics, agents/robotics sim, larger worlds beyond 1.1-Plus cubes, enterprise offerings, and USD / `KHR_gaussian_splatting` export. Not found.
- The primary Atlas announcement text and the Atlas docs pages (`atlas-beta.worldlabs.ai/docs/*`), which were unreachable.
- Whether Atlas will be exposed under `marble/v1` or stays on `/api/v2`, and any Atlas pricing (only the Camera Studio sample's own pack prices: 3 generations for $5, 12 for $20, 60 for $100, which are that app's prices, not World Labs' API rates).
- Primary CNBC article text (host unreachable); deal details come from search excerpts.

---

## 7. Community and third-party tooling

### Takeaway
There is a small but active ecosystem: MCP servers, a Unity editor client, spatial QA and conversion tools, agent-skill packs and Isaac Sim guides. Quality is uneven and several repos carry stale model names. No official Blender add-on for Marble was found; official Blender work is the Atlas-focused `atlas-blender` skill.

### Cited Findings
- [sandraschi/worldlabs-mcp](https://github.com/sandraschi/worldlabs-mcp): FastMCP 3.2 server and webapp wrapping the Marble API (text, images, video), with docs files such as `SPARK_V2.md`, `WORLD_MODELING.md`, `COMPETITION.md`, and a stated DCC export pipeline (Blender, Unity3D, Resonite). Setup via `just bootstrap` and `just serve`. [2nd-hand]
- [jkoets/Marble-WorldLabs-MCP-Server](https://github.com/jkoets/Marble-WorldLabs-MCP-Server) (also on [Glama](https://glama.ai/mcp/servers/jkoets/Marble-WorldLabs-MCP-Server)): Node MCP server giving Claude Marble API access. [2nd-hand]
- [sceneview PR #3751](https://github.com/sceneview/sceneview/pull/3751): `generate_world` BYOK tool for World Labs Marble in the SceneView MCP. [2nd-hand]
- [DakkuaDev/unity-worldlabs.ai-API-client-tool](https://github.com/DakkuaDev/unity-worldlabs.ai-API-client-tool): Unity 6 editor middleware, imports splats plus collider with coordinate correction. [2nd-hand]
- [3-rt/worldspec](https://github.com/3-rt/worldspec): "Spatial QA for World Labs Marble worlds"; handles metric-scale and ground-plane use of `semantics_metadata`. [2nd-hand]
- [leftysplat/splatworld (DeepWiki: Marble client and 3D conversion)](https://deepwiki.com/leftysplat/splatworld/6.3-marble-client-and-3d-conversion): Marble client plus 3D conversion pipeline. [2nd-hand]
- [CloudAI-X/world-labs-skills](https://github.com/CloudAI-X/world-labs-skills): eight Claude Code skills (api, text-prompt, image-prompt, multi-image, pano-video, chisel, studio, export), MIT. Uses outdated "0.1-plus/mini" model names and credit numbers. [2nd-hand, stale]
- DEV Community write-up on the real cost of one image-to-3D world ("image-blaster"). [2nd-hand] — [DEV article](https://dev.to/tiaforge/image-blaster-the-real-cost-of-one-image-3d-world-1n4d)
- Isaac Sim import guide (Medium). [2nd-hand] — [Medium](https://medium.com/@geedhpruthvi/from-imagination-to-simulation-a-complete-guide-to-importing-world-labs-marble-models-into-nvidia-69dde0ed5d6e)
- Game example: "STARSPEED," described as built with Marble, Spark.js, Blender and three.js with 100M+ splat environments. [2nd-hand] — [search summary of Spark 2.0 coverage](https://www.worldlabs.ai/blog/spark-2.0)
- Official demo/sample apps: `atlas-camera-studio` (63 stars) and `worldlabs-api-examples` (40 stars). [GH-fetched metadata] — [worldlabsai org search](https://github.com/worldlabsai)

### Inferences
- The most reusable third-party pieces for a Blender-bound pipeline are the Unity tool's coordinate-correction logic and `worldspec`'s metric-scale handling, as references for how others apply `semantics_metadata`. I did not inspect their code.

### Gaps
- I did not read any third-party repo's code, test coverage or licences, except what search summaries state.
- No official or well-known community Blender add-on specifically importing Marble worlds (SPZ/PLY plus GLB collider) was identified. Blender 5.3's native splat import may make one unnecessary.
- Reddit, Hacker News, Discord and YouTube tutorials were not searched.
