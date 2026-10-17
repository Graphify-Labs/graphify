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
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue" alt="License: Apache-2.0"/></a>
  <a href="https://pepy.tech/project/graphifyy"><img src="https://img.shields.io/pepy/dt/graphifyy?color=blue&label=downloads" alt="Downloads"/></a>
  <a href="https://docs.graphify.com"><img src="https://img.shields.io/badge/Docs-docs.graphify.com-0b7285?style=flat&logo=readthedocs&logoColor=white" alt="Docs"/></a>
  <a href="https://app.graphify.com/login"><img src="https://img.shields.io/badge/Graphify%20Cloud-app.graphify.com-118d4f?style=flat&logoColor=white" alt="Graphify Cloud"/></a>
  <a href="https://discord.gg/XDnKVpzdXB"><img src="https://img.shields.io/badge/Discord-Join-5865F2?style=flat&logo=discord&logoColor=white" alt="Discord"/></a>
  <a href="https://www.youtube.com/@graphifylabs"><img src="https://img.shields.io/badge/YouTube-Graphify%20Labs-FF0000?style=flat&logo=youtube&logoColor=white" alt="YouTube"/></a>
  <a href="https://www.linkedin.com/company/graphify-labs"><img src="https://img.shields.io/badge/LinkedIn-Graphify%20Labs-0077B5?logo=linkedin" alt="LinkedIn"/></a>
  <a href="https://www.ycombinator.com/companies/graphify-labs"><img src="https://img.shields.io/badge/Y%20Combinator-S26-F0652F?style=flat&logo=ycombinator&logoColor=white" alt="YC S26"/></a>
</p>

<p align="center">
  <b>Senken Sie die Token-Ausgaben Ihrer Agenten um 80%.</b> Graphify Cloud ist ein stets aktives Gedächtnis, das Ihre Agenten steuert, die Codequalität hoch hält und die Korrektheit mit formaler Verifikation nachweist. <a href="https://app.graphify.com/login"><b>Starten Sie eine kostenlose 14-tägige Testphase &rarr;</b></a>
</p>

Geben Sie `/graphify` in Ihren KI-Coding-Assistenten ein, und er bildet Ihr gesamtes Projekt (Code, Dokumente, PDFs, Bilder, Videos) in einen **Wissensgraphen** ab, den Sie **abfragen können, statt** durch Dateien zu **grep**pen.

- **Code-Karten kostenlos, vollständig lokal.** Code wird mit tree-sitter AST geparst: deterministisch, kein LLM, nichts verlässt Ihren Rechner. (Dokumente, PDFs, Bilder und Videos nutzen das Modell Ihres Assistenten oder einen konfigurierten API-Schlüssel für einen semantischen Durchlauf.)
- **Jede Kante wird erklärt.** Jede Verbindung ist mit `EXTRACTED` (explizit in der Quelle) oder `INFERRED` (von graphify aufgelöst) markiert, sodass Sie unterscheiden können, was direkt gelesen und was abgeleitet wurde.
- **Kein Vektorindex.** Keine Embeddings, kein Vektorspeicher: ein echter Graph, den Sie durchlaufen. Stellen Sie eine Frage, verfolgen Sie den Pfad zwischen zwei Dingen oder lassen Sie ein Konzept erklären.

