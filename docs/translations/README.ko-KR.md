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
  <b>에이전트의 토큰 지출을 80% 줄이세요.</b> Graphify Cloud 는 상시 작동하는 메모리로, 에이전트를 통제하고 코드 품질을 높게 유지하며 형식 검증으로 정확성을 증명합니다. <a href="https://app.graphify.com/login"><b>14 일 무료 체험 시작 &rarr;</b></a>
</p>

AI 코딩 어시스턴트에서 `/graphify` 를 입력하면, 프로젝트 전체(코드, 문서, PDF, 이미지, 동영상)를 **지식 그래프**로 매핑하여 파일을 grep 하는 대신 **쿼리로 조회**할 수 있습니다.

- **코드 매핑은 무료이며 완전히 로컬입니다.** 코드는 tree-sitter AST 로 파싱됩니다. 결정론적이고, LLM 을 쓰지 않으며, 무엇도 당신의 머신을 벗어나지 않습니다. (문서, PDF, 이미지, 동영상은 어시스턴트의 모델 또는 설정한 API key 를 사용해 의미 분석 패스를 한 번 수행합니다.)
- **모든 엣지에 설명이 있습니다.** 각 연결은 `EXTRACTED`(소스에 명시적으로 존재) 또는 `INFERRED`(graphify 가 해석함)로 태그되므로, 직접 읽은 것과 추론한 것을 구별할 수 있습니다.
- **벡터 인덱스가 아닙니다.** 임베딩도 벡터 저장소도 없습니다. 실제로 순회할 수 있는 그래프입니다. 질문을 하거나, 두 대상 사이의 경로를 추적하거나, 하나의 개념을 설명할 수 있습니다.

