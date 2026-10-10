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
  <b>Vähennä agenttien tokenkulutusta 80%.</b> Graphify Cloud on aina päällä oleva muisti, joka ohjaa agenttejasi, pitää koodin laadun korkeana ja todistaa oikeellisuuden formaalilla verifioinnilla. <a href="https://app.graphify.com/login"><b>Aloita ilmainen 14 päivän kokeilu &rarr;</b></a>
</p>

Kirjoita `/graphify` AI-koodausavustajaasi, niin se kartoittaa koko projektisi (koodi, dokumentit, PDF-tiedostot, kuvat, videot) **tietograafiksi**, jota voit **kysellä sen sijaan, että greppaisit** tiedostoja läpi.

- **Koodi kartoittuu ilmaiseksi, täysin paikallisesti.** Koodi jäsennetään tree-sitter AST:llä: deterministisesti, ei LLM:ää, mikään ei poistu koneeltasi. (Dokumentit, PDF-tiedostot, kuvat ja video käyttävät avustajasi mallia tai määritettyä API-avainta semanttiseen käsittelyyn.)
- **Jokainen kaari selitetään.** Jokainen yhteys merkitään `EXTRACTED` (selkeä lähteessä) tai `INFERRED` (graphifyn päättelemä), joten voit erottaa suoraan luetun päätellystä.
- **Ei vektori-indeksi.** Ei embeddingejä, ei vektorivarastoa: oikea graafi, jota läpikäyt. Esitä kysymys, jäljitä polku kahden asian välillä tai selitä yksi käsite.

