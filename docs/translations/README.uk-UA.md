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
  <b>Скоротіть витрати токенів агентів на 80%.</b> Graphify Cloud - це завжди активна памʼять, яка керує вашими агентами, підтримує високу якість коду та доводить коректність за допомогою формальної верифікації. <a href="https://app.graphify.com/login"><b>Почніть безкоштовну 14-денну пробну версію &rarr;</b></a>
</p>

Введіть `/graphify` у вашому AI-асистенті для кодування, і він відобразить увесь ваш проєкт (код, документацію, PDF, зображення, відео) у **граф знань**, який ви можете **запитувати замість того, щоб грепати** файли.

- **Карти коду безкоштовно, повністю локально.** Код розбирається за допомогою tree-sitter AST: детерміновано, без LLM, нічого не залишає вашу машину. (Документи, PDF, зображення та відео використовують модель вашого асистента або налаштований ключ API для семантичного проходу.)
- **Кожне ребро пояснюється.** Кожне зʼєднання позначається `EXTRACTED` (явно в джерелі) або `INFERRED` (визначено graphify), тож ви можете відрізнити те, що було прочитано безпосередньо, від того, що було виведено.
- **Це не векторний індекс.** Жодних ембедингів, жодного векторного сховища: справжній граф, яким ви проходите. Поставте питання, простежте шлях між двома речами або поясніть одне поняття.

