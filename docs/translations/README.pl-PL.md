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
  <b>Zmniejsz zużycie tokenów przez agentów o 80%.</b> Graphify Cloud to zawsze aktywna pamięć, która zarządza Twoimi agentami, utrzymuje wysoką jakość kodu i potwierdza poprawność dzięki weryfikacji formalnej. <a href="https://app.graphify.com/login"><b>Rozpocznij darmowy 14-dniowy okres próbny &rarr;</b></a>
</p>

Wpisz `/graphify` w swoim asystencie kodowania AI, a zmapuje on cały Twój projekt (kod, dokumentację, pliki PDF, obrazy, filmy) w **graf wiedzy**, który możesz **odpytywać zamiast przeszukiwać** pliki poleceniem grep.

- **Mapy kodu za darmo, w pełni lokalnie.** Kod jest parsowany za pomocą drzewa AST tree-sitter: deterministycznie, bez LLM, nic nie opuszcza Twojej maszyny. (Dokumentacja, pliki PDF, obrazy i filmy korzystają z modelu Twojego asystenta lub skonfigurowanego klucza API do przebiegu semantycznego.)
- **Każda krawędź jest wyjaśniona.** Każde połączenie jest oznaczone jako `EXTRACTED` (jawne w źródle) lub `INFERRED` (rozpoznane przez graphify), więc możesz odróżnić to, co odczytano bezpośrednio, od tego, co wywnioskowano.
- **To nie jest indeks wektorowy.** Żadnych osadzeń, żadnego magazynu wektorów: prawdziwy graf, po którym się poruszasz. Zadaj pytanie, prześledź ścieżkę między dwiema rzeczami lub wyjaśnij jedną koncepcję.

