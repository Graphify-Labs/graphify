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
  <a href="https://discord.gg/graphify"><img src="https://img.shields.io/badge/Discord-Join-5865F2?style=flat&logo=discord&logoColor=white" alt="Discord"/></a>
  <a href="https://www.youtube.com/@graphifylabs"><img src="https://img.shields.io/badge/YouTube-Graphify%20Labs-FF0000?style=flat&logo=youtube&logoColor=white" alt="YouTube"/></a>
  <a href="https://www.linkedin.com/company/graphify-labs"><img src="https://img.shields.io/badge/LinkedIn-Graphify%20Labs-0077B5?logo=linkedin" alt="LinkedIn"/></a>
  <a href="https://www.ycombinator.com/companies/graphify-labs"><img src="https://img.shields.io/badge/Y%20Combinator-S26-F0652F?style=flat&logo=ycombinator&logoColor=white" alt="YC S26"/></a>
</p>

<p align="center">
  <b>Reduza o gasto de tokens dos agentes em 80%.</b> O Graphify Cloud é uma memória sempre ativa que governa seus agentes, mantém a qualidade do código alta e prova a correção com verificação formal. <a href="https://app.graphify.com/login"><b>Comece um teste gratuito de 14 dias &rarr;</b></a>
</p>

Digite `/graphify` no seu assistente de programação com IA e ele mapeia o seu projeto inteiro (código, documentos, PDFs, imagens, vídeos) em um **grafo de conhecimento** que você pode **consultar em vez de fazer grep** nos arquivos.

- **Mapeamento de código grátis, totalmente local.** O código é analisado com AST do tree-sitter: determinístico, sem LLM, nada sai da sua máquina. (Documentos, PDFs, imagens e vídeo usam o modelo do seu assistente, ou uma chave de API configurada, para uma passagem semântica.)
- **Toda aresta é explicada.** Cada conexão é marcada como `EXTRACTED` (explícita na fonte) ou `INFERRED` (resolvida pelo graphify), para que você possa distinguir o que foi lido diretamente do que foi inferido.
- **Não é um índice vetorial.** Sem embeddings, sem armazenamento de vetores: um grafo real que você percorre. Faça uma pergunta, trace o caminho entre duas coisas ou explique um conceito.

