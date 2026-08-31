<p align="center">
  <a href="https://graphifylabs.ai"><img src="https://raw.githubusercontent.com/safishamsi/graphify/v4/docs/logo-text.svg" width="260" height="64" alt="Graphify"/></a>
</p>

<p align="center">
  🇺🇸 <a href="../../README.md">English</a> | 🇨🇳 <a href="README.zh-CN.md">简体中文</a> | 🇯🇵 <a href="README.ja-JP.md">日本語</a> | 🇰🇷 <a href="README.ko-KR.md">한국어</a> | 🇩🇪 <a href="README.de-DE.md">Deutsch</a> | 🇫🇷 <a href="README.fr-FR.md">Français</a> | 🇪🇸 <a href="README.es-ES.md">Español</a> | 🇮🇳 <a href="README.hi-IN.md">हिन्दी</a> | 🇧🇷 <a href="README.pt-BR.md">Português</a> | 🇷🇺 <a href="README.ru-RU.md">Русский</a> | 🇸🇦 <a href="README.ar-SA.md">العربية</a> | 🇮🇷 <a href="README.fa-IR.md">فارسی</a> | 🇮🇹 <a href="README.it-IT.md">Italiano</a> | 🇵🇱 <a href="README.pl-PL.md">Polski</a> | 🇳🇱 <a href="README.nl-NL.md">Nederlands</a> | 🇹🇷 <a href="README.tr-TR.md">Türkçe</a> | 🇺🇦 <a href="README.uk-UA.md">Українська</a> | 🇻🇳 <a href="README.vi-VN.md">Tiếng Việt</a> | 🇮🇩 <a href="README.id-ID.md">Bahasa Indonesia</a> | 🇸🇪 <a href="README.sv-SE.md">Svenska</a> | 🇬🇷 <a href="README.el-GR.md">Ελληνικά</a> | 🇷🇴 <a href="README.ro-RO.md">Română</a> | 🇨🇿 <a href="README.cs-CZ.md">Čeština</a> | 🇫🇮 <a href="README.fi-FI.md">Suomi</a> | 🇩🇰 <a href="README.da-DK.md">Dansk</a> | 🇳🇴 <a href="README.no-NO.md">Norsk</a> | 🇭🇺 <a href="README.hu-HU.md">Magyar</a> | 🇹🇭 <a href="README.th-TH.md">ภาษาไทย</a> | 🇺🇿 <a href="README.uz-UZ.md">Oʻzbekcha</a> | 🇹🇼 <a href="README.zh-TW.md">繁體中文</a> | 🇵🇭 <a href="README.fil-PH.md">Filipino</a>
</p>

<p align="center">
  <a href="https://www.ycombinator.com/companies/graphify"><img src="https://img.shields.io/badge/Y%20Combinator-S26-F0652F?style=flat&logo=ycombinator&logoColor=white" alt="YC S26"/></a>
  <a href="https://discord.gg/598Ad9zQZ"><img src="https://img.shields.io/badge/Discord-Join-5865F2?style=flat&logo=discord&logoColor=white" alt="Discord"/></a>
  <a href="https://safishamsi.gumroad.com/l/qetvlo"><img src="https://img.shields.io/badge/Book-The%20Memory%20Layer-2ea44f?style=flat&logo=gitbook&logoColor=white" alt="The Memory Layer"/></a>
  <a href="https://github.com/safishamsi/graphify/actions/workflows/ci.yml"><img src="https://github.com/safishamsi/graphify/actions/workflows/ci.yml/badge.svg?branch=v8" alt="CI"/></a>
  <a href="https://pypi.org/project/graphifyy/"><img src="https://img.shields.io/pypi/v/graphifyy" alt="PyPI"/></a>
  <a href="https://pepy.tech/project/graphifyy"><img src="https://img.shields.io/pepy/dt/graphifyy?color=blue&label=downloads" alt="Downloads"/></a>
  <a href="https://github.com/sponsors/safishamsi"><img src="https://img.shields.io/badge/sponsor-safishamsi-ea4aaa?logo=github-sponsors" alt="Sponsor"/></a>
  <a href="https://www.linkedin.com/in/safi-shamsi"><img src="https://img.shields.io/badge/LinkedIn-Safi%20Shamsi-0077B5?logo=linkedin" alt="LinkedIn"/></a>
  <a href="https://x.com/graphifyy"><img src="https://img.shields.io/badge/X-graphifyy-000000?logo=x&logoColor=white" alt="X"/></a>
</p>

<p align="center">
  <a href="https://star-history.com/#safishamsi/graphify&Date">
    <img src="https://api.star-history.com/svg?repos=safishamsi/graphify&type=Date" alt="Star History Chart" width="370"/>
  </a>
</p>

在你的 AI 程式碼助手中輸入 `/graphify`，它會把整個專案 —— 程式碼、文件、PDF、圖片、影片 —— 映射成一張知識圖譜，讓你直接查詢，而不必再逐一 grep 檔案。

可在 Claude Code、Codex、OpenCode、Kilo Code、Cursor、Gemini CLI、GitHub Copilot CLI、VS Code Copilot Chat、Aider、Amp、OpenClaw、Factory Droid、Trae、Hermes、Kimi Code、Kiro、Pi、Devin CLI 與 Google Antigravity 中使用。

```
/graphify .
```

就這樣。你會得到三個檔案：

```
graphify-out/
├── graph.html       在任何瀏覽器中開啟 —— 點擊節點、篩選、搜尋
├── GRAPH_REPORT.md  重點摘要：關鍵概念、令人驚訝的連結、建議問題
└── graph.json       完整圖譜 —— 隨時查詢，不必重新讀取你的檔案
```

如需一份附有 Mermaid 呼叫流程圖、易讀的架構頁面，執行：

```bash
graphify export callflow-html
```

---

## 先決條件