> [!NOTE]
> **Chcesz mieć to zawsze aktywne?** [Graphify Cloud](https://app.graphify.com/login) utrzymuje graf na żywo w całym cyklu życia oprogramowania: obsługa monorepo i wielu repozytoriów, weryfikacja formalna oraz przegląd kodu z lotu ptaka na cały Twój cykl SDLC, a do tego konektory dla Sentry, Jira i innych, dzięki czemu incydenty i zgłoszenia znajdują się w tym samym grafie co Twój kod. **[Rozpocznij darmowy 14-dniowy okres próbny na app.graphify.com](https://app.graphify.com/login)**.

<p align="center">
  <img src="https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/graph-hero.png" alt="graphify's interactive graph.html showing the FastAPI codebase as a force-directed knowledge graph with a legend of detected communities" width="900">
</p>
<p align="center">
  <em>Baza kodu FastAPI zmapowana przez graphify. Każdy węzeł to koncepcja, kolory to wykryte społeczności, a całość jest klikalna w graph.html.</em>
</p>

**Pierwsze kroki** (30 sekund). Wymaga Python 3.10+ oraz uv (lub pipx):

```bash
uv tool install graphifyy      # install the CLI (or: pipx install graphifyy)
graphify install               # detects your assistant and registers the skill
```

Następnie, w swoim asystencie AI:

```
/graphify .
```

To wszystko. Otrzymujesz **trzy pliki**:

```
graphify-out/
├── graph.html       open in any browser: click nodes, filter, search
├── GRAPH_REPORT.md  the highlights: key concepts, surprising connections, suggested questions
└── graph.json       the full graph: query it anytime without re-reading your files
```

Utrwalony graf zawiera `graph.schema_version`, aby integracje mogły wykrywać
niezgodne zmiany formatu, a także `graph.graphify_version` identyfikujące
wydanie Graphify, które go wygenerowało.

**Jedna instalacja, dowolny asystent, dowolny system.** Claude Code, Cursor, Codex, Gemini CLI, GitHub Copilot i ponad 20 innych, na macOS, Linux i Windows: [wybierz swoją platformę](#install).

---

## See it in action

<p align="center">
  <img src="https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/demo-path.svg" alt="graphify path query: a terminal asks for the shortest path between FastAPI and ModelField, and the answer lights up hop by hop across the knowledge graph" width="900">
</p>

Gdy graf zostanie zbudowany, odpytujesz go zamiast czytać pliki. Prawdziwy wynik, graphify uruchomiony na pokazanej powyżej bazie kodu FastAPI:

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

Każda krawędź niesie **znacznik pewności** (`EXTRACTED` = jawne w źródle, `INFERRED` = wyprowadzone przez rozpoznawanie), więc możesz odróżnić to, co odczytano bezpośrednio, od tego, co wywnioskowano. `graphify query "<question>"` zwraca zawężony podgraf dla pytania w języku naturalnym, a `graphify path A B` pokazuje, jak łączą się dowolne dwie rzeczy.

---

## What it does

Co otrzymujesz od razu po instalacji:

| Capability | What you get |
|---|---|
| **God nodes** | Najbardziej połączone koncepcje, dzięki czemu widzisz, przez co wszystko przepływa |
| **Communities** | Graf podzielony na podsystemy (Leiden), z etykietami bez użycia LLM |
| **Cross-file links** | `calls` / `imports` / `inherits` / `mixes_in` rozpoznane w około 40 językach dzięki drzewu AST tree-sitter |
| **Query, path, explain** | Zadaj pytanie, prześledź ścieżkę między dwiema rzeczami lub wyjaśnij jedną koncepcję: wszystko względem `graph.json` |
| **Rationale + doc refs** | Komentarze `# NOTE:` / `# WHY:` oraz cytowania ADR/RFC stają się pełnoprawnymi węzłami powiązanymi z kodem |
| **Beyond code** | Dokumentacja, pliki PDF, obrazy oraz pliki wideo/audio: wszystko mapuje się do tego samego grafu |
| **Local-first** | Kod jest parsowany lokalnie przez tree-sitter (bez LLM, nic nie opuszcza Twojej maszyny); tylko przebieg semantyczny po dokumentacji/mediach wywołuje backend, i to wyłącznie, jeśli go skonfigurujesz |

> [!TIP]
> Uruchamiasz to na wielu repozytoriach lub w monorepo? [Graphify Cloud](https://app.graphify.com/login) robi to w sposób ciągły i zmniejsza zużycie tokenów przez agentów o 80%, z połączeniami między repozytoriami, przeglądem kodu obejmującym cały cykl SDLC, weryfikacją formalną oraz konektorami Sentry/Jira. [Rozpocznij darmowy 14-dniowy okres próbny &rarr;](https://app.graphify.com/login)

---

## Benchmarks: 0.497 recall@10, 0 LLM credits

| Benchmark | Metric | graphify | Field |
|---|---|---|---|
| LOCOMO (n=300) | recall@10 | **0.497** | mem0 0.048, supermemory 0.149 |
| LOCOMO (n=300) | QA accuracy | 45.3% | supermemory 49.7%, mem0 27.3% |
| LongMemEval-S (n=50) | QA accuracy | **76%** | tied with dense RAG |
| ERPNext cross-tool (n=6) | key-fact coverage | **82.0%** | grep/read baseline 70.8% |
| Graph build | LLM credits | **0** | per-token for most systems |

Każdy system działał na tej samej infrastrukturze testowej z tym samym modelem i budżetami, oceniany przez sędziego zwalidowanego na ślepo względem drugiego sędziego (90,6% zgodności, kappa Cohena 0,81). Pełne tabele dla poszczególnych systemów, wynik dotyczący inteligencji kodu oraz polecenia do odtworzenia: **[BENCHMARKS.md](../../BENCHMARKS.md)**.

---

## Documentation

Pełne przewodniki i dokumentacja referencyjna znajdują się pod adresem **[docs.graphify.com](https://docs.graphify.com)**:

- **[Quickstart](https://docs.graphify.com/quickstart)**: zbuduj swój pierwszy graf
- **[CLI reference](https://docs.graphify.com/reference/overview)**: każde polecenie i flaga
- **[Ask better graph questions](https://docs.graphify.com/guides/querying)**: wzorce odpytywania
- **[Configuration](https://docs.graphify.com/reference/configuration)**: zmienne środowiskowe i strojenie
- **[Supported inputs](https://docs.graphify.com/concepts/supported-inputs)**: języki i typy plików
- **[Team workflows](https://docs.graphify.com/guides/team-workflows)** i **[PR review](https://docs.graphify.com/guides/pull-requests)**
- **[Troubleshooting](https://docs.graphify.com/troubleshooting)** i **[How it works](https://docs.graphify.com/concepts/architecture)**

---

## Prerequisites

| Requirement | Minimum | Check | Install |
|---|---|---|---|
| Python | 3.10+ | `python --version` | [python.org](https://www.python.org/downloads/) |
| uv *(recommended)* | any | `uv --version` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| pipx *(alternative)* | any | `pipx --version` | `pip install pipx` |

**Szybka instalacja na macOS (Homebrew):**
```bash
brew install python@3.12 uv
```

**Szybka instalacja na Windows:**
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
> **Oficjalny pakiet:** Pakiet w PyPI to `graphifyy` (podwójne y). Inne pakiety `graphify*` w PyPI nie są z nami powiązane. Polecenie CLI to nadal `graphify`.

Oficjalne repozytorium źródłowe to [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify).

Dwukomendowy szybki start znajduje się na górze tego README. Ta sekcja opisuje metody instalacji, instalacje w zakresie projektu oraz każdą obsługiwaną platformę.

**Metody instalacji** (wybierz jedną):

```bash
uv tool install graphifyy   # recommended, isolated env (if 'graphify' isn't found after, run: uv tool update-shell)
pipx install graphifyy      # alternative
pip install graphifyy       # may need PATH setup, see Troubleshooting below
```

Następnie uruchom `graphify install` raz. Wykrywa, którego asystenta używasz, i rejestruje umiejętność, więc nie ma konfiguracji dla każdego asystenta z osobna. Otwórz swojego asystenta AI i wpisz `/graphify .`

Aby zainstalować umiejętność asystenta w bieżącym repozytorium zamiast w profilu
użytkownika, dodaj `--project`:

```bash
graphify install --project
graphify install --project --platform codex
```

Instalacje w zakresie projektu zapisują pliki w bieżącym katalogu, na przykład
`.claude/skills/graphify/SKILL.md` lub `.agents/skills/graphify/SKILL.md` (plus
dodatkowy katalog `references/`, który umiejętność ładuje na żądanie), oraz
wypisują wskazówkę `git add` dla plików, które można zatwierdzić.
Polecenia dla poszczególnych platform, które obsługują instalacje w zakresie projektu, przyjmują tę samą flagę,
na przykład `graphify claude install --project` lub `graphify codex install --project`.

> [!TIP]
> Napotykasz `command not found`, problem z `pip` na Macu/Windowsie, kwestie cytowania w PowerShell, użycie `uvx`, osobliwości PATH w git-hookach lub tryb ścisły? Zobacz **[Installation](https://docs.graphify.com/installation)** i **[Troubleshooting](https://docs.graphify.com/troubleshooting)**.

<details>
<summary><b>Pick your platform</b> (20+ assistants, click to expand)</summary>

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
| Pi coding agent | `graphify install --platform pi`, plus `graphify pi guard install` dla natywnego guarda |
| Cursor | `graphify cursor install` |
| Devin CLI | `graphify devin install` |
| Google Antigravity | `graphify antigravity install` |

Użytkownicy Codex potrzebują również `multi_agent = true` w sekcji `[features]` w pliku `~/.codex/config.toml`, aby włączyć równoległą ekstrakcję. CodeBuddy korzysta z tego samego mechanizmu narzędzia Agent i hooka PreToolUse co Claude Code. Factory Droid używa narzędzia `Task` do równoległego uruchamiania podagentów. OpenClaw i Aider korzystają z ekstrakcji sekwencyjnej (obsługa równoległych agentów jest na tych platformach wciąż we wczesnej fazie). Trae używa narzędzia Agent do równoległego uruchamiania podagentów i **nie** obsługuje hooków `PreToolUse`, więc AGENTS.md jest mechanizmem zawsze aktywnym.

`--platform agents` (alias `--platform skills`) celuje w generyczne, międzyframeworkowe lokalizacje [Agent-Skills](https://github.com/anthropics/skills): zdefiniowany w specyfikacji katalog globalny użytkownika `~/.agents/skills/` (odczytywany przez `npx skills` i frameworki zgodne ze specyfikacją) dla instalacji globalnej oraz `./.agents/skills/` dla instalacji w zakresie projektu (`--project`). Samo `graphify install` z założenia pozostaje jednoplatformowe (Claude Code): użyj nazwanej platformy `agents`, gdy chcesz, aby umiejętność była wykrywalna przez dowolny framework odczytujący `.agents/skills`.

Pi nie ma hooka `PreToolUse`, więc `graphify pi guard install` rejestruje natywne rozszerzenie Pi (poprzez własne `pi install <package directory>` Pi), które uruchamia zainstalowane `graphify hook-guard` przed wywołaniami `read`, `grep`, `find` oraz `bash` w stylu wyszukiwania w Pi. Decyzje o świeżości/nieaktualności grafu oraz jednorazowa na sesję odmowa odczytu zindeksowanych plików przy `GRAPHIFY_HOOK_STRICT=1` pochodzą z tej samej polityki, więc Pi odpowiada zachowaniu hooków Claude Code; wskazówki docierają jako komunikat sterujący `<system-reminder source="graphify">`. Wymaga Pi 0.58.4 lub nowszego: wcześniejsze wersje pozwalały, aby komunikat sterujący pominął resztę równoległej partii wywołań narzędzi. Pakiet jest dostarczany wewnątrz instalacji Graphify, więc zainstaluj Graphify trwale (`uv tool install graphifyy` lub `pipx install graphifyy`, nie `uvx`), zrestartuj Pi po instalacji lub aktualizacji i usuń go za pomocą `graphify pi guard uninstall`. Sprawdzane są wyłącznie lokalne cele plikowe; hook potrzebuje `graphify` w bezwzględnym wpisie `PATH` poza projektem, jest ograniczony do dwusekundowego wywołania 256 KiB na wejściu / 64 KiB na wyjściu i zawodzi w sposób otwarty (fail open). Ten sam pakiet ładuje się również w [Oh My Pi](https://github.com/can1357/oh-my-pi): `omp plugin install "$(graphify pi guard path)"`. Zarejestrowana ścieżka zawiera wersję Pythona i venv, więc uruchom ponownie `graphify pi guard install` po zmianie którejkolwiek z nich i usuń stary wpis za pomocą `pi remove <old path>`.

> Codex używa `$graphify` zamiast `/graphify`.

</details>

<details>
<summary><b>Optional extras</b> (install only what you need)</summary>

| Extra | What it adds | Install |
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

## Make your assistant always use the graph

Uruchom to raz w swoim projekcie po zbudowaniu grafu:

Uruchom `graphify <platform> install` raz w swoim projekcie, na przykład `graphify claude install` lub `graphify codex install` (albo `graphify install --platform <name>`).

To zapisuje mały plik konfiguracyjny, który mówi Twojemu asystentowi, aby przy pytaniach o bazę kodu sięgał do grafu wiedzy, preferując zawężone zapytania takie jak `graphify query "<question>"` zamiast czytania całego raportu lub przeszukiwania surowych plików poleceniem grep.

- **Platformy z hookami** (Claude Code, Gemini CLI): hook uruchamia się automatycznie przed wywołaniami narzędzi w stylu wyszukiwania (a w Claude Code również przed czytaniem plików źródłowych po kolei za pomocą narzędzi Read/Glob) i kieruje Twojego asystenta w stronę ścieżki grafu.
- **Platformy z plikami instrukcji** (Codex, OpenCode, Cursor itd.): trwałe pliki instrukcji (`AGENTS.md`, `.cursor/rules/` itd.) zapewniają te same wskazówki „najpierw zapytaj graf".

`GRAPH_REPORT.md` jest nadal dostępny do szerokiego przeglądu architektury.

Dokładnie to, które pliki zapisuje każda platforma (`CODEBUDDY.md` + hooki `PreToolUse` w CodeBuddy, `AGENTS.md` w Codex, natywny plugin `.kilo` w Kilo, reguła `alwaysApply` w Cursorze itd.), jest opisane w **[Always-on setup](https://docs.graphify.com/guides/always-on)**.

Aby usunąć graphify ze wszystkich platform naraz: `graphify uninstall` (dodaj `--purge`, aby usunąć również `graphify-out/`). Albo użyj polecenia dla konkretnej platformy (np. `graphify claude uninstall`).

### CLI skills or MCP instructions?

Instrukcje instalowane przez `graphify install` oraz te dostarczane wraz z połączeniem Graphify MCP opisują różne sposoby odpytywania grafu:

| Setup | Guidance to use | Query access |
|---|---|---|
| Lokalne CLI i zainstalowana umiejętność asystenta | Instrukcje platformy zapisane przez `graphify install` | Uruchamiaj `graphify query`, `graphify path` i `graphify explain` względem lokalnego grafu (domyślnie `graphify-out/`). |
| Połączony serwer Graphify MCP | Instrukcje połączenia i narzędzia wymienione przez ten serwer | Wywołuj wymienione narzędzia MCP względem grafu obsługiwanego przez to połączenie. Nazwy i opisy narzędzi pochodzą z serwera. |

Oba podejścia zachęcają do zawężonych zapytań do grafu przed szerokim przeszukiwaniem źródeł. Wybierz instrukcje pasujące do narzędzi, do których Twój asystent faktycznie ma dostęp; żaden z tych bloków nie ustanawia uniwersalnej reguły pierwszeństwa dla plików instrukcji Twojego asystenta. Jeśli używasz obu integracji, ustal, który graf odpytuje każda z nich, i wybierz główną ścieżkę zapytań zamiast kopiować dwa bezwarunkowe bloki instrukcji do `AGENTS.md`.

`graphify install` instaluje lokalną integrację asystenta; nie ustanawia połączenia MCP. Klient MCP nie musi uruchamiać lokalnych zapytań CLI, aby korzystać z połączonego serwera. Serwer hostowany lokalnie nadal potrzebuje własnej instalacji Graphify i grafu, podczas gdy hostowane połączenie może obsługiwać graf, którego nie ma w katalogu roboczym klienta. Jeśli brakuje oczekiwanych narzędzi, sprawdź odpowiednią instalację CLI lub połączenie MCP, zamiast traktować instrukcje drugiej konfiguracji jako wymienne.

---

## What's in the report

`GRAPH_REPORT.md` podsumowuje god nodes, społeczności i kluczowe ścieżki na potrzeby szerokiego przeglądu architektury. Jak graf jest budowany i co zawiera: **[How graphify works](https://docs.graphify.com/concepts/architecture)**.

---

## What files it handles: ~40 languages

graphify parsuje około 40 języków programowania lokalnie za pomocą drzewa AST tree-sitter oraz mapuje dokumentację, pliki PDF, obrazy i audio/wideo poprzez opcjonalny przebieg semantyczny. Pełna lista: **[Supported inputs](https://docs.graphify.com/concepts/supported-inputs)**.

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

Zobacz [pełną dokumentację poleceń](#full-command-reference) poniżej.

---

## Ignoring files

graphify respektuje `.gitignore` oraz obsługuje wzorce `--exclude` i projektowy `.graphifyignore`. Szczegóły: **[Configuration](https://docs.graphify.com/reference/configuration)**.


## Project configuration

Utwórz plik `.graphifyrc` w katalogu głównym skanowania dla ustawień, które należą do projektu, a nie do pojedynczego uruchomienia. Jeden `key=value` w wierszu; wiersze zaczynające się od `#` są komentarzami.

**Niejednoznaczne rozszerzenia.** Niektóre rozszerzenia oznaczają różne języki w różnych projektach: `.inc` to PHP w pfSense, Pascal w drzewie Delphi, SQL lub asembler gdzie indziej; `.h` to C lub C++; `.m` to Objective-C lub MATLAB. graphify musi wybrać jedno globalne ustawienie domyślne, a gdy wybierze źle, plik nie kończy się błędem: jest parsowany jako niewłaściwy język i daje garść przypadkowych węzłów, więc graf wygląda na wypełniony, podczas gdy brakuje prawdziwych symboli. Zadeklaruj, co dane rozszerzenie oznacza w Twoim repozytorium:

```
# .graphifyrc
# A language name:
language.inc=php
# Or an extension graphify already knows:
language.tpl=.ts
# Baked into the git hooks (see Team setup):
viz_node_limit=0
```

Deklaracja przepływa przez klasyfikację, wybór ekstraktora, gramatykę i rozpoznawanie, importy, `graphify watch` oraz pamięć podręczną AST (plik ponownie sparsowany pod innym językiem nigdy nie używa ponownie starego wpisu), a ten sam `.graphifyrc` jest odczytywany przez `extract`, `update`, hooki, serwer MCP oraz umiejętność `/graphify`. Literówka jest raz zgłaszana na stderr, a skanowanie jest kontynuowane z ustawieniami domyślnymi. Jak deklaracje współdziałają z buforowaniem, przyrostowymi przebudowami i rozpoznawaniem importów: **[Configuration](https://docs.graphify.com/reference/configuration)**.

---

## Team setup

Zatwierdź lub udostępnij graf, aby cały Twój zespół odpytywał ten sam kontekst, i przeglądaj pull requesty z kontekstem grafu. Zobacz **[Share context with your team](https://docs.graphify.com/guides/team-workflows)** i **[Review pull requests](https://docs.graphify.com/guides/pull-requests)**.

---

## Using the graph directly

Poza Twoim asystentem AI możesz odpytywać `graph.json` bezpośrednio z CLI za pomocą `graphify query`, `graphify path` i `graphify explain`. Nazwa pasująca do kilku węzłów jest odrzucana z wypisaniem kandydatów, zamiast być zgadywana. Skrypty mogą odczytać wynik z kodu wyjścia: `0` odpowiedź, `3` niejednoznaczna nazwa, `4` brak pasującego węzła. Zobacz **[Ask better graph questions](https://docs.graphify.com/guides/querying)** oraz **[query reference](https://docs.graphify.com/reference/query)**.

---

## Environment variables

Backendy, klucze API, zachowanie hooków i strojenie są kontrolowane przez zmienne środowiskowe. Pełna tabela: **[Configuration](https://docs.graphify.com/reference/configuration)**.

---

## Privacy

- **Pliki kodu**: przetwarzane lokalnie przez tree-sitter. Nic nie opuszcza Twojej maszyny. Korpus zawierający wyłącznie kod nie wymaga klucza API: `graphify extract` działa w pełni offline. W mieszanym repozytorium dodaj `--code-only`, aby zindeksować tylko kod i pominąć dokumentację/pliki PDF/obrazy, które w przeciwnym razie wymagałyby LLM.
- **Wideo / audio**: transkrybowane lokalnie za pomocą faster-whisper. Nic nie opuszcza Twojej maszyny.
- **Dokumentacja, pliki PDF, obrazy**: wysyłane do Twojego asystenta AI w celu ekstrakcji semantycznej (poprzez umiejętność `/graphify`, z użyciem dowolnego modelu, na którym działa Twoja sesja IDE). Bezgłowe `graphify extract` wymaga `GEMINI_API_KEY` / `GOOGLE_API_KEY` (Gemini), `MOONSHOT_API_KEY` (Kimi), `ANTHROPIC_API_KEY` (Claude), `OPENAI_API_KEY` (OpenAI), `DEEPSEEK_API_KEY` (DeepSeek), działającej instancji Ollama (`OLLAMA_BASE_URL`), poświadczeń AWS poprzez standardowy łańcuch dostawców (Bedrock: nie jest potrzebny klucz API, używa IAM) lub binarki CLI `claude` (Claude Code: nie jest potrzebny klucz API, używa Twojej subskrypcji Claude). Flaga `--dedup-llm` używa tego samego klucza.
- **Rezydencja danych**: `graphify extract` automatycznie wykrywa, którego dostawcy użyć, na podstawie tego, który klucz API jest ustawiony (priorytet: Gemini → Kimi → Claude → OpenAI → DeepSeek → Azure → Bedrock → Ollama). W przypadku kodu z wymaganiami dotyczącymi rezydencji danych użyj `--backend ollama` (w pełni lokalnie) lub przekaż jawną flagę `--backend`. Kimi (`MOONSHOT_API_KEY`) kieruje do serwerów Moonshot AI w Chinach.
- **Brak telemetrii**, brak śledzenia użycia, brak analityki.
- **Rejestrowanie zapytań**: każde wywołanie `graphify query`, `graphify path`, `graphify explain` oraz MCP `query_graph` jest zapisywane do `~/.cache/graphify-queries.log` w formacie JSON Lines (znacznik czasu, pytanie, korpus, liczba zwróconych węzłów, czas trwania). Pełne odpowiedzi podgrafu **nie** są domyślnie przechowywane. Ustaw `GRAPHIFY_QUERY_LOG_DISABLE=1`, aby zrezygnować, lub `GRAPHIFY_QUERY_LOG=/dev/null`, aby wyciszyć bez wyłączania ścieżki kodu.

---

## Troubleshooting

Typowe problemy z instalacją i ekstrakcją oraz ich rozwiązania: **[Troubleshooting](https://docs.graphify.com/troubleshooting)**.

---

## Full command reference

Każde polecenie i flaga, z przykładami: **[CLI reference](https://docs.graphify.com/reference/overview)**.

---

## Learn more

- [docs.graphify.com](https://docs.graphify.com): pełna dokumentacja: przewodniki, dokumentacja poleceń i integracje
- [How it works](../how-it-works.md): potok ekstrakcji, wykrywanie społeczności, ocena pewności, benchmarki
- [ARCHITECTURE.md](../../ARCHITECTURE.md): podział na moduły, jak dodać język
- [Optional integrations](../docker-mcp-sqlite.md): Docker MCP Toolkit + SQLite
- [The Memory Layer](https://safishamsi.gumroad.com/l/qetvlo): książka o ideach stojących za graphify, architektura od początku do końca

---

## Graphify Cloud

[**Graphify Cloud**](https://app.graphify.com/login) to zawsze aktywna warstwa zbudowana na bazie graphify. Zamiast grafu, który odbudowujesz na żądanie dla każdego folderu, utrzymuje jeden graf na żywo w całym cyklu życia Twojego oprogramowania:

- **80% mniej tokenów**: zawsze aktywna pamięć sprawia, że Twoi agenci przestają ponownie czytać i ponownie wyjaśniać bazę kodu w każdej sesji.
- **Monorepo i wiele repozytoriów**: jeden połączony graf obejmujący każdą usługę i repozytorium, a nie graf na folder.
- **Weryfikacja formalna**: sprawdzaj niezmienniki architektoniczne i zależności względem grafu na żywo.
- **Przegląd kodu z lotu ptaka na cały Twój SDLC**: zobacz, jak zmiana rozchodzi się po całym systemie, zanim ją scalisz.
- **Konektory SDLC**: pobieraj dane z Sentry, Jira i innych, dzięki czemu incydenty, zgłoszenia i kod żyją w jednym grafie.
- **Zawsze aktywne**: aktualizuje się w sposób ciągły w tle, obejmując kod, dokumentację i spotkania.

**[Rozpocznij darmowy 14-dniowy okres próbny na app.graphify.com &rarr;](https://app.graphify.com/login)**

---

## Contributing

Wkład jest mile widziany. Zobacz **[CONTRIBUTING.md](../../CONTRIBUTING.md)**, aby poznać konfigurację środowiska deweloperskiego, polecenia testów i zgodności z CI, przepływ pracy w git oraz to, co składa się na mocny wkład (opracowane przykłady i zgłoszenia błędów ekstrakcji są najbardziej przydatne). Architektura i jak dodać język: [ARCHITECTURE.md](../../ARCHITECTURE.md).

Jesteś tu nowy? Przywitaj się na [Discordzie](https://discord.gg/graphify) lub w [GitHub Discussions](https://github.com/Graphify-Labs/graphify/discussions).

---

## Contributors

<a href="https://github.com/Graphify-Labs/graphify/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=Graphify-Labs/graphify" alt="graphify contributors" />
</a>

Wykonane z [contrib.rocks](https://contrib.rocks).

---

## Translations

README jest dostępne w 32 językach. Użyj przełącznika języków na górze tego pliku, aby przeczytać je w swoim, lub przeglądaj [`docs/translations/`](./). Aby ulepszyć tłumaczenie lub dodać nowe, otwórz pull request dotyczący odpowiedniego pliku w tym miejscu.

---

## Building on graphify

Budujesz coś w ekosystemie graphify? To jest zachęcane. Jeśli Twój projekt używa „graphify" w swojej nazwie (na przykład `graphify-dashboard` lub `graphify-action`), dodaj proszę krótką notkę do swojego README wyjaśniającą, że został zbudowany przez społeczność i nie jest powiązany z Graphify Labs ani przez nie wspierany. „graphify" oraz logo graphify są znakami Graphify Labs; prosimy nie używać ich w sposób sugerujący oficjalny status.

---

## Community and links

<p align="center">
  <a href="https://graphify.com"><img src="https://img.shields.io/badge/Website-graphify.com-4c1?style=flat&logo=googlechrome&logoColor=white" alt="Website"/></a>
  <a href="https://discord.gg/graphify"><img src="https://img.shields.io/badge/Discord-Join-5865F2?style=flat&logo=discord&logoColor=white" alt="Discord"/></a>
  <a href="https://x.com/graphify"><img src="https://img.shields.io/badge/X-graphify-000000?logo=x&logoColor=white" alt="X"/></a>
  <a href="https://www.youtube.com/@graphifylabs"><img src="https://img.shields.io/badge/YouTube-Graphify%20Labs-FF0000?style=flat&logo=youtube&logoColor=white" alt="YouTube"/></a>
  <a href="https://github.com/sponsors/safishamsi"><img src="https://img.shields.io/badge/sponsor-safishamsi-ea4aaa?logo=github-sponsors" alt="Sponsor"/></a>
  <a href="https://safishamsi.gumroad.com/l/qetvlo"><img src="https://img.shields.io/badge/Book-The%20Memory%20Layer-2ea44f?style=flat&logo=gitbook&logoColor=white" alt="The Memory Layer"/></a>
</p>
