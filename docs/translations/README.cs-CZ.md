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
  <b>Snižte spotřebu tokenů agentů o 80 %.</b> Graphify Cloud je vždy zapnutá paměť, která řídí vaše agenty, udržuje vysokou kvalitu kódu a dokazuje správnost pomocí formální verifikace. <a href="https://app.graphify.com/login"><b>Spusťte bezplatnou 14denní zkušební verzi &rarr;</b></a>
</p>

Napište `/graphify` ve svém AI programovacím asistentovi a ten zmapuje celý váš projekt (kód, dokumentaci, PDF, obrázky, videa) do **znalostního grafu**, který můžete **dotazovat namísto grepování** skrze soubory.

- **Mapování kódu zdarma, plně lokálně.** Kód se parsuje pomocí tree-sitter AST: deterministicky, bez LLM, nic neopouští váš počítač. (Dokumentace, PDF, obrázky a video využívají model vašeho asistenta nebo nakonfigurovaný API klíč pro sémantický průchod.)
- **Každá hrana je vysvětlena.** Každé spojení je označeno `EXTRACTED` (explicitní ve zdroji) nebo `INFERRED` (odvozené nástrojem graphify), takže poznáte, co bylo přečteno přímo, od toho, co bylo odvozeno.
- **Nejde o vektorový index.** Žádné embeddingy, žádné vektorové úložiště: skutečný graf, kterým procházíte. Položte otázku, vysledujte cestu mezi dvěma věcmi nebo vysvětlete jeden koncept.