> [!NOTE]
> **Хочете, щоб це було завжди активним?** [Graphify Cloud](https://app.graphify.com/login) підтримує граф живим упродовж усього вашого SDLC: підтримка монорепозиторіїв і крос-репозиторіїв, формальна верифікація та код-рев'ю з висоти пташиного польоту над вашим SDLC, а також конектори для Sentry, Jira та інших, тож інциденти й тикети перебувають у тому самому графі, що й ваш код. **[Почніть безкоштовну 14-денну пробну версію на app.graphify.com](https://app.graphify.com/login)**.

<p align="center">
  <img src="https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/graph-hero.png" alt="graphify's interactive graph.html showing the FastAPI codebase as a force-directed knowledge graph with a legend of detected communities" width="900">
</p>
<p align="center">
  <em>Кодова база FastAPI, відображена graphify. Кожен вузол - це поняття, кольори - це виявлені спільноти, і все це клікабельне у graph.html.</em>
</p>

**Початок роботи** (30 секунд). Потрібні Python 3.10+ та uv (або pipx):

```bash
uv tool install graphifyy      # install the CLI (or: pipx install graphifyy)
graphify install               # detects your assistant and registers the skill
```

Потім у вашому AI-асистенті:

```
/graphify .
```

Ось і все. Ви отримуєте **три файли**:

```
graphify-out/
├── graph.html       open in any browser: click nodes, filter, search
├── GRAPH_REPORT.md  the highlights: key concepts, surprising connections, suggested questions
└── graph.json       the full graph: query it anytime without re-reading your files
```

Збережений граф містить `graph.schema_version`, щоб інтеграції могли виявляти
несумісні зміни формату, а також `graph.graphify_version`, що ідентифікує
випуск Graphify, який його створив.

**Одне встановлення, будь-який асистент, будь-яка ОС.** Claude Code, Cursor, Codex, Gemini CLI, GitHub Copilot та ще 20+, на macOS, Linux і Windows: [оберіть свою платформу](#install).

---

## Подивіться в дії

<p align="center">
  <img src="https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/demo-path.svg" alt="graphify path query: a terminal asks for the shortest path between FastAPI and ModelField, and the answer lights up hop by hop across the knowledge graph" width="900">
</p>

Щойно граф побудовано, ви запитуєте його замість читання файлів. Реальний вивід, graphify запущено на кодовій базі FastAPI, показаній вище:

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

Кожне ребро несе **позначку впевненості** (`EXTRACTED` = явно в джерелі, `INFERRED` = виведено шляхом розвʼязання), тож ви можете відрізнити те, що було прочитано безпосередньо, від того, що було виведено. `graphify query "<question>"` повертає обмежений підграф для запитання звичайною мовою, а `graphify path A B` простежує, як зʼєднуються будь-які дві речі.

---

## Що це робить

Що ви отримуєте з коробки:

| Можливість | Що ви отримуєте |
|---|---|
| **Божественні вузли** | Найбільш звʼязані поняття, тож ви бачите, через що все проходить |
| **Спільноти** | Граф, розділений на підсистеми (Leiden), з мітками без LLM |
| **Міжфайлові звʼязки** | `calls` / `imports` / `inherits` / `mixes_in`, розвʼязані між ~40 мовами через tree-sitter AST |
| **Запит, шлях, пояснення** | Поставте питання, простежте шлях між двома речами або поясніть одне поняття, усе проти `graph.json` |
| **Обґрунтування + посилання на документи** | Коментарі `# NOTE:` / `# WHY:` та цитати ADR/RFC стають повноцінними вузлами, повʼязаними з кодом |
| **Поза межами коду** | Документи, PDF, зображення та відео/аудіо - усе відображається в той самий граф |
| **Локальний пріоритет** | Код розбирається локально за допомогою tree-sitter (без LLM, нічого не залишає вашу машину); лише семантичний прохід над документами/медіа звертається до бекенду, і тільки якщо ви його налаштуєте |

> [!TIP]
> Запускаєте це на багатьох репозиторіях чи монорепозиторії? [Graphify Cloud](https://app.graphify.com/login) робить це безперервно та скорочує витрати токенів агентів на 80%, з крос-репозиторними звʼязками, код-рев'ю на рівні всього SDLC, формальною верифікацією та конекторами Sentry/Jira. [Почніть безкоштовну 14-денну пробну версію &rarr;](https://app.graphify.com/login)

---

## Benchmarks: 0.497 recall@10, 0 LLM credits

| Benchmark | Metric | graphify | Field |
|---|---|---|---|
| LOCOMO (n=300) | recall@10 | **0.497** | mem0 0.048, supermemory 0.149 |
| LOCOMO (n=300) | QA accuracy | 45.3% | supermemory 49.7%, mem0 27.3% |
| LongMemEval-S (n=50) | QA accuracy | **76%** | tied with dense RAG |
| ERPNext cross-tool (n=6) | key-fact coverage | **82.0%** | grep/read baseline 70.8% |
| Graph build | LLM credits | **0** | per-token for most systems |

Кожна система працювала на тому самому харнесі з тією самою моделлю та бюджетами, оцінена суддею, сліпо перевіреним проти другого судді (90.6% згоди, каппа Коена 0.81). Повні таблиці по кожній системі, результат з інтелектуального аналізу коду та команди для відтворення: **[BENCHMARKS.md](../../BENCHMARKS.md)**.

---

## Документація

Повні посібники та довідник розміщено на **[docs.graphify.com](https://docs.graphify.com)**:

- **[Швидкий старт](https://docs.graphify.com/quickstart)**: побудуйте свій перший граф
- **[Довідник CLI](https://docs.graphify.com/reference/overview)**: кожна команда та прапорець
- **[Ставте кращі запитання до графа](https://docs.graphify.com/guides/querying)**: шаблони запитів
- **[Конфігурація](https://docs.graphify.com/reference/configuration)**: змінні середовища та налаштування
- **[Підтримувані вхідні дані](https://docs.graphify.com/concepts/supported-inputs)**: мови та типи файлів
- **[Командні робочі процеси](https://docs.graphify.com/guides/team-workflows)** та **[рев'ю PR](https://docs.graphify.com/guides/pull-requests)**
- **[Усунення несправностей](https://docs.graphify.com/troubleshooting)** та **[Як це працює](https://docs.graphify.com/concepts/architecture)**

---

## Передумови

| Вимога | Мінімум | Перевірка | Встановлення |
|---|---|---|---|
| Python | 3.10+ | `python --version` | [python.org](https://www.python.org/downloads/) |
| uv *(рекомендовано)* | будь-яка | `uv --version` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| pipx *(альтернатива)* | будь-яка | `pipx --version` | `pip install pipx` |

**Швидке встановлення на macOS (Homebrew):**
```bash
brew install python@3.12 uv
```

**Швидке встановлення на Windows:**
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
> **Офіційний пакет:** Пакет на PyPI - `graphifyy` (подвійна y). Інші пакети `graphify*` на PyPI не є афілійованими. Команда CLI досі `graphify`.

Офіційний репозиторій джерельного коду - [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify).

Швидкий старт із двох команд наведено на початку цього README. Цей розділ охоплює методи встановлення, встановлення в межах проєкту та кожну підтримувану платформу.

**Методи встановлення** (оберіть один):

```bash
uv tool install graphifyy   # recommended, isolated env (if 'graphify' isn't found after, run: uv tool update-shell)
pipx install graphifyy      # alternative
pip install graphifyy       # may need PATH setup, see Troubleshooting below
```

Потім один раз запустіть `graphify install`. Він визначає, якого асистента ви використовуєте, і реєструє скіл, тож немає потреби в налаштуванні для кожного асистента. Відкрийте свого AI-асистента та введіть `/graphify .`

Щоб встановити скіл асистента в поточний репозиторій замість вашого
профілю користувача, додайте `--project`:

```bash
graphify install --project
graphify install --project --platform codex
```

Встановлення в межах проєкту записуються в поточний каталог, наприклад
`.claude/skills/graphify/SKILL.md` або `.agents/skills/graphify/SKILL.md` (плюс
sidecar `references/`, який скіл завантажує на вимогу), і
виводять підказку `git add` для файлів, які можна закомітити.
Команди для конкретних платформ, що підтримують встановлення в межах проєкту, приймають той самий прапорець,
наприклад `graphify claude install --project` або `graphify codex install --project`.

> [!TIP]
> Стикаєтеся з `command not found`, проблемою `pip` на Mac/Windows, екрануванням у PowerShell, використанням `uvx`, особливостями PATH у git-хуках або суворим режимом? Дивіться **[Встановлення](https://docs.graphify.com/installation)** та **[Усунення несправностей](https://docs.graphify.com/troubleshooting)**.

<details>
<summary><b>Оберіть свою платформу</b> (20+ асистентів, натисніть, щоб розгорнути)</summary>

| Платформа | Команда встановлення |
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

Користувачам Codex також потрібно `multi_agent = true` у секції `[features]` в `~/.codex/config.toml` для паралельного вилучення. CodeBuddy використовує той самий механізм інструмента Agent та хука PreToolUse, що й Claude Code. Factory Droid використовує інструмент `Task` для паралельної диспетчеризації субагентів. OpenClaw та Aider використовують послідовне вилучення (підтримка паралельних агентів на цих платформах ще на ранній стадії). Trae використовує інструмент Agent для паралельної диспетчеризації субагентів і **не** підтримує хуки `PreToolUse`, тож AGENTS.md є завжди активним механізмом.

`--platform agents` (alias `--platform skills`) націлюється на загальні крос-фреймворкові розташування [Agent-Skills](https://github.com/anthropics/skills): визначене специфікацією глобальне для користувача `~/.agents/skills/` (читається `npx skills` та фреймворками, сумісними зі специфікацією) для глобального встановлення, та `./.agents/skills/` для встановлення в межах проєкту (`--project`). Голий `graphify install` залишається одноплатформним (Claude Code) за задумом: використовуйте іменовану платформу `agents`, коли хочете, щоб скіл був виявним будь-яким фреймворком, що читає `.agents/skills`.

Pi не має хука `PreToolUse`, тож `graphify pi guard install` реєструє нативне розширення Pi (через власний `pi install <package directory>` від Pi), яке запускає встановлений `graphify hook-guard` перед викликами `read`, `grep`, `find` та пошуковими викликами `bash` від Pi. Рішення про свіжий/застарілий граф та заборона читання проіндексованого раз на сесію `GRAPHIFY_HOOK_STRICT=1` походять з тієї самої політики, тож Pi відповідає поведінці хуків Claude Code; настанови надходять як steering-повідомлення `<system-reminder source="graphify">`. Потрібен Pi 0.58.4 або новіший: раніші версії дозволяли steering-повідомленню пропускати решту пакета паралельних викликів інструментів. Пакет постачається всередині встановлення Graphify, тож встановлюйте Graphify стало (`uv tool install graphifyy` or `pipx install graphifyy`, not `uvx`), перезапустіть Pi після встановлення чи оновлення та видаліть його за допомогою `graphify pi guard uninstall`. Перевіряються лише локальні файлові цілі; хуку потрібен `graphify` на абсолютному записі `PATH` поза межами проєкту, він обмежений викликом на дві секунди, 256 KiB-вхід/64 KiB-вихід та відмовляє відкрито. Той самий пакет також завантажується в [Oh My Pi](https://github.com/can1357/oh-my-pi): `omp plugin install "$(graphify pi guard path)"`. Зареєстрований шлях містить версію Python та venv, тож повторно запустіть `graphify pi guard install` після зміни будь-чого з них і видаліть старий запис за допомогою `pi remove <old path>`.

> Codex використовує `$graphify` замість `/graphify`.

</details>

<details>
<summary><b>Додаткові розширення</b> (встановлюйте лише те, що вам потрібно)</summary>

| Розширення | Що воно додає | Встановлення |
|---|---|---|
| `pdf` | Вилучення PDF | `uv tool install "graphifyy[pdf]"` |
| `office` | Підтримка `.docx` та `.xlsx` | `uv tool install "graphifyy[office]"` |
| `google` | Рендеринг Google Sheets | `uv tool install "graphifyy[google]"` |
| `video` | Транскрипція відео/аудіо (faster-whisper + yt-dlp) | `uv tool install "graphifyy[video]"` |
| `mcp` | MCP stdio-сервер | `uv tool install "graphifyy[mcp]"` |
| `neo4j` | Підтримка push у Neo4j | `uv tool install "graphifyy[neo4j]"` |
| `falkordb` | Підтримка push у FalkorDB | `uv tool install "graphifyy[falkordb]"` |
| `svg` | Експорт графа в SVG | `uv tool install "graphifyy[svg]"` |
| `leiden` | Виявлення спільнот Leiden (graspologic на Python < 3.13; нативний бекенд на 3.13+) | `uv tool install "graphifyy[leiden]"` |
| `ollama` | Локальний інференс Ollama | `uv tool install "graphifyy[ollama]"` |
| `openai` | OpenAI / OpenAI-сумісні API | `uv tool install "graphifyy[openai]"` |
| `gemini` | API Google Gemini | `uv tool install "graphifyy[gemini]"` |
| `anthropic` | API Anthropic Claude (`--backend claude`, uses `ANTHROPIC_API_KEY`) | `uv tool install "graphifyy[anthropic]"` |
| `bedrock` | AWS Bedrock (uses IAM, no API key) | `uv tool install "graphifyy[bedrock]"` |
| `azure` | Azure OpenAI Service (`--backend azure`, uses `AZURE_OPENAI_API_KEY` + `AZURE_OPENAI_ENDPOINT`) | `uv tool install "graphifyy[openai]"` |
| `sql` | Вилучення схеми SQL | `uv tool install "graphifyy[sql]"` |
| `postgres` | Жива інтроспекція PostgreSQL (`--postgres DSN`) | `uv tool install "graphifyy[postgres]"` |
| `dm` | Вилучення AST BYOND DreamMaker `.dm`/`.dme` (може знадобитися компілятор C + `python3-dev`, якщо немає підхожого wheel для вашої платформи) | `uv tool install "graphifyy[dm]"` |
| `terraform` | Вилучення AST Terraform / HCL `.tf`/`.tfvars`/`.hcl` | `uv tool install "graphifyy[terraform]"` |
| `pascal` | Вилучення AST Pascal / Delphi `.pas`/`.dpr`/`.dpk`/`.inc` (точніші ребра `calls`/`inherits`; повертається до regex-екстрактора за відсутності) | `uv tool install "graphifyy[pascal]"` |
| `ocaml` | Вилучення AST OCaml `.ml`/`.mli` | `uv tool install "graphifyy[ocaml]"` |
| `commonlisp` | Вилучення AST Common Lisp `.lisp`/`.cl`/`.lsp`/`.asd` | `uv tool install "graphifyy[commonlisp]"` |
| `robot` | Вилучення Robot Framework `.robot`/`.resource` (набори, тест-кейси, ключові слова, ребра виклику ключових слів та імпорту ресурсів/бібліотек) | `uv tool install "graphifyy[robot]"` |
| `chinese` | Сегментація запитів китайською (jieba) | `uv tool install "graphifyy[chinese]"` |
| `all` | Усе вищеперелічене | `uv tool install "graphifyy[all]"` |

</details>

---

## Зробіть так, щоб ваш асистент завжди використовував граф

Запустіть це один раз у вашому проєкті після побудови графа:

Запустіть `graphify <platform> install` один раз у вашому проєкті, наприклад `graphify claude install` або `graphify codex install` (or `graphify install --platform <name>`).

Це записує невеликий файл конфігурації, який повідомляє вашому асистенту звертатися до графа знань для запитань щодо кодової бази, віддаючи перевагу обмеженим запитам на кшталт `graphify query "<question>"` над читанням повного звіту чи грепанням сирих файлів.

- **Платформи з хуками** (Claude Code, Gemini CLI): хук спрацьовує автоматично перед пошуковими викликами інструментів (і, на Claude Code, перед читанням джерельних файлів по одному через інструменти Read/Glob) та підштовхує вашого асистента до шляху графа.
- **Платформи з файлами інструкцій** (Codex, OpenCode, Cursor тощо): постійні файли інструкцій (`AGENTS.md`, `.cursor/rules/` тощо) надають ту саму настанову "спочатку запит".

`GRAPH_REPORT.md` досі доступний для широкого огляду архітектури.

Які саме файли записує кожна платформа (CodeBuddy's `CODEBUDDY.md` + `PreToolUse` hooks, Codex's `AGENTS.md`, нативний плагін Kilo `.kilo`, правило Cursor `alwaysApply` тощо) описано в **[Always-on setup](https://docs.graphify.com/guides/always-on)**.

Щоб видалити graphify з усіх платформ одразу: `graphify uninstall` (додайте `--purge`, щоб також видалити `graphify-out/`). Або використайте команду для конкретної платформи (наприклад, `graphify claude uninstall`).

### Скіли CLI чи інструкції MCP?

Інструкції, встановлені `graphify install`, та ті, що постачаються зі зʼєднанням Graphify MCP, описують різні способи запиту графа:

| Налаштування | Настанова до використання | Доступ до запитів |
|---|---|---|
| Локальний CLI та встановлений скіл асистента | Інструкції платформи, записані `graphify install` | Запустіть `graphify query`, `graphify path` та `graphify explain` проти локального графа (`graphify-out/` by default). |
| Підключений сервер Graphify MCP | Інструкції зʼєднання та інструменти, перелічені тим сервером | Викликайте перелічені інструменти MCP проти графа, що обслуговується цим зʼєднанням. Назви та описи інструментів походять від сервера. |

Обидва заохочують обмежені запити графа перед широкими пошуками в джерелах. Оберіть інструкції, що відповідають інструментам, до яких ваш асистент дійсно має доступ; жоден блок не встановлює універсального правила пріоритету для файлів інструкцій вашого асистента. Якщо ви використовуєте обидві інтеграції, визначте, який граф запитує кожна, та оберіть основний шлях запитів замість копіювання двох безумовних блоків інструкцій у `AGENTS.md`.

`graphify install` встановлює локальну інтеграцію асистента; він не встановлює зʼєднання MCP. Клієнту MCP не потрібно запускати локальні запити CLI, щоб використовувати свій підключений сервер. Локально розміщеному серверу досі потрібні власне встановлення Graphify та граф, тоді як розміщене зʼєднання може обслуговувати граф, якого немає в робочому каталозі клієнта. Якщо очікувані інструменти відсутні, перевірте відповідне встановлення CLI чи зʼєднання MCP, а не ставтеся до інструкцій іншого налаштування як до взаємозамінних.

---

## Що є у звіті

`GRAPH_REPORT.md` узагальнює божественні вузли, спільноти та ключові шляхи для широкого огляду архітектури. Як будується граф і що він містить: **[Як працює graphify](https://docs.graphify.com/concepts/architecture)**.

---

## Які файли він обробляє: ~40 languages

graphify розбирає ~40 мов програмування локально за допомогою tree-sitter AST та відображає документи, PDF, зображення й аудіо/відео через опціональний семантичний прохід. Повний список: **[Підтримувані вхідні дані](https://docs.graphify.com/concepts/supported-inputs)**.

---

## Поширені команди

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

Дивіться [повний довідник команд](#full-command-reference) нижче.

---

## Ігнорування файлів

graphify шанує `.gitignore` та підтримує шаблони `--exclude` і проєктний `.graphifyignore`. Деталі: **[Конфігурація](https://docs.graphify.com/reference/configuration)**.


## Конфігурація проєкту

Створіть `.graphifyrc` у корені сканування для налаштувань, що належать проєкту, а не одному запуску. Один `key=value` на рядок; рядки, що починаються з `#`, є коментарями.

**Неоднозначні розширення.** Деякі розширення означають різні мови в різних проєктах: `.inc` - це PHP на pfSense, Pascal у дереві Delphi, SQL або асемблер в інших місцях; `.h` - це C або C++; `.m` - це Objective-C або MATLAB. graphify має обрати один глобальний default, і коли він обирає неправильно, файл не зазнає збою: він розбирається як неправильна мова та дає жменю випадкових вузлів, тож граф виглядає заповненим, тоді як справжні символи відсутні. Оголосіть, що означає розширення у вашому репозиторії:

```
# .graphifyrc
# A language name:
language.inc=php
# Or an extension graphify already knows:
language.tpl=.ts
# Baked into the git hooks (see Team setup):
viz_node_limit=0
```

Оголошення проходить через класифікацію, вибір екстрактора, граматику та розвʼязання, імпорти, `graphify watch` та кеш AST (файл, повторно розібраний під іншою мовою, ніколи не перевикористовує старий запис), і той самий `.graphifyrc` читається `extract`, `update`, хуками, сервером MCP та скілом `/graphify`. Про помилку друку повідомляється один раз у stderr, і сканування продовжується з defaults. Як оголошення взаємодіють з кешуванням, інкрементними перебудовами та розвʼязанням імпортів: **[Конфігурація](https://docs.graphify.com/reference/configuration)**.

---

## Налаштування для команди

Закомітьте або поділіться графом, щоб уся ваша команда запитувала той самий контекст, та робіть рев'ю pull-запитів з контекстом графа. Дивіться **[Поділіться контекстом зі своєю командою](https://docs.graphify.com/guides/team-workflows)** та **[Рев'ю pull-запитів](https://docs.graphify.com/guides/pull-requests)**.

---

## Використання графа напряму

Окрім вашого AI-асистента, запитуйте `graph.json` прямо з CLI за допомогою `graphify query`, `graphify path` та `graphify explain`. Назва, що збігається з кількома вузлами, відхиляється з переліченими кандидатами, а не вгадується. Скрипти можуть прочитати результат з коду виходу: `0` - відповідь, `3` - неоднозначна назва, `4` - немає відповідного вузла. Дивіться **[Ставте кращі запитання до графа](https://docs.graphify.com/guides/querying)** та **[довідник запитів](https://docs.graphify.com/reference/query)**.

---

## Змінні середовища

Бекенди, ключі API, поведінка хуків та налаштування керуються змінними середовища. Повна таблиця: **[Конфігурація](https://docs.graphify.com/reference/configuration)**.

---

## Приватність

- **Файли коду**: обробляються локально через tree-sitter. Нічого не залишає вашу машину. Корпус лише з коду не потребує ключа API: `graphify extract` працює повністю офлайн. На змішаному репозиторії додайте `--code-only`, щоб проіндексувати лише код і пропустити документи/PDF/зображення, яким інакше знадобився б LLM.
- **Відео / аудіо**: транскрибуються локально за допомогою faster-whisper. Нічого не залишає вашу машину.
- **Документи, PDF, зображення**: надсилаються вашому AI-асистенту для семантичного вилучення (через скіл `/graphify`, використовуючи будь-яку модель, що працює у вашій IDE-сесії). Безголовий `graphify extract` потребує `GEMINI_API_KEY` / `GOOGLE_API_KEY` (Gemini), `MOONSHOT_API_KEY` (Kimi), `ANTHROPIC_API_KEY` (Claude), `OPENAI_API_KEY` (OpenAI), `DEEPSEEK_API_KEY` (DeepSeek), запущеного екземпляра Ollama (`OLLAMA_BASE_URL`), облікових даних AWS через стандартний ланцюжок провайдерів (Bedrock - no API key needed, uses IAM) або бінарника `claude` CLI (Claude Code - no API key needed, uses your Claude subscription). Прапорець `--dedup-llm` використовує той самий ключ.
- **Резидентність даних**: `graphify extract` автоматично визначає, якого провайдера використовувати, за тим, який ключ API встановлено (priority: Gemini → Kimi → Claude → OpenAI → DeepSeek → Azure → Bedrock → Ollama). Для коду з вимогами до резидентності даних використовуйте `--backend ollama` (повністю локально) або передайте явний прапорець `--backend`. Kimi (`MOONSHOT_API_KEY`) маршрутизує на сервери Moonshot AI в Китаї.
- **Жодної телеметрії**, жодного відстеження використання, жодної аналітики.
- **Логування запитів**: кожен виклик `graphify query`, `graphify path`, `graphify explain` та MCP `query_graph` логується у `~/.cache/graphify-queries.log` у форматі JSON Lines (мітка часу, запитання, корпус, повернуті вузли, тривалість). Повні відповіді підграфа **не** зберігаються за замовчуванням. Встановіть `GRAPHIFY_QUERY_LOG_DISABLE=1`, щоб відмовитися, або `GRAPHIFY_QUERY_LOG=/dev/null`, щоб вимкнути без відключення шляху коду.

---

## Усунення несправностей

Поширені проблеми встановлення та вилучення та їх виправлення: **[Усунення несправностей](https://docs.graphify.com/troubleshooting)**.

---

## Повний довідник команд

Кожна команда та прапорець, з прикладами: **[Довідник CLI](https://docs.graphify.com/reference/overview)**.

---

## Дізнайтеся більше

- [docs.graphify.com](https://docs.graphify.com): повна документація: посібники, довідник команд та інтеграції
- [Як це працює](../how-it-works.md): конвеєр вилучення, виявлення спільнот, оцінка впевненості, бенчмарки
- [ARCHITECTURE.md](../../ARCHITECTURE.md): розбивка модулів, як додати мову
- [Опціональні інтеграції](../docker-mcp-sqlite.md): Docker MCP Toolkit + SQLite
- [The Memory Layer](https://safishamsi.gumroad.com/l/qetvlo): книга про ідеї, що лежать в основі graphify, архітектура від початку до кінця

---

## Graphify Cloud

[**Graphify Cloud**](https://app.graphify.com/login) - це завжди активний рівень, побудований поверх graphify. Замість графа, який ви перебудовуєте на вимогу для кожної теки, він підтримує один живий граф упродовж усього вашого життєвого циклу розробки ПЗ:

- **На 80% менше токенів**: завжди активна памʼять означає, що ваші агенти припиняють повторно читати та повторно пояснювати кодову базу щосесії.
- **Монорепозиторій та крос-репозиторій**: один звʼязаний граф на всі сервіси та репозиторії, а не граф на теку.
- **Формальна верифікація**: перевіряйте архітектурні та залежнісні інваріанти проти живого графа.
- **Код-рев'ю з висоти пташиного польоту над вашим SDLC**: побачте, як зміна розходиться по всій системі, перш ніж ви зробите merge.
- **Конектори SDLC**: підтягуйте Sentry, Jira та інше, тож інциденти, тикети та код живуть в одному графі.
- **Завжди активний**: оновлюється безперервно у фоновому режимі по коду, документах та зустрічах.

**[Почніть безкоштовну 14-денну пробну версію на app.graphify.com &rarr;](https://app.graphify.com/login)**

---

## Внесок

Внески вітаються. Дивіться **[CONTRIBUTING.md](../../CONTRIBUTING.md)** для налаштування розробки, команд тестування та відповідності CI, git-процесу та того, що робить внесок сильним (опрацьовані приклади та звіти про баги вилучення найкорисніші). Архітектура та як додати мову: [ARCHITECTURE.md](../../ARCHITECTURE.md).

Новачок тут? Привітайтеся в [Discord](https://discord.gg/XDnKVpzdXB) або в [GitHub Discussions](https://github.com/Graphify-Labs/graphify/discussions).

---

## Контриб'ютори

<a href="https://github.com/Graphify-Labs/graphify/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=Graphify-Labs/graphify" alt="graphify contributors" />
</a>

Зроблено за допомогою [contrib.rocks](https://contrib.rocks).

---

## Переклади

README доступний 32 мовами. Використовуйте перемикач мов угорі цього файлу, щоб прочитати його своєю, або перегляньте [`docs/translations/`](./). Щоб покращити переклад або додати новий, відкрийте pull-запит проти відповідного файлу там.

---

## Побудова на graphify

Будуєте щось в екосистемі graphify? Це заохочується. Якщо ваш проєкт використовує "graphify" у своїй назві (наприклад, `graphify-dashboard` or `graphify-action`), будь ласка, додайте коротку примітку до свого README, що розʼяснює, що це створено спільнотою та не є афілійованим із Graphify Labs чи схваленим ним. "graphify" та логотип graphify є марками Graphify Labs; будь ласка, не використовуйте їх у спосіб, що передбачає офіційний статус.

---

## Спільнота та посилання

<p align="center">
  <a href="https://graphify.com"><img src="https://img.shields.io/badge/Website-graphify.com-4c1?style=flat&logo=googlechrome&logoColor=white" alt="Website"/></a>
  <a href="https://discord.gg/XDnKVpzdXB"><img src="https://img.shields.io/badge/Discord-Join-5865F2?style=flat&logo=discord&logoColor=white" alt="Discord"/></a>
  <a href="https://x.com/graphify"><img src="https://img.shields.io/badge/X-graphify-000000?logo=x&logoColor=white" alt="X"/></a>
  <a href="https://www.youtube.com/@graphifylabs"><img src="https://img.shields.io/badge/YouTube-Graphify%20Labs-FF0000?style=flat&logo=youtube&logoColor=white" alt="YouTube"/></a>
  <a href="https://github.com/sponsors/safishamsi"><img src="https://img.shields.io/badge/sponsor-safishamsi-ea4aaa?logo=github-sponsors" alt="Sponsor"/></a>
  <a href="https://safishamsi.gumroad.com/l/qetvlo"><img src="https://img.shields.io/badge/Book-The%20Memory%20Layer-2ea44f?style=flat&logo=gitbook&logoColor=white" alt="The Memory Layer"/></a>
</p>
