# Codex 入口

<!-- llm-wiki context: 如有知识库，优先查阅 wiki/index.md -->

这是 Codex 的薄入口文件。共享说明看 [../../README.md](../../README.md)，核心能力看 [../../SKILL.md](../../SKILL.md)。

## Codex 应该怎么装

执行：

```bash
bash install.sh --platform codex
```

如果你还需要网页 / X / 微信公众号 / YouTube / 知乎自动提取，再执行：

```bash
bash install.sh --platform codex --with-optional-adapters
```

默认安装位置：`~/.codex/skills/llm-wiki`

如果用户环境仍然在用旧的 `~/.Codex/skills`，安装器会自动兼容。
