# AGENTS.md

## 🧭 仓库导航（任何人 / AI 进来先读这里）

本仓库是 **llm-wiki monorepo**，含三个区：

| 区 | 位置 | 状态 |
|---|---|---|
| **agent 工作台**（开发主线） | `workbench/`（server + web） | 🚧 活跃开发 |
| **共享图谱引擎** | `packages/graph-engine/` | 🚧 随 agent 演进 |
| **Skill 形态** | 根目录 `SKILL.md` / `scripts/` / `templates/` / `platforms/` | ❄️ 成熟·维护冻结 |

➡️ **开发 agent 工作台（日常主线）**：先读 [workbench/AGENTS.md](workbench/AGENTS.md) + [workbench/PRODUCT.md](workbench/PRODUCT.md)——当前阶段、ADR、协作规则都在那里。

➡️ **本文件以下内容**：Skill 形态的安装与维护规则，**仅当你在维护 Skill 时才看**（install.sh / SKILL.md / scripts / templates / platforms）。Skill 已功能成熟、进入维护冻结，不再追加新功能。

---

## Skill 形态：安装与维护

这是 llm-wiki 在 Codex 下的入口文件。

先看这三个文件：

- [README.md](README.md)：多平台总说明
- [platforms/codex/AGENTS.md](platforms/codex/AGENTS.md)：Codex 专属入口提示
- [SKILL.md](SKILL.md)：核心能力和工作流

## Codex 安装动作

如果当前任务是安装这个 skill，执行：

```bash
bash install.sh --platform codex
```

默认安装到 `~/.codex/skills/llm-wiki`。如果用户机器上还是旧的 `~/.Codex/skills`，安装器也会自动兼容。

默认只准备知识库核心主线。如果这次要自动提取网页 / X / 微信公众号 / YouTube / 知乎，再执行：

```bash
bash install.sh --platform codex --with-optional-adapters
```

## 重要提醒

- 不要把这个仓库当成 Codex 专属仓库；Claude Code、OpenClaw、Hermes 也共用同一套核心内容
- 安装完成后，再按 [SKILL.md](SKILL.md) 的工作流继续做事
- 如果 OpenClaw 使用的是自定义技能目录，可以改用 `--target-dir <你的技能目录>/llm-wiki`

## 分支管理规则

改动代码（非纯文档/注释）时，按以下流程操作：

1. 开新分支：从 main 创建，命名表达用 feat 或 fix 前缀；Codex 环境默认使用 `codex/` 命名空间，例如 `codex/fix-cache-reliability-write-through`
2. 分步 commit：每完成一个逻辑单元就提交（脚本实现、测试、文档更新分开 commit）
3. 推送并创建 PR：推到远端后用 `gh pr create` 创建 PR
4. 合并：确认测试通过后在 GitHub 上合并

不需要开分支的情况：

- 只改了 AGENTS.md、CLAUDE.md、文档、注释
- 只是探索性阅读代码

设计文档或 plan 写完准备动手改代码时，也先开分支再开始实现。

## 使用顺序

安装完成后，按 [SKILL.md](SKILL.md) 中的工作流继续执行：

1. `init`
2. `ingest`
3. `batch-ingest`
4. `query`
5. `digest`
6. `lint`
7. `status`
8. `graph`

## 已记录的解决方案

`docs/solutions/` 存放过去解决问题的文档（bug、最佳实践、工作流改进），按类别分目录，每份有 YAML frontmatter（`module`、`tags`、`problem_type`）。涉及已记录领域时（graph、cache、install、lint 等），先搜一下有没有现成经验。

## 推送前测试规则

每次 `git push` 前必须验证，按改动范围选深度：

### 第一层：快速检查（Codex 直接跑，1 分钟内）

不管改了什么都跑这 3 项：

1. `bash install.sh --dry-run --platform codex` — 安装脚本不报错
2. 改过的脚本如果有 `tests/fixtures/`，跑一下 diff 预期输出
3. `grep -r '本机用户路径\|真实姓名\|私有素材路径' scripts/ templates/ tests/ SKILL.md` — 没泄露隐私路径

### 第二/三层：工作流测试

- **第二层**（只改了 SKILL.md 里个别工作流）：生成测试提示词写到文件，并用 Codex 跑涉及的工作流
- **第三层**（多工作流改动 / 版本号升级）：生成全量回归提示词，在 Codex 跑完整流程（init → ingest → lint → digest → graph）

素材复用 `~/Desktop/llm-wiki-cowork-test/raw-input/` 里的 3 篇文章，不用每次重新找。

跑完后生成 `test-report.md`，确认无阻塞问题后才执行 `git push`。

## 推送前文档更新规则

每次 commit 含功能改动（feat/fix）后、`git push` 前，**必须**主动检查并更新以下文档，不需要用户提醒：

1. **CHANGELOG.md**：在顶部加新版本条目（日期、新增/改进/修复分类）
2. **README.md 功能列表**：新增功能或行为变化时，在"功能"章节补一条
3. **版本号**：如果改动涉及新功能，在 CHANGELOG 条目里用新版本号（按 v当前+1 递增）

跳过条件：纯文档/排版/注释改动不需要更新。

## Skill routing

当用户请求匹配可用 skill 时，优先使用对应 skill 的工作流。不要直接临时发挥；先打开对应 `SKILL.md`，按里面的流程做。

关键路由规则：

- Product ideas, "is this worth building", brainstorming → 使用 office-hours
- Bugs, errors, "why is this broken", 500 errors → 使用 investigate
- Ship, deploy, push, create PR → 使用 ship
- QA, test the site, find bugs → 使用 qa
- Code review, check my diff → 使用 review
- Update docs after shipping → 使用 document-release
- Weekly retro → 使用 retro
- Design system, brand → 使用 design-consultation
- Visual audit, design polish → 使用 design-review
- Architecture review → 使用 plan-eng-review
- Save progress, checkpoint, resume → 使用 checkpoint
- Code quality, health check → 使用 health
