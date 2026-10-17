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
  <a href="https://discord.gg/XDnKVpzdXB"><img src="https://img.shields.io/badge/Discord-Join-5865F2?style=flat&logo=discord&logoColor=white" alt="Discord"/></a>
  <a href="https://www.youtube.com/@graphifylabs"><img src="https://img.shields.io/badge/YouTube-Graphify%20Labs-FF0000?style=flat&logo=youtube&logoColor=white" alt="YouTube"/></a>
  <a href="https://www.linkedin.com/company/graphify-labs"><img src="https://img.shields.io/badge/LinkedIn-Graphify%20Labs-0077B5?logo=linkedin" alt="LinkedIn"/></a>
  <a href="https://www.ycombinator.com/companies/graphify-labs"><img src="https://img.shields.io/badge/Y%20Combinator-S26-F0652F?style=flat&logo=ycombinator&logoColor=white" alt="YC S26"/></a>
</p>

<p align="center">
  <b>צמצמו את הוצאות הטוקנים של הסוכן ב-80%.</b> Graphify Cloud הוא זיכרון תמידי שמנהל את הסוכנים שלכם, שומר על איכות קוד גבוהה, ומוכיח נכונות באמצעות אימות פורמלי. <a href="https://app.graphify.com/login"><b>התחילו תקופת ניסיון חינם של 14 יום &rarr;</b></a>
</p>

הקלידו `/graphify` בעוזר קוד ה-AI שלכם והוא ממפה את כל הפרויקט (קוד, מסמכים, PDFs, תמונות, סרטונים) ל**גרף ידע** שאפשר **לתשאל במקום לבצע grep** על הקבצים.

- **מיפוי קוד בחינם, מקומי לחלוטין.** הקוד מנותח עם tree-sitter AST: דטרמיניסטי, ללא LLM, שום דבר לא עוזב את המכונה שלכם. (מסמכים, PDFs, תמונות וסרטונים משתמשים במודל של העוזר שלכם, או במפתח API מוגדר, למעבר סמנטי.)
- **כל קשת מוסברת.** כל חיבור מתויג `EXTRACTED` (מפורש במקור) או `INFERRED` (נפתר על ידי graphify), כך שתוכלו להבחין בין מה שנקרא ישירות לבין מה שהוסק.
- **לא אינדקס וקטורי.** ללא embeddings, ללא מאגר וקטורים: גרף אמיתי שעוברים בו. שאלו שאלה, עקבו אחר הנתיב בין שני דברים, או הסבירו מושג אחד.

