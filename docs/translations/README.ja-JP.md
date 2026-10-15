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
  <b>エージェントのトークン支出を 80% 削減。</b> Graphify Cloud は常時稼働のメモリであり、エージェントを統制し、コード品質を高く保ち、形式的検証で正しさを証明します。<a href="https://app.graphify.com/login"><b>14 日間の無料トライアルを始める &rarr;</b></a>
</p>

AI コーディングアシスタントで `/graphify` と入力すると、プロジェクト全体（コード、ドキュメント、PDF、画像、動画）を**ナレッジグラフ**にマッピングし、ファイルを grep する代わりに**クエリで調べられる**ようになります。

- **コードのマッピングは無料で、完全にローカル。** コードは tree-sitter の AST で解析されます。決定論的で、LLM を使わず、何もマシンの外に出ません。（ドキュメント、PDF、画像、動画は、アシスタントのモデルまたは設定した API key を使って意味的なパスを 1 回行います。）
- **すべてのエッジに説明がある。** 各接続は `EXTRACTED`（ソース内に明示的に存在）または `INFERRED`（graphify が解決）とタグ付けされるので、直接読み取ったものと推論したものを区別できます。
- **ベクトルインデックスではない。** 埋め込みもベクトルストアもありません。実際にたどれるグラフです。質問する、2 つのものの間のパスをたどる、1 つの概念を説明する、といったことができます。

