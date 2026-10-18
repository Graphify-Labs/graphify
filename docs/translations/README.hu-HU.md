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
  <a href="https://discord.gg/XDnKVpzdXB"><img src="https://img.shields.io/badge/Discord-Join-5865F2?style=flat&logo=discord&logoColor=white" alt="Discord"/></a>
  <a href="https://www.youtube.com/@graphifylabs"><img src="https://img.shields.io/badge/YouTube-Graphify%20Labs-FF0000?style=flat&logo=youtube&logoColor=white" alt="YouTube"/></a>
  <a href="https://www.linkedin.com/company/graphify-labs"><img src="https://img.shields.io/badge/LinkedIn-Graphify%20Labs-0077B5?logo=linkedin" alt="LinkedIn"/></a>
  <a href="https://www.ycombinator.com/companies/graphify-labs"><img src="https://img.shields.io/badge/Y%20Combinator-S26-F0652F?style=flat&logo=ycombinator&logoColor=white" alt="YC S26"/></a>
</p>

<p align="center">
  <b>Csökkentse az ügynökök tokenköltségét 80%-kal.</b> A Graphify Cloud mindig aktív memória, amely irányítja az ügynökeit, magasan tartja a kódminőséget, és formális verifikációval bizonyítja a helyességet. <a href="https://app.graphify.com/login"><b>Indítson ingyenes 14 napos próbaidőszakot &rarr;</b></a>
</p>

Írja be a `/graphify` parancsot az AI-kódolási asszisztensébe, és az a teljes projektjét (kód, dokumentumok, PDF-ek, képek, videók) **tudásgráffá** alakítja, amelyet **lekérdezhet ahelyett, hogy grep-pel** keresgélne a fájlok között.

- **A kód feltérképezése ingyenes, teljesen lokális.** A kódot a tree-sitter AST elemzi: determinisztikus, nincs LLM, semmi sem hagyja el a gépét. (A dokumentumok, PDF-ek, képek és videók az asszisztense modelljét vagy egy beállított API-kulcsot használnak egy szemantikai futtatáshoz.)
- **Minden él magyarázattal rendelkezik.** Minden kapcsolat `EXTRACTED` (a forrásban explicit) vagy `INFERRED` (a graphify által feloldott) címkét kap, így meg tudja különböztetni a közvetlenül kiolvasott dolgokat a kikövetkeztetettektől.
- **Nem vektorindex.** Nincsenek beágyazások, nincs vektortár: egy valódi gráf, amelyet bejár. Tegyen fel egy kérdést, kövesse nyomon a két dolog közötti utat, vagy magyaráztasson el egy fogalmat.