> [!NOTE]
> **Chcete to mít vždy zapnuté?** [Graphify Cloud](https://app.graphify.com/login) udržuje graf živý napříč celým vaším SDLC: podpora monorepa i napříč repozitáři, formální verifikace a revize kódu s ptačím pohledem na váš SDLC, plus konektory pro Sentry, Jira a další, takže incidenty a tikety sedí ve stejném grafu jako váš kód. **[Spusťte bezplatnou 14denní zkušební verzi na app.graphify.com](https://app.graphify.com/login)**.

<p align="center">
  <img src="https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/graph-hero.png" alt="graphify's interactive graph.html showing the FastAPI codebase as a force-directed knowledge graph with a legend of detected communities" width="900">
</p>
<p align="center">
  <em>Kódová báze FastAPI zmapovaná nástrojem graphify. Každý uzel je koncept, barvy jsou detekované komunity a celek je klikatelný v graph.html.</em>
</p>

**Začínáme** (30 sekund). Vyžaduje Python 3.10+ a uv (nebo pipx):

```bash
uv tool install graphifyy      # install the CLI (or: pipx install graphifyy)
graphify install               # detects your assistant and registers the skill
```

Poté ve svém AI asistentovi:

```
/graphify .
```

A je to. Získáte **tři soubory**:

```
graphify-out/
├── graph.html       open in any browser: click nodes, filter, search
├── GRAPH_REPORT.md  the highlights: key concepts, surprising connections, suggested questions
└── graph.json       the full graph: query it anytime without re-reading your files
```

Uložený graf obsahuje `graph.schema_version`, aby integrace dokázaly detekovat
nekompatibilní změny formátu, plus `graph.graphify_version`, který identifikuje
vydání Graphify, jež jej vytvořilo.

**Jedna instalace, jakýkoli asistent, jakýkoli OS.** Claude Code, Cursor, Codex, Gemini CLI, GitHub Copilot a 20+ dalších, na macOS, Linux a Windows: [vyberte svou platformu](#install).

---

## Jak to vypadá v praxi

<p align="center">
  <img src="https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/demo-path.svg" alt="graphify path query: a terminal asks for the shortest path between FastAPI and ModelField, and the answer lights up hop by hop across the knowledge graph" width="900">
</p>

Jakmile je graf sestaven, dotazujete jej namísto čtení souborů. Skutečný výstup, graphify spuštěný na kódové bázi FastAPI zobrazené výše:

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

Každá hrana nese **značku spolehlivosti** (`EXTRACTED` = explicitní ve zdroji, `INFERRED` = odvozená rozlišením), takže poznáte, co bylo přečteno přímo, od toho, co bylo odvozeno. `graphify query "<question>"` vrací omezený podgraf pro otázku v běžném jazyce a `graphify path A B` vysleduje, jak se libovolné dvě věci propojují.

---

## Co to dělá

Co dostanete rovnou z krabice:

| Schopnost | Co získáte |
|---|---|
| **Boží uzly** | Nejvíce propojené koncepty, takže vidíte, čím vše protéká |
| **Komunity** | Graf rozdělený na podsystémy (Leiden), s popisky bez LLM |
| **Propojení napříč soubory** | `calls` / `imports` / `inherits` / `mixes_in` rozlišené napříč ~40 jazyky pomocí tree-sitter AST |
| **Query, path, explain** | Položte otázku, vysledujte cestu mezi dvěma věcmi nebo vysvětlete jeden koncept, vše proti `graph.json` |
| **Zdůvodnění + odkazy na dokumentaci** | Komentáře `# NOTE:` / `# WHY:` a citace ADR/RFC se stávají prvotřídními uzly propojenými s kódem |
| **Nad rámec kódu** | Dokumentace, PDF, obrázky a video/audio se vše mapuje do stejného grafu |
| **Lokální na prvním místě** | Kód se parsuje lokálně pomocí tree-sitter (bez LLM, nic neopouští váš počítač); pouze sémantický průchod přes dokumentaci/média volá backend, a to jen pokud nějaký nakonfigurujete |

> [!TIP]
> Spouštíte to napříč mnoha repozitáři nebo monorepem? [Graphify Cloud](https://app.graphify.com/login) to dělá nepřetržitě a snižuje spotřebu tokenů agentů o 80 %, s propojeními napříč repozitáři, revizí kódu v celém SDLC, formální verifikací a konektory Sentry/Jira. [Spusťte bezplatnou 14denní zkušební verzi &rarr;](https://app.graphify.com/login)

---

## Benchmarks: 0.497 recall@10, 0 LLM credits

| Benchmark | Metrika | graphify | Pole |
|---|---|---|---|
| LOCOMO (n=300) | recall@10 | **0.497** | mem0 0.048, supermemory 0.149 |
| LOCOMO (n=300) | přesnost QA | 45.3% | supermemory 49.7%, mem0 27.3% |
| LongMemEval-S (n=50) | přesnost QA | **76%** | shodně s dense RAG |
| ERPNext cross-tool (n=6) | pokrytí klíčových faktů | **82.0%** | základní linie grep/read 70.8% |
| Sestavení grafu | LLM kredity | **0** | za token u většiny systémů |

Každý systém běžel na stejném harnessu se stejným modelem a rozpočty, hodnocen porotcem naslepo validovaným proti druhému porotci (90.6% shoda, Cohenovo kappa 0.81). Úplné tabulky po jednotlivých systémech, výsledek kódové inteligence a příkazy pro reprodukci: **[BENCHMARKS.md](../../BENCHMARKS.md)**.

---

## Dokumentace

Úplné průvodce a reference najdete na **[docs.graphify.com](https://docs.graphify.com)**:

- **[Quickstart](https://docs.graphify.com/quickstart)**: sestavte svůj první graf
- **[CLI reference](https://docs.graphify.com/reference/overview)**: každý příkaz a přepínač
- **[Pokládejte lepší otázky grafu](https://docs.graphify.com/guides/querying)**: vzory dotazování
- **[Konfigurace](https://docs.graphify.com/reference/configuration)**: proměnné prostředí a ladění
- **[Podporované vstupy](https://docs.graphify.com/concepts/supported-inputs)**: jazyky a typy souborů
- **[Týmové workflow](https://docs.graphify.com/guides/team-workflows)** a **[Revize PR](https://docs.graphify.com/guides/pull-requests)**
- **[Řešení potíží](https://docs.graphify.com/troubleshooting)** a **[Jak to funguje](https://docs.graphify.com/concepts/architecture)**

---

## Předpoklady

| Požadavek | Minimum | Kontrola | Instalace |
|---|---|---|---|
| Python | 3.10+ | `python --version` | [python.org](https://www.python.org/downloads/) |
| uv *(doporučeno)* | jakékoli | `uv --version` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| pipx *(alternativa)* | jakékoli | `pipx --version` | `pip install pipx` |

**Rychlá instalace na macOS (Homebrew):**
```bash
brew install python@3.12 uv
```

**Rychlá instalace na Windows:**
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
> **Oficiální balíček:** Balíček na PyPI je `graphifyy` (dvě y). Ostatní balíčky `graphify*` na PyPI nejsou nijak spojené. Příkaz CLI je stále `graphify`.

Oficiální zdrojový repozitář je [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify).

Dvoupříkazový quickstart je na začátku tohoto README. Tato sekce pokrývá metody instalace, instalace omezené na projekt a každou podporovanou platformu.

**Metody instalace** (vyberte jednu):

```bash
uv tool install graphifyy   # recommended, isolated env (if 'graphify' isn't found after, run: uv tool update-shell)
pipx install graphifyy      # alternative
pip install graphifyy       # may need PATH setup, see Troubleshooting below
```

Poté jednou spusťte `graphify install`. Detekuje, kterého asistenta používáte, a zaregistruje skill, takže není nutná žádná konfigurace pro jednotlivé asistenty. Otevřete svého AI asistenta a napište `/graphify .`

Chcete-li nainstalovat asistentský skill do aktuálního repozitáře namísto vašeho uživatelského
profilu, přidejte `--project`:

```bash
graphify install --project
graphify install --project --platform codex
```

Instalace omezené na projekt zapisují do aktuálního adresáře, například
`.claude/skills/graphify/SKILL.md` nebo `.agents/skills/graphify/SKILL.md` (plus
sidecar `references/`, který skill načítá na vyžádání), a
vypíší nápovědu `git add` pro soubory, které lze commitnout.
Příkazy pro jednotlivé platformy, které podporují instalace omezené na projekt, přijímají stejný přepínač,
například `graphify claude install --project` nebo `graphify codex install --project`.

> [!TIP]
> Narážíte na `command not found`, problém s `pip` na Macu/Windows, uvozovkování v PowerShellu, použití `uvx`, zvláštnosti PATH u git hooků nebo strict mode? Viz **[Instalace](https://docs.graphify.com/installation)** a **[Řešení potíží](https://docs.graphify.com/troubleshooting)**.

<details>
<summary><b>Vyberte svou platformu</b> (20+ asistentů, klikněte pro rozbalení)</summary>

| Platforma | Instalační příkaz |
|----------|----------------|
| Claude Code (Linux/Mac) | `graphify install` |
| Claude Code (Windows) | `graphify install` (automaticky detekováno) nebo `graphify install --platform windows` |
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
| Agent Skills (napříč frameworky) | `graphify install --platform agents` (alias `--platform skills`) |
| Kiro IDE/CLI | `graphify kiro install` |
| Pi coding agent | `graphify install --platform pi`, plus `graphify pi guard install` pro nativní guard |
| Cursor | `graphify cursor install` |
| Devin CLI | `graphify devin install` |
| Google Antigravity | `graphify antigravity install` |

Uživatelé Codexu také potřebují `multi_agent = true` pod `[features]` v `~/.codex/config.toml` pro paralelní extrakci. CodeBuddy používá stejný mechanismus Agent tool a PreToolUse hook jako Claude Code. Factory Droid používá nástroj `Task` pro paralelní rozesílání subagentů. OpenClaw a Aider používají sekvenční extrakci (podpora paralelních agentů je na těchto platformách stále v rané fázi). Trae používá nástroj Agent pro paralelní rozesílání subagentů a **ne**podporuje hooky `PreToolUse`, takže AGENTS.md je vždy zapnutý mechanismus.

`--platform agents` (alias `--platform skills`) cílí na generické umístění [Agent-Skills](https://github.com/anthropics/skills) napříč frameworky: specifikací definované uživatelsky globální `~/.agents/skills/` (čtené pomocí `npx skills` a frameworky kompatibilními se specifikací) pro globální instalaci a `./.agents/skills/` pro projektovou (`--project`) instalaci. Holé `graphify install` zůstává záměrně pro jedinou platformu (Claude Code): pojmenovanou platformu `agents` použijte tehdy, když chcete, aby byl skill zjistitelný jakýmkoli frameworkem, který čte `.agents/skills`.

Pi nemá hook `PreToolUse`, takže `graphify pi guard install` registruje nativní rozšíření Pi (prostřednictvím vlastního `pi install <package directory>` od Pi), které spouští nainstalovaný `graphify hook-guard` před voláními `read`, `grep`, `find` a vyhledávacími `bash` voláními Pi. Rozhodnutí o čerstvém/zastaralém grafu a jednou-za-relaci odepření indexovaného čtení pomocí `GRAPHIFY_HOOK_STRICT=1` pocházejí ze stejné politiky, takže Pi odpovídá chování hooku Claude Code; navádění přichází jako steering zpráva `<system-reminder source="graphify">`. Vyžaduje Pi 0.58.4 nebo novější: starší verze nechaly steering zprávu přeskočit zbytek dávky paralelních volání nástrojů. Balíček se dodává uvnitř instalace Graphify, takže nainstalujte Graphify trvale (`uv tool install graphifyy` nebo `pipx install graphifyy`, nikoli `uvx`), po instalaci nebo upgradu restartujte Pi a odeberte jej pomocí `graphify pi guard uninstall`. Kontrolují se pouze lokální souborové cíle; hook potřebuje `graphify` na absolutní položce `PATH` mimo projekt, je omezen na dvousekundové volání s 256 KiB vstupu / 64 KiB výstupu a selhává bezpečně (fail open). Stejný balíček se také načítá v [Oh My Pi](https://github.com/can1357/oh-my-pi): `omp plugin install "$(graphify pi guard path)"`. Registrovaná cesta obsahuje verzi Pythonu a venv, takže po změně kterékoli z nich znovu spusťte `graphify pi guard install` a starou položku odeberte pomocí `pi remove <old path>`.

> Codex používá `$graphify` namísto `/graphify`.

</details>

<details>
<summary><b>Volitelná rozšíření</b> (nainstalujte jen to, co potřebujete)</summary>

| Rozšíření | Co přidává | Instalace |
|---|---|---|
| `pdf` | Extrakce PDF | `uv tool install "graphifyy[pdf]"` |
| `office` | Podpora `.docx` a `.xlsx` | `uv tool install "graphifyy[office]"` |
| `google` | Vykreslování Google Sheets | `uv tool install "graphifyy[google]"` |
| `video` | Transkripce videa/audia (faster-whisper + yt-dlp) | `uv tool install "graphifyy[video]"` |
| `mcp` | MCP stdio server | `uv tool install "graphifyy[mcp]"` |
| `neo4j` | Podpora pushe do Neo4j | `uv tool install "graphifyy[neo4j]"` |
| `falkordb` | Podpora pushe do FalkorDB | `uv tool install "graphifyy[falkordb]"` |
| `svg` | Export grafu do SVG | `uv tool install "graphifyy[svg]"` |
| `leiden` | Detekce komunit Leiden (graspologic na Pythonu < 3.13; nativní backend na 3.13+) | `uv tool install "graphifyy[leiden]"` |
| `ollama` | Lokální inference Ollama | `uv tool install "graphifyy[ollama]"` |
| `openai` | OpenAI / API kompatibilní s OpenAI | `uv tool install "graphifyy[openai]"` |
| `gemini` | Google Gemini API | `uv tool install "graphifyy[gemini]"` |
| `anthropic` | Anthropic Claude API (`--backend claude`, používá `ANTHROPIC_API_KEY`) | `uv tool install "graphifyy[anthropic]"` |
| `bedrock` | AWS Bedrock (používá IAM, bez API klíče) | `uv tool install "graphifyy[bedrock]"` |
| `azure` | Azure OpenAI Service (`--backend azure`, používá `AZURE_OPENAI_API_KEY` + `AZURE_OPENAI_ENDPOINT`) | `uv tool install "graphifyy[openai]"` |
| `sql` | Extrakce SQL schématu | `uv tool install "graphifyy[sql]"` |
| `postgres` | Živá introspekce PostgreSQL (`--postgres DSN`) | `uv tool install "graphifyy[postgres]"` |
| `dm` | Extrakce AST pro BYOND DreamMaker `.dm`/`.dme` (může vyžadovat C kompilátor + `python3-dev`, pokud žádný wheel neodpovídá vaší platformě) | `uv tool install "graphifyy[dm]"` |
| `terraform` | Extrakce AST pro Terraform / HCL `.tf`/`.tfvars`/`.hcl` | `uv tool install "graphifyy[terraform]"` |
| `pascal` | Extrakce AST pro Pascal / Delphi `.pas`/`.dpr`/`.dpk`/`.inc` (přesnější hrany `calls`/`inherits`; při nepřítomnosti se vrací k regexovému extraktoru) | `uv tool install "graphifyy[pascal]"` |
| `ocaml` | Extrakce AST pro OCaml `.ml`/`.mli` | `uv tool install "graphifyy[ocaml]"` |
| `commonlisp` | Extrakce AST pro Common Lisp `.lisp`/`.cl`/`.lsp`/`.asd` | `uv tool install "graphifyy[commonlisp]"` |
| `robot` | Extrakce Robot Framework `.robot`/`.resource` (suity, testovací případy, klíčová slova, hrany volání klíčových slov a importů resource/library) | `uv tool install "graphifyy[robot]"` |
| `chinese` | Segmentace čínských dotazů (jieba) | `uv tool install "graphifyy[chinese]"` |
| `all` | Vše výše uvedené | `uv tool install "graphifyy[all]"` |

</details>

---

## Přimějte svého asistenta vždy používat graf

Spusťte toto jednou ve svém projektu po sestavení grafu:

Spusťte `graphify <platform> install` jednou ve svém projektu, například `graphify claude install` nebo `graphify codex install` (nebo `graphify install --platform <name>`).

Toto zapíše malý konfigurační soubor, který řekne vašemu asistentovi, aby u otázek o kódové bázi konzultoval znalostní graf a dával přednost omezeným dotazům jako `graphify query "<question>"` před čtením celého reportu nebo grepováním surových souborů.

- **Platformy s hooky** (Claude Code, Gemini CLI): hook se spustí automaticky před voláními nástrojů vyhledávacího typu (a na Claude Code před čtením zdrojových souborů jeden po druhém pomocí nástrojů Read/Glob) a nasměruje vašeho asistenta k cestě přes graf.
- **Platformy s instrukčními soubory** (Codex, OpenCode, Cursor atd.): trvalé instrukční soubory (`AGENTS.md`, `.cursor/rules/` atd.) poskytují stejné navádění s předností dotazu.

`GRAPH_REPORT.md` je stále k dispozici pro širokou architektonickou revizi.

Přesně které soubory každá platforma zapisuje (CodeBuddy `CODEBUDDY.md` + hooky `PreToolUse`, Codex `AGENTS.md`, nativní plugin `.kilo` u Kilo, pravidlo `alwaysApply` u Cursoru a tak dále) je pokryto v **[Nastavení vždy zapnuto](https://docs.graphify.com/guides/always-on)**.

Chcete-li odebrat graphify ze všech platforem najednou: `graphify uninstall` (přidejte `--purge`, chcete-li také smazat `graphify-out/`). Nebo použijte příkaz pro jednotlivou platformu (např. `graphify claude uninstall`).

### CLI skills nebo MCP instrukce?

Instrukce instalované pomocí `graphify install` a ty dodávané s připojením Graphify MCP popisují různé způsoby, jak dotazovat graf:

| Nastavení | Pokyny k použití | Přístup k dotazům |
|---|---|---|
| Lokální CLI a nainstalovaný asistentský skill | Instrukce platformy zapsané pomocí `graphify install` | Spusťte `graphify query`, `graphify path` a `graphify explain` proti lokálnímu grafu (ve výchozím nastavení `graphify-out/`). |
| Připojený Graphify MCP server | Instrukce připojení a nástroje uvedené tímto serverem | Volejte uvedené MCP nástroje proti grafu obsluhovanému tímto připojením. Názvy a popisy nástrojů pocházejí ze serveru. |

Obojí podporuje omezené dotazy do grafu před širokým vyhledáváním ve zdroji. Vyberte instrukce, které odpovídají nástrojům, k nimž má váš asistent skutečně přístup; žádný z bloků nestanovuje univerzální pravidlo přednosti pro instrukční soubory vašeho asistenta. Pokud používáte obě integrace, zjistěte, který graf každá z nich dotazuje, a vyberte primární cestu dotazů namísto kopírování dvou nepodmíněných instrukčních bloků do `AGENTS.md`.

`graphify install` instaluje lokální asistentskou integraci; nenavazuje MCP připojení. MCP klient nepotřebuje spouštět lokální CLI dotazy, aby mohl používat svůj připojený server. Lokálně hostovaný server stále potřebuje vlastní instalaci Graphify a graf, zatímco hostované připojení může obsluhovat graf, který není přítomen v pracovním adresáři klienta. Pokud očekávané nástroje chybí, zkontrolujte příslušnou instalaci CLI nebo MCP připojení, místo abyste instrukce druhého nastavení považovali za zaměnitelné.

---

## Co je v reportu

`GRAPH_REPORT.md` shrnuje boží uzly, komunity a klíčové cesty pro širokou architektonickou revizi. Jak se graf sestavuje a co obsahuje: **[Jak graphify funguje](https://docs.graphify.com/concepts/architecture)**.

---

## Jaké soubory zpracovává: ~40 languages

graphify parsuje ~40 programovacích jazyků lokálně pomocí tree-sitter AST a mapuje dokumentaci, PDF, obrázky a audio/video prostřednictvím volitelného sémantického průchodu. Úplný seznam: **[Podporované vstupy](https://docs.graphify.com/concepts/supported-inputs)**.

---

## Běžné příkazy

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

Viz [úplná reference příkazů](#full-command-reference) níže.

---

## Ignorování souborů

graphify respektuje `.gitignore` a podporuje vzory `--exclude` a projektový `.graphifyignore`. Podrobnosti: **[Konfigurace](https://docs.graphify.com/reference/configuration)**.


## Konfigurace projektu

Vytvořte `.graphifyrc` v kořeni skenování pro nastavení, která patří projektu spíše než jednomu běhu. Jeden `key=value` na řádek; řádky začínající `#` jsou komentáře.

**Nejednoznačné přípony.** Některé přípony znamenají v různých projektech různé jazyky: `.inc` je PHP na pfSense, Pascal ve stromu Delphi, SQL nebo assembler jinde; `.h` je C nebo C++; `.m` je Objective-C nebo MATLAB. graphify musí zvolit jeden globální výchozí jazyk, a když zvolí špatně, soubor neselže: parsuje se jako špatný jazyk a vrací hrstku náhodných uzlů, takže graf vypadá zaplněný, zatímco skutečné symboly chybí. Deklarujte, co přípona ve vašem repozitáři znamená:

```
# .graphifyrc
# A language name:
language.inc=php
# Or an extension graphify already knows:
language.tpl=.ts
# Baked into the git hooks (see Team setup):
viz_node_limit=0
```

Deklarace prochází klasifikací, výběrem extraktoru, gramatikou a rozlišením, importy, `graphify watch` a AST cache (soubor znovu parsovaný pod jiným jazykem nikdy nepoužije starou položku) a stejný `.graphifyrc` čtou `extract`, `update`, hooky, MCP server a skill `/graphify`. Překlep je jednou nahlášen na stderr a sken pokračuje s výchozími hodnotami. Jak deklarace interagují s cachováním, inkrementálními rebuildy a rozlišením importů: **[Konfigurace](https://docs.graphify.com/reference/configuration)**.

---

## Týmové nastavení

Commitněte nebo sdílejte graf, aby celý váš tým dotazoval stejný kontext, a revidujte pull requesty s kontextem grafu. Viz **[Sdílejte kontext se svým týmem](https://docs.graphify.com/guides/team-workflows)** a **[Revidujte pull requesty](https://docs.graphify.com/guides/pull-requests)**.

---

## Používání grafu přímo

Kromě vašeho AI asistenta dotazujte `graph.json` přímo z CLI pomocí `graphify query`, `graphify path` a `graphify explain`. Název, který odpovídá více uzlům, je odmítnut s uvedenými kandidáty, místo aby byl uhodnut. Skripty mohou číst výsledek z návratového kódu: `0` odpověď, `3` nejednoznačný název, `4` žádný odpovídající uzel. Viz **[Pokládejte lepší otázky grafu](https://docs.graphify.com/guides/querying)** a **[reference dotazů](https://docs.graphify.com/reference/query)**.

---

## Proměnné prostředí

Backendy, API klíče, chování hooků a ladění se řídí proměnnými prostředí. Úplná tabulka: **[Konfigurace](https://docs.graphify.com/reference/configuration)**.

---

## Soukromí

- **Soubory s kódem**: zpracovány lokálně pomocí tree-sitter. Nic neopouští váš počítač. Korpus obsahující pouze kód nevyžaduje žádný API klíč: `graphify extract` běží plně offline. U smíšeného repozitáře přidejte `--code-only`, chcete-li indexovat jen kód a přeskočit dokumentaci/PDF/obrázky, které by jinak potřebovaly LLM.
- **Video / audio**: transkribováno lokálně pomocí faster-whisper. Nic neopouští váš počítač.
- **Dokumentace, PDF, obrázky**: odeslány vašemu AI asistentovi pro sémantickou extrakci (prostřednictvím skillu `/graphify`, s použitím jakéhokoli modelu, který běží ve vaší relaci IDE). Headless `graphify extract` vyžaduje `GEMINI_API_KEY` / `GOOGLE_API_KEY` (Gemini), `MOONSHOT_API_KEY` (Kimi), `ANTHROPIC_API_KEY` (Claude), `OPENAI_API_KEY` (OpenAI), `DEEPSEEK_API_KEY` (DeepSeek), běžící instanci Ollama (`OLLAMA_BASE_URL`), přihlašovací údaje AWS přes standardní řetězec poskytovatelů (Bedrock - není potřeba API klíč, používá IAM) nebo binárku CLI `claude` (Claude Code - není potřeba API klíč, používá vaše předplatné Claude). Přepínač `--dedup-llm` používá stejný klíč.
- **Rezidence dat**: `graphify extract` automaticky detekuje, kterého poskytovatele použít, podle toho, který API klíč je nastaven (priorita: Gemini → Kimi → Claude → OpenAI → DeepSeek → Azure → Bedrock → Ollama). U kódu s požadavky na rezidenci dat použijte `--backend ollama` (plně lokální) nebo předejte explicitní přepínač `--backend`. Kimi (`MOONSHOT_API_KEY`) směruje na servery Moonshot AI v Číně.
- **Žádná telemetrie**, žádné sledování využití, žádná analytika.
- **Logování dotazů**: každé volání `graphify query`, `graphify path`, `graphify explain` a MCP `query_graph` je logováno do `~/.cache/graphify-queries.log` ve formátu JSON Lines (časová značka, otázka, korpus, vrácené uzly, doba trvání). Úplné odpovědi podgrafu ve výchozím nastavení **ne**jsou ukládány. Nastavte `GRAPHIFY_QUERY_LOG_DISABLE=1` pro opt-out nebo `GRAPHIFY_QUERY_LOG=/dev/null` pro ztišení bez vypnutí kódové cesty.

---

## Řešení potíží

Běžné problémy s instalací a extrakcí a jejich řešení: **[Řešení potíží](https://docs.graphify.com/troubleshooting)**.

---

## Úplná reference příkazů

Každý příkaz a přepínač, s příklady: **[CLI reference](https://docs.graphify.com/reference/overview)**.

---

## Dozvědět se více

- [docs.graphify.com](https://docs.graphify.com): úplná dokumentace: průvodci, reference příkazů a integrace
- [Jak to funguje](../how-it-works.md): extrakční pipeline, detekce komunit, skórování spolehlivosti, benchmarky
- [ARCHITECTURE.md](../../ARCHITECTURE.md): rozpis modulů, jak přidat jazyk
- [Volitelné integrace](../docker-mcp-sqlite.md): Docker MCP Toolkit + SQLite
- [The Memory Layer](https://safishamsi.gumroad.com/l/qetvlo): kniha o myšlenkách stojících za graphify, architektura od začátku do konce

---

## Graphify Cloud

[**Graphify Cloud**](https://app.graphify.com/login) je vždy zapnutá vrstva postavená nad graphify. Namísto grafu, který na vyžádání znovu sestavujete pro jednotlivé složky, udržuje jeden živý graf napříč celým životním cyklem vývoje softwaru:

- **O 80 % méně tokenů**: vždy zapnutá paměť znamená, že vaši agenti přestanou v každé relaci znovu číst a znovu vysvětlovat kódovou bázi.
- **Monorepo a napříč repozitáři**: jeden propojený graf napříč každou službou a repozitářem, nikoli graf pro každou složku.
- **Formální verifikace**: kontrolujte architektonické a závislostní invarianty proti živému grafu.
- **Revize kódu s ptačím pohledem na váš SDLC**: uvidíte, jak se změna šíří napříč celým systémem, ještě než ji mergnete.
- **SDLC konektory**: zapojte Sentry, Jira a další, aby incidenty, tikety a kód žily v jednom grafu.
- **Vždy zapnuto**: nepřetržitě se aktualizuje na pozadí napříč kódem, dokumentací a schůzkami.

**[Spusťte bezplatnou 14denní zkušební verzi na app.graphify.com &rarr;](https://app.graphify.com/login)**

---

## Přispívání

Příspěvky jsou vítány. Viz **[CONTRIBUTING.md](../../CONTRIBUTING.md)** pro vývojové nastavení, příkazy pro testy a paritu s CI, git workflow a to, co dělá silný příspěvek (vypracované příklady a hlášení chyb extrakce jsou nejužitečnější). Architektura a jak přidat jazyk: [ARCHITECTURE.md](../../ARCHITECTURE.md).

Jste tu noví? Pozdravte nás na [Discordu](https://discord.gg/XDnKVpzdXB) nebo v [GitHub Discussions](https://github.com/Graphify-Labs/graphify/discussions).

---

## Přispěvatelé

<a href="https://github.com/Graphify-Labs/graphify/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=Graphify-Labs/graphify" alt="graphify contributors" />
</a>

Vytvořeno pomocí [contrib.rocks](https://contrib.rocks).

---

## Překlady

README je k dispozici v 32 jazycích. Použijte přepínač jazyků v horní části tohoto souboru pro čtení ve svém jazyce, nebo procházejte [`docs/translations/`](./). Chcete-li vylepšit překlad nebo přidat nový, otevřete pull request proti odpovídajícímu souboru tam.

---

## Stavění na graphify

Stavíte něco v ekosystému graphify? To je podporováno. Pokud váš projekt používá "graphify" ve svém názvu (například `graphify-dashboard` nebo `graphify-action`), přidejte prosím do svého README krátkou poznámku objasňující, že jde o projekt vytvořený komunitou, který není spojen s Graphify Labs ani jimi schválen. "graphify" a logo graphify jsou značky Graphify Labs; nepoužívejte je prosím způsobem, který naznačuje oficiální status.

---

## Komunita a odkazy

<p align="center">
  <a href="https://graphify.com"><img src="https://img.shields.io/badge/Website-graphify.com-4c1?style=flat&logo=googlechrome&logoColor=white" alt="Website"/></a>
  <a href="https://discord.gg/XDnKVpzdXB"><img src="https://img.shields.io/badge/Discord-Join-5865F2?style=flat&logo=discord&logoColor=white" alt="Discord"/></a>
  <a href="https://x.com/graphify"><img src="https://img.shields.io/badge/X-graphify-000000?logo=x&logoColor=white" alt="X"/></a>
  <a href="https://www.youtube.com/@graphifylabs"><img src="https://img.shields.io/badge/YouTube-Graphify%20Labs-FF0000?style=flat&logo=youtube&logoColor=white" alt="YouTube"/></a>
  <a href="https://github.com/sponsors/safishamsi"><img src="https://img.shields.io/badge/sponsor-safishamsi-ea4aaa?logo=github-sponsors" alt="Sponsor"/></a>
  <a href="https://safishamsi.gumroad.com/l/qetvlo"><img src="https://img.shields.io/badge/Book-The%20Memory%20Layer-2ea44f?style=flat&logo=gitbook&logoColor=white" alt="The Memory Layer"/></a>
</p>
