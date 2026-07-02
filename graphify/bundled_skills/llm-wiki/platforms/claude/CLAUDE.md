# Claude Code 入口

这是 Claude Code 的薄入口文件。共享说明看 [../../README.md](../../README.md)，核心能力看 [../../SKILL.md](../../SKILL.md)。

## Claude 应该怎么装

优先执行：

```bash
bash install.sh --platform claude
```

如果你还需要网页 / X / 微信公众号 / YouTube / 知乎自动提取，再执行：

```bash
bash install.sh --platform claude --with-optional-adapters
```

如果你希望 Claude Code 在会话开始时自动感知当前知识库上下文，可以执行：

```bash
bash install.sh --platform claude --install-hooks
```

默认安装位置：`~/.claude/skills/llm-wiki`

安装完成后，还会一并带上 `/llm-wiki-upgrade`。以后要更新核心主线，可以直接让 Claude 执行这个命令；如果还要刷新网页 / X / 微信公众号 / YouTube / 知乎自动提取能力，再继续执行带 `--with-optional-adapters` 的升级。

## 兼容入口

老用户仍然可以继续执行：

```bash
bash setup.sh
```

它现在会走同一套安装流程，不再单独维护另一份逻辑。若需要自动提取 URL 类来源，再显式追加 `--with-optional-adapters`。
