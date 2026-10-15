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
  <b>Cắt giảm chi phí token của agent đi 80%.</b> Graphify Cloud là bộ nhớ luôn bật, giúp quản trị các agent của bạn, giữ chất lượng code ở mức cao, và chứng minh tính đúng đắn bằng kiểm chứng hình thức. <a href="https://app.graphify.com/login"><b>Bắt đầu dùng thử miễn phí 14 ngày &rarr;</b></a>
</p>

Gõ `/graphify` trong trợ lý lập trình AI của bạn và nó ánh xạ toàn bộ dự án của bạn (code, tài liệu, PDF, hình ảnh, video) thành một **đồ thị tri thức** mà bạn có thể **truy vấn thay vì grep** xuyên qua các tệp.

- **Ánh xạ code miễn phí, hoàn toàn cục bộ.** Code được phân tích bằng tree-sitter AST: xác định, không dùng LLM, không gì rời khỏi máy của bạn. (Tài liệu, PDF, hình ảnh và video dùng mô hình của trợ lý của bạn, hoặc một API key đã cấu hình, cho một lượt xử lý ngữ nghĩa.)
- **Mọi cạnh đều được giải thích.** Mỗi kết nối được gắn thẻ `EXTRACTED` (hiện diện rõ ràng trong nguồn) hoặc `INFERRED` (được graphify giải quyết), nên bạn có thể phân biệt điều gì được đọc trực tiếp với điều gì được suy luận.
- **Không phải chỉ mục vector.** Không embedding, không kho vector: một đồ thị thực sự mà bạn duyệt qua. Hỏi một câu hỏi, lần theo đường đi giữa hai thứ, hoặc giải thích một khái niệm.