> [!NOTE]
> **Haluatko tämän aina päälle?** [Graphify Cloud](https://app.graphify.com/login) pitää graafin elävänä koko SDLC:n läpi: monorepo- ja repojen välinen tuki, formaali verifiointi ja koodikatselmointi lintuperspektiivistä koko SDLC:ääsi, sekä liittimet Sentryyn, Jiraan ja muihin, niin että häiriöt ja tiketit ovat samassa graafissa kuin koodisi. **[Aloita ilmainen 14 päivän kokeilu osoitteessa app.graphify.com](https://app.graphify.com/login)**.

<p align="center">
  <img src="https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/graph-hero.png" alt="graphify's interactive graph.html showing the FastAPI codebase as a force-directed knowledge graph with a legend of detected communities" width="900">
</p>
<p align="center">
  <em>FastAPI-koodikanta graphifyn kartoittamana. Jokainen solmu on käsite, värit ovat havaittuja yhteisöjä, ja koko juttu on klikattavissa tiedostossa graph.html.</em>
</p>

**Pääse alkuun** (30 sekuntia):

```bash
uv tool install graphifyy      # install the CLI (or: pipx install graphifyy)
graphify install               # register the skill with your AI assistant
```

Sitten AI-avustajassasi:

```
/graphify .
```

Siinä kaikki. Saat **kolme tiedostoa**:

```
graphify-out/
├── graph.html       open in any browser — click nodes, filter, search
├── GRAPH_REPORT.md  the highlights: key concepts, surprising connections, suggested questions
└── graph.json       the full graph — query it anytime without re-reading your files
```

Tallennettu graafi sisältää `graph.schema_version`-tiedon, jotta integraatiot voivat havaita
yhteensopimattomat formaattimuutokset, sekä `graph.graphify_version`-tiedon, joka yksilöi sen
Graphify-julkaisun, joka sen tuotti.

**Toimii työkaluissa** Claude Code, Cursor, Codex, Gemini CLI, GitHub Copilot ja 15+ muuta — [valitse alustasi](#install).

---

## Dokumentaatio

Täydelliset oppaat ja viite löytyvät osoitteesta **[docs.graphify.com](https://docs.graphify.com)**:

- **[Pikaopas](https://docs.graphify.com/quickstart)** — rakenna ensimmäinen graafisi
- **[CLI-viite](https://docs.graphify.com/reference/overview)** — jokainen komento ja lippu
- **[Esitä parempia graafikysymyksiä](https://docs.graphify.com/guides/querying)** — kyselymallit
- **[Konfiguraatio](https://docs.graphify.com/reference/configuration)** — ympäristömuuttujat ja viritys
- **[Tuetut syötteet](https://docs.graphify.com/concepts/supported-inputs)** — kielet ja tiedostotyypit
- **[Tiimin työnkulut](https://docs.graphify.com/guides/team-workflows)** ja **[PR-katselmointi](https://docs.graphify.com/guides/pull-requests)**
- **[Vianetsintä](https://docs.graphify.com/troubleshooting)** ja **[Miten se toimii](https://docs.graphify.com/concepts/architecture)**

---

## Katso se toiminnassa

<p align="center">
  <img src="https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/demo-path.svg" alt="graphify path query: a terminal asks for the shortest path between FastAPI and ModelField, and the answer lights up hop by hop across the knowledge graph" width="900">
</p>

Kun graafi on rakennettu, kyselet sitä sen sijaan, että lukisit tiedostoja. Oikeaa tulostetta, graphify ajettuna yllä näytetyllä FastAPI-koodikannalla:

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

Jokainen kaari kantaa **luottamusmerkintää** (`EXTRACTED` = selkeä lähteessä, `INFERRED` = johdettu resoluutiolla), joten voit erottaa suoraan luetun päätellystä. `graphify query "<question>"` palauttaa rajatun aligraafin selkokieliseen kysymykseen, ja `graphify path A B` jäljittää, miten kaksi asiaa liittyvät toisiinsa.

---

## Mitä se tekee

Mitä saat suoraan laatikosta:

| Ominaisuus | Mitä saat |
|---|---|
| **Jumalsolmut** | Eniten yhteyksiä omaavat käsitteet, niin että näet, minkä läpi kaikki virtaa |
| **Yhteisöt** | Graafi jaettuna alijärjestelmiin (Leiden), LLM-vapailla etiketeillä |
| **Tiedostojen väliset linkit** | `calls` / `imports` / `inherits` / `mixes_in` ratkaistuna ~40 kielen yli tree-sitter AST:llä |
| **Query, path, explain** | Esitä kysymys, jäljitä polku kahden asian välillä tai selitä yksi käsite, kaikki `graph.json`-tiedostoa vasten |
| **Perustelut + dokumenttiviittaukset** | `# NOTE:` / `# WHY:` -kommentit ja ADR/RFC-viittaukset muuttuvat ensiluokkaisiksi solmuiksi, jotka on linkitetty koodiin |
| **Koodin yli** | Dokumentit, PDF-tiedostot, kuvat ja video/ääni kartoittuvat kaikki samaan graafiin |
| **Paikallinen ensin** | Koodi jäsennetään paikallisesti tree-sitterillä (ei LLM:ää, mikään ei poistu koneeltasi); vain dokumenttien/median semanttinen käsittely kutsuu taustajärjestelmää, ja vain jos määrität sellaisen |

> [!TIP]
> Ajatko tätä useiden repojen tai monorepon yli? [Graphify Cloud](https://app.graphify.com/login) tekee sen jatkuvasti ja leikkaa agenttien tokenkulutusta 80%, repojen välisillä linkeillä, koko SDLC:n kattavalla koodikatselmoinnilla, formaalilla verifioinnilla ja Sentry/Jira-liittimillä. [Aloita ilmainen 14 päivän kokeilu &rarr;](https://app.graphify.com/login)

---

## Benchmarks

| Benchmark | Mittari | graphify | Vertailukenttä |
|---|---|---|---|
| LOCOMO (n=300) | recall@10 | **0.497** | mem0 0.048, supermemory 0.149 |
| LOCOMO (n=300) | QA-tarkkuus | 45.3% | supermemory 49.7%, mem0 27.3% |
| LongMemEval-S (n=50) | QA-tarkkuus | **76%** | tasoissa tiheän RAG:n kanssa |
| ERPNext työkalujen välinen (n=6) | avaintietojen kattavuus | **82.0%** | grep/read-perustaso 70.8% |
| Graafin rakennus | LLM-krediitit | **0** | per token useimmille järjestelmille |

Jokainen järjestelmä ajettiin samassa testialustassa samalla mallilla ja budjeteilla, ja sen arvioi tuomari, joka oli sokkovalidoitu toista tuomaria vasten (90.6% yksimielisyys, Cohenin kappa 0.81). Täydelliset järjestelmäkohtaiset taulukot, koodiälykkyyden tulos ja toistokomennot: **[BENCHMARKS.md](../../BENCHMARKS.md)**.

---

## Edellytykset

| Vaatimus | Vähimmäis | Tarkista | Asenna |
|---|---|---|---|
| Python | 3.10+ | `python --version` | [python.org](https://www.python.org/downloads/) |
| uv *(suositeltu)* | mikä tahansa | `uv --version` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| pipx *(vaihtoehto)* | mikä tahansa | `pipx --version` | `pip install pipx` |

**macOS pika-asennus (Homebrew):**
```bash
brew install python@3.12 uv
```

**Windows pika-asennus:**
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
> **Virallinen paketti:** PyPI-paketti on `graphifyy` (kaksois-y). Muut `graphify*`-paketit PyPI:ssä eivät ole sidoksissa. CLI-komento on edelleen `graphify`.

Virallinen lähdekoodirepositorio on [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify).

**Vaihe 1 — asenna paketti:**

```bash
# Recommended (isolated env; if 'graphify' isn't found after, run: uv tool update-shell):
uv tool install graphifyy

# Alternatives:
pipx install graphifyy
pip install graphifyy  # may need PATH setup — see note below
```

**Vaihe 2 — rekisteröi taito AI-avustajallesi:**

```bash
graphify install
```

Siinä kaikki. Avaa AI-avustajasi ja kirjoita `/graphify .`

Asentaaksesi avustajataidon nykyiseen repositorioon käyttäjäprofiilisi sijaan,
lisää `--project`:

```bash
graphify install --project
graphify install --project --platform codex
```

Projektikohtaiset asennukset kirjoittuvat nykyisen hakemiston alle, esimerkiksi
`.claude/skills/graphify/SKILL.md` tai `.agents/skills/graphify/SKILL.md` (sekä
`references/`-sivutiedosto, jonka taito lataa tarvittaessa), ja
tulostavat `git add` -vihjeen tiedostoille, jotka voidaan committaa.
Alustakohtaiset komennot, jotka tukevat projektikohtaisia asennuksia, hyväksyvät saman lipun,
esimerkiksi `graphify claude install --project` tai `graphify codex install --project`.

> [!TIP]
> Törmäätkö `command not found`-virheeseen, `pip`-ongelmaan Macilla/Windowsilla, PowerShell-lainausmerkkeihin, `uvx`-käyttöön, git-hookien PATH-erikoisuuksiin tai strict-tilaan? Katso **[Asennus](https://docs.graphify.com/installation)** ja **[Vianetsintä](https://docs.graphify.com/troubleshooting)**.

<details>
<summary><b>Valitse alustasi</b> (20+ avustajaa, laajenna klikkaamalla)</summary>

| Alusta | Asennuskomento |
|----------|----------------|
| Claude Code (Linux/Mac) | `graphify install` |
| Claude Code (Windows) | `graphify install` (tunnistetaan automaattisesti) tai `graphify install --platform windows` |
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
| Agent Skills (kehysten välinen) | `graphify install --platform agents` (alias `--platform skills`) |
| Kiro IDE/CLI | `graphify kiro install` |
| Pi coding agent | `graphify install --platform pi` |
| Cursor | `graphify cursor install` |
| Devin CLI | `graphify devin install` |
| Google Antigravity | `graphify antigravity install` |

Codex-käyttäjät tarvitsevat myös `multi_agent = true` kohdan `[features]` alle tiedostossa `~/.codex/config.toml` rinnakkaista ekstraktiota varten. CodeBuddy käyttää samaa Agent-työkalua ja PreToolUse-hookmekanismia kuin Claude Code. Factory Droid käyttää `Task`-työkalua rinnakkaiseen aliagenttien lähetykseen. OpenClaw ja Aider käyttävät peräkkäistä ekstraktiota (rinnakkaisten agenttien tuki on vielä varhaisessa vaiheessa näillä alustoilla). Trae käyttää Agent-työkalua rinnakkaiseen aliagenttien lähetykseen eikä tue `PreToolUse`-hookeja, joten AGENTS.md on aina päällä oleva mekanismi.

`--platform agents` (alias `--platform skills`) kohdistuu geneerisiin kehysten välisiin [Agent-Skills](https://github.com/anthropics/skills)-sijainteihin: spesifikaation käyttäjäglobaali `~/.agents/skills/` (jonka lukevat `npx skills` ja spesifikaation mukaiset kehykset) globaaliin asennukseen, ja `./.agents/skills/` projektiasennukseen (`--project`). Pelkkä `graphify install` pysyy yksialustaisena (Claude Code) tarkoituksella — käytä nimettyä `agents`-alustaa, kun haluat taidon olevan minkä tahansa `.agents/skills`-polun lukevan kehyksen löydettävissä.

> Codex käyttää `$graphify` komennon `/graphify` sijaan.

</details>

<details>
<summary><b>Valinnaiset lisäosat</b> (asenna vain se, mitä tarvitset)</summary>

| Lisäosa | Mitä se lisää | Asenna |
|---|---|---|
| `pdf` | PDF-ekstraktio | `uv tool install "graphifyy[pdf]"` |
| `office` | `.docx`- ja `.xlsx`-tuki | `uv tool install "graphifyy[office]"` |
| `google` | Google Sheetsin renderöinti | `uv tool install "graphifyy[google]"` |
| `video` | Videon/äänen litterointi (faster-whisper + yt-dlp) | `uv tool install "graphifyy[video]"` |
| `mcp` | MCP stdio-palvelin | `uv tool install "graphifyy[mcp]"` |
| `neo4j` | Neo4j-push-tuki | `uv tool install "graphifyy[neo4j]"` |
| `falkordb` | FalkorDB-push-tuki | `uv tool install "graphifyy[falkordb]"` |
| `svg` | SVG-graafin vienti | `uv tool install "graphifyy[svg]"` |
| `leiden` | Leiden-yhteisöjen havaitseminen (graspologic Pythonilla < 3.13; natiivi taustajärjestelmä versiossa 3.13+) | `uv tool install "graphifyy[leiden]"` |
| `ollama` | Ollama-paikallinen päättely | `uv tool install "graphifyy[ollama]"` |
| `openai` | OpenAI / OpenAI-yhteensopivat API:t | `uv tool install "graphifyy[openai]"` |
| `gemini` | Google Gemini API | `uv tool install "graphifyy[gemini]"` |
| `anthropic` | Anthropic Claude API (`--backend claude`, käyttää `ANTHROPIC_API_KEY`) | `uv tool install "graphifyy[anthropic]"` |
| `bedrock` | AWS Bedrock (käyttää IAM:ia, ei API-avainta) | `uv tool install "graphifyy[bedrock]"` |
| `azure` | Azure OpenAI Service (`--backend azure`, käyttää `AZURE_OPENAI_API_KEY` + `AZURE_OPENAI_ENDPOINT`) | `uv tool install "graphifyy[openai]"` |
| `sql` | SQL-skeeman ekstraktio | `uv tool install "graphifyy[sql]"` |
| `postgres` | Live-PostgreSQL-introspektio (`--postgres DSN`) | `uv tool install "graphifyy[postgres]"` |
| `dm` | BYOND DreamMaker `.dm`/`.dme` AST-ekstraktio (voi tarvita C-kääntäjän + `python3-dev`, jos mikään wheel ei vastaa alustaasi) | `uv tool install "graphifyy[dm]"` |
| `terraform` | Terraform / HCL `.tf`/`.tfvars`/`.hcl` AST-ekstraktio | `uv tool install "graphifyy[terraform]"` |
| `pascal` | Pascal / Delphi `.pas`/`.dpr`/`.dpk`/`.inc` AST-ekstraktio (tarkempia `calls`/`inherits`-kaaria; palaa regex-ekstraktoriin, kun puuttuu) | `uv tool install "graphifyy[pascal]"` |
| `ocaml` | OCaml `.ml`/`.mli` AST-ekstraktio | `uv tool install "graphifyy[ocaml]"` |
| `commonlisp` | Common Lisp `.lisp`/`.cl`/`.lsp`/`.asd` AST-ekstraktio | `uv tool install "graphifyy[commonlisp]"` |
| `robot` | Robot Framework `.robot`/`.resource`-ekstraktio (sarjat, testitapaukset, avainsanat, avainsanakutsut sekä resurssi-/kirjastotuontien kaaret) | `uv tool install "graphifyy[robot]"` |
| `chinese` | Kiinalaisen kyselyn segmentointi (jieba) | `uv tool install "graphifyy[chinese]"` |
| `all` | Kaikki yllä oleva | `uv tool install "graphifyy[all]"` |

</details>

---

## Saa avustajasi käyttämään aina graafia

Aja tämä kerran projektissasi graafin rakentamisen jälkeen:

Aja `graphify <platform> install` kerran projektissasi, esimerkiksi `graphify claude install` tai `graphify codex install` (tai `graphify install --platform <name>`).

Tämä kirjoittaa pienen konfiguraatiotiedoston, joka kehottaa avustajaasi konsultoimaan tietograafia koodikantakysymyksissä ja suosimaan rajattuja kyselyitä kuten `graphify query "<question>"` koko raportin lukemisen tai raakatiedostojen greppaamisen sijaan.

- **Hook-alustat** (Claude Code, Gemini CLI): hook laukeaa automaattisesti ennen hakutyylisiä työkalukutsuja (ja, Claude Codessa, ennen kuin lähdetiedostoja luetaan yksi kerrallaan Read/Glob-työkaluilla) ja ohjaa avustajaasi graafipolulle.
- **Ohjetiedostoalustat** (Codex, OpenCode, Cursor jne.): pysyvät ohjetiedostot (`AGENTS.md`, `.cursor/rules/` jne.) tarjoavat saman kysely-ensin-ohjauksen.

`GRAPH_REPORT.md` on edelleen käytettävissä laajaan arkkitehtuurikatselmointiin.

**CodeBuddy** tekee samat kaksi asiaa kuin Claude Code: kirjoittaa `CODEBUDDY.md`-osion, joka kehottaa CodeBuddyä lukemaan `graphify-out/GRAPH_REPORT.md` ennen arkkitehtuurikysymyksiin vastaamista, ja asentaa `PreToolUse`-hookit (`.codebuddy/settings.json`), jotka laukeavat ennen Bash-hakukomentoja ja tiedostojen lukuja ja ohjaavat sen sijaan kohti `graphify query`-komentoa.

**Codex** kirjoittaa tiedostoon `AGENTS.md`, joka on se, mikä tällä alustalla itse asiassa kantaa aina päällä olevan graafiohjauksen. `graphify codex install` rekisteröi myös `PreToolUse`-hookin tiedostoon `.codex/hooks.json` (`graphify hook-check`), mutta tämä merkintä on tarkoituksella **no-op**: Codex Desktop hylkää `hookSpecificOutput.additionalContext`-arvon kohdassa `PreToolUse`, joten ohjauksen lähettäminen siellä rikkoisi Bash-työkalukutsut. Toisin kuin Claude Codessa, jossa hook (`graphify hook-guard`) tekee ohjauksen, Codexissa hook laukeaa ja ei tarkoituksella tee mitään, ja `AGENTS.md` on aina päällä oleva mekanismi.

**Kilo Code** asentaa Graphify-taidon polkuun `~/.config/kilo/skills/graphify/SKILL.md` ja natiivin `/graphify`-komennon polkuun `~/.config/kilo/command/graphify.md`. `graphify kilo install` kirjoittaa myös `AGENTS.md`-tiedoston sekä natiivin `tool.execute.before`-liitännäisen (`.kilo/plugins/graphify.js` + rekisteröinti tiedostoon `.kilo/kilo.json` tai `.kilo/kilo.jsonc`), niin että Kilo saa saman aina päällä olevan graafimuistutuskäyttäytymisen natiivin `.kilo`-konfiguraation kautta.

**Cursor** kirjoittaa tiedoston `.cursor/rules/graphify.mdc` asetuksella `alwaysApply: true`, joten Cursor sisällyttää sen jokaiseen keskusteluun automaattisesti, hookia ei tarvita.

Poistaaksesi graphifyn kaikilta alustoilta kerralla: `graphify uninstall` (lisää `--purge` poistaaksesi myös `graphify-out/`). Tai käytä alustakohtaista komentoa (esim. `graphify claude uninstall`).

---

## Mitä raportissa on

`GRAPH_REPORT.md` tiivistää jumalsolmut, yhteisöt ja keskeiset polut laajaan arkkitehtuurikatselmointiin. Miten graafi rakennetaan ja mitä se sisältää: **[Miten graphify toimii](https://docs.graphify.com/concepts/architecture)**.

---

## Mitä tiedostoja se käsittelee

graphify jäsentää ~40 ohjelmointikieltä paikallisesti tree-sitter AST:llä, ja kartoittaa dokumentit, PDF-tiedostot, kuvat sekä äänen/videon valinnaisen semanttisen käsittelyn kautta. Täysi lista: **[Tuetut syötteet](https://docs.graphify.com/concepts/supported-inputs)**.

---

## Yleiset komennot

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

Katso [täydellinen komentoviite](#full-command-reference) alta.

---

## Tiedostojen ohittaminen

graphify kunnioittaa `.gitignore`-tiedostoa ja tukee `--exclude`-malleja sekä projektikohtaista `.graphifyignore`-tiedostoa. Lisätietoja: **[Konfiguraatio](https://docs.graphify.com/reference/configuration)**.

---

## Tiimin asetukset

Committaa tai jaa graafi, niin koko tiimisi kyselee samaa kontekstia, ja katselmoi pull requestit graafikontekstin kanssa. Katso **[Jaa konteksti tiimisi kanssa](https://docs.graphify.com/guides/team-workflows)** ja **[Katselmoi pull requestit](https://docs.graphify.com/guides/pull-requests)**.

---

## Graafin käyttö suoraan

AI-avustajasi lisäksi voit kysellä `graph.json`-tiedostoa suoraan CLI:stä komennoilla `graphify query`, `graphify path` ja `graphify explain`. Katso **[Esitä parempia graafikysymyksiä](https://docs.graphify.com/guides/querying)** ja **[kyselyviite](https://docs.graphify.com/reference/query)**.

---

## Ympäristömuuttujat

Taustajärjestelmiä, API-avaimia, hook-käyttäytymistä ja viritystä ohjataan ympäristömuuttujilla. Täysi taulukko: **[Konfiguraatio](https://docs.graphify.com/reference/configuration)**.

---

## Yksityisyys

- **Koodtiedostot** — käsitellään paikallisesti tree-sitterin kautta. Mikään ei poistu koneeltasi. Pelkkää koodia sisältävä korpus ei vaadi API-avainta — `graphify extract` toimii täysin offline-tilassa. Sekarepossa lisää `--code-only` indeksoidaksesi vain koodin ja ohittaaksesi dokumentit/PDF-tiedostot/kuvat, jotka muuten tarvitsisivat LLM:ää.
- **Video / ääni** — litteroidaan paikallisesti faster-whisperillä. Mikään ei poistu koneeltasi.
- **Dokumentit, PDF-tiedostot, kuvat** — lähetetään AI-avustajallesi semanttiseen ekstraktioon (`/graphify`-taidon kautta, käyttäen mallia, jota IDE-istuntosi ajaa). Headless `graphify extract` vaatii `GEMINI_API_KEY` / `GOOGLE_API_KEY` (Gemini), `MOONSHOT_API_KEY` (Kimi), `ANTHROPIC_API_KEY` (Claude), `OPENAI_API_KEY` (OpenAI), `DEEPSEEK_API_KEY` (DeepSeek), käynnissä olevan Ollama-instanssin (`OLLAMA_BASE_URL`), AWS-tunnistetiedot vakiomuotoisen tarjoajaketjun kautta (Bedrock – ei API-avainta tarvita, käyttää IAM:ia), tai `claude`-CLI-binäärin (Claude Code – ei API-avainta tarvita, käyttää Claude-tilaustasi). `--dedup-llm`-lippu käyttää samaa avainta.
- **Datan sijainti** — `graphify extract` tunnistaa automaattisesti, mitä tarjoajaa käyttää sen perusteella, mikä API-avain on asetettu (prioriteetti: Gemini → Kimi → Claude → OpenAI → DeepSeek → Azure → Bedrock → Ollama). Koodille, jolla on datan sijaintivaatimuksia, käytä `--backend ollama` (täysin paikallinen) tai anna eksplisiittinen `--backend`-lippu. Kimi (`MOONSHOT_API_KEY`) reitittää Moonshot AI:n palvelimille Kiinassa.
- **Ei telemetriaa**, ei käytön seurantaa, ei analytiikkaa.
- **Kyselyjen lokitus** — jokainen `graphify query`-, `graphify path`-, `graphify explain`- ja MCP `query_graph`-kutsu lokitetaan tiedostoon `~/.cache/graphify-queries.log` JSON Lines -muodossa (aikaleima, kysymys, korpus, palautetut solmut, kesto). Täydellisiä aligraafivastauksia **ei** tallenneta oletuksena. Aseta `GRAPHIFY_QUERY_LOG_DISABLE=1` kieltäytyäksesi, tai `GRAPHIFY_QUERY_LOG=/dev/null` vaimentaaksesi poistamatta koodipolkua käytöstä.

---

## Vianetsintä

Yleiset asennus- ja ekstraktio-ongelmat ja niiden korjaukset: **[Vianetsintä](https://docs.graphify.com/troubleshooting)**.

---

## Täydellinen komentoviite

Jokainen komento ja lippu, esimerkkien kera: **[CLI-viite](https://docs.graphify.com/reference/overview)**.

---

## Lue lisää

- [docs.graphify.com](https://docs.graphify.com) — täysi dokumentaatio: oppaat, komentoviite ja integraatiot
- [Miten se toimii](../how-it-works.md) — ekstraktioputki, yhteisöjen havaitseminen, luottamuspisteytys, benchmarks
- [ARCHITECTURE.md](../../ARCHITECTURE.md) — moduulien erittely, miten lisätä kieli
- [Valinnaiset integraatiot](../docker-mcp-sqlite.md) — Docker MCP Toolkit + SQLite
- [The Memory Layer](https://safishamsi.gumroad.com/l/qetvlo) — kirja graphifyn taustalla olevista ideoista, arkkitehtuuri päästä päähän

---

## Graphify Cloud

[**Graphify Cloud**](https://app.graphify.com/login) on aina päällä oleva kerros, joka on rakennettu graphifyn päälle. Sen sijaan, että rakentaisit graafin tarvittaessa uudelleen kansiokohtaisesti, se pitää yhtä elävää graafia koko ohjelmistokehityksen elinkaaren läpi:

- **80% vähemmän tokeneita** — aina päällä oleva muisti tarkoittaa, että agenttisi lopettavat koodikannan uudelleenlukemisen ja -selittämisen joka istunnossa.
- **Monorepo ja repojen välinen** — yksi yhdistetty graafi jokaisen palvelun ja repositorion yli, ei graafia kansiota kohden.
- **Formaali verifiointi** — tarkista arkkitehtuuri- ja riippuvuusinvariantit elävää graafia vasten.
- **Koodikatselmointi lintuperspektiivistä SDLC:ääsi** — näe, miten muutos leviää läpi koko järjestelmän ennen kuin merge:aat.
- **SDLC-liittimet** — tuo mukaan Sentry, Jira ja muita, niin että häiriöt, tiketit ja koodi elävät yhdessä graafissa.
- **Aina päällä** — päivittyy jatkuvasti taustalla koodin, dokumenttien ja kokousten yli.

**[Aloita ilmainen 14 päivän kokeilu osoitteessa app.graphify.com &rarr;](https://app.graphify.com/login)**

---

## Osallistuminen

Osallistumiset ovat tervetulleita. Katso **[CONTRIBUTING.md](../../CONTRIBUTING.md)** kehitysympäristön, testi- ja CI-pariteettikomentojen, git-työnkulun ja sen osalta, mikä tekee vahvan osallistumisen (työstetyt esimerkit ja ekstraktiovikailmoitukset ovat hyödyllisimpiä). Arkkitehtuuri ja miten lisätä kieli: [ARCHITECTURE.md](../../ARCHITECTURE.md).

Uusi täällä? Sano hei [Discordissa](https://discord.gg/XDnKVpzdXB) tai [GitHub Discussionsissa](https://github.com/Graphify-Labs/graphify/discussions).

---

## Osallistujat

<a href="https://github.com/Graphify-Labs/graphify/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=Graphify-Labs/graphify" alt="graphify contributors" />
</a>

Tehty työkalulla [contrib.rocks](https://contrib.rocks).

---

## Käännökset

README on saatavilla 32 kielellä. Käytä tämän tiedoston yläreunan kielivalitsinta lukeaksesi sen omallasi, tai selaa [`docs/translations/`](./). Parantaaksesi käännöstä tai lisätäksesi uuden, avaa pull request vastaavaa tiedostoa vasten siellä.

---

## graphifyn päälle rakentaminen

Rakennatko jotain graphify-ekosysteemissä? Sitä kannustetaan. Jos projektisi käyttää nimessään "graphify" (esimerkiksi `graphify-dashboard` tai `graphify-action`), lisää READMEesi lyhyt huomautus, joka selventää, että se on yhteisön rakentama eikä sidoksissa Graphify Labsiin tai sen hyväksymä. "graphify" ja graphify-logo ovat Graphify Labsin tavaramerkkejä; älä käytä niitä tavalla, joka antaa ymmärtää virallista asemaa.

---

## Yhteisö ja linkit

<p align="center">
  <a href="https://graphify.com"><img src="https://img.shields.io/badge/Website-graphify.com-4c1?style=flat&logo=googlechrome&logoColor=white" alt="Website"/></a>
  <a href="https://discord.gg/XDnKVpzdXB"><img src="https://img.shields.io/badge/Discord-Join-5865F2?style=flat&logo=discord&logoColor=white" alt="Discord"/></a>
  <a href="https://x.com/graphify"><img src="https://img.shields.io/badge/X-graphify-000000?logo=x&logoColor=white" alt="X"/></a>
  <a href="https://www.youtube.com/@graphifylabs"><img src="https://img.shields.io/badge/YouTube-Graphify%20Labs-FF0000?style=flat&logo=youtube&logoColor=white" alt="YouTube"/></a>
  <a href="https://github.com/sponsors/safishamsi"><img src="https://img.shields.io/badge/sponsor-safishamsi-ea4aaa?logo=github-sponsors" alt="Sponsor"/></a>
  <a href="https://safishamsi.gumroad.com/l/qetvlo"><img src="https://img.shields.io/badge/Book-The%20Memory%20Layer-2ea44f?style=flat&logo=gitbook&logoColor=white" alt="The Memory Layer"/></a>
</p>
