<p align="center">
  <a href="https://graphify.com"><img src="https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/graphify-logo.png" width="360" height="189" alt="Graphify"/></a>
</p>

<p align="center">
  <a href="https://trendshift.io/repositories/25296?utm_source=repository-badge&amp;utm_medium=badge&amp;utm_campaign=badge-repository-25296" target="_blank" rel="noopener noreferrer"><img src="https://trendshift.io/api/badge/repositories/25296" alt="Graphify-Labs%2Fgraphify | Trendshift" width="250" height="55"/></a>
</p>

<div align="center">
<details><summary><b>Read this in other languages</b></summary>

<a href="../../README.md">English</a> | <a href="README.zh-CN.md">简体中文</a> | <a href="README.ja-JP.md">日本語</a> | <a href="README.ko-KR.md">한국어</a> | <a href="README.de-DE.md">Deutsch</a> | <a href="README.fr-FR.md">Français</a> | <a href="README.es-ES.md">Español</a> | <a href="README.hi-IN.md">हिन्दी</a> | <a href="README.pt-BR.md">Português</a> | <a href="README.ru-RU.md">Русский</a> | <a href="README.ar-SA.md">العربية</a> | <a href="README.fa-IR.md">فارسی</a> | <a href="README.it-IT.md">Italiano</a> | <a href="README.pl-PL.md">Polski</a> | <a href="README.nl-NL.md">Nederlands</a> | <a href="README.tr-TR.md">Türkçe</a> | <a href="README.uk-UA.md">Українська</a> | <a href="README.vi-VN.md">Tiếng Việt</a> | <a href="README.id-ID.md">Bahasa Indonesia</a> | <a href="README.sv-SE.md">Svenska</a> | <a href="README.el-GR.md">Ελληνικά</a> | <a href="README.ro-RO.md">Română</a> | <a href="README.cs-CZ.md">Čeština</a> | <a href="README.fi-FI.md">Suomi</a> | <a href="README.da-DK.md">Dansk</a> | <a href="README.no-NO.md">Norsk</a> | <a href="README.hu-HU.md">Magyar</a> | <a href="README.th-TH.md">ภาษาไทย</a> | <a href="README.uz-UZ.md">Oʻzbekcha</a> | <a href="README.zh-TW.md">繁體中文</a> | <a href="README.fil-PH.md">Filipino</a> | <a href="README.he-IL.md">עברית</a>

</details>
</div>

<p align="center">
  <a href="https://pypi.org/project/graphifyy/"><img src="https://img.shields.io/pypi/v/graphifyy" alt="PyPI"/></a>
  <a href="https://github.com/Graphify-Labs/graphify/actions/workflows/ci.yml"><img src="https://github.com/Graphify-Labs/graphify/actions/workflows/ci.yml/badge.svg?branch=v8" alt="CI"/></a>
  <a href="../../LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue" alt="License: Apache-2.0"/></a>
  <a href="https://pepy.tech/project/graphifyy"><img src="https://img.shields.io/pepy/dt/graphifyy?color=blue&label=downloads" alt="Downloads"/></a>
  <a href="https://docs.graphify.com"><img src="https://img.shields.io/badge/Docs-docs.graphify.com-0b7285?style=flat&logo=readthedocs&logoColor=white" alt="Docs"/></a>
  <a href="https://app.graphify.com/login"><img src="https://img.shields.io/badge/Graphify%20Cloud-app.graphify.com-118d4f?style=flat&logoColor=white" alt="Graphify Cloud"/></a>
  <a href="https://discord.gg/graphify"><img src="https://img.shields.io/badge/Discord-Join-5865F2?style=flat&logo=discord&logoColor=white" alt="Discord"/></a>
  <a href="https://www.youtube.com/@graphifylabs"><img src="https://img.shields.io/badge/YouTube-Graphify%20Labs-FF0000?style=flat&logo=youtube&logoColor=white" alt="YouTube"/></a>
  <a href="https://www.linkedin.com/company/graphify-labs"><img src="https://img.shields.io/badge/LinkedIn-Graphify%20Labs-0077B5?logo=linkedin" alt="LinkedIn"/></a>
  <a href="https://www.ycombinator.com/companies/graphify-labs"><img src="https://img.shields.io/badge/Y%20Combinator-S26-F0652F?style=flat&logo=ycombinator&logoColor=white" alt="YC S26"/></a>
</p>

<p align="center">
  <b>خفّض إنفاق وكلائك على الرموز بنسبة 80%.</b> Graphify Cloud ذاكرة دائمة التشغيل تحكم وكلاءك، وتحافظ على جودة عالية للكود، وتثبت الصحة عبر التحقق الصوري. <a href="https://app.graphify.com/login"><b>ابدأ تجربة مجانية لمدة 14 يومًا &rarr;</b></a>
</p>

اكتب `/graphify` في مساعد البرمجة بالذكاء الاصطناعي لديك فيرسم مشروعك بالكامل (الكود والمستندات وملفات PDF والصور والفيديو) في **رسم بياني معرفي** يمكنك **الاستعلام عنه بدلًا من البحث بـ grep** عبر الملفات.

