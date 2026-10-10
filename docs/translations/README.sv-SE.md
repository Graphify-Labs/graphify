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
  <b>Minska agenternas tokenförbrukning med 80%.</b> Graphify Cloud är ett alltid aktivt minne som styr dina agenter, håller kodkvaliteten hög och bevisar korrekthet med formell verifiering. <a href="https://app.graphify.com/login"><b>Starta en kostnadsfri 14-dagars provperiod &rarr;</b></a>
</p>

Skriv `/graphify` i din AI-kodassistent så kartlägger den hela ditt projekt (kod, dokument, PDF-filer, bilder, videor) till en **kunskapsgraf** som du kan **fråga i stället för att greppa** genom filer.

- **Kod kartläggs gratis, helt lokalt.** Kod parsas med tree-sitter AST: deterministiskt, ingen LLM, inget lämnar din maskin. (Dokument, PDF-filer, bilder och video använder din assistents modell, eller en konfigurerad API-nyckel, för en semantisk genomgång.)
- **Varje kant förklaras.** Varje koppling märks `EXTRACTED` (explicit i källan) eller `INFERRED` (härledd av graphify), så att du kan skilja det som lästes direkt från det som härleddes.
- **Inte ett vektorindex.** Inga embeddings, ingen vektorlagring: en riktig graf som du traverserar. Ställ en fråga, spåra vägen mellan två saker, eller förklara ett begrepp.