> [!NOTE]
> **רוצים את זה באופן תמידי?** [Graphify Cloud](https://app.graphify.com/login) שומר על הגרף חי לאורך כל ה-SDLC שלכם: תמיכה במונורפו ובין מאגרים, אימות פורמלי, וסקירת קוד עם מבט על של ה-SDLC שלכם, בתוספת מחברים ל-Sentry, Jira, ועוד, כך שתקריות וכרטיסים יושבים באותו גרף כמו הקוד שלכם. **[התחילו תקופת ניסיון חינם של 14 יום ב-app.graphify.com](https://app.graphify.com/login)**.

<p align="center">
  <img src="https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/graph-hero.png" alt="graphify's interactive graph.html showing the FastAPI codebase as a force-directed knowledge graph with a legend of detected communities" width="900">
</p>
<p align="center">
  <em>בסיס הקוד של FastAPI ממופה על ידי graphify. כל צומת הוא מושג, הצבעים הם קהילות שזוהו, והכל ניתן ללחיצה ב-graph.html.</em>
</p>

**התחלה מהירה** (30 שניות). דורש Python 3.10+ ו-uv (או pipx):

```bash
uv tool install graphifyy      # install the CLI (or: pipx install graphifyy)
graphify install               # detects your assistant and registers the skill
```

לאחר מכן, בעוזר ה-AI שלכם:

```
/graphify .
```

זהו. אתם מקבלים **שלושה קבצים**:

```
graphify-out/
├── graph.html       open in any browser: click nodes, filter, search
├── GRAPH_REPORT.md  the highlights: key concepts, surprising connections, suggested questions
└── graph.json       the full graph: query it anytime without re-reading your files
```

הגרף הנשמר כולל `graph.schema_version` כך שאינטגרציות יכולות לזהות שינויי פורמט לא תואמים, בתוספת `graph.graphify_version` המזהה את גרסת Graphify שיצרה אותו.

**התקנה אחת, כל עוזר, כל מערכת הפעלה.** Claude Code, Cursor, Codex, Gemini CLI, GitHub Copilot, ועוד 20+, ב-macOS, Linux, ו-Windows: [בחרו את הפלטפורמה שלכם](#install).

---

## לראות את זה בפעולה

<p align="center">
  <img src="https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/demo-path.svg" alt="graphify path query: a terminal asks for the shortest path between FastAPI and ModelField, and the answer lights up hop by hop across the knowledge graph" width="900">
</p>

ברגע שהגרף נבנה אתם מתשאלים אותו במקום לקרוא קבצים. פלט אמיתי, graphify שהורץ על בסיס הקוד של FastAPI שמוצג למעלה:

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

כל קשת נושאת **תג ביטחון** (`EXTRACTED` = מפורש במקור, `INFERRED` = נגזר מתוך פתרון), כך שתוכלו להבחין בין מה שנקרא ישירות לבין מה שהוסק. `graphify query "<question>"` מחזיר תת-גרף ממוקד לשאלה בשפה טבעית, ו-`graphify path A B` עוקב אחר האופן שבו שני דברים מתחברים.

---

## מה זה עושה

מה אתם מקבלים מהקופסה:

| יכולת | מה אתם מקבלים |
|---|---|
| **צמתי על (God nodes)** | המושגים המחוברים ביותר, כך שאתם רואים דרך מה הכל זורם |
| **קהילות** | הגרף מחולק לתת-מערכות (Leiden), עם תוויות ללא LLM |
| **קישורים חוצי-קבצים** | `calls` / `imports` / `inherits` / `mixes_in` נפתרים על פני ~40 שפות באמצעות tree-sitter AST |
| **Query, path, explain** | שאלו שאלה, עקבו אחר הנתיב בין שני דברים, או הסבירו מושג אחד, הכל מול `graph.json` |
| **נימוקים + הפניות למסמכים** | הערות `# NOTE:` / `# WHY:` וציטוטי ADR/RFC הופכים לצמתים מהשורה הראשונה המקושרים לקוד |
| **מעבר לקוד** | מסמכים, PDFs, תמונות, ווידאו/אודיו, כולם ממופים לאותו גרף |
| **מקומי-ראשון** | הקוד מנותח מקומית עם tree-sitter (ללא LLM, שום דבר לא עוזב את המכונה שלכם); רק המעבר הסמנטי על מסמכים/מדיה פונה לשרת עורפי, ורק אם הגדרתם אחד |

> [!TIP]
> מריצים את זה על פני מאגרים רבים או מונורפו? [Graphify Cloud](https://app.graphify.com/login) עושה זאת ברציפות ומצמצם את הוצאות הטוקנים של הסוכן ב-80%, עם קישורים בין מאגרים, סקירת קוד לכל ה-SDLC, אימות פורמלי, ומחברי Sentry/Jira. [התחילו תקופת ניסיון חינם של 14 יום &rarr;](https://app.graphify.com/login)

---

## מדדי ביצועים: 0.497 recall@10, 0 LLM credits

| מדד | מטריקה | graphify | התחום |
|---|---|---|---|
| LOCOMO (n=300) | recall@10 | **0.497** | mem0 0.048, supermemory 0.149 |
| LOCOMO (n=300) | דיוק QA | 45.3% | supermemory 49.7%, mem0 27.3% |
| LongMemEval-S (n=50) | דיוק QA | **76%** | תיקו עם RAG צפוף |
| ERPNext cross-tool (n=6) | כיסוי עובדות מפתח | **82.0%** | קו בסיס grep/read 70.8% |
| בניית גרף | קרדיטים של LLM | **0** | לכל טוקן ברוב המערכות |

כל מערכת רצה על אותה תשתית בדיקה עם אותו מודל ואותם תקציבים, נוקדה על ידי שופט שאומת בעיוור מול שופט שני (90.6% הסכמה, קאפה של כהן 0.81). טבלאות מלאות לכל מערכת, תוצאת אינטליגנציית הקוד, ופקודות השחזור: **[BENCHMARKS.md](../../BENCHMARKS.md)**.

---

## תיעוד

מדריכים מלאים ותיעוד נמצאים ב-**[docs.graphify.com](https://docs.graphify.com)**:

- **[התחלה מהירה](https://docs.graphify.com/quickstart)**: בנו את הגרף הראשון שלכם
- **[תיעוד CLI](https://docs.graphify.com/reference/overview)**: כל פקודה ודגל
- **[שאלו שאלות גרף טובות יותר](https://docs.graphify.com/guides/querying)**: דפוסי תשאול
- **[תצורה](https://docs.graphify.com/reference/configuration)**: משתני סביבה וכוונון
- **[קלטים נתמכים](https://docs.graphify.com/concepts/supported-inputs)**: שפות וסוגי קבצים
- **[תהליכי עבודה לצוות](https://docs.graphify.com/guides/team-workflows)** ו-**[סקירת PR](https://docs.graphify.com/guides/pull-requests)**
- **[פתרון תקלות](https://docs.graphify.com/troubleshooting)** ו-**[איך זה עובד](https://docs.graphify.com/concepts/architecture)**

---

## דרישות מקדימות

| דרישה | מינימום | בדיקה | התקנה |
|---|---|---|---|
| Python | 3.10+ | `python --version` | [python.org](https://www.python.org/downloads/) |
| uv *(מומלץ)* | כל גרסה | `uv --version` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| pipx *(חלופה)* | כל גרסה | `pipx --version` | `pip install pipx` |

**התקנה מהירה ל-macOS (Homebrew):**
```bash
brew install python@3.12 uv
```

**התקנה מהירה ל-Windows:**
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
> **החבילה הרשמית:** חבילת PyPI היא `graphifyy` (עם שני y). חבילות `graphify*` אחרות ב-PyPI אינן קשורות. פקודת ה-CLI עדיין `graphify`.

מאגר המקור הרשמי הוא [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify).

ההתחלה המהירה בשתי פקודות נמצאת בראש ה-README הזה. הסעיף הזה מכסה את שיטות ההתקנה, התקנות בהיקף פרויקט, וכל פלטפורמה נתמכת.

**שיטות התקנה** (בחרו אחת):

```bash
uv tool install graphifyy   # recommended, isolated env (if 'graphify' isn't found after, run: uv tool update-shell)
pipx install graphifyy      # alternative
pip install graphifyy       # may need PATH setup, see Troubleshooting below
```

לאחר מכן הריצו `graphify install` פעם אחת. הוא מזהה איזה עוזר אתם מריצים ורושם את המיומנות, כך שאין הגדרה לכל עוזר בנפרד. פתחו את עוזר ה-AI שלכם והקלידו `/graphify .`

כדי להתקין את מיומנות העוזר למאגר הנוכחי במקום לפרופיל המשתמש שלכם, הוסיפו `--project`:

```bash
graphify install --project
graphify install --project --platform codex
```

התקנות בהיקף פרויקט נכתבות תחת הספרייה הנוכחית, לדוגמה `.claude/skills/graphify/SKILL.md` או `.agents/skills/graphify/SKILL.md` (בתוספת סייד-קאר `references/` שהמיומנות טוענת לפי דרישה), ומדפיסות רמז `git add` לקבצים שניתן לבצע להם commit. פקודות ספציפיות לפלטפורמה שתומכות בהתקנות בהיקף פרויקט מקבלות את אותו דגל, לדוגמה `graphify claude install --project` או `graphify codex install --project`.

> [!TIP]
> נתקלתם ב-`command not found`, בבעיית `pip` ב-Mac/Windows, בציטוט ב-PowerShell, בשימוש ב-`uvx`, בתקלות PATH של git-hook, או במצב מחמיר? ראו **[התקנה](https://docs.graphify.com/installation)** ו-**[פתרון תקלות](https://docs.graphify.com/troubleshooting)**.

<details>
<summary><b>בחרו את הפלטפורמה שלכם</b> (20+ עוזרים, לחצו להרחבה)</summary>

| פלטפורמה | פקודת התקנה |
|----------|----------------|
| Claude Code (Linux/Mac) | `graphify install` |
| Claude Code (Windows) | `graphify install` (זיהוי אוטומטי) או `graphify install --platform windows` |
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
| Agent Skills (חוצה-מסגרות) | `graphify install --platform agents` (כינוי `--platform skills`) |
| Kiro IDE/CLI | `graphify kiro install` |
| Pi coding agent | `graphify install --platform pi`, בתוספת `graphify pi guard install` לשומר המקורי |
| Cursor | `graphify cursor install` |
| Devin CLI | `graphify devin install` |
| Google Antigravity | `graphify antigravity install` |

משתמשי Codex זקוקים גם ל-`multi_agent = true` תחת `[features]` ב-`~/.codex/config.toml` לחילוץ מקבילי. CodeBuddy משתמש באותו כלי Agent ובאותו מנגנון hook של PreToolUse כמו Claude Code. Factory Droid משתמש בכלי `Task` לשיגור תת-סוכנים מקבילי. OpenClaw ו-Aider משתמשים בחילוץ עוקב (תמיכה בסוכנים מקביליים עדיין מוקדמת בפלטפורמות אלו). Trae משתמש בכלי Agent לשיגור תת-סוכנים מקבילי ו**אינו** תומך ב-hooks של `PreToolUse`, ולכן AGENTS.md הוא המנגנון התמידי.

`--platform agents` (כינוי `--platform skills`) מכוון למיקומי [Agent-Skills](https://github.com/anthropics/skills) הגנריים חוצי-המסגרות: ה-`~/.agents/skills/` הגלובלי למשתמש של המפרט (נקרא על ידי `npx skills` ומסגרות תואמות-מפרט) להתקנה גלובלית, ו-`./.agents/skills/` להתקנת פרויקט (`--project`). ה-`graphify install` החשוף נשאר חד-פלטפורמי (Claude Code) בכוונה: השתמשו בפלטפורמה הנקובה `agents` כשאתם רוצים שהמיומנות תהיה ניתנת לגילוי על ידי כל מסגרת שקוראת את `.agents/skills`.

ל-Pi אין hook של `PreToolUse`, ולכן `graphify pi guard install` רושם הרחבת Pi מקורית (באמצעות ה-`pi install <package directory>` של Pi עצמו) שמריצה את ה-`graphify hook-guard` המותקן לפני קריאות `read`, `grep`, `find` וקריאות `bash` בסגנון חיפוש של Pi. החלטות גרף טרי/מיושן ושלילת הקריאה המאונדקסת פעם-אחת-לכל-סשן של `GRAPHIFY_HOOK_STRICT=1` מגיעות מאותה מדיניות, כך ש-Pi תואם להתנהגות ה-hook של Claude Code; ההנחיה מגיעה כהודעת היגוי `<system-reminder source="graphify">`. הוא דורש Pi 0.58.4 או חדש יותר: גרסאות קודמות אפשרו להודעת היגוי לדלג על שאר אצווה של קריאות כלים מקבילות. החבילה נשלחת בתוך התקנת Graphify, לכן התקינו את Graphify באופן מתמשך (`uv tool install graphifyy` או `pipx install graphifyy`, לא `uvx`), הפעילו מחדש את Pi לאחר התקנה או שדרוג, והסירו אותו עם `graphify pi guard uninstall`. רק יעדי קבצים מקומיים נבדקים; ה-hook דורש את `graphify` בערך `PATH` מוחלט מחוץ לפרויקט, מוגבל לקריאה של שתי שניות, 256 KiB-נכנס/64 KiB-יוצא, ונכשל באופן פתוח. אותה חבילה נטענת גם ב-[Oh My Pi](https://github.com/can1357/oh-my-pi): `omp plugin install "$(graphify pi guard path)"`. הנתיב הרשום מכיל את גרסת Python ואת ה-venv, לכן הריצו שוב `graphify pi guard install` לאחר שינוי של אחד מהם, והסירו את הערך הישן עם `pi remove <old path>`.

> Codex משתמש ב-`$graphify` במקום `/graphify`.

</details>

<details>
<summary><b>תוספות אופציונליות</b> (התקינו רק את מה שאתם צריכים)</summary>

| תוספת | מה זה מוסיף | התקנה |
|---|---|---|
| `pdf` | חילוץ PDF | `uv tool install "graphifyy[pdf]"` |
| `office` | תמיכה ב-`.docx` וב-`.xlsx` | `uv tool install "graphifyy[office]"` |
| `google` | רינדור Google Sheets | `uv tool install "graphifyy[google]"` |
| `video` | תמלול וידאו/אודיו (faster-whisper + yt-dlp) | `uv tool install "graphifyy[video]"` |
| `mcp` | שרת stdio של MCP | `uv tool install "graphifyy[mcp]"` |
| `neo4j` | תמיכה בדחיפה ל-Neo4j | `uv tool install "graphifyy[neo4j]"` |
| `falkordb` | תמיכה בדחיפה ל-FalkorDB | `uv tool install "graphifyy[falkordb]"` |
| `svg` | ייצוא גרף SVG | `uv tool install "graphifyy[svg]"` |
| `leiden` | זיהוי קהילות Leiden (graspologic ב-Python < 3.13; שרת עורפי מקורי ב-3.13+) | `uv tool install "graphifyy[leiden]"` |
| `ollama` | הסקה מקומית של Ollama | `uv tool install "graphifyy[ollama]"` |
| `openai` | ממשקי API של OpenAI / תואמי-OpenAI | `uv tool install "graphifyy[openai]"` |
| `gemini` | API של Google Gemini | `uv tool install "graphifyy[gemini]"` |
| `anthropic` | API של Anthropic Claude (`--backend claude`, משתמש ב-`ANTHROPIC_API_KEY`) | `uv tool install "graphifyy[anthropic]"` |
| `bedrock` | AWS Bedrock (משתמש ב-IAM, ללא מפתח API) | `uv tool install "graphifyy[bedrock]"` |
| `azure` | Azure OpenAI Service (`--backend azure`, משתמש ב-`AZURE_OPENAI_API_KEY` + `AZURE_OPENAI_ENDPOINT`) | `uv tool install "graphifyy[openai]"` |
| `sql` | חילוץ סכמת SQL | `uv tool install "graphifyy[sql]"` |
| `postgres` | אינטרוספקציה חיה של PostgreSQL (`--postgres DSN`) | `uv tool install "graphifyy[postgres]"` |
| `dm` | חילוץ AST של BYOND DreamMaker `.dm`/`.dme` (עשוי לדרוש מהדר C + `python3-dev` אם אין wheel שתואם לפלטפורמה שלכם) | `uv tool install "graphifyy[dm]"` |
| `terraform` | חילוץ AST של Terraform / HCL `.tf`/`.tfvars`/`.hcl` | `uv tool install "graphifyy[terraform]"` |
| `pascal` | חילוץ AST של Pascal / Delphi `.pas`/`.dpr`/`.dpk`/`.inc` (קשתות `calls`/`inherits` מדויקות יותר; נסוג למחלץ regex בהיעדרו) | `uv tool install "graphifyy[pascal]"` |
| `ocaml` | חילוץ AST של OCaml `.ml`/`.mli` | `uv tool install "graphifyy[ocaml]"` |
| `commonlisp` | חילוץ AST של Common Lisp `.lisp`/`.cl`/`.lsp`/`.asd` | `uv tool install "graphifyy[commonlisp]"` |
| `robot` | חילוץ של Robot Framework `.robot`/`.resource` (מערכות, מקרי בדיקה, מילות מפתח, קשתות של קריאת מילות מפתח וייבוא resource/library) | `uv tool install "graphifyy[robot]"` |
| `chinese` | פילוח שאילתות בסינית (jieba) | `uv tool install "graphifyy[chinese]"` |
| `all` | כל מה שלמעלה | `uv tool install "graphifyy[all]"` |

</details>

---

## גרמו לעוזר שלכם להשתמש תמיד בגרף

הריצו זאת פעם אחת בפרויקט שלכם לאחר בניית גרף:

הריצו `graphify <platform> install` פעם אחת בפרויקט שלכם, לדוגמה `graphify claude install` או `graphify codex install` (או `graphify install --platform <name>`).

זה כותב קובץ תצורה קטן שאומר לעוזר שלכם להיוועץ בגרף הידע לשאלות על בסיס הקוד, ומעדיף שאילתות ממוקדות כמו `graphify query "<question>"` על פני קריאת הדוח המלא או ביצוע grep על קבצים גולמיים.

- **פלטפורמות hook** (Claude Code, Gemini CLI): hook נורה אוטומטית לפני קריאות כלים בסגנון חיפוש (וב-Claude Code, לפני קריאת קבצי מקור אחד-אחד באמצעות הכלים Read/Glob) ומכוון את העוזר שלכם לנתיב הגרף.
- **פלטפורמות קובץ-הנחיות** (Codex, OpenCode, Cursor, וכו'): קבצי הנחיות מתמשכים (`AGENTS.md`, `.cursor/rules/`, וכו') מספקים את אותה הנחיית תשאול-תחילה.

`GRAPH_REPORT.md` עדיין זמין לסקירת ארכיטקטורה רחבה.

אילו קבצים בדיוק כל פלטפורמה כותבת (ה-`CODEBUDDY.md` + hooks של `PreToolUse` של CodeBuddy, ה-`AGENTS.md` של Codex, תוסף ה-`.kilo` המקורי של Kilo, כלל ה-`alwaysApply` של Cursor, וכן הלאה) מכוסה ב-**[הגדרה תמידית](https://docs.graphify.com/guides/always-on)**.

כדי להסיר את graphify מכל הפלטפורמות בבת אחת: `graphify uninstall` (הוסיפו `--purge` כדי למחוק גם את `graphify-out/`). או השתמשו בפקודה הספציפית לפלטפורמה (לדוגמה `graphify claude uninstall`).

### מיומנויות CLI או הנחיות MCP?

ההנחיות המותקנות על ידי `graphify install` ואלו המסופקות עם חיבור MCP של Graphify מתארות דרכים שונות לתשאל גרף:

| הגדרה | הנחיה לשימוש | גישת תשאול |
|---|---|---|
| CLI מקומי ומיומנות עוזר מותקנת | הנחיות הפלטפורמה שנכתבו על ידי `graphify install` | הריצו `graphify query`, `graphify path`, ו-`graphify explain` מול הגרף המקומי (`graphify-out/` כברירת מחדל). |
| שרת MCP מחובר של Graphify | הנחיות החיבור והכלים המפורטים על ידי אותו שרת | קראו לכלי ה-MCP המפורטים מול הגרף שמוגש על ידי אותו חיבור. שמות הכלים והתיאורים מגיעים מהשרת. |

שתיהן מעודדות שאילתות גרף ממוקדות לפני חיפושי מקור רחבים. בחרו את ההנחיות שתואמות לכלים שהעוזר שלכם יכול לגשת אליהם בפועל; אף בלוק אינו קובע כלל קדימות אוניברסלי לקבצי ההנחיות של העוזר שלכם. אם אתם משתמשים בשתי האינטגרציות, זהו איזה גרף כל אחת מתשאלת ובחרו נתיב תשאול ראשי במקום להעתיק שני בלוקי הנחיות ללא תנאי ל-`AGENTS.md`.

`graphify install` מתקין את האינטגרציה המקומית של העוזר; הוא אינו יוצר חיבור MCP. לקוח MCP אינו צריך להריץ שאילתות CLI מקומיות כדי להשתמש בשרת המחובר שלו. שרת מתארח מקומית עדיין צריך התקנת Graphify וגרף משלו, בעוד שחיבור מתארח עשוי להגיש גרף שאינו קיים בספריית העבודה של הלקוח. אם הכלים הצפויים חסרים, בדקו את התקנת ה-CLI הרלוונטית או את חיבור ה-MCP במקום להתייחס להנחיות של ההגדרה האחרת כבנות-החלפה.

---

## מה יש בדוח

`GRAPH_REPORT.md` מסכם את צמתי העל, הקהילות, והנתיבים המרכזיים לסקירת ארכיטקטורה רחבה. איך הגרף נבנה ומה הוא מכיל: **[איך graphify עובד](https://docs.graphify.com/concepts/architecture)**.

---

## אילו קבצים הוא מטפל בהם: ~40 languages

graphify מנתח ~40 שפות תכנות מקומית עם tree-sitter AST, וממפה מסמכים, PDFs, תמונות, ואודיו/וידאו דרך מעבר סמנטי אופציונלי. רשימה מלאה: **[קלטים נתמכים](https://docs.graphify.com/concepts/supported-inputs)**.

---

## פקודות נפוצות

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

ראו את [תיעוד הפקודות המלא](#full-command-reference) למטה.

---

## התעלמות מקבצים

graphify מכבד את `.gitignore` ותומך בדפוסי `--exclude` וב-`.graphifyignore` של הפרויקט. פרטים: **[תצורה](https://docs.graphify.com/reference/configuration)**.


## תצורת פרויקט

צרו `.graphifyrc` בשורש הסריקה עבור הגדרות ששייכות לפרויקט ולא להרצה אחת. `key=value` אחד בכל שורה; שורות שמתחילות ב-`#` הן הערות.

**סיומות דו-משמעיות.** חלק מהסיומות מציינות שפות שונות בפרויקטים שונים: `.inc` הוא PHP ב-pfSense, Pascal בעץ Delphi, SQL או אסמבלי במקומות אחרים; `.h` הוא C או C++; `.m` הוא Objective-C או MATLAB. graphify חייב לבחור ברירת מחדל גלובלית אחת, וכשהוא בוחר לא נכון הקובץ אינו נכשל: הוא מנותח כשפה הלא נכונה ומניב קומץ צמתים מקריים, כך שהגרף נראה מאוכלס בעוד שהסמלים האמיתיים חסרים. הצהירו מה הסיומת מציינת במאגר שלכם:

```
# .graphifyrc
# A language name:
language.inc=php
# Or an extension graphify already knows:
language.tpl=.ts
# Baked into the git hooks (see Team setup):
viz_node_limit=0
```

ההצהרה זורמת דרך סיווג, בחירת מחלץ, דקדוק ופתרון, ייבואים, `graphify watch`, ומטמון ה-AST (קובץ שנותח מחדש תחת שפה אחרת לעולם לא עושה שימוש חוזר בערך הישן), ואותו `.graphifyrc` נקרא על ידי `extract`, `update`, ה-hooks, שרת ה-MCP, ומיומנות ה-`/graphify`. שגיאת הקלדה מדווחת פעם אחת ב-stderr והסריקה ממשיכה עם ברירות המחדל. איך הצהרות מתקשרות עם מטמון, בנייה מחדש מצטברת, ופתרון ייבוא: **[תצורה](https://docs.graphify.com/reference/configuration)**.

---

## הגדרת צוות

בצעו commit או שתפו את הגרף כך שכל הצוות שלכם מתשאל את אותו הקשר, וסקרו pull requests עם הקשר גרף. ראו **[שתפו הקשר עם הצוות שלכם](https://docs.graphify.com/guides/team-workflows)** ו-**[סקרו pull requests](https://docs.graphify.com/guides/pull-requests)**.

---

## שימוש ישיר בגרף

מעבר לעוזר ה-AI שלכם, תשאלו את `graph.json` ישירות מה-CLI עם `graphify query`, `graphify path`, ו-`graphify explain`. שם שתואם למספר צמתים נדחה עם רשימת המועמדים במקום לנחש. סקריפטים יכולים לקרוא את התוצאה מקוד היציאה: `0` תשובה, `3` שם דו-משמעי, `4` אין צומת תואם. ראו **[שאלו שאלות גרף טובות יותר](https://docs.graphify.com/guides/querying)** ואת **[תיעוד התשאול](https://docs.graphify.com/reference/query)**.

---

## משתני סביבה

שרתים עורפיים, מפתחות API, התנהגות hook, וכוונון נשלטים על ידי משתני סביבה. טבלה מלאה: **[תצורה](https://docs.graphify.com/reference/configuration)**.

---

## פרטיות

- **קבצי קוד**: מעובדים מקומית באמצעות tree-sitter. שום דבר לא עוזב את המכונה שלכם. קורפוס של קוד בלבד אינו דורש מפתח API: `graphify extract` רץ לגמרי לא מקוון. במאגר מעורב, הוסיפו `--code-only` כדי לאנדקס רק את הקוד ולדלג על המסמכים/PDFs/תמונות שאחרת היו דורשים LLM.
- **וידאו / אודיו**: מתומללים מקומית עם faster-whisper. שום דבר לא עוזב את המכונה שלכם.
- **מסמכים, PDFs, תמונות**: נשלחים לעוזר ה-AI שלכם לחילוץ סמנטי (באמצעות מיומנות ה-`/graphify`, בשימוש בכל מודל שסשן ה-IDE שלכם מריץ). `graphify extract` ללא ממשק דורש `GEMINI_API_KEY` / `GOOGLE_API_KEY` (Gemini), `MOONSHOT_API_KEY` (Kimi), `ANTHROPIC_API_KEY` (Claude), `OPENAI_API_KEY` (OpenAI), `DEEPSEEK_API_KEY` (DeepSeek), מופע Ollama פעיל (`OLLAMA_BASE_URL`), אישורי AWS דרך שרשרת הספקים הסטנדרטית (Bedrock, ללא צורך במפתח API, משתמש ב-IAM), או את הקובץ הבינארי של ה-CLI `claude` (Claude Code, ללא צורך במפתח API, משתמש במנוי Claude שלכם). הדגל `--dedup-llm` משתמש באותו מפתח.
- **מיקום נתונים**: `graphify extract` מזהה אוטומטית באיזה ספק להשתמש בהתבסס על איזה מפתח API מוגדר (עדיפות: Gemini → Kimi → Claude → OpenAI → DeepSeek → Azure → Bedrock → Ollama). עבור קוד עם דרישות מיקום נתונים, השתמשו ב-`--backend ollama` (מקומי לחלוטין) או העבירו דגל `--backend` מפורש. Kimi (`MOONSHOT_API_KEY`) מנתב לשרתי Moonshot AI בסין.
- **ללא טלמטריה**, ללא מעקב שימוש, ללא אנליטיקה.
- **רישום שאילתות**: כל קריאת `graphify query`, `graphify path`, `graphify explain`, וקריאת `query_graph` של MCP נרשמת ל-`~/.cache/graphify-queries.log` בפורמט JSON Lines (חותמת זמן, שאלה, קורפוס, צמתים שהוחזרו, משך). תגובות תת-גרף מלאות **אינן** נשמרות כברירת מחדל. הגדירו `GRAPHIFY_QUERY_LOG_DISABLE=1` כדי לבטל הסכמה, או `GRAPHIFY_QUERY_LOG=/dev/null` כדי להשתיק בלי להשבית את נתיב הקוד.

---

## פתרון תקלות

בעיות התקנה וחילוץ נפוצות והתיקונים שלהן: **[פתרון תקלות](https://docs.graphify.com/troubleshooting)**.

---

## תיעוד פקודות מלא

כל פקודה ודגל, עם דוגמאות: **[תיעוד CLI](https://docs.graphify.com/reference/overview)**.

---

## מידע נוסף

- [docs.graphify.com](https://docs.graphify.com): תיעוד מלא: מדריכים, תיעוד פקודות, ואינטגרציות
- [איך זה עובד](../how-it-works.md): צינור החילוץ, זיהוי קהילות, ניקוד ביטחון, מדדי ביצועים
- [ARCHITECTURE.md](../../ARCHITECTURE.md): פירוק מודולים, איך להוסיף שפה
- [אינטגרציות אופציונליות](../docker-mcp-sqlite.md): Docker MCP Toolkit + SQLite
- [The Memory Layer](https://safishamsi.gumroad.com/l/qetvlo): הספר על הרעיונות שמאחורי graphify, הארכיטקטורה מקצה לקצה

---

## Graphify Cloud

[**Graphify Cloud**](https://app.graphify.com/login) היא השכבה התמידית שנבנתה מעל graphify. במקום גרף שאתם בונים מחדש לפי דרישה לכל תיקייה, היא שומרת גרף חי אחד לאורך כל מחזור חיי פיתוח התוכנה שלכם:

- **80% פחות טוקנים**: זיכרון תמידי אומר שהסוכנים שלכם מפסיקים לקרוא ולהסביר מחדש את בסיס הקוד בכל סשן.
- **מונורפו ובין מאגרים**: גרף מחובר אחד על פני כל שירות ומאגר, לא גרף לכל תיקייה.
- **אימות פורמלי**: בדקו אינבריאנטים ארכיטקטוניים ותלותיים מול הגרף החי.
- **סקירת קוד עם מבט על של ה-SDLC שלכם**: ראו איך שינוי מתפשט על פני כל המערכת לפני שאתם ממזגים.
- **מחברי SDLC**: משכו פנימה את Sentry, Jira, ועוד, כך שתקריות, כרטיסים, וקוד חיים בגרף אחד.
- **תמידי**: מתעדכן ברציפות ברקע על פני קוד, מסמכים, ופגישות.

**[התחילו תקופת ניסיון חינם של 14 יום ב-app.graphify.com &rarr;](https://app.graphify.com/login)**

---

## תרומה

תרומות מתקבלות בברכה. ראו **[CONTRIBUTING.md](../../CONTRIBUTING.md)** עבור הגדרת הפיתוח, פקודות הבדיקה ושקילות ה-CI, תהליך העבודה של git, ומה הופך תרומה לחזקה (דוגמאות מעשיות ודיווחי באגים של חילוץ הם השימושיים ביותר). ארכיטקטורה ואיך להוסיף שפה: [ARCHITECTURE.md](../../ARCHITECTURE.md).

חדשים כאן? אמרו שלום ב-[Discord](https://discord.gg/XDnKVpzdXB) או ב-[GitHub Discussions](https://github.com/Graphify-Labs/graphify/discussions).

---

## תורמים

<a href="https://github.com/Graphify-Labs/graphify/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=Graphify-Labs/graphify" alt="graphify contributors" />
</a>

נוצר עם [contrib.rocks](https://contrib.rocks).

---

## תרגומים

ה-README זמין ב-32 שפות. השתמשו במחליף השפות בראש הקובץ הזה כדי לקרוא אותו בשלכם, או עיינו ב-[`docs/translations/`](./). כדי לשפר תרגום או להוסיף חדש, פתחו pull request מול הקובץ התואם שם.

---

## בנייה על graphify

בונים משהו באקוסיסטם של graphify? זה מעודד. אם הפרויקט שלכם משתמש ב-"graphify" בשם שלו (לדוגמה `graphify-dashboard` או `graphify-action`), אנא הוסיפו הערה קצרה ל-README שלכם שמבהירה שהוא נבנה על ידי הקהילה ואינו קשור או מאושר על ידי Graphify Labs. "graphify" והלוגו של graphify הם סימנים של Graphify Labs; אנא אל תשתמשו בהם באופן שמרמז על מעמד רשמי.

---

## קהילה וקישורים

<p align="center">
  <a href="https://graphify.com"><img src="https://img.shields.io/badge/Website-graphify.com-4c1?style=flat&logo=googlechrome&logoColor=white" alt="Website"/></a>
  <a href="https://discord.gg/XDnKVpzdXB"><img src="https://img.shields.io/badge/Discord-Join-5865F2?style=flat&logo=discord&logoColor=white" alt="Discord"/></a>
  <a href="https://x.com/graphify"><img src="https://img.shields.io/badge/X-graphify-000000?logo=x&logoColor=white" alt="X"/></a>
  <a href="https://www.youtube.com/@graphifylabs"><img src="https://img.shields.io/badge/YouTube-Graphify%20Labs-FF0000?style=flat&logo=youtube&logoColor=white" alt="YouTube"/></a>
  <a href="https://github.com/sponsors/safishamsi"><img src="https://img.shields.io/badge/sponsor-safishamsi-ea4aaa?logo=github-sponsors" alt="Sponsor"/></a>
  <a href="https://safishamsi.gumroad.com/l/qetvlo"><img src="https://img.shields.io/badge/Book-The%20Memory%20Layer-2ea44f?style=flat&logo=gitbook&logoColor=white" alt="The Memory Layer"/></a>
</p>