> [!NOTE]
> **Szeretné ezt mindig aktívan?** A [Graphify Cloud](https://app.graphify.com/login) a teljes SDLC-jén át élőben tartja a gráfot: monorepo- és repository-közi támogatás, formális verifikáció, valamint kódellenőrzés madártávlatból az SDLC-jéről, továbbá konnektorok a Sentryhez, Jirához és másokhoz, hogy az incidensek és jegyek ugyanabban a gráfban legyenek, mint a kódja. **[Indítson ingyenes 14 napos próbaidőszakot az app.graphify.com oldalon](https://app.graphify.com/login)**.

<p align="center">
  <img src="https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/graph-hero.png" alt="graphify's interactive graph.html showing the FastAPI codebase as a force-directed knowledge graph with a legend of detected communities" width="900">
</p>
<p align="center">
  <em>A graphify által feltérképezett FastAPI-kódbázis. Minden csomópont egy fogalom, a színek az észlelt közösségek, és az egész kattintható a graph.html fájlban.</em>
</p>

**Kezdés** (30 másodperc). Python 3.10+ és uv (vagy pipx) szükséges:

```bash
uv tool install graphifyy      # install the CLI (or: pipx install graphifyy)
graphify install               # detects your assistant and registers the skill
```

Majd az AI-asszisztensében:

```
/graphify .
```

Ennyi az egész. **Három fájlt** kap:

```
graphify-out/
├── graph.html       open in any browser: click nodes, filter, search
├── GRAPH_REPORT.md  the highlights: key concepts, surprising connections, suggested questions
└── graph.json       the full graph: query it anytime without re-reading your files
```

A megőrzött gráf tartalmazza a `graph.schema_version` mezőt, hogy az integrációk
észlelhessék a nem kompatibilis formátumváltozásokat, valamint a `graph.graphify_version`
mezőt, amely azonosítja az azt előállító Graphify-kiadást.

**Egy telepítés, bármely asszisztens, bármely operációs rendszer.** Claude Code, Cursor, Codex, Gemini CLI, GitHub Copilot és több mint 20 további, macOS, Linux és Windows rendszeren: [válassza ki a platformját](#install).

---

## See it in action

<p align="center">
  <img src="https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/demo-path.svg" alt="graphify path query: a terminal asks for the shortest path between FastAPI and ModelField, and the answer lights up hop by hop across the knowledge graph" width="900">
</p>

Miután a gráf elkészült, azt lekérdezi ahelyett, hogy fájlokat olvasna. Valódi kimenet, a graphify a fent látható FastAPI-kódbázison futtatva:

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

Minden él **megbízhatósági címkét** hordoz (`EXTRACTED` = a forrásban explicit, `INFERRED` = feloldással származtatott), így meg tudja különböztetni a közvetlenül kiolvasott dolgokat a kikövetkeztetettektől. A `graphify query "<question>"` egy természetes nyelvű kérdéshez tartozó szűkített részgráfot ad vissza, a `graphify path A B` pedig nyomon követi, hogyan kapcsolódik össze bármely két dolog.

---

## What it does

Amit alapból kap:

| Képesség | Amit kap |
|---|---|
| **God nodes** | A legtöbb kapcsolattal rendelkező fogalmak, így látja, hogy min folyik keresztül minden |
| **Communities** | A gráf alrendszerekre bontva (Leiden), LLM-mentes címkékkel |
| **Fájlközi hivatkozások** | `calls` / `imports` / `inherits` / `mixes_in` feloldva ~40 nyelven át a tree-sitter AST segítségével |
| **Query, path, explain** | Tegyen fel egy kérdést, kövesse nyomon a két dolog közötti utat, vagy magyaráztasson el egy fogalmat, mindezt a `graph.json` ellenében |
| **Indoklás + dokumentumhivatkozások** | A `# NOTE:` / `# WHY:` megjegyzések és az ADR/RFC-hivatkozások elsőrangú csomópontokká válnak, amelyek a kódhoz kapcsolódnak |
| **A kódon túl** | A dokumentumok, PDF-ek, képek és videó/hang mind ugyanabba a gráfba képeződnek le |
| **Local-first** | A kódot lokálisan elemzi a tree-sitter (nincs LLM, semmi sem hagyja el a gépét); csak a dokumentumokon/médián végzett szemantikai futtatás hív meg egy backendet, és csak akkor, ha beállít egyet |

> [!TIP]
> Sok repón vagy egy monorepón át futtatja ezt? A [Graphify Cloud](https://app.graphify.com/login) folyamatosan végzi, és 80%-kal csökkenti az ügynökök tokenköltségét, repository-közi hivatkozásokkal, SDLC-szintű kódellenőrzéssel, formális verifikációval és Sentry/Jira konnektorokkal. [Indítson ingyenes 14 napos próbaidőszakot &rarr;](https://app.graphify.com/login)

---

## Benchmarks: 0.497 recall@10, 0 LLM credits

| Benchmark | Metrika | graphify | Mező |
|---|---|---|---|
| LOCOMO (n=300) | recall@10 | **0.497** | mem0 0.048, supermemory 0.149 |
| LOCOMO (n=300) | QA accuracy | 45.3% | supermemory 49.7%, mem0 27.3% |
| LongMemEval-S (n=50) | QA accuracy | **76%** | holtverseny a dense RAG-gal |
| ERPNext cross-tool (n=6) | key-fact coverage | **82.0%** | grep/read baseline 70.8% |
| Graph build | LLM credits | **0** | a legtöbb rendszernél tokenenként |

Minden rendszer ugyanazon a harness-en futott, ugyanazzal a modellel és költségkeretekkel, egy olyan bíró által pontozva, amelyet egy második bíróval szemben vakon validáltak (90.6% egyezés, Cohen-féle kappa 0.81). Teljes rendszerenkénti táblázatok, a kód-intelligencia eredmény és a reprodukciós parancsok: **[BENCHMARKS.md](../../BENCHMARKS.md)**.

---

## Documentation

A teljes útmutatók és a referencia itt található: **[docs.graphify.com](https://docs.graphify.com)**:

- **[Quickstart](https://docs.graphify.com/quickstart)**: építse fel az első gráfját
- **[CLI reference](https://docs.graphify.com/reference/overview)**: minden parancs és flag
- **[Ask better graph questions](https://docs.graphify.com/guides/querying)**: lekérdezési minták
- **[Configuration](https://docs.graphify.com/reference/configuration)**: környezeti változók és finomhangolás
- **[Supported inputs](https://docs.graphify.com/concepts/supported-inputs)**: nyelvek és fájltípusok
- **[Team workflows](https://docs.graphify.com/guides/team-workflows)** és **[PR review](https://docs.graphify.com/guides/pull-requests)**
- **[Troubleshooting](https://docs.graphify.com/troubleshooting)** és **[How it works](https://docs.graphify.com/concepts/architecture)**

---

## Prerequisites

| Követelmény | Minimum | Ellenőrzés | Telepítés |
|---|---|---|---|
| Python | 3.10+ | `python --version` | [python.org](https://www.python.org/downloads/) |
| uv *(ajánlott)* | bármely | `uv --version` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| pipx *(alternatíva)* | bármely | `pipx --version` | `pip install pipx` |

**macOS gyors telepítés (Homebrew):**
```bash
brew install python@3.12 uv
```

**Windows gyors telepítés:**
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
> **Hivatalos csomag:** A PyPI-csomag a `graphifyy` (dupla y). A PyPI egyéb `graphify*` csomagjai nem kapcsolódnak hozzá. A CLI-parancs továbbra is `graphify`.

A hivatalos forrás-repository a [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify).

A kétparancsos gyorsindító e README tetején található. Ez a szakasz a telepítési módszereket, a projekt-hatókörű telepítéseket és minden támogatott platformot ismertet.

**Telepítési módszerek** (válasszon egyet):

```bash
uv tool install graphifyy   # recommended, isolated env (if 'graphify' isn't found after, run: uv tool update-shell)
pipx install graphifyy      # alternative
pip install graphifyy       # may need PATH setup, see Troubleshooting below
```

Majd futtassa egyszer a `graphify install` parancsot. Felismeri, melyik asszisztenst használja, és regisztrálja a skillt, így nincs asszisztensenkénti beállítás. Nyissa meg az AI-asszisztensét, és írja be: `/graphify .`

Ha az asszisztens-skillt a felhasználói profilja helyett az aktuális
repository-ba szeretné telepíteni, adja hozzá a `--project` kapcsolót:

```bash
graphify install --project
graphify install --project --platform codex
```

A projekt-hatókörű telepítések az aktuális könyvtárba írnak, például
`.claude/skills/graphify/SKILL.md` vagy `.agents/skills/graphify/SKILL.md` (plusz egy
`references/` kiegészítő, amelyet a skill igény szerint tölt be), és
`git add` tippet írnak ki a commitolható fájlokhoz.
A projekt-hatókörű telepítéseket támogató platformspecifikus parancsok ugyanazt a kapcsolót fogadják el,
például `graphify claude install --project` vagy `graphify codex install --project`.

> [!TIP]
> `command not found` hibába, egy Mac/Windows-on jelentkező `pip`-problémába, PowerShell-idézőjelezésbe, `uvx`-használatba, git-hook PATH-furcsaságokba vagy strict módba ütközik? Lásd: **[Installation](https://docs.graphify.com/installation)** és **[Troubleshooting](https://docs.graphify.com/troubleshooting)**.

<details>
<summary><b>Pick your platform</b> (20+ assistants, click to expand)</summary>

| Platform | Telepítési parancs |
|----------|----------------|
| Claude Code (Linux/Mac) | `graphify install` |
| Claude Code (Windows) | `graphify install` (automatikusan felismerve) vagy `graphify install --platform windows` |
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
| Agent Skills (keretrendszer-független) | `graphify install --platform agents` (alias `--platform skills`) |
| Kiro IDE/CLI | `graphify kiro install` |
| Pi coding agent | `graphify install --platform pi`, plusz `graphify pi guard install` a natív guardhoz |
| Cursor | `graphify cursor install` |
| Devin CLI | `graphify devin install` |
| Google Antigravity | `graphify antigravity install` |

A Codex-felhasználóknak a párhuzamos kinyeréshez `multi_agent = true` is szükséges a `~/.codex/config.toml` fájl `[features]` szakaszában. A CodeBuddy ugyanazt az Agent eszközt és PreToolUse hook mechanizmust használja, mint a Claude Code. A Factory Droid a `Task` eszközt használja a párhuzamos szubügynök-küldéshez. Az OpenClaw és az Aider szekvenciális kinyerést használ (a párhuzamos ügynöktámogatás ezeken a platformokon még korai stádiumban van). A Trae az Agent eszközt használja a párhuzamos szubügynök-küldéshez, és **nem** támogatja a `PreToolUse` hookokat, ezért az AGENTS.md a mindig aktív mechanizmus.

A `--platform agents` (alias `--platform skills`) az általános, keretrendszer-független [Agent-Skills](https://github.com/anthropics/skills) helyeket célozza: a specifikáció felhasználó-globális `~/.agents/skills/` helyét (amelyet az `npx skills` és a specifikációnak megfelelő keretrendszerek olvasnak) a globális telepítéshez, és a `./.agents/skills/` helyet a projekt- (`--project`) telepítéshez. A puszta `graphify install` szándékosan egyplatformos marad (Claude Code): használja a megnevezett `agents` platformot, ha azt szeretné, hogy a skillt bármely keretrendszer felfedezze, amely a `.agents/skills` helyet olvassa.

Pinek nincs `PreToolUse` hookja, ezért a `graphify pi guard install` egy natív Pi-bővítményt regisztrál (a Pi saját `pi install <package directory>` parancsán keresztül), amely a telepített `graphify hook-guard`-ot futtatja a Pi `read`, `grep`, `find` és keresés jellegű `bash` hívásai előtt. A friss/elavult gráfdöntések és a `GRAPHIFY_HOOK_STRICT=1` munkamenetenként egyszeri indexelt-olvasás elutasítása ugyanabból a házirendből származik, így a Pi megfelel a Claude Code hook-viselkedésének; az útmutatás egy `<system-reminder source="graphify">` irányító üzenetként érkezik. Pi 0.58.4 vagy újabb szükséges hozzá: a korábbi verziók megengedték, hogy egy irányító üzenet kihagyja egy párhuzamos eszközhívás-köteg hátralévő részét. A csomag a Graphify-telepítésen belül érkezik, ezért telepítse a Graphify-t tartósan (`uv tool install graphifyy` vagy `pipx install graphifyy`, nem `uvx`), indítsa újra a Pit telepítés vagy frissítés után, és távolítsa el a `graphify pi guard uninstall` paranccsal. Csak a lokális fájlcélokat vizsgálja; a hooknak a `graphify`-ra van szüksége egy abszolút, projekten kívüli `PATH`-bejegyzésben, két másodpercre és 256 KiB bemenetre/64 KiB kimenetre korlátozott hívás, és hiba esetén nyitva marad (fail open). Ugyanez a csomag betöltődik az [Oh My Pi](https://github.com/can1357/oh-my-pi) rendszerben is: `omp plugin install "$(graphify pi guard path)"`. A regisztrált útvonal tartalmazza a Python verzióját és a venv-et, ezért futtassa újra a `graphify pi guard install` parancsot bármelyik megváltoztatása után, és távolítsa el a régi bejegyzést a `pi remove <old path>` paranccsal.

> A Codex a `$graphify` parancsot használja a `/graphify` helyett.

</details>

<details>
<summary><b>Optional extras</b> (install only what you need)</summary>

| Extra | Mit ad hozzá | Telepítés |
|---|---|---|
| `pdf` | PDF-kinyerés | `uv tool install "graphifyy[pdf]"` |
| `office` | `.docx` és `.xlsx` támogatás | `uv tool install "graphifyy[office]"` |
| `google` | Google Sheets megjelenítés | `uv tool install "graphifyy[google]"` |
| `video` | Videó-/hangátirat (faster-whisper + yt-dlp) | `uv tool install "graphifyy[video]"` |
| `mcp` | MCP stdio-kiszolgáló | `uv tool install "graphifyy[mcp]"` |
| `neo4j` | Neo4j push-támogatás | `uv tool install "graphifyy[neo4j]"` |
| `falkordb` | FalkorDB push-támogatás | `uv tool install "graphifyy[falkordb]"` |
| `svg` | SVG-gráfexport | `uv tool install "graphifyy[svg]"` |
| `leiden` | Leiden közösségészlelés (graspologic Python < 3.13 esetén; natív backend 3.13+ esetén) | `uv tool install "graphifyy[leiden]"` |
| `ollama` | Ollama helyi inferencia | `uv tool install "graphifyy[ollama]"` |
| `openai` | OpenAI / OpenAI-kompatibilis API-k | `uv tool install "graphifyy[openai]"` |
| `gemini` | Google Gemini API | `uv tool install "graphifyy[gemini]"` |
| `anthropic` | Anthropic Claude API (`--backend claude`, az `ANTHROPIC_API_KEY`-t használja) | `uv tool install "graphifyy[anthropic]"` |
| `bedrock` | AWS Bedrock (IAM-et használ, nincs API-kulcs) | `uv tool install "graphifyy[bedrock]"` |
| `azure` | Azure OpenAI Service (`--backend azure`, az `AZURE_OPENAI_API_KEY` + `AZURE_OPENAI_ENDPOINT` értékeket használja) | `uv tool install "graphifyy[openai]"` |
| `sql` | SQL-sémakinyerés | `uv tool install "graphifyy[sql]"` |
| `postgres` | Élő PostgreSQL-introspekció (`--postgres DSN`) | `uv tool install "graphifyy[postgres]"` |
| `dm` | BYOND DreamMaker `.dm`/`.dme` AST-kinyerés (szükség lehet C-fordítóra + `python3-dev`-re, ha egyetlen wheel sem illik a platformjához) | `uv tool install "graphifyy[dm]"` |
| `terraform` | Terraform / HCL `.tf`/`.tfvars`/`.hcl` AST-kinyerés | `uv tool install "graphifyy[terraform]"` |
| `pascal` | Pascal / Delphi `.pas`/`.dpr`/`.dpk`/`.inc` AST-kinyerés (pontosabb `calls`/`inherits` élek; hiányában egy regex-alapú kinyerőre vált) | `uv tool install "graphifyy[pascal]"` |
| `ocaml` | OCaml `.ml`/`.mli` AST-kinyerés | `uv tool install "graphifyy[ocaml]"` |
| `commonlisp` | Common Lisp `.lisp`/`.cl`/`.lsp`/`.asd` AST-kinyerés | `uv tool install "graphifyy[commonlisp]"` |
| `robot` | Robot Framework `.robot`/`.resource` kinyerés (suite-ok, tesztesetek, kulcsszavak, kulcsszóhívási és resource-/library-import élek) | `uv tool install "graphifyy[robot]"` |
| `chinese` | Kínai lekérdezés-szegmentálás (jieba) | `uv tool install "graphifyy[chinese]"` |
| `all` | Mindent a fentiekből | `uv tool install "graphifyy[all]"` |

</details>

---

## Make your assistant always use the graph

Futtassa ezt egyszer a projektjében, miután felépített egy gráfot:

Futtassa egyszer a `graphify <platform> install` parancsot a projektjében, például `graphify claude install` vagy `graphify codex install` (vagy `graphify install --platform <name>`).

Ez egy kis konfigurációs fájlt ír ki, amely arra utasítja az asszisztensét, hogy a kódbázissal kapcsolatos kérdésekhez a tudásgráfot konzultálja, a szűkített lekérdezéseket, mint a `graphify query "<question>"`, előnyben részesítve a teljes jelentés olvasásával vagy a nyers fájlok grep-elésével szemben.

- **Hook-platformok** (Claude Code, Gemini CLI): egy hook automatikusan elindul a keresés jellegű eszközhívások előtt (és Claude Code esetén, mielőtt a forrásfájlokat egyenként beolvasná a Read/Glob eszközökkel), és az asszisztensét a gráf felé tereli.
- **Utasításfájl-platformok** (Codex, OpenCode, Cursor stb.): a perzisztens utasításfájlok (`AGENTS.md`, `.cursor/rules/` stb.) ugyanazt a lekérdezés-első útmutatást nyújtják.

A `GRAPH_REPORT.md` továbbra is elérhető a széles körű architektúra-áttekintéshez.

Hogy pontosan mely fájlokat írja ki az egyes platformok (a CodeBuddy `CODEBUDDY.md` + `PreToolUse` hookjai, a Codex `AGENTS.md`-je, a Kilo natív `.kilo` beépülője, a Cursor `alwaysApply` szabálya és így tovább), azt a **[Always-on setup](https://docs.graphify.com/guides/always-on)** ismerteti.

A graphify egyszerre minden platformról való eltávolításához: `graphify uninstall` (adja hozzá a `--purge` kapcsolót a `graphify-out/` törléséhez is). Vagy használja a platformspecifikus parancsot (pl. `graphify claude uninstall`).

### CLI skills or MCP instructions?

A `graphify install` által telepített utasítások és a Graphify MCP-kapcsolattal biztosított utasítások a gráf lekérdezésének különböző módjait írják le:

| Beállítás | Használandó útmutatás | Lekérdezési hozzáférés |
|---|---|---|
| Helyi CLI és telepített asszisztens-skill | A `graphify install` által kiírt platformutasítások | Futtassa a `graphify query`, `graphify path` és `graphify explain` parancsokat a helyi gráf ellenében (alapértelmezés szerint `graphify-out/`). |
| Csatlakoztatott Graphify MCP-kiszolgáló | A kapcsolat utasításai és az adott kiszolgáló által felsorolt eszközök | Hívja meg a felsorolt MCP-eszközöket az adott kapcsolat által kiszolgált gráf ellenében. Az eszköznevek és -leírások a kiszolgálóból származnak. |

Mindkettő a szűkített gráflekérdezéseket ösztönzi a széles körű forráskeresések előtt. Válassza azokat az utasításokat, amelyek megfelelnek az asszisztense által ténylegesen elérhető eszközöknek; egyik blokk sem állapít meg univerzális elsőbbségi szabályt az asszisztense utasításfájljaira. Ha mindkét integrációt használja, állapítsa meg, melyik melyik gráfot kérdezi le, és válasszon egy elsődleges lekérdezési útvonalat ahelyett, hogy két feltétel nélküli utasításblokkot másolna az `AGENTS.md` fájlba.

A `graphify install` a helyi asszisztens-integrációt telepíti; nem hoz létre MCP-kapcsolatot. Egy MCP-kliensnek nem kell helyi CLI-lekérdezéseket futtatnia ahhoz, hogy a csatlakoztatott kiszolgálóját használja. Egy helyben üzemeltetett kiszolgálónak továbbra is szüksége van saját Graphify-telepítésre és gráfra, míg egy üzemeltetett kapcsolat olyan gráfot is kiszolgálhat, amely nincs jelen a kliens munkakönyvtárában. Ha a várt eszközök hiányoznak, ellenőrizze a megfelelő CLI-telepítést vagy MCP-kapcsolatot, ahelyett hogy a másik beállítás utasításait felcserélhetőnek tekintené.

---

## What's in the report

A `GRAPH_REPORT.md` összefoglalja a god node-okat, közösségeket és kulcsfontosságú utakat a széles körű architektúra-áttekintéshez. Hogyan épül fel a gráf, és mit tartalmaz: **[How graphify works](https://docs.graphify.com/concepts/architecture)**.

---

## What files it handles: ~40 languages

A graphify ~40 programozási nyelvet elemez lokálisan a tree-sitter AST segítségével, és a dokumentumokat, PDF-eket, képeket és hang-/videóanyagokat egy opcionális szemantikai futtatáson át képezi le. Teljes lista: **[Supported inputs](https://docs.graphify.com/concepts/supported-inputs)**.

---

## Common commands

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

Lásd lentebb a [teljes parancsreferenciát](#full-command-reference).

---

## Ignoring files

A graphify tiszteletben tartja a `.gitignore` fájlt, és támogatja a `--exclude` mintákat, valamint egy projekt `.graphifyignore` fájlt. Részletek: **[Configuration](https://docs.graphify.com/reference/configuration)**.


## Project configuration

Hozzon létre egy `.graphifyrc` fájlt a szkennelési gyökérben azokhoz a beállításokhoz, amelyek a projekthez tartoznak, nem pedig egyetlen futtatáshoz. Soronként egy `key=value`; a `#` karakterrel kezdődő sorok megjegyzések.

**Nem egyértelmű kiterjesztések.** Egyes kiterjesztések különböző projektekben különböző nyelveket jelentenek: a `.inc` a pfSense-en PHP, egy Delphi-fában Pascal, máshol SQL vagy assembly; a `.h` C vagy C++; a `.m` Objective-C vagy MATLAB. A graphify-nak egyetlen globális alapértelmezést kell választania, és amikor rosszul választ, a fájl nem bukik el: rossz nyelvként elemzi, és egy maréknyi véletlenszerű csomópontot eredményez, így a gráf népesnek tűnik, miközben a valódi szimbólumok hiányoznak. Deklarálja, hogy a kiterjesztés mit jelent a repójában:

```
# .graphifyrc
# A language name:
language.inc=php
# Or an extension graphify already knows:
language.tpl=.ts
# Baked into the git hooks (see Team setup):
viz_node_limit=0
```

A deklaráció végigfut az osztályozáson, a kinyerő kiválasztásán, a nyelvtanon és feloldáson, az importokon, a `graphify watch`-on és az AST-gyorsítótáron (egy más nyelven újraelemzett fájl soha nem használja fel újra a régi bejegyzést), és ugyanazt a `.graphifyrc` fájlt olvassa az `extract`, az `update`, a hookok, az MCP-kiszolgáló és a `/graphify` skill. Az elgépelést egyszer jelenti a stderr-en, és a szkennelés az alapértelmezésekkel folytatódik. Hogyan hatnak egymásra a deklarációk a gyorsítótárazással, az inkrementális újraépítésekkel és az import-feloldással: **[Configuration](https://docs.graphify.com/reference/configuration)**.

---

## Team setup

Commitolja vagy ossza meg a gráfot, hogy az egész csapata ugyanazt a kontextust kérdezze le, és ellenőrizze a pull requesteket gráfkontextussal. Lásd: **[Share context with your team](https://docs.graphify.com/guides/team-workflows)** és **[Review pull requests](https://docs.graphify.com/guides/pull-requests)**.

---

## Using the graph directly

Az AI-asszisztensén túl a `graph.json` fájlt közvetlenül a CLI-ből is lekérdezheti a `graphify query`, `graphify path` és `graphify explain` parancsokkal. A több csomópontra illeszkedő nevet elutasítja, és a jelölteket felsorolja ahelyett, hogy találgatna. A szkriptek a kilépési kódból olvashatják ki az eredményt: `0` egy válasz, `3` egy nem egyértelmű név, `4` nincs illeszkedő csomópont. Lásd: **[Ask better graph questions](https://docs.graphify.com/guides/querying)** és a **[query reference](https://docs.graphify.com/reference/query)**.

---

## Environment variables

A backendeket, API-kulcsokat, hook-viselkedést és finomhangolást környezeti változók vezérlik. Teljes táblázat: **[Configuration](https://docs.graphify.com/reference/configuration)**.

---

## Privacy

- **Kódfájlok**: lokálisan feldolgozva a tree-sitter segítségével. Semmi sem hagyja el a gépét. Egy csak kódot tartalmazó korpuszhoz nincs szükség API-kulcsra: a `graphify extract` teljesen offline fut. Vegyes repo esetén adja hozzá a `--code-only` kapcsolót, hogy csak a kódot indexelje, és kihagyja a dokumentumokat/PDF-eket/képeket, amelyekhez egyébként LLM kellene.
- **Videó / hang**: lokálisan átírva a faster-whisper segítségével. Semmi sem hagyja el a gépét.
- **Dokumentumok, PDF-ek, képek**: szemantikai kinyerésre elküldve az AI-asszisztensének (a `/graphify` skillen keresztül, azzal a modellel, amelyet az IDE-munkamenete futtat). A fej nélküli `graphify extract` a következők egyikét igényli: `GEMINI_API_KEY` / `GOOGLE_API_KEY` (Gemini), `MOONSHOT_API_KEY` (Kimi), `ANTHROPIC_API_KEY` (Claude), `OPENAI_API_KEY` (OpenAI), `DEEPSEEK_API_KEY` (DeepSeek), egy futó Ollama-példány (`OLLAMA_BASE_URL`), AWS-hitelesítő adatok a standard provider-láncon keresztül (Bedrock - nincs szükség API-kulcsra, IAM-et használ), vagy a `claude` CLI-bináris (Claude Code - nincs szükség API-kulcsra, az Ön Claude-előfizetését használja). A `--dedup-llm` kapcsoló ugyanazt a kulcsot használja.
- **Adatrezidencia**: a `graphify extract` automatikusan felismeri, melyik providert használja, annak alapján, hogy melyik API-kulcs van beállítva (prioritás: Gemini → Kimi → Claude → OpenAI → DeepSeek → Azure → Bedrock → Ollama). Adatrezidencia-követelményekkel rendelkező kód esetén használja a `--backend ollama` (teljesen lokális) beállítást, vagy adjon meg egy explicit `--backend` kapcsolót. A Kimi (`MOONSHOT_API_KEY`) a kínai Moonshot AI-kiszolgálókra irányít.
- **Nincs telemetria**, nincs használatkövetés, nincs analitika.
- **Lekérdezés-naplózás**: minden `graphify query`, `graphify path`, `graphify explain` és MCP `query_graph` hívás a `~/.cache/graphify-queries.log` fájlba naplózódik JSON Lines formátumban (időbélyeg, kérdés, korpusz, visszaadott csomópontok, időtartam). A teljes részgráf-válaszok alapértelmezés szerint **nem** tárolódnak. Állítsa be a `GRAPHIFY_QUERY_LOG_DISABLE=1` értéket a kikapcsoláshoz, vagy a `GRAPHIFY_QUERY_LOG=/dev/null` értéket a kódút letiltása nélküli elnémításhoz.

---

## Troubleshooting

Gyakori telepítési és kinyerési problémák és azok megoldásai: **[Troubleshooting](https://docs.graphify.com/troubleshooting)**.

---

## Full command reference

Minden parancs és flag, példákkal: **[CLI reference](https://docs.graphify.com/reference/overview)**.

---

## Learn more

- [docs.graphify.com](https://docs.graphify.com): teljes dokumentáció: útmutatók, parancsreferencia és integrációk
- [How it works](../how-it-works.md): a kinyerési folyamat, közösségészlelés, megbízhatósági pontozás, benchmarkok
- [ARCHITECTURE.md](../../ARCHITECTURE.md): modulbontás, hogyan adjunk hozzá egy nyelvet
- [Optional integrations](../docker-mcp-sqlite.md): Docker MCP Toolkit + SQLite
- [The Memory Layer](https://safishamsi.gumroad.com/l/qetvlo): a könyv a graphify mögötti ötletekről, az architektúráról elejétől a végéig

---

## Graphify Cloud

A [**Graphify Cloud**](https://app.graphify.com/login) a graphify tetejére épülő, mindig aktív réteg. Ahelyett, hogy mappánként igény szerint újraépítene egy gráfot, egyetlen élő gráfot tart fenn a teljes szoftverfejlesztési életciklusán át:

- **80%-kal kevesebb token**: a mindig aktív memória azt jelenti, hogy az ügynökei minden munkamenetben abbahagyják a kódbázis újraolvasását és újramagyarázását.
- **Monorepo és repository-közi**: egyetlen összekapcsolt gráf minden szolgáltatáson és repository-n át, nem mappánkénti gráf.
- **Formális verifikáció**: architekturális és függőségi invariánsok ellenőrzése az élő gráf ellenében.
- **Kódellenőrzés az SDLC madártávlati nézetével**: lássa, hogyan gyűrűzik végig egy változás az egész rendszeren, mielőtt mergelne.
- **SDLC-konnektorok**: húzza be a Sentryt, Jirát és másokat, hogy az incidensek, jegyek és a kód egyetlen gráfban éljenek.
- **Mindig aktív**: folyamatosan frissül a háttérben a kódon, dokumentumokon és megbeszéléseken át.

**[Indítson ingyenes 14 napos próbaidőszakot az app.graphify.com oldalon &rarr;](https://app.graphify.com/login)**

---

## Contributing

A hozzájárulásokat szívesen fogadjuk. A fejlesztési beállításért, a teszt- és CI-paritási parancsokért, a git-munkafolyamatért és azért, hogy mi tesz egy hozzájárulást erőssé (a kidolgozott példák és a kinyerési hibajelentések a leghasznosabbak), lásd: **[CONTRIBUTING.md](../../CONTRIBUTING.md)**. Architektúra és hogyan adjunk hozzá egy nyelvet: [ARCHITECTURE.md](../../ARCHITECTURE.md).

Új itt? Köszönjön be a [Discordon](https://discord.gg/XDnKVpzdXB) vagy a [GitHub Discussions](https://github.com/Graphify-Labs/graphify/discussions) felületen.

---

## Contributors

<a href="https://github.com/Graphify-Labs/graphify/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=Graphify-Labs/graphify" alt="graphify contributors" />
</a>

Készült a [contrib.rocks](https://contrib.rocks) segítségével.

---

## Translations

A README 32 nyelven érhető el. Használja a fájl tetején lévő nyelvváltót, hogy a sajátján olvassa, vagy böngésszen a [`docs/translations/`](./) között. Egy fordítás javításához vagy új hozzáadásához nyisson egy pull requestet az ottani megfelelő fájl ellen.

---

## Building on graphify

Épít valamit a graphify ökoszisztémában? Ezt bátorítjuk. Ha a projektje a nevében a „graphify” szót használja (például `graphify-dashboard` vagy `graphify-action`), kérjük, adjon egy rövid megjegyzést a README-jéhez, amely tisztázza, hogy közösségi fejlesztésű, és nem áll kapcsolatban a Graphify Labs-szel, és nem is támogatja azt. A „graphify” és a graphify logó a Graphify Labs védjegyei; kérjük, ne használja őket olyan módon, amely hivatalos státuszt sugall.

---

## Community and links

<p align="center">
  <a href="https://graphify.com"><img src="https://img.shields.io/badge/Website-graphify.com-4c1?style=flat&logo=googlechrome&logoColor=white" alt="Website"/></a>
  <a href="https://discord.gg/XDnKVpzdXB"><img src="https://img.shields.io/badge/Discord-Join-5865F2?style=flat&logo=discord&logoColor=white" alt="Discord"/></a>
  <a href="https://x.com/graphify"><img src="https://img.shields.io/badge/X-graphify-000000?logo=x&logoColor=white" alt="X"/></a>
  <a href="https://www.youtube.com/@graphifylabs"><img src="https://img.shields.io/badge/YouTube-Graphify%20Labs-FF0000?style=flat&logo=youtube&logoColor=white" alt="YouTube"/></a>
  <a href="https://github.com/sponsors/safishamsi"><img src="https://img.shields.io/badge/sponsor-safishamsi-ea4aaa?logo=github-sponsors" alt="Sponsor"/></a>
  <a href="https://safishamsi.gumroad.com/l/qetvlo"><img src="https://img.shields.io/badge/Book-The%20Memory%20Layer-2ea44f?style=flat&logo=gitbook&logoColor=white" alt="The Memory Layer"/></a>
</p>
