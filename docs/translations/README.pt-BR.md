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
  <b>Reduza em 80% o gasto de tokens dos seus agentes.</b> O Graphify Cloud é uma memória sempre ativa que governa seus agentes, mantém a qualidade do código em alta e comprova a correção com verificação formal. <a href="https://app.graphify.com/login"><b>Comece um teste gratuito de 14 dias &rarr;</b></a>
</p>

Digite `/graphify` no seu assistente de código com IA e ele mapeia o projeto inteiro (código, docs, PDFs, imagens, vídeos) em um **grafo de conhecimento** que você pode **consultar em vez de fazer grep** nos arquivos.

- **Mapeia código de graça, totalmente local.** O código é analisado com AST do tree-sitter: determinístico, sem LLM, nada sai da sua máquina. (Docs, PDFs, imagens e vídeo usam o modelo do seu assistente, ou uma chave de API configurada, para uma passagem semântica.)
- **Toda aresta é explicada.** Cada conexão é marcada como `EXTRACTED` (explícita na fonte) ou `INFERRED` (resolvida pelo graphify), para você distinguir o que foi lido diretamente do que foi inferido.
- **Não é um índice vetorial.** Sem embeddings, sem armazenamento vetorial: um grafo de verdade que você percorre. Faça uma pergunta, trace o caminho entre duas coisas ou explique um conceito.