- **خرائط الكود مجانية، ومحلية بالكامل.** يُحلَّل الكود بشجرة بنية tree-sitter AST: حتمي، بلا نموذج لغوي كبير، ولا شيء يغادر جهازك. (أما المستندات وملفات PDF والصور والفيديو فتستخدم نموذج مساعدك، أو مفتاح API مُهيّأ، لتمريرة دلالية.)
- **كل حافة مشروحة.** يُوسَم كل اتصال بـ `EXTRACTED` (صريح في المصدر) أو `INFERRED` (استنتجه graphify)، لتميّز ما قُرئ مباشرة عما استُنتج.
- **ليس فهرسًا شعاعيًا.** لا تضمينات، ولا مخزن شعاعي: رسم بياني حقيقي تجتازه. اطرح سؤالًا، أو تتبّع المسار بين شيئين، أو اشرح مفهومًا واحدًا.

> [!NOTE]
> **تريد هذا دائم التشغيل؟** يُبقي [Graphify Cloud](https://app.graphify.com/login) الرسم البياني حيًّا عبر دورة حياة تطوير البرمجيات بأكملها: دعم المستودعات الأحادية والعابرة للمستودعات، والتحقق الصوري، ومراجعة الكود بنظرة شاملة على دورة حياة التطوير، إضافة إلى موصّلات لـ Sentry وJira والمزيد لتجلس الحوادث والتذاكر في الرسم البياني ذاته مع الكود. **[ابدأ تجربة مجانية لمدة 14 يومًا على app.graphify.com](https://app.graphify.com/login)**.

<p align="center">
  <img src="https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/graph-hero.png" alt="graphify's interactive graph.html showing the FastAPI codebase as a force-directed knowledge graph with a legend of detected communities" width="900">
</p>
<p align="center">
  <em>قاعدة كود FastAPI مرسومة بواسطة graphify. كل عقدة مفهوم، والألوان مجتمعات مكتشفة، والكل قابل للنقر في graph.html.</em>
</p>

**ابدأ الآن** (30 ثانية). يتطلب Python 3.10+ وuv (أو pipx):

```bash
uv tool install graphifyy      # install the CLI (or: pipx install graphifyy)
graphify install               # detects your assistant and registers the skill
```

ثم، في مساعد الذكاء الاصطناعي لديك:

```
/graphify .
```

هذا كل شيء. تحصل على **ثلاثة ملفات**:

```
graphify-out/
├── graph.html       open in any browser: click nodes, filter, search
├── GRAPH_REPORT.md  the highlights: key concepts, surprising connections, suggested questions
└── graph.json       the full graph: query it anytime without re-reading your files
```

يتضمن الرسم البياني المحفوظ `graph.schema_version` ليتمكن التكامل من اكتشاف
تغييرات التنسيق غير المتوافقة، إضافة إلى `graph.graphify_version` الذي يحدد
إصدار Graphify الذي أنتجه.

**تثبيت واحد، أي مساعد، أي نظام تشغيل.** Claude Code وCursor وCodex وGemini CLI وGitHub Copilot و20+ غيرها، على macOS وLinux وWindows: [اختر منصتك](#install).

---

## See it in action

<p align="center">
  <img src="https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/demo-path.svg" alt="graphify path query: a terminal asks for the shortest path between FastAPI and ModelField, and the answer lights up hop by hop across the knowledge graph" width="900">
</p>

بمجرد بناء الرسم البياني تستعلم عنه بدلًا من قراءة الملفات. مخرجات حقيقية، من تشغيل graphify على قاعدة كود FastAPI الموضحة أعلاه:

```text
$ graphify explain "APIRouter"
Node: APIRouter
  Source:    routing.py L2210
  Community: 2
  Degree:    47

Connections (47):
  --> RequestValidationError [uses] [INFERRED]
  --> Dependant [uses] [INFERRED]
  --> .get() [method] [EXTRACTED]
  <-- __init__.py [imports] [EXTRACTED]
  ...

$ graphify path "FastAPI" "ModelField"
Shortest path (3 hops):
  FastAPI --uses--> DefaultPlaceholder <--references-- get_request_handler() --references--> ModelField
```

تحمل كل حافة **وسم ثقة** (`EXTRACTED` = صريح في المصدر، `INFERRED` = مشتق بالتحليل)، لتميّز ما قُرئ مباشرة عما استُنتج. يعيد `graphify query "<question>"` رسمًا بيانيًا فرعيًا محدد النطاق لسؤال بلغة عادية، ويتتبّع `graphify path A B` كيف يرتبط أي شيئين.

---

## What it does

ما تحصل عليه جاهزًا:

| Capability | What you get |
|---|---|
| **God nodes** | أكثر المفاهيم اتصالًا، فترى ما يتدفق كل شيء من خلاله |
| **Communities** | الرسم البياني مقسّم إلى أنظمة فرعية (Leiden)، بتسميات بلا نموذج لغوي كبير |
| **Cross-file links** | `calls` / `imports` / `inherits` / `mixes_in` محلولة عبر ~40 لغة بواسطة tree-sitter AST |
| **Query, path, explain** | اطرح سؤالًا، أو تتبّع المسار بين شيئين، أو اشرح مفهومًا واحدًا، كل ذلك مقابل `graph.json` |
| **Rationale + doc refs** | تعليقات `# NOTE:` / `# WHY:` واستشهادات ADR/RFC تصبح عقدًا من الدرجة الأولى مرتبطة بالكود |
| **Beyond code** | المستندات وملفات PDF والصور والفيديو/الصوت كلها تُرسم في الرسم البياني ذاته |
| **Local-first** | يُحلَّل الكود محليًا بـ tree-sitter (بلا نموذج لغوي كبير، ولا شيء يغادر جهازك)؛ فقط التمريرة الدلالية على المستندات/الوسائط تستدعي خلفية، وفقط إذا هيّأت واحدة |

> [!TIP]
> تشغّل هذا عبر مستودعات كثيرة أو مستودع أحادي؟ يفعله [Graphify Cloud](https://app.graphify.com/login) باستمرار ويخفّض إنفاق الوكلاء على الرموز بنسبة 80%، مع روابط عابرة للمستودعات، ومراجعة كود على مستوى دورة حياة التطوير، وتحقق صوري، وموصّلات Sentry/Jira. [ابدأ تجربة مجانية لمدة 14 يومًا &rarr;](https://app.graphify.com/login)

---

## Benchmarks: 0.497 recall@10, 0 LLM credits

| Benchmark | Metric | graphify | Field |
|---|---|---|---|
| LOCOMO (n=300) | recall@10 | **0.497** | mem0 0.048, supermemory 0.149 |
| LOCOMO (n=300) | QA accuracy | 45.3% | supermemory 49.7%, mem0 27.3% |
| LongMemEval-S (n=50) | QA accuracy | **76%** | tied with dense RAG |
| ERPNext cross-tool (n=6) | key-fact coverage | **82.0%** | grep/read baseline 70.8% |
| Graph build | LLM credits | **0** | per-token for most systems |

شُغّل كل نظام على المنصة ذاتها بالنموذج ذاته والميزانيات ذاتها، وجرى تقييمه بحكَم مُتحقَّق منه بلا معرفة مسبقة مقابل حكَم ثانٍ (اتفاق 90.6%، كابا كوهين 0.81). جداول كاملة لكل نظام، ونتيجة ذكاء الكود، وأوامر إعادة الإنتاج: **[BENCHMARKS.md](../../BENCHMARKS.md)**.

---

## Documentation

الأدلة الكاملة والمرجع على **[docs.graphify.com](https://docs.graphify.com)**:

- **[Quickstart](https://docs.graphify.com/quickstart)**: ابنِ أول رسم بياني لك
- **[CLI reference](https://docs.graphify.com/reference/overview)**: كل أمر وراية
- **[Ask better graph questions](https://docs.graphify.com/guides/querying)**: أنماط الاستعلام
- **[Configuration](https://docs.graphify.com/reference/configuration)**: متغيرات البيئة والضبط
- **[Supported inputs](https://docs.graphify.com/concepts/supported-inputs)**: اللغات وأنواع الملفات
- **[Team workflows](https://docs.graphify.com/guides/team-workflows)** و**[PR review](https://docs.graphify.com/guides/pull-requests)**
- **[Troubleshooting](https://docs.graphify.com/troubleshooting)** و**[How it works](https://docs.graphify.com/concepts/architecture)**

---

## Prerequisites

| Requirement | Minimum | Check | Install |
|---|---|---|---|
| Python | 3.10+ | `python --version` | [python.org](https://www.python.org/downloads/) |
| uv *(recommended)* | any | `uv --version` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| pipx *(alternative)* | any | `pipx --version` | `pip install pipx` |

**تثبيت سريع على macOS (Homebrew):**
```bash
brew install python@3.12 uv
```

**تثبيت سريع على Windows:**
```powershell
winget install astral-sh.uv
```

**Ubuntu/Debian:**
```bash
sudo apt install python3.12 python3-pip pipx
# or install uv:
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## Install

> [!IMPORTANT]
> **الحزمة الرسمية:** حزمة PyPI هي `graphifyy` (بحرفَي y). حزم `graphify*` الأخرى على PyPI غير تابعة. أمر CLI ما يزال `graphify`.

مستودع المصدر الرسمي هو [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify).

البدء السريع بأمرين في أعلى هذا الملف التعريفي. يغطي هذا القسم طرق التثبيت، والتثبيت محدد النطاق بالمشروع، وكل منصة مدعومة.

**طرق التثبيت** (اختر واحدة):

```bash
uv tool install graphifyy   # recommended, isolated env (if 'graphify' isn't found after, run: uv tool update-shell)
pipx install graphifyy      # alternative
pip install graphifyy       # may need PATH setup, see Troubleshooting below
```

ثم شغّل `graphify install` مرة واحدة. يكتشف المساعد الذي تشغّله ويسجّل المهارة، فلا يوجد إعداد لكل مساعد. افتح مساعد الذكاء الاصطناعي لديك واكتب `/graphify .`

لتثبيت مهارة المساعد داخل المستودع الحالي بدلًا من ملف تعريف
المستخدم، أضف `--project`:

```bash
graphify install --project
graphify install --project --platform codex
```

يكتب التثبيت محدد النطاق بالمشروع تحت الدليل الحالي، على سبيل المثال
`.claude/skills/graphify/SKILL.md` أو `.agents/skills/graphify/SKILL.md` (إضافة إلى
ملحق `references/` تحمّله المهارة عند الطلب)، و
يطبع تلميح `git add` للملفات القابلة للإيداع.
الأوامر الخاصة بكل منصة التي تدعم التثبيت محدد النطاق بالمشروع تقبل الراية ذاتها،
على سبيل المثال `graphify claude install --project` أو `graphify codex install --project`.

> [!TIP]
> تواجه `command not found`، أو مشكلة `pip` على Mac/Windows، أو اقتباس PowerShell، أو استخدام `uvx`، أو مشاكل PATH في خطاف git، أو الوضع الصارم؟ راجع **[Installation](https://docs.graphify.com/installation)** و**[Troubleshooting](https://docs.graphify.com/troubleshooting)**.

<details>
<summary><b>Pick your platform</b> (20+ assistants, click to expand)</summary>

| Platform | Install command |
|----------|----------------|
| Claude Code (Linux/Mac) | `graphify install` |
| Claude Code (Windows) | `graphify install` (auto-detected) or `graphify install --platform windows` |
| CodeBuddy | `graphify install --platform codebuddy` |
| Codex | `graphify install --platform codex` |
| OpenCode | `graphify install --platform opencode` |
| Kilo Code | `graphify install --platform kilo` |
| GitHub Copilot CLI | `graphify install --platform copilot` |
| VS Code Copilot Chat | `graphify vscode install` |
| Aider | `graphify install --platform aider` |
| OpenClaw | `graphify install --platform claw` |
| Factory Droid | `graphify install --platform droid` |
| Trae | `graphify install --platform trae` |
| Trae CN | `graphify install --platform trae-cn` |
| Gemini CLI | `graphify install --platform gemini` |
| Hermes | `graphify install --platform hermes` |
| Kimi Code | `graphify install --platform kimi` |
| Amp | `graphify amp install` |
| Agent Skills (cross-framework) | `graphify install --platform agents` (alias `--platform skills`) |
| Kiro IDE/CLI | `graphify kiro install` |
| Pi coding agent | `graphify install --platform pi`, plus `graphify pi guard install` for the native guard |
| Cursor | `graphify cursor install` |
| Devin CLI | `graphify devin install` |
| Google Antigravity | `graphify antigravity install` |

يحتاج مستخدمو Codex أيضًا إلى `multi_agent = true` ضمن `[features]` في `~/.codex/config.toml` من أجل الاستخراج المتوازي. يستخدم CodeBuddy آلية أداة Agent وخطاف PreToolUse ذاتها التي يستخدمها Claude Code. يستخدم Factory Droid أداة `Task` لإرسال الوكلاء الفرعيين المتوازيين. يستخدم OpenClaw وAider استخراجًا تسلسليًا (دعم الوكلاء المتوازيين ما يزال مبكرًا على تلك المنصات). يستخدم Trae أداة Agent لإرسال الوكلاء الفرعيين المتوازيين و**لا** يدعم خطافات `PreToolUse`، لذا فإن AGENTS.md هي الآلية دائمة التشغيل.

تستهدف `--platform agents` (المرادف `--platform skills`) مواقع [Agent-Skills](https://github.com/anthropics/skills) العابرة للأُطر العامة: موقع المواصفة العام للمستخدم `~/.agents/skills/` (يقرؤه `npx skills` والأُطر المتوافقة مع المواصفة) للتثبيت العام، و`./.agents/skills/` للتثبيت محدد النطاق بالمشروع (`--project`). يبقى `graphify install` المجرد أحادي المنصة (Claude Code) عن قصد: استخدم منصة `agents` المسماة حين تريد أن تكون المهارة قابلة للاكتشاف بأي إطار يقرأ `.agents/skills`.

لا يملك Pi خطاف `PreToolUse`، لذا يسجّل `graphify pi guard install` امتداد Pi أصليًا (عبر أمر Pi الخاص `pi install <package directory>`) يشغّل `graphify hook-guard` المثبّت قبل استدعاءات Pi لـ `read` و`grep` و`find` واستدعاءات `bash` ذات نمط البحث. قرارات الرسم البياني الطازج/القديم ورفض القراءة المفهرسة مرة واحدة لكل جلسة عبر `GRAPHIFY_HOOK_STRICT=1` تأتي من السياسة ذاتها، فيطابق Pi سلوك خطاف Claude Code؛ ويصل التوجيه كرسالة تسيير `<system-reminder source="graphify">`. يحتاج إلى Pi 0.58.4 أو أحدث: الإصدارات الأقدم تجعل رسالة التسيير تتخطى بقية دفعة استدعاءات الأدوات المتوازية. تُشحن الحزمة داخل تثبيت Graphify، لذا ثبّت Graphify بشكل دائم (`uv tool install graphifyy` أو `pipx install graphifyy`، لا `uvx`)، وأعد تشغيل Pi بعد التثبيت أو الترقية، وأزله بـ `graphify pi guard uninstall`. تُفحص أهداف الملفات المحلية فقط؛ ويحتاج الخطاف إلى `graphify` على مدخل `PATH` مطلق خارج المشروع، وهو مقيّد باستدعاء مدته ثانيتان بحجم 256 كيبي داخلًا/64 كيبي خارجًا، ويفشل مفتوحًا. تُحمّل الحزمة ذاتها أيضًا في [Oh My Pi](https://github.com/can1357/oh-my-pi): `omp plugin install "$(graphify pi guard path)"`. يحتوي المسار المسجَّل على إصدار Python والبيئة الافتراضية، لذا أعد تشغيل `graphify pi guard install` بعد تغيير أيٍّ منهما، وأزل المدخل القديم بـ `pi remove <old path>`.

> يستخدم Codex `$graphify` بدلًا من `/graphify`.

</details>

<details>
<summary><b>Optional extras</b> (install only what you need)</summary>

| Extra | What it adds | Install |
|---|---|---|
| `pdf` | استخراج PDF | `uv tool install "graphifyy[pdf]"` |
| `office` | دعم `.docx` و`.xlsx` | `uv tool install "graphifyy[office]"` |
| `google` | عرض Google Sheets | `uv tool install "graphifyy[google]"` |
| `video` | نسخ الفيديو/الصوت (faster-whisper + yt-dlp) | `uv tool install "graphifyy[video]"` |
| `mcp` | خادم MCP عبر stdio | `uv tool install "graphifyy[mcp]"` |
| `neo4j` | دعم الدفع إلى Neo4j | `uv tool install "graphifyy[neo4j]"` |
| `falkordb` | دعم الدفع إلى FalkorDB | `uv tool install "graphifyy[falkordb]"` |
| `svg` | تصدير الرسم البياني بصيغة SVG | `uv tool install "graphifyy[svg]"` |
| `leiden` | اكتشاف مجتمعات Leiden (graspologic على Python < 3.13؛ خلفية أصلية على 3.13+) | `uv tool install "graphifyy[leiden]"` |
| `ollama` | استدلال Ollama المحلي | `uv tool install "graphifyy[ollama]"` |
| `openai` | واجهات OpenAI / المتوافقة مع OpenAI | `uv tool install "graphifyy[openai]"` |
| `gemini` | واجهة Google Gemini | `uv tool install "graphifyy[gemini]"` |
| `anthropic` | واجهة Anthropic Claude (`--backend claude`، تستخدم `ANTHROPIC_API_KEY`) | `uv tool install "graphifyy[anthropic]"` |
| `bedrock` | AWS Bedrock (يستخدم IAM، بلا مفتاح API) | `uv tool install "graphifyy[bedrock]"` |
| `azure` | خدمة Azure OpenAI (`--backend azure`، تستخدم `AZURE_OPENAI_API_KEY` + `AZURE_OPENAI_ENDPOINT`) | `uv tool install "graphifyy[openai]"` |
| `sql` | استخراج مخطط SQL | `uv tool install "graphifyy[sql]"` |
| `postgres` | استبطان PostgreSQL حي (`--postgres DSN`) | `uv tool install "graphifyy[postgres]"` |
| `dm` | استخراج BYOND DreamMaker `.dm`/`.dme` AST (قد يحتاج مترجم C + `python3-dev` إن لم تطابق أي عجلة منصتك) | `uv tool install "graphifyy[dm]"` |
| `terraform` | استخراج Terraform / HCL `.tf`/`.tfvars`/`.hcl` AST | `uv tool install "graphifyy[terraform]"` |
| `pascal` | استخراج Pascal / Delphi `.pas`/`.dpr`/`.dpk`/`.inc` AST (حواف `calls`/`inherits` أدق؛ يرجع إلى مستخرج regex عند غيابه) | `uv tool install "graphifyy[pascal]"` |
| `ocaml` | استخراج OCaml `.ml`/`.mli` AST | `uv tool install "graphifyy[ocaml]"` |
| `commonlisp` | استخراج Common Lisp `.lisp`/`.cl`/`.lsp`/`.asd` AST | `uv tool install "graphifyy[commonlisp]"` |
| `robot` | استخراج Robot Framework `.robot`/`.resource` (المجموعات، حالات الاختبار، الكلمات المفتاحية، حواف استدعاء الكلمات المفتاحية واستيراد الموارد/المكتبات) | `uv tool install "graphifyy[robot]"` |
| `chinese` | تقطيع الاستعلام الصيني (jieba) | `uv tool install "graphifyy[chinese]"` |
| `all` | كل ما سبق | `uv tool install "graphifyy[all]"` |

</details>

---

## Make your assistant always use the graph

شغّل هذا مرة واحدة في مشروعك بعد بناء رسم بياني:

شغّل `graphify <platform> install` مرة واحدة في مشروعك، على سبيل المثال `graphify claude install` أو `graphify codex install` (أو `graphify install --platform <name>`).

يكتب هذا ملف ضبط صغيرًا يخبر مساعدك أن يستشير الرسم البياني المعرفي في أسئلة قاعدة الكود، مفضّلًا الاستعلامات محددة النطاق مثل `graphify query "<question>"` على قراءة التقرير الكامل أو البحث بـ grep في الملفات الخام.

- **منصات الخطاف** (Claude Code وGemini CLI): يُطلَق خطاف تلقائيًا قبل استدعاءات الأدوات ذات نمط البحث (وعلى Claude Code، قبل قراءة ملفات المصدر واحدًا تلو الآخر عبر أداتَي Read/Glob) ويوجّه مساعدك نحو مسار الرسم البياني.
- **منصات ملف التعليمات** (Codex وOpenCode وCursor وغيرها): توفر ملفات التعليمات الدائمة (`AGENTS.md` و`.cursor/rules/` وغيرها) التوجيه ذاته المفضّل للاستعلام أولًا.

ما يزال `GRAPH_REPORT.md` متاحًا لمراجعة معمارية عامة.

الملفات التي تكتبها كل منصة بالضبط (ملف CodeBuddy `CODEBUDDY.md` + خطافات `PreToolUse`، وملف Codex `AGENTS.md`، وإضافة Kilo الأصلية `.kilo`، وقاعدة Cursor `alwaysApply`، وهكذا) مشروحة في **[Always-on setup](https://docs.graphify.com/guides/always-on)**.

لإزالة graphify من كل المنصات دفعة واحدة: `graphify uninstall` (أضف `--purge` لحذف `graphify-out/` أيضًا). أو استخدم الأمر الخاص بكل منصة (مثل `graphify claude uninstall`).

### CLI skills or MCP instructions?

تصف التعليمات التي يثبّتها `graphify install` وتلك المرفقة باتصال Graphify MCP طرقًا مختلفة لاستعلام رسم بياني:

| Setup | Guidance to use | Query access |
|---|---|---|
| CLI محلي ومهارة مساعد مثبّتة | تعليمات المنصة التي يكتبها `graphify install` | شغّل `graphify query` و`graphify path` و`graphify explain` مقابل الرسم البياني المحلي (`graphify-out/` افتراضيًا). |
| خادم Graphify MCP متصل | تعليمات الاتصال والأدوات التي يسردها ذلك الخادم | استدعِ أدوات MCP المسرودة مقابل الرسم البياني الذي يخدمه ذلك الاتصال. أسماء الأدوات وأوصافها تأتي من الخادم. |

كلاهما يشجّع الاستعلامات محددة النطاق على الرسم البياني قبل عمليات البحث الواسعة في المصدر. اختر التعليمات التي تطابق الأدوات التي يستطيع مساعدك الوصول إليها فعلًا؛ ولا تؤسس أي من الكتلتين قاعدة أسبقية شاملة لملفات تعليمات مساعدك. إذا استخدمت كلا التكاملين، فحدّد أي رسم بياني يستعلم عنه كل منهما واختر مسار استعلام أساسيًا بدلًا من نسخ كتلتَي تعليمات غير مشروطتين إلى `AGENTS.md`.

يثبّت `graphify install` تكامل المساعد المحلي؛ ولا يؤسس اتصال MCP. لا يحتاج عميل MCP إلى تشغيل استعلامات CLI محلية لاستخدام خادمه المتصل. خادم مستضاف محليًا ما يزال يحتاج إلى تثبيت Graphify ورسم بياني خاص به، بينما قد يخدم اتصال مستضاف رسمًا بيانيًا غير موجود في دليل عمل العميل. إذا كانت الأدوات المتوقعة مفقودة، فتحقق من تثبيت CLI أو اتصال MCP المعني بدلًا من معاملة تعليمات الإعداد الآخر على أنها قابلة للتبادل.

---

## What's in the report

يلخّص `GRAPH_REPORT.md` عقد god، والمجتمعات، والمسارات الرئيسية لمراجعة معمارية عامة. كيف يُبنى الرسم البياني وما يحتويه: **[How graphify works](https://docs.graphify.com/concepts/architecture)**.

---

## What files it handles: ~40 languages

يحلل graphify ~40 لغة برمجة محليًا بـ tree-sitter AST، ويرسم المستندات وملفات PDF والصور والصوت/الفيديو عبر تمريرة دلالية اختيارية. القائمة الكاملة: **[Supported inputs](https://docs.graphify.com/concepts/supported-inputs)**.

---

## Common commands

```bash
/graphify .                        # build graph for current folder
/graphify ./docs --update          # re-extract only changed files
/graphify . --cluster-only         # rerun clustering without re-extracting
/graphify . --cluster-only --resolution 1.5      # more granular communities
/graphify . --cluster-only --exclude-hubs 99     # suppress utility super-hubs from god-node rankings
/graphify . --no-viz               # skip the HTML, just the report + JSON
/graphify . --wiki                 # build a markdown wiki from the graph
graphify export callflow-html      # Mermaid architecture/call-flow HTML (auto-regenerates on every git commit if hook is installed)

/graphify query "what connects auth to the database?"
/graphify path "UserService" "DatabasePool"
/graphify explain "RateLimiter"

/graphify add https://arxiv.org/abs/1706.03762   # fetch a paper and add it
/graphify add <youtube-url>                       # transcribe and add a video

graphify hook install              # auto-rebuild on commit + branch checkout (run `graphify update .` after `git pull`: see "Recommended workflow" below)
graphify merge-graphs a.json b.json              # combine two graphs

graphify prs                       # PR dashboard: CI state, review status, worktree mapping
graphify prs 42                    # deep dive on PR #42 with graph impact
graphify prs --triage              # AI ranks your review queue (uses whatever backend is configured)
graphify prs --conflicts           # PRs sharing graph communities: merge-order risk
```

راجع [المرجع الكامل للأوامر](#full-command-reference) أدناه.

---

## Ignoring files

يحترم graphify ملف `.gitignore` ويدعم أنماط `--exclude` وملف مشروع `.graphifyignore`. التفاصيل: **[Configuration](https://docs.graphify.com/reference/configuration)**.


## Project configuration

أنشئ ملف `.graphifyrc` في جذر الفحص لإعدادات تخص المشروع لا تشغيلة واحدة. `key=value` واحد لكل سطر؛ والأسطر التي تبدأ بـ `#` تعليقات.

**الامتدادات الغامضة.** بعض الامتدادات تعني لغات مختلفة في مشاريع مختلفة: `.inc` هو PHP على pfSense، وPascal في شجرة Delphi، وSQL أو تجميعية في غيرها؛ و`.h` هو C أو C++؛ و`.m` هو Objective-C أو MATLAB. على graphify أن يختار افتراضًا عامًا واحدًا، وحين يختار خطأً لا يفشل الملف: يُحلَّل كاللغة الخاطئة ويعطي حفنة من العقد العرضية، فيبدو الرسم البياني مأهولًا بينما الرموز الحقيقية مفقودة. صرّح بما يعنيه الامتداد في مستودعك:

```
# .graphifyrc
# A language name:
language.inc=php
# Or an extension graphify already knows:
language.tpl=.ts
# Baked into the git hooks (see Team setup):
viz_node_limit=0
```

يتدفق التصريح عبر التصنيف، واختيار المستخرج، والقواعد والتحليل، والاستيرادات، و`graphify watch`، وذاكرة AST المؤقتة (ملف يُعاد تحليله بلغة مختلفة لا يعيد استخدام المدخل القديم أبدًا)، ويُقرأ `.graphifyrc` ذاته بواسطة `extract` و`update` والخطافات وخادم MCP ومهارة `/graphify`. يُبلَّغ عن الخطأ المطبعي مرة واحدة على stderr ويستمر الفحص بالافتراضات. كيف تتفاعل التصريحات مع التخزين المؤقت، وإعادة البناء التراكمي، وتحليل الاستيراد: **[Configuration](https://docs.graphify.com/reference/configuration)**.

---

## Team setup

أودِع الرسم البياني أو شاركه ليستعلم فريقك كله عن السياق ذاته، وراجع طلبات السحب بسياق الرسم البياني. راجع **[Share context with your team](https://docs.graphify.com/guides/team-workflows)** و**[Review pull requests](https://docs.graphify.com/guides/pull-requests)**.

---

## Using the graph directly

إلى جانب مساعد الذكاء الاصطناعي لديك، استعلم عن `graph.json` مباشرة من CLI بـ `graphify query` و`graphify path` و`graphify explain`. الاسم الذي يطابق عدة عقد يُرفض بسرد المرشحين بدلًا من التخمين. يمكن للسكربتات قراءة النتيجة من رمز الخروج: `0` إجابة، `3` اسم غامض، `4` لا عقدة مطابقة. راجع **[Ask better graph questions](https://docs.graphify.com/guides/querying)** و**[query reference](https://docs.graphify.com/reference/query)**.

---

## Environment variables

تُتحكَّم الخلفيات ومفاتيح API وسلوك الخطاف والضبط بمتغيرات البيئة. الجدول الكامل: **[Configuration](https://docs.graphify.com/reference/configuration)**.

---

## Privacy

- **ملفات الكود**: تُعالَج محليًا عبر tree-sitter. لا شيء يغادر جهازك. لا يتطلب مجموعة أكواد فقط أي مفتاح API: يعمل `graphify extract` بلا اتصال بالكامل. على مستودع مختلط، أضف `--code-only` لفهرسة الكود فقط وتخطي المستندات/ملفات PDF/الصور التي كانت ستحتاج نموذجًا لغويًا كبيرًا لولا ذلك.
- **الفيديو / الصوت**: يُنسخ محليًا بـ faster-whisper. لا شيء يغادر جهازك.
- **المستندات وملفات PDF والصور**: تُرسل إلى مساعد الذكاء الاصطناعي لديك للاستخراج الدلالي (عبر مهارة `/graphify`، باستخدام أي نموذج تشغّله جلسة بيئتك). يتطلب `graphify extract` بلا واجهة `GEMINI_API_KEY` / `GOOGLE_API_KEY` (Gemini)، أو `MOONSHOT_API_KEY` (Kimi)، أو `ANTHROPIC_API_KEY` (Claude)، أو `OPENAI_API_KEY` (OpenAI)، أو `DEEPSEEK_API_KEY` (DeepSeek)، أو مثيل Ollama قيد التشغيل (`OLLAMA_BASE_URL`)، أو بيانات اعتماد AWS عبر سلسلة المزود القياسية (Bedrock - بلا حاجة لمفتاح API، يستخدم IAM)، أو ثنائي `claude` CLI (Claude Code - بلا حاجة لمفتاح API، يستخدم اشتراك Claude لديك). تستخدم راية `--dedup-llm` المفتاح ذاته.
- **إقامة البيانات**: يكتشف `graphify extract` تلقائيًا أي مزود يستخدم بناءً على مفتاح API المضبوط (الأولوية: Gemini → Kimi → Claude → OpenAI → DeepSeek → Azure → Bedrock → Ollama). للكود ذي متطلبات إقامة البيانات، استخدم `--backend ollama` (محلي بالكامل) أو مرّر راية `--backend` صريحة. يوجّه Kimi (`MOONSHOT_API_KEY`) إلى خوادم Moonshot AI في الصين.
- **بلا قياس عن بُعد**، ولا تتبع استخدام، ولا تحليلات.
- **تسجيل الاستعلامات**: يُسجَّل كل استدعاء `graphify query` و`graphify path` و`graphify explain` وMCP `query_graph` إلى `~/.cache/graphify-queries.log` بصيغة JSON Lines (الطابع الزمني، السؤال، المجموعة، العقد المُعادة، المدة). استجابات الرسم البياني الفرعي الكاملة **لا** تُخزَّن افتراضيًا. اضبط `GRAPHIFY_QUERY_LOG_DISABLE=1` للانسحاب، أو `GRAPHIFY_QUERY_LOG=/dev/null` للإسكات دون تعطيل مسار الكود.

---

## Troubleshooting

مشاكل التثبيت والاستخراج الشائعة وإصلاحاتها: **[Troubleshooting](https://docs.graphify.com/troubleshooting)**.

---

## Full command reference

كل أمر وراية، مع أمثلة: **[CLI reference](https://docs.graphify.com/reference/overview)**.

---

## Learn more

- [docs.graphify.com](https://docs.graphify.com): التوثيق الكامل: الأدلة، ومرجع الأوامر، والتكاملات
- [How it works](../how-it-works.md): خط أنابيب الاستخراج، واكتشاف المجتمعات، وتسجيل الثقة، والمقاييس المعيارية
- [ARCHITECTURE.md](../../ARCHITECTURE.md): تفصيل الوحدات، وكيفية إضافة لغة
- [Optional integrations](../docker-mcp-sqlite.md): Docker MCP Toolkit + SQLite
- [The Memory Layer](https://safishamsi.gumroad.com/l/qetvlo): الكتاب عن الأفكار وراء graphify، والمعمارية من طرف إلى طرف

---

## Graphify Cloud

[**Graphify Cloud**](https://app.graphify.com/login) هي الطبقة دائمة التشغيل المبنية فوق graphify. بدلًا من رسم بياني تعيد بناءه عند الطلب لكل مجلد، تُبقي رسمًا بيانيًا حيًّا واحدًا عبر دورة حياة تطوير برمجياتك بأكملها:

- **رموز أقل بنسبة 80%**: الذاكرة دائمة التشغيل تعني أن وكلاءك يتوقفون عن إعادة قراءة قاعدة الكود وإعادة شرحها كل جلسة.
- **المستودع الأحادي والعابر للمستودعات**: رسم بياني متصل واحد عبر كل خدمة ومستودع، لا رسم بياني لكل مجلد.
- **التحقق الصوري**: افحص الثوابت المعمارية وثوابت التبعية مقابل الرسم البياني الحي.
- **مراجعة كود بنظرة شاملة على دورة حياة التطوير**: شاهد كيف يتموّج تغيير عبر النظام كله قبل الدمج.
- **موصّلات دورة حياة التطوير**: اسحب Sentry وJira والمزيد، لتعيش الحوادث والتذاكر والكود في رسم بياني واحد.
- **دائم التشغيل**: يُحدَّث باستمرار في الخلفية عبر الكود والمستندات والاجتماعات.

**[ابدأ تجربة مجانية لمدة 14 يومًا على app.graphify.com &rarr;](https://app.graphify.com/login)**

---

## Contributing

المساهمات مرحّب بها. راجع **[CONTRIBUTING.md](../../CONTRIBUTING.md)** لإعداد التطوير، وأوامر الاختبار وتكافؤ CI، وسير عمل git، وما يصنع مساهمة قوية (الأمثلة العملية وتقارير أخطاء الاستخراج هي الأكثر فائدة). المعمارية وكيفية إضافة لغة: [ARCHITECTURE.md](../../ARCHITECTURE.md).

جديد هنا؟ ألقِ التحية على [Discord](https://discord.gg/graphify) أو في [GitHub Discussions](https://github.com/Graphify-Labs/graphify/discussions).

---

## Contributors

<a href="https://github.com/Graphify-Labs/graphify/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=Graphify-Labs/graphify" alt="graphify contributors" />
</a>

Made with [contrib.rocks](https://contrib.rocks).

---

## Translations

الملف التعريفي متاح بـ 32 لغة. استخدم مبدّل اللغة في أعلى هذا الملف لقراءته بلغتك، أو تصفّح [`docs/translations/`](./). لتحسين ترجمة أو إضافة ترجمة جديدة، افتح طلب سحب مقابل الملف المطابق هناك.

---

## Building on graphify

تبني شيئًا في منظومة graphify؟ هذا مشجَّع. إذا استخدم مشروعك "graphify" في اسمه (على سبيل المثال `graphify-dashboard` أو `graphify-action`)، فأضف ملاحظة قصيرة إلى ملفك التعريفي توضح أنه مبني من المجتمع وغير تابع لـ Graphify Labs أو معتمد منها. "graphify" وشعار graphify علامتان لـ Graphify Labs؛ فالرجاء عدم استخدامهما بطريقة توحي بصفة رسمية.

---

## Community and links

<p align="center">
  <a href="https://graphify.com"><img src="https://img.shields.io/badge/Website-graphify.com-4c1?style=flat&logo=googlechrome&logoColor=white" alt="Website"/></a>
  <a href="https://discord.gg/graphify"><img src="https://img.shields.io/badge/Discord-Join-5865F2?style=flat&logo=discord&logoColor=white" alt="Discord"/></a>
  <a href="https://x.com/graphify"><img src="https://img.shields.io/badge/X-graphify-000000?logo=x&logoColor=white" alt="X"/></a>
  <a href="https://www.youtube.com/@graphifylabs"><img src="https://img.shields.io/badge/YouTube-Graphify%20Labs-FF0000?style=flat&logo=youtube&logoColor=white" alt="YouTube"/></a>
  <a href="https://github.com/sponsors/safishamsi"><img src="https://img.shields.io/badge/sponsor-safishamsi-ea4aaa?logo=github-sponsors" alt="Sponsor"/></a>
  <a href="https://safishamsi.gumroad.com/l/qetvlo"><img src="https://img.shields.io/badge/Book-The%20Memory%20Layer-2ea44f?style=flat&logo=gitbook&logoColor=white" alt="The Memory Layer"/></a>
</p>
