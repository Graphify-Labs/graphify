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
  <b>Réduisez de 80 % les dépenses en tokens de vos agents.</b> Graphify Cloud est une mémoire toujours active qui gouverne vos agents, maintient une haute qualité de code et prouve la justesse par vérification formelle. <a href="https://app.graphify.com/login"><b>Commencez un essai gratuit de 14 jours &rarr;</b></a>
</p>

Tapez `/graphify` dans votre assistant de codage IA, et il cartographie l'ensemble de votre projet (code, documents, PDF, images, vidéos) dans un **graphe de connaissances** que vous pouvez **interroger au lieu de faire un grep** à travers les fichiers.

- **Cartographie du code gratuite, entièrement locale.** Le code est analysé avec l'AST de tree-sitter : déterministe, sans LLM, rien ne quitte votre machine. (Les documents, PDF, images et vidéos utilisent le modèle de votre assistant, ou une clé d'API configurée, pour une passe sémantique.)
- **Chaque arête est expliquée.** Chaque connexion est étiquetée `EXTRACTED` (explicite dans la source) ou `INFERRED` (résolue par graphify), de sorte que vous pouvez distinguer ce qui a été lu directement de ce qui a été inféré.
- **Pas un index vectoriel.** Pas d'embeddings, pas de magasin de vecteurs : un vrai graphe que vous parcourez. Posez une question, tracez le chemin entre deux choses, ou expliquez un concept.

