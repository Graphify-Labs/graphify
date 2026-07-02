# Wiki Schema（知识库配置规范）

> 这个文件告诉 AI 如何维护你的知识库。你和 AI 可以一起调整它。

## 知识库信息

- 主题：{{TOPIC}}
- 创建日期：{{DATE}}
- 语言：{{LANGUAGE}}
- 版本：1.1

## 目录结构

```
{{WIKI_ROOT}}/
├── raw/                    # 原始素材（AI 只读，不会修改）
│   ├── articles/           # 网页文章
│   ├── tweets/             # X/Twitter 内容
│   ├── wechat/             # 微信公众号文章
│   ├── xiaohongshu/        # 小红书内容
│   ├── zhihu/              # 知乎内容
│   ├── pdfs/               # PDF 文件
│   ├── notes/              # 手写笔记
│   └── assets/             # 图片等附件
├── wiki/                   # 知识库主体（AI 写，你看）
│   ├── entities/           # 实体页（人物、组织、概念）
│   ├── topics/             # 主题页（研究主题、知识领域）
│   ├── sources/            # 素材摘要页（每个素材一篇摘要）
│   ├── comparisons/        # 对比分析页
│   └── synthesis/          # 综合分析页
├── index.md                # 内容索引（目录）
├── log.md                  # 操作日志（时间线）
└── .wiki-schema.md         # 本文件（配置规范）
```

## 页面命名规范

- 实体页：`wiki/entities/{名称}.md`
  - 例：`wiki/entities/知识构建.md`、`wiki/entities/Transformer.md`
- 主题页：`wiki/topics/{主题名}.md`
  - 例：`wiki/topics/AI编程工具.md`、`wiki/topics/大语言模型.md`
- 素材摘要：`wiki/sources/{日期}-{短标题}.md`
  - 例：`wiki/sources/2026-04-05-karpathy-llm-wiki.md`
- 对比分析：`wiki/comparisons/{对比主题}.md`
  - 例：`wiki/comparisons/工具选型.md`
- 综合分析：`wiki/synthesis/{分析主题}.md`
  - 例：`wiki/synthesis/AI工具选型建议.md`

## 交叉引用规范

- 页面间使用 `[[页面名]]` 语法（Obsidian 兼容的双向链接）
- 素材引用格式：`[来源: 素材标题](../sources/xxx.md)`
- 每个页面底部维护"相关页面"列表

## 页面格式规范

每个 wiki 页面应包含：

```markdown
---
tags: [标签1, 标签2]
created: YYYY-MM-DD
updated: YYYY-MM-DD
sources: [关联素材列表]
---

# 页面标题

> 一句话摘要

## 正文内容

...

## 相关页面

- [[另一个页面]]
- [[又一个页面]]
```

## Ingest（消化素材）规则

### 分级处理

根据素材长度和信息密度自动分级：

**完整处理**（素材 > 1000 字）：
1. 每个新素材**必须**生成摘要页（`wiki/sources/` 下）
2. 从素材中提取 3-5 个关键概念
3. 检查是否需要创建新的实体页（`wiki/entities/`）
4. 检查是否需要创建或更新主题页（`wiki/topics/`）
5. 更新 `index.md`（添加新条目）
6. 更新 `log.md`（记录操作）
7. 更新 `overview.md`（如果知识库全貌有变化）

**简化处理**（素材 < 1000 字，如短推文、小红书笔记）：
1. 生成摘要页（`wiki/sources/` 下）
2. 提取 1-3 个关键概念
3. 如果关键概念已有实体页，追加信息；如果没有，在摘要页中标记 `[待创建]`
4. 更新 `index.md` 和 `log.md`
5. 跳过主题页和 overview 更新

### 来源边界

这套边界和安装输出、状态说明、回归测试保持一致。

| 分类 | 当前来源 | 处理原则 |
|------|----------|----------|
| 核心主线 | `PDF / 本地 PDF`、`Markdown/文本/HTML`、`纯文本粘贴` | 不依赖外挂，直接进入主线 |
| 可选外挂 | `网页文章`、`X/Twitter`、`微信公众号`、`YouTube`、`知乎` | 先自动提取；失败时退回手动入口 |
| 手动入口 | `小红书` | 只接受用户手动粘贴 |