> [!NOTE]
> **Möchten Sie das stets aktiv haben?** [Graphify Cloud](https://app.graphify.com/login) hält den Graphen über Ihren gesamten SDLC hinweg live: Unterstützung für Monorepos und repo-übergreifende Arbeit, formale Verifikation und Code-Review mit einer Vogelperspektive auf Ihren SDLC, dazu Konnektoren für Sentry, Jira und mehr, damit Vorfälle und Tickets im selben Graphen wie Ihr Code liegen. **[Starten Sie eine kostenlose 14-tägige Testphase unter app.graphify.com](https://app.graphify.com/login)**.

<p align="center">
  <img src="https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/graph-hero.png" alt="graphify's interactive graph.html showing the FastAPI codebase as a force-directed knowledge graph with a legend of detected communities" width="900">
</p>
<p align="center">
  <em>Die FastAPI-Codebasis, abgebildet von graphify. Jeder Knoten ist ein Konzept, Farben sind erkannte Communities, und das Ganze ist in graph.html anklickbar.</em>
</p>

**Erste Schritte** (30 Sekunden). Benötigt Python 3.10+ und uv (oder pipx):

```bash
uv tool install graphifyy      # install the CLI (or: pipx install graphifyy)
graphify install               # detects your assistant and registers the skill
```

Dann, in Ihrem KI-Assistenten:

```
/graphify .
```

Das war's. Sie erhalten **drei Dateien**:

```
graphify-out/
├── graph.html       open in any browser: click nodes, filter, search
├── GRAPH_REPORT.md  the highlights: key concepts, surprising connections, suggested questions
└── graph.json       the full graph: query it anytime without re-reading your files
```

Der persistierte Graph enthält `graph.schema_version`, damit Integrationen
inkompatible Formatänderungen erkennen können, sowie `graph.graphify_version`,
das die Graphify-Version angibt, die ihn erzeugt hat.

**Eine Installation, jeder Assistent, jedes Betriebssystem.** Claude Code, Cursor, Codex, Gemini CLI, GitHub Copilot und über 20 weitere, auf macOS, Linux und Windows: [wählen Sie Ihre Plattform](#install).

---

## In Aktion sehen

<p align="center">
  <img src="https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/demo-path.svg" alt="graphify path query: a terminal asks for the shortest path between FastAPI and ModelField, and the answer lights up hop by hop across the knowledge graph" width="900">
</p>

Sobald der Graph erstellt ist, fragen Sie ihn ab, anstatt Dateien zu lesen. Echte Ausgabe, graphify ausgeführt auf der oben gezeigten FastAPI-Codebasis:

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

Jede Kante trägt eine **Vertrauensmarkierung** (`EXTRACTED` = explizit in der Quelle, `INFERRED` = durch Auflösung abgeleitet), sodass Sie unterscheiden können, was direkt gelesen und was abgeleitet wurde. `graphify query "<question>"` liefert einen begrenzten Teilgraphen für eine Frage in natürlicher Sprache, und `graphify path A B` verfolgt, wie zwei beliebige Dinge zusammenhängen.

---

## Was es tut

Was Sie out of the box bekommen:

| Funktion | Was Sie erhalten |
|---|---|
| **God-Nodes** | Die am stärksten verbundenen Konzepte, damit Sie sehen, wodurch alles fließt |
| **Communities** | Der Graph aufgeteilt in Subsysteme (Leiden), mit LLM-freien Labels |
| **Dateiübergreifende Verknüpfungen** | `calls` / `imports` / `inherits` / `mixes_in` aufgelöst über ~40 Sprachen via tree-sitter AST |
| **Query, path, explain** | Stellen Sie eine Frage, verfolgen Sie den Pfad zwischen zwei Dingen oder lassen Sie ein Konzept erklären, alles gegen `graph.json` |
| **Begründung + Dok-Referenzen** | `# NOTE:` / `# WHY:` Kommentare und ADR/RFC-Zitate werden zu erstklassigen Knoten, die mit dem Code verknüpft sind |
| **Über Code hinaus** | Dokumente, PDFs, Bilder und Video/Audio bilden sich alle in denselben Graphen ab |
| **Local-first** | Code wird lokal mit tree-sitter geparst (kein LLM, nichts verlässt Ihren Rechner); nur der semantische Durchlauf über Dokumente/Medien ruft ein Backend auf, und auch nur, wenn Sie eines konfigurieren |

> [!TIP]
> Führen Sie das über viele Repos oder ein Monorepo aus? [Graphify Cloud](https://app.graphify.com/login) tut dies kontinuierlich und senkt die Token-Ausgaben der Agenten um 80%, mit repo-übergreifenden Verknüpfungen, SDLC-weitem Code-Review, formaler Verifikation und Sentry/Jira-Konnektoren. [Starten Sie eine kostenlose 14-tägige Testphase &rarr;](https://app.graphify.com/login)

---

## Benchmarks: 0.497 recall@10, 0 LLM credits

| Benchmark | Metrik | graphify | Feld |
|---|---|---|---|
| LOCOMO (n=300) | recall@10 | **0.497** | mem0 0.048, supermemory 0.149 |
| LOCOMO (n=300) | QA accuracy | 45.3% | supermemory 49.7%, mem0 27.3% |
| LongMemEval-S (n=50) | QA accuracy | **76%** | tied with dense RAG |
| ERPNext cross-tool (n=6) | key-fact coverage | **82.0%** | grep/read baseline 70.8% |
| Graph build | LLM credits | **0** | per-token for most systems |

Jedes System lief auf demselben Harness mit demselben Modell und denselben Budgets, bewertet von einem Judge, der blind gegen einen zweiten Judge validiert wurde (90.6% Übereinstimmung, Cohens Kappa 0.81). Vollständige Tabellen pro System, das Code-Intelligence-Ergebnis und Reproduktionsbefehle: **[BENCHMARKS.md](../../BENCHMARKS.md)**.

---

## Dokumentation

Vollständige Anleitungen und Referenz finden Sie unter **[docs.graphify.com](https://docs.graphify.com)**:

- **[Quickstart](https://docs.graphify.com/quickstart)**: erstellen Sie Ihren ersten Graphen
- **[CLI-Referenz](https://docs.graphify.com/reference/overview)**: jeder Befehl und jedes Flag
- **[Bessere Graphenfragen stellen](https://docs.graphify.com/guides/querying)**: Abfragemuster
- **[Konfiguration](https://docs.graphify.com/reference/configuration)**: Umgebungsvariablen und Feinabstimmung
- **[Unterstützte Eingaben](https://docs.graphify.com/concepts/supported-inputs)**: Sprachen und Dateitypen
- **[Team-Workflows](https://docs.graphify.com/guides/team-workflows)** und **[PR-Review](https://docs.graphify.com/guides/pull-requests)**
- **[Fehlerbehebung](https://docs.graphify.com/troubleshooting)** und **[Wie es funktioniert](https://docs.graphify.com/concepts/architecture)**

---

## Voraussetzungen

| Anforderung | Minimum | Prüfen | Installieren |
|---|---|---|---|
| Python | 3.10+ | `python --version` | [python.org](https://www.python.org/downloads/) |
| uv *(empfohlen)* | beliebig | `uv --version` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| pipx *(Alternative)* | beliebig | `pipx --version` | `pip install pipx` |

**macOS Schnellinstallation (Homebrew):**
```bash
brew install python@3.12 uv
```

**Windows Schnellinstallation:**
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
> **Offizielles Paket:** Das PyPI-Paket ist `graphifyy` (doppeltes y). Andere `graphify*`-Pakete auf PyPI sind nicht affiliiert. Der CLI-Befehl ist weiterhin `graphify`.

Das offizielle Quell-Repository ist [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify).

Der Zwei-Befehle-Quickstart steht am Anfang dieser README. Dieser Abschnitt behandelt die Installationsmethoden, projektbezogene Installationen und jede unterstützte Plattform.

**Installationsmethoden** (eine auswählen):

```bash
uv tool install graphifyy   # recommended, isolated env (if 'graphify' isn't found after, run: uv tool update-shell)
pipx install graphifyy      # alternative
pip install graphifyy       # may need PATH setup, see Troubleshooting below
```

Führen Sie dann einmal `graphify install` aus. Es erkennt, welchen Assistenten Sie nutzen, und registriert den Skill, sodass es keine Einrichtung pro Assistent gibt. Öffnen Sie Ihren KI-Assistenten und geben Sie `/graphify .` ein.

Um den Assistenten-Skill in das aktuelle Repository statt in Ihr
Benutzerprofil zu installieren, fügen Sie `--project` hinzu:

```bash
graphify install --project
graphify install --project --platform codex
```

Projektbezogene Installationen schreiben unter das aktuelle Verzeichnis, zum Beispiel
`.claude/skills/graphify/SKILL.md` oder `.agents/skills/graphify/SKILL.md` (plus ein
`references/`-Sidecar, das der Skill bei Bedarf lädt), und
geben einen `git add`-Hinweis für Dateien aus, die committet werden können.
Per-Plattform-Befehle, die projektbezogene Installationen unterstützen, akzeptieren dasselbe Flag,
zum Beispiel `graphify claude install --project` oder `graphify codex install --project`.

> [!TIP]
> Stoßen Sie auf `command not found`, ein `pip`-Problem unter Mac/Windows, PowerShell-Quoting, `uvx`-Nutzung, Git-Hook-PATH-Eigenheiten oder den Strict-Modus? Siehe **[Installation](https://docs.graphify.com/installation)** und **[Fehlerbehebung](https://docs.graphify.com/troubleshooting)**.

<details>
<summary><b>Pick your platform</b> (20+ assistants, click to expand)</summary>

| Plattform | Installationsbefehl |
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

Codex-Nutzer benötigen außerdem `multi_agent = true` unter `[features]` in `~/.codex/config.toml` für parallele Extraktion. CodeBuddy verwendet denselben Agent-Tool- und PreToolUse-Hook-Mechanismus wie Claude Code. Factory Droid nutzt das `Task`-Tool für parallelen Subagent-Versand. OpenClaw und Aider nutzen sequenzielle Extraktion (die Unterstützung paralleler Agenten steckt auf diesen Plattformen noch in den Anfängen). Trae nutzt das Agent-Tool für parallelen Subagent-Versand und unterstützt **keine** `PreToolUse`-Hooks, daher ist AGENTS.md der stets aktive Mechanismus.

`--platform agents` (alias `--platform skills`) zielt auf die generischen framework-übergreifenden [Agent-Skills](https://github.com/anthropics/skills)-Verzeichnisse: den benutzer-globalen `~/.agents/skills/` der Spezifikation (gelesen von `npx skills` und spec-konformen Frameworks) für eine globale Installation, und `./.agents/skills/` für eine Projekt-Installation (`--project`). Das bloße `graphify install` bleibt bewusst einplattformig (Claude Code): nutzen Sie die benannte `agents`-Plattform, wenn der Skill von jedem Framework auffindbar sein soll, das `.agents/skills` liest.

Pi hat keinen `PreToolUse`-Hook, daher registriert `graphify pi guard install` eine native Pi-Erweiterung (über Pis eigenes `pi install <package directory>`), die das installierte `graphify hook-guard` vor Pis `read`-, `grep`-, `find`- und suchartigen `bash`-Aufrufen ausführt. Entscheidungen über frische/veraltete Graphen und die `GRAPHIFY_HOOK_STRICT=1`-Verweigerung eines indizierten Lesevorgangs einmal pro Sitzung stammen aus derselben Richtlinie, sodass Pi dem Hook-Verhalten von Claude Code entspricht; die Anleitung kommt als `<system-reminder source="graphify">`-Steuernachricht. Es benötigt Pi 0.58.4 oder neuer: frühere Versionen ließen eine Steuernachricht den Rest eines parallelen Tool-Call-Batches überspringen. Das Paket wird innerhalb der Graphify-Installation ausgeliefert, installieren Sie Graphify also persistent (`uv tool install graphifyy` oder `pipx install graphifyy`, nicht `uvx`), starten Sie Pi nach Installation oder Upgrade neu und entfernen Sie es mit `graphify pi guard uninstall`. Nur lokale Dateiziele werden inspiziert; der Hook benötigt `graphify` auf einem absoluten `PATH`-Eintrag außerhalb des Projekts, ist auf einen Aufruf von zwei Sekunden, 256 KiB-rein/64 KiB-raus begrenzt und schlägt fail-open. Dasselbe Paket lädt auch in [Oh My Pi](https://github.com/can1357/oh-my-pi): `omp plugin install "$(graphify pi guard path)"`. Der registrierte Pfad enthält die Python-Version und das venv, führen Sie `graphify pi guard install` also nach einer Änderung an einem von beiden erneut aus, und entfernen Sie den alten Eintrag mit `pi remove <old path>`.

> Codex verwendet `$graphify` statt `/graphify`.

</details>

<details>
<summary><b>Optional extras</b> (install only what you need)</summary>

| Extra | Was es hinzufügt | Installieren |
|---|---|---|
| `pdf` | PDF-Extraktion | `uv tool install "graphifyy[pdf]"` |
| `office` | `.docx`- und `.xlsx`-Unterstützung | `uv tool install "graphifyy[office]"` |
| `google` | Google Sheets Rendering | `uv tool install "graphifyy[google]"` |
| `video` | Video/Audio-Transkription (faster-whisper + yt-dlp) | `uv tool install "graphifyy[video]"` |
| `mcp` | MCP stdio-Server | `uv tool install "graphifyy[mcp]"` |
| `neo4j` | Neo4j Push-Unterstützung | `uv tool install "graphifyy[neo4j]"` |
| `falkordb` | FalkorDB Push-Unterstützung | `uv tool install "graphifyy[falkordb]"` |
| `svg` | SVG-Graphexport | `uv tool install "graphifyy[svg]"` |
| `leiden` | Leiden-Community-Erkennung (graspologic auf Python < 3.13; natives Backend auf 3.13+) | `uv tool install "graphifyy[leiden]"` |
| `ollama` | Ollama lokale Inferenz | `uv tool install "graphifyy[ollama]"` |
| `openai` | OpenAI / OpenAI-kompatible APIs | `uv tool install "graphifyy[openai]"` |
| `gemini` | Google Gemini API | `uv tool install "graphifyy[gemini]"` |
| `anthropic` | Anthropic Claude API (`--backend claude`, uses `ANTHROPIC_API_KEY`) | `uv tool install "graphifyy[anthropic]"` |
| `bedrock` | AWS Bedrock (uses IAM, no API key) | `uv tool install "graphifyy[bedrock]"` |
| `azure` | Azure OpenAI Service (`--backend azure`, uses `AZURE_OPENAI_API_KEY` + `AZURE_OPENAI_ENDPOINT`) | `uv tool install "graphifyy[openai]"` |
| `sql` | SQL-Schema-Extraktion | `uv tool install "graphifyy[sql]"` |
| `postgres` | Live-PostgreSQL-Introspektion (`--postgres DSN`) | `uv tool install "graphifyy[postgres]"` |
| `dm` | BYOND DreamMaker `.dm`/`.dme` AST-Extraktion (benötigt möglicherweise einen C-Compiler + `python3-dev`, falls kein Wheel zu Ihrer Plattform passt) | `uv tool install "graphifyy[dm]"` |
| `terraform` | Terraform / HCL `.tf`/`.tfvars`/`.hcl` AST-Extraktion | `uv tool install "graphifyy[terraform]"` |
| `pascal` | Pascal / Delphi `.pas`/`.dpr`/`.dpk`/`.inc` AST-Extraktion (genauere `calls`/`inherits`-Kanten; fällt auf einen Regex-Extraktor zurück, wenn nicht vorhanden) | `uv tool install "graphifyy[pascal]"` |
| `ocaml` | OCaml `.ml`/`.mli` AST-Extraktion | `uv tool install "graphifyy[ocaml]"` |
| `commonlisp` | Common Lisp `.lisp`/`.cl`/`.lsp`/`.asd` AST-Extraktion | `uv tool install "graphifyy[commonlisp]"` |
| `robot` | Robot Framework `.robot`/`.resource`-Extraktion (Suites, Testfälle, Keywords, Keyword-Call- und Resource/Library-Import-Kanten) | `uv tool install "graphifyy[robot]"` |
| `chinese` | Chinesische Query-Segmentierung (jieba) | `uv tool install "graphifyy[chinese]"` |
| `all` | Alles oben Genannte | `uv tool install "graphifyy[all]"` |

</details>

---

## Bringen Sie Ihren Assistenten dazu, den Graphen immer zu nutzen

Führen Sie dies einmal in Ihrem Projekt aus, nachdem Sie einen Graphen erstellt haben:

Führen Sie `graphify <platform> install` einmal in Ihrem Projekt aus, zum Beispiel `graphify claude install` oder `graphify codex install` (oder `graphify install --platform <name>`).

Dies schreibt eine kleine Konfigurationsdatei, die Ihrem Assistenten sagt, den Wissensgraphen für Codebasis-Fragen zu konsultieren und begrenzte Abfragen wie `graphify query "<question>"` dem Lesen des vollständigen Berichts oder dem Grep roher Dateien vorzuziehen.

- **Hook-Plattformen** (Claude Code, Gemini CLI): ein Hook feuert automatisch vor suchartigen Tool-Aufrufen (und, bei Claude Code, bevor Quelldateien einzeln über die Read/Glob-Tools gelesen werden) und lenkt Ihren Assistenten in Richtung des Graphenpfads.
- **Instruktionsdatei-Plattformen** (Codex, OpenCode, Cursor usw.): persistente Instruktionsdateien (`AGENTS.md`, `.cursor/rules/` usw.) liefern dieselbe query-first-Anleitung.

`GRAPH_REPORT.md` steht weiterhin für eine breite Architekturüberprüfung zur Verfügung.

Welche Dateien jede Plattform genau schreibt (CodeBuddys `CODEBUDDY.md` + `PreToolUse`-Hooks, Codex' `AGENTS.md`, Kilos natives `.kilo`-Plugin, Cursors `alwaysApply`-Regel usw.) wird in **[Always-on-Einrichtung](https://docs.graphify.com/guides/always-on)** behandelt.

Um graphify von allen Plattformen auf einmal zu entfernen: `graphify uninstall` (fügen Sie `--purge` hinzu, um auch `graphify-out/` zu löschen). Oder nutzen Sie den Per-Plattform-Befehl (z. B. `graphify claude uninstall`).

### CLI-Skills oder MCP-Instruktionen?

Die von `graphify install` installierten Instruktionen und jene, die mit einer Graphify-MCP-Verbindung geliefert werden, beschreiben unterschiedliche Wege, einen Graphen abzufragen:

| Einrichtung | Zu nutzende Anleitung | Abfragezugriff |
|---|---|---|
| Lokale CLI und installierter Assistenten-Skill | Die von `graphify install` geschriebenen Plattform-Instruktionen | Führen Sie `graphify query`, `graphify path` und `graphify explain` gegen den lokalen Graphen aus (`graphify-out/` standardmäßig). |
| Verbundener Graphify-MCP-Server | Die Instruktionen der Verbindung und die von diesem Server aufgelisteten Tools | Rufen Sie die aufgelisteten MCP-Tools gegen den von dieser Verbindung bereitgestellten Graphen auf. Tool-Namen und -Beschreibungen stammen vom Server. |

Beide empfehlen begrenzte Graphenabfragen vor breiten Quellensuchen. Wählen Sie die Instruktionen, die zu den Tools passen, auf die Ihr Assistent tatsächlich zugreifen kann; keiner der Blöcke legt eine universelle Vorrangregel für die Instruktionsdateien Ihres Assistenten fest. Wenn Sie beide Integrationen nutzen, identifizieren Sie, welchen Graphen jede abfragt, und wählen Sie einen primären Abfragepfad, statt zwei unbedingte Instruktionsblöcke in `AGENTS.md` zu kopieren.

`graphify install` installiert die lokale Assistenten-Integration; es stellt keine MCP-Verbindung her. Ein MCP-Client muss keine lokalen CLI-Abfragen ausführen, um seinen verbundenen Server zu nutzen. Ein lokal gehosteter Server benötigt weiterhin seine eigene Graphify-Installation und einen Graphen, während eine gehostete Verbindung einen Graphen bereitstellen kann, der nicht im Arbeitsverzeichnis des Clients vorhanden ist. Wenn die erwarteten Tools fehlen, prüfen Sie die relevante CLI-Installation oder MCP-Verbindung, statt die Instruktionen der jeweils anderen Einrichtung als austauschbar zu behandeln.

---

## Was im Bericht steht

`GRAPH_REPORT.md` fasst die God-Nodes, Communities und Schlüsselpfade für eine breite Architekturüberprüfung zusammen. Wie der Graph erstellt wird und was er enthält: **[Wie graphify funktioniert](https://docs.graphify.com/concepts/architecture)**.

---

## Welche Dateien es verarbeitet: ~40 languages

graphify parst ~40 Programmiersprachen lokal mit tree-sitter AST und bildet Dokumente, PDFs, Bilder und Audio/Video über einen optionalen semantischen Durchlauf ab. Vollständige Liste: **[Unterstützte Eingaben](https://docs.graphify.com/concepts/supported-inputs)**.

---

## Gängige Befehle

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

Siehe die [vollständige Befehlsreferenz](#full-command-reference) unten.

---

## Dateien ignorieren

graphify beachtet `.gitignore` und unterstützt `--exclude`-Muster sowie ein projektbezogenes `.graphifyignore`. Details: **[Konfiguration](https://docs.graphify.com/reference/configuration)**.


## Projektkonfiguration

Erstellen Sie eine `.graphifyrc` im Scan-Root für Einstellungen, die zum Projekt gehören statt zu einem einzelnen Lauf. Ein `key=value` pro Zeile; Zeilen, die mit `#` beginnen, sind Kommentare.

**Mehrdeutige Erweiterungen.** Manche Erweiterungen bedeuten in verschiedenen Projekten verschiedene Sprachen: `.inc` ist PHP in pfSense, Pascal in einem Delphi-Baum, SQL oder Assembler anderswo; `.h` ist C oder C++; `.m` ist Objective-C oder MATLAB. graphify muss einen globalen Standard wählen, und wenn es falsch wählt, schlägt die Datei nicht fehl: sie wird als falsche Sprache geparst und liefert eine Handvoll beiläufiger Knoten, sodass der Graph bevölkert aussieht, während die echten Symbole fehlen. Deklarieren Sie, was die Erweiterung in Ihrem Repo bedeutet:

```
# .graphifyrc
# A language name:
language.inc=php
# Or an extension graphify already knows:
language.tpl=.ts
# Baked into the git hooks (see Team setup):
viz_node_limit=0
```

Die Deklaration fließt durch Klassifizierung, Extraktor-Auswahl, Grammatik und Auflösung, Imports, `graphify watch` und den AST-Cache (eine unter einer anderen Sprache neu geparste Datei nutzt nie den alten Eintrag wieder), und dieselbe `.graphifyrc` wird von `extract`, `update`, den Hooks, dem MCP-Server und dem `/graphify`-Skill gelesen. Ein Tippfehler wird einmal auf stderr gemeldet, und der Scan läuft mit den Standardwerten weiter. Wie Deklarationen mit Caching, inkrementellen Neuerstellungen und Import-Auflösung zusammenwirken: **[Konfiguration](https://docs.graphify.com/reference/configuration)**.

---

## Team-Einrichtung

Committen oder teilen Sie den Graphen, damit Ihr ganzes Team denselben Kontext abfragt, und überprüfen Sie Pull Requests mit Graphenkontext. Siehe **[Kontext mit Ihrem Team teilen](https://docs.graphify.com/guides/team-workflows)** und **[Pull Requests überprüfen](https://docs.graphify.com/guides/pull-requests)**.

---

## Den Graphen direkt nutzen

Über Ihren KI-Assistenten hinaus können Sie `graph.json` direkt von der CLI aus mit `graphify query`, `graphify path` und `graphify explain` abfragen. Ein Name, der auf mehrere Knoten passt, wird mit aufgelisteten Kandidaten abgelehnt, statt geraten. Skripte können das Ergebnis aus dem Exit-Code lesen: `0` eine Antwort, `3` ein mehrdeutiger Name, `4` kein passender Knoten. Siehe **[Bessere Graphenfragen stellen](https://docs.graphify.com/guides/querying)** und die **[Query-Referenz](https://docs.graphify.com/reference/query)**.

---

## Umgebungsvariablen

Backends, API-Schlüssel, Hook-Verhalten und Feinabstimmung werden durch Umgebungsvariablen gesteuert. Vollständige Tabelle: **[Konfiguration](https://docs.graphify.com/reference/configuration)**.

---

## Datenschutz

- **Code-Dateien**: lokal via tree-sitter verarbeitet. Nichts verlässt Ihren Rechner. Ein reiner Code-Korpus benötigt keinen API-Schlüssel: `graphify extract` läuft vollständig offline. Fügen Sie bei einem gemischten Repo `--code-only` hinzu, um nur den Code zu indizieren und die Dokumente/PDFs/Bilder zu überspringen, die sonst ein LLM benötigen würden.
- **Video / Audio**: lokal mit faster-whisper transkribiert. Nichts verlässt Ihren Rechner.
- **Dokumente, PDFs, Bilder**: zur semantischen Extraktion an Ihren KI-Assistenten gesendet (über den `/graphify`-Skill, unter Nutzung des Modells, das Ihre IDE-Sitzung ausführt). Headless `graphify extract` benötigt `GEMINI_API_KEY` / `GOOGLE_API_KEY` (Gemini), `MOONSHOT_API_KEY` (Kimi), `ANTHROPIC_API_KEY` (Claude), `OPENAI_API_KEY` (OpenAI), `DEEPSEEK_API_KEY` (DeepSeek), eine laufende Ollama-Instanz (`OLLAMA_BASE_URL`), AWS-Anmeldedaten über die Standard-Provider-Kette (Bedrock - kein API-Schlüssel nötig, nutzt IAM) oder das `claude`-CLI-Binary (Claude Code - kein API-Schlüssel nötig, nutzt Ihr Claude-Abonnement). Das `--dedup-llm`-Flag nutzt denselben Schlüssel.
- **Datenresidenz**: `graphify extract` erkennt automatisch, welchen Provider es nutzt, basierend darauf, welcher API-Schlüssel gesetzt ist (Priorität: Gemini → Kimi → Claude → OpenAI → DeepSeek → Azure → Bedrock → Ollama). Für Code mit Datenresidenz-Anforderungen nutzen Sie `--backend ollama` (vollständig lokal) oder übergeben Sie ein explizites `--backend`-Flag. Kimi (`MOONSHOT_API_KEY`) leitet zu Moonshot-AI-Servern in China.
- **Keine Telemetrie**, kein Nutzungs-Tracking, keine Analytik.
- **Query-Logging**: jeder `graphify query`-, `graphify path`-, `graphify explain`- und MCP-`query_graph`-Aufruf wird im JSON-Lines-Format in `~/.cache/graphify-queries.log` geloggt (Zeitstempel, Frage, Korpus, zurückgegebene Knoten, Dauer). Vollständige Teilgraph-Antworten werden standardmäßig **nicht** gespeichert. Setzen Sie `GRAPHIFY_QUERY_LOG_DISABLE=1`, um sich abzumelden, oder `GRAPHIFY_QUERY_LOG=/dev/null`, um ohne Deaktivierung des Codepfads stumm zu schalten.

---

## Fehlerbehebung

Häufige Installations- und Extraktionsprobleme und ihre Lösungen: **[Fehlerbehebung](https://docs.graphify.com/troubleshooting)**.

---

## Vollständige Befehlsreferenz

Jeder Befehl und jedes Flag, mit Beispielen: **[CLI-Referenz](https://docs.graphify.com/reference/overview)**.

---

## Mehr erfahren

- [docs.graphify.com](https://docs.graphify.com): vollständige Dokumentation: Anleitungen, Befehlsreferenz und Integrationen
- [Wie es funktioniert](../how-it-works.md): die Extraktions-Pipeline, Community-Erkennung, Confidence-Scoring, Benchmarks
- [ARCHITECTURE.md](../../ARCHITECTURE.md): Modulaufteilung, wie man eine Sprache hinzufügt
- [Optionale Integrationen](../docker-mcp-sqlite.md): Docker MCP Toolkit + SQLite
- [The Memory Layer](https://safishamsi.gumroad.com/l/qetvlo): das Buch über die Ideen hinter graphify, die Architektur von Anfang bis Ende

---

## Graphify Cloud

[**Graphify Cloud**](https://app.graphify.com/login) ist die stets aktive Schicht, die auf graphify aufbaut. Statt eines Graphen, den Sie pro Ordner auf Abruf neu erstellen, hält es einen live-Graphen über Ihren gesamten Software-Entwicklungszyklus:

- **80% weniger Tokens**: stets aktives Gedächtnis bedeutet, dass Ihre Agenten die Codebasis nicht in jeder Sitzung neu lesen und neu erklären.
- **Monorepo und repo-übergreifend**: ein verbundener Graph über jeden Service und jedes Repository, nicht ein Graph pro Ordner.
- **Formale Verifikation**: prüfen Sie architektonische und Abhängigkeits-Invarianten gegen den live-Graphen.
- **Code-Review mit einer Vogelperspektive auf Ihren SDLC**: sehen Sie, wie sich eine Änderung durch das gesamte System auswirkt, bevor Sie mergen.
- **SDLC-Konnektoren**: ziehen Sie Sentry, Jira und mehr herein, sodass Vorfälle, Tickets und Code in einem Graphen leben.
- **Stets aktiv**: aktualisiert sich kontinuierlich im Hintergrund über Code, Dokumente und Meetings.

**[Starten Sie eine kostenlose 14-tägige Testphase unter app.graphify.com &rarr;](https://app.graphify.com/login)**

---

## Mitwirken

Beiträge sind willkommen. Siehe **[CONTRIBUTING.md](../../CONTRIBUTING.md)** für die Entwicklungseinrichtung, die Test- und CI-Paritätsbefehle, den Git-Workflow und was einen starken Beitrag ausmacht (durchgearbeitete Beispiele und Extraktions-Fehlerberichte sind am nützlichsten). Architektur und wie man eine Sprache hinzufügt: [ARCHITECTURE.md](../../ARCHITECTURE.md).

Neu hier? Sagen Sie Hallo auf [Discord](https://discord.gg/XDnKVpzdXB) oder in den [GitHub Discussions](https://github.com/Graphify-Labs/graphify/discussions).

---

## Mitwirkende

<a href="https://github.com/Graphify-Labs/graphify/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=Graphify-Labs/graphify" alt="graphify contributors" />
</a>

Erstellt mit [contrib.rocks](https://contrib.rocks).

---

## Übersetzungen

Die README ist in 32 Sprachen verfügbar. Nutzen Sie den Sprachumschalter am Anfang dieser Datei, um sie in Ihrer Sprache zu lesen, oder durchstöbern Sie [`docs/translations/`](./). Um eine Übersetzung zu verbessern oder eine neue hinzuzufügen, öffnen Sie einen Pull Request gegen die passende Datei dort.

---

## Auf graphify aufbauen

Bauen Sie etwas im graphify-Ökosystem? Das ist erwünscht. Wenn Ihr Projekt "graphify" in seinem Namen verwendet (zum Beispiel `graphify-dashboard` oder `graphify-action`), fügen Sie Ihrer README bitte einen kurzen Hinweis hinzu, der klarstellt, dass es community-erstellt und nicht mit Graphify Labs affiliiert oder von diesem unterstützt ist. "graphify" und das graphify-Logo sind Marken von Graphify Labs; bitte verwenden Sie sie nicht auf eine Weise, die einen offiziellen Status impliziert.

---

## Community und Links

<p align="center">
  <a href="https://graphify.com"><img src="https://img.shields.io/badge/Website-graphify.com-4c1?style=flat&logo=googlechrome&logoColor=white" alt="Website"/></a>
  <a href="https://discord.gg/XDnKVpzdXB"><img src="https://img.shields.io/badge/Discord-Join-5865F2?style=flat&logo=discord&logoColor=white" alt="Discord"/></a>
  <a href="https://x.com/graphify"><img src="https://img.shields.io/badge/X-graphify-000000?logo=x&logoColor=white" alt="X"/></a>
  <a href="https://www.youtube.com/@graphifylabs"><img src="https://img.shields.io/badge/YouTube-Graphify%20Labs-FF0000?style=flat&logo=youtube&logoColor=white" alt="YouTube"/></a>
  <a href="https://github.com/sponsors/safishamsi"><img src="https://img.shields.io/badge/sponsor-safishamsi-ea4aaa?logo=github-sponsors" alt="Sponsor"/></a>
  <a href="https://safishamsi.gumroad.com/l/qetvlo"><img src="https://img.shields.io/badge/Book-The%20Memory%20Layer-2ea44f?style=flat&logo=gitbook&logoColor=white" alt="The Memory Layer"/></a>
</p>
