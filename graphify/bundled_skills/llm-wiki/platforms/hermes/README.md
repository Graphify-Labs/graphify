# Hermes 入口

这是 Hermes 的薄入口文件。共享说明看 [../../README.md](../../README.md)，核心能力看 [../../SKILL.md](../../SKILL.md)。

## Hermes 应该怎么装

执行：

```bash
bash install.sh --platform hermes
```

如果你还需要网页 / X / 微信公众号 / YouTube / 知乎自动提取，再执行：

```bash
bash install.sh --platform hermes --with-optional-adapters
```

默认安装位置：`~/.hermes/skills/llm-wiki`

如果你的 Hermes 配了其他 skill 目录，改用：

```bash
bash install.sh --platform hermes --target-dir <你的技能目录>/llm-wiki
```

之后升级同一个自定义目录时，也传同样的目标目录：

```bash
bash install.sh --upgrade --platform hermes --target-dir <你的技能目录>/llm-wiki
```
