# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 开发命令

```bash
# 用 uv 管理依赖和运行
uv sync                                          # 安装全部依赖
uv run pytest tests/ -q                          # 跑全部测试
uv run pytest tests/test_extract.py -q           # 跑单个测试文件
uv run pytest tests/test_extract.py::test_func -q # 跑单个测试函数

# Lint / 类型检查 / 安全审计
uv run ruff check .                              # lint
uv run pyright                                   # 类型检查
uv run pre-commit run --all-files                # 全面检查（含 skillgen 一致性校验）

# 构建
uv run python -m build                           # 构建 wheel
uv run python -m tools.skillgen                  # 重新生成 17 个 SKILL.md（fragments → graphify/skill*.md）
uv run python -m tools.skillgen --bless          #   + 更新 expected 快照
```

## 架构（参见 ARCHITECTURE.md 了解详情）

**管线**：`detect() → extract() → build_graph() → cluster() → analyze() → report() → export()`

每个阶段是独立模块中的一个函数，以 NetworkX 图和简单 dict 传递数据，无共享状态。

**关键模块**：
| 模块 | 职责 |
|------|------|
| `graphify/__main__.py` | CLI 入口（~2600 行）：`install`/`uninstall`/`extract`/`update`/`serve`/`watch`/`clone` 等 |
| `graphify/extract.py` | 统一委派到 `graphify/extractors/*.py` 中的全部语言解析器 |
| `graphify/serve.py` | MCP 服务端入口（`graphify-mcp` 命令） |
| `tools/skillgen/` | **生成系统**：把 fragments 目录下的片段渲染为 `graphify/skill*.md`（17 个 platform）。编辑片段后**必须**重新运行 `python -m tools.skillgen`，否则 pre-commit 和 CI 会失败 |
| `graphify/bundled_skills/` | 15 个社区 skill（`gf-*` 命名空间），随包分发 |

**安全**：所有外部输入（URL、路径、label）均通过 `graphify/security.py` 校验。

## 使用任何 skill 都不能忽略 graphify 要求

## 任何情况下都必须遵守，未经允许不得修改代码

## 项目自身的 graphify 要求

> 这是 `AGENTS.md` 的要求——本项目使用 graphify 管理自身的知识图谱。

- **回答架构/代码库问题前**：先读 `graphify-out/GRAPH_REPORT.md` 了解 god node 和社区结构
- **若有 `graphify-out/wiki/index.md`**：导航 wiki 而非直接读原始文件
- **修改代码后**：运行 `graphify update .` 更新图谱（纯 AST 提取，不消耗 API）

## 离线安装器（本分支变更）

`feat/zip-installer` 分支用极简 zip 方案替换了 65 MB Nuitka `.exe`：

**新方案**（`tools/build_zip_installer.sh` → `dist/graphify-offline-installer.zip` ~11 MB）：
- `python/` — Python 3.12.10 embeddable
- `install.bat` — 探测 Python → `pip install graphifyy`（走内网代理 `192.168.21.14:25000`）→ `graphify install claude`
- `uninstall.bat` — 反向操作
- `README.txt` — 用户说明

**已删除**：`tools/build_windows_installer.{sh,py}`、`tools/installer_main.py`、`graphify/installer/`、5 个 installer 测试、`.github/workflows/build-windows-installer.yml`

**关键简化**：不再下载 38 个 wheels 到本地，不再编译 Nuitka，macOS 上就能构建。依赖从内网代理拉取。

## 约定

- 注释、变量名、commit message 用英文；解释性文字用简体中文
- CLI 子命令在 `graphify/__main__.py::main()` 的 if-elif 链中分发（无 click/argparse 框架）
- 测试文件一一对应模块：`tests/test_<module>.py`