### 素材类型路由

| 来源 | raw 目录 | 提取方式 |
|------|----------|----------|
| 网页文章 | `raw/articles/` | baoyu-url-to-markdown skill |
| X/Twitter | `raw/tweets/` | baoyu-url-to-markdown skill（需 Chrome 登录） |
| 微信公众号 | `raw/wechat/` | wechat-article-to-markdown |
| YouTube | `raw/articles/` | youtube-transcript skill |
| 小红书 | `raw/xiaohongshu/` | 用户手动粘贴内容 |
| 知乎 | `raw/zhihu/` | 用户手动粘贴内容 或 baoyu-url-to-markdown skill |
| PDF / 本地 PDF | `raw/pdfs/` | 直接读取 |
| Markdown/文本/HTML | `raw/notes/` | 直接读取 |
| 纯文本粘贴 | `raw/notes/` | 直接使用 |

## 别名词表（Alias Table）

用于 query 和 digest 时自动展开搜索。搜索任意一个词，会同时搜索同一行的所有别名。
AI 在 ingest 时如果发现新的同义词关系，可以建议用户添加。

格式：每行一组同义词，用 `=` 分隔。

```
LLM = 大语言模型 = 大模型 = Large Language Model
RAG = 检索增强生成 = Retrieval Augmented Generation
fine-tuning = 微调 = 精调
prompt engineering = 提示工程 = 提示词工程
```

维护原则：
- 只收录在你的知识库里**实际出现过**的同义词，不要预填一堆用不到的
- 每组控制在 5 个以内，太多说明概念本身需要拆分
- 中英文混用时把最常用的放第一个
- ingest 发现新的同义词关系时，AI 应主动建议添加到此表

## Query（查询）规则

1. 先读 `index.md`，定位相关条目
2. 用 Grep 在 `wiki/` 下搜索关键词
3. 阅读相关页面后综合回答
4. 回答中标注来源页面（引用链接）
5. 有价值的分析建议保存为新的 wiki 页面

## Lint（健康检查）规则

1. 检查范围：随机抽查 10 个页面 + 最近更新的 10 个页面
2. 检查项：
   - 页面间矛盾（不同页面说法不一致）
   - 孤立页面（没有其他页面链接到它）
   - 缺失概念页（被 `[[某概念]]` 链接但实际不存在）
   - 缺少交叉引用（相关页面之间没有互相链接）
   - index 一致性（index.md 记录与实际文件是否对应）
3. 输出中文报告，对每个问题给出修复建议
4. 如果发现问题，询问用户是否自动修复

## 关系类型词汇表（可选，用于手动标注知识图谱）

这张表提供 graph 工作流生成的 `wiki/knowledge-graph.md` 里**可选**的关系类型词汇。
AI 生成图谱时默认全部用 `-->`（无标注），不自动判断关系类型。如果你想让图谱
更清楚地表达节点之间的语义，可以用编辑器把最重要的几条箭头改写成带标注的形式：

| 类型关键词 | 含义 | Mermaid 写法示例 |
|-----------|------|-----------------|
| 实现       | A 是 B 的具体实现 | `A -->|实现| B` |
| 依赖       | A 依赖 B 才能工作 | `A -->|依赖| B` |
| 对比       | A 与 B 是同类可以比较 | `A -->|对比| B` |
| 矛盾       | A 与 B 存在观点冲突 | `A -->|矛盾| B` |
| 衍生       | A 从 B 演化而来 | `A -->|衍生| B` |

使用原则：
- 只标最重要的 3-5 条关系，不要强行给所有箭头打标
- 不确定的关系保持默认 `-->` 箭头
- 自定义类型控制在 2 个以内，避免词汇表膨胀
- 标注后在 Obsidian / VS Code（Markdown Preview Enhanced）/ Typora 里重新渲染就能看到标签
