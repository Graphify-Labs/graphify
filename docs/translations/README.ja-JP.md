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
  <b>エージェントのトークン消費を 80% 削減。</b> Graphify Cloud は、エージェントを統制し、コード品質を高く保ち、形式的検証で正しさを証明する、常時オンのメモリです。<a href="https://app.graphify.com/login"><b>14 日間の無料トライアルを始める &rarr;</b></a>
</p>

AI コーディングアシスタントで `/graphify` と入力すると、プロジェクト全体（コード、ドキュメント、PDF、画像、動画）を**ナレッジグラフ**にマッピングし、**ファイルを grep する代わりにクエリできる**ようになります。

- **コードのマッピングは無料で、完全にローカル。** コードは tree-sitter の AST で解析されます。決定論的で、LLM 不要、何一つマシンの外に出ません。（ドキュメント、PDF、画像、動画は、アシスタントのモデルまたは設定された API キーを使ってセマンティックパスを行います。）
- **すべてのエッジに説明が付く。** 各接続は `EXTRACTED`（ソース内に明示的）または `INFERRED`（graphify が解決）とタグ付けされるため、直接読み取られたものと推論されたものを見分けられます。
- **ベクトルインデックスではない。** 埋め込みもベクトルストアもありません。実際にたどれる本物のグラフです。質問する、2 つのものの間の経路をたどる、または 1 つの概念を説明する、といったことができます。