> [!NOTE]
> **Quer isso sempre ativo?** O [Graphify Cloud](https://app.graphify.com/login) mantém o grafo ativo em todo o seu SDLC: suporte a monorepo e multi-repositório, verificação formal e revisão de código com uma visão panorâmica do seu SDLC, além de conectores para Sentry, Jira e mais, para que incidentes e tickets fiquem no mesmo grafo que o seu código. **[Comece um teste gratuito de 14 dias em app.graphify.com](https://app.graphify.com/login)**.

<p align="center">
  <img src="https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/graph-hero.png" alt="graphify's interactive graph.html showing the FastAPI codebase as a force-directed knowledge graph with a legend of detected communities" width="900">
</p>
<p align="center">
  <em>A base de código do FastAPI mapeada pelo graphify. Cada nó é um conceito, as cores são comunidades detectadas, e tudo é clicável em graph.html.</em>
</p>

**Comece agora** (30 segundos). Precisa de Python 3.10+ e uv (ou pipx):

```bash
uv tool install graphifyy      # install the CLI (or: pipx install graphifyy)
graphify install               # detects your assistant and registers the skill
```

Depois, no seu assistente de IA:

```
/graphify .
```

Pronto. Você recebe **três arquivos**:

```
graphify-out/
├── graph.html       open in any browser: click nodes, filter, search
├── GRAPH_REPORT.md  the highlights: key concepts, surprising connections, suggested questions
└── graph.json       the full graph: query it anytime without re-reading your files
```

O grafo persistido inclui `graph.schema_version` para que integrações possam detectar
mudanças de formato incompatíveis, além de `graph.graphify_version` identificando a
versão do Graphify que o produziu.

**Uma instalação, qualquer assistente, qualquer SO.** Claude Code, Cursor, Codex, Gemini CLI, GitHub Copilot e mais de 20 outros, no macOS, Linux e Windows: [escolha sua plataforma](#install).

---

## Veja em ação

<p align="center">
  <img src="https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/demo-path.svg" alt="graphify path query: a terminal asks for the shortest path between FastAPI and ModelField, and the answer lights up hop by hop across the knowledge graph" width="900">
</p>

Depois que o grafo é construído, você o consulta em vez de ler arquivos. Saída real, graphify executado na base de código do FastAPI mostrada acima:

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

Toda aresta carrega uma **marca de confiança** (`EXTRACTED` = explícita na fonte, `INFERRED` = derivada por resolução), para que você possa distinguir o que foi lido diretamente do que foi inferido. `graphify query "<question>"` retorna um subgrafo com escopo para uma pergunta em linguagem simples, e `graphify path A B` traça como duas coisas quaisquer se conectam.

---

## O que ele faz

O que você obtém de imediato:

| Recurso | O que você obtém |
|---|---|
| **God nodes** | Os conceitos mais conectados, para você ver por onde tudo flui |
| **Comunidades** | O grafo dividido em subsistemas (Leiden), com rótulos sem LLM |
| **Links entre arquivos** | `calls` / `imports` / `inherits` / `mixes_in` resolvidos em ~40 linguagens via AST do tree-sitter |
| **Query, path, explain** | Faça uma pergunta, trace o caminho entre duas coisas ou explique um conceito, tudo contra `graph.json` |
| **Justificativa + refs de docs** | Comentários `# NOTE:` / `# WHY:` e citações de ADR/RFC se tornam nós de primeira classe ligados ao código |
| **Além do código** | Documentos, PDFs, imagens e vídeo/áudio mapeiam todos no mesmo grafo |
| **Local em primeiro lugar** | O código é analisado localmente com tree-sitter (sem LLM, nada sai da sua máquina); apenas a passagem semântica sobre docs/mídia chama um backend, e só se você configurar um |

> [!TIP]
> Executando isso em muitos repositórios ou em um monorepo? O [Graphify Cloud](https://app.graphify.com/login) faz isso continuamente e reduz o gasto de tokens dos agentes em 80%, com links multi-repositório, revisão de código em todo o SDLC, verificação formal e conectores Sentry/Jira. [Comece um teste gratuito de 14 dias &rarr;](https://app.graphify.com/login)

---

## Benchmarks: 0.497 recall@10, 0 LLM credits

| Benchmark | Métrica | graphify | Campo |
|---|---|---|---|
| LOCOMO (n=300) | recall@10 | **0.497** | mem0 0.048, supermemory 0.149 |
| LOCOMO (n=300) | precisão de QA | 45.3% | supermemory 49.7%, mem0 27.3% |
| LongMemEval-S (n=50) | precisão de QA | **76%** | empatado com RAG denso |
| ERPNext cross-tool (n=6) | cobertura de fatos-chave | **82.0%** | baseline grep/read 70.8% |
| Construção do grafo | créditos de LLM | **0** | por token na maioria dos sistemas |

Todos os sistemas rodaram no mesmo harness com o mesmo modelo e orçamentos, avaliados por um juiz validado às cegas contra um segundo juiz (90.6% de concordância, kappa de Cohen 0.81). Tabelas completas por sistema, o resultado de inteligência de código e comandos de reprodução: **[BENCHMARKS.md](../../BENCHMARKS.md)**.

---

## Documentação

Guias completos e referência ficam em **[docs.graphify.com](https://docs.graphify.com)**:

- **[Início rápido](https://docs.graphify.com/quickstart)**: construa seu primeiro grafo
- **[Referência da CLI](https://docs.graphify.com/reference/overview)**: todos os comandos e flags
- **[Faça melhores perguntas ao grafo](https://docs.graphify.com/guides/querying)**: padrões de consulta
- **[Configuração](https://docs.graphify.com/reference/configuration)**: variáveis de ambiente e ajustes
- **[Entradas suportadas](https://docs.graphify.com/concepts/supported-inputs)**: linguagens e tipos de arquivo
- **[Fluxos de equipe](https://docs.graphify.com/guides/team-workflows)** e **[Revisão de PR](https://docs.graphify.com/guides/pull-requests)**
- **[Solução de problemas](https://docs.graphify.com/troubleshooting)** e **[Como funciona](https://docs.graphify.com/concepts/architecture)**

---

## Pré-requisitos

| Requisito | Mínimo | Verificar | Instalar |
|---|---|---|---|
| Python | 3.10+ | `python --version` | [python.org](https://www.python.org/downloads/) |
| uv *(recomendado)* | qualquer | `uv --version` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| pipx *(alternativa)* | qualquer | `pipx --version` | `pip install pipx` |

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
> **Pacote oficial:** O pacote no PyPI é `graphifyy` (com y duplo). Outros pacotes `graphify*` no PyPI não são afiliados. O comando da CLI continua sendo `graphify`.

O repositório oficial de código-fonte é [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify).

O início rápido de dois comandos está no topo deste README. Esta seção cobre os métodos de instalação, instalações com escopo de projeto e todas as plataformas suportadas.

**Métodos de instalação** (escolha um):

```bash
uv tool install graphifyy   # recommended, isolated env (if 'graphify' isn't found after, run: uv tool update-shell)
pipx install graphifyy      # alternative
pip install graphifyy       # may need PATH setup, see Troubleshooting below
```

Depois execute `graphify install` uma vez. Ele detecta qual assistente você usa e registra a skill, então não há configuração por assistente. Abra seu assistente de IA e digite `/graphify .`

Para instalar a skill do assistente no repositório atual em vez do seu perfil de
usuário, adicione `--project`:

```bash
graphify install --project
graphify install --project --platform codex
```

Instalações com escopo de projeto gravam no diretório atual, por exemplo
`.claude/skills/graphify/SKILL.md` ou `.agents/skills/graphify/SKILL.md` (além de um
sidecar `references/` que a skill carrega sob demanda), e
imprimem uma dica de `git add` para arquivos que podem ser commitados.
Comandos por plataforma que suportam instalações com escopo de projeto aceitam a mesma flag,
por exemplo `graphify claude install --project` ou `graphify codex install --project`.

> [!TIP]
> Esbarrou em `command not found`, um problema de `pip` no Mac/Windows, aspas no PowerShell, uso de `uvx`, peculiaridades de PATH em git-hook ou modo estrito? Veja **[Instalação](https://docs.graphify.com/installation)** e **[Solução de problemas](https://docs.graphify.com/troubleshooting)**.

<details>
<summary><b>Escolha sua plataforma</b> (mais de 20 assistentes, clique para expandir)</summary>

| Plataforma | Comando de instalação |
|----------|----------------|
| Claude Code (Linux/Mac) | `graphify install` |
| Claude Code (Windows) | `graphify install` (detectado automaticamente) ou `graphify install --platform windows` |
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

Usuários do Codex também precisam de `multi_agent = true` em `[features]` no `~/.codex/config.toml` para extração paralela. O CodeBuddy usa o mesmo mecanismo de ferramenta Agent e hook PreToolUse que o Claude Code. O Factory Droid usa a ferramenta `Task` para despacho paralelo de subagentes. OpenClaw e Aider usam extração sequencial (o suporte a agentes paralelos ainda é inicial nessas plataformas). O Trae usa a ferramenta Agent para despacho paralelo de subagentes e **não** suporta hooks `PreToolUse`, então o AGENTS.md é o mecanismo sempre ativo.

`--platform agents` (alias `--platform skills`) mira os locais genéricos entre frameworks do [Agent-Skills](https://github.com/anthropics/skills): o `~/.agents/skills/` global do usuário da especificação (lido por `npx skills` e frameworks compatíveis com a especificação) para uma instalação global, e `./.agents/skills/` para uma instalação de projeto (`--project`). O `graphify install` puro permanece de plataforma única (Claude Code) por design: use a plataforma nomeada `agents` quando quiser que a skill seja descobrível por qualquer framework que leia `.agents/skills`.

O Pi não tem hook `PreToolUse`, então `graphify pi guard install` registra uma extensão nativa do Pi (via o próprio `pi install <package directory>` do Pi) que executa o `graphify hook-guard` instalado antes das chamadas `read`, `grep`, `find` e `bash` de busca do Pi. As decisões de grafo atualizado/desatualizado e a negação de leitura indexada uma vez por sessão com `GRAPHIFY_HOOK_STRICT=1` vêm dessa mesma política, então o Pi corresponde ao comportamento de hook do Claude Code; a orientação chega como uma mensagem de direcionamento `<system-reminder source="graphify">`. Ele precisa do Pi 0.58.4 ou mais novo: versões anteriores deixam uma mensagem de direcionamento pular o resto de um lote de chamadas de ferramenta paralelas. O pacote vem dentro da instalação do Graphify, então instale o Graphify de forma persistente (`uv tool install graphifyy` ou `pipx install graphifyy`, não `uvx`), reinicie o Pi após instalar ou atualizar, e remova-o com `graphify pi guard uninstall`. Apenas alvos de arquivo locais são inspecionados; o hook precisa de `graphify` em uma entrada de `PATH` absoluta fora do projeto, é limitado a uma chamada de dois segundos, 256 KiB de entrada/64 KiB de saída, e falha de forma aberta. O mesmo pacote também carrega no [Oh My Pi](https://github.com/can1357/oh-my-pi): `omp plugin install "$(graphify pi guard path)"`. O caminho registrado contém a versão do Python e o venv, então execute `graphify pi guard install` novamente após alterar qualquer um deles, e remova a entrada antiga com `pi remove <old path>`.

> O Codex usa `$graphify` em vez de `/graphify`.

</details>

<details>
<summary><b>Extras opcionais</b> (instale apenas o que precisar)</summary>

| Extra | O que adiciona | Instalar |
|---|---|---|
| `pdf` | Extração de PDF | `uv tool install "graphifyy[pdf]"` |
| `office` | Suporte a `.docx` e `.xlsx` | `uv tool install "graphifyy[office]"` |
| `google` | Renderização de Google Sheets | `uv tool install "graphifyy[google]"` |
| `video` | Transcrição de vídeo/áudio (faster-whisper + yt-dlp) | `uv tool install "graphifyy[video]"` |
| `mcp` | Servidor MCP stdio | `uv tool install "graphifyy[mcp]"` |
| `neo4j` | Suporte a push para Neo4j | `uv tool install "graphifyy[neo4j]"` |
| `falkordb` | Suporte a push para FalkorDB | `uv tool install "graphifyy[falkordb]"` |
| `svg` | Exportação de grafo em SVG | `uv tool install "graphifyy[svg]"` |
| `leiden` | Detecção de comunidades Leiden (graspologic no Python < 3.13; backend nativo no 3.13+) | `uv tool install "graphifyy[leiden]"` |
| `ollama` | Inferência local com Ollama | `uv tool install "graphifyy[ollama]"` |
| `openai` | APIs OpenAI / compatíveis com OpenAI | `uv tool install "graphifyy[openai]"` |
| `gemini` | API do Google Gemini | `uv tool install "graphifyy[gemini]"` |
| `anthropic` | API Anthropic Claude (`--backend claude`, usa `ANTHROPIC_API_KEY`) | `uv tool install "graphifyy[anthropic]"` |
| `bedrock` | AWS Bedrock (usa IAM, sem chave de API) | `uv tool install "graphifyy[bedrock]"` |
| `azure` | Azure OpenAI Service (`--backend azure`, usa `AZURE_OPENAI_API_KEY` + `AZURE_OPENAI_ENDPOINT`) | `uv tool install "graphifyy[openai]"` |
| `sql` | Extração de esquema SQL | `uv tool install "graphifyy[sql]"` |
| `postgres` | Introspecção ao vivo de PostgreSQL (`--postgres DSN`) | `uv tool install "graphifyy[postgres]"` |
| `dm` | Extração de AST de BYOND DreamMaker `.dm`/`.dme` (pode precisar de um compilador C + `python3-dev` se nenhum wheel corresponder à sua plataforma) | `uv tool install "graphifyy[dm]"` |
| `terraform` | Extração de AST de Terraform / HCL `.tf`/`.tfvars`/`.hcl` | `uv tool install "graphifyy[terraform]"` |
| `pascal` | Extração de AST de Pascal / Delphi `.pas`/`.dpr`/`.dpk`/`.inc` (arestas `calls`/`inherits` mais precisas; recorre a um extrator de regex quando ausente) | `uv tool install "graphifyy[pascal]"` |
| `ocaml` | Extração de AST de OCaml `.ml`/`.mli` | `uv tool install "graphifyy[ocaml]"` |
| `commonlisp` | Extração de AST de Common Lisp `.lisp`/`.cl`/`.lsp`/`.asd` | `uv tool install "graphifyy[commonlisp]"` |
| `robot` | Extração de Robot Framework `.robot`/`.resource` (suítes, casos de teste, keywords, arestas de chamada de keyword e de importação de resource/library) | `uv tool install "graphifyy[robot]"` |
| `chinese` | Segmentação de consulta em chinês (jieba) | `uv tool install "graphifyy[chinese]"` |
| `all` | Tudo acima | `uv tool install "graphifyy[all]"` |

</details>

---

## Faça seu assistente sempre usar o grafo

Execute isto uma vez no seu projeto depois de construir um grafo:

Execute `graphify <platform> install` uma vez no seu projeto, por exemplo `graphify claude install` ou `graphify codex install` (ou `graphify install --platform <name>`).

Isso grava um pequeno arquivo de configuração que diz ao seu assistente para consultar o grafo de conhecimento em perguntas sobre a base de código, preferindo consultas com escopo como `graphify query "<question>"` em vez de ler o relatório completo ou fazer grep em arquivos brutos.

- **Plataformas com hook** (Claude Code, Gemini CLI): um hook dispara automaticamente antes de chamadas de ferramenta de busca (e, no Claude Code, antes de ler arquivos-fonte um a um via as ferramentas Read/Glob) e empurra seu assistente para o caminho do grafo.
- **Plataformas com arquivo de instruções** (Codex, OpenCode, Cursor, etc.): arquivos de instrução persistentes (`AGENTS.md`, `.cursor/rules/`, etc.) fornecem a mesma orientação de consulta em primeiro lugar.

O `GRAPH_REPORT.md` continua disponível para revisão ampla de arquitetura.

Exatamente quais arquivos cada plataforma grava (o `CODEBUDDY.md` + hooks `PreToolUse` do CodeBuddy, o `AGENTS.md` do Codex, o plugin nativo `.kilo` do Kilo, a regra `alwaysApply` do Cursor, e assim por diante) é coberto em **[Configuração sempre ativa](https://docs.graphify.com/guides/always-on)**.

Para remover o graphify de todas as plataformas de uma vez: `graphify uninstall` (adicione `--purge` para também excluir `graphify-out/`). Ou use o comando por plataforma (por exemplo, `graphify claude uninstall`).

### Skills de CLI ou instruções de MCP?

As instruções instaladas por `graphify install` e aquelas fornecidas com uma conexão MCP do Graphify descrevem maneiras diferentes de consultar um grafo:

| Configuração | Orientação a usar | Acesso de consulta |
|---|---|---|
| CLI local e skill de assistente instalada | As instruções de plataforma escritas por `graphify install` | Execute `graphify query`, `graphify path` e `graphify explain` contra o grafo local (`graphify-out/` por padrão). |
| Servidor MCP do Graphify conectado | As instruções da conexão e as ferramentas listadas por esse servidor | Chame as ferramentas MCP listadas contra o grafo servido por essa conexão. Os nomes e descrições das ferramentas vêm do servidor. |

Ambas incentivam consultas com escopo ao grafo antes de buscas amplas na fonte. Escolha as instruções que correspondem às ferramentas que seu assistente realmente consegue acessar; nenhum dos blocos estabelece uma regra universal de precedência para os arquivos de instrução do seu assistente. Se você usa as duas integrações, identifique qual grafo cada uma consulta e escolha um caminho de consulta principal em vez de copiar dois blocos de instrução incondicionais no `AGENTS.md`.

`graphify install` instala a integração local do assistente; ele não estabelece uma conexão MCP. Um cliente MCP não precisa executar consultas locais da CLI para usar seu servidor conectado. Um servidor hospedado localmente ainda precisa da própria instalação e grafo do Graphify, enquanto uma conexão hospedada pode servir um grafo que não está presente no diretório de trabalho do cliente. Se as ferramentas esperadas estiverem faltando, verifique a instalação relevante da CLI ou a conexão MCP em vez de tratar as instruções da outra configuração como intercambiáveis.

---

## O que há no relatório

O `GRAPH_REPORT.md` resume os god nodes, as comunidades e os caminhos principais para revisão ampla de arquitetura. Como o grafo é construído e o que ele contém: **[Como o graphify funciona](https://docs.graphify.com/concepts/architecture)**.

---

## Quais arquivos ele processa: ~40 languages

O graphify analisa ~40 linguagens de programação localmente com AST do tree-sitter, e mapeia documentos, PDFs, imagens e áudio/vídeo através de uma passagem semântica opcional. Lista completa: **[Entradas suportadas](https://docs.graphify.com/concepts/supported-inputs)**.

---

## Comandos comuns

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

Veja a [referência completa de comandos](#full-command-reference) abaixo.

---

## Ignorando arquivos

O graphify respeita `.gitignore` e suporta padrões `--exclude` e um `.graphifyignore` de projeto. Detalhes: **[Configuração](https://docs.graphify.com/reference/configuration)**.


## Configuração do projeto

Crie um `.graphifyrc` na raiz da varredura para configurações que pertencem ao projeto e não a uma única execução. Um `key=value` por linha; linhas começando com `#` são comentários.

**Extensões ambíguas.** Algumas extensões significam linguagens diferentes em projetos diferentes: `.inc` é PHP no pfSense, Pascal em uma árvore Delphi, SQL ou assembly em outros lugares; `.h` é C ou C++; `.m` é Objective-C ou MATLAB. O graphify tem que escolher um padrão global, e quando escolhe errado o arquivo não falha: ele é analisado como a linguagem errada e produz um punhado de nós incidentais, então o grafo parece populado enquanto os símbolos reais estão faltando. Declare o que a extensão significa no seu repositório:

```
# .graphifyrc
# A language name:
language.inc=php
# Or an extension graphify already knows:
language.tpl=.ts
# Baked into the git hooks (see Team setup):
viz_node_limit=0
```

A declaração flui pela classificação, seleção de extrator, gramática e resolução, importações, `graphify watch` e o cache de AST (um arquivo reanalisado sob uma linguagem diferente nunca reutiliza a entrada antiga), e o mesmo `.graphifyrc` é lido por `extract`, `update`, os hooks, o servidor MCP e a skill `/graphify`. Um erro de digitação é reportado uma vez no stderr e a varredura continua com os padrões. Como as declarações interagem com cache, reconstruções incrementais e resolução de importações: **[Configuração](https://docs.graphify.com/reference/configuration)**.

---

## Configuração de equipe

Faça commit ou compartilhe o grafo para que toda a sua equipe consulte o mesmo contexto, e revise pull requests com contexto do grafo. Veja **[Compartilhe contexto com sua equipe](https://docs.graphify.com/guides/team-workflows)** e **[Revise pull requests](https://docs.graphify.com/guides/pull-requests)**.

---

## Usando o grafo diretamente

Além do seu assistente de IA, consulte `graph.json` diretamente da CLI com `graphify query`, `graphify path` e `graphify explain`. Um nome que corresponde a vários nós é recusado com os candidatos listados em vez de adivinhado. Scripts podem ler o resultado pelo código de saída: `0` uma resposta, `3` um nome ambíguo, `4` nenhum nó correspondente. Veja **[Faça melhores perguntas ao grafo](https://docs.graphify.com/guides/querying)** e a **[referência de query](https://docs.graphify.com/reference/query)**.

---

## Variáveis de ambiente

Backends, chaves de API, comportamento de hooks e ajustes são controlados por variáveis de ambiente. Tabela completa: **[Configuração](https://docs.graphify.com/reference/configuration)**.

---

## Privacidade

- **Arquivos de código**: processados localmente via tree-sitter. Nada sai da sua máquina. Um corpus somente de código não requer chave de API: `graphify extract` roda totalmente offline. Em um repositório misto, adicione `--code-only` para indexar apenas o código e pular os docs/PDFs/imagens que de outra forma precisariam de uma LLM.
- **Vídeo / áudio**: transcritos localmente com faster-whisper. Nada sai da sua máquina.
- **Docs, PDFs, imagens**: enviados ao seu assistente de IA para extração semântica (via a skill `/graphify`, usando qualquer modelo que sua sessão de IDE execute). O `graphify extract` headless requer `GEMINI_API_KEY` / `GOOGLE_API_KEY` (Gemini), `MOONSHOT_API_KEY` (Kimi), `ANTHROPIC_API_KEY` (Claude), `OPENAI_API_KEY` (OpenAI), `DEEPSEEK_API_KEY` (DeepSeek), uma instância Ollama em execução (`OLLAMA_BASE_URL`), credenciais AWS via a cadeia de provedores padrão (Bedrock - sem chave de API necessária, usa IAM), ou o binário da CLI `claude` (Claude Code - sem chave de API necessária, usa sua assinatura do Claude). A flag `--dedup-llm` usa a mesma chave.
- **Residência de dados**: `graphify extract` detecta automaticamente qual provedor usar com base em qual chave de API está definida (prioridade: Gemini → Kimi → Claude → OpenAI → DeepSeek → Azure → Bedrock → Ollama). Para código com requisitos de residência de dados, use `--backend ollama` (totalmente local) ou passe uma flag `--backend` explícita. Kimi (`MOONSHOT_API_KEY`) roteia para servidores da Moonshot AI na China.
- **Sem telemetria**, sem rastreamento de uso, sem analytics.
- **Registro de consultas**: cada chamada `graphify query`, `graphify path`, `graphify explain` e MCP `query_graph` é registrada em `~/.cache/graphify-queries.log` no formato JSON Lines (timestamp, pergunta, corpus, nós retornados, duração). Respostas completas de subgrafo **não** são armazenadas por padrão. Defina `GRAPHIFY_QUERY_LOG_DISABLE=1` para optar por não participar, ou `GRAPHIFY_QUERY_LOG=/dev/null` para silenciar sem desativar o caminho de código.

---

## Solução de problemas

Problemas comuns de instalação e extração e suas correções: **[Solução de problemas](https://docs.graphify.com/troubleshooting)**.

---

## Full command reference

Todos os comandos e flags, com exemplos: **[Referência da CLI](https://docs.graphify.com/reference/overview)**.

---

## Saiba mais

- [docs.graphify.com](https://docs.graphify.com): documentação completa: guias, referência de comandos e integrações
- [Como funciona](../how-it-works.md): o pipeline de extração, detecção de comunidades, pontuação de confiança, benchmarks
- [ARCHITECTURE.md](../../ARCHITECTURE.md): detalhamento de módulos, como adicionar uma linguagem
- [Integrações opcionais](../docker-mcp-sqlite.md): Docker MCP Toolkit + SQLite
- [The Memory Layer](https://safishamsi.gumroad.com/l/qetvlo): o livro sobre as ideias por trás do graphify, a arquitetura de ponta a ponta

---

## Graphify Cloud

O [**Graphify Cloud**](https://app.graphify.com/login) é a camada sempre ativa construída sobre o graphify. Em vez de um grafo que você reconstrói sob demanda por pasta, ele mantém um grafo ativo em todo o seu ciclo de vida de desenvolvimento de software:

- **80% menos tokens**: memória sempre ativa significa que seus agentes param de reler e reexplicar a base de código a cada sessão.
- **Monorepo e multi-repositório**: um grafo conectado em cada serviço e repositório, não um grafo por pasta.
- **Verificação formal**: verifique invariantes de arquitetura e de dependências contra o grafo ativo.
- **Revisão de código com uma visão panorâmica do seu SDLC**: veja como uma mudança se propaga por todo o sistema antes de fazer o merge.
- **Conectores de SDLC**: traga Sentry, Jira e mais, para que incidentes, tickets e código vivam em um único grafo.
- **Sempre ativo**: atualiza continuamente em segundo plano em código, docs e reuniões.

**[Comece um teste gratuito de 14 dias em app.graphify.com &rarr;](https://app.graphify.com/login)**

---

## Contribuindo

Contribuições são bem-vindas. Veja **[CONTRIBUTING.md](../../CONTRIBUTING.md)** para a configuração de desenvolvimento, os comandos de teste e de paridade com a CI, o fluxo de trabalho do git, e o que faz uma contribuição forte (exemplos resolvidos e relatórios de bugs de extração são os mais úteis). Arquitetura e como adicionar uma linguagem: [ARCHITECTURE.md](../../ARCHITECTURE.md).

Novo por aqui? Diga oi no [Discord](https://discord.gg/graphify) ou nas [GitHub Discussions](https://github.com/Graphify-Labs/graphify/discussions).

---

## Colaboradores

<a href="https://github.com/Graphify-Labs/graphify/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=Graphify-Labs/graphify" alt="graphify contributors" />
</a>

Feito com [contrib.rocks](https://contrib.rocks).

---

## Traduções

O README está disponível em 32 idiomas. Use o seletor de idiomas no topo deste arquivo para lê-lo no seu, ou navegue em [`docs/translations/`](./). Para melhorar uma tradução ou adicionar uma nova, abra um pull request contra o arquivo correspondente lá.

---

## Construindo sobre o graphify

Está construindo algo no ecossistema do graphify? Isso é incentivado. Se o seu projeto usa "graphify" no nome (por exemplo `graphify-dashboard` ou `graphify-action`), adicione uma breve nota ao seu README esclarecendo que é feito pela comunidade e não é afiliado nem endossado pela Graphify Labs. "graphify" e o logo do graphify são marcas da Graphify Labs; não os use de uma forma que implique status oficial.

---

## Comunidade e links

<p align="center">
  <a href="https://graphify.com"><img src="https://img.shields.io/badge/Website-graphify.com-4c1?style=flat&logo=googlechrome&logoColor=white" alt="Website"/></a>
  <a href="https://discord.gg/graphify"><img src="https://img.shields.io/badge/Discord-Join-5865F2?style=flat&logo=discord&logoColor=white" alt="Discord"/></a>
  <a href="https://x.com/graphify"><img src="https://img.shields.io/badge/X-graphify-000000?logo=x&logoColor=white" alt="X"/></a>
  <a href="https://www.youtube.com/@graphifylabs"><img src="https://img.shields.io/badge/YouTube-Graphify%20Labs-FF0000?style=flat&logo=youtube&logoColor=white" alt="YouTube"/></a>
  <a href="https://github.com/sponsors/safishamsi"><img src="https://img.shields.io/badge/sponsor-safishamsi-ea4aaa?logo=github-sponsors" alt="Sponsor"/></a>
  <a href="https://safishamsi.gumroad.com/l/qetvlo"><img src="https://img.shields.io/badge/Book-The%20Memory%20Layer-2ea44f?style=flat&logo=gitbook&logoColor=white" alt="The Memory Layer"/></a>
</p>
