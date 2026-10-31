<p align="center">
  <a href="https://graphify.com"><img src="https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/graphify-logo.png" width="360" height="189" alt="Graphify"/></a>
</p>

<p align="center">
  <a href="https://trendshift.io/repositories/25296?utm_source=repository-badge&amp;utm_medium=badge&amp;utm_campaign=badge-repository-25296" target="_blank" rel="noopener noreferrer"><img src="https://trendshift.io/api/badge/repositories/25296" alt="Graphify-Labs%2Fgraphify | Trendshift" width="250" height="55"/></a>
</p>

<div align="center">
<details><summary><b>Read this in other languages</b></summary>

<a href="../../README.md">English</a> | <a href="README.zh-CN.md">简体中文</a> | <a href="README.ja-JP.md">日本語</a> | <a href="README.ko-KR.md">한국어</a> | <a href="README.de-DE.md">Deutsch</a> | <a href="README.fr-FR.md">Français</a> | <a href="README.es-ES.md">Español</a> | <a href="README.hi-IN.md">हिन्दी</a> | <a href="README.pt-BR.md">Português</a> | <a href="README.ru-RU.md">Русский</a> | <a href="README.ar-SA.md">العربية</a> | <a href="README.fa-IR.md">فارسی</a> | <a href="README.it-IT.md">Italiano</a> | <a href="README.pl-PL.md">Polski</a> | <a href="README.nl-NL.md">Nederlands</a> | <a href="README.tr-TR.md">Türkçe</a> | <a href="README.uk-UA.md">Українська</a> | <a href="README.vi-VN.md">Tiếng Việt</a> | <a href="README.id-ID.md">Bahasa Indonesia</a> | <a href="README.sv-SE.md">Svenska</a> | <a href="README.el-GR.md">Ελληνικά</a> | <a href="README.ro-RO.md">Română</a> | <a href="README.cs-CZ.md">Čeština</a> | <a href="README.fi-FI.md">Suomi</a> | <a href="README.da-DK.md">Dansk</a> | <a href="README.no-NO.md">Norsk</a> | <a href="README.hu-HU.md">Magyar</a> | <a href="README.th-TH.md">ภาษาไทย</a> | <a href="README.uz-UZ.md">Oʻzbekcha</a> | <a href="README.zh-TW.md">繁體中文</a> | <a href="README.fil-PH.md">Filipino</a> | <a href="README.he-IL.md">עברית</a>

</details>
</div>

<p align="center">
  <a href="https://pypi.org/project/graphifyy/"><img src="https://img.shields.io/pypi/v/graphifyy" alt="PyPI"/></a>
  <a href="https://github.com/Graphify-Labs/graphify/actions/workflows/ci.yml"><img src="https://github.com/Graphify-Labs/graphify/actions/workflows/ci.yml/badge.svg?branch=v8" alt="CI"/></a>
  <a href="../../LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue" alt="License: Apache-2.0"/></a>
  <a href="https://pepy.tech/project/graphifyy"><img src="https://img.shields.io/pepy/dt/graphifyy?color=blue&label=downloads" alt="Downloads"/></a>
  <a href="https://docs.graphify.com"><img src="https://img.shields.io/badge/Docs-docs.graphify.com-0b7285?style=flat&logo=readthedocs&logoColor=white" alt="Docs"/></a>
  <a href="https://app.graphify.com/login"><img src="https://img.shields.io/badge/Graphify%20Cloud-app.graphify.com-118d4f?style=flat&logoColor=white" alt="Graphify Cloud"/></a>
  <a href="https://discord.gg/graphify"><img src="https://img.shields.io/badge/Discord-Join-5865F2?style=flat&logo=discord&logoColor=white" alt="Discord"/></a>
  <a href="https://www.youtube.com/@graphifylabs"><img src="https://img.shields.io/badge/YouTube-Graphify%20Labs-FF0000?style=flat&logo=youtube&logoColor=white" alt="YouTube"/></a>
  <a href="https://www.linkedin.com/company/graphify-labs"><img src="https://img.shields.io/badge/LinkedIn-Graphify%20Labs-0077B5?logo=linkedin" alt="LinkedIn"/></a>
  <a href="https://www.ycombinator.com/companies/graphify-labs"><img src="https://img.shields.io/badge/Y%20Combinator-S26-F0652F?style=flat&logo=ycombinator&logoColor=white" alt="YC S26"/></a>
</p>

<p align="center">
  <b>Bawasan ang paggastos ng token ng agent nang 80%.</b> Ang Graphify Cloud ay laging-nakabukas na memory na namamahala sa iyong mga agent, pinapanatiling mataas ang kalidad ng code, at pinapatunayan ang pagiging tama gamit ang formal verification. <a href="https://app.graphify.com/login"><b>Magsimula ng libreng 14-araw na pagsubok &rarr;</b></a>
</p>

I-type ang `/graphify` sa iyong AI coding assistant at imumapa nito ang buong proyekto mo (code, docs, PDF, mga larawan, video) sa isang **knowledge graph** na maaari mong **i-query sa halip na mag-grep** sa mga file.

