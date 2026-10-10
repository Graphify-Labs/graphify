<p align="center">
  <a href="https://graphify.com"><img src="https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/graphify-logo.png" width="360" height="189" alt="Graphify"/></a>
</p>

<p align="center">
  <a href="https://trendshift.io/repositories/25296?utm_source=repository-badge&amp;utm_medium=badge&amp;utm_campaign=badge-repository-25296" target="_blank" rel="noopener noreferrer"><img src="https://trendshift.io/api/badge/repositories/25296" alt="Graphify-Labs%2Fgraphify | Trendshift" width="250" height="55"/></a>
</p>

<div align="center">
<details><summary><b>Read this in other languages</b></summary>

🇺🇸 <a href="../../README.md">English</a> | 🇨🇳 <a href="README.zh-CN.md">简体中文</a> | 🇯🇵 <a href="README.ja-JP.md">日本語</a> | 🇰🇷 <a href="README.ko-KR.md">한국어</a> | 🇩🇪 <a href="README.de-DE.md">Deutsch</a> | 🇫🇷 <a href="README.fr-FR.md">Français</a> | 🇪🇸 <a href="README.es-ES.md">Español</a> | 🇮🇳 <a href="README.hi-IN.md">हिन्दी</a> | 🇧🇷 <a href="README.pt-BR.md">Português</a> | 🇷🇺 <a href="README.ru-RU.md">Русский</a> | 🇸🇦 <a href="README.ar-SA.md">العربية</a> | 🇮🇷 <a href="README.fa-IR.md">فارسی</a> | 🇮🇹 <a href="README.it-IT.md">Italiano</a> | 🇵🇱 <a href="README.pl-PL.md">Polski</a> | 🇳🇱 <a href="README.nl-NL.md">Nederlands</a> | 🇹🇷 <a href="README.tr-TR.md">Türkçe</a> | 🇺🇦 <a href="README.uk-UA.md">Українська</a> | 🇻🇳 <a href="README.vi-VN.md">Tiếng Việt</a> | 🇮🇩 <a href="README.id-ID.md">Bahasa Indonesia</a> | 🇸🇪 <a href="README.sv-SE.md">Svenska</a> | 🇬🇷 <a href="README.el-GR.md">Ελληνικά</a> | 🇷🇴 <a href="README.ro-RO.md">Română</a> | 🇨🇿 <a href="README.cs-CZ.md">Čeština</a> | 🇫🇮 <a href="README.fi-FI.md">Suomi</a> | 🇩🇰 <a href="README.da-DK.md">Dansk</a> | 🇳🇴 <a href="README.no-NO.md">Norsk</a> | 🇭🇺 <a href="README.hu-HU.md">Magyar</a> | 🇹🇭 <a href="README.th-TH.md">ภาษาไทย</a> | 🇺🇿 <a href="README.uz-UZ.md">Oʻzbekcha</a> | 🇹🇼 <a href="README.zh-TW.md">繁體中文</a> | 🇵🇭 <a href="README.fil-PH.md">Filipino</a> | 🇮🇱 <a href="README.he-IL.md">עברית</a>

</details>
</div>

<p align="center">
  <a href="https://pypi.org/project/graphifyy/"><img src="https://img.shields.io/pypi/v/graphifyy" alt="PyPI"/></a>
  <a href="https://github.com/Graphify-Labs/graphify/actions/workflows/ci.yml"><img src="https://github.com/Graphify-Labs/graphify/actions/workflows/ci.yml/badge.svg?branch=v8" alt="CI"/></a>
  <a href="../../LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue" alt="License: Apache-2.0"/></a>
  <a href="https://pepy.tech/project/graphifyy"><img src="https://img.shields.io/pepy/dt/graphifyy?color=blue&label=downloads" alt="Downloads"/></a>
  <a href="https://docs.graphify.com"><img src="https://img.shields.io/badge/Docs-docs.graphify.com-0b7285?style=flat&logo=readthedocs&logoColor=white" alt="Docs"/></a>
  <a href="https://app.graphify.com/login"><img src="https://img.shields.io/badge/Graphify%20Cloud-app.graphify.com-118d4f?style=flat&logoColor=white" alt="Graphify Cloud"/></a>
  <a href="https://discord.gg/XDnKVpzdXB"><img src="https://img.shields.io/badge/Discord-Join-5865F2?style=flat&logo=discord&logoColor=white" alt="Discord"/></a>
  <a href="https://www.youtube.com/@graphifylabs"><img src="https://img.shields.io/badge/YouTube-Graphify%20Labs-FF0000?style=flat&logo=youtube&logoColor=white" alt="YouTube"/></a>
  <a href="https://www.linkedin.com/company/graphify-labs"><img src="https://img.shields.io/badge/LinkedIn-Graphify%20Labs-0077B5?logo=linkedin" alt="LinkedIn"/></a>
  <a href="https://www.ycombinator.com/companies/graphify-labs"><img src="https://img.shields.io/badge/Y%20Combinator-S26-F0652F?style=flat&logo=ycombinator&logoColor=white" alt="YC S26"/></a>