> [!NOTE]
> **이것을 상시 작동하게 하고 싶으신가요?** [Graphify Cloud](https://app.graphify.com/login) 는 당신의 SDLC 전체에 걸쳐 그래프를 항상 라이브로 유지합니다: 모노레포 및 레포 간 지원, 형식 검증, SDLC 를 조감하는 코드 리뷰, 그리고 Sentry, Jira 등을 위한 커넥터를 통해 인시던트와 티켓이 코드와 같은 그래프에 놓입니다. **[app.graphify.com 에서 14 일 무료 체험을 시작하세요](https://app.graphify.com/login)**.

<p align="center">
  <img src="https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/graph-hero.png" alt="graphify 의 인터랙티브 graph.html 이 FastAPI 코드베이스를 힘 기반으로 배치된 지식 그래프로, 검출된 커뮤니티 범례와 함께 보여준다" width="900">
</p>
<p align="center">
  <em>graphify 가 매핑한 FastAPI 코드베이스. 모든 노드는 하나의 개념이고, 색상은 검출된 커뮤니티이며, 전체가 graph.html 에서 클릭 가능합니다.</em>
</p>

**시작하기**(30 seconds). Python 3.10+ 와 uv(또는 pipx)가 필요합니다.

```bash
uv tool install graphifyy      # install the CLI (or: pipx install graphifyy)
graphify install               # detects your assistant and registers the skill
```

그런 다음, AI 어시스턴트에서:

```
/graphify .
```

이게 전부입니다. **세 개의 파일**을 얻게 됩니다:

```
graphify-out/
├── graph.html       open in any browser: click nodes, filter, search
├── GRAPH_REPORT.md  the highlights: key concepts, surprising connections, suggested questions
└── graph.json       the full graph: query it anytime without re-reading your files
```

영속화된 그래프에는 `graph.schema_version` 이 포함되어 통합 측이 호환되지 않는 포맷 변경을 감지할 수 있으며, 더불어 그것을 생성한 Graphify 릴리스를 식별하는 `graph.graphify_version` 도 포함됩니다.

**한 번 설치로, 어떤 어시스턴트든, 어떤 OS 든.** Claude Code, Cursor, Codex, Gemini CLI, GitHub Copilot, 그리고 20+ 개 이상에서, macOS, Linux, Windows 로 동작합니다: [플랫폼 고르기](#install).

---

## 실제 동작 보기

<p align="center">
  <img src="https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/demo-path.svg" alt="graphify 경로 쿼리: 터미널이 FastAPI 와 ModelField 사이의 최단 경로를 묻고, 그 답이 지식 그래프에서 홉마다 점등된다" width="900">
</p>

그래프가 구축되면 파일을 읽는 대신 그것을 쿼리합니다. 실제 출력으로, 위에 보인 FastAPI 코드베이스에서 graphify 를 실행한 것입니다:

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

모든 엣지는 **신뢰도 태그**를 가집니다(`EXTRACTED` = 소스에 명시적으로 존재, `INFERRED` = 해석으로 도출). 그래서 직접 읽은 것과 추론한 것을 구별할 수 있습니다. `graphify query "<question>"` 는 평이한 언어로 된 질문에 대해 범위가 한정된 서브그래프를 반환하고, `graphify path A B` 는 임의의 두 대상이 어떻게 연결되는지 추적합니다.

---

## 무엇을 하는가

기본으로 제공되는 것은 다음과 같습니다:

| 기능 | 얻는 것 |
|---|---|
| **God nodes** | 가장 많이 연결된 개념들로, 모든 것이 무엇을 거쳐 흐르는지 보입니다 |
| **Communities** | 그래프를 서브시스템으로 분할(Leiden)하고, LLM 없이 라벨을 붙입니다 |
| **Cross-file links** | `calls` / `imports` / `inherits` / `mixes_in` 를 tree-sitter AST 를 통해 ~40 languages 에 걸쳐 해석합니다 |
| **Query, path, explain** | 질문하기, 두 대상 사이의 경로 추적하기, 하나의 개념 설명하기. 모두 `graph.json` 을 대상으로 합니다 |
| **Rationale + doc refs** | `# NOTE:` / `# WHY:` 주석과 ADR/RFC 인용이 일급 노드가 되어 코드에 연결됩니다 |
| **Beyond code** | 문서, PDF, 이미지, 동영상/오디오가 모두 같은 그래프에 매핑됩니다 |
| **Local-first** | 코드는 tree-sitter 로 로컬에서 파싱됩니다(LLM 없음, 무엇도 머신을 벗어나지 않음). 문서/미디어에 대한 의미 분석 패스만 백엔드를 호출하며, 그것도 당신이 설정한 경우에만 그렇습니다 |

> [!TIP]
> 여러 레포나 모노레포에 걸쳐 이것을 실행하고 계신가요? [Graphify Cloud](https://app.graphify.com/login) 는 이를 지속적으로 수행하며 에이전트의 토큰 지출을 80% 줄입니다. 레포 간 링크, SDLC 전반의 코드 리뷰, 형식 검증, Sentry/Jira 커넥터를 제공합니다. [14 일 무료 체험 시작 &rarr;](https://app.graphify.com/login)

---

## 벤치마크: 0.497 recall@10, 0 LLM credits

| Benchmark | Metric | graphify | Field |
|---|---|---|---|
| LOCOMO (n=300) | recall@10 | **0.497** | mem0 0.048, supermemory 0.149 |
| LOCOMO (n=300) | QA accuracy | 45.3% | supermemory 49.7%, mem0 27.3% |
| LongMemEval-S (n=50) | QA accuracy | **76%** | tied with dense RAG |
| ERPNext cross-tool (n=6) | key-fact coverage | **82.0%** | grep/read baseline 70.8% |
| Graph build | LLM credits | **0** | per-token for most systems |

모든 시스템은 동일한 하니스에서 동일한 모델과 예산으로 실행되었고, 두 번째 심사자에 대해 블라인드 검증된 심사자가 채점했습니다(90.6% agreement, Cohen's kappa 0.81). 시스템별 전체 표, 코드 인텔리전스 결과, 재현 명령은 다음을 참고하세요: **[BENCHMARKS.md](../../BENCHMARKS.md)**.

---

## 문서

전체 가이드와 레퍼런스는 **[docs.graphify.com](https://docs.graphify.com)** 에 있습니다:

- **[Quickstart](https://docs.graphify.com/quickstart)**: 첫 그래프 만들기
- **[CLI reference](https://docs.graphify.com/reference/overview)**: 모든 명령과 플래그
- **[Ask better graph questions](https://docs.graphify.com/guides/querying)**: 쿼리 패턴
- **[Configuration](https://docs.graphify.com/reference/configuration)**: 환경 변수와 튜닝
- **[Supported inputs](https://docs.graphify.com/concepts/supported-inputs)**: 언어와 파일 유형
- **[Team workflows](https://docs.graphify.com/guides/team-workflows)** 와 **[PR review](https://docs.graphify.com/guides/pull-requests)**
- **[Troubleshooting](https://docs.graphify.com/troubleshooting)** 와 **[How it works](https://docs.graphify.com/concepts/architecture)**

---

## 사전 요구 사항

| 요구 사항 | 최소 | 확인 | 설치 |
|---|---|---|---|
| Python | 3.10+ | `python --version` | [python.org](https://www.python.org/downloads/) |
| uv *(recommended)* | any | `uv --version` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| pipx *(alternative)* | any | `pipx --version` | `pip install pipx` |

**macOS 빠른 설치(Homebrew):**
```bash
brew install python@3.12 uv
```

**Windows 빠른 설치:**
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
> **공식 패키지:** PyPI 패키지는 `graphifyy`(y 가 두 개)입니다. PyPI 의 다른 `graphify*` 패키지는 제휴 관계가 없습니다. CLI 명령은 여전히 `graphify` 입니다.

공식 소스 저장소는 [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify) 입니다.

두 명령 빠른 시작은 이 README 상단에 있습니다. 이 섹션에서는 설치 방법, 프로젝트 범위 설치, 그리고 지원되는 모든 플랫폼을 다룹니다.

**설치 방법**(하나 선택):

```bash
uv tool install graphifyy   # recommended, isolated env (if 'graphify' isn't found after, run: uv tool update-shell)
pipx install graphifyy      # alternative
pip install graphifyy       # may need PATH setup, see Troubleshooting below
```

그런 다음 `graphify install` 을 한 번 실행하세요. 어떤 어시스턴트를 쓰는지 감지하여 스킬을 등록하므로, 어시스턴트별 설정이 필요 없습니다. AI 어시스턴트를 열고 `/graphify .` 를 입력하세요.

어시스턴트 스킬을 사용자 프로필이 아니라 현재 저장소에 설치하려면 `--project` 를 추가하세요:

```bash
graphify install --project
graphify install --project --platform codex
```

프로젝트 범위 설치는 현재 디렉터리 아래에 기록됩니다. 예를 들어 `.claude/skills/graphify/SKILL.md` 또는 `.agents/skills/graphify/SKILL.md`(그리고 스킬이 필요 시 로드하는 `references/` 사이드카)이며, 커밋할 수 있는 파일에 대해 `git add` 힌트를 출력합니다. 프로젝트 범위 설치를 지원하는 플랫폼별 명령도 같은 플래그를 받습니다. 예를 들어 `graphify claude install --project` 또는 `graphify codex install --project` 입니다.

> [!TIP]
> `command not found`, Mac/Windows 의 `pip` 문제, PowerShell 따옴표, `uvx` 사용법, git-hook 의 PATH 특이점, 또는 strict 모드에 부딪혔나요? **[Installation](https://docs.graphify.com/installation)** 과 **[Troubleshooting](https://docs.graphify.com/troubleshooting)** 을 참고하세요.

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
| Pi coding agent | `graphify install --platform pi`, plus `graphify pi guard install` for the native guard |
| Cursor | `graphify cursor install` |
| Devin CLI | `graphify devin install` |
| Google Antigravity | `graphify antigravity install` |

Codex 사용자는 병렬 추출을 위해 `~/.codex/config.toml` 의 `[features]` 아래에 `multi_agent = true` 도 필요합니다. CodeBuddy 는 Claude Code 와 동일한 Agent tool 및 PreToolUse hook 메커니즘을 사용합니다. Factory Droid 는 병렬 서브에이전트 디스패치에 `Task` tool 을 사용합니다. OpenClaw 와 Aider 는 순차 추출을 사용합니다(이 플랫폼들에서 병렬 에이전트 지원은 아직 초기 단계입니다). Trae 는 병렬 서브에이전트 디스패치에 Agent tool 을 사용하며 `PreToolUse` hook 을 지원하지 **않으므로**, AGENTS.md 가 상시 작동 메커니즘이 됩니다.

`--platform agents`(별칭 `--platform skills`)는 범용 크로스 프레임워크 [Agent-Skills](https://github.com/anthropics/skills) 위치를 대상으로 합니다: 전역 설치에는 스펙의 사용자 전역 `~/.agents/skills/`(`npx skills` 와 스펙 준수 프레임워크가 읽음)를, 프로젝트(`--project`) 설치에는 `./.agents/skills/` 를 사용합니다. 맨 `graphify install` 은 설계상 단일 플랫폼(Claude Code)으로 유지됩니다: `.agents/skills` 를 읽는 어떤 프레임워크에서도 스킬이 발견되기를 원한다면 이름이 지정된 `agents` 플랫폼을 사용하세요.

Pi 에는 `PreToolUse` hook 이 없으므로, `graphify pi guard install` 은 (Pi 자체의 `pi install <package directory>` 를 통해) 네이티브 Pi 확장을 등록하여, Pi 의 `read`, `grep`, `find` 및 검색형 `bash` 호출 이전에 설치된 `graphify hook-guard` 를 실행합니다. 신선/오래됨 그래프 판단과 `GRAPHIFY_HOOK_STRICT=1` 의 세션당 한 번 인덱스된 읽기 거부는 동일한 정책에서 나오므로, Pi 는 Claude Code 의 hook 동작과 일치합니다. 안내는 `<system-reminder source="graphify">` 스티어링 메시지로 도착합니다. Pi 0.58.4 이상이 필요합니다: 그 이전 버전은 스티어링 메시지가 병렬 도구 호출 배치의 나머지를 건너뛰게 합니다. 이 패키지는 Graphify 설치 안에 함께 들어 있으므로, Graphify 를 영속적으로 설치하고(`uvx` 가 아니라 `uv tool install graphifyy` 또는 `pipx install graphifyy`), 설치 또는 업그레이드 후 Pi 를 재시작하며, `graphify pi guard uninstall` 로 제거하세요. 검사되는 것은 로컬 파일 대상뿐입니다. 이 hook 은 프로젝트 외부의 절대 `PATH` 항목에 `graphify` 가 있어야 하고, 2 초, 입력 256 KiB/출력 64 KiB 호출로 제한되며, 실패 시 열린 상태로 통과시킵니다. 같은 패키지는 [Oh My Pi](https://github.com/can1357/oh-my-pi) 에도 로드됩니다: `omp plugin install "$(graphify pi guard path)"`. 등록된 경로에는 Python 버전과 venv 가 포함되므로, 둘 중 하나를 변경한 뒤에는 `graphify pi guard install` 을 다시 실행하고, 이전 항목은 `pi remove <old path>` 로 제거하세요.

> Codex 는 `/graphify` 대신 `$graphify` 를 사용합니다.

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

## 어시스턴트가 항상 그래프를 사용하게 만들기

그래프를 만든 뒤, 프로젝트에서 이것을 한 번 실행하세요:

프로젝트에서 `graphify <platform> install` 을 한 번 실행하세요. 예를 들어 `graphify claude install` 또는 `graphify codex install`(또는 `graphify install --platform <name>`)입니다.

이것은 작은 설정 파일을 기록하여, 코드베이스 질문에서는 지식 그래프를 참조하고, 전체 보고서를 읽거나 원시 파일을 grep 하는 것보다 `graphify query "<question>"` 같은 범위가 한정된 쿼리를 선호하도록 어시스턴트에게 지시합니다.

- **Hook 플랫폼**(Claude Code, Gemini CLI): 검색형 도구 호출 이전에(그리고 Claude Code 에서는 Read/Glob 도구로 소스 파일을 하나씩 읽기 전에도) hook 이 자동으로 발동하여 어시스턴트를 그래프 경로로 유도합니다.
- **지침 파일 플랫폼**(Codex, OpenCode, Cursor 등): 영속적인 지침 파일(`AGENTS.md`, `.cursor/rules/` 등)이 동일한 쿼리 우선 안내를 제공합니다.

`GRAPH_REPORT.md` 는 폭넓은 아키텍처 검토에 여전히 사용할 수 있습니다.

각 플랫폼이 정확히 어떤 파일을 기록하는지(CodeBuddy 의 `CODEBUDDY.md` + `PreToolUse` hooks, Codex 의 `AGENTS.md`, Kilo 의 네이티브 `.kilo` 플러그인, Cursor 의 `alwaysApply` 규칙 등)는 **[Always-on setup](https://docs.graphify.com/guides/always-on)** 에서 다룹니다.

모든 플랫폼에서 graphify 를 한 번에 제거하려면: `graphify uninstall`(`--purge` 를 추가하면 `graphify-out/` 도 삭제). 또는 플랫폼별 명령(예: `graphify claude uninstall`)을 사용하세요.

### CLI 스킬인가 MCP 지시인가?

`graphify install` 이 설치하는 지침과 Graphify MCP 연결과 함께 제공되는 지침은 그래프를 쿼리하는 서로 다른 방식을 설명합니다:

| Setup | Guidance to use | Query access |
|---|---|---|
| 로컬 CLI 및 설치된 어시스턴트 스킬 | `graphify install` 이 기록한 플랫폼 지침 | 로컬 그래프(기본값 `graphify-out/`)를 대상으로 `graphify query`, `graphify path`, `graphify explain` 을 실행합니다. |
| 연결된 Graphify MCP 서버 | 해당 연결의 지침과 그 서버가 나열한 도구 | 해당 연결이 제공하는 그래프를 대상으로 나열된 MCP 도구를 호출합니다. 도구 이름과 설명은 서버에서 옵니다. |

둘 다 폭넓은 소스 검색 이전에 범위가 한정된 그래프 쿼리를 권장합니다. 어시스턴트가 실제로 접근할 수 있는 도구에 맞는 지침을 선택하세요. 어느 블록도 어시스턴트의 지침 파일에 대한 보편적 우선순위 규칙을 수립하지 않습니다. 두 통합을 모두 사용한다면, 각각이 어떤 그래프를 쿼리하는지 식별하고, 두 개의 무조건적 지침 블록을 `AGENTS.md` 에 복사하는 대신 하나의 주요 쿼리 경로를 선택하세요.

`graphify install` 은 로컬 어시스턴트 통합을 설치하며, MCP 연결을 수립하지는 않습니다. MCP 클라이언트는 연결된 서버를 사용하기 위해 로컬 CLI 쿼리를 실행할 필요가 없습니다. 로컬에 호스팅된 서버는 여전히 자체 Graphify 설치와 그래프가 필요하지만, 호스팅된 연결은 클라이언트의 작업 디렉터리에 존재하지 않는 그래프를 제공할 수 있습니다. 기대한 도구가 보이지 않으면, 다른 설정의 지침을 서로 바꿔 쓸 수 있는 것으로 취급하지 말고 해당 CLI 설치나 MCP 연결을 확인하세요.

---

## 보고서에 담긴 내용

`GRAPH_REPORT.md` 는 폭넓은 아키텍처 검토를 위해 god nodes, 커뮤니티, 핵심 경로를 요약합니다. 그래프가 어떻게 구축되고 무엇을 담고 있는지는 **[How graphify works](https://docs.graphify.com/concepts/architecture)** 를 참고하세요.

---

## 처리하는 파일: ~40 languages

graphify 는 ~40 programming languages 를 tree-sitter AST 로 로컬에서 파싱하고, 선택적 의미 분석 패스를 통해 문서, PDF, 이미지, 오디오/동영상을 매핑합니다. 전체 목록: **[Supported inputs](https://docs.graphify.com/concepts/supported-inputs)**.

---

## 자주 쓰는 명령어

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

아래의 [전체 명령 레퍼런스](#full-command-reference)를 참고하세요.

---

## 파일 무시하기

graphify 는 `.gitignore` 를 존중하고, `--exclude` 패턴과 프로젝트 `.graphifyignore` 를 지원합니다. 자세한 내용: **[Configuration](https://docs.graphify.com/reference/configuration)**.


## 프로젝트 구성

한 번의 실행이 아니라 프로젝트에 속하는 설정을 위해, 스캔 루트에 `.graphifyrc` 를 만드세요. 한 줄에 하나의 `key=value` 이고, `#` 로 시작하는 줄은 주석입니다.

**모호한 확장자.** 일부 확장자는 프로젝트에 따라 다른 언어를 의미합니다: `.inc` 는 pfSense 에서 PHP, Delphi 트리에서 Pascal, 그 밖에서는 SQL 또는 어셈블리입니다. `.h` 는 C 또는 C++, `.m` 은 Objective-C 또는 MATLAB 입니다. graphify 는 하나의 전역 기본값을 골라야 하고, 잘못 고르더라도 파일이 실패하지는 않습니다: 잘못된 언어로 파싱되어 몇 개의 부수적인 노드를 만들어내므로, 실제 심볼은 빠져 있는데도 그래프는 채워져 있는 것처럼 보입니다. 해당 확장자가 당신의 레포에서 무엇을 의미하는지 선언하세요:

```
# .graphifyrc
# A language name:
language.inc=php
# Or an extension graphify already knows:
language.tpl=.ts
# Baked into the git hooks (see Team setup):
viz_node_limit=0
```

이 선언은 분류, 추출기 선택, 문법과 해석, 임포트, `graphify watch`, 그리고 AST 캐시(다른 언어로 다시 파싱된 파일은 이전 항목을 결코 재사용하지 않음)를 거쳐 흐르며, 같은 `.graphifyrc` 는 `extract`, `update`, hooks, MCP 서버, `/graphify` 스킬에 의해 읽힙니다. 오타는 stderr 에 한 번 보고되고 스캔은 기본값으로 계속됩니다. 선언이 캐싱, 증분 재구축, 임포트 해석과 어떻게 상호 작용하는지는 **[Configuration](https://docs.graphify.com/reference/configuration)** 을 참고하세요.

---

## 팀 설정

그래프를 커밋하거나 공유하여 팀 전체가 같은 컨텍스트를 쿼리하게 하고, 그래프 컨텍스트로 풀 리퀘스트를 검토하세요. **[Share context with your team](https://docs.graphify.com/guides/team-workflows)** 와 **[Review pull requests](https://docs.graphify.com/guides/pull-requests)** 를 참고하세요.

---

## 그래프를 직접 사용하기

AI 어시스턴트 외에도, `graphify query`, `graphify path`, `graphify explain` 로 CLI 에서 직접 `graph.json` 을 쿼리할 수 있습니다. 여러 노드에 일치하는 이름은 추측하지 않고 후보를 나열하며 거부됩니다. 스크립트는 종료 코드로 결과를 읽을 수 있습니다: `0` 은 답, `3` 은 모호한 이름, `4` 는 일치하는 노드 없음. **[Ask better graph questions](https://docs.graphify.com/guides/querying)** 와 **[query reference](https://docs.graphify.com/reference/query)** 를 참고하세요.

---

## 환경 변수

백엔드, API key, hook 동작, 튜닝은 환경 변수로 제어됩니다. 전체 표: **[Configuration](https://docs.graphify.com/reference/configuration)**.

---

## 개인정보 보호

- **코드 파일**: tree-sitter 를 통해 로컬에서 처리됩니다. 무엇도 당신의 머신을 벗어나지 않습니다. 코드만 있는 코퍼스는 API key 가 필요 없습니다: `graphify extract` 는 완전히 오프라인으로 실행됩니다. 혼합 레포에서는 `--code-only` 를 추가하면 코드만 인덱싱하고, 그렇지 않으면 LLM 이 필요했을 문서/PDF/이미지를 건너뜁니다.
- **동영상 / 오디오**: faster-whisper 로 로컬에서 전사됩니다. 무엇도 당신의 머신을 벗어나지 않습니다.
- **문서, PDF, 이미지**: 의미 추출을 위해 당신의 AI 어시스턴트로 전송됩니다(`/graphify` 스킬을 통해, IDE 세션이 실행하는 모델을 사용). 헤드리스 `graphify extract` 는 `GEMINI_API_KEY` / `GOOGLE_API_KEY`(Gemini), `MOONSHOT_API_KEY`(Kimi), `ANTHROPIC_API_KEY`(Claude), `OPENAI_API_KEY`(OpenAI), `DEEPSEEK_API_KEY`(DeepSeek), 실행 중인 Ollama 인스턴스(`OLLAMA_BASE_URL`), 표준 제공자 체인을 통한 AWS 자격 증명(Bedrock, API key 불필요, IAM 사용), 또는 `claude` CLI 바이너리(Claude Code, API key 불필요, 당신의 Claude 구독 사용)가 필요합니다. `--dedup-llm` 플래그는 같은 key 를 사용합니다.
- **데이터 레지던시**: `graphify extract` 는 어떤 API key 가 설정되어 있는지에 따라 사용할 제공자를 자동 감지합니다(우선순위: Gemini → Kimi → Claude → OpenAI → DeepSeek → Azure → Bedrock → Ollama). 데이터 레지던시 요구가 있는 코드에는 `--backend ollama`(완전 로컬)를 사용하거나 명시적인 `--backend` 플래그를 전달하세요. Kimi(`MOONSHOT_API_KEY`)는 중국에 있는 Moonshot AI 서버로 라우팅됩니다.
- **텔레메트리 없음**, 사용 추적 없음, 분석 없음.
- **쿼리 로깅**: 모든 `graphify query`, `graphify path`, `graphify explain`, 그리고 MCP `query_graph` 호출은 JSON Lines 형식으로 `~/.cache/graphify-queries.log` 에 기록됩니다(타임스탬프, 질문, 코퍼스, 반환된 노드, 소요 시간). 전체 서브그래프 응답은 기본적으로 저장되지 **않습니다**. 옵트아웃하려면 `GRAPHIFY_QUERY_LOG_DISABLE=1` 을 설정하고, 코드 경로를 비활성화하지 않고 조용히 하려면 `GRAPHIFY_QUERY_LOG=/dev/null` 을 설정하세요.

---

## 문제 해결

흔한 설치 및 추출 문제와 그 해결책: **[Troubleshooting](https://docs.graphify.com/troubleshooting)**.

---

## 전체 명령어 레퍼런스

모든 명령과 플래그, 예시 포함: **[CLI reference](https://docs.graphify.com/reference/overview)**.

---

## 더 알아보기

- [docs.graphify.com](https://docs.graphify.com): 전체 문서: 가이드, 명령 레퍼런스, 통합
- [How it works](../how-it-works.md): 추출 파이프라인, 커뮤니티 검출, 신뢰도 스코어링, 벤치마크
- [ARCHITECTURE.md](../../ARCHITECTURE.md): 모듈 구성, 언어 추가 방법
- [Optional integrations](../docker-mcp-sqlite.md): Docker MCP Toolkit + SQLite
- [The Memory Layer](https://safishamsi.gumroad.com/l/qetvlo): graphify 의 기저 아이디어와 처음부터 끝까지의 아키텍처를 다룬 책

---

## Graphify Cloud

[**Graphify Cloud**](https://app.graphify.com/login) 는 graphify 위에 구축된 상시 작동 레이어입니다. 폴더마다 필요 시 재구축하는 그래프 대신, 소프트웨어 개발 수명주기 전체에 걸쳐 하나의 라이브 그래프를 유지합니다:

- **80% 더 적은 토큰**: 상시 작동 메모리는 당신의 에이전트가 세션마다 코드베이스를 다시 읽고 다시 설명하기를 멈추게 합니다.
- **모노레포 및 레포 간**: 폴더마다 하나의 그래프가 아니라, 모든 서비스와 저장소에 걸친 하나의 연결된 그래프.
- **형식 검증**: 아키텍처와 의존성 불변식을 라이브 그래프에 대해 검사합니다.
- **SDLC 를 조감하는 코드 리뷰**: 병합하기 전에, 변경이 시스템 전체로 어떻게 파급되는지 봅니다.
- **SDLC 커넥터**: Sentry, Jira 등을 끌어와, 인시던트, 티켓, 코드가 하나의 그래프에 존재하게 합니다.
- **상시 작동**: 코드, 문서, 미팅에 걸쳐 백그라운드에서 지속적으로 업데이트합니다.

**[app.graphify.com 에서 14 일 무료 체험 시작 &rarr;](https://app.graphify.com/login)**

---

## 기여하기

기여를 환영합니다. 개발 환경 설정, 테스트 및 CI-parity 명령, git 워크플로, 그리고 무엇이 강력한 기여가 되는지(실제 예시와 추출 버그 리포트가 가장 유용합니다)는 **[CONTRIBUTING.md](../../CONTRIBUTING.md)** 를 참고하세요. 아키텍처와 언어 추가 방법: [ARCHITECTURE.md](../../ARCHITECTURE.md).

처음이신가요? [Discord](https://discord.gg/XDnKVpzdXB) 또는 [GitHub Discussions](https://github.com/Graphify-Labs/graphify/discussions) 에서 인사해 주세요.

---

## 기여자

<a href="https://github.com/Graphify-Labs/graphify/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=Graphify-Labs/graphify" alt="graphify contributors" />
</a>

Made with [contrib.rocks](https://contrib.rocks).

---

## 번역

이 README 는 32 개 언어로 제공됩니다. 이 파일 상단의 언어 전환기를 사용해 당신의 언어로 읽거나, [`docs/translations/`](./) 를 둘러보세요. 번역을 개선하거나 새 번역을 추가하려면, 그곳의 해당 파일에 대해 풀 리퀘스트를 여세요.

---

## graphify 위에 빌드하기

graphify 생태계에서 무언가를 만들고 계신가요? 그것은 권장됩니다. 당신의 프로젝트가 이름에 "graphify" 를 사용한다면(예: `graphify-dashboard` 또는 `graphify-action`), 그것이 커뮤니티가 만든 것이며 Graphify Labs 와 제휴하거나 그로부터 승인받지 않았음을 명확히 하는 짧은 안내를 README 에 추가해 주세요. "graphify" 와 graphify 로고는 Graphify Labs 의 마크입니다. 공식임을 암시하는 방식으로 사용하지 말아 주세요.

---

## 커뮤니티와 링크

<p align="center">
  <a href="https://graphify.com"><img src="https://img.shields.io/badge/Website-graphify.com-4c1?style=flat&logo=googlechrome&logoColor=white" alt="Website"/></a>
  <a href="https://discord.gg/XDnKVpzdXB"><img src="https://img.shields.io/badge/Discord-Join-5865F2?style=flat&logo=discord&logoColor=white" alt="Discord"/></a>
  <a href="https://x.com/graphify"><img src="https://img.shields.io/badge/X-graphify-000000?logo=x&logoColor=white" alt="X"/></a>
  <a href="https://www.youtube.com/@graphifylabs"><img src="https://img.shields.io/badge/YouTube-Graphify%20Labs-FF0000?style=flat&logo=youtube&logoColor=white" alt="YouTube"/></a>
  <a href="https://github.com/sponsors/safishamsi"><img src="https://img.shields.io/badge/sponsor-safishamsi-ea4aaa?logo=github-sponsors" alt="Sponsor"/></a>
  <a href="https://safishamsi.gumroad.com/l/qetvlo"><img src="https://img.shields.io/badge/Book-The%20Memory%20Layer-2ea44f?style=flat&logo=gitbook&logoColor=white" alt="The Memory Layer"/></a>
</p>