> [!NOTE]
> **Vill du ha detta alltid aktivt?** [Graphify Cloud](https://app.graphify.com/login) håller grafen levande genom hela din SDLC: stöd för monorepo och korsrepo, formell verifiering och kodgranskning med ett fågelperspektiv över din SDLC, plus kopplingar för Sentry, Jira med mera så att incidenter och ärenden ligger i samma graf som din kod. **[Starta en kostnadsfri 14-dagars provperiod på app.graphify.com](https://app.graphify.com/login)**.

<p align="center">
  <img src="https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/graph-hero.png" alt="graphify's interactive graph.html showing the FastAPI codebase as a force-directed knowledge graph with a legend of detected communities" width="900">
</p>
<p align="center">
  <em>FastAPI-kodbasen kartlagd av graphify. Varje nod är ett begrepp, färger är detekterade gemenskaper och hela saken är klickbar i graph.html.</em>
</p>

**Kom igång** (30 sekunder):

```bash
uv tool install graphifyy      # install the CLI (or: pipx install graphifyy)
graphify install               # register the skill with your AI assistant
```

Sedan, i din AI-assistent:

```
/graphify .
```

Det är allt. Du får **tre filer**:

```
graphify-out/
├── graph.html       open in any browser — click nodes, filter, search
├── GRAPH_REPORT.md  the highlights: key concepts, surprising connections, suggested questions
└── graph.json       the full graph — query it anytime without re-reading your files
```

Den sparade grafen inkluderar `graph.schema_version` så att integrationer kan upptäcka
inkompatibla formatändringar, plus `graph.graphify_version` som identifierar den
Graphify-version som skapade den.

**Fungerar i** Claude Code, Cursor, Codex, Gemini CLI, GitHub Copilot och 15+ till — [välj din plattform](#install).

---

## Dokumentation

Fullständiga guider och referens finns på **[docs.graphify.com](https://docs.graphify.com)**:

- **[Snabbstart](https://docs.graphify.com/quickstart)** — bygg din första graf
- **[CLI-referens](https://docs.graphify.com/reference/overview)** — alla kommandon och flaggor
- **[Ställ bättre graffrågor](https://docs.graphify.com/guides/querying)** — frågemönster
- **[Konfiguration](https://docs.graphify.com/reference/configuration)** — miljövariabler och finjustering
- **[Inmatningar som stöds](https://docs.graphify.com/concepts/supported-inputs)** — språk och filtyper
- **[Teamarbetsflöden](https://docs.graphify.com/guides/team-workflows)** och **[PR-granskning](https://docs.graphify.com/guides/pull-requests)**
- **[Felsökning](https://docs.graphify.com/troubleshooting)** och **[Så fungerar det](https://docs.graphify.com/concepts/architecture)**

---

## Se det i praktiken

<p align="center">
  <img src="https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/demo-path.svg" alt="graphify path query: a terminal asks for the shortest path between FastAPI and ModelField, and the answer lights up hop by hop across the knowledge graph" width="900">
</p>

När grafen är byggd frågar du i den i stället för att läsa filer. Verklig utdata, graphify körd på FastAPI-kodbasen som visas ovan:

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

Varje kant bär en **konfidensmärkning** (`EXTRACTED` = explicit i källan, `INFERRED` = härledd genom resolution), så att du kan skilja det som lästes direkt från det som härleddes. `graphify query "<question>"` returnerar en avgränsad delgraf för en fråga i klarspråk, och `graphify path A B` spårar hur två saker hänger ihop.

---

## Vad den gör

Vad du får direkt ur lådan:

| Funktion | Vad du får |
|---|---|
| **Gudnoder** | De mest sammankopplade begreppen, så att du ser vad allt flödar genom |
| **Gemenskaper** | Grafen uppdelad i delsystem (Leiden), med LLM-fria etiketter |
| **Länkar mellan filer** | `calls` / `imports` / `inherits` / `mixes_in` upplösta över ~40 språk via tree-sitter AST |
| **Query, path, explain** | Ställ en fråga, spåra vägen mellan två saker, eller förklara ett begrepp, allt mot `graph.json` |
| **Motivering + dokumentreferenser** | `# NOTE:` / `# WHY:`-kommentarer och ADR/RFC-citeringar blir förstklassiga noder länkade till koden |
| **Bortom kod** | Dokument, PDF-filer, bilder och video/ljud kartläggs alla in i samma graf |
| **Lokalt först** | Kod parsas lokalt med tree-sitter (ingen LLM, inget lämnar din maskin); endast den semantiska genomgången av dokument/media anropar en backend, och endast om du konfigurerar en |

> [!TIP]
> Kör du detta över många repon eller ett monorepo? [Graphify Cloud](https://app.graphify.com/login) gör det kontinuerligt och minskar agenternas tokenförbrukning med 80%, med korsrepolänkar, kodgranskning över hela SDLC, formell verifiering och kopplingar för Sentry/Jira. [Starta en kostnadsfri 14-dagars provperiod &rarr;](https://app.graphify.com/login)

---

## Benchmarks

| Riktmärke | Mått | graphify | Fältet |
|---|---|---|---|
| LOCOMO (n=300) | recall@10 | **0.497** | mem0 0.048, supermemory 0.149 |
| LOCOMO (n=300) | QA-träffsäkerhet | 45.3% | supermemory 49.7%, mem0 27.3% |
| LongMemEval-S (n=50) | QA-träffsäkerhet | **76%** | likvärdig med tät RAG |
| ERPNext flera verktyg (n=6) | täckning av nyckelfakta | **82.0%** | grep/read-baslinje 70.8% |
| Grafbygge | LLM-krediter | **0** | per token för de flesta system |

Varje system kördes på samma testrigg med samma modell och budgetar, bedömt av en domare blindvaliderad mot en andra domare (90.6% överensstämmelse, Cohens kappa 0.81). Fullständiga tabeller per system, resultatet för kodintelligens och kommandon för reproduktion: **[BENCHMARKS.md](../../BENCHMARKS.md)**.

---

## Förutsättningar

| Krav | Minimum | Kontrollera | Installera |
|---|---|---|---|
| Python | 3.10+ | `python --version` | [python.org](https://www.python.org/downloads/) |
| uv *(rekommenderas)* | valfri | `uv --version` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| pipx *(alternativ)* | valfri | `pipx --version` | `pip install pipx` |

**Snabbinstallation på macOS (Homebrew):**
```bash
brew install python@3.12 uv
```

**Snabbinstallation på Windows:**
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
> **Officiellt paket:** PyPI-paketet är `graphifyy` (dubbel-y). Andra `graphify*`-paket på PyPI är inte anslutna. CLI-kommandot är fortfarande `graphify`.

Det officiella källkodsförrådet är [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify).

**Steg 1 — installera paketet:**

```bash
# Recommended (isolated env; if 'graphify' isn't found after, run: uv tool update-shell):
uv tool install graphifyy

# Alternatives:
pipx install graphifyy
pip install graphifyy  # may need PATH setup — see note below
```

**Steg 2 — registrera färdigheten hos din AI-assistent:**

```bash
graphify install
```

Det är allt. Öppna din AI-assistent och skriv `/graphify .`

För att installera assistentfärdigheten i det aktuella förrådet i stället för din
användarprofil, lägg till `--project`:

```bash
graphify install --project
graphify install --project --platform codex
```

Projektavgränsade installationer skrivs under den aktuella katalogen, till exempel
`.claude/skills/graphify/SKILL.md` eller `.agents/skills/graphify/SKILL.md` (plus en
`references/`-sidofil som färdigheten laddar vid behov), och
skriver ut en `git add`-ledtråd för filer som kan checkas in.
Kommandon per plattform som stöder projektavgränsade installationer accepterar samma flagga,
till exempel `graphify claude install --project` eller `graphify codex install --project`.

> [!TIP]
> Stöter du på `command not found`, ett `pip`-problem på Mac/Windows, PowerShell-citering, `uvx`-användning, PATH-egenheter med git-hooks eller strikt läge? Se **[Installation](https://docs.graphify.com/installation)** och **[Felsökning](https://docs.graphify.com/troubleshooting)**.

<details>
<summary><b>Välj din plattform</b> (20+ assistenter, klicka för att expandera)</summary>

| Plattform | Installationskommando |
|----------|----------------|
| Claude Code (Linux/Mac) | `graphify install` |
| Claude Code (Windows) | `graphify install` (upptäcks automatiskt) eller `graphify install --platform windows` |
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
| Agent Skills (korsramverk) | `graphify install --platform agents` (alias `--platform skills`) |
| Kiro IDE/CLI | `graphify kiro install` |
| Pi coding agent | `graphify install --platform pi` |
| Cursor | `graphify cursor install` |
| Devin CLI | `graphify devin install` |
| Google Antigravity | `graphify antigravity install` |

Codex-användare behöver även `multi_agent = true` under `[features]` i `~/.codex/config.toml` för parallell extraktion. CodeBuddy använder samma Agent-verktyg och PreToolUse-hookmekanism som Claude Code. Factory Droid använder `Task`-verktyget för parallell utskickning av subagenter. OpenClaw och Aider använder sekventiell extraktion (stöd för parallella agenter är fortfarande tidigt på dessa plattformar). Trae använder Agent-verktyget för parallell utskickning av subagenter och stöder **inte** `PreToolUse`-hooks, så AGENTS.md är den alltid aktiva mekanismen.

`--platform agents` (alias `--platform skills`) riktar in sig på de generiska korsramverksplatserna för [Agent-Skills](https://github.com/anthropics/skills): specifikationens användarglobala `~/.agents/skills/` (läses av `npx skills` och specifikationsenliga ramverk) för en global installation, och `./.agents/skills/` för en projektinstallation (`--project`). Det blotta `graphify install` förblir enplattform (Claude Code) avsiktligt — använd den namngivna `agents`-plattformen när du vill att färdigheten ska kunna upptäckas av vilket ramverk som helst som läser `.agents/skills`.

> Codex använder `$graphify` i stället för `/graphify`.

</details>

<details>
<summary><b>Valfria tillägg</b> (installera bara det du behöver)</summary>

| Tillägg | Vad det lägger till | Installera |
|---|---|---|
| `pdf` | PDF-extraktion | `uv tool install "graphifyy[pdf]"` |
| `office` | Stöd för `.docx` och `.xlsx` | `uv tool install "graphifyy[office]"` |
| `google` | Rendering av Google Sheets | `uv tool install "graphifyy[google]"` |
| `video` | Transkribering av video/ljud (faster-whisper + yt-dlp) | `uv tool install "graphifyy[video]"` |
| `mcp` | MCP stdio-server | `uv tool install "graphifyy[mcp]"` |
| `neo4j` | Stöd för push till Neo4j | `uv tool install "graphifyy[neo4j]"` |
| `falkordb` | Stöd för push till FalkorDB | `uv tool install "graphifyy[falkordb]"` |
| `svg` | SVG-grafexport | `uv tool install "graphifyy[svg]"` |
| `leiden` | Leiden-gemenskapsdetektering (graspologic på Python < 3.13; inbyggd backend på 3.13+) | `uv tool install "graphifyy[leiden]"` |
| `ollama` | Lokal inferens med Ollama | `uv tool install "graphifyy[ollama]"` |
| `openai` | OpenAI / OpenAI-kompatibla API:er | `uv tool install "graphifyy[openai]"` |
| `gemini` | Google Gemini API | `uv tool install "graphifyy[gemini]"` |
| `anthropic` | Anthropic Claude API (`--backend claude`, använder `ANTHROPIC_API_KEY`) | `uv tool install "graphifyy[anthropic]"` |
| `bedrock` | AWS Bedrock (använder IAM, ingen API-nyckel) | `uv tool install "graphifyy[bedrock]"` |
| `azure` | Azure OpenAI Service (`--backend azure`, använder `AZURE_OPENAI_API_KEY` + `AZURE_OPENAI_ENDPOINT`) | `uv tool install "graphifyy[openai]"` |
| `sql` | Extraktion av SQL-schema | `uv tool install "graphifyy[sql]"` |
| `postgres` | Live-introspektion av PostgreSQL (`--postgres DSN`) | `uv tool install "graphifyy[postgres]"` |
| `dm` | BYOND DreamMaker `.dm`/`.dme` AST-extraktion (kan behöva en C-kompilator + `python3-dev` om inget wheel matchar din plattform) | `uv tool install "graphifyy[dm]"` |
| `terraform` | Terraform / HCL `.tf`/`.tfvars`/`.hcl` AST-extraktion | `uv tool install "graphifyy[terraform]"` |
| `pascal` | Pascal / Delphi `.pas`/`.dpr`/`.dpk`/`.inc` AST-extraktion (mer exakta `calls`/`inherits`-kanter; faller tillbaka på en regex-extraktor när den saknas) | `uv tool install "graphifyy[pascal]"` |
| `ocaml` | OCaml `.ml`/`.mli` AST-extraktion | `uv tool install "graphifyy[ocaml]"` |
| `commonlisp` | Common Lisp `.lisp`/`.cl`/`.lsp`/`.asd` AST-extraktion | `uv tool install "graphifyy[commonlisp]"` |
| `robot` | Robot Framework `.robot`/`.resource`-extraktion (sviter, testfall, nyckelord, kanter för nyckelordsanrop och resurs-/biblioteksimport) | `uv tool install "graphifyy[robot]"` |
| `chinese` | Kinesisk frågesegmentering (jieba) | `uv tool install "graphifyy[chinese]"` |
| `all` | Allt ovanstående | `uv tool install "graphifyy[all]"` |

</details>

---

## Få din assistent att alltid använda grafen

Kör detta en gång i ditt projekt efter att du har byggt en graf:

Kör `graphify <platform> install` en gång i ditt projekt, till exempel `graphify claude install` eller `graphify codex install` (eller `graphify install --platform <name>`).

Detta skriver en liten konfigurationsfil som säger åt din assistent att konsultera kunskapsgrafen för frågor om kodbasen, och föredra avgränsade frågor som `graphify query "<question>"` framför att läsa hela rapporten eller greppa råa filer.

- **Hook-plattformar** (Claude Code, Gemini CLI): en hook utlöses automatiskt före sökliknande verktygsanrop (och, på Claude Code, innan källfiler läses en och en via Read/Glob-verktygen) och styr din assistent mot grafvägen.
- **Instruktionsfilsplattformar** (Codex, OpenCode, Cursor, m.fl.): beständiga instruktionsfiler (`AGENTS.md`, `.cursor/rules/`, m.m.) ger samma frågan-först-vägledning.

`GRAPH_REPORT.md` är fortfarande tillgänglig för bred arkitekturgranskning.

**CodeBuddy** gör samma två saker som Claude Code: skriver en `CODEBUDDY.md`-sektion som säger åt CodeBuddy att läsa `graphify-out/GRAPH_REPORT.md` innan den besvarar arkitekturfrågor, och installerar `PreToolUse`-hooks (`.codebuddy/settings.json`) som utlöses före Bash-sökkommandon och filläsningar och styr mot `graphify query` i stället.

**Codex** skriver till `AGENTS.md`, vilket är det som faktiskt bär den alltid aktiva grafvägledningen på denna plattform. `graphify codex install` registrerar även en `PreToolUse`-hook i `.codex/hooks.json` (`graphify hook-check`), men den posten är avsiktligt en **no-op**: Codex Desktop avvisar `hookSpecificOutput.additionalContext` på `PreToolUse`, så att sända en styrning där skulle bryta Bash-verktygsanrop. Till skillnad från Claude Code, där hooken (`graphify hook-guard`) utför styrningen, utlöses hooken på Codex och gör avsiktligt ingenting, och `AGENTS.md` är den alltid aktiva mekanismen.

**Kilo Code** installerar Graphify-färdigheten till `~/.config/kilo/skills/graphify/SKILL.md` och ett inbyggt `/graphify`-kommando till `~/.config/kilo/command/graphify.md`. `graphify kilo install` skriver även `AGENTS.md` plus ett inbyggt `tool.execute.before`-plugin (`.kilo/plugins/graphify.js` + registrering i `.kilo/kilo.json` eller `.kilo/kilo.jsonc`) så att Kilo får samma alltid aktiva grafpåminnelsebeteende genom inbyggd `.kilo`-konfiguration.

**Cursor** skriver `.cursor/rules/graphify.mdc` med `alwaysApply: true`, så att Cursor inkluderar den i varje konversation automatiskt, ingen hook behövs.

För att ta bort graphify från alla plattformar på en gång: `graphify uninstall` (lägg till `--purge` för att även radera `graphify-out/`). Eller använd kommandot per plattform (t.ex. `graphify claude uninstall`).

---

## Vad som finns i rapporten

`GRAPH_REPORT.md` sammanfattar gudnoderna, gemenskaperna och viktiga vägar för bred arkitekturgranskning. Hur grafen byggs och vad den innehåller: **[Så fungerar graphify](https://docs.graphify.com/concepts/architecture)**.

---

## Vilka filer den hanterar

graphify parsar ~40 programmeringsspråk lokalt med tree-sitter AST, och kartlägger dokument, PDF-filer, bilder och ljud/video genom en valfri semantisk genomgång. Fullständig lista: **[Inmatningar som stöds](https://docs.graphify.com/concepts/supported-inputs)**.

---

## Vanliga kommandon

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

Se den [fullständiga kommandoreferensen](#full-command-reference) nedan.

---

## Ignorera filer

graphify respekterar `.gitignore` och stöder `--exclude`-mönster och en projekt-`.graphifyignore`. Detaljer: **[Konfiguration](https://docs.graphify.com/reference/configuration)**.

---

## Teaminställning

Checka in eller dela grafen så att hela ditt team frågar mot samma kontext, och granska pull requests med grafkontext. Se **[Dela kontext med ditt team](https://docs.graphify.com/guides/team-workflows)** och **[Granska pull requests](https://docs.graphify.com/guides/pull-requests)**.

---

## Använda grafen direkt

Utöver din AI-assistent kan du fråga `graph.json` direkt från CLI med `graphify query`, `graphify path` och `graphify explain`. Se **[Ställ bättre graffrågor](https://docs.graphify.com/guides/querying)** och **[frågereferensen](https://docs.graphify.com/reference/query)**.

---

## Miljövariabler

Backends, API-nycklar, hook-beteende och finjustering styrs av miljövariabler. Fullständig tabell: **[Konfiguration](https://docs.graphify.com/reference/configuration)**.

---

## Integritet

- **Kodfiler** — bearbetas lokalt via tree-sitter. Inget lämnar din maskin. Ett korpus med enbart kod kräver ingen API-nyckel — `graphify extract` körs helt offline. I ett blandat förråd, lägg till `--code-only` för att indexera endast koden och hoppa över dokument/PDF-filer/bilder som annars skulle behöva en LLM.
- **Video / ljud** — transkriberas lokalt med faster-whisper. Inget lämnar din maskin.
- **Dokument, PDF-filer, bilder** — skickas till din AI-assistent för semantisk extraktion (via `/graphify`-färdigheten, med den modell din IDE-session kör). Huvudlös `graphify extract` kräver `GEMINI_API_KEY` / `GOOGLE_API_KEY` (Gemini), `MOONSHOT_API_KEY` (Kimi), `ANTHROPIC_API_KEY` (Claude), `OPENAI_API_KEY` (OpenAI), `DEEPSEEK_API_KEY` (DeepSeek), en körande Ollama-instans (`OLLAMA_BASE_URL`), AWS-autentiseringsuppgifter via den standardmässiga leverantörskedjan (Bedrock – ingen API-nyckel behövs, använder IAM), eller `claude`-CLI-binären (Claude Code – ingen API-nyckel behövs, använder din Claude-prenumeration). Flaggan `--dedup-llm` använder samma nyckel.
- **Datahemvist** — `graphify extract` upptäcker automatiskt vilken leverantör som ska användas baserat på vilken API-nyckel som är satt (prioritet: Gemini → Kimi → Claude → OpenAI → DeepSeek → Azure → Bedrock → Ollama). För kod med krav på datahemvist, använd `--backend ollama` (helt lokal) eller ange en uttrycklig `--backend`-flagga. Kimi (`MOONSHOT_API_KEY`) dirigeras till Moonshot AI-servrar i Kina.
- **Ingen telemetri**, ingen användningsspårning, ingen analys.
- **Frågeloggning** — varje anrop av `graphify query`, `graphify path`, `graphify explain` och MCP `query_graph` loggas till `~/.cache/graphify-queries.log` i JSON Lines-format (tidsstämpel, fråga, korpus, returnerade noder, varaktighet). Fullständiga delgrafssvar lagras **inte** som standard. Sätt `GRAPHIFY_QUERY_LOG_DISABLE=1` för att välja bort, eller `GRAPHIFY_QUERY_LOG=/dev/null` för att tysta utan att inaktivera kodvägen.

---

## Felsökning

Vanliga installations- och extraktionsproblem och deras lösningar: **[Felsökning](https://docs.graphify.com/troubleshooting)**.

---

## Fullständig kommandoreferens

Alla kommandon och flaggor, med exempel: **[CLI-referens](https://docs.graphify.com/reference/overview)**.

---

## Läs mer

- [docs.graphify.com](https://docs.graphify.com) — fullständig dokumentation: guider, kommandoreferens och integrationer
- [Så fungerar det](../how-it-works.md) — extraktionspipelinen, gemenskapsdetektering, konfidenspoängsättning, benchmarks
- [ARCHITECTURE.md](../../ARCHITECTURE.md) — modulöversikt, hur man lägger till ett språk
- [Valfria integrationer](../docker-mcp-sqlite.md) — Docker MCP Toolkit + SQLite
- [The Memory Layer](https://safishamsi.gumroad.com/l/qetvlo) — boken om idéerna bakom graphify, arkitekturen från början till slut

---

## Graphify Cloud

[**Graphify Cloud**](https://app.graphify.com/login) är det alltid aktiva lagret byggt ovanpå graphify. I stället för en graf som du bygger om på begäran per mapp, håller det en levande graf genom hela din livscykel för programvaruutveckling:

- **80% färre tokens** — alltid aktivt minne innebär att dina agenter slutar läsa om och förklara om kodbasen varje session.
- **Monorepo och korsrepo** — en sammankopplad graf över varje tjänst och förråd, inte en graf per mapp.
- **Formell verifiering** — kontrollera arkitektur- och beroendeinvarianter mot den levande grafen.
- **Kodgranskning med fågelperspektiv över din SDLC** — se hur en ändring sprider sig genom hela systemet innan du slår ihop.
- **SDLC-kopplingar** — hämta in Sentry, Jira med mera, så att incidenter, ärenden och kod lever i en graf.
- **Alltid aktiv** — uppdateras kontinuerligt i bakgrunden över kod, dokument och möten.

**[Starta en kostnadsfri 14-dagars provperiod på app.graphify.com &rarr;](https://app.graphify.com/login)**

---

## Bidra

Bidrag är välkomna. Se **[CONTRIBUTING.md](../../CONTRIBUTING.md)** för utvecklingsmiljön, kommandona för test och CI-paritet, git-arbetsflödet och vad som gör ett starkt bidrag (utarbetade exempel och felrapporter om extraktion är mest användbara). Arkitektur och hur man lägger till ett språk: [ARCHITECTURE.md](../../ARCHITECTURE.md).

Ny här? Säg hej på [Discord](https://discord.gg/XDnKVpzdXB) eller i [GitHub Discussions](https://github.com/Graphify-Labs/graphify/discussions).

---

## Bidragsgivare

<a href="https://github.com/Graphify-Labs/graphify/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=Graphify-Labs/graphify" alt="graphify contributors" />
</a>

Skapad med [contrib.rocks](https://contrib.rocks).

---

## Översättningar

README finns på 32 språk. Använd språkväljaren högst upp i den här filen för att läsa den på ditt, eller bläddra i [`docs/translations/`](./). För att förbättra en översättning eller lägga till en ny, öppna en pull request mot motsvarande fil där.

---

## Bygga på graphify

Bygger du något i graphify-ekosystemet? Det uppmuntras. Om ditt projekt använder "graphify" i sitt namn (till exempel `graphify-dashboard` eller `graphify-action`), lägg gärna till en kort notis i din README som förtydligar att det är community-byggt och inte anslutet till eller godkänt av Graphify Labs. "graphify" och graphify-logotypen är varumärken som tillhör Graphify Labs; använd dem inte på ett sätt som antyder officiell status.

---

## Community och länkar

<p align="center">
  <a href="https://graphify.com"><img src="https://img.shields.io/badge/Website-graphify.com-4c1?style=flat&logo=googlechrome&logoColor=white" alt="Website"/></a>
  <a href="https://discord.gg/XDnKVpzdXB"><img src="https://img.shields.io/badge/Discord-Join-5865F2?style=flat&logo=discord&logoColor=white" alt="Discord"/></a>
  <a href="https://x.com/graphify"><img src="https://img.shields.io/badge/X-graphify-000000?logo=x&logoColor=white" alt="X"/></a>
  <a href="https://www.youtube.com/@graphifylabs"><img src="https://img.shields.io/badge/YouTube-Graphify%20Labs-FF0000?style=flat&logo=youtube&logoColor=white" alt="YouTube"/></a>
  <a href="https://github.com/sponsors/safishamsi"><img src="https://img.shields.io/badge/sponsor-safishamsi-ea4aaa?logo=github-sponsors" alt="Sponsor"/></a>
  <a href="https://safishamsi.gumroad.com/l/qetvlo"><img src="https://img.shields.io/badge/Book-The%20Memory%20Layer-2ea44f?style=flat&logo=gitbook&logoColor=white" alt="The Memory Layer"/></a>
</p>
