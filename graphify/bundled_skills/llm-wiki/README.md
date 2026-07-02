[English](README.en.md) | 中文

<div align="center">

# llm-wiki

基于 [Andrej Karpathy](https://karpathy.ai/) 的 [llm-wiki 方法论](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)

**更适合国内宝宝体质的 K 神知识库**

把碎片化的信息变成持续积累、互相链接的知识库

[![version](https://img.shields.io/badge/v3.6.11-社区节点地图-E8D5B5?style=flat-square&labelColor=3a3026&color=E8D5B5)](https://github.com/sdyckjq-lab/llm-wiki-skill/releases)
[![license](https://img.shields.io/badge/MIT-license-5a6e5c?style=flat-square&labelColor=3a3026)](LICENSE)
[![platforms](https://img.shields.io/badge/Claude·Codex·OpenClaw·Hermes-多平台-7a96a6?style=flat-square&labelColor=3a3026)]

</div>

---

## 效果预览

<div align="center">
<img src="assets/graph-demo.gif?v=20260428" width="100%" alt="知识图谱演示">
</div>

东方编辑部 × 数字山水风交互式知识图谱 — 双击 HTML 文件即可在浏览器中探索。搜索、社区图例、聚焦筛选、节点视觉分层、社区轻量地图、悬停预览、轻量摘要、明确进入阅读、Shift 多选、画布缩放拖拽和小地图定位，全部离线运行，不依赖服务器。

---

## 30 秒上手

把仓库链接扔给你正在用的 agent，让它自己完成安装。

```bash
# Claude Code
bash install.sh --platform claude

# Codex
bash install.sh --platform codex

# OpenClaw
bash install.sh --platform openclaw

# Hermes
bash install.sh --platform hermes
```

然后说：

> "帮我初始化一个知识库"
> "帮我消化这篇：<链接>"

核心区别：知识被**编译一次，持续维护**，而不是每次查询都从原始文档重新推导。

---

## 核心亮点

| | 功能 | 说明 |
|---|---|---|
| 🗺️ | **数字山水知识图谱** | 自包含 HTML，双击即可浏览；三栏国风布局、山水底图、可拖拽缩放画布、小地图定位和左右阅读区全部离线运行 |
| ✨ | **图谱阅读体验打磨** | 节点按地名、索引签条、朱砂批注分层；默认画面更轻，悬停可预览，点击先看摘要，再通过明确动作进入阅读 |
| 🎓 | **本地阅读动线** | 社区图例、聚焦筛选、图谱搜索、右侧摘要/阅读抽屉和选区抽屉保持联动；社区先摘要再进入聚焦 |
| 🧭 | **社区轻量地图** | 进入社区后改用更松弛的点状地图；节点按类型区分颜色，悬停或点击时只突出相关节点和关系 |
| 📦 | **零配置初始化** | 一句话创建完整知识库，自动生成目录结构、模板和研究方向页 |
| 🔗 | **结构化 Wiki** | 自动生成实体页、主题页、素材摘要，用 `[[双向链接]]` 互相关联 |
| 🏷️ | **置信度标注** | EXTRACTED / INFERRED / AMBIGUOUS / UNVERIFIED，一眼看出哪些需要核实 |
| 🔄 | **智能缓存** | SHA256 去重 + 写入即更新 + 自愈安全网，弱模型也不会漏缓存 |
| 🧠 | **对话结晶化** | 把有价值的对话内容直接沉淀为知识库页面 |
| 🎨 | **工作台 Paper 视觉** | 工作台沿用暖纸配色，按钮、消息、侧栏和图谱控件保持统一，长标题不会撑开页面 |
| 💬 | **工作台对话自动跟随** | 发送和流式回复时自动停在最新内容，用户上翻时暂停，并用向下箭头一键回到底部 |
| 🧰 | **工作台动态工具状态** | agent 执行工具时显示当前动作；完成后折叠成摘要，避免主对话被工具流水账刷屏 |
| 📡 | **自动上下文注入** | SessionStart hook 让 agent 每次会话自动感知知识库 |
| 📊 | **多格式分析** | 深度报告、对比表、时间线三种综合分析格式 |

---

## 素材来源

| 分类 | 来源 | 处理方式 |
|---|---|---|
| 核心 | PDF、Markdown、文本、HTML、纯文本粘贴 | 直接消化，不依赖外挂 |
| 可选 | 网页文章、X/Twitter、微信公众号、YouTube、知乎 | 自动提取；失败时按回退提示改走手动 |
| 手动 | 小红书 | 当前只支持手动粘贴 |

可选提取器需要在安装时显式开启：

```bash
bash install.sh --platform claude --with-optional-adapters
```

---

## 平台入口

每个平台有专属入口说明：

- [Claude Code](platforms/claude/CLAUDE.md)
- [Codex](platforms/codex/AGENTS.md)
- [OpenClaw](platforms/openclaw/README.md)
- [Hermes](platforms/hermes/README.md)

---

<details>
<summary><strong>完整功能列表</strong></summary>

- **研究方向引导** — `purpose.md` 让 agent 在整理和查询时有明确方向
- **两步式整理** — 先分析后生成，长内容走两步链式思考，短内容简化处理
- **ingest 格式验证** — 脚本自动校验分析结果，模型再笨也不会写出残缺数据
- **智能素材路由** — 根据 URL 域名自动选择最佳提取方式
- **核心优先安装** — 默认只准备知识库主线，网页/X/公众号/YouTube/知乎按需显式开启
- **伴随升级命令** — Claude Code 安装后自带 `/llm-wiki-upgrade`
- **素材删除** — 级联删除时自动清理关联页面、断链和缓存
- **图谱运行时兜底更稳** — helper 同时支持浏览器全局与 CommonJS，旧运行时下的复杂 emoji 截断和离线 HTML 失败回滚都更可靠
- **大图谱全局路线** — 全局视角以 Sigma/Graphology 承接地图级浏览和轻量摘要；DOM/SVG 保留给社区阅读、离线细节和小图异常兜底
- **社区轻量地图** — 进入社区后默认显示更小、更松的节点；不同类型节点用不同颜色区分，悬停或点击节点时只突出一度、二度关系
- **图谱视野稳定** — 点击社区摘要或重复点击同一位置时，图谱保持原视角，不会被右侧抽屉挤动
- **工作台 Paper 视觉** — Paper v2 暖纸配色覆盖工作台默认主题、新对话按钮、消息气泡、侧栏和图谱控件，长标题和长消息保持在页面内部
- **查询结果持久化** — 有价值的综合回答可保存回知识库，越用越完整
- **批量消化** — 给一个文件夹路径，批量处理所有文件
- **工作台对话自动跟随** — 发送消息和接收长回复时默认跟随最新内容，用户上翻阅读历史时暂停，并提供图标按钮回到底部
- **工作台工具摘要** — `workbench/` 对话区采用 `omp` 风格动态工具状态，停止时显示取消状态，历史工具调用默认折叠为分组摘要
- **知识库健康检查** — 脚本检测孤立页面、断链、index 一致性；AI 层面检查矛盾和交叉引用
- **ingest 隐私自查** — 首次消化素材时提醒检查手机号、API key 等敏感信息
- **图谱关系词汇表** — 可选的手动标注词汇，让图谱表达更精确
- **Obsidian 兼容** — 所有内容都是本地 markdown，直接用 Obsidian 打开

</details>

<details>
<summary><strong>安装详情</strong></summary>

### 默认安装位置

| 平台 | 路径 |
|---|---|
| Claude Code | `~/.claude/skills/llm-wiki` |
| Codex | `~/.codex/skills/llm-wiki` |
| OpenClaw | `~/.openclaw/skills/llm-wiki` |
| Hermes | `~/.hermes/skills/llm-wiki` |

### 更新

已安装？进入仓库目录执行：

```bash
bash install.sh --upgrade
```

自动完成：`git pull` → 检测已安装平台 → 重新复制核心文件 → 已有 hook 不受影响。

Claude Code 默认安装的，可以直接用 `/llm-wiki-upgrade`。

自定义目录：

```bash
bash install.sh --upgrade --platform openclaw --target-dir <你的技能目录>/llm-wiki
```

```bash
bash install.sh --upgrade --platform hermes --target-dir <你的技能目录>/llm-wiki
```

### 前置条件

- 核心：agent 能执行 shell 命令、读写本地文件即可；图谱构建和来源信号覆盖检查需要 `jq` + `node`
- 可选：微信公众号提取需要 `uv`；网页提取需要 `bun` 或 `npm`；需要登录态的内容可开启 Chrome 调试端口 9222

</details>

<details>
<summary><strong>目录结构</strong></summary>

```
你的知识库/
├── raw/                    # 原始素材（不可变）
│   ├── articles/           # 网页文章
│   ├── tweets/             # X/Twitter
│   ├── wechat/             # 微信公众号
│   ├── xiaohongshu/        # 小红书
│   ├── zhihu/              # 知乎
│   ├── pdfs/               # PDF
│   ├── notes/              # 笔记
│   └── assets/             # 图片等附件
├── wiki/                   # AI 生成的知识库
│   ├── entities/           # 实体页（人物、概念、工具）
│   ├── topics/             # 主题页
│   ├── sources/            # 素材摘要
│   ├── comparisons/        # 对比分析
│   ├── synthesis/          # 综合分析
│   │   └── sessions/       # 对话结晶化页面
│   └── queries/            # 保存的查询结果
├── purpose.md              # 研究方向与目标
├── index.md                # 索引
├── log.md                  # 操作日志
├── .wiki-schema.md         # 配置
└── .wiki-cache.json        # 素材去重缓存
```

</details>

<details>
<summary><strong>常见问题</strong></summary>

**这个仓库还是只给 Claude 用吗？**
不是。Claude 只是其中一个入口。同一个链接能被 Claude Code、Codex、OpenClaw、Hermes 安装和使用。

**为什么 Hermes 要看 `HERMES.md`？**
Hermes 会优先加载仓库根的 `HERMES.md` 作为项目上下文。这个文件只负责 Hermes 的入口与安装说明，核心能力和工作流仍以 `SKILL.md` 为准。

**Claude Code 里可以直接用命令更新吗？**
可以。默认安装后自带 `/llm-wiki-upgrade`，更新核心主线。需要网页/X/公众号/YouTube/知乎提取能力时，再加 `--with-optional-adapters`。

**X/Twitter 提取失败？**
确保已安装可选提取器（`--with-optional-adapters`）。需要登录态的内容请开启 Chrome 调试端口 9222，或者直接粘贴内容给 agent。

**公众号提取失败？**
需要 `uv`。安装后重新运行 `bash install.sh --platform <你的平台> --with-optional-adapters`。

</details>

---

## 这个仓库里有什么

本仓库是 llm-wiki 的 monorepo，包含两种使用形态，读写同一份知识库格式、可自由切换：

- **Skill 形态**（上文介绍，成熟稳定）：把仓库链接丢给 Claude Code / Codex / OpenClaw / Hermes 一键安装，在你的 AI CLI 里维护知识库。
- **agent 工作台**（`workbench/`，开发中）：本地运行的知识库工作台，以对话为中心、内置交互式数字山水知识图谱。当前面向开发者（`npm run dev`），成熟后提供桌面应用；图谱语义会保持同一套，方便后续桌面形态复用。

交互式图谱引擎（`packages/graph-engine/`）由两种形态共享——Skill 的离线 HTML 和工作台的图谱视图，是同一个引擎的两个出口。

---

## Windows 用户

Windows PowerShell 5.1（Win10 / Win11 系统自带）默认 console 编码为 GB2312、`$OutputEncoding` 为 ASCII，Python 子进程 `sys.stdout.encoding` 默认为 `gbk`。直接在 PS 5.1 下运行 `bash install.sh` 会导致中文输出和 hook JSON 出现乱码（[#16](https://github.com/sdyckjq-lab/llm-wiki-skill/issues/16)）。

**方案 A — 使用 `install.ps1`（推荐）**

在仓库根目录下：

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1 --platform claude
powershell -ExecutionPolicy Bypass -File install.ps1 --platform codex --dry-run
```

`install.ps1` 会自动把 console / `$OutputEncoding` / `PYTHONIOENCODING` 全部设为 UTF-8，再转发到 `bash install.sh`。

**方案 B — 手动设置 PowerShell 编码**

```powershell
chcp 65001
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = 'utf-8'
bash install.sh --platform claude
```

**方案 C — 升级到 PowerShell 7+**

PowerShell 7 默认 UTF-8。安装：`winget install Microsoft.PowerShell`，然后 `pwsh` 下直接 `bash install.sh --platform claude`。

### Python 命令

Windows 上 Python 通常安装为 `python.exe` 而非 `python3.exe`（Microsoft Store 的 `python3` 是安装提示 stub，调用会失败）。本项目 `scripts/shared-config.sh` 已加入自动检测：**先尝试 `python3`，失败回退到 `python`**。所以只要 Python 3.8+ 在 PATH 中（任一命名即可），脚本能正常工作。

---

## 致谢

本项目复用和集成了以下开源项目：

- **[Andrej Karpathy](https://karpathy.ai/)** — [llm-wiki gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)，核心方法论来源
- **[baoyu-url-to-markdown](https://github.com/JimLiu/baoyu-skills#baoyu-url-to-markdown)** by [JimLiu](https://github.com/JimLiu) — 网页、X/Twitter 内容提取
- **youtube-transcript** — YouTube 字幕提取
- **[wechat-article-to-markdown](https://github.com/jackwener/wechat-article-to-markdown)** — 微信公众号文章提取

## License

MIT

---

## Star History

[![Star History Chart](https://api.star-history.com/chart?repos=sdyckjq-lab/llm-wiki-skill&type=date)](https://www.star-history.com/?repos=sdyckjq-lab%2Fllm-wiki-skill&type=date)