> [!NOTE]
> **Vous voulez cela en permanence ?** [Graphify Cloud](https://app.graphify.com/login) maintient le graphe à jour sur l'ensemble de votre SDLC : prise en charge des monorepos et du multi-dépôt, vérification formelle et revue de code avec une vue d'ensemble de votre SDLC, plus des connecteurs pour Sentry, Jira et davantage, afin que les incidents et les tickets se trouvent dans le même graphe que votre code. **[Commencez un essai gratuit de 14 jours sur app.graphify.com](https://app.graphify.com/login)**.

<p align="center">
  <img src="https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/graph-hero.png" alt="graphify's interactive graph.html showing the FastAPI codebase as a force-directed knowledge graph with a legend of detected communities" width="900">
</p>
<p align="center">
  <em>La base de code FastAPI cartographiée par graphify. Chaque nœud est un concept, les couleurs sont des communautés détectées, et l'ensemble est cliquable dans graph.html.</em>
</p>

**Pour démarrer** (30 secondes). Nécessite Python 3.10+ et uv (ou pipx) :

```bash
uv tool install graphifyy      # install the CLI (or: pipx install graphifyy)
graphify install               # detects your assistant and registers the skill
```

Ensuite, dans votre assistant IA :

```
/graphify .
```

C'est tout. Vous obtenez **trois fichiers** :

```
graphify-out/
├── graph.html       open in any browser: click nodes, filter, search
├── GRAPH_REPORT.md  the highlights: key concepts, surprising connections, suggested questions
└── graph.json       the full graph: query it anytime without re-reading your files
```

Le graphe persistant inclut `graph.schema_version` afin que les intégrations puissent détecter
les changements de format incompatibles, ainsi que `graph.graphify_version` identifiant la
version de Graphify qui l'a produit.

**Une seule installation, tout assistant, tout OS.** Claude Code, Cursor, Codex, Gemini CLI, GitHub Copilot et plus de 20 autres, sur macOS, Linux et Windows : [choisissez votre plateforme](#install).

---

## See it in action

<p align="center">
  <img src="https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/demo-path.svg" alt="graphify path query: a terminal asks for the shortest path between FastAPI and ModelField, and the answer lights up hop by hop across the knowledge graph" width="900">
</p>

Une fois le graphe construit, vous l'interrogez au lieu de lire des fichiers. Sortie réelle, graphify exécuté sur la base de code FastAPI montrée ci-dessus :

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

Chaque arête porte une **étiquette de confiance** (`EXTRACTED` = explicite dans la source, `INFERRED` = dérivée par résolution), de sorte que vous pouvez distinguer ce qui a été lu directement de ce qui a été inféré. `graphify query "<question>"` renvoie un sous-graphe ciblé pour une question en langage naturel, et `graphify path A B` trace comment deux éléments quelconques sont reliés.

---

## What it does

Ce que vous obtenez d'emblée :

| Capacité | Ce que vous obtenez |
|---|---|
| **God nodes** | Les concepts les plus connectés, pour voir par où tout transite |
| **Communities** | Le graphe découpé en sous-systèmes (Leiden), avec des étiquettes sans LLM |
| **Liens inter-fichiers** | `calls` / `imports` / `inherits` / `mixes_in` résolus à travers ~40 langages via l'AST de tree-sitter |
| **Query, path, explain** | Posez une question, tracez le chemin entre deux choses, ou expliquez un concept, le tout sur `graph.json` |
| **Justification + réf. doc** | Les commentaires `# NOTE:` / `# WHY:` et les citations ADR/RFC deviennent des nœuds de première classe liés au code |
| **Au-delà du code** | Documents, PDF, images et vidéo/audio sont tous cartographiés dans le même graphe |
| **Local-first** | Le code est analysé localement avec tree-sitter (pas de LLM, rien ne quitte votre machine) ; seule la passe sémantique sur les documents/médias appelle un backend, et seulement si vous en configurez un |

> [!TIP]
> Vous exécutez cela sur de nombreux dépôts ou un monorepo ? [Graphify Cloud](https://app.graphify.com/login) le fait en continu et réduit de 80 % les dépenses en tokens des agents, avec des liens multi-dépôt, une revue de code à l'échelle du SDLC, la vérification formelle et des connecteurs Sentry/Jira. [Commencez un essai gratuit de 14 jours &rarr;](https://app.graphify.com/login)

---

## Benchmarks: 0.497 recall@10, 0 LLM credits

| Benchmark | Métrique | graphify | Domaine |
|---|---|---|---|
| LOCOMO (n=300) | recall@10 | **0.497** | mem0 0.048, supermemory 0.149 |
| LOCOMO (n=300) | QA accuracy | 45.3% | supermemory 49.7%, mem0 27.3% |
| LongMemEval-S (n=50) | QA accuracy | **76%** | à égalité avec le dense RAG |
| ERPNext cross-tool (n=6) | key-fact coverage | **82.0%** | grep/read baseline 70.8% |
| Graph build | LLM credits | **0** | par token pour la plupart des systèmes |

Chaque système a tourné sur le même harnais avec le même modèle et les mêmes budgets, noté par un juge validé à l'aveugle contre un second juge (90,6 % d'accord, kappa de Cohen 0,81). Tableaux complets par système, le résultat de code-intelligence et les commandes de reproduction : **[BENCHMARKS.md](../../BENCHMARKS.md)**.

---

## Documentation

Guides complets et référence disponibles sur **[docs.graphify.com](https://docs.graphify.com)** :

- **[Quickstart](https://docs.graphify.com/quickstart)** : construisez votre premier graphe
- **[CLI reference](https://docs.graphify.com/reference/overview)** : chaque commande et chaque option
- **[Ask better graph questions](https://docs.graphify.com/guides/querying)** : modèles de requêtes
- **[Configuration](https://docs.graphify.com/reference/configuration)** : variables d'environnement et réglages
- **[Supported inputs](https://docs.graphify.com/concepts/supported-inputs)** : langages et types de fichiers
- **[Team workflows](https://docs.graphify.com/guides/team-workflows)** et **[PR review](https://docs.graphify.com/guides/pull-requests)**
- **[Troubleshooting](https://docs.graphify.com/troubleshooting)** et **[How it works](https://docs.graphify.com/concepts/architecture)**

---

## Prerequisites

| Exigence | Minimum | Vérifier | Installer |
|---|---|---|---|
| Python | 3.10+ | `python --version` | [python.org](https://www.python.org/downloads/) |
| uv *(recommandé)* | toute version | `uv --version` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| pipx *(alternative)* | toute version | `pipx --version` | `pip install pipx` |

**Installation rapide sur macOS (Homebrew) :**
```bash
brew install python@3.12 uv
```

**Installation rapide sur Windows :**
```powershell
winget install astral-sh.uv
```

**Ubuntu/Debian :**
```bash
sudo apt install python3.12 python3-pip pipx
# or install uv:
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## Install

> [!IMPORTANT]
> **Paquet officiel :** le paquet PyPI est `graphifyy` (double y). Les autres paquets `graphify*` sur PyPI ne sont pas affiliés. La commande CLI reste `graphify`.

Le dépôt source officiel est [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify).

Le quickstart en deux commandes se trouve en haut de ce README. Cette section couvre les méthodes d'installation, les installations à portée projet et chaque plateforme prise en charge.

**Méthodes d'installation** (choisissez-en une) :

```bash
uv tool install graphifyy   # recommended, isolated env (if 'graphify' isn't found after, run: uv tool update-shell)
pipx install graphifyy      # alternative
pip install graphifyy       # may need PATH setup, see Troubleshooting below
```

Ensuite, exécutez `graphify install` une fois. Il détecte quel assistant vous utilisez et enregistre la skill, il n'y a donc aucune configuration par assistant. Ouvrez votre assistant IA et tapez `/graphify .`

Pour installer la skill de l'assistant dans le dépôt courant plutôt que dans votre
profil utilisateur, ajoutez `--project` :

```bash
graphify install --project
graphify install --project --platform codex
```

Les installations à portée projet écrivent sous le répertoire courant, par exemple
`.claude/skills/graphify/SKILL.md` ou `.agents/skills/graphify/SKILL.md` (plus un
sidecar `references/` que la skill charge à la demande), et
affichent une indication `git add` pour les fichiers qui peuvent être commités.
Les commandes par plateforme qui prennent en charge les installations à portée projet acceptent la même option,
par exemple `graphify claude install --project` ou `graphify codex install --project`.

> [!TIP]
> Vous tombez sur `command not found`, un souci `pip` sur Mac/Windows, du quoting PowerShell, l'usage de `uvx`, des bizarreries de PATH avec les git-hooks, ou le mode strict ? Voir **[Installation](https://docs.graphify.com/installation)** et **[Troubleshooting](https://docs.graphify.com/troubleshooting)**.

<details>
<summary><b>Pick your platform</b> (20+ assistants, click to expand)</summary>

| Plateforme | Commande d'installation |
|----------|----------------|
| Claude Code (Linux/Mac) | `graphify install` |
| Claude Code (Windows) | `graphify install` (détecté automatiquement) ou `graphify install --platform windows` |
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
| Agent Skills (multi-frameworks) | `graphify install --platform agents` (alias `--platform skills`) |
| Kiro IDE/CLI | `graphify kiro install` |
| Pi coding agent | `graphify install --platform pi`, plus `graphify pi guard install` pour le garde natif |
| Cursor | `graphify cursor install` |
| Devin CLI | `graphify devin install` |
| Google Antigravity | `graphify antigravity install` |

Les utilisateurs de Codex ont aussi besoin de `multi_agent = true` sous `[features]` dans `~/.codex/config.toml` pour l'extraction parallèle. CodeBuddy utilise le même mécanisme d'outil Agent et de hook PreToolUse que Claude Code. Factory Droid utilise l'outil `Task` pour le dispatch parallèle des sous-agents. OpenClaw et Aider utilisent une extraction séquentielle (la prise en charge des agents parallèles en est encore à ses débuts sur ces plateformes). Trae utilise l'outil Agent pour le dispatch parallèle des sous-agents et ne prend **pas** en charge les hooks `PreToolUse`, donc AGENTS.md est le mécanisme toujours actif.

`--platform agents` (alias `--platform skills`) cible les emplacements génériques et multi-frameworks d'[Agent-Skills](https://github.com/anthropics/skills) : le `~/.agents/skills/` global de l'utilisateur défini par la spécification (lu par `npx skills` et les frameworks conformes à la spécification) pour une installation globale, et `./.agents/skills/` pour une installation projet (`--project`). Le `graphify install` nu reste mono-plateforme (Claude Code) par conception : utilisez la plateforme nommée `agents` lorsque vous voulez que la skill soit découvrable par n'importe quel framework qui lit `.agents/skills`.

Pi n'a pas de hook `PreToolUse`, donc `graphify pi guard install` enregistre une extension Pi native (via le propre `pi install <package directory>` de Pi) qui exécute le `graphify hook-guard` installé avant les appels `read`, `grep`, `find` et les appels `bash` de type recherche de Pi. Les décisions de graphe frais/périmé et le refus de lecture indexée une fois par session via `GRAPHIFY_HOOK_STRICT=1` proviennent de cette même politique, de sorte que Pi reproduit le comportement de hook de Claude Code ; les consignes arrivent sous forme de message d'orientation `<system-reminder source="graphify">`. Il nécessite Pi 0.58.4 ou plus récent : les versions antérieures laissent un message d'orientation sauter le reste d'un lot d'appels d'outils parallèles. Le paquet est livré à l'intérieur de l'installation de Graphify, installez donc Graphify de façon persistante (`uv tool install graphifyy` ou `pipx install graphifyy`, pas `uvx`), redémarrez Pi après l'installation ou la mise à niveau, et retirez-le avec `graphify pi guard uninstall`. Seules les cibles de fichiers locaux sont inspectées ; le hook a besoin de `graphify` sur une entrée `PATH` absolue en dehors du projet, est borné à un appel de deux secondes, 256 KiB-in/64 KiB-out, et échoue en mode ouvert. Le même paquet se charge aussi dans [Oh My Pi](https://github.com/can1357/oh-my-pi) : `omp plugin install "$(graphify pi guard path)"`. Le chemin enregistré contient la version de Python et le venv, donc réexécutez `graphify pi guard install` après avoir changé l'un ou l'autre, et retirez l'ancienne entrée avec `pi remove <old path>`.

> Codex utilise `$graphify` au lieu de `/graphify`.

</details>

<details>
<summary><b>Optional extras</b> (install only what you need)</summary>

| Extra | Ce qu'il ajoute | Installer |
|---|---|---|
| `pdf` | Extraction de PDF | `uv tool install "graphifyy[pdf]"` |
| `office` | Prise en charge de `.docx` et `.xlsx` | `uv tool install "graphifyy[office]"` |
| `google` | Rendu de Google Sheets | `uv tool install "graphifyy[google]"` |
| `video` | Transcription vidéo/audio (faster-whisper + yt-dlp) | `uv tool install "graphifyy[video]"` |
| `mcp` | Serveur MCP stdio | `uv tool install "graphifyy[mcp]"` |
| `neo4j` | Prise en charge du push Neo4j | `uv tool install "graphifyy[neo4j]"` |
| `falkordb` | Prise en charge du push FalkorDB | `uv tool install "graphifyy[falkordb]"` |
| `svg` | Export du graphe en SVG | `uv tool install "graphifyy[svg]"` |
| `leiden` | Détection de communautés Leiden (graspologic sur Python < 3.13 ; backend natif sur 3.13+) | `uv tool install "graphifyy[leiden]"` |
| `ollama` | Inférence locale Ollama | `uv tool install "graphifyy[ollama]"` |
| `openai` | API OpenAI / compatibles OpenAI | `uv tool install "graphifyy[openai]"` |
| `gemini` | API Google Gemini | `uv tool install "graphifyy[gemini]"` |
| `anthropic` | API Anthropic Claude (`--backend claude`, utilise `ANTHROPIC_API_KEY`) | `uv tool install "graphifyy[anthropic]"` |
| `bedrock` | AWS Bedrock (utilise IAM, pas de clé d'API) | `uv tool install "graphifyy[bedrock]"` |
| `azure` | Azure OpenAI Service (`--backend azure`, utilise `AZURE_OPENAI_API_KEY` + `AZURE_OPENAI_ENDPOINT`) | `uv tool install "graphifyy[openai]"` |
| `sql` | Extraction de schémas SQL | `uv tool install "graphifyy[sql]"` |
| `postgres` | Introspection PostgreSQL en direct (`--postgres DSN`) | `uv tool install "graphifyy[postgres]"` |
| `dm` | Extraction AST BYOND DreamMaker `.dm`/`.dme` (peut nécessiter un compilateur C + `python3-dev` si aucun wheel ne correspond à votre plateforme) | `uv tool install "graphifyy[dm]"` |
| `terraform` | Extraction AST Terraform / HCL `.tf`/`.tfvars`/`.hcl` | `uv tool install "graphifyy[terraform]"` |
| `pascal` | Extraction AST Pascal / Delphi `.pas`/`.dpr`/`.dpk`/`.inc` (arêtes `calls`/`inherits` plus précises ; se rabat sur un extracteur regex en son absence) | `uv tool install "graphifyy[pascal]"` |
| `ocaml` | Extraction AST OCaml `.ml`/`.mli` | `uv tool install "graphifyy[ocaml]"` |
| `commonlisp` | Extraction AST Common Lisp `.lisp`/`.cl`/`.lsp`/`.asd` | `uv tool install "graphifyy[commonlisp]"` |
| `robot` | Extraction Robot Framework `.robot`/`.resource` (suites, cas de test, keywords, arêtes d'appel de keyword et d'import de ressource/bibliothèque) | `uv tool install "graphifyy[robot]"` |
| `chinese` | Segmentation des requêtes en chinois (jieba) | `uv tool install "graphifyy[chinese]"` |
| `all` | Tout ce qui précède | `uv tool install "graphifyy[all]"` |

</details>

---

## Make your assistant always use the graph

Exécutez ceci une fois dans votre projet après avoir construit un graphe :

Exécutez `graphify <platform> install` une fois dans votre projet, par exemple `graphify claude install` ou `graphify codex install` (ou `graphify install --platform <name>`).

Cela écrit un petit fichier de configuration qui indique à votre assistant de consulter le graphe de connaissances pour les questions sur la base de code, en préférant des requêtes ciblées comme `graphify query "<question>"` à la lecture du rapport complet ou au grep de fichiers bruts.

- **Plateformes à hooks** (Claude Code, Gemini CLI) : un hook se déclenche automatiquement avant les appels d'outils de type recherche (et, sur Claude Code, avant de lire les fichiers source un par un via les outils Read/Glob) et oriente votre assistant vers le chemin du graphe.
- **Plateformes à fichiers d'instructions** (Codex, OpenCode, Cursor, etc.) : des fichiers d'instructions persistants (`AGENTS.md`, `.cursor/rules/`, etc.) fournissent les mêmes consignes de requête d'abord.

`GRAPH_REPORT.md` reste disponible pour une revue d'architecture globale.

Exactement quels fichiers chaque plateforme écrit (le `CODEBUDDY.md` + les hooks `PreToolUse` de CodeBuddy, l'`AGENTS.md` de Codex, le plugin natif `.kilo` de Kilo, la règle `alwaysApply` de Cursor, et ainsi de suite) est couvert dans **[Always-on setup](https://docs.graphify.com/guides/always-on)**.

Pour retirer graphify de toutes les plateformes d'un coup : `graphify uninstall` (ajoutez `--purge` pour supprimer aussi `graphify-out/`). Ou utilisez la commande par plateforme (par ex. `graphify claude uninstall`).

### CLI skills or MCP instructions?

Les instructions installées par `graphify install` et celles fournies avec une connexion Graphify MCP décrivent différentes façons d'interroger un graphe :

| Configuration | Consigne à utiliser | Accès aux requêtes |
|---|---|---|
| CLI locale et skill d'assistant installée | Les instructions de plateforme écrites par `graphify install` | Exécutez `graphify query`, `graphify path` et `graphify explain` contre le graphe local (`graphify-out/` par défaut). |
| Serveur Graphify MCP connecté | Les instructions de la connexion et les outils listés par ce serveur | Appelez les outils MCP listés contre le graphe servi par cette connexion. Les noms et descriptions des outils proviennent du serveur. |

Les deux encouragent les requêtes de graphe ciblées avant les recherches de source larges. Choisissez les instructions qui correspondent aux outils auxquels votre assistant peut réellement accéder ; aucun des deux blocs n'établit de règle de préséance universelle pour les fichiers d'instructions de votre assistant. Si vous utilisez les deux intégrations, identifiez quel graphe chacune interroge et choisissez un chemin de requête principal plutôt que de copier deux blocs d'instructions inconditionnels dans `AGENTS.md`.

`graphify install` installe l'intégration locale de l'assistant ; il n'établit pas de connexion MCP. Un client MCP n'a pas besoin d'exécuter des requêtes CLI locales pour utiliser son serveur connecté. Un serveur hébergé localement a toujours besoin de sa propre installation de Graphify et de son propre graphe, tandis qu'une connexion hébergée peut servir un graphe qui n'est pas présent dans le répertoire de travail du client. Si les outils attendus sont manquants, vérifiez l'installation CLI ou la connexion MCP concernée plutôt que de traiter les instructions de l'autre configuration comme interchangeables.

---

## What's in the report

`GRAPH_REPORT.md` résume les god nodes, les communautés et les chemins clés pour une revue d'architecture globale. Comment le graphe est construit et ce qu'il contient : **[How graphify works](https://docs.graphify.com/concepts/architecture)**.

---

## What files it handles: ~40 languages

graphify analyse ~40 langages de programmation localement avec l'AST de tree-sitter, et cartographie les documents, PDF, images et audio/vidéo via une passe sémantique optionnelle. Liste complète : **[Supported inputs](https://docs.graphify.com/concepts/supported-inputs)**.

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

Voir la [référence complète des commandes](#full-command-reference) ci-dessous.

---

## Ignoring files

graphify respecte `.gitignore` et prend en charge les motifs `--exclude` ainsi qu'un fichier de projet `.graphifyignore`. Détails : **[Configuration](https://docs.graphify.com/reference/configuration)**.


## Project configuration

Créez un `.graphifyrc` dans la racine de scan pour les réglages qui appartiennent au projet plutôt qu'à une seule exécution. Un `key=value` par ligne ; les lignes commençant par `#` sont des commentaires.

**Extensions ambiguës.** Certaines extensions désignent des langages différents selon les projets : `.inc` est du PHP sur pfSense, du Pascal dans une arborescence Delphi, du SQL ou de l'assembleur ailleurs ; `.h` est du C ou du C++ ; `.m` est de l'Objective-C ou du MATLAB. graphify doit choisir une valeur par défaut globale, et lorsqu'il choisit mal le fichier n'échoue pas : il est analysé comme le mauvais langage et produit une poignée de nœuds accessoires, de sorte que le graphe semble peuplé alors que les vrais symboles sont absents. Déclarez ce que l'extension signifie dans votre dépôt :

```
# .graphifyrc
# A language name:
language.inc=php
# Or an extension graphify already knows:
language.tpl=.ts
# Baked into the git hooks (see Team setup):
viz_node_limit=0
```

La déclaration traverse la classification, la sélection d'extracteur, la grammaire et la résolution, les imports, `graphify watch` et le cache AST (un fichier réanalysé sous un langage différent ne réutilise jamais l'ancienne entrée), et le même `.graphifyrc` est lu par `extract`, `update`, les hooks, le serveur MCP et la skill `/graphify`. Une faute de frappe est signalée une fois sur stderr et le scan se poursuit avec les valeurs par défaut. Comment les déclarations interagissent avec la mise en cache, les reconstructions incrémentales et la résolution des imports : **[Configuration](https://docs.graphify.com/reference/configuration)**.

---

## Team setup

Commitez ou partagez le graphe pour que toute votre équipe interroge le même contexte, et relisez les pull requests avec le contexte du graphe. Voir **[Share context with your team](https://docs.graphify.com/guides/team-workflows)** et **[Review pull requests](https://docs.graphify.com/guides/pull-requests)**.

---

## Using the graph directly

Au-delà de votre assistant IA, interrogez `graph.json` directement depuis la CLI avec `graphify query`, `graphify path` et `graphify explain`. Un nom qui correspond à plusieurs nœuds est refusé avec les candidats listés plutôt que deviné. Les scripts peuvent lire le résultat depuis le code de sortie : `0` une réponse, `3` un nom ambigu, `4` aucun nœud correspondant. Voir **[Ask better graph questions](https://docs.graphify.com/guides/querying)** et la **[query reference](https://docs.graphify.com/reference/query)**.

---

## Environment variables

Les backends, les clés d'API, le comportement des hooks et les réglages sont contrôlés par des variables d'environnement. Tableau complet : **[Configuration](https://docs.graphify.com/reference/configuration)**.

---

## Privacy

- **Fichiers de code** : traités localement via tree-sitter. Rien ne quitte votre machine. Un corpus composé uniquement de code ne nécessite aucune clé d'API : `graphify extract` tourne entièrement hors ligne. Sur un dépôt mixte, ajoutez `--code-only` pour n'indexer que le code et ignorer les documents/PDF/images qui nécessiteraient autrement un LLM.
- **Vidéo / audio** : transcrits localement avec faster-whisper. Rien ne quitte votre machine.
- **Documents, PDF, images** : envoyés à votre assistant IA pour une extraction sémantique (via la skill `/graphify`, en utilisant le modèle que votre session IDE exécute). En mode headless, `graphify extract` nécessite `GEMINI_API_KEY` / `GOOGLE_API_KEY` (Gemini), `MOONSHOT_API_KEY` (Kimi), `ANTHROPIC_API_KEY` (Claude), `OPENAI_API_KEY` (OpenAI), `DEEPSEEK_API_KEY` (DeepSeek), une instance Ollama en cours d'exécution (`OLLAMA_BASE_URL`), des identifiants AWS via la chaîne de fournisseurs standard (Bedrock : pas de clé d'API nécessaire, utilise IAM), ou le binaire CLI `claude` (Claude Code : pas de clé d'API nécessaire, utilise votre abonnement Claude). L'option `--dedup-llm` utilise la même clé.
- **Résidence des données** : `graphify extract` détecte automatiquement quel fournisseur utiliser en fonction de la clé d'API définie (priorité : Gemini → Kimi → Claude → OpenAI → DeepSeek → Azure → Bedrock → Ollama). Pour du code soumis à des exigences de résidence des données, utilisez `--backend ollama` (entièrement local) ou passez une option `--backend` explicite. Kimi (`MOONSHOT_API_KEY`) achemine vers les serveurs de Moonshot AI en Chine.
- **Pas de télémétrie**, pas de suivi d'utilisation, pas d'analytique.
- **Journalisation des requêtes** : chaque appel `graphify query`, `graphify path`, `graphify explain` et MCP `query_graph` est journalisé dans `~/.cache/graphify-queries.log` au format JSON Lines (horodatage, question, corpus, nœuds renvoyés, durée). Les réponses complètes du sous-graphe ne sont **pas** stockées par défaut. Définissez `GRAPHIFY_QUERY_LOG_DISABLE=1` pour vous désinscrire, ou `GRAPHIFY_QUERY_LOG=/dev/null` pour le rendre silencieux sans désactiver le chemin de code.

---

## Troubleshooting

Problèmes courants d'installation et d'extraction et leurs correctifs : **[Troubleshooting](https://docs.graphify.com/troubleshooting)**.

---

## Full command reference

Chaque commande et chaque option, avec des exemples : **[CLI reference](https://docs.graphify.com/reference/overview)**.

---

## Learn more

- [docs.graphify.com](https://docs.graphify.com) : documentation complète : guides, référence des commandes et intégrations
- [How it works](../how-it-works.md) : le pipeline d'extraction, la détection de communautés, le scoring de confiance, les benchmarks
- [ARCHITECTURE.md](../../ARCHITECTURE.md) : découpage des modules, comment ajouter un langage
- [Optional integrations](../docker-mcp-sqlite.md) : Docker MCP Toolkit + SQLite
- [The Memory Layer](https://safishamsi.gumroad.com/l/qetvlo) : le livre sur les idées derrière graphify, l'architecture de bout en bout

---

## Graphify Cloud

[**Graphify Cloud**](https://app.graphify.com/login) est la couche toujours active construite au-dessus de graphify. Au lieu d'un graphe que vous reconstruisez à la demande par dossier, elle maintient un graphe vivant unique sur l'ensemble de votre cycle de vie de développement logiciel :

- **80 % de tokens en moins** : une mémoire toujours active signifie que vos agents cessent de relire et de ré-expliquer la base de code à chaque session.
- **Monorepo et multi-dépôt** : un seul graphe connecté sur chaque service et dépôt, pas un graphe par dossier.
- **Vérification formelle** : vérifiez les invariants d'architecture et de dépendances contre le graphe vivant.
- **Revue de code avec une vue d'ensemble de votre SDLC** : voyez comment un changement se répercute sur tout le système avant de merger.
- **Connecteurs SDLC** : intégrez Sentry, Jira et davantage, afin que les incidents, les tickets et le code vivent dans un seul graphe.
- **Toujours actif** : se met à jour en continu en arrière-plan sur le code, les documents et les réunions.

**[Commencez un essai gratuit de 14 jours sur app.graphify.com &rarr;](https://app.graphify.com/login)**

---

## Contributing

Les contributions sont les bienvenues. Voir **[CONTRIBUTING.md](../../CONTRIBUTING.md)** pour la configuration de développement, les commandes de test et de parité CI, le workflow git, et ce qui fait une contribution solide (les exemples travaillés et les rapports de bugs d'extraction sont les plus utiles). Architecture et comment ajouter un langage : [ARCHITECTURE.md](../../ARCHITECTURE.md).

Nouveau ici ? Dites bonjour sur [Discord](https://discord.gg/graphify) ou dans les [GitHub Discussions](https://github.com/Graphify-Labs/graphify/discussions).

---

## Contributors

<a href="https://github.com/Graphify-Labs/graphify/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=Graphify-Labs/graphify" alt="graphify contributors" />
</a>

Réalisé avec [contrib.rocks](https://contrib.rocks).

---

## Translations

Le README est disponible en 32 langues. Utilisez le sélecteur de langue en haut de ce fichier pour le lire dans la vôtre, ou parcourez [`docs/translations/`](./). Pour améliorer une traduction ou en ajouter une nouvelle, ouvrez une pull request sur le fichier correspondant.

---

## Building on graphify

Vous construisez quelque chose dans l'écosystème graphify ? C'est encouragé. Si votre projet utilise « graphify » dans son nom (par exemple `graphify-dashboard` ou `graphify-action`), veuillez ajouter une brève note à votre README précisant qu'il est construit par la communauté et qu'il n'est ni affilié à Graphify Labs ni approuvé par eux. « graphify » et le logo graphify sont des marques de Graphify Labs ; veuillez ne pas les utiliser d'une manière qui laisserait entendre un statut officiel.

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
