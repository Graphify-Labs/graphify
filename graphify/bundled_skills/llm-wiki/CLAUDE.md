# CLAUDE.md

## 🧭 仓库导航（任何人 / AI 进来先读这里）

本仓库是 **llm-wiki monorepo**，含三个区：

| 区 | 位置 | 状态 |
|---|---|---|
| **agent 工作台**（开发主线） | `workbench/`（server + web） | 🚧 活跃开发 |
| **共享图谱引擎** | `packages/graph-engine/` | 🚧 随 agent 演进 |
| **Skill 形态** | 根目录 `SKILL.md` / `scripts/` / `templates/` / `platforms/` | ❄️ 成熟·维护冻结 |

➡️ **开发 agent 工作台（日常主线）**：先读 [workbench/CLAUDE.md](workbench/CLAUDE.md) + [workbench/PRODUCT.md](workbench/PRODUCT.md)——当前阶段、ADR、协作规则都在那里。

➡️ **本文件以下内容**：Skill 形态的安装与维护规则，**仅当你在维护 Skill 时才看**（install.sh / SKILL.md / scripts / templates / platforms）。Skill 已功能成熟、进入维护冻结，不再追加新功能。

---

## Skill 形态：安装与维护

先看这三个文件：

- [README.md](README.md)：多平台总说明
- [platforms/claude/CLAUDE.md](platforms/claude/CLAUDE.md)：Claude 专属入口提示
- [SKILL.md](SKILL.md)：核心能力和工作流

## Claude 安装动作

如果当前任务是安装这个 skill，优先执行：

```bash
bash install.sh --platform claude
```

> `setup.sh` 是 `install.sh --platform claude` 的兼容包装，老用户可以继续用。

默认只准备知识库核心主线。如果这次要自动提取网页 / X / 微信公众号 / YouTube / 知乎，再执行：

```bash
bash install.sh --platform claude --with-optional-adapters
```

安装完成后，还会一并带上 `/llm-wiki-upgrade`。以后要更新核心主线，可以直接让 Claude 执行这个命令。

## 分支管理规则

改动代码（非纯文档/注释）时，按以下流程操作：

1. 开新分支：从 main 创建，命名用 feat/ 或 fix/ 前缀（如 fix/cache-reliability-write-through）
2. 分步 commit：每完成一个逻辑单元就提交（脚本实现 → 测试 → 文档更新，分开 commit）
3. 推送并创建 PR：推到远端后用 `gh pr create` 创建 PR
4. 合并：确认测试通过后在 GitHub 上合并

不需要开分支的情况：
- 只改了 CLAUDE.md、文档、注释
- 只是探索性阅读代码

设计文档或 plan 写完准备动手改代码时，也先开分支再开始实现。

## 推送前测试规则

每次 `git push` 前必须验证，按改动范围选深度：

### 第一层：快速检查（Claude Code 直接跑，1 分钟内）

不管改了什么都跑这 3 项：

1. `bash install.sh --dry-run --platform codex` — 安装脚本不报错
2. 改过的脚本如果有 `tests/fixtures/`，跑一下 diff 预期输出
3. `grep -r '本机用户路径\\|真实姓名\\|私有素材路径' scripts/ templates/ tests/ SKILL.md` — 没泄露隐私路径

### 第二/三层：工作流测试（你在 codex 终端手动跑）

- **第二层**（只改了 SKILL.md 里个别工作流）：Claude Code 生成测试提示词写到文件，告诉你路径，你复制到 codex 跑涉及的工作流
- **第三层**（多工作流改动 / 版本号升级）：Claude Code 生成全量回归提示词，你在 codex 跑完整流程（init → ingest → lint → digest → graph）

素材复用本机私有测试素材，不上传到远端。

codex 跑完后把 `test-report.md` 发回来，Claude Code 确认无阻塞问题后才执行 `git push`。

## 推送前文档更新规则

每次 commit 含功能改动（feat/fix）后、`git push` 前，**必须**主动检查并更新以下文档，不需要用户提醒：

1. **CHANGELOG.md**：在顶部加新版本条目（日期、新增/改进/修复分类）
2. **README.md 功能列表**：新增功能或行为变化时，在"功能"章节补一条
3. **版本号**：如果改动涉及新功能，在 CHANGELOG 条目里用新版本号（按 v当前+1 递增）

跳过条件：纯文档/排版/注释改动不需要更新。

## Skill routing

When the user's request matches an available skill, ALWAYS invoke it using the Skill
tool as your FIRST action. Do NOT answer directly, do NOT use other tools first.
The skill has specialized workflows that produce better results than ad-hoc answers.

Key routing rules:
- Product ideas, "is this worth building", brainstorming → invoke office-hours
- Bugs, errors, "why is this broken", 500 errors → invoke investigate
- Ship, deploy, push, create PR → invoke ship
- QA, test the site, find bugs → invoke qa
- Code review, check my diff → invoke review
- Update docs after shipping → invoke document-release
- Weekly retro → invoke retro
- Design system, brand → invoke design-consultation
- Visual audit, design polish → invoke design-review
- Architecture review → invoke plan-eng-review
- Save progress, checkpoint, resume → invoke checkpoint
- Code quality, health check → invoke health