- **Libreng pag-mapa ng code, ganap na lokal.** Ang code ay pini-parse gamit ang tree-sitter AST: deterministiko, walang LLM, walang umaalis sa iyong makina. (Ang docs, PDF, mga larawan at video ay gumagamit ng modelo ng iyong assistant, o ng naka-configure na API key, para sa semantikong pass.)
- **Bawat edge ay may paliwanag.** Bawat koneksyon ay tinatatakan na `EXTRACTED` (tahasan sa pinagmulan) o `INFERRED` (nireresolba ng graphify), kaya masasabi mo kung ano ang direktang nabasa kumpara sa kung ano ang nahinuha.
- **Hindi isang vector index.** Walang embeddings, walang vector store: isang tunay na graph na tinatahak mo. Magtanong, subaybayan ang landas sa pagitan ng dalawang bagay, o ipaliwanag ang isang konsepto.

> [!NOTE]
> **Gusto mo bang laging-nakabukas ito?** Pinapanatili ng [Graphify Cloud](https://app.graphify.com/login) na buhay ang graph sa buong SDLC mo: suporta sa monorepo at cross-repo, formal verification, at code review na may bird's-eye view ng iyong SDLC, kasama ang mga connector para sa Sentry, Jira, at iba pa upang ang mga insidente at ticket ay nasa iisang graph kasama ng iyong code. **[Magsimula ng libreng 14-araw na pagsubok sa app.graphify.com](https://app.graphify.com/login)**.

<p align="center">
  <img src="https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/graph-hero.png" alt="graphify's interactive graph.html showing the FastAPI codebase as a force-directed knowledge graph with a legend of detected communities" width="900">
</p>
<p align="center">
  <em>Ang FastAPI codebase na inimapa ng graphify. Bawat node ay isang konsepto, ang mga kulay ay mga natukoy na community, at ang buong bagay ay naki-click sa graph.html.</em>
</p>

**Magsimula** (30 segundo). Kailangan ng Python 3.10+ at uv (o pipx):

```bash
uv tool install graphifyy      # install the CLI (or: pipx install graphifyy)
graphify install               # detects your assistant and registers the skill
```

Pagkatapos, sa iyong AI assistant:

```
/graphify .
```

Ayan na. Makakakuha ka ng **tatlong file**:

```
graphify-out/
├── graph.html       open in any browser: click nodes, filter, search
├── GRAPH_REPORT.md  the highlights: key concepts, surprising connections, suggested questions
└── graph.json       the full graph: query it anytime without re-reading your files
```

Ang napanatiling graph ay may kasamang `graph.schema_version` upang matukoy ng mga integrasyon ang
hindi-tugmang mga pagbabago sa format, kasama ang `graph.graphify_version` na kumikilala sa
release ng Graphify na gumawa nito.

**Isang install, kahit anong assistant, kahit anong OS.** Claude Code, Cursor, Codex, Gemini CLI, GitHub Copilot, at 20+ pa, sa macOS, Linux, at Windows: [piliin ang iyong platform](#install).

---

## Tingnan ito sa aksyon

<p align="center">
  <img src="https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/demo-path.svg" alt="graphify path query: a terminal asks for the shortest path between FastAPI and ModelField, and the answer lights up hop by hop across the knowledge graph" width="900">
</p>

Kapag naitayo na ang graph ay ini-query mo ito sa halip na magbasa ng mga file. Tunay na output, graphify na pinatakbo sa FastAPI codebase na ipinakita sa itaas:

```text
$ graphify explain "APIRouter"
Node: APIRouter
  Source:    routing.py L2210
  Community: 2
  Degree:    47

Connections (47):
  --> RequestValidationError [uses] [INFERRED]
  --> Dependant [uses] [INFERRED]
  --> .get() [method] [EXTRACTED]
  <-- __init__.py [imports] [EXTRACTED]
  ...

$ graphify path "FastAPI" "ModelField"
Shortest path (3 hops):
  FastAPI --uses--> DefaultPlaceholder <--references-- get_request_handler() --references--> ModelField
```

Bawat edge ay may dalang **confidence tag** (`EXTRACTED` = tahasan sa pinagmulan, `INFERRED` = hinango sa resolution), kaya masasabi mo kung ano ang direktang nabasa kumpara sa kung ano ang nahinuha. Ang `graphify query "<question>"` ay nagbabalik ng naka-scope na subgraph para sa isang simpleng-wika na tanong, at ang `graphify path A B` ay sinusubaybayan kung paano nag-uugnay ang dalawang bagay.

---

## Ano ang ginagawa nito

Ang makukuha mo nang out of the box:

| Kakayahan | Ano ang makukuha mo |
|---|---|
| **God nodes** | Ang pinaka-nakakonektang mga konsepto, para makita mo kung saan dumadaloy ang lahat |
| **Communities** | Ang graph na hinati sa mga subsystem (Leiden), na may mga label na walang LLM |
| **Cross-file links** | `calls` / `imports` / `inherits` / `mixes_in` na nireresolba sa ~40 na wika sa pamamagitan ng tree-sitter AST |
| **Query, path, explain** | Magtanong, subaybayan ang landas sa pagitan ng dalawang bagay, o ipaliwanag ang isang konsepto, lahat laban sa `graph.json` |
| **Rationale + doc refs** | Ang mga komentong `# NOTE:` / `# WHY:` at mga sitas na ADR/RFC ay nagiging first-class na node na naka-link sa code |
| **Lampas sa code** | Ang docs, PDF, mga larawan, at video/audio ay lahat nag-mamapa sa iisang graph |
| **Local-first** | Ang code ay pini-parse nang lokal gamit ang tree-sitter (walang LLM, walang umaalis sa iyong makina); tanging ang semantikong pass sa docs/media ang tumatawag ng backend, at tanging kung mag-configure ka ng isa |

> [!TIP]
> Pinapatakbo ito sa maraming repo o isang monorepo? Ginagawa ito ng [Graphify Cloud](https://app.graphify.com/login) nang tuloy-tuloy at binabawasan ang paggastos ng token ng agent nang 80%, na may mga cross-repo na link, code review na saklaw ng buong SDLC, formal verification, at mga connector ng Sentry/Jira. [Magsimula ng libreng 14-araw na pagsubok &rarr;](https://app.graphify.com/login)

---

## Benchmarks: 0.497 recall@10, 0 LLM credits

| Benchmark | Metric | graphify | Field |
|---|---|---|---|
| LOCOMO (n=300) | recall@10 | **0.497** | mem0 0.048, supermemory 0.149 |
| LOCOMO (n=300) | QA accuracy | 45.3% | supermemory 49.7%, mem0 27.3% |
| LongMemEval-S (n=50) | QA accuracy | **76%** | tied with dense RAG |
| ERPNext cross-tool (n=6) | key-fact coverage | **82.0%** | grep/read baseline 70.8% |
| Graph build | LLM credits | **0** | per-token for most systems |

Bawat sistema ay tumakbo sa parehong harness na may parehong modelo at badyet, iniskor ng isang hukom na blind-validated laban sa pangalawang hukom (90.6% na pagkakasundo, Cohen's kappa 0.81). Buong mga talahanayan kada-sistema, ang resulta ng code-intelligence, at mga utos ng reproduksyon: **[BENCHMARKS.md](../../BENCHMARKS.md)**.

---

## Dokumentasyon

Ang buong gabay at reference ay nasa **[docs.graphify.com](https://docs.graphify.com)**:

- **[Quickstart](https://docs.graphify.com/quickstart)**: itayo ang iyong unang graph
- **[CLI reference](https://docs.graphify.com/reference/overview)**: bawat utos at flag
- **[Magtanong ng mas mahusay na mga tanong sa graph](https://docs.graphify.com/guides/querying)**: mga pattern ng pag-query
- **[Configuration](https://docs.graphify.com/reference/configuration)**: mga environment variable at tuning
- **[Mga suportadong input](https://docs.graphify.com/concepts/supported-inputs)**: mga wika at uri ng file
- **[Mga workflow ng team](https://docs.graphify.com/guides/team-workflows)** at **[PR review](https://docs.graphify.com/guides/pull-requests)**
- **[Troubleshooting](https://docs.graphify.com/troubleshooting)** at **[Paano ito gumagana](https://docs.graphify.com/concepts/architecture)**

---

## Mga kinakailangan

| Kinakailangan | Minimum | Suriin | Install |
|---|---|---|---|
| Python | 3.10+ | `python --version` | [python.org](https://www.python.org/downloads/) |
| uv *(inirerekomenda)* | kahit ano | `uv --version` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| pipx *(alternatibo)* | kahit ano | `pipx --version` | `pip install pipx` |

**macOS mabilis na install (Homebrew):**
```bash
brew install python@3.12 uv
```

**Windows mabilis na install:**
```powershell
winget install astral-sh.uv
```

**Ubuntu/Debian:**
```bash
sudo apt install python3.12 python3-pip pipx
# or install uv:
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## Install

> [!IMPORTANT]
> **Opisyal na package:** Ang PyPI package ay `graphifyy` (dobleng-y). Ang iba pang mga `graphify*` package sa PyPI ay hindi kaanib. Ang CLI command ay `graphify` pa rin.

Ang opisyal na source repository ay [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify).

Ang dalawang-utos na quickstart ay nasa itaas ng README na ito. Ang seksyong ito ay sumasaklaw sa mga paraan ng pag-install, mga naka-scope sa proyekto na install, at bawat suportadong platform.

**Mga paraan ng pag-install** (pumili ng isa):

```bash
uv tool install graphifyy   # recommended, isolated env (if 'graphify' isn't found after, run: uv tool update-shell)
pipx install graphifyy      # alternative
pip install graphifyy       # may need PATH setup, see Troubleshooting below
```

Pagkatapos ay patakbuhin ang `graphify install` nang isang beses. Natutukoy nito kung aling assistant ang iyong pinapatakbo at nirerehistro ang skill, kaya walang per-assistant na setup. Buksan ang iyong AI assistant at i-type ang `/graphify .`

Upang i-install ang assistant skill sa kasalukuyang repository sa halip na sa iyong user
profile, idagdag ang `--project`:

```bash
graphify install --project
graphify install --project --platform codex
```

Ang mga naka-scope sa proyekto na install ay nagsusulat sa ilalim ng kasalukuyang direktoryo, halimbawa
`.claude/skills/graphify/SKILL.md` o `.agents/skills/graphify/SKILL.md` (kasama ang isang
`references/` sidecar na nilo-load ng skill kapag kailangan), at
nagpi-print ng isang `git add` na pahiwatig para sa mga file na maaaring i-commit.
Ang mga per-platform na utos na sumusuporta sa mga naka-scope sa proyekto na install ay tumatanggap ng parehong flag,
halimbawa `graphify claude install --project` o `graphify codex install --project`.

> [!TIP]
> Nauumpog sa `command not found`, isang isyu ng `pip`-sa-Mac/Windows, PowerShell quoting, `uvx` na paggamit, mga quirk ng git-hook PATH, o strict mode? Tingnan ang **[Installation](https://docs.graphify.com/installation)** at **[Troubleshooting](https://docs.graphify.com/troubleshooting)**.

<details>
<summary><b>Piliin ang iyong platform</b> (20+ assistants, i-click upang palawakin)</summary>

| Platform | Install command |
|----------|----------------|
| Claude Code (Linux/Mac) | `graphify install` |
| Claude Code (Windows) | `graphify install` (auto-detected) or `graphify install --platform windows` |
| CodeBuddy | `graphify install --platform codebuddy` |
| Codex | `graphify install --platform codex` |
| OpenCode | `graphify install --platform opencode` |
| Kilo Code | `graphify install --platform kilo` |
| GitHub Copilot CLI | `graphify install --platform copilot` |
| VS Code Copilot Chat | `graphify vscode install` |
| Aider | `graphify install --platform aider` |
| OpenClaw | `graphify install --platform claw` |
| Factory Droid | `graphify install --platform droid` |
| Trae | `graphify install --platform trae` |
| Trae CN | `graphify install --platform trae-cn` |
| Gemini CLI | `graphify install --platform gemini` |
| Hermes | `graphify install --platform hermes` |
| Kimi Code | `graphify install --platform kimi` |
| Amp | `graphify amp install` |
| Agent Skills (cross-framework) | `graphify install --platform agents` (alias `--platform skills`) |
| Kiro IDE/CLI | `graphify kiro install` |
| Pi coding agent | `graphify install --platform pi`, plus `graphify pi guard install` for the native guard |
| Cursor | `graphify cursor install` |
| Devin CLI | `graphify devin install` |
| Google Antigravity | `graphify antigravity install` |

Kailangan din ng mga user ng Codex ng `multi_agent = true` sa ilalim ng `[features]` sa `~/.codex/config.toml` para sa parallel na extraction. Ang CodeBuddy ay gumagamit ng parehong Agent tool at PreToolUse hook mechanism gaya ng Claude Code. Ang Factory Droid ay gumagamit ng `Task` tool para sa parallel na pagpapadala ng subagent. Ang OpenClaw at Aider ay gumagamit ng sequential na extraction (ang parallel agent support ay maaga pa sa mga platform na iyon). Ang Trae ay gumagamit ng Agent tool para sa parallel na pagpapadala ng subagent at **hindi** sumusuporta sa mga `PreToolUse` hook, kaya ang AGENTS.md ang laging-nakabukas na mekanismo.

Ang `--platform agents` (alias `--platform skills`) ay tumutukoy sa generic na cross-framework na [Agent-Skills](https://github.com/anthropics/skills) na mga lokasyon: ang user-global na `~/.agents/skills/` ng spec (binabasa ng `npx skills` at mga spec-compliant na framework) para sa isang global na install, at ang `./.agents/skills/` para sa isang proyekto (`--project`) na install. Ang hubad na `graphify install` ay nananatiling single-platform (Claude Code) sa disenyo: gamitin ang pinangalanang `agents` na platform kapag gusto mong matuklasan ang skill ng anumang framework na nagbabasa ng `.agents/skills`.

Ang Pi ay walang `PreToolUse` hook, kaya ang `graphify pi guard install` ay nagrerehistro ng isang native na Pi extension (sa pamamagitan ng sariling `pi install <package directory>` ng Pi) na nagpapatakbo ng naka-install na `graphify hook-guard` bago ang mga `read`, `grep`, `find` at search-style na `bash` na tawag ng Pi. Ang mga desisyon sa sariwa/luma na graph at ang `GRAPHIFY_HOOK_STRICT=1` na minsan-kada-sesyon na pagtanggi sa indexed-read ay nagmumula sa parehong policy na iyon, kaya tumutugma ang Pi sa hook behavior ng Claude Code; ang gabay ay dumarating bilang isang `<system-reminder source="graphify">` na steering message. Kailangan nito ng Pi 0.58.4 o mas bago: ang mga naunang bersyon ay hinahayaan ang isang steering message na laktawan ang natitirang bahagi ng isang parallel tool-call batch. Ang package ay naka-ship sa loob ng Graphify installation, kaya i-install ang Graphify nang permanente (`uv tool install graphifyy` o `pipx install graphifyy`, hindi `uvx`), i-restart ang Pi pagkatapos mag-install o mag-upgrade, at alisin ito gamit ang `graphify pi guard uninstall`. Tanging ang mga lokal na file target ang sinusuri; kailangan ng hook ng `graphify` sa isang absolute na `PATH` entry sa labas ng proyekto, nakatakda sa isang dalawang-segundo, 256 KiB-in/64 KiB-out na tawag, at fails open. Ang parehong package ay naglo-load din sa [Oh My Pi](https://github.com/can1357/oh-my-pi): `omp plugin install "$(graphify pi guard path)"`. Ang nakarehistrong path ay naglalaman ng bersyon ng Python at venv, kaya muling patakbuhin ang `graphify pi guard install` pagkatapos baguhin ang alinman, at alisin ang lumang entry gamit ang `pi remove <old path>`.

> Ang Codex ay gumagamit ng `$graphify` sa halip na `/graphify`.

</details>

<details>
<summary><b>Mga opsyonal na extra</b> (i-install lamang ang kailangan mo)</summary>

| Extra | Ano ang idinadagdag nito | Install |
|---|---|---|
| `pdf` | PDF extraction | `uv tool install "graphifyy[pdf]"` |
| `office` | `.docx` and `.xlsx` support | `uv tool install "graphifyy[office]"` |
| `google` | Google Sheets rendering | `uv tool install "graphifyy[google]"` |
| `video` | Video/audio transcription (faster-whisper + yt-dlp) | `uv tool install "graphifyy[video]"` |
| `mcp` | MCP stdio server | `uv tool install "graphifyy[mcp]"` |
| `neo4j` | Neo4j push support | `uv tool install "graphifyy[neo4j]"` |
| `falkordb` | FalkorDB push support | `uv tool install "graphifyy[falkordb]"` |
| `svg` | SVG graph export | `uv tool install "graphifyy[svg]"` |
| `leiden` | Leiden community detection (graspologic on Python < 3.13; native backend on 3.13+) | `uv tool install "graphifyy[leiden]"` |
| `ollama` | Ollama local inference | `uv tool install "graphifyy[ollama]"` |
| `openai` | OpenAI / OpenAI-compatible APIs | `uv tool install "graphifyy[openai]"` |
| `gemini` | Google Gemini API | `uv tool install "graphifyy[gemini]"` |
| `anthropic` | Anthropic Claude API (`--backend claude`, uses `ANTHROPIC_API_KEY`) | `uv tool install "graphifyy[anthropic]"` |
| `bedrock` | AWS Bedrock (uses IAM, no API key) | `uv tool install "graphifyy[bedrock]"` |
| `azure` | Azure OpenAI Service (`--backend azure`, uses `AZURE_OPENAI_API_KEY` + `AZURE_OPENAI_ENDPOINT`) | `uv tool install "graphifyy[openai]"` |
| `sql` | SQL schema extraction | `uv tool install "graphifyy[sql]"` |
| `postgres` | Live PostgreSQL introspection (`--postgres DSN`) | `uv tool install "graphifyy[postgres]"` |
| `dm` | BYOND DreamMaker `.dm`/`.dme` AST extraction (may need a C compiler + `python3-dev` if no wheel matches your platform) | `uv tool install "graphifyy[dm]"` |
| `terraform` | Terraform / HCL `.tf`/`.tfvars`/`.hcl` AST extraction | `uv tool install "graphifyy[terraform]"` |
| `pascal` | Pascal / Delphi `.pas`/`.dpr`/`.dpk`/`.inc` AST extraction (more accurate `calls`/`inherits` edges; falls back to a regex extractor when absent) | `uv tool install "graphifyy[pascal]"` |
| `ocaml` | OCaml `.ml`/`.mli` AST extraction | `uv tool install "graphifyy[ocaml]"` |
| `commonlisp` | Common Lisp `.lisp`/`.cl`/`.lsp`/`.asd` AST extraction | `uv tool install "graphifyy[commonlisp]"` |
| `robot` | Robot Framework `.robot`/`.resource` extraction (suites, test cases, keywords, keyword-call and resource/library import edges) | `uv tool install "graphifyy[robot]"` |
| `chinese` | Chinese query segmentation (jieba) | `uv tool install "graphifyy[chinese]"` |
| `all` | Everything above | `uv tool install "graphifyy[all]"` |

</details>

---

## Gawing laging gamitin ng iyong assistant ang graph

Patakbuhin ito nang isang beses sa iyong proyekto pagkatapos itayo ang isang graph:

Patakbuhin ang `graphify <platform> install` nang isang beses sa iyong proyekto, halimbawa `graphify claude install` o `graphify codex install` (o `graphify install --platform <name>`).

Nagsusulat ito ng maliit na config file na nagsasabi sa iyong assistant na kumonsulta sa knowledge graph para sa mga tanong tungkol sa codebase, na mas pinipili ang mga naka-scope na query gaya ng `graphify query "<question>"` kaysa sa pagbabasa ng buong ulat o pag-grep ng mga hilaw na file.

- **Mga hook platform** (Claude Code, Gemini CLI): isang hook ang awtomatikong pumuputok bago ang mga search-style na tawag ng tool (at, sa Claude Code, bago basahin ang mga source file isa-isa sa pamamagitan ng Read/Glob na mga tool) at itinutulak ang iyong assistant patungo sa landas ng graph.
- **Mga instruction-file platform** (Codex, OpenCode, Cursor, atbp.): ang mga paulit-ulit na instruction file (`AGENTS.md`, `.cursor/rules/`, atbp.) ay nagbibigay ng parehong query-first na gabay.

Ang `GRAPH_REPORT.md` ay magagamit pa rin para sa malawak na pagsusuri ng arkitektura.

Kung aling mga file ang isinusulat ng bawat platform (ang `CODEBUDDY.md` + `PreToolUse` hook ng CodeBuddy, ang `AGENTS.md` ng Codex, ang native na `.kilo` plugin ng Kilo, ang `alwaysApply` na panuntunan ng Cursor, at iba pa) ay saklaw sa **[Always-on setup](https://docs.graphify.com/guides/always-on)**.

Upang alisin ang graphify sa lahat ng platform nang sabay-sabay: `graphify uninstall` (idagdag ang `--purge` upang tanggalin din ang `graphify-out/`). O gamitin ang per-platform na utos (hal. `graphify claude uninstall`).

### CLI skills o MCP instructions?

Ang mga instruksyong ini-install ng `graphify install` at ang mga ibinibigay sa isang Graphify MCP connection ay naglalarawan ng magkakaibang paraan ng pag-query ng isang graph:

| Setup | Gabay na gagamitin | Query access |
|---|---|---|
| Lokal na CLI at naka-install na assistant skill | Ang mga instruksyon ng platform na isinulat ng `graphify install` | Patakbuhin ang `graphify query`, `graphify path`, at `graphify explain` laban sa lokal na graph (`graphify-out/` bilang default). |
| Nakakonektang Graphify MCP server | Ang mga instruksyon ng koneksyon at ang mga tool na nakalista ng server na iyon | Tawagin ang mga nakalistang MCP tool laban sa graph na inihahain ng koneksyong iyon. Ang mga pangalan at paglalarawan ng tool ay nagmumula sa server. |

Parehong naghihikayat ng mga naka-scope na graph query bago ang malawak na source search. Piliin ang mga instruksyong tumutugma sa mga tool na talagang maa-access ng iyong assistant; walang bloke sa dalawa ang nagtatakda ng unibersal na panuntunan ng pagkakasunod para sa mga instruction file ng iyong assistant. Kung gumagamit ka ng parehong integrasyon, tukuyin kung aling graph ang ini-query ng bawat isa at pumili ng pangunahing landas ng query sa halip na kumopya ng dalawang hindi-kondisyonal na instruction block sa `AGENTS.md`.

Ini-install ng `graphify install` ang lokal na assistant integration; hindi ito nagtatatag ng MCP connection. Ang isang MCP client ay hindi kailangang magpatakbo ng mga lokal na CLI query upang gamitin ang nakakonektang server nito. Ang isang lokal na naka-host na server ay kailangan pa rin ng sarili nitong Graphify installation at graph, samantalang ang isang naka-host na koneksyon ay maaaring maghain ng isang graph na wala sa working directory ng client. Kung nawawala ang mga inaasahang tool, suriin ang kaugnay na CLI installation o MCP connection sa halip na ituring na mapagpapalit ang mga instruksyon ng kabilang setup.

---

## Ano ang nasa ulat

Binubuod ng `GRAPH_REPORT.md` ang mga god node, community, at pangunahing landas para sa malawak na pagsusuri ng arkitektura. Kung paano itinatayo ang graph at kung ano ang nilalaman nito: **[Paano gumagana ang graphify](https://docs.graphify.com/concepts/architecture)**.

---

## Anong mga file ang hinahawakan nito: ~40 languages

Pini-parse ng graphify ang ~40 na programming language nang lokal gamit ang tree-sitter AST, at imimapa ang docs, PDF, mga larawan, at audio/video sa pamamagitan ng isang opsyonal na semantikong pass. Buong listahan: **[Mga suportadong input](https://docs.graphify.com/concepts/supported-inputs)**.

---

## Mga karaniwang utos

```bash
/graphify .                        # build graph for current folder
/graphify ./docs --update          # re-extract only changed files
/graphify . --cluster-only         # rerun clustering without re-extracting
/graphify . --cluster-only --resolution 1.5      # more granular communities
/graphify . --cluster-only --exclude-hubs 99     # suppress utility super-hubs from god-node rankings
/graphify . --no-viz               # skip the HTML, just the report + JSON
/graphify . --wiki                 # build a markdown wiki from the graph
graphify export callflow-html      # Mermaid architecture/call-flow HTML (auto-regenerates on every git commit if hook is installed)

/graphify query "what connects auth to the database?"
/graphify path "UserService" "DatabasePool"
/graphify explain "RateLimiter"

/graphify add https://arxiv.org/abs/1706.03762   # fetch a paper and add it
/graphify add <youtube-url>                       # transcribe and add a video

graphify hook install              # auto-rebuild on commit + branch checkout (run `graphify update .` after `git pull`: see "Recommended workflow" below)
graphify merge-graphs a.json b.json              # combine two graphs

graphify prs                       # PR dashboard: CI state, review status, worktree mapping
graphify prs 42                    # deep dive on PR #42 with graph impact
graphify prs --triage              # AI ranks your review queue (uses whatever backend is configured)
graphify prs --conflicts           # PRs sharing graph communities: merge-order risk
```

Tingnan ang [buong command reference](#full-command-reference) sa ibaba.

---

## Pagpapabaya sa mga file

Iginagalang ng graphify ang `.gitignore` at sumusuporta sa mga pattern na `--exclude` at isang proyektong `.graphifyignore`. Mga detalye: **[Configuration](https://docs.graphify.com/reference/configuration)**.


## Configuration ng proyekto

Gumawa ng isang `.graphifyrc` sa scan root para sa mga setting na pag-aari ng proyekto sa halip na ng isang run. Isang `key=value` kada linya; ang mga linyang nagsisimula sa `#` ay mga komento.

**Mga malabong extension.** May ilang extension na nangangahulugan ng magkakaibang wika sa magkakaibang proyekto: ang `.inc` ay PHP sa pfSense, Pascal sa isang Delphi tree, SQL o assembly sa iba; ang `.h` ay C o C++; ang `.m` ay Objective-C o MATLAB. Kailangang pumili ang graphify ng isang global na default, at kapag maling napili nito ay hindi nabibigo ang file: pini-parse ito bilang maling wika at nagbubunga ng ilang paimbabaw na node, kaya mukhang populado ang graph habang nawawala ang mga tunay na simbolo. Ideklara kung ano ang ibig sabihin ng extension sa iyong repo:

```
# .graphifyrc
# A language name:
language.inc=php
# Or an extension graphify already knows:
language.tpl=.ts
# Baked into the git hooks (see Team setup):
viz_node_limit=0
```

Ang deklarasyon ay dumadaloy sa klasipikasyon, pagpili ng extractor, grammar at resolution, imports, `graphify watch`, at ang AST cache (ang isang file na muling pini-parse sa ilalim ng ibang wika ay hindi kailanman muling gumagamit ng lumang entry), at ang parehong `.graphifyrc` ay binabasa ng `extract`, `update`, ang mga hook, ang MCP server, at ang `/graphify` na skill. Ang isang typo ay iniuulat nang isang beses sa stderr at ang scan ay nagpapatuloy gamit ang mga default. Kung paano nakikipag-ugnayan ang mga deklarasyon sa caching, incremental na rebuild, at import resolution: **[Configuration](https://docs.graphify.com/reference/configuration)**.

---

## Setup ng team

I-commit o ibahagi ang graph upang ang buong team mo ay nag-query ng parehong konteksto, at suriin ang mga pull request na may konteksto ng graph. Tingnan ang **[Ibahagi ang konteksto sa iyong team](https://docs.graphify.com/guides/team-workflows)** at **[Suriin ang mga pull request](https://docs.graphify.com/guides/pull-requests)**.

---

## Paggamit ng graph nang direkta

Lampas sa iyong AI assistant, i-query ang `graph.json` nang diretso mula sa CLI gamit ang `graphify query`, `graphify path`, at `graphify explain`. Ang isang pangalan na tumutugma sa ilang node ay tinatanggihan kasama ang nakalistang mga kandidato sa halip na hulaan. Mababasa ng mga script ang resulta mula sa exit code: `0` isang sagot, `3` isang malabong pangalan, `4` walang tumutugmang node. Tingnan ang **[Magtanong ng mas mahusay na mga tanong sa graph](https://docs.graphify.com/guides/querying)** at ang **[query reference](https://docs.graphify.com/reference/query)**.

---

## Mga environment variable

Ang mga backend, API key, hook behavior, at tuning ay kontrolado ng mga environment variable. Buong talahanayan: **[Configuration](https://docs.graphify.com/reference/configuration)**.

---

## Privacy

- **Mga code file**: pinoproseso nang lokal sa pamamagitan ng tree-sitter. Walang umaalis sa iyong makina. Ang isang code-only na corpus ay hindi nangangailangan ng API key: ang `graphify extract` ay tumatakbo nang ganap na offline. Sa isang pinaghalong repo, idagdag ang `--code-only` upang i-index lamang ang code at laktawan ang docs/PDF/mga larawan na kung hindi ay mangangailangan ng LLM.
- **Video / audio**: nasa-transcribe nang lokal gamit ang faster-whisper. Walang umaalis sa iyong makina.
- **Docs, PDF, mga larawan**: ipinapadala sa iyong AI assistant para sa semantikong extraction (sa pamamagitan ng `/graphify` na skill, gamit ang kahit anong modelo na pinapatakbo ng iyong IDE session). Ang headless na `graphify extract` ay nangangailangan ng `GEMINI_API_KEY` / `GOOGLE_API_KEY` (Gemini), `MOONSHOT_API_KEY` (Kimi), `ANTHROPIC_API_KEY` (Claude), `OPENAI_API_KEY` (OpenAI), `DEEPSEEK_API_KEY` (DeepSeek), isang tumatakbong Ollama instance (`OLLAMA_BASE_URL`), AWS credentials sa pamamagitan ng standard provider chain (Bedrock - walang kailangang API key, gumagamit ng IAM), o ang `claude` CLI binary (Claude Code - walang kailangang API key, gumagamit ng iyong Claude subscription). Ang `--dedup-llm` na flag ay gumagamit ng parehong key.
- **Data residency**: ang `graphify extract` ay awtomatikong tumutukoy kung aling provider ang gagamitin batay sa kung aling API key ang nakatakda (priyoridad: Gemini → Kimi → Claude → OpenAI → DeepSeek → Azure → Bedrock → Ollama). Para sa code na may mga kinakailangan sa data-residency, gamitin ang `--backend ollama` (ganap na lokal) o magpasa ng isang tahasang `--backend` na flag. Ang Kimi (`MOONSHOT_API_KEY`) ay nagruruta sa mga server ng Moonshot AI sa China.
- **Walang telemetry**, walang usage tracking, walang analytics.
- **Query logging**: bawat tawag na `graphify query`, `graphify path`, `graphify explain`, at MCP `query_graph` ay nilo-log sa `~/.cache/graphify-queries.log` sa format na JSON Lines (timestamp, tanong, corpus, mga node na ibinalik, tagal). Ang buong subgraph na mga tugon ay **hindi** iniimbak bilang default. Itakda ang `GRAPHIFY_QUERY_LOG_DISABLE=1` upang mag-opt out, o `GRAPHIFY_QUERY_LOG=/dev/null` upang patahimikin nang hindi dini-disable ang code path.

---

## Troubleshooting

Mga karaniwang isyu sa install at extraction at ang kanilang mga ayos: **[Troubleshooting](https://docs.graphify.com/troubleshooting)**.

---

## Buong command reference

Bawat utos at flag, na may mga halimbawa: **[CLI reference](https://docs.graphify.com/reference/overview)**.

---

## Matuto pa

- [docs.graphify.com](https://docs.graphify.com): buong dokumentasyon: mga gabay, command reference, at mga integrasyon
- [Paano ito gumagana](../how-it-works.md): ang extraction pipeline, community detection, confidence scoring, benchmarks
- [ARCHITECTURE.md](../../ARCHITECTURE.md): paghahati-hati ng module, kung paano magdagdag ng wika
- [Mga opsyonal na integrasyon](../docker-mcp-sqlite.md): Docker MCP Toolkit + SQLite
- [The Memory Layer](https://safishamsi.gumroad.com/l/qetvlo): ang aklat tungkol sa mga ideya sa likod ng graphify, ang arkitektura mula simula hanggang dulo

---

## Graphify Cloud

Ang [**Graphify Cloud**](https://app.graphify.com/login) ay ang laging-nakabukas na layer na itinayo sa ibabaw ng graphify. Sa halip na isang graph na muli mong itinatayo kapag kailangan kada folder, pinapanatili nito ang isang buhay na graph sa buong software development lifecycle mo:

- **80% mas kaunting token**: ang laging-nakabukas na memory ay nangangahulugang hihinto ang iyong mga agent sa muling-pagbabasa at muling-pagpapaliwanag ng codebase bawat sesyon.
- **Monorepo at cross-repo**: isang konektadong graph sa bawat serbisyo at repository, hindi isang graph kada folder.
- **Formal verification**: suriin ang mga architectural at dependency invariant laban sa buhay na graph.
- **Code review na may bird's-eye view ng iyong SDLC**: tingnan kung paano kumakalat ang isang pagbabago sa buong sistema bago ka mag-merge.
- **Mga SDLC connector**: hilahin ang Sentry, Jira, at iba pa, upang ang mga insidente, ticket, at code ay nasa iisang graph.
- **Laging-nakabukas**: nag-a-update nang tuloy-tuloy sa background sa code, docs, at mga pulong.

**[Magsimula ng libreng 14-araw na pagsubok sa app.graphify.com &rarr;](https://app.graphify.com/login)**

---

## Pag-aambag

Malugod na tinatanggap ang mga kontribusyon. Tingnan ang **[CONTRIBUTING.md](../../CONTRIBUTING.md)** para sa development setup, ang mga utos para sa test at CI-parity, ang git workflow, at kung ano ang bumubuo ng isang matibay na kontribusyon (ang mga worked example at extraction bug report ang pinaka-kapaki-pakinabang). Arkitektura at kung paano magdagdag ng wika: [ARCHITECTURE.md](../../ARCHITECTURE.md).

Bago rito? Kumusta sa [Discord](https://discord.gg/graphify) o sa [GitHub Discussions](https://github.com/Graphify-Labs/graphify/discussions).

---

## Mga nag-ambag

<a href="https://github.com/Graphify-Labs/graphify/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=Graphify-Labs/graphify" alt="graphify contributors" />
</a>

Ginawa gamit ang [contrib.rocks](https://contrib.rocks).

---

## Mga pagsasalin

Ang README ay magagamit sa 32 na wika. Gamitin ang language switcher sa itaas ng file na ito upang basahin ito sa iyong wika, o mag-browse sa [`docs/translations/`](./). Upang pahusayin ang isang pagsasalin o magdagdag ng bago, magbukas ng pull request laban sa katugmang file doon.

---

## Pagtatayo sa ibabaw ng graphify

May ginagawa ka ba sa ekosistema ng graphify? Iyon ay hinihikayat. Kung ang proyekto mo ay gumagamit ng "graphify" sa pangalan nito (halimbawa `graphify-dashboard` o `graphify-action`), mangyaring magdagdag ng isang maikling tala sa iyong README na nililinaw na ito ay itinayo ng komunidad at hindi kaanib ng o inendorso ng Graphify Labs. Ang "graphify" at ang graphify logo ay mga marka ng Graphify Labs; mangyaring huwag gamitin ang mga ito sa paraang nagpapahiwatig ng opisyal na katayuan.

---

## Komunidad at mga link

<p align="center">
  <a href="https://graphify.com"><img src="https://img.shields.io/badge/Website-graphify.com-4c1?style=flat&logo=googlechrome&logoColor=white" alt="Website"/></a>
  <a href="https://discord.gg/graphify"><img src="https://img.shields.io/badge/Discord-Join-5865F2?style=flat&logo=discord&logoColor=white" alt="Discord"/></a>
  <a href="https://x.com/graphify"><img src="https://img.shields.io/badge/X-graphify-000000?logo=x&logoColor=white" alt="X"/></a>
  <a href="https://www.youtube.com/@graphifylabs"><img src="https://img.shields.io/badge/YouTube-Graphify%20Labs-FF0000?style=flat&logo=youtube&logoColor=white" alt="YouTube"/></a>
  <a href="https://github.com/sponsors/safishamsi"><img src="https://img.shields.io/badge/sponsor-safishamsi-ea4aaa?logo=github-sponsors" alt="Sponsor"/></a>
  <a href="https://safishamsi.gumroad.com/l/qetvlo"><img src="https://img.shields.io/badge/Book-The%20Memory%20Layer-2ea44f?style=flat&logo=gitbook&logoColor=white" alt="The Memory Layer"/></a>
</p>