> [!NOTE]
> **常時稼働にしたいですか？** [Graphify Cloud](https://app.graphify.com/login) は SDLC 全体でグラフを常にライブに保ちます。モノレポおよびリポジトリ横断のサポート、形式的検証、SDLC を俯瞰するコードレビュー、さらに Sentry、Jira などのコネクタにより、インシデントやチケットがコードと同じグラフに収まります。**[app.graphify.com で 14 日間の無料トライアルを始める](https://app.graphify.com/login)**。

<p align="center">
  <img src="https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/graph-hero.png" alt="graphify のインタラクティブな graph.html が、FastAPI コードベースを力学的に配置されたナレッジグラフとして、検出されたコミュニティの凡例とともに表示している" width="900">
</p>
<p align="center">
  <em>graphify がマッピングした FastAPI コードベース。すべてのノードは概念であり、色は検出されたコミュニティを表し、全体が graph.html でクリック可能です。</em>
</p>

**始め方**（30 seconds）。Python 3.10+ と uv（または pipx）が必要です。

```bash
uv tool install graphifyy      # install the CLI (or: pipx install graphifyy)
graphify install               # detects your assistant and registers the skill
```

次に、AI アシスタントで次のように入力します。

```
/graphify .
```

これで完了です。**3 つのファイル**が得られます。

```
graphify-out/
├── graph.html       open in any browser: click nodes, filter, search
├── GRAPH_REPORT.md  the highlights: key concepts, surprising connections, suggested questions
└── graph.json       the full graph: query it anytime without re-reading your files
```

永続化されたグラフには `graph.schema_version` が含まれており、統合側は互換性のないフォーマット変更を検出できます。さらに、それを生成した Graphify のリリースを示す `graph.graphify_version` も含まれます。

**1 回のインストールで、どのアシスタントでも、どの OS でも。** Claude Code、Cursor、Codex、Gemini CLI、GitHub Copilot、そして 20+ 以上に対応し、macOS、Linux、Windows で動作します。[プラットフォームを選ぶ](#install)。

---

## 実際の動作を見る

<p align="center">
  <img src="https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/demo-path.svg" alt="graphify のパスクエリ: ターミナルが FastAPI と ModelField の間の最短パスを尋ね、その答えがナレッジグラフ上でホップごとに点灯していく" width="900">
</p>

グラフが構築されると、ファイルを読む代わりにそれをクエリします。これは実際の出力で、graphify を上記の FastAPI コードベースで実行したものです。

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

すべてのエッジには**信頼度タグ**が付いています（`EXTRACTED` = ソース内に明示的に存在、`INFERRED` = 解決によって導出）。そのため、直接読み取ったものと推論したものを区別できます。`graphify query "<question>"` は平易な言葉による質問に対してスコープ付きのサブグラフを返し、`graphify path A B` は任意の 2 つのものがどうつながっているかをたどります。

---

## 何をするのか

そのまま使える内容は次のとおりです。

| 機能 | 得られるもの |
|---|---|
| **God nodes** | 最も多く接続された概念。すべてが何を通って流れているかが見えます |
| **Communities** | グラフをサブシステムに分割（Leiden）し、LLM 不要のラベルを付けます |
| **Cross-file links** | `calls` / `imports` / `inherits` / `mixes_in` を tree-sitter AST により ~40 languages にわたって解決します |
| **Query, path, explain** | 質問する、2 つのものの間のパスをたどる、1 つの概念を説明する。すべて `graph.json` に対して行います |
| **Rationale + doc refs** | `# NOTE:` / `# WHY:` コメントや ADR/RFC の引用が一級ノードになり、コードにリンクされます |
| **Beyond code** | ドキュメント、PDF、画像、動画/音声がすべて同じグラフにマッピングされます |
| **Local-first** | コードは tree-sitter でローカルに解析されます（LLM なし、何もマシンの外に出ません）。ドキュメント/メディアに対する意味的なパスだけがバックエンドを呼び出し、それも設定した場合のみです |

> [!TIP]
> これを多数のリポジトリやモノレポで実行していますか？[Graphify Cloud](https://app.graphify.com/login) はそれを継続的に行い、エージェントのトークン支出を 80% 削減します。リポジトリ横断のリンク、SDLC 全体のコードレビュー、形式的検証、Sentry/Jira コネクタを備えています。[14 日間の無料トライアルを始める &rarr;](https://app.graphify.com/login)

---

## ベンチマーク: 0.497 recall@10, 0 LLM credits

| Benchmark | Metric | graphify | Field |
|---|---|---|---|
| LOCOMO (n=300) | recall@10 | **0.497** | mem0 0.048, supermemory 0.149 |
| LOCOMO (n=300) | QA accuracy | 45.3% | supermemory 49.7%, mem0 27.3% |
| LongMemEval-S (n=50) | QA accuracy | **76%** | tied with dense RAG |
| ERPNext cross-tool (n=6) | key-fact coverage | **82.0%** | grep/read baseline 70.8% |
| Graph build | LLM credits | **0** | per-token for most systems |

すべてのシステムは、同じハーネス上で、同じモデルと予算で実行され、2 人目の審査員に対してブラインド検証された審査員によって採点されました（90.6% agreement、Cohen's kappa 0.81）。システムごとの完全な表、コードインテリジェンスの結果、再現コマンドは次を参照してください。**[BENCHMARKS.md](../../BENCHMARKS.md)**。

---

## ドキュメント

完全なガイドとリファレンスは **[docs.graphify.com](https://docs.graphify.com)** にあります。

- **[Quickstart](https://docs.graphify.com/quickstart)**: 最初のグラフを構築する
- **[CLI reference](https://docs.graphify.com/reference/overview)**: すべてのコマンドとフラグ
- **[Ask better graph questions](https://docs.graphify.com/guides/querying)**: クエリのパターン
- **[Configuration](https://docs.graphify.com/reference/configuration)**: 環境変数とチューニング
- **[Supported inputs](https://docs.graphify.com/concepts/supported-inputs)**: 言語とファイルタイプ
- **[Team workflows](https://docs.graphify.com/guides/team-workflows)** と **[PR review](https://docs.graphify.com/guides/pull-requests)**
- **[Troubleshooting](https://docs.graphify.com/troubleshooting)** と **[How it works](https://docs.graphify.com/concepts/architecture)**

---

## 前提条件

| 要件 | 最小 | 確認 | インストール |
|---|---|---|---|
| Python | 3.10+ | `python --version` | [python.org](https://www.python.org/downloads/) |
| uv *(recommended)* | any | `uv --version` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| pipx *(alternative)* | any | `pipx --version` | `pip install pipx` |

**macOS クイックインストール（Homebrew）:**
```bash
brew install python@3.12 uv
```

**Windows クイックインストール:**
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
> **公式パッケージ:** PyPI パッケージは `graphifyy`（y が 2 つ）です。PyPI 上の他の `graphify*` パッケージは関係ありません。CLI コマンドは依然として `graphify` です。

公式のソースリポジトリは [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify) です。

2 コマンドのクイックスタートはこの README の冒頭にあります。このセクションでは、インストール方法、プロジェクトスコープのインストール、そして対応するすべてのプラットフォームを扱います。

**インストール方法**（いずれか 1 つを選択）:

```bash
uv tool install graphifyy   # recommended, isolated env (if 'graphify' isn't found after, run: uv tool update-shell)
pipx install graphifyy      # alternative
pip install graphifyy       # may need PATH setup, see Troubleshooting below
```

次に `graphify install` を 1 回実行します。これは実行しているアシスタントを検出してスキルを登録するので、アシスタントごとのセットアップは不要です。AI アシスタントを開いて `/graphify .` と入力してください。

アシスタントスキルをユーザープロファイルではなく現在のリポジトリにインストールするには、`--project` を追加します。

```bash
graphify install --project
graphify install --project --platform codex
```

プロジェクトスコープのインストールは現在のディレクトリの下に書き込まれます。例えば `.claude/skills/graphify/SKILL.md` や `.agents/skills/graphify/SKILL.md`（さらにスキルがオンデマンドで読み込む `references/` サイドカー）であり、コミット可能なファイルについては `git add` のヒントを出力します。プロジェクトスコープのインストールに対応するプラットフォーム別コマンドも同じフラグを受け付けます。例えば `graphify claude install --project` や `graphify codex install --project` です。

> [!TIP]
> `command not found`、Mac/Windows での `pip` の問題、PowerShell のクォート、`uvx` の使い方、git フックの PATH の癖、または strict モードに遭遇していますか？**[Installation](https://docs.graphify.com/installation)** と **[Troubleshooting](https://docs.graphify.com/troubleshooting)** を参照してください。

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

Codex のユーザーは、並列抽出のために `~/.codex/config.toml` の `[features]` の下に `multi_agent = true` も必要です。CodeBuddy は Claude Code と同じ Agent tool と PreToolUse hook の仕組みを使います。Factory Droid は並列サブエージェントのディスパッチに `Task` tool を使います。OpenClaw と Aider は逐次抽出を使います（これらのプラットフォームでの並列エージェントのサポートはまだ初期段階です）。Trae は並列サブエージェントのディスパッチに Agent tool を使い、`PreToolUse` hook には**対応していない**ため、AGENTS.md が常時稼働の仕組みになります。

`--platform agents`（別名 `--platform skills`）は、汎用のクロスフレームワーク [Agent-Skills](https://github.com/anthropics/skills) の場所を対象にします。グローバルインストールには仕様のユーザーグローバルな `~/.agents/skills/`（`npx skills` と仕様準拠のフレームワークが読み込む）を、プロジェクト（`--project`）インストールには `./.agents/skills/` を使います。素の `graphify install` は設計上、単一プラットフォーム（Claude Code）のままです。`.agents/skills` を読み込む任意のフレームワークからスキルを発見可能にしたい場合は、名前付きの `agents` プラットフォームを使ってください。

Pi には `PreToolUse` hook がないため、`graphify pi guard install` は（Pi 自身の `pi install <package directory>` を介して）ネイティブな Pi 拡張を登録し、Pi の `read`、`grep`、`find`、および検索系の `bash` 呼び出しの前に、インストール済みの `graphify hook-guard` を実行します。新鮮/陳腐なグラフの判断と、`GRAPHIFY_HOOK_STRICT=1` によるセッションごとに 1 回のインデックス済み読み取り拒否は、同じポリシーから来るため、Pi は Claude Code の hook の挙動と一致します。ガイダンスは `<system-reminder source="graphify">` ステアリングメッセージとして届きます。これには Pi 0.58.4 以降が必要です。それより前のバージョンでは、ステアリングメッセージが並列ツール呼び出しバッチの残りをスキップさせてしまいます。このパッケージは Graphify のインストールに同梱されているため、Graphify を永続的にインストールし（`uvx` ではなく `uv tool install graphifyy` または `pipx install graphifyy`）、インストールまたはアップグレード後に Pi を再起動し、`graphify pi guard uninstall` で削除してください。検査されるのはローカルファイルのターゲットのみです。この hook はプロジェクト外の絶対的な `PATH` エントリ上に `graphify` があることを必要とし、2 秒、入力 256 KiB/出力 64 KiB の呼び出しに制限され、失敗時はオープンにフェイルします。同じパッケージは [Oh My Pi](https://github.com/can1357/oh-my-pi) にも読み込まれます: `omp plugin install "$(graphify pi guard path)"`。登録されるパスには Python のバージョンと venv が含まれるため、いずれかを変更した後は `graphify pi guard install` を再実行し、古いエントリは `pi remove <old path>` で削除してください。

> Codex は `/graphify` の代わりに `$graphify` を使います。

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

## アシスタントに常にグラフを使わせる

グラフを構築した後、プロジェクトでこれを 1 回実行します。

プロジェクトで `graphify <platform> install` を 1 回実行します。例えば `graphify claude install` や `graphify codex install`（または `graphify install --platform <name>`）です。

これは小さな設定ファイルを書き込み、コードベースに関する質問ではナレッジグラフを参照するよう、そしてレポート全体を読んだり生のファイルを grep したりするより `graphify query "<question>"` のようなスコープ付きクエリを優先するよう、アシスタントに伝えます。

- **Hook プラットフォーム**（Claude Code、Gemini CLI）: 検索系のツール呼び出しの前に（Claude Code では、Read/Glob ツールでソースファイルを 1 つずつ読む前にも）hook が自動的に発火し、アシスタントをグラフのパスへ促します。
- **指示ファイルプラットフォーム**（Codex、OpenCode、Cursor など）: 永続的な指示ファイル（`AGENTS.md`、`.cursor/rules/` など）が同じクエリ優先のガイダンスを提供します。

`GRAPH_REPORT.md` は依然として幅広いアーキテクチャレビューに利用できます。

各プラットフォームが具体的にどのファイルを書き込むか（CodeBuddy の `CODEBUDDY.md` + `PreToolUse` hooks、Codex の `AGENTS.md`、Kilo のネイティブ `.kilo` プラグイン、Cursor の `alwaysApply` ルールなど）は、**[Always-on setup](https://docs.graphify.com/guides/always-on)** で扱っています。

すべてのプラットフォームから graphify を一度に削除するには: `graphify uninstall`（`--purge` を追加すると `graphify-out/` も削除します）。または、プラットフォーム別コマンド（例: `graphify claude uninstall`）を使います。

### CLI スキルか MCP 指示か？

`graphify install` がインストールする指示と、Graphify MCP 接続に付属する指示は、グラフをクエリする異なる方法を記述します。

| Setup | Guidance to use | Query access |
|---|---|---|
| ローカル CLI とインストール済みのアシスタントスキル | `graphify install` が書き込んだプラットフォームの指示 | ローカルグラフ（デフォルトは `graphify-out/`）に対して `graphify query`、`graphify path`、`graphify explain` を実行します。 |
| 接続された Graphify MCP サーバー | その接続の指示と、そのサーバーがリストするツール | その接続が提供するグラフに対して、リストされた MCP ツールを呼び出します。ツール名と説明はサーバーから来ます。 |

どちらも、幅広いソース検索の前にスコープ付きのグラフクエリを行うことを推奨します。アシスタントが実際にアクセスできるツールに合った指示を選んでください。どちらのブロックも、アシスタントの指示ファイルに対する普遍的な優先順位ルールを確立するものではありません。両方の統合を使う場合は、それぞれがどのグラフをクエリするかを特定し、2 つの無条件な指示ブロックを `AGENTS.md` にコピーするのではなく、主要なクエリパスを 1 つ選んでください。

`graphify install` はローカルのアシスタント統合をインストールするものであり、MCP 接続を確立するものではありません。MCP クライアントは、接続先のサーバーを使うためにローカル CLI クエリを実行する必要はありません。ローカルでホストされるサーバーは依然として自身の Graphify インストールとグラフを必要としますが、ホスト型の接続は、クライアントの作業ディレクトリに存在しないグラフを提供することがあります。期待したツールが見当たらない場合は、他方のセットアップの指示を相互に置き換え可能なものとして扱うのではなく、該当する CLI インストールや MCP 接続を確認してください。

---

## レポートの中身

`GRAPH_REPORT.md` は、幅広いアーキテクチャレビューのために god nodes、コミュニティ、主要なパスを要約します。グラフがどう構築され、何を含むかは **[How graphify works](https://docs.graphify.com/concepts/architecture)** を参照してください。

---

## 扱えるファイル: ~40 languages

graphify は ~40 programming languages を tree-sitter AST でローカルに解析し、ドキュメント、PDF、画像、音声/動画を任意の意味的パスを通してマッピングします。完全なリストは **[Supported inputs](https://docs.graphify.com/concepts/supported-inputs)** を参照してください。

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

graphify hook install              # auto-rebuild on commit + branch checkout (run `graphify update .` after `git pull`: see "Recommended workflow" below)
graphify merge-graphs a.json b.json              # combine two graphs

graphify prs                       # PR dashboard: CI state, review status, worktree mapping
graphify prs 42                    # deep dive on PR #42 with graph impact
graphify prs --triage              # AI ranks your review queue (uses whatever backend is configured)
graphify prs --conflicts           # PRs sharing graph communities: merge-order risk
```

下記の[完全なコマンドリファレンス](#full-command-reference)を参照してください。

---

## ファイルの無視

graphify は `.gitignore` を尊重し、`--exclude` パターンとプロジェクトの `.graphifyignore` をサポートします。詳細は **[Configuration](https://docs.graphify.com/reference/configuration)** を参照してください。


## プロジェクト設定

1 回の実行ではなくプロジェクトに属する設定のために、スキャンのルートに `.graphifyrc` を作成します。1 行につき 1 つの `key=value` で、`#` で始まる行はコメントです。

**あいまいな拡張子。** いくつかの拡張子は、プロジェクトによって異なる言語を意味します。`.inc` は pfSense では PHP、Delphi のツリーでは Pascal、それ以外では SQL やアセンブリです。`.h` は C か C++、`.m` は Objective-C か MATLAB です。graphify はグローバルなデフォルトを 1 つ選ばなければならず、選択を誤ってもファイルは失敗しません。誤った言語として解析され、わずかな付随的ノードを生成するため、実際のシンボルが欠けているのにグラフは中身があるように見えます。その拡張子がリポジトリで何を意味するかを宣言してください。

```
# .graphifyrc
# A language name:
language.inc=php
# Or an extension graphify already knows:
language.tpl=.ts
# Baked into the git hooks (see Team setup):
viz_node_limit=0
```

この宣言は、分類、抽出器の選択、文法と解決、インポート、`graphify watch`、AST キャッシュ（別の言語で再解析されたファイルは古いエントリを決して再利用しません）を通じて反映され、同じ `.graphifyrc` は `extract`、`update`、hooks、MCP サーバー、`/graphify` スキルによって読み込まれます。タイプミスは stderr に 1 回報告され、スキャンはデフォルトで続行します。宣言がキャッシュ、インクリメンタルな再構築、インポート解決とどう相互作用するかは **[Configuration](https://docs.graphify.com/reference/configuration)** を参照してください。

---

## チームのセットアップ

グラフをコミットまたは共有して、チーム全体が同じコンテキストをクエリできるようにし、グラフのコンテキストでプルリクエストをレビューします。**[Share context with your team](https://docs.graphify.com/guides/team-workflows)** と **[Review pull requests](https://docs.graphify.com/guides/pull-requests)** を参照してください。

---

## グラフを直接使う

AI アシスタントに加えて、`graphify query`、`graphify path`、`graphify explain` で CLI から直接 `graph.json` をクエリできます。複数のノードに一致する名前は、推測するのではなく候補を列挙して拒否されます。スクリプトは終了コードから結果を読み取れます。`0` は答え、`3` はあいまいな名前、`4` は一致するノードなし、です。**[Ask better graph questions](https://docs.graphify.com/guides/querying)** と **[query reference](https://docs.graphify.com/reference/query)** を参照してください。

---

## 環境変数

バックエンド、API key、hook の挙動、チューニングは環境変数で制御します。完全な表は **[Configuration](https://docs.graphify.com/reference/configuration)** を参照してください。

---

## プライバシー

- **コードファイル**: tree-sitter を介してローカルで処理されます。何もマシンの外に出ません。コードのみのコーパスは API key を必要としません。`graphify extract` は完全にオフラインで実行されます。混在リポジトリでは、`--code-only` を追加するとコードだけをインデックス化し、本来 LLM を必要とするドキュメント/PDF/画像をスキップします。
- **動画 / 音声**: faster-whisper でローカルに書き起こされます。何もマシンの外に出ません。
- **ドキュメント、PDF、画像**: 意味的抽出のために AI アシスタントに送られます（`/graphify` スキルを介し、IDE セッションが実行するモデルを使用）。ヘッドレスの `graphify extract` は、`GEMINI_API_KEY` / `GOOGLE_API_KEY`（Gemini）、`MOONSHOT_API_KEY`（Kimi）、`ANTHROPIC_API_KEY`（Claude）、`OPENAI_API_KEY`（OpenAI）、`DEEPSEEK_API_KEY`（DeepSeek）、稼働中の Ollama インスタンス（`OLLAMA_BASE_URL`）、標準のプロバイダチェーン経由の AWS 認証情報（Bedrock、API key 不要、IAM を使用）、または `claude` CLI バイナリ（Claude Code、API key 不要、あなたの Claude サブスクリプションを使用）を必要とします。`--dedup-llm` フラグは同じ key を使います。
- **データ所在地**: `graphify extract` は、どの API key が設定されているかに基づいて使用するプロバイダを自動検出します（優先順位: Gemini → Kimi → Claude → OpenAI → DeepSeek → Azure → Bedrock → Ollama）。データ所在地の要件があるコードには、`--backend ollama`（完全にローカル）を使うか、明示的な `--backend` フラグを渡してください。Kimi（`MOONSHOT_API_KEY`）は中国の Moonshot AI サーバーへルーティングされます。
- **テレメトリなし**、使用状況の追跡なし、分析なし。
- **クエリのログ記録**: すべての `graphify query`、`graphify path`、`graphify explain`、および MCP `query_graph` の呼び出しは、JSON Lines 形式で `~/.cache/graphify-queries.log` に記録されます（タイムスタンプ、質問、コーパス、返されたノード、所要時間）。完全なサブグラフのレスポンスはデフォルトでは**保存されません**。`GRAPHIFY_QUERY_LOG_DISABLE=1` を設定するとオプトアウトでき、`GRAPHIFY_QUERY_LOG=/dev/null` を設定するとコードパスを無効化せずに静かにできます。

---

## トラブルシューティング

よくあるインストールと抽出の問題とその修正: **[Troubleshooting](https://docs.graphify.com/troubleshooting)**。

---

## 完全なコマンドリファレンス

すべてのコマンドとフラグ、例付き: **[CLI reference](https://docs.graphify.com/reference/overview)**。

---

## さらに詳しく

- [docs.graphify.com](https://docs.graphify.com): 完全なドキュメント: ガイド、コマンドリファレンス、統合
- [How it works](../how-it-works.md): 抽出パイプライン、コミュニティ検出、信頼度スコアリング、ベンチマーク
- [ARCHITECTURE.md](../../ARCHITECTURE.md): モジュールの内訳、言語の追加方法
- [Optional integrations](../docker-mcp-sqlite.md): Docker MCP Toolkit + SQLite
- [The Memory Layer](https://safishamsi.gumroad.com/l/qetvlo): graphify の背後にある考え方と、端から端までのアーキテクチャについての書籍

---

## Graphify Cloud

[**Graphify Cloud**](https://app.graphify.com/login) は、graphify の上に構築された常時稼働のレイヤーです。フォルダごとにオンデマンドで再構築するグラフではなく、ソフトウェア開発ライフサイクル全体で 1 つのライブなグラフを保ちます。

- **80% 少ないトークン**: 常時稼働のメモリにより、エージェントはセッションごとにコードベースを読み直したり説明し直したりするのをやめます。
- **モノレポとリポジトリ横断**: フォルダごとのグラフではなく、すべてのサービスとリポジトリにまたがる 1 つの接続されたグラフ。
- **形式的検証**: アーキテクチャと依存関係の不変条件をライブなグラフに対して検査します。
- **SDLC を俯瞰するコードレビュー**: マージする前に、変更がシステム全体にどう波及するかを把握します。
- **SDLC コネクタ**: Sentry、Jira などを取り込み、インシデント、チケット、コードが 1 つのグラフに存在するようにします。
- **常時稼働**: コード、ドキュメント、会議にまたがり、バックグラウンドで継続的に更新します。

**[app.graphify.com で 14 日間の無料トライアルを始める &rarr;](https://app.graphify.com/login)**

---

## コントリビューション

コントリビューションを歓迎します。開発環境のセットアップ、テストと CI-parity のコマンド、git ワークフロー、そして何が優れたコントリビューションになるか（実例と抽出バグレポートが最も役立ちます）については、**[CONTRIBUTING.md](../../CONTRIBUTING.md)** を参照してください。アーキテクチャと言語の追加方法: [ARCHITECTURE.md](../../ARCHITECTURE.md)。

初めてですか？[Discord](https://discord.gg/XDnKVpzdXB) または [GitHub Discussions](https://github.com/Graphify-Labs/graphify/discussions) で挨拶してください。

---

## コントリビューター

<a href="https://github.com/Graphify-Labs/graphify/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=Graphify-Labs/graphify" alt="graphify contributors" />
</a>

Made with [contrib.rocks](https://contrib.rocks).

---

## 翻訳

この README は 32 言語で利用できます。このファイルの上部にある言語スイッチャーを使って自分の言語で読むか、[`docs/translations/`](./) を閲覧してください。翻訳を改善したり新しいものを追加したりするには、そこの該当ファイルに対してプルリクエストを開いてください。

---

## graphify の上に構築する

graphify のエコシステムで何かを作っていますか？それは歓迎されます。あなたのプロジェクトが名前に「graphify」を使う場合（例えば `graphify-dashboard` や `graphify-action`）、それがコミュニティ製であり、Graphify Labs と提携も推薦もされていないことを明確にする短い注記を README に追加してください。「graphify」と graphify のロゴは Graphify Labs のマークです。公式であることを暗示するような形で使わないでください。

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