| 需求 | 最低版本 | 檢查 | 安裝 |
|---|---|---|---|
| Python | 3.10+ | `python --version` | [python.org](https://www.python.org/downloads/) |
| uv *(建議)* | 任意 | `uv --version` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| pipx *(替代方案)* | 任意 | `pipx --version` | `pip install pipx` |

**macOS 快速安裝（Homebrew）：**
```bash
brew install python@3.12 uv
```

**Windows 快速安裝：**
```powershell
winget install astral-sh.uv
```

**Ubuntu/Debian：**
```bash
sudo apt install python3.12 python3-pip pipx
# 或安裝 uv：
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## 安裝

> **官方套件：** PyPI 套件名稱為 `graphifyy`（兩個 y）。PyPI 上其他 `graphify*` 套件與本專案無關。CLI 指令仍然是 `graphify`。

**步驟 1 — 安裝套件：**

```bash
# 建議（隔離環境；若安裝後找不到 'graphify'，執行：uv tool update-shell）：
uv tool install graphifyy

# 替代方案：
pipx install graphifyy
pip install graphifyy  # 可能需要設定 PATH —— 見下方說明
```

**步驟 2 — 向你的 AI 助手註冊技能：**

```bash
graphify install
```

就這樣。開啟你的 AI 助手並輸入 `/graphify .`

若要將助手技能安裝到目前的儲存庫，而非你的使用者設定檔，加上 `--project`：

```bash
graphify install --project
graphify install --project --platform codex
```

專案範圍（project-scoped）的安裝會寫入目前目錄底下，例如
`.claude/skills/graphify/SKILL.md` 或 `.agents/skills/graphify/SKILL.md`（外加一個技能會按需載入的
`references/` 附屬目錄），並會
印出可提交檔案的 `git add` 提示。
支援專案範圍安裝的各平台指令也接受相同旗標，
例如 `graphify claude install --project` 或 `graphify codex install --project`。

> **PowerShell 注意：** 使用 `graphify .` 而非 `/graphify .` —— 在 PowerShell 中開頭的斜線是路徑分隔符號。

> **`graphify: command not found`？** `uv tool install` / `pipx install` 會把 `graphify` 指令放在它們的工具 bin 目錄（`~/.local/bin`）。若安裝後 shell 立刻找不到它 —— 在全新的 macOS + zsh 設定上很常見 —— 表示該目錄尚未加入你的 `PATH`：執行 `uv tool update-shell`（或 `pipx ensurepath`），然後開啟新的終端機。使用純 `pip` 時，請將 `~/.local/bin`（Linux）或 `~/Library/Python/3.x/bin`（Mac）加入你的 PATH，或執行 `python -m graphify`。

> **想用 `uvx` / `uv tool run` 而不安裝？** 要指定套件名稱，而非指令：`uvx --from graphifyy graphify install`。純 `uvx graphify …` 會失敗（`No solution found … no versions of graphify`），因為 `uv tool run` 會把第一個字當成*套件*，而套件是 `graphifyy` —— `graphify` 指令包在它裡面。

> **在 Mac/Windows 上盡量避免 `pip install`。** 技能會在執行期從 `graphify-out/.graphify_python` 解析 Python；若該路徑指向的環境與 `pip` 安裝套件的環境不同，你會得到 `ModuleNotFoundError: No module named 'graphify'`。`uv tool install` 與 `pipx install` 會把套件隔離在各自的環境中，完全避免這個問題。

> **Git hooks 與 uv tool / pipx：** `graphify hook install` 會在安裝時把目前的直譯器路徑直接嵌入 hook 腳本，因此即使在 `~/.local/bin` 不在 PATH 上的 GUI git 客戶端與 CI runner 中，post-commit hook 也能正確觸發。若你重新安裝或升級 graphify，請重新執行 `graphify hook install` 以更新嵌入的路徑。

### 選擇你的平台

| 平台 | 安裝指令 |
|----------|----------------|
| Claude Code (Linux/Mac) | `graphify install` |
| Claude Code (Windows) | `graphify install`（自動偵測）或 `graphify install --platform windows` |
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
| Agent Skills（跨框架） | `graphify install --platform agents`（別名 `--platform skills`） |
| Kiro IDE/CLI | `graphify kiro install` |
| Pi coding agent | `graphify install --platform pi` |
| Cursor | `graphify cursor install` |
| Devin CLI | `graphify devin install` |
| Google Antigravity | `graphify antigravity install` |

Codex 使用者還需要在 `~/.codex/config.toml` 的 `[features]` 底下設定 `multi_agent = true` 以進行並行提取。CodeBuddy 使用與 Claude Code 相同的 Agent 工具與 PreToolUse hook 機制。Factory Droid 使用 `Task` 工具進行並行子代理派發。OpenClaw 與 Aider 使用循序提取（這些平台的並行 agent 支援仍在早期階段）。Trae 使用 Agent 工具進行並行子代理派發，且**不**支援 PreToolUse hook —— AGENTS.md 是其常駐機制。

`--platform agents`（別名 `--platform skills`）會以通用的跨框架 [Agent-Skills](https://github.com/anthropics/skills) 位置為目標：規範定義的使用者全域 `~/.agents/skills/`（由 `npx skills` 與符合規範的框架讀取）用於全域安裝，而 `./.agents/skills/` 用於專案（`--project`）安裝。純 `graphify install` 在設計上維持單一平台（Claude Code）—— 當你希望技能能被任何讀取 `.agents/skills` 的框架探索到時，請使用具名的 `agents` 平台。

> Codex 使用 `$graphify` 而非 `/graphify`。

### 選用附加元件

只安裝你需要的：

| 附加元件 | 增加的功能 | 安裝 |
|---|---|---|
| `pdf` | PDF 提取 | `uv tool install "graphifyy[pdf]"` |
| `office` | `.docx` 與 `.xlsx` 支援 | `uv tool install "graphifyy[office]"` |
| `google` | Google Sheets 渲染 | `uv tool install "graphifyy[google]"` |
| `video` | 影片／音訊轉錄（faster-whisper + yt-dlp） | `uv tool install "graphifyy[video]"` |
| `mcp` | MCP stdio 伺服器 | `uv tool install "graphifyy[mcp]"` |
| `neo4j` | Neo4j 推送支援 | `uv tool install "graphifyy[neo4j]"` |
| `falkordb` | FalkorDB 推送支援 | `uv tool install "graphifyy[falkordb]"` |
| `svg` | SVG 圖譜匯出 | `uv tool install "graphifyy[svg]"` |
| `leiden` | Leiden 社群偵測（僅限 Python < 3.13） | `uv tool install "graphifyy[leiden]"` |
| `ollama` | Ollama 本地推論 | `uv tool install "graphifyy[ollama]"` |
| `openai` | OpenAI／OpenAI 相容 API | `uv tool install "graphifyy[openai]"` |
| `gemini` | Google Gemini API | `uv tool install "graphifyy[gemini]"` |
| `anthropic` | Anthropic Claude API（`--backend claude`，使用 `ANTHROPIC_API_KEY`） | `uv tool install "graphifyy[anthropic]"` |
| `bedrock` | AWS Bedrock（使用 IAM，免 API key） | `uv tool install "graphifyy[bedrock]"` |
| `azure` | Azure OpenAI Service（`--backend azure`，使用 `AZURE_OPENAI_API_KEY` + `AZURE_OPENAI_ENDPOINT`） | `uv tool install "graphifyy[openai]"` |
| `sql` | SQL schema 提取 | `uv tool install "graphifyy[sql]"` |
| `postgres` | 即時 PostgreSQL 內省（`--postgres DSN`） | `uv tool install "graphifyy[postgres]"` |
| `dm` | BYOND DreamMaker `.dm`/`.dme` AST 提取（若沒有符合你平台的 wheel，可能需要 C 編譯器 + `python3-dev`） | `uv tool install "graphifyy[dm]"` |
| `terraform` | Terraform / HCL `.tf`/`.tfvars`/`.hcl` AST 提取 | `uv tool install "graphifyy[terraform]"` |
| `chinese` | 中文查詢分詞（jieba） | `uv tool install "graphifyy[chinese]"` |
| `all` | 以上全部 | `uv tool install "graphifyy[all]"` |

---

## 讓你的助手永遠使用圖譜

建立圖譜後，在你的專案中執行一次：

| 平台 | 指令 |
|----------|---------|
| Claude Code | `graphify claude install` |
| CodeBuddy | `graphify codebuddy install` |
| Codex | `graphify codex install` |
| OpenCode | `graphify opencode install` |
| Kilo Code | `graphify kilo install` |
| GitHub Copilot CLI | `graphify copilot install` |
| VS Code Copilot Chat | `graphify vscode install` |
| Aider | `graphify aider install` |
| OpenClaw | `graphify claw install` |
| Factory Droid | `graphify droid install` |
| Trae | `graphify trae install` |
| Trae CN | `graphify trae-cn install` |
| Cursor | `graphify cursor install` |
| Gemini CLI | `graphify gemini install` |
| Hermes | `graphify hermes install` |
| Kimi Code | `graphify install --platform kimi` |
| Amp | `graphify amp install` |
| Agent Skills（跨框架） | `graphify agents install`（別名 `graphify skills install`） |
| Kiro IDE/CLI | `graphify kiro install` |
| Pi coding agent | `graphify pi install` |
| Devin CLI | `graphify devin install` |
| Google Antigravity | `graphify antigravity install` |

這會寫入一個小型設定檔，告訴你的助手在回答程式碼庫問題時要查閱知識圖譜 —— 優先使用範圍明確的查詢，如 `graphify query "<問題>"`，而非閱讀完整報告或 grep 原始檔案。在支援帶 payload 之 hook 的平台（Claude Code、Gemini CLI）上，一個 hook 會在搜尋類工具呼叫之前自動觸發（在 Claude Code 上，也會在透過 Read/Glob 工具逐一讀取原始檔案之前觸發），並引導你的助手走向圖譜路徑。在其他平台（Codex、OpenCode、Cursor 等）上，常駐的指令檔（`AGENTS.md`、`.cursor/rules/` 等）提供同樣的查詢優先（query-first）引導。`GRAPH_REPORT.md` 仍可用於廣泛的架構檢視。

**CodeBuddy** 做的兩件事和 Claude Code 相同：寫入一段 `CODEBUDDY.md` 章節，告訴 CodeBuddy 在回答架構問題前先讀 `graphify-out/GRAPH_REPORT.md`，並安裝 **PreToolUse hooks**（`.codebuddy/settings.json`），在 Bash 搜尋指令與檔案讀取之前觸發，引導改用 `graphify query`。

**Codex** 會寫入 `AGENTS.md`，並在 `.codex/hooks.json` 中安裝一個 **PreToolUse hook**，在每次 Bash 工具呼叫之前觸發 —— 與 Claude Code 相同的常駐機制。

若要一次從所有平台移除 graphify：`graphify uninstall`（加上 `--purge` 也會刪除 `graphify-out/`）。或使用各平台對應指令（例如 `graphify claude uninstall`）。

---

**Kilo Code** 會把 Graphify 技能安裝到 `~/.config/kilo/skills/graphify/SKILL.md`，並把原生的 `/graphify` 指令安裝到 `~/.config/kilo/command/graphify.md`。`graphify kilo install` 也會寫入 `AGENTS.md`，外加一個原生的 **`tool.execute.before` 外掛**（`.kilo/plugins/graphify.js` + `.kilo/kilo.json` 或 `.kilo/kilo.jsonc` 註冊），讓 Kilo 透過原生 `.kilo` 設定取得同樣的常駐圖譜提醒行為。

**Cursor** 會寫入 `.cursor/rules/graphify.mdc` 並設定 `alwaysApply: true` —— Cursor 會自動將其納入每次對話，不需要 hook。

## 報告裡有什麼

- **God nodes** —— 你專案中連結最多的概念。一切都流經這些節點。
- **令人驚訝的連結** —— 位於不同檔案或模組中的事物之間的連結。依其出乎意料的程度排名。
- **「為什麼」** —— 行內註解（`# NOTE:`、`# WHY:`、`# HACK:`）、docstring，以及文件中的設計理由，都會被提取為獨立節點，並連結到它們所解釋的程式碼。
- **建議問題** —— 4 到 5 個圖譜特別適合回答的問題。
- **置信度標記** —— 每條推斷出的關係都會被標記為 `EXTRACTED`、`INFERRED` 或 `AMBIGUOUS`。你永遠知道哪些是找到的、哪些是猜測的。

---

## 它能處理哪些檔案

| 類型 | 副檔名 |
|------|-----------|
| 程式碼（36 種 tree-sitter 文法） | `.py .ts .js .jsx .tsx .mjs .go .rs .java .c .cpp .h .hpp .cu .cuh .metal .rb .cs .kt .scala .php .swift .lua .luau .zig .ps1 .psm1 .ex .exs .m .mm .jl .vue .svelte .astro .groovy .gradle .dart .v .sv .svh .sql .f .f90 .f95 .f03 .f08 .pas .pp .dpr .dpk .lpr .inc .dfm .lfm .lpk .sh .bash .json .dm .dme .dmi .dmm .dmf .sln .slnx .csproj .fsproj .vbproj .xaml .razor .cshtml`（`.dm`/`.dme` 需要 `uv tool install graphifyy[dm]`；CUDA `.cu`/`.cuh` 與 Metal `.metal` 重用 C++ 文法） |
| Salesforce Apex | `.cls .trigger`（以正規表示式為基礎；類別、介面、列舉、方法、trigger、SOQL/DML 邊） |
| Terraform / HCL | `.tf .tfvars .hcl`（需要 `uv tool install graphifyy[terraform]`） |
| MCP 設定 | `.mcp.json` `mcp.json` `mcp_servers.json` `claude_desktop_config.json` —— 提取伺服器節點、套件參照、環境變數需求 |
| 套件 manifest | `apm.yml` `pyproject.toml` `go.mod` `pom.xml` —— 每個套件（依名稱）一個正規的套件節點，外加 `depends_on` 邊，因此一個被許多 manifest 參照的套件會是單一樞紐 |
| 文件 | `.md .mdx .qmd .html .txt .rst .yaml .yml`（markdown 的 `[text](./other.md)` 連結與 `[[wikilinks]]` 會成為文件之間的 `references` 邊） |
| Office | `.docx .xlsx`（需要 `uv tool install graphifyy[office]`） |
| Google Workspace | `.gdoc .gsheet .gslides`（選用；需要 `gws` 驗證與 `--google-workspace`；Sheets 需要 `uv tool install graphifyy[google]`） |
| PDF | `.pdf` |
| 圖片 | `.png .jpg .webp .gif` |
| 影片／音訊 | `.mp4 .mov .mp3 .wav` 等（需要 `uv tool install graphifyy[video]`） |
| YouTube / URL | 任何影片 URL（需要 `uv tool install graphifyy[video]`） |

程式碼會在本地提取，不需任何 API 呼叫（透過 tree-sitter 的 AST）。其餘所有內容都會經過你 AI 助手的模型 API。

桌面版 Google Drive 的 `.gdoc`、`.gsheet` 與 `.gslides` 檔案是捷徑
指標，並非文件內容本身。若要在無頭（headless）提取中納入原生的 Google Docs、Sheets 與 Slides，
請安裝並驗證
[`gws` CLI](https://github.com/googleworkspace/cli)，然後執行：

```bash
uv tool install "graphifyy[google]"  # Google Sheets 表格渲染所需
gws auth login -s drive
graphify extract ./docs --google-workspace
```

你也可以設定 `GRAPHIFY_GOOGLE_WORKSPACE=1`。Graphify 會把捷徑匯出成
`graphify-out/converted/` 底下的 Markdown 附屬檔，然後提取那些檔案。

---

## 常用指令

```bash
/graphify .                        # 為目前資料夾建立圖譜
/graphify ./docs --update          # 只重新提取變更過的檔案
/graphify . --cluster-only         # 重新執行聚類，不重新提取
/graphify . --cluster-only --resolution 1.5      # 更細緻的社群
/graphify . --cluster-only --exclude-hubs 99     # 從 god-node 排名中抑制工具型超級樞紐
/graphify . --no-viz               # 略過 HTML，只產生 report + JSON
/graphify . --wiki                 # 從圖譜建立 markdown wiki
graphify export callflow-html      # Mermaid 架構／呼叫流程 HTML（若安裝 hook，每次 git commit 都會自動重新產生）

/graphify query "什麼連結了 auth 與 database？"
/graphify path "UserService" "DatabasePool"
/graphify explain "RateLimiter"

/graphify add https://arxiv.org/abs/1706.03762   # 抓取一篇論文並加入
/graphify add <youtube-url>                       # 轉錄並加入一段影片

graphify hook install              # git commit 時自動重建
graphify merge-graphs a.json b.json              # 合併兩張圖譜

graphify prs                       # PR 儀表板：CI 狀態、審查狀態、worktree 對應
graphify prs 42                    # 深入分析 PR #42 並附圖譜影響
graphify prs --triage              # AI 為你的審查佇列排名（使用設定的後端）
graphify prs --conflicts           # 共用圖譜社群的 PR —— 合併順序風險
```

詳見下方[完整指令參考](#完整指令參考)。

---

## 忽略檔案

在你的專案根目錄建立 `.graphifyignore` —— 語法與 `.gitignore` 相同，包含 `!` 反向忽略。

**`.gitignore` 會自動被尊重。** graphify 會讀取每個目錄中的 `.gitignore`。若同時存在 `.graphifyignore`，兩者會被**合併** —— `.graphifyignore` 的模式會最後評估，因此在衝突時勝出（包含 `!` 反向忽略）。新增 `.graphifyignore` 只會排除更多檔案；它絕不會重新納入你的 `.gitignore` 已經排除的檔案。子目錄範圍的運作方式與 git 相同 —— 一個忽略檔只會影響它自己的子樹。

```
# .graphifyignore
node_modules/
dist/
*.generated.py

# 只索引 src/，忽略其餘所有內容
*
!src/
!src/**
```

---

## 團隊設定

`graphify-out/` 是設計來提交（commit）到 git 的，這樣團隊中的每個人一開始就有一張地圖。

**建議加入的 `.gitignore`：**
```
graphify-out/cost.json        # 僅限本地
# graphify-out/cache/         # 選用：為速度提交，或為了讓 repo 精簡而略過
```

> `manifest.json` 現在是可攜的 —— 鍵以相對路徑儲存，並在載入時重新錨定，因此提交它是安全的，且能避免首次 checkout 時的完整重建。

**工作流程：**
1. 一個人執行 `/graphify .` 並提交 `graphify-out/`。
2. 其他人 pull —— 他們的助手會立刻讀取圖譜。
3. 執行 `graphify hook install`，在每次 commit 後自動重建（僅 AST，無 API 成本）。這也會設定一個 git merge driver，因此 `graph.json` 絕不會留下衝突標記 —— 兩位開發者並行 commit 時，他們的圖譜會自動聯集合併。
4. 當文件或論文變更時，執行 `/graphify --update` 來刷新那些節點。

---

## 直接使用圖譜

```bash
# 從終端機查詢圖譜
graphify query "show the auth flow"
graphify query "what connects DigestAuth to Response?" --graph graphify-out/graph.json

# 將圖譜作為 MCP 伺服器公開（供重複的工具呼叫存取）
python -m graphify.serve graphify-out/graph.json
python -m graphify.serve --graph graphify-out/graph.json  # 也接受 --graph 旗標

# 向 Kimi Code 註冊：
kimi mcp add --transport stdio graphify -- python -m graphify.serve graphify-out/graph.json

# 或透過 HTTP 提供服務，讓整個團隊指向同一個 URL（不需在本地執行 graphify）：
python -m graphify.serve graphify-out/graph.json --transport http --port 8080
python -m graphify.serve graphify-out/graph.json --transport http --host 0.0.0.0 --api-key "$SECRET"
```

MCP 伺服器讓你的助手取得結構化存取：`query_graph`、`get_node`、`get_neighbors`、`shortest_path`、`list_prs`、`get_pr_impact`、`triage_prs`。

### 共用 HTTP 伺服器

`--transport stdio`（預設）會為每位開發者各自啟動一個本地伺服器。`--transport http` 會透過 MCP Streamable HTTP 傳輸提供相同的工具，因此單一共用程序就能為整個團隊提供圖譜服務 —— 客戶端把 IDE 的 MCP 設定指向 `http://<host>:8080/mcp`，而不必在本地執行 graphify。

| 旗標 | 預設值 | 用途 |
|---|---|---|
| `--transport {stdio,http}` | `stdio` | 提供服務的傳輸方式 |
| `--host` | `127.0.0.1` | HTTP 綁定主機（使用 `0.0.0.0` 以暴露到 localhost 之外） |
| `--port` | `8080` | HTTP 綁定埠 |
| `--api-key` | env `GRAPHIFY_API_KEY` | 要求 `Authorization: Bearer <key>`（或 `X-API-Key`） |
| `--path` | `/mcp` | HTTP 掛載路徑 |
| `--json-response` | 關閉 | 回傳純 JSON 而非 SSE 串流 |
| `--stateless` | 關閉 | 無每階段（per-session）狀態（用於負載平衡／CI 部署） |
| `--session-timeout` | `3600` | 在 N 秒後回收閒置的有狀態階段（`0` 表示停用） |

預設的 `127.0.0.1` 綁定僅限 loopback。在共用主機上暴露時，請同時設定 `--host 0.0.0.0` **與** `--api-key`。在容器中執行：

```bash
docker build -t graphify .
docker run -p 8080:8080 -v "$(pwd)/graphify-out:/data" graphify \
  /data/graph.json --transport http --host 0.0.0.0 --api-key "$SECRET"
```

> **WSL / Linux 注意：** Ubuntu 提供的是 `python3`，而非 `python`。使用 venv 以避免衝突：
> ```bash
> python3 -m venv .venv && .venv/bin/pip install "graphifyy[mcp]"
> ```

---

## 環境變數

這些只在 **無頭／CI 提取**（`graphify extract`）時才需要。當你透過 IDE 內的 `/graphify` 技能執行時，模型 API 由你的 IDE 階段提供 —— 不需要額外的金鑰。

| 變數 | 用於 | 何時需要 |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude（Anthropic）後端 | `--backend claude` |
| `ANTHROPIC_BASE_URL` | Anthropic 相容端點 URL（LiteLLM proxy、閘道…） | `--backend claude`（預設：`https://api.anthropic.com`） |
| `ANTHROPIC_MODEL` | Claude 後端的模型名稱 —— 對自訂端點，使用你伺服器公開的模型名稱／別名 | `--backend claude`（預設：`claude-sonnet-4-6`） |
| `GEMINI_API_KEY` 或 `GOOGLE_API_KEY` | Google Gemini 後端 | `--backend gemini` |
| `OPENAI_API_KEY` | OpenAI 或 OpenAI 相容 API | `--backend openai`（本地伺服器接受任何非空值） |
| `OPENAI_BASE_URL` | OpenAI 相容伺服器 URL（llama.cpp、vLLM、LM Studio…） | `--backend openai`（預設：`https://api.openai.com/v1`） |
| `OPENAI_MODEL` | OpenAI 後端的模型名稱 —— 對自架伺服器，使用你伺服器公開的模型名稱／別名（查看其 `/v1/models` 端點），例如 llama.cpp 的 `LFM2.5-8B-A1B-UD-Q4_K_XL` | `--backend openai`（預設：`gpt-4.1-mini`） |
| `DEEPSEEK_API_KEY` | DeepSeek 後端 | `--backend deepseek` |
| `MOONSHOT_API_KEY` | Kimi Code 後端 | `--backend kimi` |
| `OLLAMA_BASE_URL` | Ollama 本地推論 URL | `--backend ollama`(預設：`http://localhost:11434`) |
| `OLLAMA_MODEL` | Ollama 模型名稱 | `--backend ollama`（預設：自動偵測） |
| `GRAPHIFY_OLLAMA_NUM_CTX` | 覆寫 Ollama KV-cache 視窗大小 | 選用 —— 預設自動調整 |
| `GRAPHIFY_OLLAMA_KEEP_ALIVE` | 保持 Ollama 模型載入的分鐘數 | 選用 —— 設為 `0` 可在每個 chunk 後卸載 |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI Service 後端 | `--backend azure` |
| `AZURE_OPENAI_ENDPOINT` | Azure 資源端點 URL | `--backend azure`（需與 API key 一起提供） |
| `AZURE_OPENAI_API_VERSION` | Azure API 版本覆寫 | 選用 —— 預設 `2024-12-01-preview` |
| `AZURE_OPENAI_DEPLOYMENT` 或 `GRAPHIFY_AZURE_MODEL` | Azure 部署名稱 | 選用 —— 預設 `gpt-4o` |
| `AWS_*` / `~/.aws/credentials` | AWS Bedrock —— 標準憑證鏈 | `--backend bedrock`（免 API key，使用 IAM） |
| `GRAPHIFY_MAX_WORKERS` | AST 平行處理執行緒數 | 選用 —— 也可用 `--max-workers` 旗標 |
| `GRAPHIFY_MAX_OUTPUT_TOKENS` | 為密集語料提高輸出上限 | 選用 —— 例如大型檔案用 `32768` |
| `GRAPHIFY_API_TIMEOUT` | HTTP、claude-cli 與 Anthropic SDK 後端的每次呼叫逾時秒數（預設：600） | 選用 —— 也可用 `--api-timeout` 旗標 |
| `GRAPHIFY_MAX_RETRIES` | 在放棄前重試被限流（429）請求的次數（預設：6；遵守 `Retry-After`） | 選用 —— 對嚴格的 per-org 限制可調高（例如 kimi）；`0` 表示停用 |
| `GRAPHIFY_FORCE` | 即使節點較少也強制重建圖譜 | 選用 —— 也可用 `--force` 旗標 |
| `GRAPHIFY_GOOGLE_WORKSPACE` | 自動啟用 Google Workspace 匯出 | 選用 —— 設為 `1` |
| `GRAPHIFY_TRIAGE_BACKEND` | `graphify prs --triage` 的後端 | 選用 —— 由可用金鑰自動偵測 |
| `GRAPHIFY_TRIAGE_MODEL` | triage 的模型覆寫 | 選用 —— 例如 `claude-opus-4-7` |
| `GRAPHIFY_QUERY_LOG` | 覆寫查詢日誌路徑（預設：`~/.cache/graphify-queries.log`） | 選用 —— 設為空值或 `/dev/null` 以靜音 |
| `GRAPHIFY_QUERY_LOG_DISABLE` | 設為 `1` 以完全停用查詢日誌 | 選用 |
| `GRAPHIFY_QUERY_LOG_RESPONSES` | 設為 `1` 以同時記錄完整子圖回應（預設關閉） | 選用 |
| `GRAPHIFY_MAX_GRAPH_BYTES` | 覆寫 512 MiB 的 graph.json 大小上限 —— 例如 `700MB`、`2GB`，或純位元組數 | 選用 —— 對非常大的語料有用 |
| `GRAPHIFY_LLM_TEMPERATURE` | 覆寫語意提取的 LLM temperature —— 例如 `0.7`，或 `none` 以省略 | 選用 —— 對 o1/o3/o4/gpt-5 推理模型自動省略 |

---

## 隱私

- **程式碼檔案** —— 透過 tree-sitter 在本地處理。不會有任何內容離開你的機器。純程式碼的語料不需要 API key —— `graphify extract` 可完全離線執行。
- **影片／音訊** —— 以 faster-whisper 在本地轉錄。不會有任何內容離開你的機器。
- **文件、PDF、圖片** —— 會送往你的 AI 助手進行語意提取（透過 `/graphify` 技能，使用你 IDE 階段所執行的任何模型）。無頭的 `graphify extract` 需要 `GEMINI_API_KEY` / `GOOGLE_API_KEY`（Gemini）、`MOONSHOT_API_KEY`（Kimi）、`ANTHROPIC_API_KEY`（Claude）、`OPENAI_API_KEY`（OpenAI）、`DEEPSEEK_API_KEY`（DeepSeek）、一個執行中的 Ollama 實例（`OLLAMA_BASE_URL`）、透過標準供應者鏈提供的 AWS 憑證（Bedrock —— 不需 API key，使用 IAM），或 `claude` CLI 二進位檔（Claude Code —— 不需 API key，使用你的 Claude 訂閱）。`--dedup-llm` 旗標使用同一把金鑰。
- **資料落地（Data residency）** —— `graphify extract` 會依設定了哪一把 API key 自動偵測要使用哪個供應者（優先序：Gemini → Kimi → Claude → OpenAI → DeepSeek → Azure → Bedrock → Ollama）。對有資料落地需求的程式碼，使用 `--backend ollama`（完全本地）或傳入明確的 `--backend` 旗標。Kimi（`MOONSHOT_API_KEY`）會路由到 Moonshot AI 位於中國的伺服器。
- 無遙測、無使用追蹤、無分析。
- **查詢日誌** —— 每次 `graphify query`、`graphify path`、`graphify explain` 與 MCP `query_graph` 呼叫都會以 JSON Lines 格式記錄到 `~/.cache/graphify-queries.log`（時間戳、問題、語料、回傳節點數、耗時）。完整的子圖回應預設**不會**儲存。設定 `GRAPHIFY_QUERY_LOG_DISABLE=1` 以退出，或 `GRAPHIFY_QUERY_LOG=/dev/null` 以靜音而不停用程式碼路徑。

---

## 疑難排解

**安裝後 `graphify: command not found`**
CLI 已安裝，但其 bin 目錄不在你 shell 的 `PATH` 上。依你的安裝方式選擇對應修法：
- **uv**（`uv tool install graphifyy`）：指令會落在 uv 的工具 bin 目錄（`~/.local/bin`），全新的 macOS/zsh 設定常常沒把它放在 `PATH` 上。執行 `uv tool update-shell`，然後開啟新終端機。（用 `uv tool dir --bin` 找出該目錄。）
- **pipx**（`pipx install graphifyy`）：執行 `pipx ensurepath`，然後開啟新終端機。
- **pip**（`pip install graphifyy`）：pip 會把腳本安裝到一個可能不在 `PATH` 上的使用者 bin 目錄 —— 在 `~/.zshrc`/`~/.bashrc` 中把 `~/Library/Python/3.x/bin`（macOS）或 `~/.local/bin`（Linux）加入你的 `PATH`，或直接執行 `python -m graphify`。

**`uvx graphify …` 或 `uv tool run graphify …` 無法解析 `graphify`**
PyPI 套件是 `graphifyy`；`graphify` 只是它所提供的指令。`uv tool run` 會把第一個字當成*套件名稱*，因此它會去找一個叫 `graphify` 的套件並回報 `No solution found … no versions of graphify`。請明確指定套件：`uvx --from graphifyy graphify install`（等同 `uv tool run --from graphifyy graphify install`）。或先 `uv tool install graphifyy`，之後直接呼叫 `graphify`。

**`python -m graphify` 可以但 `graphify` 指令不行**
你 shell 的 `PATH` 不包含該指令安裝到的 bin 目錄。優先使用 `uv tool install` / `pipx install` 而非純 `pip`，然後執行 `uv tool update-shell` / `pipx ensurepath` 並開啟新終端機（見上方安裝說明）。

**在 PowerShell 中 `/graphify .` 造成「path not recognized」**
PowerShell 把開頭的 `/` 視為路徑分隔符號。在 Windows 上使用 `graphify .`（不加斜線）。

**`--update` 或重建後圖譜節點變少**
若重構刪除了檔案，舊節點會殘留。傳入 `--force`（或設定 `GRAPHIFY_FORCE=1`），即使重建後節點較少也會覆寫。

**同一個實體在圖譜中出現重複節點（ghost 重複）**
Ghost 重複（同一個符號出現兩次 —— 一次來自帶有原始位置的 AST 提取，一次來自不帶位置的語意提取）現在會在建構時自動合併。若你在 v0.8.33 之前建立的圖譜中看到這種情況，執行一次完整重新提取以清理：
```bash
graphify extract . --force
```

**Ollama 耗盡 VRAM／超出上下文視窗**
KV-cache 視窗會自動調整大小，但對你的 GPU 而言可能太大。將它縮小：
```bash
GRAPHIFY_OLLAMA_NUM_CTX=8192 graphify extract ./docs --backend ollama --token-budget 4000
```

**`LLM returned invalid JSON` / `Unterminated string` 警告**
模型的 JSON 回應達到了它的輸出 token 上限，並在字串中途被截斷。graphify 會自動復原（它會切分 chunk 並重新提取兩半，而過大的單一文件會先在標題／段落邊界切片，因此整個檔案仍會被涵蓋），所以這些警告很吵但並非資料遺失。若要減少這種反覆，提高輸出上限或縮小每個 chunk 的輸出：
```bash
GRAPHIFY_MAX_OUTPUT_TOKENS=16384 graphify extract . --mode deep   # 提高上限
graphify extract . --mode deep --token-budget 4000                # 較小的輸入 chunk -> 較小的輸出
```
搭配像 OpenRouter 這類雲端閘道時，相較於 Ollama shim，偏好使用 `--backend openai`（設定 `OPENAI_BASE_URL`）—— 那是更乾淨的 OpenAI 相容路徑。若模型本身有最大輸出上限，降低 `--token-budget` 是可靠的調節手段。

**圖譜 HTML 太大，瀏覽器開不了（>5000 節點）**
略過 HTML 產生並直接使用 JSON：
```bash
graphify cluster-only ./my-project --no-viz
graphify query "..."
```

**兩位開發者同時 commit 後 `graph.json` 出現衝突標記**
執行 `graphify hook install` —— 它會設定一個 git merge driver，自動聯集合併 `graph.json`，使衝突永不發生。

**文件或 PDF 的提取回傳空的節點／邊**
文件、PDF 與圖片需要 LLM 呼叫 —— 純程式碼語料則不需要金鑰。檢查你的 API key 是否已設定且後端正確：
```bash
ANTHROPIC_API_KEY=sk-... graphify extract ./docs --backend claude
```

**IDE 中出現技能版本不符警告**
你安裝的 graphify 版本與技能檔不同。更新：
```bash
uv tool upgrade graphifyy
graphify install  # 覆寫技能檔
```

---

## 完整指令參考

```
/graphify                          # 在目前目錄執行
/graphify ./raw                    # 在指定資料夾執行
/graphify ./raw --mode deep        # 更積極的關係提取
/graphify ./raw --update           # 只重新提取變更過的檔案
/graphify ./raw --directed         # 保留邊的方向
/graphify ./raw --cluster-only     # 在既有圖譜上重新執行聚類
/graphify ./raw --no-viz           # 略過 HTML 視覺化
/graphify ./raw --obsidian         # 產生 Obsidian vault
/graphify ./raw --obsidian --obsidian-dir ~/vault  # 寫入既有的 vault（絕不覆寫你自己的筆記或 .obsidian 設定）
/graphify ./raw --wiki             # 建立 agent 可爬取的 markdown wiki
/graphify ./raw --svg              # 匯出 graph.svg
/graphify ./raw --graphml          # 為 Gephi / yEd 匯出
/graphify ./raw --neo4j            # 為 Neo4j 產生 cypher.txt
/graphify ./raw --neo4j-push bolt://localhost:7687
/graphify ./raw --falkordb         # 為 FalkorDB 產生 cypher.txt
/graphify ./raw --falkordb-push falkordb://localhost:6379
/graphify ./raw --watch            # 隨檔案變更自動同步
/graphify ./raw --mcp              # 啟動 MCP stdio 伺服器

/graphify add https://arxiv.org/abs/1706.03762
/graphify add <video-url>
/graphify add https://... --author "Name" --contributor "Name"

/graphify query "what connects attention to the optimizer?"
/graphify query "..." --dfs --budget 1500
/graphify path "DigestAuth" "Response"
/graphify explain "SwinTransformer"

graphify save-result --question "Q" --answer "A" --nodes Foo Bar --outcome useful   # 記錄一次問答的結果（work memory；outcome ∈ useful|dead_end|corrected）
graphify reflect                   # 把 graphify-out/memory/ 的結果彙整成 reflections/LESSONS.md
graphify reflect --if-stale        # 當 LESSONS.md 已比每個輸入都新時不做任何事（每個階段執行都很便宜）
graphify reflect --out docs/LESSONS.md    # 把 lessons 文件寫到別處
graphify reflect --graph graphify-out/graph.json  # 依社群分組 lessons + 寫入 work-memory overlay（.graphify_learning.json）
                                   # overlay 會把節點標記為 preferred/tentative/contested（依時近性加權，附來源）；
                                   # graphify explain / query 接著會顯示「Lesson:」提示，當來源已變動時標記為「code changed — re-verify」
graphify uninstall                 # 一次從所有平台移除
graphify uninstall --purge         # 同時刪除 graphify-out/
graphify uninstall --project --platform codex  # 只移除專案範圍的安裝檔

graphify hook install              # post-commit + post-checkout hooks
graphify hook uninstall
graphify hook status

# 常駐助手指令 - 各平台專屬
graphify claude install            # CLAUDE.md + PreToolUse hook（Claude Code）
graphify claude uninstall
graphify codebuddy install         # CODEBUDDY.md + PreToolUse hook（CodeBuddy）
graphify codebuddy uninstall
graphify codex install             # AGENTS.md + .codex/hooks.json 中的 PreToolUse hook（Codex）
graphify opencode install          # AGENTS.md + tool.execute.before plugin（OpenCode）
graphify kilo install              # 原生 Kilo 技能 + /graphify 指令 + AGENTS.md + .kilo plugin
graphify kilo uninstall
graphify cursor install            # .cursor/rules/graphify.mdc（Cursor）
graphify cursor uninstall
graphify gemini install            # GEMINI.md + BeforeTool hook（Gemini CLI）
graphify gemini uninstall
graphify copilot install           # 技能檔（GitHub Copilot CLI）
graphify copilot uninstall
graphify aider install             # AGENTS.md（Aider）
graphify aider uninstall
graphify claw install              # AGENTS.md（OpenClaw）
graphify claw uninstall
graphify droid install             # AGENTS.md（Factory Droid）
graphify droid uninstall
graphify trae install              # AGENTS.md（Trae）
graphify trae uninstall
graphify trae-cn install           # AGENTS.md（Trae CN）
graphify trae-cn uninstall
graphify hermes install             # AGENTS.md + ~/.hermes/skills/（Hermes）
graphify hermes uninstall
graphify amp install               # 技能檔（Amp）
graphify amp uninstall
graphify agents install            # ~/.agents/skills/ + AGENTS.md（跨框架；別名：graphify skills）
graphify agents uninstall
graphify kiro install               # .kiro/skills/ + .kiro/steering/graphify.md（Kiro IDE/CLI）
graphify kiro uninstall
graphify pi install                # 技能檔（Pi coding agent）
graphify pi uninstall
graphify devin install             # 技能檔 + .windsurf/rules/graphify.md（Devin CLI）
graphify devin uninstall
graphify antigravity install       # .agents/rules + .agents/workflows（Google Antigravity）
graphify antigravity uninstall

graphify extract ./docs                        # 為 CI 進行無頭 LLM 提取（不需要 IDE）
graphify extract ./docs --backend gemini       # 明確指定後端：gemini、kimi、claude、openai、deepseek、ollama、bedrock 或 claude-cli
graphify extract ./docs --backend gemini --model gemini-3.1-pro-preview
graphify extract ./docs --backend ollama       # 本地 Ollama（設定 OLLAMA_BASE_URL / OLLAMA_MODEL）- loopback 不需 API key
OPENAI_BASE_URL=http://localhost:8080/v1 OPENAI_MODEL=my-model graphify extract ./docs --backend openai   # 任何 OpenAI 相容伺服器（llama.cpp、vLLM、LM Studio）
ANTHROPIC_BASE_URL=http://localhost:4000 ANTHROPIC_MODEL=my-model graphify extract ./docs --backend claude   # 任何 Anthropic 相容端點（LiteLLM proxy、閘道）
GRAPHIFY_OLLAMA_NUM_CTX=32768 graphify extract ./docs --backend ollama   # 覆寫 KV-cache 視窗（預設自動調整）
GRAPHIFY_OLLAMA_KEEP_ALIVE=0 graphify extract ./docs --backend ollama    # 每個 chunk 後卸載模型（在小 GPU 上節省 VRAM）
graphify extract ./docs --backend bedrock      # 透過 IAM 的 AWS Bedrock - 不需 API key，使用 AWS 憑證鏈
graphify extract ./docs --backend claude-cli   # 透過 Claude Code CLI 路由 - 不需 API key，使用你的 Claude 訂閱
graphify extract ./docs --backend azure        # Azure OpenAI（設定 AZURE_OPENAI_API_KEY + AZURE_OPENAI_ENDPOINT）
graphify extract ./docs --max-workers 16       # AST 平行處理（也可用 GRAPHIFY_MAX_WORKERS）
graphify extract --postgres "postgresql://user:pass@host/db"   # 直接內省即時 PostgreSQL schema
graphify extract ./my-workspace --cargo        # 直接內省 Rust Cargo workspace 相依
graphify extract ./docs --token-budget 30000   # 為本地／小型模型使用較小的語意 chunk
graphify extract ./docs --max-concurrency 2    # 較少的並行 LLM 呼叫（對本地推論有用）
graphify extract ./docs --api-timeout 900      # 為緩慢的本地模型延長 HTTP 逾時（預設 600s）
graphify extract ./docs --google-workspace     # 在提取前透過 gws 匯出 .gdoc/.gsheet/.gslides
graphify extract ./docs --mode deep            # 透過延伸的系統提示進行更豐富的語意提取
graphify extract ./docs --no-cluster           # 只做原始提取，略過聚類
graphify extract ./docs --timing               # 把每階段的 wall-clock 時間印到 stderr（也適用於 cluster-only）
graphify extract ./docs --force                # 即使新圖譜節點較少也覆寫 graph.json（重構後或清除 ghost 重複時使用）
graphify extract ./docs --dedup-llm            # 對模糊的實體配對使用 LLM 仲裁（使用同一把 API key）
graphify extract ./docs --global --as myrepo   # 提取並註冊到跨專案的全域圖譜
GRAPHIFY_MAX_OUTPUT_TOKENS=32768 graphify extract ./docs --backend claude  # 為密集語料提高輸出上限

graphify export callflow-html                       # graphify-out/<project>-callflow.html
graphify export callflow-html --max-sections 8      # 限制產生的架構章節數
graphify export callflow-html --output docs/arch.html
graphify export callflow-html ./some-repo/graphify-out

graphify global add graphify-out/graph.json --as myrepo   # 把專案圖譜註冊到 ~/.graphify/global-graph.json
graphify global remove myrepo                         # 從全域圖譜移除一個專案
graphify global list                                  # 顯示所有已註冊的 repo + 節點／邊數
graphify global path                                  # 印出全域圖譜檔的路徑

graphify prs                              # PR 儀表板：CI、審查、worktree、圖譜影響
graphify prs 42                           # 深入分析 PR #42
graphify prs --triage                     # AI triage 排名（自動從環境偵測後端）
graphify prs --worktrees                  # worktree → branch → PR 對應
graphify prs --conflicts                  # 共用圖譜社群的 PR（合併順序風險）
graphify prs --base main                  # 篩選出以特定 base 分支為目標的 PR
graphify prs --repo owner/repo            # 對不同的 GitHub repo 執行
GRAPHIFY_TRIAGE_BACKEND=kimi graphify prs --triage   # 為 triage 使用特定後端

graphify clone https://github.com/karpathy/nanoGPT
graphify merge-graphs a.json b.json --out merged.json
graphify --version                                    # 印出已安裝版本
graphify watch ./src
graphify check-update ./src
graphify update ./src
graphify update ./src --no-cluster  # 略過重新聚類，只寫入原始 AST 圖譜
graphify update ./src --force       # 即使新圖譜節點較少也覆寫
graphify cluster-only ./my-project
graphify cluster-only ./my-project --graph path/to/graph.json  # 自訂圖譜位置
graphify cluster-only ./my-project --max-concurrency 16 --batch-size 200  # 並行社群標記（大型圖譜）
graphify cluster-only ./my-project --resolution 1.5            # 更多、更小的社群
graphify cluster-only ./my-project --exclude-hubs 99           # 從分割中排除 p99 度數節點
graphify cluster-only ./my-project --no-label                  # 保留「Community N」佔位符
graphify cluster-only ./my-project --backend=gemini            # 社群命名的後端
graphify cluster-only ./my-project --backend=gemini --model gemini-2.5-pro  # 特定模型
graphify label ./my-project                                    # 用設定的後端（重新）命名社群
graphify label ./my-project --backend=openai --model gpt-4o   # 強制使用特定後端與模型
```

> **社群名稱：** 在 agent 內（Claude Code、Gemini CLI），agent 會自己命名社群。當你執行純 CLI 時，`cluster-only` 會用設定的後端（內建或自訂的 OpenAI 相容供應者）自動命名 —— 傳入 `--no-label` 以保留 `Community N`，或執行 `graphify label` 以按需（重新）產生名稱。

---

## 了解更多

- [運作原理](../how-it-works.md) —— 提取流程、社群偵測、置信度評分、基準測試
- [ARCHITECTURE.md](../../ARCHITECTURE.md) —— 模組分解、如何新增語言
- [選用整合](../docker-mcp-sqlite.md) —— Docker MCP Toolkit + SQLite

---

## 基於 graphify 構建 —— Penpax

[**Penpax**](https://graphifylabs.ai) 是建構在 graphify 之上的常駐層 —— 它把同樣的圖譜方法套用到你的整個工作生活：會議、瀏覽器歷史、電子郵件、檔案與程式碼，在背景持續更新。

為那些工作橫跨數百場對話與文件、永遠無法完整重建的人而打造。無雲端，完全在裝置上執行。

**免費試用即將推出。** [加入等待名單 →](https://graphifylabs.ai)

---

<details>
<summary>貢獻</summary>

### 開發環境設定

本專案使用 [uv](https://docs.astral.sh/uv/) 作為開發工作流程。安裝一次，然後：

```bash
git clone https://github.com/safishamsi/graphify.git
cd graphify
git checkout v8                        # 活躍的開發分支

# 建立專案 venv 並安裝 graphify + 所有 extras + dev group
#（pytest）。uv 預設會安裝 dev 相依群組；傳入 --no-dev 可
# 略過。
uv sync --all-extras
```

驗證可編輯（editable）安裝：
```bash
uv run graphify --version
uv run python -c "import graphify; print(graphify.__file__)"
```

### 執行測試

```bash
uv run pytest tests/ -q                # 執行完整測試套件
uv run pytest tests/test_extract.py -q # 單一模組
uv run pytest tests/ -q -k "python"    # 依名稱篩選
```

> macOS 注意：測試套件同時包含 `sample.f90` 與 `sample.F90` fixtures。它們在不分大小寫的 HFS+ / APFS 檔案系統上會衝突。若你需要同時測試兩種 Fortran 變體，請在 Linux 或 Docker 容器中執行。

### Git 工作流程

- 活躍開發在 `v8` 分支上進行。
- Commit 風格：`fix: <description>` / `feat: <description>` / `docs: <description>`
- 開 PR 前，執行 `uv run pytest tests/ -q` 並確認通過。
- 為任何新的語言提取器，在 `tests/fixtures/` 新增一個 fixture 檔，並在 `tests/test_languages.py` 新增測試。

### 該貢獻什麼

**Worked examples（實作範例）** 是最有用的貢獻。對一個真實語料執行 `/graphify`，把輸出存到 `worked/{slug}/`，寫一份誠實的 `review.md`，說明圖譜哪裡做對了、哪裡做錯了，然後開 PR。

**提取 bug** —— 開 issue 並附上輸入檔、快取項目（`graphify-out/cache/`），以及遺漏或弄錯了什麼。

模組職責與如何新增語言，見 [ARCHITECTURE.md](../../ARCHITECTURE.md)。

</details>
