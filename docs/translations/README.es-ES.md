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
  <b>Reduce el gasto de tokens de tus agentes en un 80%.</b> Graphify Cloud es una memoria siempre activa que gobierna tus agentes, mantiene alta la calidad del código y demuestra la correctitud con verificación formal. <a href="https://app.graphify.com/login"><b>Comienza una prueba gratuita de 14 días &rarr;</b></a>
</p>

Escribe `/graphify` en tu asistente de programación con IA y mapea todo tu proyecto (código, documentos, PDF, imágenes, vídeos) en un **grafo de conocimiento** que puedes **consultar en lugar de usar grep** sobre los archivos.

- **Mapea el código gratis, totalmente local.** El código se analiza con AST de tree-sitter: determinista, sin LLM, nada sale de tu máquina. (Los documentos, PDF, imágenes y vídeo usan el modelo de tu asistente, o una clave de API configurada, para una pasada semántica.)
- **Cada arista se explica.** Cada conexión se etiqueta como `EXTRACTED` (explícita en la fuente) o `INFERRED` (resuelta por graphify), para que puedas distinguir lo que se leyó directamente de lo que se infirió.
- **No es un índice vectorial.** Sin embeddings, sin almacén de vectores: un grafo real que recorres. Haz una pregunta, traza la ruta entre dos cosas o explica un concepto.

