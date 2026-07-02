# OpenClaw 入口

这是 OpenClaw 的薄入口文件。共享说明看 [../../README.md](../../README.md)，核心能力看 [../../SKILL.md](../../SKILL.md)。

## OpenClaw 应该怎么装

执行：

```bash
bash install.sh --platform openclaw
```

如果你还需要网页 / X / 微信公众号 / YouTube / 知乎自动提取，再执行：

```bash
bash install.sh --platform openclaw --with-optional-adapters
```

默认安装位置：`~/.openclaw/skills/llm-wiki`

如果你的 OpenClaw 不是这个目录，改用：

```bash
bash install.sh --platform openclaw --target-dir <你的技能目录>/llm-wiki
```

之后升级同一个自定义目录时，也传同样的目标目录：

```bash
bash install.sh --upgrade --platform openclaw --target-dir <你的技能目录>/llm-wiki
```