</p>

<p align="center">
  <b>Reducér agenternes tokenforbrug med 80%.</b> Graphify Cloud er en altid aktiv hukommelse, der styrer dine agenter, holder kodekvaliteten høj og beviser korrekthed med formel verifikation. <a href="https://app.graphify.com/login"><b>Start en gratis 14-dages prøveperiode &rarr;</b></a>
</p>

Skriv `/graphify` i din AI-kodeassistent, og den kortlægger hele dit projekt (kode, dokumenter, PDF-filer, billeder, videoer) til en **vidensgraf**, som du kan **forespørge i stedet for at greppe** gennem filer.

- **Kode kortlægges gratis, fuldt lokalt.** Kode parses med tree-sitter AST: deterministisk, ingen LLM, intet forlader din maskine. (Dokumenter, PDF-filer, billeder og video bruger din assistents model eller en konfigureret API-nøgle til en semantisk gennemgang.)
- **Hver kant forklares.** Hver forbindelse mærkes `EXTRACTED` (eksplicit i kilden) eller `INFERRED` (udledt af graphify), så du kan skelne det, der blev læst direkte, fra det, der blev udledt.
- **Ikke et vektorindeks.** Ingen embeddings, intet vektorlager: en rigtig graf, du gennemløber. Stil et spørgsmål, spor stien mellem to ting, eller forklar ét begreb.

