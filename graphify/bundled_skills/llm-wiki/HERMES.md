# HERMES.md

这是 llm-wiki 在 Hermes 下的入口文件。

先看这三个文件：

- [README.md](README.md)：多平台总说明
- [platforms/hermes/README.md](platforms/hermes/README.md)：Hermes 专属入口提示
- [SKILL.md](SKILL.md)：核心能力和工作流

## Hermes 安装动作

如果当前任务是安装这个 skill，执行：

```bash
bash install.sh --platform hermes
```

默认安装到 `~/.hermes/skills/llm-wiki`。

默认只准备知识库核心主线。如果这次要自动提取网页 / X / 微信公众号 / YouTube / 知乎，再执行：

```bash
bash install.sh --platform hermes --with-optional-adapters
```

## 重要提醒

- 不要把这个仓库当成 Hermes 专属仓库；Claude Code、Codex、OpenClaw 也共用同一套核心内容
- Hermes 会优先读取仓库根的 `HERMES.md`；这里负责安装入口，知识库能力本身仍以 [SKILL.md](SKILL.md) 为准
- 安装完成后，再按 [SKILL.md](SKILL.md) 的工作流继续做事

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