> [!NOTE]
> **これを常時オンにしたい？** [Graphify Cloud](https://app.graphify.com/login) は、SDLC 全体でグラフを常に最新に保ちます。モノレポおよびクロスリポジトリのサポート、形式的検証、SDLC を俯瞰するコードレビュー、さらに Sentry や Jira などのコネクタにより、インシデントやチケットがコードと同じグラフ上に並びます。**[app.graphify.com で 14 日間の無料トライアルを始める](https://app.graphify.com/login)**。

<p align="center">
  <img src="https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/graph-hero.png" alt="graphify's interactive graph.html showing the FastAPI codebase as a force-directed knowledge graph with a legend of detected communities" width="900">
</p>
<p align="center">
  <em>graphify がマッピングした FastAPI のコードベース。各ノードは概念であり、色は検出されたコミュニティを表し、全体が graph.html 上でクリック可能です。</em>
</p>

**はじめに**（30 秒）：

```bash
uv tool install graphifyy      # install the CLI (or: pipx install graphifyy)
graphify install               # register the skill with your AI assistant
```

次に、AI アシスタントで：

```
/graphify .
```

これだけです。**3 つのファイル**が得られます：

```
graphify-out/
├── graph.html       open in any browser — click nodes, filter, search
├── GRAPH_REPORT.md  the highlights: key concepts, surprising connections, suggested questions
└── graph.json       the full graph — query it anytime without re-reading your files
```

永続化されたグラフには `graph.schema_version` が含まれ、統合側が
互換性のないフォーマット変更を検出できます。さらに、それを生成した
Graphify のリリースを示す `graph.graphify_version` も含まれます。

**対応**： Claude Code、Cursor、Codex、Gemini CLI、GitHub Copilot、ほか 15 種類以上 —— [プラットフォームを選ぶ](#install)。

---

## ドキュメント

完全なガイドとリファレンスは **[docs.graphify.com](https://docs.graphify.com)** にあります：

- **[Quickstart](https://docs.graphify.com/quickstart)** —— 最初のグラフを構築する
- **[CLI reference](https://docs.graphify.com/reference/overview)** —— すべてのコマンドとフラグ
- **[Ask better graph questions](https://docs.graphify.com/guides/querying)** —— クエリのパターン
- **[Configuration](https://docs.graphify.com/reference/configuration)** —— 環境変数とチューニング
- **[Supported inputs](https://docs.graphify.com/concepts/supported-inputs)** —— 言語とファイル形式
- **[Team workflows](https://docs.graphify.com/guides/team-workflows)** と **[PR review](https://docs.graphify.com/guides/pull-requests)**
- **[Troubleshooting](https://docs.graphify.com/troubleshooting)** と **[How it works](https://docs.graphify.com/concepts/architecture)**

---

## 動作例

<p align="center">
  <img src="https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/demo-path.svg" alt="graphify path query: a terminal asks for the shortest path between FastAPI and ModelField, and the answer lights up hop by hop across the knowledge graph" width="900">
</p>

グラフを構築したら、ファイルを読む代わりにそれをクエリします。上に示した FastAPI のコードベースで graphify を実行した実際の出力です：

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

すべてのエッジには**信頼度タグ**（`EXTRACTED` = ソース内に明示的、`INFERRED` = 解決によって導出）が付いているため、直接読み取られたものと推論されたものを見分けられます。`graphify query "<question>"` は、平易な言葉の質問に対してスコープを絞ったサブグラフを返し、`graphify path A B` は任意の 2 つのものがどうつながっているかをたどります。

---

## 何ができるのか

そのまますぐに得られるもの：

| 機能 | 得られるもの |
|---|---|
| **ゴッドノード（God nodes）** | 最も多くつながっている概念。すべてが何を通って流れているかが分かる |
| **コミュニティ（Communities）** | グラフをサブシステムに分割（Leiden）、LLM 不要のラベル付き |
| **ファイル横断のリンク** | `calls` / `imports` / `inherits` / `mixes_in` を tree-sitter の AST で約 40 言語にわたって解決 |
| **クエリ、経路、説明** | 質問する、2 つのものの間の経路をたどる、または 1 つの概念を説明する。すべて `graph.json` に対して行う |
| **根拠 + ドキュメント参照** | `# NOTE:` / `# WHY:` コメントや ADR/RFC の引用が、コードにリンクされた一級ノードになる |
| **コードを超えて** | ドキュメント、PDF、画像、動画/音声がすべて同じグラフにマッピングされる |
| **ローカルファースト** | コードは tree-sitter でローカルに解析（LLM 不要、何一つマシンの外に出ない）。ドキュメント/メディアに対するセマンティックパスのみがバックエンドを呼び出し、それも設定した場合に限る |

> [!TIP]
> 多数のリポジトリやモノレポにまたがって実行していますか？[Graphify Cloud](https://app.graphify.com/login) はそれを継続的に行い、エージェントのトークン消費を 80% 削減します。クロスリポジトリのリンク、SDLC 全体のコードレビュー、形式的検証、Sentry/Jira コネクタ付き。[14 日間の無料トライアルを始める &rarr;](https://app.graphify.com/login)

---

## ベンチマーク

| ベンチマーク | 指標 | graphify | 他社 |
|---|---|---|---|
| LOCOMO (n=300) | recall@10 | **0.497** | mem0 0.048, supermemory 0.149 |
| LOCOMO (n=300) | QA accuracy | 45.3% | supermemory 49.7%, mem0 27.3% |
| LongMemEval-S (n=50) | QA accuracy | **76%** | tied with dense RAG |
| ERPNext cross-tool (n=6) | key-fact coverage | **82.0%** | grep/read baseline 70.8% |
| Graph build | LLM credits | **0** | per-token for most systems |

すべてのシステムは、同じハーネス、同じモデル、同じ予算で実行され、2 人目の判定者に対してブラインド検証された判定者によって採点されました（一致率 90.6%、Cohen's kappa 0.81）。システムごとの完全な表、コードインテリジェンスの結果、再現コマンドは **[BENCHMARKS.md](../../BENCHMARKS.md)** にあります。

---

## 前提条件

| 要件 | 最小 | 確認 | インストール |
|---|---|---|---|
| Python | 3.10+ | `python --version` | [python.org](https://www.python.org/downloads/) |
| uv *(推奨)* | 任意 | `uv --version` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| pipx *(代替)* | 任意 | `pipx --version` | `pip install pipx` |

**macOS クイックインストール（Homebrew）：**
```bash
brew install python@3.12 uv
```

**Windows クイックインストール：**
```powershell
winget install astral-sh.uv
```

**Ubuntu/Debian：**
```bash
sudo apt install python3.12 python3-pip pipx
# or install uv:
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## Install

> [!IMPORTANT]
> **公式パッケージ：** PyPI のパッケージは `graphifyy`（y が 2 つ）です。PyPI 上の他の `graphify*` パッケージは関係ありません。CLI コマンドは引き続き `graphify` です。

公式のソースリポジトリは [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify) です。

**ステップ 1 —— パッケージをインストール：**

```bash
# Recommended (isolated env; if 'graphify' isn't found after, run: uv tool update-shell):
uv tool install graphifyy

# Alternatives:
pipx install graphifyy
pip install graphifyy  # may need PATH setup — see note below
```

**ステップ 2 —— AI アシスタントにスキルを登録：**

```bash
graphify install
```

これだけです。AI アシスタントを開いて `/graphify .` と入力してください。

ユーザープロファイルではなく現在のリポジトリにアシスタントスキルを
インストールするには、`--project` を追加します：

```bash
graphify install --project
graphify install --project --platform codex
```

プロジェクトスコープのインストールは、現在のディレクトリの下に書き込みます。たとえば
`.claude/skills/graphify/SKILL.md` や `.agents/skills/graphify/SKILL.md`（さらにスキルが
オンデマンドで読み込む `references/` サイドカー）が作成され、
コミット可能なファイルについては `git add` のヒントが表示されます。
プロジェクトスコープのインストールに対応するプラットフォーム別コマンドも同じフラグを受け付けます。
たとえば `graphify claude install --project` や `graphify codex install --project` です。

> [!TIP]
> `command not found`、Mac/Windows での `pip` の問題、PowerShell のクォート、`uvx` の使い方、git フックの PATH の癖、または strict モードに引っかかっていますか？**[Installation](https://docs.graphify.com/installation)** と **[Troubleshooting](https://docs.graphify.com/troubleshooting)** を参照してください。

<details>
<summary><b>プラットフォームを選ぶ</b>（20 種類以上のアシスタント、クリックで展開）</summary>

| プラットフォーム | インストールコマンド |
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

Codex ユーザーは、並列抽出のために `~/.codex/config.toml` の `[features]` の下に `multi_agent = true` も必要です。CodeBuddy は Claude Code と同じ Agent ツールと PreToolUse フックの仕組みを使います。Factory Droid は並列サブエージェントのディスパッチに `Task` ツールを使います。OpenClaw と Aider は逐次抽出を使います（これらのプラットフォームでの並列エージェントのサポートはまだ初期段階です）。Trae は並列サブエージェントのディスパッチに Agent ツールを使い、`PreToolUse` フックには**対応していない**ため、AGENTS.md が常時オンの仕組みになります。

`--platform agents`（別名 `--platform skills`）は、汎用のクロスフレームワーク [Agent-Skills](https://github.com/anthropics/skills) の場所を対象にします。グローバルインストールには、仕様で定められたユーザーグローバルの `~/.agents/skills/`（`npx skills` と仕様準拠のフレームワークが読み取る）を、プロジェクト（`--project`）インストールには `./.agents/skills/` を使います。素の `graphify install` は設計上シングルプラットフォーム（Claude Code）のままです —— `.agents/skills` を読み取る任意のフレームワークからスキルを発見可能にしたいときは、名前付きの `agents` プラットフォームを使ってください。

> Codex は `/graphify` ではなく `$graphify` を使います。

</details>

<details>
<summary><b>オプションの追加機能</b>（必要なものだけインストール）</summary>

| 追加機能 | 追加されるもの | インストール |
|---|---|---|
| `pdf` | PDF 抽出 | `uv tool install "graphifyy[pdf]"` |
| `office` | `.docx` と `.xlsx` のサポート | `uv tool install "graphifyy[office]"` |
| `google` | Google Sheets のレンダリング | `uv tool install "graphifyy[google]"` |
| `video` | 動画/音声の文字起こし（faster-whisper + yt-dlp） | `uv tool install "graphifyy[video]"` |
| `mcp` | MCP stdio サーバー | `uv tool install "graphifyy[mcp]"` |
| `neo4j` | Neo4j へのプッシュのサポート | `uv tool install "graphifyy[neo4j]"` |
| `falkordb` | FalkorDB へのプッシュのサポート | `uv tool install "graphifyy[falkordb]"` |
| `svg` | SVG グラフのエクスポート | `uv tool install "graphifyy[svg]"` |
| `leiden` | Leiden コミュニティ検出（Python < 3.13 では graspologic、3.13+ ではネイティブバックエンド） | `uv tool install "graphifyy[leiden]"` |
| `ollama` | Ollama ローカル推論 | `uv tool install "graphifyy[ollama]"` |
| `openai` | OpenAI / OpenAI 互換 API | `uv tool install "graphifyy[openai]"` |
| `gemini` | Google Gemini API | `uv tool install "graphifyy[gemini]"` |
| `anthropic` | Anthropic Claude API（`--backend claude`、`ANTHROPIC_API_KEY` を使用） | `uv tool install "graphifyy[anthropic]"` |
| `bedrock` | AWS Bedrock（IAM を使用、API キー不要） | `uv tool install "graphifyy[bedrock]"` |
| `azure` | Azure OpenAI Service（`--backend azure`、`AZURE_OPENAI_API_KEY` + `AZURE_OPENAI_ENDPOINT` を使用） | `uv tool install "graphifyy[openai]"` |
| `sql` | SQL スキーマ抽出 | `uv tool install "graphifyy[sql]"` |
| `postgres` | ライブ PostgreSQL のイントロスペクション（`--postgres DSN`） | `uv tool install "graphifyy[postgres]"` |
| `dm` | BYOND DreamMaker `.dm`/`.dme` の AST 抽出（お使いのプラットフォームに合う wheel がない場合は C コンパイラ + `python3-dev` が必要なことがあります） | `uv tool install "graphifyy[dm]"` |
| `terraform` | Terraform / HCL `.tf`/`.tfvars`/`.hcl` の AST 抽出 | `uv tool install "graphifyy[terraform]"` |
| `pascal` | Pascal / Delphi `.pas`/`.dpr`/`.dpk`/`.inc` の AST 抽出（より正確な `calls`/`inherits` エッジ。存在しない場合は正規表現ベースの抽出器にフォールバック） | `uv tool install "graphifyy[pascal]"` |
| `ocaml` | OCaml `.ml`/`.mli` の AST 抽出 | `uv tool install "graphifyy[ocaml]"` |
| `commonlisp` | Common Lisp `.lisp`/`.cl`/`.lsp`/`.asd` の AST 抽出 | `uv tool install "graphifyy[commonlisp]"` |
| `robot` | Robot Framework `.robot`/`.resource` の抽出（スイート、テストケース、キーワード、キーワード呼び出し、resource/library のインポートエッジ） | `uv tool install "graphifyy[robot]"` |
| `chinese` | 中国語クエリの分かち書き（jieba） | `uv tool install "graphifyy[chinese]"` |
| `all` | 上記すべて | `uv tool install "graphifyy[all]"` |

</details>

---

## アシスタントに常にグラフを使わせる

グラフを構築した後、プロジェクトで一度だけ実行します：

プロジェクトで `graphify <platform> install` を一度実行します。たとえば `graphify claude install` や `graphify codex install`（または `graphify install --platform <name>`）です。

これにより小さな設定ファイルが書き込まれ、コードベースに関する質問ではナレッジグラフを参照し、完全なレポートを読んだり生のファイルを grep したりするよりも `graphify query "<question>"` のようなスコープを絞ったクエリを優先するよう、アシスタントに指示します。

- **フックプラットフォーム**（Claude Code、Gemini CLI）：検索系のツール呼び出しの前に（さらに Claude Code では、Read/Glob ツールでソースファイルを 1 つずつ読む前に）フックが自動的に発火し、アシスタントをグラフ経路へと導きます。
- **指示ファイルプラットフォーム**（Codex、OpenCode、Cursor など）：永続的な指示ファイル（`AGENTS.md`、`.cursor/rules/` など）が同じ「クエリ優先」のガイダンスを提供します。

`GRAPH_REPORT.md` は、広範なアーキテクチャレビューのために引き続き利用できます。

**CodeBuddy** は Claude Code と同じ 2 つのことを行います。アーキテクチャに関する質問に答える前に `graphify-out/GRAPH_REPORT.md` を読むよう CodeBuddy に伝える `CODEBUDDY.md` セクションを書き込み、Bash の検索コマンドとファイル読み取りの前に発火して `graphify query` の利用を促す `PreToolUse` フック（`.codebuddy/settings.json`）をインストールします。

**Codex** は `AGENTS.md` に書き込みます。これがこのプラットフォームで実際に常時オンのグラフガイダンスを担うものです。`graphify codex install` は `.codex/hooks.json` に `PreToolUse` フック（`graphify hook-check`）も登録しますが、そのエントリは意図的に**何もしません（no-op）**。Codex Desktop は `PreToolUse` 上の `hookSpecificOutput.additionalContext` を拒否するため、そこでナッジを発すると Bash のツール呼び出しが壊れてしまうからです。フック（`graphify hook-guard`）がナッジを行う Claude Code とは異なり、Codex ではフックが発火しても意図的に何もせず、`AGENTS.md` が常時オンの仕組みになります。

**Kilo Code** は Graphify スキルを `~/.config/kilo/skills/graphify/SKILL.md` に、ネイティブの `/graphify` コマンドを `~/.config/kilo/command/graphify.md` にインストールします。`graphify kilo install` は `AGENTS.md` に加えて、ネイティブの `tool.execute.before` プラグイン（`.kilo/plugins/graphify.js` + `.kilo/kilo.json` または `.kilo/kilo.jsonc` への登録）も書き込むため、Kilo はネイティブの `.kilo` 設定を通じて同じ常時オンのグラフリマインダー動作を得られます。

**Cursor** は `alwaysApply: true` を指定した `.cursor/rules/graphify.mdc` を書き込むため、Cursor はフックなしで、すべての会話に自動的にそれを含めます。

すべてのプラットフォームから graphify を一度に削除するには：`graphify uninstall`（`--purge` を追加すると `graphify-out/` も削除します）。または、プラットフォーム別のコマンド（例：`graphify claude uninstall`）を使います。

---

## レポートの中身

`GRAPH_REPORT.md` は、広範なアーキテクチャレビューのために、ゴッドノード、コミュニティ、主要な経路を要約します。グラフがどう構築され、何を含むかは **[How graphify works](https://docs.graphify.com/concepts/architecture)** を参照してください。

---

## 扱えるファイル

graphify は約 40 のプログラミング言語を tree-sitter の AST でローカルに解析し、オプションのセマンティックパスを通じてドキュメント、PDF、画像、音声/動画をマッピングします。全リストは **[Supported inputs](https://docs.graphify.com/concepts/supported-inputs)** にあります。

---

## よく使うコマンド

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

下記の[完全なコマンドリファレンス](#full-command-reference)を参照してください。

---

## ファイルの無視

graphify は `.gitignore` を尊重し、`--exclude` パターンとプロジェクトの `.graphifyignore` をサポートします。詳細は **[Configuration](https://docs.graphify.com/reference/configuration)** を参照してください。

---

## チームのセットアップ

グラフをコミットまたは共有して、チーム全員が同じコンテキストをクエリできるようにし、グラフのコンテキストを使ってプルリクエストをレビューしましょう。**[Share context with your team](https://docs.graphify.com/guides/team-workflows)** と **[Review pull requests](https://docs.graphify.com/guides/pull-requests)** を参照してください。

---

## グラフを直接使う

AI アシスタントの枠を超えて、`graphify query`、`graphify path`、`graphify explain` を使って CLI から直接 `graph.json` をクエリできます。**[Ask better graph questions](https://docs.graphify.com/guides/querying)** と **[query reference](https://docs.graphify.com/reference/query)** を参照してください。

---

## 環境変数

バックエンド、API キー、フックの動作、チューニングは環境変数で制御します。完全な表は **[Configuration](https://docs.graphify.com/reference/configuration)** にあります。

---

## プライバシー

- **コードファイル** —— tree-sitter を介してローカルで処理されます。何一つマシンの外に出ません。コードのみのコーパスには API キーが不要で、`graphify extract` は完全にオフラインで実行されます。混在リポジトリでは、`--code-only` を追加するとコードだけをインデックスし、本来 LLM を必要とするドキュメント/PDF/画像をスキップできます。
- **動画 / 音声** —— faster-whisper でローカルに文字起こしされます。何一つマシンの外に出ません。
- **ドキュメント、PDF、画像** —— セマンティック抽出のために AI アシスタントに送信されます（`/graphify` スキルを介し、IDE セッションが実行しているモデルを使用）。ヘッドレスの `graphify extract` には、`GEMINI_API_KEY` / `GOOGLE_API_KEY`（Gemini）、`MOONSHOT_API_KEY`（Kimi）、`ANTHROPIC_API_KEY`（Claude）、`OPENAI_API_KEY`（OpenAI）、`DEEPSEEK_API_KEY`（DeepSeek）、稼働中の Ollama インスタンス（`OLLAMA_BASE_URL`）、標準のプロバイダーチェーン経由の AWS 認証情報（Bedrock —— API キー不要、IAM を使用）、または `claude` CLI バイナリ（Claude Code —— API キー不要、Claude のサブスクリプションを使用）のいずれかが必要です。`--dedup-llm` フラグは同じキーを使います。
- **データレジデンシー** —— `graphify extract` は、設定されている API キーに基づいてどのプロバイダーを使うかを自動検出します（優先順位：Gemini → Kimi → Claude → OpenAI → DeepSeek → Azure → Bedrock → Ollama）。データレジデンシー要件のあるコードには、`--backend ollama`（完全ローカル）を使うか、明示的な `--backend` フラグを渡してください。Kimi（`MOONSHOT_API_KEY`）は中国の Moonshot AI のサーバーへルーティングします。
- **テレメトリーなし**、利用状況トラッキングなし、アナリティクスなし。
- **クエリのロギング** —— すべての `graphify query`、`graphify path`、`graphify explain`、および MCP の `query_graph` 呼び出しは、JSON Lines 形式で `~/.cache/graphify-queries.log` に記録されます（タイムスタンプ、質問、コーパス、返されたノード数、所要時間）。完全なサブグラフのレスポンスはデフォルトでは保存**されません**。オプトアウトするには `GRAPHIFY_QUERY_LOG_DISABLE=1` を設定するか、コードパスを無効化せずに黙らせるには `GRAPHIFY_QUERY_LOG=/dev/null` を設定します。

---

## トラブルシューティング

よくあるインストールと抽出の問題とその解決策は **[Troubleshooting](https://docs.graphify.com/troubleshooting)** にあります。

---

## 完全なコマンドリファレンス

すべてのコマンドとフラグを例付きで：**[CLI reference](https://docs.graphify.com/reference/overview)**。

---

## さらに詳しく

- [docs.graphify.com](https://docs.graphify.com) —— 完全なドキュメント：ガイド、コマンドリファレンス、統合
- [How it works](../how-it-works.md) —— 抽出パイプライン、コミュニティ検出、信頼度スコアリング、ベンチマーク
- [ARCHITECTURE.md](../../ARCHITECTURE.md) —— モジュールの内訳、言語の追加方法
- [Optional integrations](../docker-mcp-sqlite.md) —— Docker MCP Toolkit + SQLite
- [The Memory Layer](https://safishamsi.gumroad.com/l/qetvlo) —— graphify の背後にある考え方と、端から端までのアーキテクチャを扱った書籍

---

## Graphify Cloud

[**Graphify Cloud**](https://app.graphify.com/login) は、graphify の上に構築された常時オンのレイヤーです。フォルダーごとにオンデマンドで再構築するグラフではなく、ソフトウェア開発ライフサイクル全体にわたって 1 つのライブグラフを保ちます：

- **トークン 80% 削減** —— 常時オンのメモリにより、エージェントがセッションのたびにコードベースを読み直し、説明し直すのをやめられます。
- **モノレポとクロスリポジトリ** —— すべてのサービスとリポジトリにまたがる 1 つの連結したグラフ。フォルダーごとのグラフではありません。
- **形式的検証** —— アーキテクチャと依存関係の不変条件をライブグラフに照らして検査します。
- **SDLC を俯瞰するコードレビュー** —— マージ前に、変更がシステム全体にどう波及するかを確認できます。
- **SDLC コネクタ** —— Sentry、Jira などを取り込み、インシデント、チケット、コードが 1 つのグラフに収まります。
- **常時オン** —— コード、ドキュメント、会議にわたってバックグラウンドで継続的に更新します。

**[app.graphify.com で 14 日間の無料トライアルを始める &rarr;](https://app.graphify.com/login)**

---

## コントリビューション

コントリビューションを歓迎します。開発環境のセットアップ、テストと CI 一致のためのコマンド、git ワークフロー、そして何が優れたコントリビューションになるか（実践的な例と抽出バグレポートが最も役立ちます）については **[CONTRIBUTING.md](../../CONTRIBUTING.md)** を参照してください。アーキテクチャと言語の追加方法：[ARCHITECTURE.md](../../ARCHITECTURE.md)。

初めてですか？[Discord](https://discord.gg/XDnKVpzdXB) か [GitHub Discussions](https://github.com/Graphify-Labs/graphify/discussions) で気軽に挨拶してください。

---

## コントリビューター

<a href="https://github.com/Graphify-Labs/graphify/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=Graphify-Labs/graphify" alt="graphify contributors" />
</a>

[contrib.rocks](https://contrib.rocks) で作成。

---

## 翻訳

この README は 32 言語で利用できます。このファイルの上部にある言語スイッチャーを使ってお使いの言語で読むか、[`docs/translations/`](./) を参照してください。翻訳を改善したり新しい翻訳を追加したりするには、そこにある対応するファイルに対してプルリクエストを開いてください。

---

## graphify の上に構築する

graphify のエコシステムで何かを構築していますか？それは歓迎されます。プロジェクト名に "graphify" を使う場合（たとえば `graphify-dashboard` や `graphify-action`）、それがコミュニティ製であり、Graphify Labs と提携しておらず、その推薦も受けていないことを明確にする短い注記を README に追加してください。"graphify" と graphify のロゴは Graphify Labs の標章です。公式であるかのように示唆する形で使わないでください。

---

## コミュニティとリンク

<p align="center">
  <a href="https://graphify.com"><img src="https://img.shields.io/badge/Website-graphify.com-4c1?style=flat&logo=googlechrome&logoColor=white" alt="Website"/></a>
  <a href="https://discord.gg/XDnKVpzdXB"><img src="https://img.shields.io/badge/Discord-Join-5865F2?style=flat&logo=discord&logoColor=white" alt="Discord"/></a>
  <a href="https://x.com/graphify"><img src="https://img.shields.io/badge/X-graphify-000000?logo=x&logoColor=white" alt="X"/></a>
  <a href="https://www.youtube.com/@graphifylabs"><img src="https://img.shields.io/badge/YouTube-Graphify%20Labs-FF0000?style=flat&logo=youtube&logoColor=white" alt="YouTube"/></a>
  <a href="https://github.com/sponsors/safishamsi"><img src="https://img.shields.io/badge/sponsor-safishamsi-ea4aaa?logo=github-sponsors" alt="Sponsor"/></a>
  <a href="https://safishamsi.gumroad.com/l/qetvlo"><img src="https://img.shields.io/badge/Book-The%20Memory%20Layer-2ea44f?style=flat&logo=gitbook&logoColor=white" alt="The Memory Layer"/></a>
</p>