> [!NOTE]
> **¿Lo quieres siempre activo?** [Graphify Cloud](https://app.graphify.com/login) mantiene el grafo vivo a lo largo de todo tu SDLC: soporte para monorepo y entre repositorios, verificación formal y revisión de código con una vista panorámica de tu SDLC, además de conectores para Sentry, Jira y más, para que los incidentes y los tickets vivan en el mismo grafo que tu código. **[Comienza una prueba gratuita de 14 días en app.graphify.com](https://app.graphify.com/login)**.

<p align="center">
  <img src="https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/graph-hero.png" alt="graphify's interactive graph.html showing the FastAPI codebase as a force-directed knowledge graph with a legend of detected communities" width="900">
</p>
<p align="center">
  <em>El código de FastAPI mapeado por graphify. Cada nodo es un concepto, los colores son comunidades detectadas, y todo es clicable en graph.html.</em>
</p>

**Primeros pasos** (30 segundos). Necesitas Python 3.10+ y uv (o pipx):

```bash
uv tool install graphifyy      # install the CLI (or: pipx install graphifyy)
graphify install               # detects your assistant and registers the skill
```

Luego, en tu asistente de IA:

```
/graphify .
```

Eso es todo. Obtienes **tres archivos**:

```
graphify-out/
├── graph.html       open in any browser: click nodes, filter, search
├── GRAPH_REPORT.md  the highlights: key concepts, surprising connections, suggested questions
└── graph.json       the full graph: query it anytime without re-reading your files
```

El grafo persistido incluye `graph.schema_version` para que las integraciones puedan detectar
cambios de formato incompatibles, además de `graph.graphify_version` que identifica la
versión de Graphify que lo produjo.

**Una instalación, cualquier asistente, cualquier sistema operativo.** Claude Code, Cursor, Codex, Gemini CLI, GitHub Copilot y más de 20 más, en macOS, Linux y Windows: [elige tu plataforma](#install).

---

## Míralo en acción

<p align="center">
  <img src="https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/demo-path.svg" alt="graphify path query: a terminal asks for the shortest path between FastAPI and ModelField, and the answer lights up hop by hop across the knowledge graph" width="900">
</p>

Una vez construido el grafo, lo consultas en lugar de leer archivos. Salida real, graphify ejecutado sobre el código de FastAPI mostrado arriba:

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

Cada arista lleva una **etiqueta de confianza** (`EXTRACTED` = explícita en la fuente, `INFERRED` = derivada por resolución), para que puedas distinguir lo que se leyó directamente de lo que se infirió. `graphify query "<question>"` devuelve un subgrafo acotado para una pregunta en lenguaje natural, y `graphify path A B` traza cómo se conectan dos cosas cualesquiera.

---

## Qué hace

Lo que obtienes de inmediato:

| Capacidad | Qué obtienes |
|---|---|
| **Nodos dios** | Los conceptos más conectados, para que veas por dónde fluye todo |
| **Comunidades** | El grafo dividido en subsistemas (Leiden), con etiquetas sin LLM |
| **Enlaces entre archivos** | `calls` / `imports` / `inherits` / `mixes_in` resueltos en ~40 lenguajes mediante AST de tree-sitter |
| **Query, path, explain** | Haz una pregunta, traza la ruta entre dos cosas o explica un concepto, todo contra `graph.json` |
| **Justificación + referencias de docs** | Los comentarios `# NOTE:` / `# WHY:` y las citas de ADR/RFC se convierten en nodos de primera clase enlazados al código |
| **Más allá del código** | Documentos, PDF, imágenes y vídeo/audio, todos se mapean en el mismo grafo |
| **Local primero** | El código se analiza localmente con tree-sitter (sin LLM, nada sale de tu máquina); solo la pasada semántica sobre documentos/medios llama a un backend, y solo si configuras uno |

> [!TIP]
> ¿Ejecutando esto en muchos repositorios o en un monorepo? [Graphify Cloud](https://app.graphify.com/login) lo hace de forma continua y reduce el gasto de tokens de los agentes en un 80%, con enlaces entre repositorios, revisión de código en todo el SDLC, verificación formal y conectores de Sentry/Jira. [Comienza una prueba gratuita de 14 días &rarr;](https://app.graphify.com/login)

---

## Benchmarks: 0.497 recall@10, 0 LLM credits

| Benchmark | Métrica | graphify | Campo |
|---|---|---|---|
| LOCOMO (n=300) | recall@10 | **0.497** | mem0 0.048, supermemory 0.149 |
| LOCOMO (n=300) | precisión de QA | 45.3% | supermemory 49.7%, mem0 27.3% |
| LongMemEval-S (n=50) | precisión de QA | **76%** | empatado con RAG denso |
| ERPNext cross-tool (n=6) | cobertura de hechos clave | **82.0%** | línea base grep/read 70.8% |
| Graph build | créditos de LLM | **0** | por token en la mayoría de los sistemas |

Todos los sistemas se ejecutaron en el mismo arnés con el mismo modelo y presupuestos, puntuados por un juez validado a ciegas contra un segundo juez (90.6% de acuerdo, kappa de Cohen 0.81). Tablas completas por sistema, el resultado de inteligencia de código y los comandos de reproducción: **[BENCHMARKS.md](../../BENCHMARKS.md)**.

---

## Documentación

Las guías completas y la referencia viven en **[docs.graphify.com](https://docs.graphify.com)**:

- **[Quickstart](https://docs.graphify.com/quickstart)**: construye tu primer grafo
- **[Referencia de CLI](https://docs.graphify.com/reference/overview)**: cada comando y flag
- **[Haz mejores preguntas al grafo](https://docs.graphify.com/guides/querying)**: patrones de consulta
- **[Configuración](https://docs.graphify.com/reference/configuration)**: variables de entorno y ajuste
- **[Entradas compatibles](https://docs.graphify.com/concepts/supported-inputs)**: lenguajes y tipos de archivo
- **[Flujos de trabajo en equipo](https://docs.graphify.com/guides/team-workflows)** y **[revisión de PR](https://docs.graphify.com/guides/pull-requests)**
- **[Resolución de problemas](https://docs.graphify.com/troubleshooting)** y **[Cómo funciona](https://docs.graphify.com/concepts/architecture)**

---

## Requisitos previos

| Requisito | Mínimo | Comprobar | Instalar |
|---|---|---|---|
| Python | 3.10+ | `python --version` | [python.org](https://www.python.org/downloads/) |
| uv *(recomendado)* | cualquiera | `uv --version` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| pipx *(alternativa)* | cualquiera | `pipx --version` | `pip install pipx` |

**Instalación rápida en macOS (Homebrew):**
```bash
brew install python@3.12 uv
```

**Instalación rápida en Windows:**
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
> **Paquete oficial:** El paquete de PyPI es `graphifyy` (doble y). Otros paquetes `graphify*` en PyPI no están afiliados. El comando de la CLI sigue siendo `graphify`.

El repositorio fuente oficial es [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify).

El quickstart de dos comandos está al principio de este README. Esta sección cubre los métodos de instalación, las instalaciones acotadas al proyecto y todas las plataformas compatibles.

**Métodos de instalación** (elige uno):

```bash
uv tool install graphifyy   # recommended, isolated env (if 'graphify' isn't found after, run: uv tool update-shell)
pipx install graphifyy      # alternative
pip install graphifyy       # may need PATH setup, see Troubleshooting below
```

Luego ejecuta `graphify install` una vez. Detecta qué asistente usas y registra la skill, por lo que no hay configuración por asistente. Abre tu asistente de IA y escribe `/graphify .`

Para instalar la skill del asistente en el repositorio actual en lugar de tu perfil
de usuario, añade `--project`:

```bash
graphify install --project
graphify install --project --platform codex
```

Las instalaciones acotadas al proyecto escriben bajo el directorio actual, por ejemplo
`.claude/skills/graphify/SKILL.md` o `.agents/skills/graphify/SKILL.md` (más un
sidecar `references/` que la skill carga bajo demanda), e
imprimen una pista de `git add` para los archivos que se pueden confirmar.
Los comandos por plataforma que admiten instalaciones acotadas al proyecto aceptan el mismo flag,
por ejemplo `graphify claude install --project` o `graphify codex install --project`.

> [!TIP]
> ¿Te topas con `command not found`, un problema de `pip` en Mac/Windows, comillas en PowerShell, uso de `uvx`, peculiaridades de PATH en git-hooks, o el modo estricto? Consulta **[Instalación](https://docs.graphify.com/installation)** y **[Resolución de problemas](https://docs.graphify.com/troubleshooting)**.

<details>
<summary><b>Elige tu plataforma</b> (más de 20 asistentes, haz clic para expandir)</summary>

| Plataforma | Comando de instalación |
|----------|----------------|
| Claude Code (Linux/Mac) | `graphify install` |
| Claude Code (Windows) | `graphify install` (auto-detectado) o `graphify install --platform windows` |
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
| Pi coding agent | `graphify install --platform pi`, más `graphify pi guard install` para el guard nativo |
| Cursor | `graphify cursor install` |
| Devin CLI | `graphify devin install` |
| Google Antigravity | `graphify antigravity install` |

Los usuarios de Codex también necesitan `multi_agent = true` bajo `[features]` en `~/.codex/config.toml` para la extracción paralela. CodeBuddy usa el mismo mecanismo de herramienta Agent y hook PreToolUse que Claude Code. Factory Droid usa la herramienta `Task` para el despacho paralelo de subagentes. OpenClaw y Aider usan extracción secuencial (el soporte de agentes en paralelo todavía es incipiente en esas plataformas). Trae usa la herramienta Agent para el despacho paralelo de subagentes y **no** admite hooks `PreToolUse`, por lo que AGENTS.md es el mecanismo siempre activo.

`--platform agents` (alias `--platform skills`) apunta a las ubicaciones genéricas entre frameworks de [Agent-Skills](https://github.com/anthropics/skills): el `~/.agents/skills/` global de usuario de la especificación (leído por `npx skills` y los frameworks que cumplen la especificación) para una instalación global, y `./.agents/skills/` para una instalación de proyecto (`--project`). El `graphify install` simple se mantiene de una sola plataforma (Claude Code) por diseño: usa la plataforma nombrada `agents` cuando quieras que la skill sea descubrible por cualquier framework que lea `.agents/skills`.

Pi no tiene un hook `PreToolUse`, por lo que `graphify pi guard install` registra una extensión nativa de Pi (vía el propio `pi install <package directory>` de Pi) que ejecuta el `graphify hook-guard` instalado antes de las llamadas `read`, `grep`, `find` y de tipo búsqueda `bash` de Pi. Las decisiones sobre grafo fresco/obsoleto y la denegación de lectura indexada una vez por sesión de `GRAPHIFY_HOOK_STRICT=1` provienen de esa misma política, por lo que Pi iguala el comportamiento del hook de Claude Code; la orientación llega como un mensaje de dirección `<system-reminder source="graphify">`. Necesita Pi 0.58.4 o posterior: las versiones anteriores dejan que un mensaje de dirección omita el resto de un lote de llamadas de herramientas en paralelo. El paquete viene dentro de la instalación de Graphify, así que instala Graphify de forma persistente (`uv tool install graphifyy` o `pipx install graphifyy`, no `uvx`), reinicia Pi después de instalar o actualizar, y elimínalo con `graphify pi guard uninstall`. Solo se inspeccionan los objetivos de archivo locales; el hook necesita `graphify` en una entrada de `PATH` absoluta fuera del proyecto, está acotado a una llamada de dos segundos y 256 KiB de entrada/64 KiB de salida, y falla abriendo. El mismo paquete también se carga en [Oh My Pi](https://github.com/can1357/oh-my-pi): `omp plugin install "$(graphify pi guard path)"`. La ruta registrada contiene la versión de Python y el venv, así que vuelve a ejecutar `graphify pi guard install` después de cambiar cualquiera de los dos, y elimina la entrada antigua con `pi remove <old path>`.

> Codex usa `$graphify` en lugar de `/graphify`.

</details>

<details>
<summary><b>Extras opcionales</b> (instala solo lo que necesites)</summary>

| Extra | Qué añade | Instalar |
|---|---|---|
| `pdf` | Extracción de PDF | `uv tool install "graphifyy[pdf]"` |
| `office` | Soporte de `.docx` y `.xlsx` | `uv tool install "graphifyy[office]"` |
| `google` | Renderizado de Google Sheets | `uv tool install "graphifyy[google]"` |
| `video` | Transcripción de vídeo/audio (faster-whisper + yt-dlp) | `uv tool install "graphifyy[video]"` |
| `mcp` | Servidor MCP por stdio | `uv tool install "graphifyy[mcp]"` |
| `neo4j` | Soporte de push a Neo4j | `uv tool install "graphifyy[neo4j]"` |
| `falkordb` | Soporte de push a FalkorDB | `uv tool install "graphifyy[falkordb]"` |
| `svg` | Exportación de grafo en SVG | `uv tool install "graphifyy[svg]"` |
| `leiden` | Detección de comunidades Leiden (graspologic en Python < 3.13; backend nativo en 3.13+) | `uv tool install "graphifyy[leiden]"` |
| `ollama` | Inferencia local con Ollama | `uv tool install "graphifyy[ollama]"` |
| `openai` | APIs de OpenAI / compatibles con OpenAI | `uv tool install "graphifyy[openai]"` |
| `gemini` | API de Google Gemini | `uv tool install "graphifyy[gemini]"` |
| `anthropic` | API de Anthropic Claude (`--backend claude`, usa `ANTHROPIC_API_KEY`) | `uv tool install "graphifyy[anthropic]"` |
| `bedrock` | AWS Bedrock (usa IAM, sin clave de API) | `uv tool install "graphifyy[bedrock]"` |
| `azure` | Azure OpenAI Service (`--backend azure`, usa `AZURE_OPENAI_API_KEY` + `AZURE_OPENAI_ENDPOINT`) | `uv tool install "graphifyy[openai]"` |
| `sql` | Extracción de esquema SQL | `uv tool install "graphifyy[sql]"` |
| `postgres` | Introspección en vivo de PostgreSQL (`--postgres DSN`) | `uv tool install "graphifyy[postgres]"` |
| `dm` | Extracción de AST de BYOND DreamMaker `.dm`/`.dme` (puede necesitar un compilador C + `python3-dev` si ningún wheel coincide con tu plataforma) | `uv tool install "graphifyy[dm]"` |
| `terraform` | Extracción de AST de Terraform / HCL `.tf`/`.tfvars`/`.hcl` | `uv tool install "graphifyy[terraform]"` |
| `pascal` | Extracción de AST de Pascal / Delphi `.pas`/`.dpr`/`.dpk`/`.inc` (aristas `calls`/`inherits` más precisas; recurre a un extractor por regex cuando está ausente) | `uv tool install "graphifyy[pascal]"` |
| `ocaml` | Extracción de AST de OCaml `.ml`/`.mli` | `uv tool install "graphifyy[ocaml]"` |
| `commonlisp` | Extracción de AST de Common Lisp `.lisp`/`.cl`/`.lsp`/`.asd` | `uv tool install "graphifyy[commonlisp]"` |
| `robot` | Extracción de Robot Framework `.robot`/`.resource` (suites, casos de prueba, keywords, aristas de llamada a keyword e importación de recurso/librería) | `uv tool install "graphifyy[robot]"` |
| `chinese` | Segmentación de consultas en chino (jieba) | `uv tool install "graphifyy[chinese]"` |
| `all` | Todo lo anterior | `uv tool install "graphifyy[all]"` |

</details>

---

## Haz que tu asistente siempre use el grafo

Ejecuta esto una vez en tu proyecto después de construir un grafo:

Ejecuta `graphify <platform> install` una vez en tu proyecto, por ejemplo `graphify claude install` o `graphify codex install` (o `graphify install --platform <name>`).

Esto escribe un pequeño archivo de configuración que le indica a tu asistente que consulte el grafo de conocimiento para preguntas sobre el código, prefiriendo consultas acotadas como `graphify query "<question>"` antes que leer el informe completo o hacer grep sobre los archivos en bruto.

- **Plataformas con hooks** (Claude Code, Gemini CLI): un hook se dispara automáticamente antes de las llamadas de herramientas de tipo búsqueda (y, en Claude Code, antes de leer archivos fuente uno a uno mediante las herramientas Read/Glob) y orienta a tu asistente hacia la ruta del grafo.
- **Plataformas con archivos de instrucciones** (Codex, OpenCode, Cursor, etc.): los archivos de instrucciones persistentes (`AGENTS.md`, `.cursor/rules/`, etc.) aportan la misma orientación de consulta-primero.

`GRAPH_REPORT.md` sigue disponible para una revisión amplia de la arquitectura.

Exactamente qué archivos escribe cada plataforma (el `CODEBUDDY.md` + hooks `PreToolUse` de CodeBuddy, el `AGENTS.md` de Codex, el plugin nativo `.kilo` de Kilo, la regla `alwaysApply` de Cursor, etc.) se cubre en **[Configuración siempre activa](https://docs.graphify.com/guides/always-on)**.

Para eliminar graphify de todas las plataformas a la vez: `graphify uninstall` (añade `--purge` para borrar también `graphify-out/`). O usa el comando por plataforma (p. ej., `graphify claude uninstall`).

### ¿Skills de CLI o instrucciones de MCP?

Las instrucciones instaladas por `graphify install` y las que vienen con una conexión MCP de Graphify describen formas distintas de consultar un grafo:

| Configuración | Orientación a usar | Acceso de consulta |
|---|---|---|
| CLI local y skill de asistente instalada | Las instrucciones de plataforma escritas por `graphify install` | Ejecuta `graphify query`, `graphify path` y `graphify explain` contra el grafo local (`graphify-out/` por defecto). |
| Servidor MCP de Graphify conectado | Las instrucciones de la conexión y las herramientas listadas por ese servidor | Llama a las herramientas MCP listadas contra el grafo servido por esa conexión. Los nombres y descripciones de las herramientas provienen del servidor. |

Ambas fomentan consultas acotadas al grafo antes que búsquedas amplias sobre la fuente. Elige las instrucciones que coincidan con las herramientas a las que tu asistente puede acceder realmente; ninguno de los bloques establece una regla de precedencia universal para los archivos de instrucciones de tu asistente. Si usas ambas integraciones, identifica qué grafo consulta cada una y elige una ruta de consulta principal en lugar de copiar dos bloques de instrucciones incondicionales en `AGENTS.md`.

`graphify install` instala la integración local del asistente; no establece una conexión MCP. Un cliente MCP no necesita ejecutar consultas de CLI locales para usar su servidor conectado. Un servidor alojado localmente todavía necesita su propia instalación de Graphify y su grafo, mientras que una conexión alojada puede servir un grafo que no está presente en el directorio de trabajo del cliente. Si faltan las herramientas esperadas, comprueba la instalación de CLI o la conexión MCP correspondiente en lugar de tratar las instrucciones de la otra configuración como intercambiables.

---

## Qué hay en el informe

`GRAPH_REPORT.md` resume los nodos dios, las comunidades y las rutas clave para una revisión amplia de la arquitectura. Cómo se construye el grafo y qué contiene: **[Cómo funciona graphify](https://docs.graphify.com/concepts/architecture)**.

---

## Qué archivos maneja: ~40 languages

graphify analiza ~40 lenguajes de programación localmente con AST de tree-sitter, y mapea documentos, PDF, imágenes y audio/vídeo mediante una pasada semántica opcional. Lista completa: **[Entradas compatibles](https://docs.graphify.com/concepts/supported-inputs)**.

---

## Comandos comunes

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

Consulta la [referencia completa de comandos](#full-command-reference) más abajo.

---

## Ignorar archivos

graphify respeta `.gitignore` y admite patrones `--exclude` y un `.graphifyignore` del proyecto. Detalles: **[Configuración](https://docs.graphify.com/reference/configuration)**.


## Configuración del proyecto

Crea un `.graphifyrc` en la raíz del escaneo para ajustes que pertenecen al proyecto en lugar de a una sola ejecución. Un `key=value` por línea; las líneas que empiezan con `#` son comentarios.

**Extensiones ambiguas.** Algunas extensiones significan lenguajes distintos en proyectos distintos: `.inc` es PHP en pfSense, Pascal en un árbol de Delphi, SQL o ensamblador en otros sitios; `.h` es C o C++; `.m` es Objective-C o MATLAB. graphify tiene que elegir un único valor por defecto global, y cuando elige mal el archivo no falla: se analiza como el lenguaje equivocado y produce un puñado de nodos incidentales, así que el grafo parece poblado mientras los símbolos reales faltan. Declara lo que significa la extensión en tu repositorio:

```
# .graphifyrc
# A language name:
language.inc=php
# Or an extension graphify already knows:
language.tpl=.ts
# Baked into the git hooks (see Team setup):
viz_node_limit=0
```

La declaración fluye a través de la clasificación, la selección de extractor, la gramática y la resolución, las importaciones, `graphify watch` y la caché de AST (un archivo re-analizado bajo un lenguaje distinto nunca reutiliza la entrada antigua), y el mismo `.graphifyrc` es leído por `extract`, `update`, los hooks, el servidor MCP y la skill `/graphify`. Un error de tipeo se reporta una vez en stderr y el escaneo continúa con los valores por defecto. Cómo interactúan las declaraciones con el almacenamiento en caché, las reconstrucciones incrementales y la resolución de importaciones: **[Configuración](https://docs.graphify.com/reference/configuration)**.

---

## Configuración de equipo

Confirma o comparte el grafo para que todo tu equipo consulte el mismo contexto, y revisa las pull requests con contexto del grafo. Consulta **[Comparte contexto con tu equipo](https://docs.graphify.com/guides/team-workflows)** y **[Revisa pull requests](https://docs.graphify.com/guides/pull-requests)**.

---

## Usar el grafo directamente

Más allá de tu asistente de IA, consulta `graph.json` directamente desde la CLI con `graphify query`, `graphify path` y `graphify explain`. Un nombre que coincide con varios nodos se rechaza con los candidatos listados en lugar de adivinarse. Los scripts pueden leer el resultado desde el código de salida: `0` una respuesta, `3` un nombre ambiguo, `4` ningún nodo coincidente. Consulta **[Haz mejores preguntas al grafo](https://docs.graphify.com/guides/querying)** y la **[referencia de consultas](https://docs.graphify.com/reference/query)**.

---

## Variables de entorno

Los backends, las claves de API, el comportamiento de los hooks y el ajuste se controlan con variables de entorno. Tabla completa: **[Configuración](https://docs.graphify.com/reference/configuration)**.

---

## Privacidad

- **Archivos de código**: procesados localmente vía tree-sitter. Nada sale de tu máquina. Un corpus solo de código no requiere clave de API: `graphify extract` se ejecuta totalmente sin conexión. En un repositorio mixto, añade `--code-only` para indexar solo el código y omitir los documentos/PDF/imágenes que de otro modo necesitarían un LLM.
- **Vídeo / audio**: transcritos localmente con faster-whisper. Nada sale de tu máquina.
- **Documentos, PDF, imágenes**: enviados a tu asistente de IA para extracción semántica (vía la skill `/graphify`, usando el modelo que ejecute tu sesión de IDE). El `graphify extract` sin interfaz requiere `GEMINI_API_KEY` / `GOOGLE_API_KEY` (Gemini), `MOONSHOT_API_KEY` (Kimi), `ANTHROPIC_API_KEY` (Claude), `OPENAI_API_KEY` (OpenAI), `DEEPSEEK_API_KEY` (DeepSeek), una instancia de Ollama en ejecución (`OLLAMA_BASE_URL`), credenciales de AWS vía la cadena de proveedores estándar (Bedrock - sin clave de API necesaria, usa IAM), o el binario de la CLI `claude` (Claude Code - sin clave de API necesaria, usa tu suscripción de Claude). El flag `--dedup-llm` usa la misma clave.
- **Residencia de datos**: `graphify extract` detecta automáticamente qué proveedor usar según qué clave de API esté configurada (prioridad: Gemini → Kimi → Claude → OpenAI → DeepSeek → Azure → Bedrock → Ollama). Para código con requisitos de residencia de datos, usa `--backend ollama` (totalmente local) o pasa un flag `--backend` explícito. Kimi (`MOONSHOT_API_KEY`) enruta a los servidores de Moonshot AI en China.
- **Sin telemetría**, sin seguimiento de uso, sin analíticas.
- **Registro de consultas**: cada llamada a `graphify query`, `graphify path`, `graphify explain` y MCP `query_graph` se registra en `~/.cache/graphify-queries.log` en formato JSON Lines (marca de tiempo, pregunta, corpus, nodos devueltos, duración). Las respuestas de subgrafo completas **no** se almacenan por defecto. Establece `GRAPHIFY_QUERY_LOG_DISABLE=1` para optar por no participar, o `GRAPHIFY_QUERY_LOG=/dev/null` para silenciar sin desactivar la ruta de código.

---

## Resolución de problemas

Problemas comunes de instalación y extracción y sus soluciones: **[Resolución de problemas](https://docs.graphify.com/troubleshooting)**.

---

## Referencia completa de comandos

Cada comando y flag, con ejemplos: **[Referencia de CLI](https://docs.graphify.com/reference/overview)**.

---

## Aprende más

- [docs.graphify.com](https://docs.graphify.com): documentación completa: guías, referencia de comandos e integraciones
- [Cómo funciona](../how-it-works.md): el pipeline de extracción, la detección de comunidades, la puntuación de confianza, los benchmarks
- [ARCHITECTURE.md](../../ARCHITECTURE.md): desglose de módulos, cómo añadir un lenguaje
- [Integraciones opcionales](../docker-mcp-sqlite.md): Docker MCP Toolkit + SQLite
- [The Memory Layer](https://safishamsi.gumroad.com/l/qetvlo): el libro sobre las ideas detrás de graphify, la arquitectura de principio a fin

---

## Graphify Cloud

[**Graphify Cloud**](https://app.graphify.com/login) es la capa siempre activa construida sobre graphify. En lugar de un grafo que reconstruyes bajo demanda por carpeta, mantiene un único grafo vivo a lo largo de todo tu ciclo de vida de desarrollo de software:

- **80% menos tokens**: la memoria siempre activa hace que tus agentes dejen de releer y reexplicar el código en cada sesión.
- **Monorepo y entre repositorios**: un único grafo conectado a través de cada servicio y repositorio, no un grafo por carpeta.
- **Verificación formal**: comprueba invariantes de arquitectura y de dependencias contra el grafo vivo.
- **Revisión de código con una vista panorámica de tu SDLC**: ve cómo un cambio se propaga por todo el sistema antes de fusionar.
- **Conectores de SDLC**: incorpora Sentry, Jira y más, para que los incidentes, los tickets y el código vivan en un solo grafo.
- **Siempre activo**: se actualiza continuamente en segundo plano a través de código, documentos y reuniones.

**[Comienza una prueba gratuita de 14 días en app.graphify.com &rarr;](https://app.graphify.com/login)**

---

## Contribuir

Las contribuciones son bienvenidas. Consulta **[CONTRIBUTING.md](../../CONTRIBUTING.md)** para la configuración de desarrollo, los comandos de pruebas y de paridad con CI, el flujo de trabajo de git y qué hace una contribución sólida (los ejemplos trabajados y los informes de errores de extracción son los más útiles). Arquitectura y cómo añadir un lenguaje: [ARCHITECTURE.md](../../ARCHITECTURE.md).

¿Nuevo por aquí? Saluda en [Discord](https://discord.gg/XDnKVpzdXB) o en [GitHub Discussions](https://github.com/Graphify-Labs/graphify/discussions).

---

## Colaboradores

<a href="https://github.com/Graphify-Labs/graphify/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=Graphify-Labs/graphify" alt="graphify contributors" />
</a>

Hecho con [contrib.rocks](https://contrib.rocks).

---

## Traducciones

El README está disponible en 32 idiomas. Usa el selector de idioma en la parte superior de este archivo para leerlo en el tuyo, o explora [`docs/translations/`](./). Para mejorar una traducción o añadir una nueva, abre una pull request contra el archivo correspondiente allí.

---

## Construir sobre graphify

¿Estás construyendo algo en el ecosistema de graphify? Eso se fomenta. Si tu proyecto usa "graphify" en su nombre (por ejemplo `graphify-dashboard` o `graphify-action`), añade una breve nota a tu README aclarando que es construido por la comunidad y no está afiliado ni respaldado por Graphify Labs. "graphify" y el logo de graphify son marcas de Graphify Labs; por favor no las uses de una forma que implique estatus oficial.

---

## Comunidad y enlaces

<p align="center">
  <a href="https://graphify.com"><img src="https://img.shields.io/badge/Website-graphify.com-4c1?style=flat&logo=googlechrome&logoColor=white" alt="Website"/></a>
  <a href="https://discord.gg/XDnKVpzdXB"><img src="https://img.shields.io/badge/Discord-Join-5865F2?style=flat&logo=discord&logoColor=white" alt="Discord"/></a>
  <a href="https://x.com/graphify"><img src="https://img.shields.io/badge/X-graphify-000000?logo=x&logoColor=white" alt="X"/></a>
  <a href="https://www.youtube.com/@graphifylabs"><img src="https://img.shields.io/badge/YouTube-Graphify%20Labs-FF0000?style=flat&logo=youtube&logoColor=white" alt="YouTube"/></a>
  <a href="https://github.com/sponsors/safishamsi"><img src="https://img.shields.io/badge/sponsor-safishamsi-ea4aaa?logo=github-sponsors" alt="Sponsor"/></a>
  <a href="https://safishamsi.gumroad.com/l/qetvlo"><img src="https://img.shields.io/badge/Book-The%20Memory%20Layer-2ea44f?style=flat&logo=gitbook&logoColor=white" alt="The Memory Layer"/></a>
</p>