> [!NOTE]
> **Quer isso sempre ativo?** O [Graphify Cloud](https://app.graphify.com/login) mantém o grafo vivo ao longo de todo o seu SDLC: suporte a monorepo e a múltiplos repositórios, verificação formal e revisão de código com uma visão panorâmica do seu SDLC, além de conectores para Sentry, Jira e muito mais, para que incidentes e tickets fiquem no mesmo grafo que o seu código. **[Comece um teste gratuito de 14 dias em app.graphify.com](https://app.graphify.com/login)**.

<p align="center">
  <img src="https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/graph-hero.png" alt="graphify's interactive graph.html showing the FastAPI codebase as a force-directed knowledge graph with a legend of detected communities" width="900">
</p>
<p align="center">
  <em>A base de código do FastAPI mapeada pelo graphify. Cada nó é um conceito, as cores são comunidades detectadas, e tudo é clicável no graph.html.</em>
</p>

**Comece agora** (30 segundos):

```bash
uv tool install graphifyy      # install the CLI (or: pipx install graphifyy)
graphify install               # register the skill with your AI assistant
```

Depois, no seu assistente de IA:

```
/graphify .
```

É isso. Você recebe **três arquivos**:

```
graphify-out/
├── graph.html       open in any browser — click nodes, filter, search
├── GRAPH_REPORT.md  the highlights: key concepts, surprising connections, suggested questions
└── graph.json       the full graph — query it anytime without re-reading your files
```

O grafo persistido inclui `graph.schema_version` para que integrações consigam detectar
mudanças de formato incompatíveis, além de `graph.graphify_version`, que identifica a
versão do Graphify que o produziu.

**Funciona no** Claude Code, Cursor, Codex, Gemini CLI, GitHub Copilot e mais de 15 outros — [escolha sua plataforma](#install).

---

## Documentation

Guias completos e referência ficam em **[docs.graphify.com](https://docs.graphify.com)**:

- **[Quickstart](https://docs.graphify.com/quickstart)** — construa seu primeiro grafo
- **[CLI reference](https://docs.graphify.com/reference/overview)** — todos os comandos e flags
- **[Ask better graph questions](https://docs.graphify.com/guides/querying)** — padrões de consulta
- **[Configuration](https://docs.graphify.com/reference/configuration)** — variáveis de ambiente e ajustes finos
- **[Supported inputs](https://docs.graphify.com/concepts/supported-inputs)** — linguagens e tipos de arquivo
- **[Team workflows](https://docs.graphify.com/guides/team-workflows)** e **[PR review](https://docs.graphify.com/guides/pull-requests)**
- **[Troubleshooting](https://docs.graphify.com/troubleshooting)** e **[How it works](https://docs.graphify.com/concepts/architecture)**

---

## See it in action

<p align="center">
  <img src="https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/demo-path.svg" alt="graphify path query: a terminal asks for the shortest path between FastAPI and ModelField, and the answer lights up hop by hop across the knowledge graph" width="900">
</p>

Uma vez que o grafo está construído, você o consulta em vez de ler arquivos. Saída real, graphify executado na base de código do FastAPI mostrada acima:

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

Toda aresta carrega uma **marca de confiança** (`EXTRACTED` = explícita na fonte, `INFERRED` = derivada por resolução), para você distinguir o que foi lido diretamente do que foi inferido. `graphify query "<question>"` retorna um subgrafo delimitado para uma pergunta em linguagem natural, e `graphify path A B` traça como duas coisas quaisquer se conectam.

---

## What it does

O que você tem de cara:

| Capability | What you get |
|---|---|
| **God nodes** | Os conceitos mais conectados, para você ver por onde tudo passa |
| **Communities** | O grafo dividido em subsistemas (Leiden), com rótulos sem LLM |
| **Cross-file links** | `calls` / `imports` / `inherits` / `mixes_in` resolvidos entre ~40 linguagens via AST do tree-sitter |
| **Query, path, explain** | Faça uma pergunta, trace o caminho entre duas coisas ou explique um conceito, tudo sobre o `graph.json` |
| **Rationale + doc refs** | Comentários `# NOTE:` / `# WHY:` e citações de ADR/RFC viram nós de primeira classe ligados ao código |
| **Beyond code** | Docs, PDFs, imagens e vídeo/áudio mapeiam todos para o mesmo grafo |
| **Local-first** | O código é analisado localmente com tree-sitter (sem LLM, nada sai da sua máquina); só a passagem semântica sobre docs/mídia chama um backend, e apenas se você configurar um |

> [!TIP]
> Rodando isso em muitos repositórios ou em um monorepo? O [Graphify Cloud](https://app.graphify.com/login) faz isso continuamente e corta em 80% o gasto de tokens dos agentes, com links entre repositórios, revisão de código em todo o SDLC, verificação formal e conectores para Sentry/Jira. [Comece um teste gratuito de 14 dias &rarr;](https://app.graphify.com/login)

---

## Benchmarks

| Benchmark | Metric | graphify | Field |
|---|---|---|---|
| LOCOMO (n=300) | recall@10 | **0.497** | mem0 0.048, supermemory 0.149 |
| LOCOMO (n=300) | QA accuracy | 45.3% | supermemory 49.7%, mem0 27.3% |
| LongMemEval-S (n=50) | QA accuracy | **76%** | tied with dense RAG |
| ERPNext cross-tool (n=6) | key-fact coverage | **82.0%** | grep/read baseline 70.8% |
| Graph build | LLM credits | **0** | per-token for most systems |

Todos os sistemas rodaram no mesmo harness, com o mesmo modelo e os mesmos orçamentos, avaliados por um juiz validado às cegas contra um segundo juiz (90,6% de concordância, kappa de Cohen 0,81). Tabelas completas por sistema, o resultado de inteligência de código e os comandos de reprodução: **[BENCHMARKS.md](../../BENCHMARKS.md)**.

---

## Prerequisites

| Requirement | Minimum | Check | Install |
|---|---|---|---|
| Python | 3.10+ | `python --version` | [python.org](https://www.python.org/downloads/) |
| uv *(recommended)* | any | `uv --version` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| pipx *(alternative)* | any | `pipx --version` | `pip install pipx` |

**Instalação rápida no macOS (Homebrew):**
```bash
brew install python@3.12 uv
```

**Instalação rápida no Windows:**
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
> **Pacote oficial:** O pacote no PyPI é `graphifyy` (com dois y). Outros pacotes `graphify*` no PyPI não têm vínculo. O comando da CLI continua sendo `graphify`.

O repositório de código-fonte oficial é [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify).

**Passo 1 — instale o pacote:**

```bash
# Recommended (isolated env; if 'graphify' isn't found after, run: uv tool update-shell):
uv tool install graphifyy

# Alternatives:
pipx install graphifyy
pip install graphifyy  # may need PATH setup — see note below
```

**Passo 2 — registre a skill no seu assistente de IA:**

```bash
graphify install
```

É isso. Abra seu assistente de IA e digite `/graphify .`

Para instalar a skill do assistente no repositório atual em vez do seu perfil
de usuário, adicione `--project`:

```bash
graphify install --project
graphify install --project --platform codex
```

Instalações com escopo de projeto escrevem no diretório atual, por exemplo
`.claude/skills/graphify/SKILL.md` ou `.agents/skills/graphify/SKILL.md` (mais um
sidecar `references/` que a skill carrega sob demanda), e
mostram uma dica de `git add` para os arquivos que podem ser commitados.
Comandos por plataforma que suportam instalações com escopo de projeto aceitam a mesma flag,
por exemplo `graphify claude install --project` ou `graphify codex install --project`.

> [!TIP]
> Esbarrou em `command not found`, um problema de `pip` no Mac/Windows, aspas no PowerShell, uso do `uvx`, peculiaridades de PATH em git-hook ou no modo strict? Veja **[Installation](https://docs.graphify.com/installation)** e **[Troubleshooting](https://docs.graphify.com/troubleshooting)**.

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
| Pi coding agent | `graphify install --platform pi` |
| Cursor | `graphify cursor install` |
| Devin CLI | `graphify devin install` |
| Google Antigravity | `graphify antigravity install` |

Usuários do Codex também precisam de `multi_agent = true` em `[features]` no `~/.codex/config.toml` para extração paralela. O CodeBuddy usa o mesmo mecanismo de ferramenta Agent e hook PreToolUse que o Claude Code. O Factory Droid usa a ferramenta `Task` para despacho paralelo de subagentes. OpenClaw e Aider usam extração sequencial (o suporte a agentes paralelos ainda é incipiente nessas plataformas). O Trae usa a ferramenta Agent para despacho paralelo de subagentes e **não** suporta hooks `PreToolUse`, então o AGENTS.md é o mecanismo sempre ativo.

`--platform agents` (alias `--platform skills`) tem como alvo os locais genéricos entre frameworks do [Agent-Skills](https://github.com/anthropics/skills): o `~/.agents/skills/` global do usuário definido pela spec (lido pelo `npx skills` e por frameworks compatíveis com a spec) para uma instalação global, e `./.agents/skills/` para uma instalação de projeto (`--project`). O `graphify install` puro permanece de plataforma única (Claude Code) por design — use a plataforma nomeada `agents` quando quiser que a skill seja descoberta por qualquer framework que leia `.agents/skills`.

> O Codex usa `$graphify` em vez de `/graphify`.

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

Rode isto uma vez no seu projeto depois de construir um grafo:

Rode `graphify <platform> install` uma vez no seu projeto, por exemplo `graphify claude install` ou `graphify codex install` (ou `graphify install --platform <name>`).

Isso escreve um pequeno arquivo de configuração que diz ao seu assistente para consultar o grafo de conhecimento em perguntas sobre a base de código, preferindo consultas delimitadas como `graphify query "<question>"` em vez de ler o relatório completo ou fazer grep em arquivos brutos.

- **Plataformas com hook** (Claude Code, Gemini CLI): um hook dispara automaticamente antes de chamadas de ferramentas do tipo busca (e, no Claude Code, antes de ler arquivos-fonte um a um pelas ferramentas Read/Glob) e empurra seu assistente para o caminho do grafo.
- **Plataformas com arquivo de instruções** (Codex, OpenCode, Cursor, etc.): arquivos de instruções persistentes (`AGENTS.md`, `.cursor/rules/`, etc.) fornecem a mesma orientação de consultar primeiro.

O `GRAPH_REPORT.md` continua disponível para uma revisão ampla de arquitetura.

**CodeBuddy** faz as mesmas duas coisas que o Claude Code: escreve uma seção `CODEBUDDY.md` dizendo ao CodeBuddy para ler `graphify-out/GRAPH_REPORT.md` antes de responder perguntas de arquitetura, e instala hooks `PreToolUse` (`.codebuddy/settings.json`) que disparam antes de comandos de busca Bash e leituras de arquivo, empurrando para `graphify query` no lugar.

**Codex** escreve no `AGENTS.md`, que é o que de fato carrega a orientação sempre ativa do grafo nessa plataforma. `graphify codex install` também registra um hook `PreToolUse` em `.codex/hooks.json` (`graphify hook-check`), mas essa entrada é deliberadamente um **no-op**: o Codex Desktop rejeita `hookSpecificOutput.additionalContext` em `PreToolUse`, então emitir um empurrão ali quebraria as chamadas de ferramenta Bash. Diferente do Claude Code, onde o hook (`graphify hook-guard`) faz o empurrão, no Codex o hook dispara e intencionalmente não faz nada, e o `AGENTS.md` é o mecanismo sempre ativo.

**Kilo Code** instala a skill do Graphify em `~/.config/kilo/skills/graphify/SKILL.md` e um comando nativo `/graphify` em `~/.config/kilo/command/graphify.md`. `graphify kilo install` também escreve o `AGENTS.md` mais um plugin nativo `tool.execute.before` (`.kilo/plugins/graphify.js` + registro em `.kilo/kilo.json` ou `.kilo/kilo.jsonc`), de modo que o Kilo ganha o mesmo comportamento de lembrete sempre ativo do grafo através da configuração nativa `.kilo`.

**Cursor** escreve `.cursor/rules/graphify.mdc` com `alwaysApply: true`, então o Cursor o inclui em toda conversa automaticamente, sem necessidade de hook.

Para remover o graphify de todas as plataformas de uma vez: `graphify uninstall` (adicione `--purge` para também apagar o `graphify-out/`). Ou use o comando por plataforma (por exemplo, `graphify claude uninstall`).

---

## What's in the report

O `GRAPH_REPORT.md` resume os god nodes, as comunidades e os caminhos-chave para uma revisão ampla de arquitetura. Como o grafo é construído e o que ele contém: **[How graphify works](https://docs.graphify.com/concepts/architecture)**.

---

## What files it handles

O graphify analisa ~40 linguagens de programação localmente com AST do tree-sitter, e mapeia docs, PDFs, imagens e áudio/vídeo por meio de uma passagem semântica opcional. Lista completa: **[Supported inputs](https://docs.graphify.com/concepts/supported-inputs)**.

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

graphify hook install              # auto-rebuild on commit + branch checkout (run `graphify update .` after `git pull` — see "Recommended workflow" below)
graphify merge-graphs a.json b.json              # combine two graphs

graphify prs                       # PR dashboard: CI state, review status, worktree mapping
graphify prs 42                    # deep dive on PR #42 with graph impact
graphify prs --triage              # AI ranks your review queue (uses whatever backend is configured)
graphify prs --conflicts           # PRs sharing graph communities — merge-order risk
```

Veja a [referência completa de comandos](#full-command-reference) abaixo.

---

## Ignoring files

O graphify respeita o `.gitignore` e suporta padrões `--exclude` e um `.graphifyignore` de projeto. Detalhes: **[Configuration](https://docs.graphify.com/reference/configuration)**.

---

## Team setup

Faça commit do grafo ou compartilhe-o para que toda a sua equipe consulte o mesmo contexto, e revise pull requests com contexto do grafo. Veja **[Share context with your team](https://docs.graphify.com/guides/team-workflows)** e **[Review pull requests](https://docs.graphify.com/guides/pull-requests)**.

---

## Using the graph directly

Além do seu assistente de IA, consulte o `graph.json` direto da CLI com `graphify query`, `graphify path` e `graphify explain`. Veja **[Ask better graph questions](https://docs.graphify.com/guides/querying)** e a **[query reference](https://docs.graphify.com/reference/query)**.

---

## Environment variables

Backends, chaves de API, comportamento de hooks e ajustes finos são controlados por variáveis de ambiente. Tabela completa: **[Configuration](https://docs.graphify.com/reference/configuration)**.

---

## Privacy

- **Arquivos de código** — processados localmente via tree-sitter. Nada sai da sua máquina. Um corpus só de código não exige chave de API — `graphify extract` roda totalmente offline. Em um repositório misto, adicione `--code-only` para indexar apenas o código e pular os docs/PDFs/imagens que, de outro modo, precisariam de uma LLM.
- **Vídeo / áudio** — transcritos localmente com faster-whisper. Nada sai da sua máquina.
- **Docs, PDFs, imagens** — enviados ao seu assistente de IA para extração semântica (via a skill `/graphify`, usando o modelo que a sessão da sua IDE estiver rodando). O `graphify extract` headless requer `GEMINI_API_KEY` / `GOOGLE_API_KEY` (Gemini), `MOONSHOT_API_KEY` (Kimi), `ANTHROPIC_API_KEY` (Claude), `OPENAI_API_KEY` (OpenAI), `DEEPSEEK_API_KEY` (DeepSeek), uma instância do Ollama em execução (`OLLAMA_BASE_URL`), credenciais AWS pela cadeia de provedores padrão (Bedrock - sem chave de API, usa IAM), ou o binário da CLI `claude` (Claude Code - sem chave de API, usa sua assinatura do Claude). A flag `--dedup-llm` usa a mesma chave.
- **Residência de dados** — `graphify extract` detecta automaticamente qual provedor usar com base em qual chave de API está definida (prioridade: Gemini → Kimi → Claude → OpenAI → DeepSeek → Azure → Bedrock → Ollama). Para código com requisitos de residência de dados, use `--backend ollama` (totalmente local) ou passe uma flag `--backend` explícita. O Kimi (`MOONSHOT_API_KEY`) roteia para os servidores da Moonshot AI na China.
- **Sem telemetria**, sem rastreamento de uso, sem analytics.
- **Registro de consultas** — toda chamada `graphify query`, `graphify path`, `graphify explain` e `query_graph` do MCP é registrada em `~/.cache/graphify-queries.log` no formato JSON Lines (timestamp, pergunta, corpus, nós retornados, duração). Respostas completas de subgrafo **não** são armazenadas por padrão. Defina `GRAPHIFY_QUERY_LOG_DISABLE=1` para optar por não participar, ou `GRAPHIFY_QUERY_LOG=/dev/null` para silenciar sem desabilitar o caminho de código.

---

## Troubleshooting

Problemas comuns de instalação e extração e suas correções: **[Troubleshooting](https://docs.graphify.com/troubleshooting)**.

---

## Full command reference

Todos os comandos e flags, com exemplos: **[CLI reference](https://docs.graphify.com/reference/overview)**.

---

## Learn more

- [docs.graphify.com](https://docs.graphify.com) — documentação completa: guias, referência de comandos e integrações
- [How it works](../how-it-works.md) — o pipeline de extração, detecção de comunidades, pontuação de confiança, benchmarks
- [ARCHITECTURE.md](../../ARCHITECTURE.md) — divisão em módulos, como adicionar uma linguagem
- [Optional integrations](../docker-mcp-sqlite.md) — Docker MCP Toolkit + SQLite
- [The Memory Layer](https://safishamsi.gumroad.com/l/qetvlo) — o livro sobre as ideias por trás do graphify, a arquitetura de ponta a ponta

---

## Graphify Cloud

[**Graphify Cloud**](https://app.graphify.com/login) é a camada sempre ativa construída sobre o graphify. Em vez de um grafo que você reconstrói sob demanda por pasta, ele mantém um único grafo vivo ao longo de todo o seu ciclo de vida de desenvolvimento de software:

- **80% menos tokens** — memória sempre ativa significa que seus agentes param de reler e reexplicar a base de código a cada sessão.
- **Monorepo e múltiplos repositórios** — um grafo conectado único entre todos os serviços e repositórios, não um grafo por pasta.
- **Verificação formal** — verifique invariantes de arquitetura e de dependência contra o grafo vivo.
- **Revisão de código com uma visão panorâmica do seu SDLC** — veja como uma mudança se propaga por todo o sistema antes de fazer o merge.
- **Conectores de SDLC** — puxe o Sentry, o Jira e mais, para que incidentes, tickets e código vivam em um único grafo.
- **Sempre ativo** — atualiza continuamente em segundo plano em código, docs e reuniões.

**[Comece um teste gratuito de 14 dias em app.graphify.com &rarr;](https://app.graphify.com/login)**

---

## Contributing

Contribuições são bem-vindas. Veja **[CONTRIBUTING.md](../../CONTRIBUTING.md)** para a configuração de desenvolvimento, os comandos de teste e de paridade com a CI, o fluxo de trabalho do git e o que faz uma contribuição forte (exemplos trabalhados e relatos de bugs de extração são os mais úteis). Arquitetura e como adicionar uma linguagem: [ARCHITECTURE.md](../../ARCHITECTURE.md).

Novo por aqui? Diga oi no [Discord](https://discord.gg/XDnKVpzdXB) ou nas [GitHub Discussions](https://github.com/Graphify-Labs/graphify/discussions).

---

## Contributors

<a href="https://github.com/Graphify-Labs/graphify/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=Graphify-Labs/graphify" alt="graphify contributors" />
</a>

Feito com [contrib.rocks](https://contrib.rocks).

---

## Translations

O README está disponível em 32 idiomas. Use o seletor de idiomas no topo deste arquivo para lê-lo no seu, ou navegue por [`docs/translations/`](./). Para melhorar uma tradução ou adicionar uma nova, abra um pull request no arquivo correspondente ali.

---

## Building on graphify

Construindo algo no ecossistema do graphify? Isso é incentivado. Se o seu projeto usar "graphify" no nome (por exemplo `graphify-dashboard` ou `graphify-action`), por favor adicione uma nota curta ao seu README esclarecendo que é um projeto construído pela comunidade e não afiliado nem endossado pela Graphify Labs. "graphify" e o logo do graphify são marcas da Graphify Labs; por favor, não os use de uma forma que sugira status oficial.

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
