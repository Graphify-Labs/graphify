# Marble (World Labs) technology deep dive: generation pipeline, 3D representations, and relation to NeRF / 3DGS / feed-forward reconstruction (state of knowledge: 22 October 2026)

**How to read these notes (important for the report writer).**

*Claim labels.* `[official]` = disclosed by World Labs (WL) itself (blog, docs, GitHub, X posts, founder interviews). `[inferred]` = my reasoning from cited evidence. `[speculative]` = plausible but weakly supported. `[literature]` = published third-party research (not WL), used for lineage and fundamentals.

*Verification markers.*
- `V:direct` = I fetched and read the page text myself (only github.com pages were fetchable).
- `V:snippet` = WL page content as quoted in a web-search summary. I did not open the page myself.
- `V:3rd` = third-party article, blog or aggregator.
- `V:memory` = from my background knowledge; the URL is the canonical paper/repo but I could not re-fetch it. `V:memory` arXiv IDs are marked with a dagger (†).

*Source-access limitation.* In this session WebFetch failed DNS resolution (`ENOTFOUND`) for worldlabs.ai, docs.worldlabs.ai, sparkjs.dev, arxiv.org, radiancefields.com, techcrunch.com, developer.nvidia.com and latent.space, and a curl attempt was blocked by the sandbox. Only github.com resolved. Consequences:
- WL blog/docs claims are `V:snippet` unless stated otherwise.
- The Spark and WL-GitHub claims are `V:direct` and are the best-verified material here.
- I could not read the Marble launch blog, the Latent Space transcript, or any arXiv paper in full.

*Terminology.* The brief says "RTT"; WL's model is **RTFM (Real-Time Frame Model)**. I assume that is what was meant.

---

## 1. What does World Labs publicly say about Marble's architecture, training, inputs and outputs, and is the splat native or derived?

### Takeaway
WL has disclosed Marble's *interface* in detail: inputs, outputs, export tiers, models and pricing. It has disclosed essentially nothing about the *internal architecture or training data*; I found no Marble paper or tech report. Gaussian splats are WL's primary, highest-fidelity output, and meshes are derived from splats (per WL docs). Whether the generator emits splat parameters directly or produces images/depth that are lifted to splats is **not officially stated**. WL's newer API artifacts (posed RGB-D tasks, depth-conditioned inpainting) point toward a "multi-view/depth first, splats after" design, but that evidence concerns Atlas-era APIs, not Marble 1.x.

### Cited Findings