> [!NOTE]
> **Muốn cái này luôn bật?** [Graphify Cloud](https://app.graphify.com/login) giữ đồ thị luôn sống xuyên suốt toàn bộ SDLC của bạn: hỗ trợ monorepo và liên repo, kiểm chứng hình thức, và rà soát code với góc nhìn bao quát toàn cảnh SDLC của bạn, cùng các trình kết nối cho Sentry, Jira và nhiều hơn nữa để sự cố và ticket nằm trong cùng đồ thị với code của bạn. **[Bắt đầu dùng thử miễn phí 14 ngày tại app.graphify.com](https://app.graphify.com/login)**.

<p align="center">
  <img src="https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/graph-hero.png" alt="graph.html tương tác của graphify hiển thị mã nguồn FastAPI dưới dạng đồ thị tri thức bố trí theo lực, kèm chú giải các cộng đồng được phát hiện" width="900">
</p>
<p align="center">
  <em>Mã nguồn FastAPI được graphify ánh xạ. Mỗi nút là một khái niệm, màu sắc là các cộng đồng được phát hiện, và toàn bộ có thể nhấp được trong graph.html.</em>
</p>

**Bắt đầu** (30 seconds). Cần Python 3.10+ và uv (hoặc pipx):

```bash
uv tool install graphifyy      # install the CLI (or: pipx install graphifyy)
graphify install               # detects your assistant and registers the skill
```

Sau đó, trong trợ lý AI của bạn:

```
/graphify .
```

Vậy là xong. Bạn nhận được **ba tệp**:

```
graphify-out/
├── graph.html       open in any browser: click nodes, filter, search
├── GRAPH_REPORT.md  the highlights: key concepts, surprising connections, suggested questions
└── graph.json       the full graph: query it anytime without re-reading your files
```

Đồ thị được lưu bao gồm `graph.schema_version` để các tích hợp có thể phát hiện các thay đổi định dạng không tương thích, cùng với `graph.graphify_version` xác định bản phát hành Graphify đã tạo ra nó.

**Một lần cài đặt, mọi trợ lý, mọi hệ điều hành.** Claude Code, Cursor, Codex, Gemini CLI, GitHub Copilot, và 20+ trợ lý khác, trên macOS, Linux và Windows: [chọn nền tảng của bạn](#install).

---

## Xem nó hoạt động

<p align="center">
  <img src="https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/demo-path.svg" alt="truy vấn đường đi của graphify: một terminal hỏi đường đi ngắn nhất giữa FastAPI và ModelField, và câu trả lời sáng lên từng chặng xuyên qua đồ thị tri thức" width="900">
</p>

Khi đồ thị đã được dựng, bạn truy vấn nó thay vì đọc các tệp. Đây là kết quả thực, graphify chạy trên mã nguồn FastAPI được hiển thị ở trên:

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

Mọi cạnh đều mang một **thẻ độ tin cậy** (`EXTRACTED` = hiện diện rõ ràng trong nguồn, `INFERRED` = suy ra từ việc giải quyết), nên bạn có thể phân biệt điều gì được đọc trực tiếp với điều gì được suy luận. `graphify query "<question>"` trả về một đồ thị con giới hạn phạm vi cho một câu hỏi bằng ngôn ngữ thông thường, và `graphify path A B` lần theo cách hai thứ bất kỳ kết nối với nhau.

---

## Nó làm gì

Những gì bạn nhận được ngay từ đầu:

| Khả năng | Bạn nhận được gì |
|---|---|
| **God nodes** | Các khái niệm được kết nối nhiều nhất, để bạn thấy mọi thứ chảy qua đâu |
| **Communities** | Đồ thị được chia thành các hệ thống con (Leiden), với nhãn không cần LLM |
| **Cross-file links** | `calls` / `imports` / `inherits` / `mixes_in` được giải quyết xuyên qua ~40 languages thông qua tree-sitter AST |
| **Query, path, explain** | Hỏi một câu hỏi, lần theo đường đi giữa hai thứ, hoặc giải thích một khái niệm, tất cả đều dựa trên `graph.json` |
| **Rationale + doc refs** | Các chú thích `# NOTE:` / `# WHY:` và trích dẫn ADR/RFC trở thành các nút hạng nhất được liên kết với code |
| **Beyond code** | Tài liệu, PDF, hình ảnh, và video/âm thanh đều ánh xạ vào cùng một đồ thị |
| **Local-first** | Code được phân tích cục bộ bằng tree-sitter (không LLM, không gì rời khỏi máy của bạn); chỉ lượt xử lý ngữ nghĩa trên tài liệu/media mới gọi tới backend, và chỉ khi bạn cấu hình một backend |

> [!TIP]
> Đang chạy cái này trên nhiều repo hay một monorepo? [Graphify Cloud](https://app.graphify.com/login) làm điều đó liên tục và cắt giảm chi phí token của agent đi 80%, với liên kết liên repo, rà soát code trên toàn bộ SDLC, kiểm chứng hình thức, và các trình kết nối Sentry/Jira. [Bắt đầu dùng thử miễn phí 14 ngày &rarr;](https://app.graphify.com/login)

---

## Benchmark: 0.497 recall@10, 0 LLM credits

| Benchmark | Metric | graphify | Field |
|---|---|---|---|
| LOCOMO (n=300) | recall@10 | **0.497** | mem0 0.048, supermemory 0.149 |
| LOCOMO (n=300) | QA accuracy | 45.3% | supermemory 49.7%, mem0 27.3% |
| LongMemEval-S (n=50) | QA accuracy | **76%** | tied with dense RAG |
| ERPNext cross-tool (n=6) | key-fact coverage | **82.0%** | grep/read baseline 70.8% |
| Graph build | LLM credits | **0** | per-token for most systems |

Mọi hệ thống đều chạy trên cùng một harness với cùng mô hình và ngân sách, được chấm điểm bởi một giám khảo đã được kiểm chứng mù đối chiếu với một giám khảo thứ hai (90.6% agreement, Cohen's kappa 0.81). Bảng đầy đủ theo từng hệ thống, kết quả hiểu code, và các lệnh tái lập: **[BENCHMARKS.md](../../BENCHMARKS.md)**.

---

## Tài liệu

Hướng dẫn và tài liệu tham khảo đầy đủ nằm tại **[docs.graphify.com](https://docs.graphify.com)**:

- **[Quickstart](https://docs.graphify.com/quickstart)**: dựng đồ thị đầu tiên của bạn
- **[CLI reference](https://docs.graphify.com/reference/overview)**: mọi lệnh và cờ
- **[Ask better graph questions](https://docs.graphify.com/guides/querying)**: các mẫu truy vấn
- **[Configuration](https://docs.graphify.com/reference/configuration)**: biến môi trường và tinh chỉnh
- **[Supported inputs](https://docs.graphify.com/concepts/supported-inputs)**: ngôn ngữ và loại tệp
- **[Team workflows](https://docs.graphify.com/guides/team-workflows)** và **[PR review](https://docs.graphify.com/guides/pull-requests)**
- **[Troubleshooting](https://docs.graphify.com/troubleshooting)** và **[How it works](https://docs.graphify.com/concepts/architecture)**

---

## Điều kiện tiên quyết

| Yêu cầu | Tối thiểu | Kiểm tra | Cài đặt |
|---|---|---|---|
| Python | 3.10+ | `python --version` | [python.org](https://www.python.org/downloads/) |
| uv *(recommended)* | any | `uv --version` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| pipx *(alternative)* | any | `pipx --version` | `pip install pipx` |

**Cài đặt nhanh trên macOS (Homebrew):**
```bash
brew install python@3.12 uv
```

**Cài đặt nhanh trên Windows:**
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
> **Gói chính thức:** Gói PyPI là `graphifyy` (hai chữ y). Các gói `graphify*` khác trên PyPI không có liên kết. Lệnh CLI vẫn là `graphify`.

Kho nguồn chính thức là [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify).

Phần bắt đầu nhanh hai lệnh nằm ở đầu README này. Phần này đề cập các phương thức cài đặt, cài đặt theo phạm vi dự án, và mọi nền tảng được hỗ trợ.

**Các phương thức cài đặt** (chọn một):

```bash
uv tool install graphifyy   # recommended, isolated env (if 'graphify' isn't found after, run: uv tool update-shell)
pipx install graphifyy      # alternative
pip install graphifyy       # may need PATH setup, see Troubleshooting below
```

Sau đó chạy `graphify install` một lần. Nó phát hiện bạn chạy trợ lý nào và đăng ký kỹ năng, nên không cần thiết lập riêng cho từng trợ lý. Mở trợ lý AI của bạn và gõ `/graphify .`

Để cài kỹ năng trợ lý vào kho hiện tại thay vì hồ sơ người dùng của bạn, thêm `--project`:

```bash
graphify install --project
graphify install --project --platform codex
```

Cài đặt theo phạm vi dự án ghi vào bên dưới thư mục hiện tại, ví dụ `.claude/skills/graphify/SKILL.md` hoặc `.agents/skills/graphify/SKILL.md` (cùng một sidecar `references/` mà kỹ năng tải khi cần), và in một gợi ý `git add` cho các tệp có thể commit. Các lệnh theo từng nền tảng hỗ trợ cài đặt theo phạm vi dự án chấp nhận cùng cờ đó, ví dụ `graphify claude install --project` hoặc `graphify codex install --project`.

> [!TIP]
> Gặp `command not found`, một vấn đề `pip` trên Mac/Windows, việc đặt dấu nháy trong PowerShell, cách dùng `uvx`, các đặc tính PATH của git-hook, hay chế độ strict? Xem **[Installation](https://docs.graphify.com/installation)** và **[Troubleshooting](https://docs.graphify.com/troubleshooting)**.

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

Người dùng Codex cũng cần `multi_agent = true` dưới `[features]` trong `~/.codex/config.toml` để trích xuất song song. CodeBuddy dùng cùng cơ chế Agent tool và PreToolUse hook như Claude Code. Factory Droid dùng `Task` tool để điều phối sub-agent song song. OpenClaw và Aider dùng trích xuất tuần tự (hỗ trợ agent song song vẫn còn ở giai đoạn đầu trên các nền tảng đó). Trae dùng Agent tool để điều phối sub-agent song song và **không** hỗ trợ `PreToolUse` hook, nên AGENTS.md là cơ chế luôn bật.

`--platform agents` (bí danh `--platform skills`) nhắm tới các vị trí [Agent-Skills](https://github.com/anthropics/skills) chung, liên khung: `~/.agents/skills/` theo đặc tả ở mức toàn người dùng (được đọc bởi `npx skills` và các khung tuân thủ đặc tả) cho cài đặt toàn cục, và `./.agents/skills/` cho cài đặt dự án (`--project`). Lệnh `graphify install` trần vẫn là đơn nền tảng (Claude Code) theo thiết kế: dùng nền tảng có tên `agents` khi bạn muốn kỹ năng có thể được phát hiện bởi bất kỳ khung nào đọc `.agents/skills`.

Pi không có `PreToolUse` hook, nên `graphify pi guard install` đăng ký một tiện ích mở rộng Pi gốc (thông qua `pi install <package directory>` của chính Pi) chạy `graphify hook-guard` đã cài trước các lệnh `read`, `grep`, `find` và các lệnh `bash` kiểu tìm kiếm của Pi. Các quyết định đồ thị mới/cũ và việc từ chối đọc đã lập chỉ mục một lần mỗi phiên với `GRAPHIFY_HOOK_STRICT=1` đến từ cùng một chính sách, nên Pi khớp với hành vi hook của Claude Code; hướng dẫn đến dưới dạng một tin nhắn định hướng `<system-reminder source="graphify">`. Nó cần Pi 0.58.4 trở lên: các phiên bản trước để một tin nhắn định hướng bỏ qua phần còn lại của một lô gọi công cụ song song. Gói này đi kèm bên trong bản cài đặt Graphify, nên hãy cài Graphify một cách bền vững (`uv tool install graphifyy` hoặc `pipx install graphifyy`, không phải `uvx`), khởi động lại Pi sau khi cài hoặc nâng cấp, và gỡ bằng `graphify pi guard uninstall`. Chỉ các mục tiêu tệp cục bộ được kiểm tra; hook cần `graphify` nằm trên một mục `PATH` tuyệt đối bên ngoài dự án, bị giới hạn ở lệnh gọi hai giây, 256 KiB vào/64 KiB ra, và fail open. Cùng gói đó cũng tải trong [Oh My Pi](https://github.com/can1357/oh-my-pi): `omp plugin install "$(graphify pi guard path)"`. Đường dẫn được đăng ký chứa phiên bản Python và venv, nên hãy chạy lại `graphify pi guard install` sau khi thay đổi một trong hai, và gỡ mục cũ bằng `pi remove <old path>`.

> Codex dùng `$graphify` thay vì `/graphify`.

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

## Khiến trợ lý của bạn luôn dùng đồ thị

Chạy cái này một lần trong dự án của bạn sau khi dựng một đồ thị:

Chạy `graphify <platform> install` một lần trong dự án của bạn, ví dụ `graphify claude install` hoặc `graphify codex install` (hoặc `graphify install --platform <name>`).

Việc này ghi một tệp cấu hình nhỏ bảo trợ lý của bạn tham khảo đồ thị tri thức cho các câu hỏi về mã nguồn, ưu tiên các truy vấn giới hạn phạm vi như `graphify query "<question>"` hơn là đọc toàn bộ báo cáo hoặc grep các tệp thô.

- **Nền tảng kiểu Hook** (Claude Code, Gemini CLI): một hook kích hoạt tự động trước các lệnh gọi công cụ kiểu tìm kiếm (và, trên Claude Code, trước khi đọc từng tệp nguồn một qua các công cụ Read/Glob) và đẩy trợ lý của bạn về phía đường đi đồ thị.
- **Nền tảng kiểu tệp hướng dẫn** (Codex, OpenCode, Cursor, v.v.): các tệp hướng dẫn bền vững (`AGENTS.md`, `.cursor/rules/`, v.v.) cung cấp cùng hướng dẫn ưu tiên truy vấn.

`GRAPH_REPORT.md` vẫn có sẵn cho việc rà soát kiến trúc trên diện rộng.

Chính xác tệp nào mỗi nền tảng ghi ra (`CODEBUDDY.md` + `PreToolUse` hooks của CodeBuddy, `AGENTS.md` của Codex, plugin `.kilo` gốc của Kilo, quy tắc `alwaysApply` của Cursor, v.v.) được đề cập trong **[Always-on setup](https://docs.graphify.com/guides/always-on)**.

Để gỡ graphify khỏi mọi nền tảng cùng lúc: `graphify uninstall` (thêm `--purge` để cũng xóa `graphify-out/`). Hoặc dùng lệnh theo từng nền tảng (ví dụ `graphify claude uninstall`).

### Skill CLI hay hướng dẫn MCP?

Các hướng dẫn được cài bởi `graphify install` và các hướng dẫn đi kèm với một kết nối Graphify MCP mô tả những cách khác nhau để truy vấn một đồ thị:

| Setup | Guidance to use | Query access |
|---|---|---|
| CLI cục bộ và kỹ năng trợ lý đã cài | Các hướng dẫn nền tảng được `graphify install` ghi ra | Chạy `graphify query`, `graphify path`, và `graphify explain` trên đồ thị cục bộ (`graphify-out/` theo mặc định). |
| Máy chủ Graphify MCP đã kết nối | Các hướng dẫn của kết nối đó và các công cụ mà máy chủ đó liệt kê | Gọi các công cụ MCP được liệt kê trên đồ thị mà kết nối đó phục vụ. Tên và mô tả công cụ đến từ máy chủ. |

Cả hai đều khuyến khích các truy vấn đồ thị giới hạn phạm vi trước các tìm kiếm nguồn trên diện rộng. Hãy chọn các hướng dẫn khớp với các công cụ mà trợ lý của bạn thực sự có thể truy cập; không khối nào thiết lập một quy tắc ưu tiên phổ quát cho các tệp hướng dẫn của trợ lý của bạn. Nếu bạn dùng cả hai tích hợp, hãy xác định mỗi cái truy vấn đồ thị nào và chọn một đường truy vấn chính thay vì sao chép hai khối hướng dẫn vô điều kiện vào `AGENTS.md`.

`graphify install` cài đặt tích hợp trợ lý cục bộ; nó không thiết lập một kết nối MCP. Một client MCP không cần chạy các truy vấn CLI cục bộ để dùng máy chủ đã kết nối của nó. Một máy chủ được host cục bộ vẫn cần bản cài đặt Graphify và đồ thị của riêng nó, trong khi một kết nối được host có thể phục vụ một đồ thị không hiện diện trong thư mục làm việc của client. Nếu các công cụ mong đợi bị thiếu, hãy kiểm tra bản cài đặt CLI hoặc kết nối MCP liên quan thay vì coi các hướng dẫn của thiết lập kia là có thể thay thế cho nhau.

---

## Có gì trong báo cáo

`GRAPH_REPORT.md` tóm tắt các god nodes, cộng đồng, và các đường đi chính cho việc rà soát kiến trúc trên diện rộng. Cách đồ thị được dựng và nó chứa gì: **[How graphify works](https://docs.graphify.com/concepts/architecture)**.

---

## Nó xử lý những tệp nào: ~40 languages

graphify phân tích ~40 programming languages một cách cục bộ bằng tree-sitter AST, và ánh xạ tài liệu, PDF, hình ảnh, và âm thanh/video qua một lượt xử lý ngữ nghĩa tùy chọn. Danh sách đầy đủ: **[Supported inputs](https://docs.graphify.com/concepts/supported-inputs)**.

---

## Các lệnh thường dùng

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

Xem [tham khảo lệnh đầy đủ](#full-command-reference) bên dưới.

---

## Bỏ qua tệp

graphify tôn trọng `.gitignore` và hỗ trợ các mẫu `--exclude` cùng một `.graphifyignore` cấp dự án. Chi tiết: **[Configuration](https://docs.graphify.com/reference/configuration)**.


## Cấu hình dự án

Tạo một `.graphifyrc` ở gốc quét cho các thiết lập thuộc về dự án chứ không thuộc về một lần chạy. Mỗi dòng một `key=value`; các dòng bắt đầu bằng `#` là chú thích.

**Các phần mở rộng mơ hồ.** Một số phần mở rộng mang ý nghĩa ngôn ngữ khác nhau trong các dự án khác nhau: `.inc` là PHP trên pfSense, là Pascal trong một cây Delphi, là SQL hoặc assembly ở nơi khác; `.h` là C hoặc C++; `.m` là Objective-C hoặc MATLAB. graphify phải chọn một mặc định toàn cục, và khi nó chọn sai thì tệp không thất bại: nó được phân tích dưới dạng ngôn ngữ sai và tạo ra một nhúm nút ngẫu nhiên, nên đồ thị trông như có dữ liệu trong khi các ký hiệu thực lại bị thiếu. Hãy khai báo phần mở rộng đó có nghĩa gì trong repo của bạn:

```
# .graphifyrc
# A language name:
language.inc=php
# Or an extension graphify already knows:
language.tpl=.ts
# Baked into the git hooks (see Team setup):
viz_node_limit=0
```

Khai báo này chảy qua phân loại, chọn trình trích xuất, ngữ pháp và giải quyết, import, `graphify watch`, và bộ nhớ đệm AST (một tệp được phân tích lại dưới một ngôn ngữ khác sẽ không bao giờ tái dùng mục cũ), và cùng một `.graphifyrc` được đọc bởi `extract`, `update`, các hook, máy chủ MCP, và kỹ năng `/graphify`. Một lỗi gõ được báo một lần trên stderr và việc quét tiếp tục với các mặc định. Cách các khai báo tương tác với bộ nhớ đệm, dựng lại tăng dần, và giải quyết import: **[Configuration](https://docs.graphify.com/reference/configuration)**.

---

## Thiết lập nhóm

Commit hoặc chia sẻ đồ thị để cả nhóm của bạn truy vấn cùng một ngữ cảnh, và rà soát các pull request với ngữ cảnh đồ thị. Xem **[Share context with your team](https://docs.graphify.com/guides/team-workflows)** và **[Review pull requests](https://docs.graphify.com/guides/pull-requests)**.

---

## Dùng đồ thị trực tiếp

Ngoài trợ lý AI của bạn, hãy truy vấn `graph.json` trực tiếp từ CLI với `graphify query`, `graphify path`, và `graphify explain`. Một tên khớp với nhiều nút sẽ bị từ chối với các ứng viên được liệt kê thay vì đoán. Các script có thể đọc kết quả từ mã thoát: `0` một câu trả lời, `3` một tên mơ hồ, `4` không có nút khớp. Xem **[Ask better graph questions](https://docs.graphify.com/guides/querying)** và **[query reference](https://docs.graphify.com/reference/query)**.

---

## Biến môi trường

Các backend, API key, hành vi hook, và tinh chỉnh được điều khiển bởi các biến môi trường. Bảng đầy đủ: **[Configuration](https://docs.graphify.com/reference/configuration)**.

---

## Quyền riêng tư

- **Tệp code**: được xử lý cục bộ qua tree-sitter. Không gì rời khỏi máy của bạn. Một kho chỉ có code không cần API key: `graphify extract` chạy hoàn toàn ngoại tuyến. Trên một repo hỗn hợp, thêm `--code-only` để chỉ lập chỉ mục code và bỏ qua các tài liệu/PDF/hình ảnh mà lẽ ra sẽ cần một LLM.
- **Video / âm thanh**: được chép lời cục bộ với faster-whisper. Không gì rời khỏi máy của bạn.
- **Tài liệu, PDF, hình ảnh**: được gửi tới trợ lý AI của bạn để trích xuất ngữ nghĩa (qua kỹ năng `/graphify`, dùng bất kỳ mô hình nào phiên IDE của bạn đang chạy). `graphify extract` không giao diện cần `GEMINI_API_KEY` / `GOOGLE_API_KEY` (Gemini), `MOONSHOT_API_KEY` (Kimi), `ANTHROPIC_API_KEY` (Claude), `OPENAI_API_KEY` (OpenAI), `DEEPSEEK_API_KEY` (DeepSeek), một instance Ollama đang chạy (`OLLAMA_BASE_URL`), thông tin xác thực AWS qua chuỗi provider chuẩn (Bedrock - không cần API key, dùng IAM), hoặc tệp nhị phân CLI `claude` (Claude Code - không cần API key, dùng gói đăng ký Claude của bạn). Cờ `--dedup-llm` dùng cùng key.
- **Lưu trú dữ liệu**: `graphify extract` tự động phát hiện dùng provider nào dựa trên API key nào được đặt (ưu tiên: Gemini → Kimi → Claude → OpenAI → DeepSeek → Azure → Bedrock → Ollama). Với code có yêu cầu lưu trú dữ liệu, dùng `--backend ollama` (hoàn toàn cục bộ) hoặc truyền một cờ `--backend` rõ ràng. Kimi (`MOONSHOT_API_KEY`) định tuyến tới các máy chủ Moonshot AI ở Trung Quốc.
- **Không telemetry**, không theo dõi sử dụng, không phân tích.
- **Ghi log truy vấn**: mọi lệnh gọi `graphify query`, `graphify path`, `graphify explain`, và MCP `query_graph` được ghi vào `~/.cache/graphify-queries.log` ở định dạng JSON Lines (dấu thời gian, câu hỏi, kho, các nút trả về, thời lượng). Các phản hồi đồ thị con đầy đủ theo mặc định **không** được lưu. Đặt `GRAPHIFY_QUERY_LOG_DISABLE=1` để từ chối, hoặc `GRAPHIFY_QUERY_LOG=/dev/null` để làm im lặng mà không vô hiệu hóa đường code.

---

## Khắc phục sự cố

Các vấn đề cài đặt và trích xuất thường gặp cùng cách khắc phục: **[Troubleshooting](https://docs.graphify.com/troubleshooting)**.

---

## Tham khảo lệnh đầy đủ

Mọi lệnh và cờ, kèm ví dụ: **[CLI reference](https://docs.graphify.com/reference/overview)**.

---

## Tìm hiểu thêm

- [docs.graphify.com](https://docs.graphify.com): tài liệu đầy đủ: hướng dẫn, tham khảo lệnh, và tích hợp
- [How it works](../how-it-works.md): pipeline trích xuất, phát hiện cộng đồng, chấm điểm độ tin cậy, benchmark
- [ARCHITECTURE.md](../../ARCHITECTURE.md): phân tách module, cách thêm một ngôn ngữ
- [Optional integrations](../docker-mcp-sqlite.md): Docker MCP Toolkit + SQLite
- [The Memory Layer](https://safishamsi.gumroad.com/l/qetvlo): cuốn sách về các ý tưởng đằng sau graphify, kiến trúc từ đầu đến cuối

---

## Graphify Cloud

[**Graphify Cloud**](https://app.graphify.com/login) là lớp luôn bật được xây dựng trên nền graphify. Thay vì một đồ thị bạn dựng lại theo nhu cầu cho từng thư mục, nó giữ một đồ thị sống duy nhất xuyên suốt toàn bộ vòng đời phát triển phần mềm của bạn:

- **Ít hơn 80% token**: bộ nhớ luôn bật nghĩa là các agent của bạn ngừng đọc lại và giải thích lại mã nguồn trong mỗi phiên.
- **Monorepo và liên repo**: một đồ thị kết nối duy nhất xuyên qua mọi dịch vụ và kho, chứ không phải một đồ thị cho mỗi thư mục.
- **Kiểm chứng hình thức**: kiểm tra các bất biến về kiến trúc và phụ thuộc đối với đồ thị sống.
- **Rà soát code với góc nhìn bao quát toàn cảnh SDLC của bạn**: thấy một thay đổi lan tỏa khắp cả hệ thống như thế nào trước khi bạn merge.
- **Trình kết nối SDLC**: kéo vào Sentry, Jira và nhiều hơn nữa, để sự cố, ticket, và code sống trong một đồ thị.
- **Luôn bật**: cập nhật liên tục ở nền xuyên qua code, tài liệu, và các cuộc họp.

**[Bắt đầu dùng thử miễn phí 14 ngày tại app.graphify.com &rarr;](https://app.graphify.com/login)**

---

## Đóng góp

Hoan nghênh đóng góp. Xem **[CONTRIBUTING.md](../../CONTRIBUTING.md)** để biết thiết lập môi trường phát triển, các lệnh kiểm thử và CI-parity, quy trình git, và điều gì làm nên một đóng góp mạnh (các ví dụ thực tế và báo cáo lỗi trích xuất là hữu ích nhất). Kiến trúc và cách thêm một ngôn ngữ: [ARCHITECTURE.md](../../ARCHITECTURE.md).

Mới đến? Chào một tiếng trên [Discord](https://discord.gg/XDnKVpzdXB) hoặc trong [GitHub Discussions](https://github.com/Graphify-Labs/graphify/discussions).

---

## Người đóng góp

<a href="https://github.com/Graphify-Labs/graphify/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=Graphify-Labs/graphify" alt="graphify contributors" />
</a>

Made with [contrib.rocks](https://contrib.rocks).

---

## Bản dịch

README có sẵn trong 32 ngôn ngữ. Dùng trình chuyển ngôn ngữ ở đầu tệp này để đọc bằng ngôn ngữ của bạn, hoặc duyệt [`docs/translations/`](./). Để cải thiện một bản dịch hoặc thêm một bản mới, hãy mở một pull request đối với tệp tương ứng ở đó.

---

## Xây dựng trên graphify

Đang xây dựng thứ gì đó trong hệ sinh thái graphify? Điều đó được khuyến khích. Nếu dự án của bạn dùng "graphify" trong tên (ví dụ `graphify-dashboard` hoặc `graphify-action`), vui lòng thêm một ghi chú ngắn vào README của bạn làm rõ rằng nó do cộng đồng xây dựng và không liên kết với hay được chứng thực bởi Graphify Labs. "graphify" và logo graphify là các nhãn hiệu của Graphify Labs; vui lòng đừng dùng chúng theo cách ngụ ý tư cách chính thức.

---

## Cộng đồng và liên kết

<p align="center">
  <a href="https://graphify.com"><img src="https://img.shields.io/badge/Website-graphify.com-4c1?style=flat&logo=googlechrome&logoColor=white" alt="Website"/></a>
  <a href="https://discord.gg/XDnKVpzdXB"><img src="https://img.shields.io/badge/Discord-Join-5865F2?style=flat&logo=discord&logoColor=white" alt="Discord"/></a>
  <a href="https://x.com/graphify"><img src="https://img.shields.io/badge/X-graphify-000000?logo=x&logoColor=white" alt="X"/></a>
  <a href="https://www.youtube.com/@graphifylabs"><img src="https://img.shields.io/badge/YouTube-Graphify%20Labs-FF0000?style=flat&logo=youtube&logoColor=white" alt="YouTube"/></a>
  <a href="https://github.com/sponsors/safishamsi"><img src="https://img.shields.io/badge/sponsor-safishamsi-ea4aaa?logo=github-sponsors" alt="Sponsor"/></a>
  <a href="https://safishamsi.gumroad.com/l/qetvlo"><img src="https://img.shields.io/badge/Book-The%20Memory%20Layer-2ea44f?style=flat&logo=gitbook&logoColor=white" alt="The Memory Layer"/></a>
</p>