> [!NOTE]
> **Vil du have dette altid aktivt?** [Graphify Cloud](https://app.graphify.com/login) holder grafen levende gennem hele din SDLC: understøttelse af monorepo og krydsrepo, formel verifikation og kodegennemgang med et fugleperspektiv over din SDLC, plus connectors til Sentry, Jira med mere, så hændelser og sager ligger i samme graf som din kode. **[Start en gratis 14-dages prøveperiode på app.graphify.com](https://app.graphify.com/login)**.

<p align="center">
  <img src="https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/graph-hero.png" alt="graphify's interactive graph.html showing the FastAPI codebase as a force-directed knowledge graph with a legend of detected communities" width="900">
</p>
<p align="center">
  <em>FastAPI-kodebasen kortlagt af graphify. Hver knude er et begreb, farver er detekterede fællesskaber, og det hele er klikbart i graph.html.</em>
</p>

**Kom godt i gang** (30 sekunder):

```bash
uv tool install graphifyy      # install the CLI (or: pipx install graphifyy)
graphify install               # register the skill with your AI assistant
```

Derefter, i din AI-assistent:

```
/graphify .
```

Det er det. Du får **tre filer**:

```
graphify-out/
├── graph.html       open in any browser — click nodes, filter, search
├── GRAPH_REPORT.md  the highlights: key concepts, surprising connections, suggested questions
└── graph.json       the full graph — query it anytime without re-reading your files
```

Den gemte graf inkluderer `graph.schema_version`, så integrationer kan registrere
inkompatible formatændringer, plus `graph.graphify_version`, der identificerer den
Graphify-udgivelse, der frembragte den.

**Fungerer i** Claude Code, Cursor, Codex, Gemini CLI, GitHub Copilot og 15+ flere — [vælg din platform](#install).

---

## Dokumentation

Fulde vejledninger og reference findes på **[docs.graphify.com](https://docs.graphify.com)**:

- **[Hurtig start](https://docs.graphify.com/quickstart)** — byg din første graf
- **[CLI-reference](https://docs.graphify.com/reference/overview)** — hver kommando og hvert flag
- **[Stil bedre grafspørgsmål](https://docs.graphify.com/guides/querying)** — forespørgselsmønstre
- **[Konfiguration](https://docs.graphify.com/reference/configuration)** — miljøvariabler og tuning
- **[Understøttede input](https://docs.graphify.com/concepts/supported-inputs)** — sprog og filtyper
- **[Teamworkflows](https://docs.graphify.com/guides/team-workflows)** og **[PR-gennemgang](https://docs.graphify.com/guides/pull-requests)**
- **[Fejlfinding](https://docs.graphify.com/troubleshooting)** og **[Sådan virker det](https://docs.graphify.com/concepts/architecture)**

---

## Se det i aktion

<p align="center">
  <img src="https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/demo-path.svg" alt="graphify path query: a terminal asks for the shortest path between FastAPI and ModelField, and the answer lights up hop by hop across the knowledge graph" width="900">
</p>

Når grafen er bygget, forespørger du den i stedet for at læse filer. Rigtig output, graphify kørt på FastAPI-kodebasen vist ovenfor:

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

Hver kant bærer et **konfidensmærke** (`EXTRACTED` = eksplicit i kilden, `INFERRED` = udledt ved resolution), så du kan skelne det, der blev læst direkte, fra det, der blev udledt. `graphify query "<question>"` returnerer en afgrænset delgraf for et spørgsmål i almindeligt sprog, og `graphify path A B` sporer, hvordan to ting hænger sammen.

---

## Hvad den gør

Hvad du får ud af kassen:

| Funktion | Hvad du får |
|---|---|
| **Gudeknuder** | De mest forbundne begreber, så du ser, hvad alt flyder igennem |
| **Fællesskaber** | Grafen opdelt i delsystemer (Leiden), med LLM-frie etiketter |
| **Links på tværs af filer** | `calls` / `imports` / `inherits` / `mixes_in` opløst på tværs af ~40 sprog via tree-sitter AST |
| **Query, path, explain** | Stil et spørgsmål, spor stien mellem to ting, eller forklar ét begreb, alt sammen mod `graph.json` |
| **Begrundelse + dokumentreferencer** | `# NOTE:` / `# WHY:`-kommentarer og ADR/RFC-citater bliver førsteklasses knuder forbundet til koden |
| **Ud over kode** | Dokumenter, PDF-filer, billeder og video/lyd kortlægges alle ind i samme graf |
| **Lokalt først** | Kode parses lokalt med tree-sitter (ingen LLM, intet forlader din maskine); kun den semantiske gennemgang af dokumenter/medier kalder en backend, og kun hvis du konfigurerer en |

> [!TIP]
> Kører du dette på tværs af mange repos eller et monorepo? [Graphify Cloud](https://app.graphify.com/login) gør det kontinuerligt og reducerer agenternes tokenforbrug med 80%, med krydsrepolinks, kodegennemgang på tværs af hele SDLC, formel verifikation og Sentry/Jira-connectors. [Start en gratis 14-dages prøveperiode &rarr;](https://app.graphify.com/login)

---

## Benchmarks

| Benchmark | Mål | graphify | Feltet |
|---|---|---|---|
| LOCOMO (n=300) | recall@10 | **0.497** | mem0 0.048, supermemory 0.149 |
| LOCOMO (n=300) | QA-nøjagtighed | 45.3% | supermemory 49.7%, mem0 27.3% |
| LongMemEval-S (n=50) | QA-nøjagtighed | **76%** | på niveau med tæt RAG |
| ERPNext på tværs af værktøjer (n=6) | dækning af nøglefakta | **82.0%** | grep/read-baseline 70.8% |
| Grafbygning | LLM-kreditter | **0** | pr. token for de fleste systemer |

Hvert system kørte på den samme harness med samme model og budgetter, bedømt af en dommer blindvalideret mod en anden dommer (90.6% enighed, Cohens kappa 0.81). Fulde tabeller pr. system, resultatet for kodeintelligens og reproduktionskommandoer: **[BENCHMARKS.md](../../BENCHMARKS.md)**.

---

## Forudsætninger

| Krav | Minimum | Tjek | Installér |
|---|---|---|---|
| Python | 3.10+ | `python --version` | [python.org](https://www.python.org/downloads/) |
| uv *(anbefalet)* | enhver | `uv --version` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| pipx *(alternativ)* | enhver | `pipx --version` | `pip install pipx` |

**macOS hurtig installation (Homebrew):**
```bash
brew install python@3.12 uv
```

**Windows hurtig installation:**
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
> **Officiel pakke:** PyPI-pakken er `graphifyy` (dobbelt-y). Andre `graphify*`-pakker på PyPI er ikke tilknyttet. CLI-kommandoen er stadig `graphify`.

Det officielle kildekoderepository er [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify).

**Trin 1 — installér pakken:**

```bash
# Recommended (isolated env; if 'graphify' isn't found after, run: uv tool update-shell):
uv tool install graphifyy

# Alternatives:
pipx install graphifyy
pip install graphifyy  # may need PATH setup — see note below
```

**Trin 2 — registrér skillet hos din AI-assistent:**

```bash
graphify install
```

Det er det. Åbn din AI-assistent, og skriv `/graphify .`

For at installere assistent-skillet i det aktuelle repository i stedet for din
brugerprofil skal du tilføje `--project`:

```bash
graphify install --project
graphify install --project --platform codex
```

Projektafgrænsede installationer skrives under den aktuelle mappe, for eksempel
`.claude/skills/graphify/SKILL.md` eller `.agents/skills/graphify/SKILL.md` (plus en
`references/`-sidecar, som skillet indlæser efter behov), og
udskriver et `git add`-hint for filer, der kan committes.
Kommandoer pr. platform, der understøtter projektafgrænsede installationer, accepterer samme flag,
for eksempel `graphify claude install --project` eller `graphify codex install --project`.

> [!TIP]
> Støder du på `command not found`, et `pip`-problem på Mac/Windows, PowerShell-citering, `uvx`-brug, PATH-særheder med git-hooks eller strict mode? Se **[Installation](https://docs.graphify.com/installation)** og **[Fejlfinding](https://docs.graphify.com/troubleshooting)**.

<details>
<summary><b>Vælg din platform</b> (20+ assistenter, klik for at udvide)</summary>

| Platform | Installationskommando |
|----------|----------------|
| Claude Code (Linux/Mac) | `graphify install` |
| Claude Code (Windows) | `graphify install` (registreres automatisk) eller `graphify install --platform windows` |
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
| Agent Skills (på tværs af frameworks) | `graphify install --platform agents` (alias `--platform skills`) |
| Kiro IDE/CLI | `graphify kiro install` |
| Pi coding agent | `graphify install --platform pi` |
| Cursor | `graphify cursor install` |
| Devin CLI | `graphify devin install` |
| Google Antigravity | `graphify antigravity install` |

Codex-brugere skal også have `multi_agent = true` under `[features]` i `~/.codex/config.toml` for parallel ekstraktion. CodeBuddy bruger samme Agent-værktøj og PreToolUse-hookmekanisme som Claude Code. Factory Droid bruger `Task`-værktøjet til parallel afsendelse af subagenter. OpenClaw og Aider bruger sekventiel ekstraktion (understøttelse af parallelle agenter er stadig tidlig på disse platforme). Trae bruger Agent-værktøjet til parallel afsendelse af subagenter og understøtter **ikke** `PreToolUse`-hooks, så AGENTS.md er den altid aktive mekanisme.

`--platform agents` (alias `--platform skills`) retter sig mod de generiske placeringer for [Agent-Skills](https://github.com/anthropics/skills) på tværs af frameworks: specifikationens brugerglobale `~/.agents/skills/` (læses af `npx skills` og specifikationskonforme frameworks) for en global installation, og `./.agents/skills/` for en projektinstallation (`--project`). Det blotte `graphify install` forbliver enkeltplatform (Claude Code) med vilje — brug den navngivne `agents`-platform, når du ønsker, at skillet skal kunne opdages af ethvert framework, der læser `.agents/skills`.

> Codex bruger `$graphify` i stedet for `/graphify`.

</details>

<details>
<summary><b>Valgfrie ekstraer</b> (installér kun det, du har brug for)</summary>

| Ekstra | Hvad det tilføjer | Installér |
|---|---|---|
| `pdf` | PDF-ekstraktion | `uv tool install "graphifyy[pdf]"` |
| `office` | Understøttelse af `.docx` og `.xlsx` | `uv tool install "graphifyy[office]"` |
| `google` | Rendering af Google Sheets | `uv tool install "graphifyy[google]"` |
| `video` | Transskribering af video/lyd (faster-whisper + yt-dlp) | `uv tool install "graphifyy[video]"` |
| `mcp` | MCP stdio-server | `uv tool install "graphifyy[mcp]"` |
| `neo4j` | Understøttelse af push til Neo4j | `uv tool install "graphifyy[neo4j]"` |
| `falkordb` | Understøttelse af push til FalkorDB | `uv tool install "graphifyy[falkordb]"` |
| `svg` | SVG-grafeksport | `uv tool install "graphifyy[svg]"` |
| `leiden` | Leiden-fællesskabsdetektering (graspologic på Python < 3.13; indbygget backend på 3.13+) | `uv tool install "graphifyy[leiden]"` |
| `ollama` | Lokal inferens med Ollama | `uv tool install "graphifyy[ollama]"` |
| `openai` | OpenAI / OpenAI-kompatible API'er | `uv tool install "graphifyy[openai]"` |
| `gemini` | Google Gemini API | `uv tool install "graphifyy[gemini]"` |
| `anthropic` | Anthropic Claude API (`--backend claude`, bruger `ANTHROPIC_API_KEY`) | `uv tool install "graphifyy[anthropic]"` |
| `bedrock` | AWS Bedrock (bruger IAM, ingen API-nøgle) | `uv tool install "graphifyy[bedrock]"` |
| `azure` | Azure OpenAI Service (`--backend azure`, bruger `AZURE_OPENAI_API_KEY` + `AZURE_OPENAI_ENDPOINT`) | `uv tool install "graphifyy[openai]"` |
| `sql` | Ekstraktion af SQL-skema | `uv tool install "graphifyy[sql]"` |
| `postgres` | Live-introspektion af PostgreSQL (`--postgres DSN`) | `uv tool install "graphifyy[postgres]"` |
| `dm` | BYOND DreamMaker `.dm`/`.dme` AST-ekstraktion (kan kræve en C-compiler + `python3-dev`, hvis intet wheel matcher din platform) | `uv tool install "graphifyy[dm]"` |
| `terraform` | Terraform / HCL `.tf`/`.tfvars`/`.hcl` AST-ekstraktion | `uv tool install "graphifyy[terraform]"` |
| `pascal` | Pascal / Delphi `.pas`/`.dpr`/`.dpk`/`.inc` AST-ekstraktion (mere præcise `calls`/`inherits`-kanter; falder tilbage til en regex-ekstraktor, når den mangler) | `uv tool install "graphifyy[pascal]"` |
| `ocaml` | OCaml `.ml`/`.mli` AST-ekstraktion | `uv tool install "graphifyy[ocaml]"` |
| `commonlisp` | Common Lisp `.lisp`/`.cl`/`.lsp`/`.asd` AST-ekstraktion | `uv tool install "graphifyy[commonlisp]"` |
| `robot` | Robot Framework `.robot`/`.resource`-ekstraktion (suites, testcases, nøgleord, kanter for nøgleordskald og ressource-/biblioteksimport) | `uv tool install "graphifyy[robot]"` |
| `chinese` | Kinesisk forespørgselssegmentering (jieba) | `uv tool install "graphifyy[chinese]"` |
| `all` | Alt ovenstående | `uv tool install "graphifyy[all]"` |

</details>

---

## Få din assistent til altid at bruge grafen

Kør dette én gang i dit projekt, efter du har bygget en graf:

Kør `graphify <platform> install` én gang i dit projekt, for eksempel `graphify claude install` eller `graphify codex install` (eller `graphify install --platform <name>`).

Dette skriver en lille konfigurationsfil, der fortæller din assistent, at den skal konsultere vidensgrafen ved spørgsmål om kodebasen, og foretrække afgrænsede forespørgsler som `graphify query "<question>"` frem for at læse hele rapporten eller greppe rå filer.

- **Hook-platforme** (Claude Code, Gemini CLI): en hook udløses automatisk før søgeagtige værktøjskald (og, på Claude Code, før kildefiler læses én ad gangen via Read/Glob-værktøjerne) og skubber din assistent mod grafstien.
- **Instruktionsfilplatforme** (Codex, OpenCode, Cursor osv.): vedvarende instruktionsfiler (`AGENTS.md`, `.cursor/rules/` osv.) giver den samme forespørgsel-først-vejledning.

`GRAPH_REPORT.md` er stadig tilgængelig til bred arkitekturgennemgang.

**CodeBuddy** gør de samme to ting som Claude Code: skriver en `CODEBUDDY.md`-sektion, der fortæller CodeBuddy at læse `graphify-out/GRAPH_REPORT.md` før besvarelse af arkitekturspørgsmål, og installerer `PreToolUse`-hooks (`.codebuddy/settings.json`), der udløses før Bash-søgekommandoer og fillæsninger og skubber mod `graphify query` i stedet.

**Codex** skriver til `AGENTS.md`, hvilket er det, der faktisk bærer den altid aktive grafvejledning på denne platform. `graphify codex install` registrerer også en `PreToolUse`-hook i `.codex/hooks.json` (`graphify hook-check`), men den post er bevidst en **no-op**: Codex Desktop afviser `hookSpecificOutput.additionalContext` på `PreToolUse`, så at udsende et skub dér ville ødelægge Bash-værktøjskald. I modsætning til Claude Code, hvor hooken (`graphify hook-guard`) udfører skubbet, udløses hooken på Codex og gør bevidst ingenting, og `AGENTS.md` er den altid aktive mekanisme.

**Kilo Code** installerer Graphify-skillet til `~/.config/kilo/skills/graphify/SKILL.md` og en indbygget `/graphify`-kommando til `~/.config/kilo/command/graphify.md`. `graphify kilo install` skriver også `AGENTS.md` plus et indbygget `tool.execute.before`-plugin (`.kilo/plugins/graphify.js` + registrering i `.kilo/kilo.json` eller `.kilo/kilo.jsonc`), så Kilo får den samme altid aktive grafpåmindelsesadfærd gennem indbygget `.kilo`-konfiguration.

**Cursor** skriver `.cursor/rules/graphify.mdc` med `alwaysApply: true`, så Cursor automatisk inkluderer den i hver samtale, ingen hook nødvendig.

For at fjerne graphify fra alle platforme på én gang: `graphify uninstall` (tilføj `--purge` for også at slette `graphify-out/`). Eller brug kommandoen pr. platform (f.eks. `graphify claude uninstall`).

---

## Hvad der er i rapporten

`GRAPH_REPORT.md` opsummerer gudeknuderne, fællesskaberne og nøglestierne til bred arkitekturgennemgang. Hvordan grafen bygges, og hvad den indeholder: **[Sådan virker graphify](https://docs.graphify.com/concepts/architecture)**.

---

## Hvilke filer den håndterer

graphify parser ~40 programmeringssprog lokalt med tree-sitter AST og kortlægger dokumenter, PDF-filer, billeder og lyd/video gennem en valgfri semantisk gennemgang. Fuld liste: **[Understøttede input](https://docs.graphify.com/concepts/supported-inputs)**.

---

## Almindelige kommandoer

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

graphify hook install              # auto-rebuild on commit + branch checkout (run `graphify update .` after `git pull` — see "Recommended workflow" below)
graphify merge-graphs a.json b.json              # combine two graphs

graphify prs                       # PR dashboard: CI state, review status, worktree mapping
graphify prs 42                    # deep dive on PR #42 with graph impact
graphify prs --triage              # AI ranks your review queue (uses whatever backend is configured)
graphify prs --conflicts           # PRs sharing graph communities — merge-order risk
```

Se den [fulde kommandoreference](#full-command-reference) nedenfor.

---

## Ignorering af filer

graphify respekterer `.gitignore` og understøtter `--exclude`-mønstre og en projekt-`.graphifyignore`. Detaljer: **[Konfiguration](https://docs.graphify.com/reference/configuration)**.

---

## Teamopsætning

Commit eller del grafen, så hele dit team forespørger mod den samme kontekst, og gennemgå pull requests med grafkontekst. Se **[Del kontekst med dit team](https://docs.graphify.com/guides/team-workflows)** og **[Gennemgå pull requests](https://docs.graphify.com/guides/pull-requests)**.

---

## Brug af grafen direkte

Ud over din AI-assistent kan du forespørge `graph.json` direkte fra CLI'en med `graphify query`, `graphify path` og `graphify explain`. Se **[Stil bedre grafspørgsmål](https://docs.graphify.com/guides/querying)** og **[forespørgselsreferencen](https://docs.graphify.com/reference/query)**.

---

## Miljøvariabler

Backends, API-nøgler, hook-adfærd og tuning styres af miljøvariabler. Fuld tabel: **[Konfiguration](https://docs.graphify.com/reference/configuration)**.

---

## Privatliv

- **Kodefiler** — behandles lokalt via tree-sitter. Intet forlader din maskine. Et korpus med kun kode kræver ingen API-nøgle — `graphify extract` kører fuldt offline. På et blandet repo skal du tilføje `--code-only` for kun at indeksere koden og springe de dokumenter/PDF-filer/billeder over, der ellers ville kræve en LLM.
- **Video / lyd** — transskriberes lokalt med faster-whisper. Intet forlader din maskine.
- **Dokumenter, PDF-filer, billeder** — sendes til din AI-assistent til semantisk ekstraktion (via `/graphify`-skillet, med den model, din IDE-session kører). Headless `graphify extract` kræver `GEMINI_API_KEY` / `GOOGLE_API_KEY` (Gemini), `MOONSHOT_API_KEY` (Kimi), `ANTHROPIC_API_KEY` (Claude), `OPENAI_API_KEY` (OpenAI), `DEEPSEEK_API_KEY` (DeepSeek), en kørende Ollama-instans (`OLLAMA_BASE_URL`), AWS-legitimationsoplysninger via den standardmæssige provider-kæde (Bedrock – ingen API-nøgle nødvendig, bruger IAM), eller `claude`-CLI-binæren (Claude Code – ingen API-nøgle nødvendig, bruger dit Claude-abonnement). Flaget `--dedup-llm` bruger den samme nøgle.
- **Dataophold** — `graphify extract` registrerer automatisk, hvilken provider der skal bruges, baseret på hvilken API-nøgle der er sat (prioritet: Gemini → Kimi → Claude → OpenAI → DeepSeek → Azure → Bedrock → Ollama). Til kode med krav om dataophold skal du bruge `--backend ollama` (fuldt lokal) eller angive et eksplicit `--backend`-flag. Kimi (`MOONSHOT_API_KEY`) ruter til Moonshot AI-servere i Kina.
- **Ingen telemetri**, ingen brugssporing, ingen analyse.
- **Forespørgselslogning** — hvert `graphify query`-, `graphify path`-, `graphify explain`- og MCP `query_graph`-kald logges til `~/.cache/graphify-queries.log` i JSON Lines-format (tidsstempel, spørgsmål, korpus, returnerede knuder, varighed). Fulde delgraf-svar gemmes **ikke** som standard. Sæt `GRAPHIFY_QUERY_LOG_DISABLE=1` for at fravælge, eller `GRAPHIFY_QUERY_LOG=/dev/null` for at dæmpe uden at deaktivere kodestien.

---

## Fejlfinding

Almindelige installations- og ekstraktionsproblemer og deres løsninger: **[Fejlfinding](https://docs.graphify.com/troubleshooting)**.

---

## Fuld kommandoreference

Hver kommando og hvert flag, med eksempler: **[CLI-reference](https://docs.graphify.com/reference/overview)**.

---

## Lær mere

- [docs.graphify.com](https://docs.graphify.com) — fuld dokumentation: vejledninger, kommandoreference og integrationer
- [Sådan virker det](../how-it-works.md) — ekstraktionspipelinen, fællesskabsdetektering, konfidensscoring, benchmarks
- [ARCHITECTURE.md](../../ARCHITECTURE.md) — modulopdeling, hvordan man tilføjer et sprog
- [Valgfrie integrationer](../docker-mcp-sqlite.md) — Docker MCP Toolkit + SQLite
- [The Memory Layer](https://safishamsi.gumroad.com/l/qetvlo) — bogen om idéerne bag graphify, arkitekturen fra ende til anden

---

## Graphify Cloud

[**Graphify Cloud**](https://app.graphify.com/login) er det altid aktive lag bygget oven på graphify. I stedet for en graf, du genopbygger efter behov pr. mappe, holder det én levende graf gennem hele din softwareudviklingslivscyklus:

- **80% færre tokens** — altid aktiv hukommelse betyder, at dine agenter holder op med at genlæse og genforklare kodebasen hver session.
- **Monorepo og krydsrepo** — én forbundet graf på tværs af hver tjeneste og hvert repository, ikke en graf pr. mappe.
- **Formel verifikation** — tjek arkitektur- og afhængighedsinvarianter mod den levende graf.
- **Kodegennemgang med et fugleperspektiv over din SDLC** — se, hvordan en ændring breder sig gennem hele systemet, før du merger.
- **SDLC-connectors** — hent Sentry, Jira med mere ind, så hændelser, sager og kode lever i én graf.
- **Altid aktiv** — opdateres kontinuerligt i baggrunden på tværs af kode, dokumenter og møder.

**[Start en gratis 14-dages prøveperiode på app.graphify.com &rarr;](https://app.graphify.com/login)**

---

## Bidrag

Bidrag er velkomne. Se **[CONTRIBUTING.md](../../CONTRIBUTING.md)** for udviklingsopsætningen, test- og CI-paritetskommandoerne, git-workflowet og hvad der gør et stærkt bidrag (gennemarbejdede eksempler og fejlrapporter om ekstraktion er de mest nyttige). Arkitektur og hvordan man tilføjer et sprog: [ARCHITECTURE.md](../../ARCHITECTURE.md).

Ny her? Sig hej på [Discord](https://discord.gg/XDnKVpzdXB) eller i [GitHub Discussions](https://github.com/Graphify-Labs/graphify/discussions).

---

## Bidragydere

<a href="https://github.com/Graphify-Labs/graphify/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=Graphify-Labs/graphify" alt="graphify contributors" />
</a>

Lavet med [contrib.rocks](https://contrib.rocks).

---

## Oversættelser

README'en er tilgængelig på 32 sprog. Brug sprogvælgeren øverst i denne fil for at læse den på dit, eller gennemse [`docs/translations/`](./). For at forbedre en oversættelse eller tilføje en ny skal du åbne en pull request mod den tilsvarende fil der.

---

## Byg videre på graphify

Bygger du noget i graphify-økosystemet? Det opmuntres. Hvis dit projekt bruger "graphify" i sit navn (for eksempel `graphify-dashboard` eller `graphify-action`), så tilføj gerne en kort note til din README, der tydeliggør, at det er community-bygget og ikke tilknyttet eller godkendt af Graphify Labs. "graphify" og graphify-logoet er varemærker tilhørende Graphify Labs; brug dem venligst ikke på en måde, der antyder officiel status.

---

## Fællesskab og links

<p align="center">
  <a href="https://graphify.com"><img src="https://img.shields.io/badge/Website-graphify.com-4c1?style=flat&logo=googlechrome&logoColor=white" alt="Website"/></a>
  <a href="https://discord.gg/XDnKVpzdXB"><img src="https://img.shields.io/badge/Discord-Join-5865F2?style=flat&logo=discord&logoColor=white" alt="Discord"/></a>
  <a href="https://x.com/graphify"><img src="https://img.shields.io/badge/X-graphify-000000?logo=x&logoColor=white" alt="X"/></a>
  <a href="https://www.youtube.com/@graphifylabs"><img src="https://img.shields.io/badge/YouTube-Graphify%20Labs-FF0000?style=flat&logo=youtube&logoColor=white" alt="YouTube"/></a>
  <a href="https://github.com/sponsors/safishamsi"><img src="https://img.shields.io/badge/sponsor-safishamsi-ea4aaa?logo=github-sponsors" alt="Sponsor"/></a>
  <a href="https://safishamsi.gumroad.com/l/qetvlo"><img src="https://img.shields.io/badge/Book-The%20Memory%20Layer-2ea44f?style=flat&logo=gitbook&logoColor=white" alt="The Memory Layer"/></a>
</p>