#### Product and inputs
- [official] Marble launched as a limited beta in Sept 2025 and went generally available on 12 Nov 2025 as WL's first commercial product, with a freemium plan structure. `V:3rd` — [Radiance Fields](https://radiancefields.com/world-labs-formally-launches-marble-a-generative-world-model); [TechCrunch](https://techcrunch.com/2025/11/12/fei-fei-lis-world-labs-speeds-up-the-world-model-race-with-marble-its-first-commercial-product/)
- [official] Marble is described by WL as a multimodal world model that generates 3D worlds from text, a single image, multiple images, video, panoramas, or a coarse 3D layout. `V:snippet`/`V:3rd` — [WL blog "Marble: A Multimodal World Model"](https://www.worldlabs.ai/blog/marble-world-model); [PYMNTS](https://www.pymnts.com/artificial-intelligence-2/2025/world-labs-launches-marble-as-spatial-intelligence-becomes-the-new-ai-battleground)
- [official] Multi-image prompts can assign different views to different parts of a world, and these are merged into one consistent scene. `V:3rd` (summary of the announcement) — [visual-slam-roadmap summary](https://github.com/changh95/visual-slam-roadmap/blob/main/level-11-world-models-spatial-ai/world-labs-marble.md)
- [official] **Chisel** (experimental) separates structure from style. The user blocks out geometry (boxes, planes, a wall tool for room perimeters/heights/doorways, imported GLB/FBX assets). A text prompt then sets the look and fills in missing elements. `V:snippet` of the official docs — [Chisel basics](https://docs.worldlabs.ai/marble/create/chisel-tools/chisel-basics); also [GIGAZINE](https://gigazine.net/gsc_news/en/20251113-marble-multimodal-world-model/), [DeepLearning.AI The Batch](https://www.deeplearning.ai/the-batch/world-labs-makes-its-marble-generative-world-model-public-adds-chisel-editing-tool)
- [official] Post-generation editing (object removal/swap, style changes, restructuring), region-selective **Expand** (adds detail where splats degraded or extends the world), and **Composer** (assembles multiple worlds into a larger space under user-controlled layout). `V:3rd` (announcement summary) — [visual-slam-roadmap summary](https://github.com/changh95/visual-slam-roadmap/blob/main/level-11-world-models-spatial-ai/world-labs-marble.md)
- [official] Videos exported from Marble can be enhanced with added dynamics (smoke, fire, water) while preserving camera path and 3D structure. `V:3rd` — same source. This is video post-processing, not a dynamic 3D asset.

#### Outputs and file specs
- [official] Splats export as **SPZ** ("Marble's native splat format, optimized for file size") or **PLY** (uncompressed, widest tool compatibility), at roughly 2M splats (full-res) or ~500k (low-res). `V:snippet` — [Export file specs](https://docs.worldlabs.ai/marble/export/specs)
- [official] The API response lists splat files under `spz_urls` with keys `500k`, `100k`, `full_res`. Other formats come from a separate `POST /marble/v1/worlds/{world_id}:export` call. `V:snippet` — [API quickstart](https://docs.worldlabs.ai/api)
- [official] A 360° **panorama** is an exportable asset: equirectangular PNG, 2560 × 1280. `V:snippet` — [Export file specs](https://docs.worldlabs.ai/marble/export/specs)
- [official] Two mesh types:
  - A coarse **collider mesh** (GLB, roughly 100–200k triangles per a secondary source) for physics.
  - A **high-quality visual mesh** (GLB). It takes up to an hour to generate, is rate-limited to 4 requests per hour per user, and is gated to the Pro plan; the collider is on the Standard plan.
  `V:snippet` — [Mesh export docs](https://docs.worldlabs.ai/marble/export/mesh); [Export specs](https://docs.worldlabs.ai/marble/export/specs); triangle count from `V:3rd` [invideo.io](https://invideo.io/blog/world-labs-marble-3d-worlds/)
- [official] WL docs state the high-quality meshes are **derived from the splat**, so reconstruction artifacts are expected, and recommend splat export for the cleanest visuals. `V:snippet` — [Mesh export docs](https://docs.worldlabs.ai/marble/export/mesh)
- [official] WL's help text says collider meshes and "mesh baking" are available natively in Marble. `V:snippet` of the Unity export docs — [Exporting to Unity](https://docs.worldlabs.ai/marble/export/gaussian-splat/unity)
- [official] Splats render in-browser via Spark (WL's open-source three.js renderer); video export has pixel-accurate camera control. `V:3rd` — [PYMNTS](https://www.pymnts.com/artificial-intelligence-2/2025/world-labs-launches-marble-as-spatial-intelligence-becomes-the-new-ai-battleground)
- [official] NVIDIA documents a Marble → Isaac Sim path: PLY splat + GLB collider, PLY converted to USD with Omniverse NuRec / 3DGRUT. Scale is then aligned manually in Isaac Sim against reference geometry. `V:snippet` — [NVIDIA developer blog](https://developer.nvidia.com/blog/simulate-robotic-environments-faster-with-nvidia-isaac-sim-and-world-labs-marble)

#### Is the splat native? What WL/founders say
- [official] Per a third-party write-up of the Latent Space interview, Justin Johnson said Marble "natively outputs Gaussian splats", with the splat as an "atomic unit". The wording is paraphrased and I could not read the transcript. A different search summary says Johnson argues splats are *not* fundamental, only the current atomic unit for many scenes. Sources conflict on emphasis. `V:3rd` — [Riffon summary](https://riffon.com/insight/ins_58co5iqjaxj5); [Latent Space episode page](https://www.latent.space/p/after-llms-spatial-intelligence-and)
- [official] A WL Python client reads SPZ into a `Gaussian3D` object and renders with `gsplat` (CUDA). Generation is an async "operation" polled until `done`, authenticated by a `WLT-Api-Key` header. `V:direct` — [worldlabs-api-python](https://github.com/worldlabsai/worldlabs-api-python)
- [official] WL's GitHub org (`V:direct` listing) contains `worldlabs-api-python`, `worldlabs-api-examples`, `skills` (agent skills), `atlas-camera-studio`, and `marble-multiview-inpainting`. It contains **no research/model code or paper repos** — [github.com/worldlabsai](https://github.com/worldlabsai)
- [official] `atlas-camera-studio` (WL, MIT, `V:direct`) is "powered by the Marble 5 API" against a beta host `api.atlas-beta.worldlabs.ai/api/v2`:
  - Pipeline: image resized to 1280×720 → task `images2PosedRGBD` creates a 3D scene (EXR depth map + camera poses) → editor builds a colored point cloud for path planning → 48 interpolated target cameras → task `atlasGenerate` returns frames → 4-second MP4 at 12 FPS.
  - Outputs expire after 7 days.
  - Source: [atlas-camera-studio](https://github.com/worldlabsai/atlas-camera-studio)
- [official] `marble-multiview-inpainting` (WL, MIT, `V:direct`) prepares inputs for Marble's `atlasMasked` inpainting API (an access-dependent preview):
  - Inputs: 2–16 well-overlapped **posed RGB-D views** (pinhole intrinsics/extrinsics + depth as EXR/NPY/NPZ) and an edited anchor image with a mask.
  - Processing: the edit region is lifted to 3D with depth and projected into the other views (occlusion-checked), and views are center-cropped to 1280×720.
  - The README says nothing about Marble's internals. Its warnings (calibrated cameras, aligned depth, trouble with thin structures, reflections, transparency, moving objects, wide baselines) describe the *tool's* limits.
  - Source: [marble-multiview-inpainting](https://github.com/worldlabsai/marble-multiview-inpainting)
- [official] Marble model lineup. The docs recommend **Marble 1.1** for new users (flat 1,500 credits per world). **Marble 1.1 Plus** is for the largest worlds and "automatically expands its coverage of 3D space" (1,500 base plus a variable 0–1,500). `V:snippet` — [Models docs](https://docs.worldlabs.ai/marble/models)
  - Third-party coverage describes the Plus mechanism as "dynamic cubes": up to five additional spatial units at 300 credits each. `V:3rd` — [Radiance Fields](https://radiancefields.com/world-labs-releases-marble-1.1-and-marble-1.1-plus); [aihola](https://aihola.com/article/world-labs-marble-1-1)
  - A third-party guide also lists "1.0" and "1.0 Draft" variants. Unconfirmed against official docs. `V:3rd` — [invideo.io](https://invideo.io/blog/world-labs-marble-3d-worlds/)
- [official] WL's X post: "Marble 1.1: Improves lighting and contrast, with a major reduction in visual artifacts. Marble 1.1-Plus: Our new model built for scale." Release notes date the models 2 April 2026. `V:snippet` — [X post](https://x.com/theworldlabs/status/2041554646561677701); [release notes](https://docs.worldlabs.ai/marble/release-notes)
- [official] No quantitative benchmarks are published for Marble; results are qualitative demos. `V:3rd` — [visual-slam-roadmap summary](https://github.com/changh95/visual-slam-roadmap/blob/main/level-11-world-models-spatial-ai/world-labs-marble.md). My own searches found no Marble paper, and a 2026 arXiv search for WL authors on splat generation found none ([search results](https://arxiv.org/abs/2610.28257) were unrelated).

#### 2026 timeline (for "look for 2026 updates")
- Jan 21, 2026: public **World API** launched (prepaid credits). `V:3rd` — [search aggregate, e.g. Sacra](https://sacra.com/c/world-labs/). Export docs also reportedly added real-world unit scaling and OpenGL/OpenCV coordinate-convention options in Jan 2026 (`V:3rd`, unverified against official docs) — [Export specs search result](https://docs.worldlabs.ai/marble/export/specs).
- Feb 2026: reported $1B round (Autodesk $200M); valuation reports conflict (~$5B vs other figures). `V:3rd` — [ValueAdd VC](https://valueaddvc.com/blog/world-labs-valuation-what-fei-fei-lis-spatial-intelligence-startup-is-worth-at-5b)
- Feb 2026: Spark 2.0 developer preview. 14/15 Apr 2026: Spark 2.0 release (see Q3). — [Spark X post](https://x.com/sparkjsdev/status/2024969164138729632)
- 2 Apr 2026: Marble 1.1 and 1.1 Plus (above).
- 3 Jun 2026: WL essay "A Functional Taxonomy of World Models" (renderers / simulators / planners; Marble placed in the *simulator* category, outputting splats plus collision meshes). `V:snippet` — [WL blog](https://www.worldlabs.ai/blog/taxonomy-of-world-models); [TechTimes](https://www.techtimes.com/articles/317927/20260606/feifei-lis-world-labs-splits-world-model-three-types-marble-targets-simulation-linchpin.htm)
- 21 Jul 2026: WL acquired robotics-sim startup SceniX. `V:3rd` — [CryptoBriefing](https://cryptobriefing.com/world-labs-scenix-acquisition-robot-training/)
- 1 Sep 2026: **Atlas** announced — an "omni" world model in early access with select partners. WL says Atlas "will power future versions of Marble." No API/pricing/date announced. `V:3rd` — [DataNorth](https://datanorth.ai/news/world-labs-introduces-atlas-world-model); [Radiance Fields](https://radiancefields.com/world-labs-announces-new-world-model-atlas); [Kingy AI](https://kingy.ai/blog/world-labs-atlas-world-model-deep-dive/)
  - Reported details: pretrained from scratch on text/images/video/3D; multimodal autoregressive diffusion transformer (rectified flow); camera geometry as an input type; camera-controlled video up to ~1 min at 1440p; reconstruction outputs as point clouds or Gaussian splats; 2–3 images typically enough for faithful reconstruction (WL claim). Parameter count, compute and data undisclosed; independent reproduction not found. `V:3rd` — [howaiworks.ai](https://howaiworks.ai/blog/world-labs-atlas-world-model-2026); [Kingy AI](https://kingy.ai/blog/world-labs-atlas-world-model-deep-dive/)
  - Benchmark fairness has been questioned (headline only; I did not read the article). `V:3rd` — [Winzheng](https://www.winzheng.com/en/article/world-labs-atlas-omni-world-model-spatial-intelligence-launc)
- 26–28 Sep 2026: AMD agreed to acquire WL in an all-stock deal of ~$8.2B (merger agreement dated 26 Sep per an SEC 8-K; announced 28 Sep; closing expected by end of 2026; Fei-Fei Li reportedly to become AMD EVP/chief scientist; research reportedly continues under Johnson and Mildenhall). I did not open the filing; verify against it before quoting. `V:3rd` — [CNBC](https://www.cnbc.com/2026/09/28/amd-fei-fei-li-world-labs.html); [SEC 8-K](https://www.sec.gov/Archives/edgar/data/0000002488/000000248826000182/amd-20260926.htm)
- The README of `atlas-camera-studio` calls the backing service the "**Marble 5 API**" while the host/task names say "atlas". I could not resolve the relationship between "Marble 5", "Atlas", and public Marble 1.1. — [atlas-camera-studio](https://github.com/worldlabsai/atlas-camera-studio)

#### Third-party corroboration that Marble splats are consumable as ordinary 3DGS assets
- [literature] WorldSculpt (arXiv 2609.05416) converted a Marble-generated splat scene into a compositional mesh without extra training. I could not open the paper. — [search result](https://arxiv.org/pdf/2609.05416)
- [literature] An Aug 2026 ACM course paper ("Powered By Gaussian Splats: From World Models to 3D Interactive Worlds") builds on Spark 2.0 and Marble. — [ACM](https://dl.acm.org/doi/10.1145/3799820.3820876)
- [official] WL's showcase: the ICARE creative team designed 7 Marble worlds and streamed them in the browser with Spark 2.0 + three.js. `V:snippet` — [WL X post](https://x.com/theworldlabs/status/2064749936907075638)

### Inferences
- [inferred] **Splats are the primary *delivered* representation, and meshes are derived.** WL docs call meshes "derived from the splat", and SPZ/PLY splats are the quality reference. Whether the network *natively* predicts Gaussian parameters is still open.
- [inferred] **Evidence for "multi-view / depth / panorama first, splat via lifting or fitting".**
  - (a) Panorama (2560×1280 equirect) is a first-class export, so a panoramic image stage probably exists in the pipeline.
  - (b) WL's Atlas-era API exposes `images2PosedRGBD` (images → posed depth), `atlasGenerate` (camera-conditioned frames) and `atlasMasked` (multi-view, depth-reprojected inpainting). These are 2D-plus-depth-plus-pose primitives.
  - (c) An independent Substack critique argues Atlas launch material describes converting depth maps and images into splats *after* generation, and that there is no "Gaussian vocabulary" or splat-space training objective in public materials. `V:3rd` — [Bret Kerr](https://bretkerr.substack.com/p/a-gaussian-splat-is-a-transparent) (critique is about Atlas, not Marble).
  - (d) Fixed output tiers (~2M / ~500k / 100k splats) suggest a canonical fixed-budget splat set plus a downsampling/merge step (cf. Spark's LoD merging).
  - Counter-evidence: Johnson's reported "natively outputs splats" quote, and the existence of splat-native generators in the literature (Lyra, DiffSplat, Bolt3D — see Q2).
- [inferred] **Fixed pricing (1,500 credits flat for 1.1) and a "Draft" tier suggest bounded, fixed-cost inference per world**, not open-ended per-scene optimization. "Dynamic cubes" in 1.1 Plus suggest worlds are generated within a bounded spatial volume and grown by adding volumetric chunks (consistent with Expand).
- [inferred] **Chisel's "structure + text → world" is consistent with a conditioning input** (coarse geometry rendered to depth/semantic-ish maps or voxels) to the same generator, since the output and export set are identical to text/image prompting. Mechanism undisclosed.
- [speculative] A pipeline of the form `prompt → (panorama / multi-view diffusion with depth) → feed-forward or short-optimization 3DGS lift → LoD/downsample → mesh baking (collider via simplified surface extraction, HQ via splat-derived surface extraction)` is the most parsimonious reconstruction consistent with all disclosed pieces. It matches the structure of CAT3D-style "generate views, then reconstruct" pipelines (Mildenhall is a CAT3D co-author) and Lyra-style distillation. None of this is confirmed by WL.
- [speculative] The `Marble 5` / `atlas-beta` naming hints that the Atlas backbone is already being exposed behind Marble-branded APIs, consistent with the statement that "Atlas will power future versions of Marble". Zero direct evidence beyond naming.

### Gaps
- No primary-source text of the Marble launch blog, docs pages, or the Latent Space transcript was opened (DNS failures). All `V:snippet` claims should be spot-checked against worldlabs.ai / docs.worldlabs.ai before final publication.
- Model architecture, parameter count, training data, training compute, and loss functions for Marble: not disclosed anywhere I could find.
- Whether the generator is splat-native, depth-lift, or optimization-based: undetermined.
- Coordinate system, units/scale convention, SH degree, and color space of Marble SPZ/PLY exports: not retrieved (WL points to a separate page, "Rendering Marble SPZ files in third-party engines", which I did not fetch).
- The arXiv paper "Dream machine -- the next creative economy" ([2606.26114](https://arxiv.org/pdf/2606.26114)) surfaced repeatedly for Marble/RTFM/Spark queries, but I could not open it to see what it says.
- The meaning of "Marble 5 API" vs "Atlas" vs "Marble 1.1".

---

## 2. Research lineages: NeRF, Instant-NGP, 3DGS, feed-forward splat predictors, video-diffusion world generation, and WL's own papers

### Takeaway
Marble's *output format* descends directly from 3D Gaussian Splatting (Kerbl et al. 2023), which itself replaced NeRF-style implicit volumes with explicit, rasterizable primitives. Marble's *generation* belongs to the "generative 3D scene" family, which splits into:
- (i) multi-view/video diffusion followed by 3D reconstruction;
- (ii) feed-forward image→Gaussian predictors (pixelSplat, MVSplat, GS-LRM, Splatt3R, VGGT-style);
- (iii) video-diffusion latent → 3DGS decoders (Lyra), and splat-native diffusion (DiffSplat, Bolt3D).

WL has published no Marble paper, so any mapping is inference. The team's own prior work (NeRF, Mip-NeRF 360, Zip-NeRF, DreamFusion, CAT3D, Pulsar, PyTorch3D) is the strongest circumstantial lineage.

### Cited Findings

#### Foundational representation papers
- [literature] **NeRF** (Mildenhall et al., 2020): an MLP maps (position, direction) → (density, view-dependent color), rendered by volumetric ray marching; trained per scene from posed images. † — [arXiv:2003.08934](https://arxiv.org/abs/2003.08934) `V:memory`
- [literature] **Instant-NGP** (Müller et al., 2022): multi-resolution hash-grid encoding plus a tiny MLP gives NeRF training in seconds–minutes. † — [arXiv:2201.05989](https://arxiv.org/abs/2201.05989) `V:memory`
- [literature] **3D Gaussian Splatting** (Kerbl, Kopanas, Leimkühler, Drettakis, 2023): explicit anisotropic 3D Gaussians, tile-based differentiable rasterizer, adaptive densification, real-time (≥100 FPS at 1080p). † — [arXiv:2308.04079](https://arxiv.org/abs/2308.04079) `V:memory`
- [literature] Surveys and reviews that map the field: [arXiv:2401.03890](https://arxiv.org/pdf/2401.03890) (A Survey on 3D Gaussian Splatting) and [arXiv:2405.03417](https://arxiv.org/pdf/2405.03417) (review) — both surfaced in search results; I did not read them.

#### Feed-forward reconstruction and splat prediction
- [literature] **pixelSplat** predicts per-pixel Gaussians from sparse views with known poses, using probabilistic (ray-wise) Gaussian placement to keep it differentiable. **MVSplat** uses plane-sweep cost volumes to estimate Gaussian centers. `V:3rd` (search summary of the survey literature) — [Survey arXiv:2507.14501](https://arxiv.org/pdf/2507.14501); papers: pixelSplat [arXiv:2312.12337](https://arxiv.org/abs/2312.12337)†, MVSplat [arXiv:2403.14627](https://arxiv.org/abs/2403.14627)† `V:memory`
- [literature] **DUSt3R / MASt3R** regress dense pointmaps from image pairs without camera calibration; MASt3R adds matching features. **Splatt3R** adds a Gaussian head to a DUSt3R-style backbone to predict splats from uncalibrated pairs. **VGGT** handles many views in one feed-forward pass, predicting poses and depth/pointmaps without iterative global alignment. `V:3rd` — [Survey arXiv:2507.14501](https://arxiv.org/pdf/2507.14501); papers: DUSt3R [2312.14132](https://arxiv.org/abs/2312.14132)†, MASt3R [2406.09756](https://arxiv.org/abs/2406.09756)†, Splatt3R [2408.13912](https://arxiv.org/abs/2408.13912)†, VGGT [2503.11651](https://arxiv.org/abs/2503.11651)† `V:memory`
- [literature] **LRM / GS-LRM**: large transformer reconstruction models for single/sparse images → 3D (LRM: triplane NeRF; GS-LRM: per-pixel Gaussians). † — [LRM arXiv:2311.04400](https://arxiv.org/abs/2311.04400), [GS-LRM arXiv:2404.19702](https://arxiv.org/abs/2404.19702) `V:memory`
- [literature] Later pose-free Gaussian methods (SelfSplat, PF3plat, SPFSplat, SPFSplatV2) build on MASt3R/VGGT backbones; a remaining fidelity gap versus optimization-based 3DGS is attributed to predicting static Gaussians valid for all viewpoints. `V:3rd` — [ViewSplat arXiv:2603.25265](https://arxiv.org/html/2603.25265v1); [Gesplat arXiv:2510.10097](https://arxiv.org/pdf/2510.10097)

#### Generative scene / world lineage
- [literature] **Lyra** (NVIDIA, ICLR 2026, arXiv:2509.19296): adds a 3DGS decoder next to a video diffusion model's RGB decoder and trains it by self-distillation (3DGS renders must match the frozen model's RGB decodes). Needs no real multi-view data. At inference it runs text/single-image → 3DGS directly. `V:3rd` (search summary of paper/project page) — [Lyra search results](https://arxiv.org/pdf/2509.19296v1); [ICLR page](https://iclr.cc/virtual/2026/poster/10006990)
- [literature] **DiffSplat** repurposes image diffusion to generate Gaussian-splat properties directly — evidence that splat-native generation is feasible. — [arXiv:2501.16764](https://arxiv.org/pdf/2501.16764). Also: "Complete Gaussian Splats from a Single Image with Denoising Diffusion Models" — [arXiv:2508.21542](https://arxiv.org/pdf/2508.21542) (surfaced in search; not read). Also GSComplete (Gaussian splat completion with 2D diffusion priors) — [arXiv:2609.08449](https://arxiv.org/abs/2609.08449).
- [literature] **ViewCrafter** (video diffusion with point-cloud-rendered conditions → novel views → 3DGS) [arXiv:2409.02048](https://arxiv.org/abs/2409.02048)†; **Cosmos** (NVIDIA world foundation models) [arXiv:2501.03575](https://arxiv.org/abs/2501.03575)†; **Bolt3D** (latent diffusion generating 3DGS in seconds) [arXiv:2503.14445](https://arxiv.org/abs/2503.14445)†; **CAT3D** (multi-view diffusion then robust NeRF reconstruction; Mildenhall is a co-author) [arXiv:2405.10314](https://arxiv.org/abs/2405.10314)†; **DreamFusion** (SDS text-to-3D; Mildenhall co-author) [arXiv:2209.14988](https://arxiv.org/abs/2209.14988)†. All `V:memory` (arXiv URLs follow the standard pattern `https://arxiv.org/abs/<ID>`).
- [official] **Genie 3** (Google DeepMind, Aug 2025) is an interactive, frame-by-frame, real-time world model with no explicit 3D asset — the nearest conceptual peer to RTFM, not to Marble. † `V:memory` — [DeepMind blog](https://deepmind.google/discover/blog/genie-3-a-new-frontier-for-world-models/)
- [literature] Contrast drawn by third parties: NeRF/3DGS need many posed images and *reproduce* observed content; Marble *generates* from sparse prompts. It exports splats as an output format but the page "does not say how Marble produces them." `V:3rd` — [visual-slam-roadmap summary](https://github.com/changh95/visual-slam-roadmap/blob/main/level-11-world-models-spatial-ai/world-labs-marble.md)

#### The WL team's own lineage
- [official] WL's founders are Fei-Fei Li, Justin Johnson, Christoph Lassner and Ben Mildenhall (Mildenhall is first author of NeRF). The Sept 2026 coverage names Johnson and Mildenhall as leading the research org. `V:3rd` — [CNBC](https://www.cnbc.com/2026/09/28/amd-fei-fei-li-world-labs.html); founding story: [Contrary Research](https://research.contrary.com/company/world-labs) (listed in search results; not opened). Roles/affiliations beyond this are `V:memory`.
- [literature] Team-relevant prior work (all `V:memory`): Mildenhall — NeRF; Mip-NeRF 360 [2111.12077]†; Zip-NeRF [2304.06706]†; RawNeRF [2111.13679]†; DreamFusion [2209.14988]†; CAT3D [2405.10314]†. Lassner — Pulsar (differentiable sphere-based rasterizer, CVPR 2021) [2004.07484]† and PyTorch3D (conceptual precursors of splat rasterization). Johnson — scene-graph image generation, Mesh R-CNN, PyTorch3D (co-developed).
- [official] The only WL-hosted *research-like* repo found is the inpainting preprocessing tool; no papers or model weights from WL on Marble/RTFM/Atlas appear in the org listing (`V:direct`) — [github.com/worldlabsai](https://github.com/worldlabsai). My search for 2026 arXiv papers by Mildenhall/Lassner/Johnson on splat generation found none.
- [official] Fei-Fei Li's "From Words to Worlds" essay (Nov 2025) frames "spatial intelligence" and "Large World Models" as the next frontier; a repo summary calls Marble the first product of this thesis. `V:3rd` — [visual-slam-roadmap summary](https://github.com/changh95/visual-slam-roadmap/blob/main/level-11-world-models-spatial-ai/world-labs-marble.md). I could not open the essay.

### Inferences
- [inferred] Of the lineage, the **most plausibly related to Marble's internals** (ranked by consistency with WL-disclosed artifacts):
  1. **CAT3D / Bolt3D-style "generate consistent views (+depth), then 3D-lift"**. This matches posed-RGB-D primitives in WL's APIs and the panorama export.
  2. **Lyra-style video/multi-view diffusion latent → 3DGS decoder**. This matches fixed ~2M splat budgets and fast, bounded inference.
  3. **VGGT / DUSt3R / MASt3R-style feed-forward pose+depth** as the lifting engine (`images2PosedRGBD`).
  4. **GS-LRM-style per-pixel Gaussian heads** for the final splat parameters (per-pixel Gaussians naturally produce millions of splats from multi-view images at moderate resolution).
- [inferred] RTFM (Q4) is the Genie-3 / video-world-model branch; Marble is the explicit-3D branch. They are different design philosophies inside one company.
- [inferred] Pulsar (Lassner) and NeRF (Mildenhall) sit before 3DGS in time, so the team has direct experience with both implicit-field and sphere/blob-based differentiable rendering; this makes a splat-based output choice natural but says nothing about the generator design.
- [speculative] Marble's mesh export (HQ mesh derived from the splat) probably uses a standard splat→surface step (depth rendering + TSDF/Poisson, or 2DGS/GOF-style surfaces), but WL does not state the method.

### Gaps
- No WL paper or tech report on Marble, RTFM or Atlas located; the claim "none exists" is limited to the searches I could run.
- All arXiv IDs marked † were not re-fetched this session (arxiv.org unreachable). They are from memory and should be spot-checked.
- Lyra, the pose-free survey literature, and the Gesplat/ViewSplat sources were read only through search-tool summaries.
- Training data for Marble (video? 3D scans? synthetic?) is unknown.

---

## 3. The Spark renderer (open-source, three.js): rendering, sorting, LOD, streaming, dynamic splats, formats, performance and limits

### Takeaway
Spark is a WL-authored, MIT-licensed 3DGS renderer for three.js (Rust/WASM core, WebGL2) that draws all splats in one instanced draw call after a background-thread depth sort, and merges with mesh geometry through the Z-buffer. Spark 2.0 (April 2026) added a hierarchical LoD splat tree, a streamable `.RAD` format, and a GPU "page table" for 100M+-splat worlds on constrained devices. Its practical limits are sort latency, alpha-blending fill cost, 16-bit position precision in the compact format, and the lack of physics/material data.

### Cited Findings

#### Overview, license, platform
- [official] Spark is a 3DGS renderer for three.js that "integrates with THREE.js rendering pipeline to fuse splat and mesh-based objects"; supports multiple splat objects with correct sorting and multiple simultaneous viewpoints; MIT license; targets "98%+ WebGL2 support". The README CDN example used Spark **2.4.0** with three.js r180, so Spark has iterated several times since the 2.0 release. Stars/forks at capture: ~3.8k / 570. `V:direct` — [sparkjsdev/spark](https://github.com/sparkjsdev/spark)
- [official] Usage: create a `SparkRenderer`, add it to the scene, add `SplatMesh` objects; the Rust/WASM component is built separately (`npm run build:wasm`). `V:direct` — [sparkjsdev/spark](https://github.com/sparkjsdev/spark)
- [official] Supported formats: PLY (including compressed PLY), SPZ, SPLAT, KSPLAT, SOG (and `.RAD` in 2.0). Compression to SPZ via `npm run assets:compress`. `V:direct` — [sparkjsdev/spark](https://github.com/sparkjsdev/spark); [new-features-2.0.md](https://github.com/sparkjsdev/spark/blob/main/docs/docs/new-features-2.0.md)

#### Rendering and sorting pipeline
- [official] `SparkRenderer` walks the visible three.js scene graph and builds a list of splats from all `SplatMesh` instances; a `SplatAccumulator` aggregates them into a `PackedSplats` buffer (16 bytes/splat). Each `SparkViewpoint` reads per-splat distance metrics back from the GPU, and a **bucket sort runs in a background worker (`SplatWorker`)**. "The sort order lags the render by at least one frame, but possibly more on older devices." On the next `render()`, one instanced draw call renders all splats, blended back-to-front, merging with opaque geometry via the Z-buffer. `V:direct` — [system-design.md](https://github.com/sparkjsdev/spark/blob/main/docs/docs/system-design.md)
- [official] Extra `SparkViewpoint`s support multiple viewpoints; Spark 2.0 allows multiple `SparkRenderer` instances (also offline, single-frame, e.g., for video output). `V:direct` — [system-design.md](https://github.com/sparkjsdev/spark/blob/main/docs/docs/system-design.md); [new-features-2.0.md](https://github.com/sparkjsdev/spark/blob/main/docs/docs/new-features-2.0.md)

#### Dynamic / editable splats
- [official] "Fully dynamic": per-splat transforms, color editing/perturbation (`SplatEdit`), dual-quaternion skeletal animation (`SplatSkinning`), and procedural splat generation. `V:direct` — [sparkjsdev/spark](https://github.com/sparkjsdev/spark); [system-design.md](https://github.com/sparkjsdev/spark/blob/main/docs/docs/system-design.md)
- [official] **Dyno** is a JavaScript-defined shader graph compiled to GLSL, run as pseudo-compute shaders. `PackedSplats`/`SplatGenerator` map an integer index → `Gsplat` (center, scales, quaternion, rgba) and can vary over time; `SplatMesh` exposes `objectModifier`/`worldModifier` hooks; `Readback` maps an index to an RGBA8 value used for CPU-side sorting. `V:direct` — [dyno-overview.md](https://github.com/sparkjsdev/spark/blob/main/docs/docs/dyno-overview.md)
- [official] Experimental in 2.0: covariance-based splats (`covSplats: true`, stores the 3D covariance matrix, enabling non-uniform scaling and general affine transforms), linear-blend skinning for mesh-style rigs, and `SparkPortals`. `V:direct` — [new-features-2.0.md](https://github.com/sparkjsdev/spark/blob/main/docs/docs/new-features-2.0.md)

#### Splat encoding (precision)
- [official] `PackedSplats` = 16 bytes/splat (4×uint32):
  - Center: 3×float16 (~10 mantissa bits; range ~32K; precision falls off away from origin).
  - Scale: 3×uint8, log-encoded, ~7% steps, covering ≈1e-4 to 8K.
  - Rotation: axis-angle (octahedral axis in 2 bytes, angle in 1 byte).
  - Color/opacity: 4×uint8 RGBA.
  - Optional SH: sh1 (7-bit), sh2 (8-bit), sh3 (6-bit) stored in an `extra` block, up to ~56 B/splat total.
  - `V:direct` — [packed-splats.md](https://github.com/sparkjsdev/spark/blob/main/docs/docs/packed-splats.md)
- [official] `ExtSplats` (2.0) = 32 bytes/splat with float32 centers, fixing float16 "striping" in large scenes. `V:direct` — [new-features-2.0.md](https://github.com/sparkjsdev/spark/blob/main/docs/docs/new-features-2.0.md)

#### LoD, streaming, paging (Spark 2.0)
- [official] **LoD tree**: any splat file can be converted to a tree whose leaves are the original splats and whose parents are merged, downsampled approximations up to one root. Each frame Spark selects a slice of the tree by distance and frustum within a budget N (default ~500K on phones to ~2.5M on desktop), with foveation (extra detail near the view center). Two builders: `tiny-lod` (fast, on-demand in a WebWorker, ~1–3 s per 1M splats) and `bhatt-lod` (higher quality, offline CLI `build-lod`). `V:direct` — [new-features-2.0.md](https://github.com/sparkjsdev/spark/blob/main/docs/docs/new-features-2.0.md)
- [official] **`.RAD`** (RADiance field) stores precomputed LoD trees and is fetched in chunks via HTTP Range requests, coarse first, prioritizing chunks that most improve the current view. `V:direct` — same source.
- [official] **Paging**: a shared LRU "splat page table" in a fixed GPU pool (default 16M splats) is shared across all splat objects. It fetches chunks on demand and evicts old ones, "intended to support scenes of 100M or more splats on limited hardware." `V:direct` — same source. WL's own post also claims streaming 100M+ splats on phones/headsets: [WL X post](https://x.com/theworldlabs/status/2044096996148171035); [WL blog "Streaming 3DGS worlds on the web"](https://www.worldlabs.ai/blog/spark-2.0) (`V:snippet`).
- [official] Multiple splat objects can share one LoD traversal, so one global set of N splats is chosen across all (useful for composing separately generated worlds). `V:direct` — same source.
- [official] Other 2.0 additions: load from `ReadableStream` (multi-GB files), `SparkXr` (WebXR wrapper with hand tracking), chainable dyno modifiers, custom shaders. `V:direct` — same source.
- Release date: blog/coverage says 14 Apr 2026; one project page says 15 Apr. `V:3rd` — [Radiance Fields on Spark 2.0](https://radiancefields.com/world-labs-previews-spark-2.0)

#### Performance guidance and limits
- [official] Splat budgets (rule of thumb): Quest 3 ≤ ~1M; Android phone 1–2M; iPhone 1–3M; computer 1–5M (10–20M+ on some desktops). Around 1M splats becomes a bottleneck on some systems for transform/sort overhead; dense clusters are costly even below that (e.g., 500K splats from a single small object at small screen scale). `V:direct` — [performance.md](https://github.com/sparkjsdev/spark/blob/main/docs/docs/performance.md)
- [official] Tuning: lower `SparkRenderer.maxStdDev` below the default √8 (≈2.8) — for VR, √5 looks nearly identical; leave WebGL `antialias` false (MSAA is costly with millions of blended splats); watch `devicePixelRatio`. `V:direct` — [performance.md](https://github.com/sparkjsdev/spark/blob/main/docs/docs/performance.md)
- [official] Sort data is limited to a 32-bit RGBA8 value per index (Dyno `Readback`). `V:direct` — [dyno-overview.md](https://github.com/sparkjsdev/spark/blob/main/docs/docs/dyno-overview.md)
- [official] Spark's repo has a docs page on "on-demand rendering", `splat-editing`, `procedural-splats`, `system-design`, `performance`, `lod-getting-started`, and a 0.1→2.0 migration guide. `V:direct` — [docs folder](https://github.com/sparkjsdev/spark/tree/main/docs/docs)
- Third-party project doc (author's summary, not verified WL text): Spark renders splats only; colliders from Marble are GLB meshes run in the host physics engine; splats carry no per-surface material data. `V:3rd` — [sandraschi/worldlabs-mcp SPARK_V2.md](https://github.com/sandraschi/worldlabs-mcp/blob/main/docs/SPARK_V2.md). The same doc reports a ~64K-splat coarse proxy shown almost immediately with `.RAD` and a 64K-splat page size; those details were not in the Spark pages I read.
- Marble-specific: 500k-splat SPZ exports throw an "Index out of range" error in Unity (community troubleshooting; convert to PLY); 2M SPZ works. `V:snippet` — [Unity export docs](https://docs.worldlabs.ai/marble/export/gaussian-splat/unity)

### Inferences
- [inferred] **Practical Marble scale vs Spark limits.** A Marble full-res world (~2M splats) is inside the desktop budget (1–5M) but exceeds phone/Quest guidance (~1–2M and ≤1M), which explains the 500k and 100k export tiers. Without LoD, only the 500k tier is comfortable on mobile.
- [inferred] The **one-frame-or-more sort lag** and **per-viewpoint sort** mean rapid camera rotation can show transient popping/blending artifacts, a known issue class for splats; WL's docs imply this by documenting the lag, not by naming artifacts.
- [inferred] Float16 centers (PackedSplats) can cause precision problems for large coordinate extents. Combined with Marble's "bigger worlds" (1.1 Plus), this explains why `ExtSplats` (float32) was added in 2.0.
- [inferred] Spark's merged-LoD design is a natural runtime for Composer-style multi-world scenes: one global budget across worlds.

### Gaps
- I could not open the official Spark 2.0 blog (worldlabs.ai/blog/spark-2.0) or sparkjs.dev; the details above come from the repo docs (read directly) plus search summaries. Names such as `Tiny-LoD`/`Bhatt-LoD` were confirmed in repo docs (`tiny-lod`/`bhatt-lod`).
- No FPS benchmarks, sort timings, or memory measurements were found in the repo pages read.
- The per-splat sort uses a "bucket sort"; bucket count/precision not documented in pages read.
- SH degree support in the 2.0 LoD/RAD path was not confirmed.
- Streaming performance claims (100M+ splats on phones) come from WL's own announcement, not independent measurement.

---

## 4. RTFM (the "RTT" real-time model) and the "Large World Model" claims: persistence, consistency, scale, expansion, composition

### Takeaway
RTFM (Real-Time Frame Model, 16 Oct 2025) is a *different* model from Marble: an autoregressive diffusion transformer that generates video frames in real time on a single H100, holding the world implicitly in a KV-cache of pose-tagged frames, with **no explicit 3D representation**. Marble is the explicit-3D, persistent-asset product. WL's "Large World Model" framing is conceptual (generative, multimodal, interactive world models), and I could not retrieve primary text defining it. Persistence in Marble comes from the exported splat asset itself, and scale and composition come from Expand, Marble 1.1 Plus auto-expansion, Composer, and Spark's merged LoD.

### Cited Findings

#### RTFM
- [official] RTFM was introduced as "a highly efficient World Model that generates video frames in real time as you interact with it, powered by a single H100 GPU … renders persistent and 3D consistent worlds, both real and imaginary." — [WL on X (16 Oct 2025)](https://x.com/theworldlabs/status/1978839171058815380); blog: [RTFM: A Real-Time Frame Model](https://www.worldlabs.ai/blog/rtfm) `V:snippet`
- [official] Architecture as summarized from the blog: an **autoregressive diffusion transformer trained end-to-end on large-scale video** to predict next frames conditioned on previous frames. It takes one or more 2D images and generates new 2D views **without building any explicit 3D representation**. Input frames become a KV cache, whose activations "implicitly represent the world." `V:snippet` — [RTFM blog](https://www.worldlabs.ai/blog/rtfm); [Radiance Fields](https://radiancefields.com/world-labs-announces-realtime-frame-model-(rtfm))
- [official] Frames carry a pose; a "context juggling" technique retrieves spatially nearby frames when rendering new ones, so persistence does not require attending to the entire interaction history. `V:3rd`/`V:snippet` — [Radiance Fields](https://radiancefields.com/world-labs-announces-realtime-frame-model-(rtfm)); [36Kr](https://eu.36kr.com/en/p/3512599772454023)
- [official] With more input views RTFM behaves like interpolation (reconstruction); with fewer it must extrapolate (generation). `V:snippet` — [RTFM blog](https://www.worldlabs.ai/blog/rtfm)
- One search summary says RTFM was "integrated into Marble"; I could not corroborate this from WL text. `V:3rd` — [search aggregate, Contrary Research listing](https://research.contrary.com/company/world-labs). Treat as unverified.
- Open-source follow-ons mimic the RTFM niche: InSpatio-WorldFM (open-source real-time generative frame model, [arXiv:2603.11911](https://arxiv.org/pdf/2603.11911)) and InSpatio-World ([arXiv:2604.07209](https://arxiv.org/pdf/2604.07209)). Not WL; surfaced in search; not read.

#### Large World Model (LWM) and taxonomy
- [official] WL describes Marble as powered by "multimodal world models that can reconstruct, generate, and simulate 3D worlds." `V:snippet` — [worldlabs.ai](https://www.worldlabs.ai/)
- [official] WL's 3 June 2026 taxonomy essay splits "world model" into **renderers** (pixel observations, judged on visual fidelity), **simulators** (track changing state), and **planners** (choose actions), organized around the agent loop (action → state change → partial observation). Marble is positioned as a *simulator*: multimodal prompts in, explorable 3D environments out, with Gaussian splats for visual exploration plus collision meshes for a physics engine. `V:snippet`/`V:3rd` — [WL blog](https://www.worldlabs.ai/blog/taxonomy-of-world-models); [TechTimes](https://www.techtimes.com/articles/317927/20260606/feifei-lis-world-labs-splits-world-model-three-types-marble-targets-simulation-linchpin.htm)
- [official] The "spatial intelligence" framing (Fei-Fei Li's Nov 2025 essay) casts Marble as a first step beyond language-only foundation models. `V:3rd` — [visual-slam-roadmap summary](https://github.com/changh95/visual-slam-roadmap/blob/main/level-11-world-models-spatial-ai/world-labs-marble.md). From memory (not re-verified here), the essay names three defining properties of a "Large World Model": generative, multimodal, interactive. `V:memory`.
- [official] In the Latent Space interview the host noted Marble models neither physics nor motion over time and asked whether a change to splats could support it; I did not see Johnson's answer. `V:3rd` — [Latent Space episode](https://www.latent.space/p/after-llms-spatial-intelligence-and)
- [literature] Third-party taxonomies note "nobody agrees what a world model is" and enumerate five competing approaches. `V:3rd` — [My Living AI (Johnson)](https://www.mylivingai.com/nobody-agrees-what-a-world-model-is-justin-johnson-world-labs-explains-why/); [Themesis](https://themesis.com/2026/01/07/world-models-five-competing-approaches/)

#### Persistence, consistency, scale, expansion, composition in Marble
- [official] Marble outputs a **persistent, downloadable 3D environment** rather than generating a world on the fly as the user explores. `V:3rd` — [TechCrunch](https://techcrunch.com/2025/11/12/fei-fei-lis-world-labs-speeds-up-the-world-model-race-with-marble-its-first-commercial-product/)
- [official] Expansion and composition tools: Expand button; Composer to assemble a shared scene from multiple worlds; style switching without changing geometry. `V:3rd` — [visual-slam-roadmap summary](https://github.com/changh95/visual-slam-roadmap/blob/main/level-11-world-models-spatial-ai/world-labs-marble.md); [Scenario help center](https://help.scenario.com/articles/4774055514-marble-by-world-labs-the-essentials)
- [official] Marble 1.1 Plus "automatically expands its coverage of 3D space to generate bigger worlds when possible"; third-party sources describe up to five extra "dynamic cubes". Earlier models generated within a fixed spatial footprint. `V:snippet`/`V:3rd` — [Models docs](https://docs.worldlabs.ai/marble/models); [aihola](https://aihola.com/article/world-labs-marble-1-1)
- Sources disagree on how many Expand operations a world allows: one says only one extension, another estimated ~2 repeats. `V:3rd` — [design4real](https://design4real.de/en/world-labs-marble-practical-test/). No official number found.
- [official] Spark's composite LoD traversal picks one global splat budget across several splat objects, and its page table is shared across all objects (see Q3). `V:direct` — [new-features-2.0.md](https://github.com/sparkjsdev/spark/blob/main/docs/docs/new-features-2.0.md)
- [official] Atlas-era "world → camera path → video" API (`atlas-camera-studio`, `V:direct`): single image → posed RGB-D scene → 48 target cameras → 4-second, 12 FPS clip. A short-clip, camera-conditioned generator is therefore the current WL video interface; no persistent session is described. — [atlas-camera-studio](https://github.com/worldlabsai/atlas-camera-studio)

### Inferences
- [inferred] **Two persistence mechanisms.** Marble persistence is *asset-level*: the splat file is the world state, so consistency is exact (the same file renders identically from any pose) and survives indefinitely. RTFM persistence is *context-level*: bounded by the KV cache and pose-based retrieval; drift or forgetting is possible when revisiting places after long excursions. WL's own "context juggling" design exists precisely because full history cannot be attended to.
- [inferred] **"RTT"/RTFM vs Marble trade-off.** RTFM can show view-dependent effects, reflections, and unobserved content without geometry, but cannot export an asset; Marble can export but is limited by splat fidelity. The taxonomy essay's "renderer vs simulator" split mirrors this: RTFM ≈ renderer, Marble ≈ simulator.
- [inferred] **Scale is added by chunking.** The 1.1 Plus "cubes" plus Expand, Composer, and Spark LoD/paging form a coherent stack for large worlds. Official numeric limits on world size (meters, splat count beyond ~2M) are not documented in the sources I found.
- [inferred] Atlas (Sept 2026) appears to unify the RTFM-like camera-conditioned video generation and Marble-like 3D reconstruction in one model (frames + depth in a shared spatial context). Atlas is "to power future versions of Marble", so the RTFM/Marble split may narrow.
- [speculative] An Atlas-backed Marble could generate explicit splat worlds from a video-like latent trajectory (Lyra-like), but WL has said nothing about this.

### Gaps
- I could not retrieve the primary RTFM blog text or any WL page that defines "Large World Model" verbatim; LWM characterizations are third-party or from memory.
- Whether RTFM is actually used inside Marble is unverified.
- No official statement on Marble world extent limits (meters), maximum Expand count, or Composer's technical alignment mechanism.
- How Atlas relates to RTFM (shared weights/architecture) is not stated by WL ([Kingy AI](https://kingy.ai/blog/world-labs-atlas-world-model-deep-dive/) notes WL does not say Atlas descends from RTFM).

---

## 5. Known limitations: view-dependent quality, floaters, geometry accuracy, scale, physics, semantics, lighting, dynamics

### Takeaway
Marble's worlds are *plausible, generated* 3D, not metrologically accurate reconstructions. WL's own docs concede artifacts in splat-derived meshes and coarse colliders. Quality degrades away from the input viewpoint and in thin, reflective, transparent, sky, and poorly covered regions. Scenes are static, lighting is baked into view-dependent splat color, and splats carry no instance or semantic labels. No independent metric accuracy study exists.

### Cited Findings
- [official] **Mesh artifacts.** "Uneven geometry, holes, and blobby or 'floater' surfaces show up most in regions that are hard to reconstruct" (thin structures, reflective/transparent surfaces, sky, poorly covered regions); high-quality meshes are splat-derived, so splat export is recommended for cleanest visuals. `V:snippet` — [Mesh export docs](https://docs.worldlabs.ai/marble/export/mesh)
- [official] **Colliders are low-fidelity** and "simplified" (coarse physics only). A panorama-based guide reports uneven floors that may need flattening. `V:snippet`/`V:3rd` — [Mesh export docs](https://docs.worldlabs.ai/marble/export/mesh); [Brain & Bot how-to](https://www.brainandbot.ai/assets/download/handbooks/4-Marble-AI-HowTo-Guide-Feb2026.pdf)
- [official] **Splat degradation → Expand.** Region-selective expansion exists because splats can degrade in some regions. `V:3rd` — [visual-slam-roadmap summary](https://github.com/changh95/visual-slam-roadmap/blob/main/level-11-world-models-spatial-ai/world-labs-marble.md)
- [official] **Scale/physics warning.** A WL essay warns that AI-generated geometry can look right while containing self-intersections or wrong scale that produce nonsensical physics. `V:snippet` — [search summary of WL taxonomy/essays](https://www.worldlabs.ai/blog/taxonomy-of-world-models) (exact essay attribution unclear)
- [official] **Scale handling in practice.** NVIDIA's Isaac Sim workflow aligns/scales the Marble radiance field to real-world dimensions after import, checked against reference geometry (e.g., a default cube); no source stated that exports are in meters. `V:snippet` — [NVIDIA blog](https://developer.nvidia.com/blog/simulate-robotic-environments-faster-with-nvidia-isaac-sim-and-world-labs-marble); [Radiance Fields on NVIDIA workflow](https://radiancefields.com/nvidia-publishes-blog-on-marble-workflow-for-robotics-simulation-with-isaac-sim). A secondary source claims exports gained "real-world unit scaling" in Jan 2026 (`V:3rd`, unverified) — [search result](https://docs.worldlabs.ai/marble/export/specs).
- [official] **Invented, not measured, content.** Guides state Marble predicts what is outside the frame, so hidden areas are invented; the visual-slam-roadmap author's analysis notes the geometry comes from learned priors rather than sensing and may not match a real place. `V:3rd` — [visual-slam-roadmap summary](https://github.com/changh95/visual-slam-roadmap/blob/main/level-11-world-models-spatial-ai/world-labs-marble.md)
- [literature] **Hands-on tests** report: lower quality away from original viewpoints and in less-represented areas; poor overlap/ordering when splats and conventional meshes share one scene; odd collision behavior; poor early mesh quality. `V:3rd` — [design4real practical test](https://design4real.de/en/world-labs-marble-practical-test/)
- [official] **Dynamics.** Marble worlds are static scene assets; "dynamics" appear only in post-processed exported videos (smoke/fire/water). A Latent Space host noted Marble does not model motion over time. `V:3rd` — [visual-slam-roadmap summary](https://github.com/changh95/visual-slam-roadmap/blob/main/level-11-world-models-spatial-ai/world-labs-marble.md); [Latent Space](https://www.latent.space/p/after-llms-spatial-intelligence-and)
- [official] **Semantics/instances/materials.** None of WL's documented outputs includes semantic or instance labels or material properties (assets: splats, colliders, meshes, panorama, video). A third-party Spark doc states splats carry no per-surface material data, so footstep sounds/material logic must be supplied by the host. `V:3rd` — [SPARK_V2.md](https://github.com/sandraschi/worldlabs-mcp/blob/main/docs/SPARK_V2.md)
- [official] **Lighting.** Marble 1.1 explicitly targeted "improved lighting and contrast" and fewer artifacts; the generated appearance is delivered as color (and, per format, possibly SH) baked into splats. No relighting export is documented. `V:snippet` — [X post](https://x.com/theworldlabs/status/2041554646561677701)
- [official] **Export operational limits.** HQ mesh generation up to an hour; 4 requests/hour/user; Pro-plan gating; 500k SPZ index error in Unity. `V:snippet` — [Export specs](https://docs.worldlabs.ai/marble/export/specs); [Unity export docs](https://docs.worldlabs.ai/marble/export/gaussian-splat/unity)
- [official] **No published quantitative benchmarks.** `V:3rd` — [visual-slam-roadmap summary](https://github.com/changh95/visual-slam-roadmap/blob/main/level-11-world-models-spatial-ai/world-labs-marble.md). For Atlas, benchmark claims are WL's own and fairness has been questioned (`V:3rd`) — [Winzheng](https://www.winzheng.com/en/article/world-labs-atlas-omni-world-model-spatial-intelligence-launc).

### Inferences
- [inferred] **View-dependent quality:** if Marble inherits the typical 3DGS/feed-forward profile, quality is best near the generating viewpoints (where Gaussians were fit/predicted from imagery) and degrades with parallax, consistent with the "quality falls off away from original views" test report. Floaters are a generic 3DGS failure mode in poorly constrained regions.
- [inferred] **Geometry is plausible, not metric.** No sensor data are involved. Surfaces come from generative priors plus lifted depth, and scale is set by learned priors or a heuristic. Treat dimensions as approximate and validate the collider's scale and watertightness before physics or robotics use.
- [inferred] **Lighting is baked.** SH-based splat color is a fixed radiance field; relighting needs separate decomposition research (see Q6) that WL has not announced.
- [inferred] **Collider vs visual mismatch.** Because the collider is a simplified mesh and the visual is a splat field, character controllers can clip through thin/foliage-like splats or collide with invisible simplified surfaces.
- [speculative] Atlas's depth-aware design might improve geometry consistency, but there is no independent evidence yet.

### Gaps
- No systematic quantitative evaluation (Chamfer/depth error, scale error, multi-view consistency) of Marble found.
- Official export coordinate/units conventions not retrieved.
- Whether Marble splats include SH beyond degree 0 not confirmed.
- Whether Marble 1.1 reduced floater rates quantitatively: only qualitative claims.

---

## 6. Fundamentals of 3DGS needed to understand all of this, and production-relevant variants

### Takeaway
3DGS represents a scene as millions of explicit, anisotropic, semi-transparent 3D Gaussians. Each has a position, covariance (scale + rotation), opacity and view-dependent color (spherical harmonics). They are rendered by sorted, tile-based rasterization with front-to-back alpha compositing. They are trained by gradient descent with adaptive densification. Compared with NeRF's implicit MLP + ray marching, this is faster to render, easier to edit, and streamable. The cost is no clean surface, floaters, aliasing, and baked lighting. Production variants address these.

### Cited Findings
All items below are `[literature]` and `V:memory` unless a source with other markers is given. These are the standard definitions from the original paper(s).

#### Gaussian parameters
- [literature] Each Gaussian stores: **position** μ ∈ ℝ³; **covariance** Σ = R S Sᵀ Rᵀ parameterized by a **scale** vector s ∈ ℝ³ and a **rotation quaternion** q (ensures a valid positive semi-definite matrix during optimization); **opacity** α (via sigmoid); **color as spherical harmonics** (degree 3 → 16 coefficients per channel, 48 floats). ≈59 learned floats per splat (3+3+4+1+48). — [Kerbl et al., arXiv:2308.04079](https://arxiv.org/abs/2308.04079)†
- [official] Spark's runtime encoding of those same fields: float16 center, log-uint8 scales, axis-angle rotation, uint8 RGBA, and optionally quantized SH1–SH3 (see Q3). `V:direct` — [packed-splats.md](https://github.com/sparkjsdev/spark/blob/main/docs/docs/packed-splats.md)

#### Differentiable rasterization
- [literature] 3D Gaussians are projected to image space using the EWA-splatting Jacobian approximation, Σ′ = J W Σ Wᵀ Jᵀ (take the upper-left 2×2). Splats are bucketed into 16×16 pixel tiles, sorted by depth per tile with a GPU radix sort, and composited front-to-back: C = Σᵢ cᵢ αᵢ Πⱼ<ᵢ(1−αⱼ), with early termination when accumulated opacity saturates. The whole pipeline is differentiable, so photometric loss (L1 + D-SSIM) trains all parameters. — [arXiv:2308.04079](https://arxiv.org/abs/2308.04079)†
- [official] Spark follows a variant of this for WebGL: a CPU-worker bucket sort per viewpoint (not per tile), one instanced draw, back-to-front blending (a sort lag of ≥1 frame). `V:direct` — [system-design.md](https://github.com/sparkjsdev/spark/blob/main/docs/docs/system-design.md)

#### Training and densification
- [literature] Initialization from SfM sparse points (COLMAP). Adaptive density control: **clone** small Gaussians in under-reconstructed regions and **split** large ones when the view-space positional gradient is high, **prune** near-transparent ones, and periodically reset opacity to remove floaters. Typical outcome 1–6M Gaussians per real scene, ~30k iterations. — [arXiv:2308.04079](https://arxiv.org/abs/2308.04079)†
- [literature] Densification variants: 3DGS-MCMC (densification as MCMC sampling; [arXiv:2404.09591]†), Scaffold-GS (anchor-based structured Gaussians; [arXiv:2312.00109]†).

#### NeRF vs 3DGS vs meshes/point clouds
- [literature] **NeRF**: implicit continuous field (MLP) queried at hundreds of samples per ray; volumetric rendering; compact but slow to render and hard to edit (Instant-NGP's hash grid accelerates training/rendering). — [arXiv:2003.08934](https://arxiv.org/abs/2003.08934)†, [arXiv:2201.05989](https://arxiv.org/abs/2201.05989)†
- [literature] **3DGS**: explicit, unordered primitives; rasterization (no per-ray MLP), real-time on GPUs; trivially editable/transformable per primitive; larger memory footprint (hundreds of MB for big scenes uncompressed). — [arXiv:2308.04079](https://arxiv.org/abs/2308.04079)†
- [literature] **Meshes** give watertight surfaces, UVs, collision, and physics, but are hard to optimize from images; **point clouds** are unsized samples without view-dependent opacity/anisotropy. 3DGS has no guaranteed surface; surface extraction (2DGS, depth fusion, TSDF/Poisson) is a separate step. — [Gaussian Splatting review arXiv:2405.03417](https://arxiv.org/pdf/2405.03417) (`V:3rd`, surfaced in search; not read)

#### Variants relevant to production
- [literature] **Mip-Splatting** (alias-free via a 3D smoothing filter and a 2D Mip filter; fixes zoom/resolution artifacts) [arXiv:2311.16493]†. **2DGS** (2D oriented surfels with depth-distortion and normal-consistency regularizers for accurate geometry) [arXiv:2403.17888]†.
- [literature] **Relightable GS** (Relightable 3D Gaussians: add normals, BRDF and visibility to decompose appearance and light) [arXiv:2311.16043]†.
- [literature] **Dynamic / 4D GS**: Dynamic 3D Gaussians (Luiten et al., persistent tracked Gaussians) [arXiv:2308.09713]†; 4D Gaussian Splatting (deformation fields) [arXiv:2310.08528]†. Recent: SplatFlux (feed-forward 4D reconstruction and generation from video latents, [arXiv:2610.28257](https://arxiv.org/abs/2610.28257)); Graphical X Splatting for 4D under uncertainty ([arXiv:2601.19843](https://arxiv.org/pdf/2601.19843)); HPC: streaming dynamic GS compression ([arXiv:2602.00671](https://arxiv.org/pdf/2602.00671)) (`V:3rd`, titles from search results).
- [literature] **Feed-forward** splat prediction (pixelSplat, MVSplat, GS-LRM, Splatt3R, VGGT-based) replaces per-scene optimization with a network forward pass (see Q2).
- [literature] **File formats**:
  - `.ply`: the canonical training output with all float parameters (large).
  - `.splat` (antimatter15): a simple 32 bytes/splat quantized format [github.com/antimatter15/splat]†.
  - `.ksplat` (mkkellogg GaussianSplats3D): a compact, quantizable variant [github.com/mkkellogg/GaussianSplats3D]†.
  - **SPZ** (Niantic): gzip-compressed quantized format designed for much smaller files, roughly an order of magnitude smaller than PLY [github.com/nianticlabs/spz]†.
  - **SOG** (PlayCanvas): Spatially Ordered Gaussians, sorted into 2D images and compressed with image codecs [PlayCanvas docs]†.
  - `.RAD`: Spark 2.0's LoD tree + streaming format (see Q3).
  - Spark reads all of these. `V:direct` — [sparkjsdev/spark](https://github.com/sparkjsdev/spark). SPZ is Marble's native/export format and PLY its uncompressed alternative. `V:snippet` — [Export specs](https://docs.worldlabs.ai/marble/export/specs)

### Inferences
- [inferred] **Why 3DGS fits a generative world model's output.** Rasterizable explicit primitives give real-time viewing in a browser (Spark), simple LoD/compression/streaming (Spark LoD tree, SPZ), and fast differentiable training signals for a generator (render-and-compare against generated images), unlike NeRF's ray marching.
- [inferred] **Why the weaknesses of 3DGS reappear in Marble.** Baked lighting (SH color), no semantics, no guaranteed surface (hence "derived" meshes), view-dependent popping/aliasing (Mip-Splatting-type issues), and floaters in under-constrained generated regions are all inherent to the representation.
- [inferred] **Production-relevance of variants.** For Marble-like assets, the most relevant are compression/LoD (SPZ, SOG, `.RAD`) for delivery, 2DGS/mesh-extraction for collision geometry, mip-style filtering for zoom stability, and relightable / dynamic GS for the two largest remaining gaps (relighting and motion). None is documented as part of Marble.
- [speculative] Future Marble versions could emit 2DGS-style or hybrid splat+mesh assets to reduce the splat→mesh artifact problem; no sign of this in current docs.

### Gaps
- I did not independently re-fetch the original 3DGS, NeRF or variant papers (arxiv.org unreachable). The parameters and equations above are from memory of the standard papers; the arXiv IDs marked † should be verified before publication.
- SH-degree and color-space conventions for Marble exports remain unconfirmed (see Q1).
- Numbers such as the "~10x smaller" SPZ claim and SOG internals are from memory and were not re-verified.
