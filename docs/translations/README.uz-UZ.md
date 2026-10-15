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
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue" alt="License: Apache-2.0"/></a>
  <a href="https://pepy.tech/project/graphifyy"><img src="https://img.shields.io/pepy/dt/graphifyy?color=blue&label=downloads" alt="Downloads"/></a>
  <a href="https://docs.graphify.com"><img src="https://img.shields.io/badge/Docs-docs.graphify.com-0b7285?style=flat&logo=readthedocs&logoColor=white" alt="Docs"/></a>
  <a href="https://app.graphify.com/login"><img src="https://img.shields.io/badge/Graphify%20Cloud-app.graphify.com-118d4f?style=flat&logoColor=white" alt="Graphify Cloud"/></a>
  <a href="https://discord.gg/XDnKVpzdXB"><img src="https://img.shields.io/badge/Discord-Join-5865F2?style=flat&logo=discord&logoColor=white" alt="Discord"/></a>
  <a href="https://www.youtube.com/@graphifylabs"><img src="https://img.shields.io/badge/YouTube-Graphify%20Labs-FF0000?style=flat&logo=youtube&logoColor=white" alt="YouTube"/></a>
  <a href="https://www.linkedin.com/company/graphify-labs"><img src="https://img.shields.io/badge/LinkedIn-Graphify%20Labs-0077B5?logo=linkedin" alt="LinkedIn"/></a>
  <a href="https://www.ycombinator.com/companies/graphify-labs"><img src="https://img.shields.io/badge/Y%20Combinator-S26-F0652F?style=flat&logo=ycombinator&logoColor=white" alt="YC S26"/></a>
</p>

<p align="center">
  <b>Agent token sarfini 80% ga qisqartiring.</b> Graphify Cloud sizning agentlaringizni boshqaradigan, kod sifatini yuqori saqlaydigan va to'g'rilikni rasmiy verifikatsiya bilan isbotlaydigan doimiy yoniq xotiradir. <a href="https://app.graphify.com/login"><b>Bepul 14 kunlik sinovni boshlang &rarr;</b></a>
</p>

AI kod yordamchingizda `/graphify` deb yozing va u butun loyihangizni (kod, hujjatlar, PDF-lar, rasmlar, videolar) **bilim grafiga** aylantiradi, uni fayllarni grep qilish o'rniga **so'rov qilishingiz mumkin**.

- **Kod bepul va to'liq lokal tarzda xaritalanadi.** Kod tree-sitter AST bilan tahlil qilinadi: deterministik, LLM yo'q, hech narsa qurilmangizdan chiqmaydi. (Hujjatlar, PDF-lar, rasmlar va video semantik o'tish uchun yordamchingizning modelidan yoki sozlangan API kalitidan foydalanadi.)
- **Har bir qirra tushuntiriladi.** Har bir bog'lanish `EXTRACTED` (manbada aniq ko'rsatilgan) yoki `INFERRED` (graphify tomonidan aniqlangan) deb belgilanadi, shunday qilib to'g'ridan-to'g'ri o'qilgan narsani xulosa qilingan narsadan ajrata olasiz.
- **Vektor indeksi emas.** Embedding yo'q, vektor ombori yo'q: siz kezib chiqadigan haqiqiy graf. Savol bering, ikki narsa o'rtasidagi yo'lni kuzating yoki bitta tushunchani tushuntiring.

> [!NOTE]
> **Buni doimiy yoniq holda xohlaysizmi?** [Graphify Cloud](https://app.graphify.com/login) grafni butun SDLC bo'ylab jonli saqlaydi: monorepo va repolararo qo'llab-quvvatlash, rasmiy verifikatsiya hamda SDLC-ga qush nigohi bilan kod ko'rib chiqish, shuningdek Sentry, Jira va boshqalar uchun konnektorlar, shunda hodisalar va chiptalar kodingiz bilan bir xil grafda joylashadi. **[app.graphify.com da bepul 14 kunlik sinovni boshlang](https://app.graphify.com/login)**.

<p align="center">
  <img src="https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/graph-hero.png" alt="graphify's interactive graph.html showing the FastAPI codebase as a force-directed knowledge graph with a legend of detected communities" width="900">
</p>
<p align="center">
  <em>graphify tomonidan xaritalangan FastAPI kod bazasi. Har bir tugun tushunchadir, ranglar aniqlangan jamoalardir, butun narsa esa graph.html da bosiladi.</em>
</p>

**Ishni boshlang** (30 soniya). Python 3.10+ va uv (yoki pipx) talab qilinadi:

```bash
uv tool install graphifyy      # install the CLI (or: pipx install graphifyy)
graphify install               # detects your assistant and registers the skill
```

Keyin, AI yordamchingizda:

```
/graphify .
```

Tamom. Siz **uchta fayl** olasiz:

```
graphify-out/
├── graph.html       open in any browser: click nodes, filter, search
├── GRAPH_REPORT.md  the highlights: key concepts, surprising connections, suggested questions
└── graph.json       the full graph: query it anytime without re-reading your files
```

Saqlangan graf `graph.schema_version` ni o'z ichiga oladi, shunday qilib integratsiyalar
mos kelmaydigan format o'zgarishlarini aniqlay oladi, hamda uni ishlab chiqargan
Graphify relizini belgilaydigan `graph.graphify_version` ni.

**Bitta o'rnatish, istalgan yordamchi, istalgan OS.** Claude Code, Cursor, Codex, Gemini CLI, GitHub Copilot va yana 20+ tasi, macOS, Linux va Windows da: [platformangizni tanlang](#install).

---

## Amalda ko'ring

<p align="center">
  <img src="https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/demo-path.svg" alt="graphify path query: a terminal asks for the shortest path between FastAPI and ModelField, and the answer lights up hop by hop across the knowledge graph" width="900">
</p>

Graf qurilgach, uni fayllarni o'qish o'rniga so'rov qilasiz. Haqiqiy natija, yuqorida ko'rsatilgan FastAPI kod bazasida ishga tushirilgan graphify:

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

Har bir qirra **ishonch yorlig'ini** olib yuradi (`EXTRACTED` = manbada aniq, `INFERRED` = aniqlash orqali kelib chiqqan), shunday qilib to'g'ridan-to'g'ri o'qilgan narsani xulosa qilingan narsadan ajrata olasiz. `graphify query "<question>"` oddiy tildagi savol uchun chegaralangan subgrafni qaytaradi, `graphify path A B` esa istalgan ikki narsaning qanday bog'lanishini kuzatadi.

---

## U nima qiladi

Qutidan chiqib nima olasiz:

| Imkoniyat | Nima olasiz |
|---|---|
| **Xudo tugunlar** | Eng ko'p bog'langan tushunchalar, shunday qilib hamma narsa nima orqali oqishini ko'rasiz |
| **Jamoalar** | Graf quyi tizimlarga bo'lingan (Leiden), LLM-siz yorliqlar bilan |
| **Fayllararo bog'lanishlar** | `calls` / `imports` / `inherits` / `mixes_in` ~40 tilda tree-sitter AST orqali aniqlanadi |
| **Query, path, explain** | Savol bering, ikki narsa o'rtasidagi yo'lni kuzating yoki bitta tushunchani tushuntiring, barchasi `graph.json` ga nisbatan |
| **Asos + hujjat havolalari** | `# NOTE:` / `# WHY:` izohlari va ADR/RFC iqtiboslari kodga bog'langan birinchi darajali tugunlarga aylanadi |
| **Koddan tashqari** | Hujjatlar, PDF-lar, rasmlar va video/audio, barchasi bir xil grafga xaritalanadi |
| **Avval lokal** | Kod lokal tarzda tree-sitter bilan tahlil qilinadi (LLM yo'q, hech narsa qurilmangizdan chiqmaydi); faqat hujjatlar/media ustidagi semantik o'tish backendga murojaat qiladi, va faqat siz uni sozlasangiz |

> [!TIP]
> Buni ko'plab repolar yoki monorepo bo'ylab ishga tushiryapsizmi? [Graphify Cloud](https://app.graphify.com/login) buni uzluksiz bajaradi va agent token sarfini 80% ga qisqartiradi, repolararo bog'lanishlar, SDLC bo'ylab kod ko'rib chiqish, rasmiy verifikatsiya va Sentry/Jira konnektorlari bilan. [Bepul 14 kunlik sinovni boshlang &rarr;](https://app.graphify.com/login)

---

## Benchmarks: 0.497 recall@10, 0 LLM credits

| Benchmark | Metrika | graphify | Soha |
|---|---|---|---|
| LOCOMO (n=300) | recall@10 | **0.497** | mem0 0.048, supermemory 0.149 |
| LOCOMO (n=300) | QA aniqligi | 45.3% | supermemory 49.7%, mem0 27.3% |
| LongMemEval-S (n=50) | QA aniqligi | **76%** | zich RAG bilan teng |
| ERPNext cross-tool (n=6) | asosiy-fakt qamrovi | **82.0%** | grep/read bazaviy ko'rsatkichi 70.8% |
| Graf qurish | LLM kreditlari | **0** | ko'pchilik tizimlar uchun token asosida |

Har bir tizim bir xil model va byudjetlar bilan bir xil stendda ishladi, ikkinchi hakamga nisbatan ko'r-ko'rona tasdiqlangan hakam tomonidan baholandi (90.6% kelishuv, Cohen kappasi 0.81). To'liq har bir tizim bo'yicha jadvallar, kod-intellekti natijasi va takrorlash buyruqlari: **[BENCHMARKS.md](../../BENCHMARKS.md)**.

---

## Hujjatlar

To'liq qo'llanmalar va ma'lumotnoma **[docs.graphify.com](https://docs.graphify.com)** da joylashgan:

- **[Tez boshlash](https://docs.graphify.com/quickstart)**: birinchi grafingizni quring
- **[CLI ma'lumotnomasi](https://docs.graphify.com/reference/overview)**: har bir buyruq va bayroq
- **[Yaxshiroq graf savollari bering](https://docs.graphify.com/guides/querying)**: so'rov namunalari
- **[Konfiguratsiya](https://docs.graphify.com/reference/configuration)**: muhit o'zgaruvchilari va sozlash
- **[Qo'llab-quvvatlanadigan kirishlar](https://docs.graphify.com/concepts/supported-inputs)**: tillar va fayl turlari
- **[Jamoa ish oqimlari](https://docs.graphify.com/guides/team-workflows)** va **[PR ko'rib chiqish](https://docs.graphify.com/guides/pull-requests)**
- **[Muammolarni bartaraf etish](https://docs.graphify.com/troubleshooting)** va **[Qanday ishlaydi](https://docs.graphify.com/concepts/architecture)**

---

## Dastlabki talablar

| Talab | Minimum | Tekshirish | O'rnatish |
|---|---|---|---|
| Python | 3.10+ | `python --version` | [python.org](https://www.python.org/downloads/) |
| uv *(tavsiya etiladi)* | istalgan | `uv --version` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| pipx *(muqobil)* | istalgan | `pipx --version` | `pip install pipx` |

**macOS tezkor o'rnatish (Homebrew):**
```bash
brew install python@3.12 uv
```

**Windows tezkor o'rnatish:**
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
> **Rasmiy paket:** PyPI paketi `graphifyy` (ikki-y). PyPI dagi boshqa `graphify*` paketlari aloqador emas. CLI buyrug'i hamon `graphify`.

Rasmiy manba repozitoriysi: [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify).

Ikki buyruqli tez boshlash ushbu README ning yuqori qismida. Ushbu bo'lim o'rnatish usullari, loyiha doirasidagi o'rnatishlar va har bir qo'llab-quvvatlanadigan platformani qamrab oladi.

**O'rnatish usullari** (birini tanlang):

```bash
uv tool install graphifyy   # recommended, isolated env (if 'graphify' isn't found after, run: uv tool update-shell)
pipx install graphifyy      # alternative
pip install graphifyy       # may need PATH setup, see Troubleshooting below
```

Keyin `graphify install` ni bir marta ishga tushiring. U qaysi yordamchini ishlatishingizni aniqlaydi va mahoratni ro'yxatdan o'tkazadi, shunday qilib har bir yordamchi uchun alohida sozlash kerak emas. AI yordamchingizni oching va `/graphify .` deb yozing.

Yordamchi mahoratini foydalanuvchi profilingiz o'rniga joriy repozitoriyga
o'rnatish uchun `--project` ni qo'shing:

```bash
graphify install --project
graphify install --project --platform codex
```

Loyiha doirasidagi o'rnatishlar joriy katalog ostiga yoziladi, masalan
`.claude/skills/graphify/SKILL.md` yoki `.agents/skills/graphify/SKILL.md` (shuningdek
mahorat talab bo'yicha yuklaydigan `references/` yon fayli), va
kommit qilinishi mumkin bo'lgan fayllar uchun `git add` maslahatini chop etadi.
Loyiha doirasidagi o'rnatishlarni qo'llab-quvvatlaydigan har bir platforma buyruqlari xuddi shu bayroqni qabul qiladi,
masalan `graphify claude install --project` yoki `graphify codex install --project`.

> [!TIP]
> `command not found`, Mac/Windows dagi `pip` muammosi, PowerShell tirnoqlari, `uvx` ishlatilishi, git-hook PATH g'alatiliklari yoki qat'iy rejimga duch keldingizmi? **[O'rnatish](https://docs.graphify.com/installation)** va **[Muammolarni bartaraf etish](https://docs.graphify.com/troubleshooting)** ga qarang.

<details>
<summary><b>Platformangizni tanlang</b> (20+ yordamchi, kengaytirish uchun bosing)</summary>

| Platforma | O'rnatish buyrug'i |
|----------|----------------|
| Claude Code (Linux/Mac) | `graphify install` |
| Claude Code (Windows) | `graphify install` (avtomatik aniqlanadi) yoki `graphify install --platform windows` |
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
| Agent Skills (freymvorklararo) | `graphify install --platform agents` (taxallus `--platform skills`) |
| Kiro IDE/CLI | `graphify kiro install` |
| Pi kod agenti | `graphify install --platform pi`, shuningdek mahalliy himoyachi uchun `graphify pi guard install` |
| Cursor | `graphify cursor install` |
| Devin CLI | `graphify devin install` |
| Google Antigravity | `graphify antigravity install` |

Codex foydalanuvchilariga parallel ekstraktsiya uchun `~/.codex/config.toml` dagi `[features]` ostida `multi_agent = true` ham kerak. CodeBuddy Claude Code bilan bir xil Agent vositasi va PreToolUse hook mexanizmidan foydalanadi. Factory Droid parallel subagent jo'natish uchun `Task` vositasidan foydalanadi. OpenClaw va Aider ketma-ket ekstraktsiyadan foydalanadi (parallel agent qo'llab-quvvatlashi ushbu platformalarda hali boshlang'ich bosqichda). Trae parallel subagent jo'natish uchun Agent vositasidan foydalanadi va `PreToolUse` hooklarini qo'llab-quvvatla**maydi**, shuning uchun AGENTS.md doimiy yoniq mexanizmdir.

`--platform agents` (taxallus `--platform skills`) umumiy freymvorklararo [Agent-Skills](https://github.com/anthropics/skills) joylashuvlariga mo'ljallangan: global o'rnatish uchun spetsifikatsiyaning foydalanuvchi-global `~/.agents/skills/` (uni `npx skills` va spetsifikatsiyaga mos freymvorklar o'qiydi), va loyiha (`--project`) o'rnatishi uchun `./.agents/skills/`. Yalang'och `graphify install` dizayn bo'yicha bitta platformali (Claude Code) bo'lib qoladi: mahoratning `.agents/skills` ni o'qiydigan istalgan freymvork tomonidan topilishini xohlasangiz, nomlangan `agents` platformasidan foydalaning.

Pi da `PreToolUse` hook yo'q, shuning uchun `graphify pi guard install` mahalliy Pi kengaytmasini ro'yxatdan o'tkazadi (Pi ning o'z `pi install <package directory>` orqali), u Pi ning `read`, `grep`, `find` va qidiruv uslubidagi `bash` chaqiruvlaridan oldin o'rnatilgan `graphify hook-guard` ni ishga tushiradi. Yangi/eskirgan graf qarorlari va `GRAPHIFY_HOOK_STRICT=1` ning har sessiyada bir marta indekslangan-o'qishni rad etishi xuddi shu siyosatdan kelib chiqadi, shuning uchun Pi Claude Code ning hook xatti-harakatiga mos keladi; ko'rsatma `<system-reminder source="graphify">` boshqaruvchi xabari sifatida keladi. Unga Pi 0.58.4 yoki undan yangiroq kerak: oldingi versiyalar boshqaruvchi xabarga parallel vosita-chaqiruv to'plamining qolgan qismini o'tkazib yuborishga ruxsat beradi. Paket Graphify o'rnatmasi ichida yetkaziladi, shuning uchun Graphify ni doimiy o'rnating (`uv tool install graphifyy` yoki `pipx install graphifyy`, `uvx` emas), o'rnatgandan yoki yangilagandan keyin Pi ni qayta ishga tushiring va uni `graphify pi guard uninstall` bilan olib tashlang. Faqat mahalliy fayl maqsadlari tekshiriladi; hookga loyihadan tashqaridagi mutlaq `PATH` yozuvida `graphify` kerak, u ikki soniyalik, 256 KiB-kirish/64 KiB-chiqish chaqiruvi bilan chegaralangan va ochiq holda ishdan chiqadi. Xuddi shu paket [Oh My Pi](https://github.com/can1357/oh-my-pi) da ham yuklanadi: `omp plugin install "$(graphify pi guard path)"`. Ro'yxatdan o'tgan yo'l Python versiyasi va venv ni o'z ichiga oladi, shuning uchun ularning birortasini o'zgartirgandan keyin `graphify pi guard install` ni qayta ishga tushiring va eski yozuvni `pi remove <old path>` bilan olib tashlang.

> Codex `/graphify` o'rniga `$graphify` dan foydalanadi.

</details>

<details>
<summary><b>Ixtiyoriy qo'shimchalar</b> (faqat kerakligini o'rnating)</summary>

| Qo'shimcha | Nima qo'shadi | O'rnatish |
|---|---|---|
| `pdf` | PDF ekstraktsiyasi | `uv tool install "graphifyy[pdf]"` |
| `office` | `.docx` va `.xlsx` qo'llab-quvvatlash | `uv tool install "graphifyy[office]"` |
| `google` | Google Sheets renderlash | `uv tool install "graphifyy[google]"` |
| `video` | Video/audio transkripsiyasi (faster-whisper + yt-dlp) | `uv tool install "graphifyy[video]"` |
| `mcp` | MCP stdio serveri | `uv tool install "graphifyy[mcp]"` |
| `neo4j` | Neo4j push qo'llab-quvvatlash | `uv tool install "graphifyy[neo4j]"` |
| `falkordb` | FalkorDB push qo'llab-quvvatlash | `uv tool install "graphifyy[falkordb]"` |
| `svg` | SVG graf eksporti | `uv tool install "graphifyy[svg]"` |
| `leiden` | Leiden jamoa aniqlash (Python < 3.13 da graspologic; 3.13+ da mahalliy backend) | `uv tool install "graphifyy[leiden]"` |
| `ollama` | Ollama mahalliy inferens | `uv tool install "graphifyy[ollama]"` |
| `openai` | OpenAI / OpenAI-mos API-lar | `uv tool install "graphifyy[openai]"` |
| `gemini` | Google Gemini API | `uv tool install "graphifyy[gemini]"` |
| `anthropic` | Anthropic Claude API (`--backend claude`, `ANTHROPIC_API_KEY` dan foydalanadi) | `uv tool install "graphifyy[anthropic]"` |
| `bedrock` | AWS Bedrock (IAM dan foydalanadi, API kaliti yo'q) | `uv tool install "graphifyy[bedrock]"` |
| `azure` | Azure OpenAI Service (`--backend azure`, `AZURE_OPENAI_API_KEY` + `AZURE_OPENAI_ENDPOINT` dan foydalanadi) | `uv tool install "graphifyy[openai]"` |
| `sql` | SQL sxema ekstraktsiyasi | `uv tool install "graphifyy[sql]"` |
| `postgres` | Jonli PostgreSQL introspeksiyasi (`--postgres DSN`) | `uv tool install "graphifyy[postgres]"` |
| `dm` | BYOND DreamMaker `.dm`/`.dme` AST ekstraktsiyasi (platformangizga mos wheel bo'lmasa C kompilyatori + `python3-dev` kerak bo'lishi mumkin) | `uv tool install "graphifyy[dm]"` |
| `terraform` | Terraform / HCL `.tf`/`.tfvars`/`.hcl` AST ekstraktsiyasi | `uv tool install "graphifyy[terraform]"` |
| `pascal` | Pascal / Delphi `.pas`/`.dpr`/`.dpk`/`.inc` AST ekstraktsiyasi (aniqroq `calls`/`inherits` qirralari; mavjud bo'lmasa regex ekstraktoriga qaytadi) | `uv tool install "graphifyy[pascal]"` |
| `ocaml` | OCaml `.ml`/`.mli` AST ekstraktsiyasi | `uv tool install "graphifyy[ocaml]"` |
| `commonlisp` | Common Lisp `.lisp`/`.cl`/`.lsp`/`.asd` AST ekstraktsiyasi | `uv tool install "graphifyy[commonlisp]"` |
| `robot` | Robot Framework `.robot`/`.resource` ekstraktsiyasi (to'plamlar, test holatlari, kalit so'zlar, kalit-so'z chaqiruvi va resource/library import qirralari) | `uv tool install "graphifyy[robot]"` |
| `chinese` | Xitoycha so'rov segmentatsiyasi (jieba) | `uv tool install "graphifyy[chinese]"` |
| `all` | Yuqoridagilarning barchasi | `uv tool install "graphifyy[all]"` |

</details>

---

## Yordamchingiz grafdan doimo foydalanishini ta'minlang

Graf qurgandan keyin loyihangizda buni bir marta ishga tushiring:

Loyihangizda `graphify <platform> install` ni bir marta ishga tushiring, masalan `graphify claude install` yoki `graphify codex install` (yoki `graphify install --platform <name>`).

Bu yordamchingizga kod bazasi savollari uchun bilim grafiga murojaat qilishni aytadigan kichik konfiguratsiya faylini yozadi, to'liq hisobotni o'qish yoki xom fayllarni grep qilishdan ko'ra `graphify query "<question>"` kabi chegaralangan so'rovlarni afzal ko'radi.

- **Hook platformalari** (Claude Code, Gemini CLI): hook qidiruv uslubidagi vosita chaqiruvlaridan oldin (va Claude Code da, Read/Glob vositalari orqali manba fayllarni birma-bir o'qishdan oldin) avtomatik ishga tushadi va yordamchingizni graf yo'liga undaydi.
- **Ko'rsatma-fayl platformalari** (Codex, OpenCode, Cursor va boshqalar): doimiy ko'rsatma fayllari (`AGENTS.md`, `.cursor/rules/` va boshqalar) xuddi shu avval-so'rov ko'rsatmasini beradi.

`GRAPH_REPORT.md` keng arxitektura ko'rib chiqish uchun hamon mavjud.

Har bir platforma aynan qaysi fayllarni yozishi (CodeBuddy ning `CODEBUDDY.md` + `PreToolUse` hooklari, Codex ning `AGENTS.md`, Kilo ning mahalliy `.kilo` plagini, Cursor ning `alwaysApply` qoidasi va hokazo) **[Doimiy yoniq sozlash](https://docs.graphify.com/guides/always-on)** da yoritilgan.

graphify ni barcha platformalardan bir vaqtning o'zida olib tashlash uchun: `graphify uninstall` (`graphify-out/` ni ham o'chirish uchun `--purge` qo'shing). Yoki har bir platforma buyrug'idan foydalaning (masalan `graphify claude uninstall`).

### CLI mahoratlari yoki MCP ko'rsatmalari?

`graphify install` tomonidan o'rnatilgan ko'rsatmalar va Graphify MCP ulanishi bilan taqdim etilganlar grafni so'rov qilishning turli usullarini tasvirlaydi:

| Sozlash | Foydalanish ko'rsatmasi | So'rov kirishi |
|---|---|---|
| Mahalliy CLI va o'rnatilgan yordamchi mahorati | `graphify install` tomonidan yozilgan platforma ko'rsatmalari | Mahalliy grafga (sukut bo'yicha `graphify-out/`) nisbatan `graphify query`, `graphify path` va `graphify explain` ni ishga tushiring. |
| Ulangan Graphify MCP serveri | Ulanishning ko'rsatmalari va o'sha server sanab o'tgan vositalar | O'sha ulanish xizmat qiladigan grafga nisbatan sanab o'tilgan MCP vositalarini chaqiring. Vosita nomlari va tavsiflari serverdan keladi. |

Ikkalasi ham keng manba qidiruvlaridan oldin chegaralangan graf so'rovlarini rag'batlantiradi. Yordamchingiz haqiqatan ham kira oladigan vositalarga mos keladigan ko'rsatmalarni tanlang; birorta blok ham yordamchingizning ko'rsatma fayllari uchun universal ustunlik qoidasini o'rnatmaydi. Agar ikkala integratsiyadan foydalansangiz, har biri qaysi grafni so'rov qilishini aniqlang va `AGENTS.md` ga ikkita shartsiz ko'rsatma blokini nusxalash o'rniga asosiy so'rov yo'lini tanlang.

`graphify install` mahalliy yordamchi integratsiyasini o'rnatadi; u MCP ulanishini o'rnatmaydi. MCP mijozi ulangan serveridan foydalanish uchun mahalliy CLI so'rovlarini ishga tushirishi shart emas. Mahalliy joylashtirilgan server hamon o'z Graphify o'rnatmasi va grafiga muhtoj, holbuki joylashtirilgan ulanish mijozning ish katalogida mavjud bo'lmagan grafga xizmat qilishi mumkin. Kutilgan vositalar yo'q bo'lsa, boshqa sozlashning ko'rsatmalarini o'zaro almashtiriladigan deb hisoblash o'rniga tegishli CLI o'rnatmasi yoki MCP ulanishini tekshiring.

---

## Hisobotda nima bor

`GRAPH_REPORT.md` keng arxitektura ko'rib chiqish uchun xudo tugunlar, jamoalar va asosiy yo'llarni jamlaydi. Graf qanday quriladi va u nimani o'z ichiga oladi: **[graphify qanday ishlaydi](https://docs.graphify.com/concepts/architecture)**.

---

## U qanday fayllarni ishlaydi: ~40 languages

graphify ~40 dasturlash tilini tree-sitter AST bilan lokal tarzda tahlil qiladi va hujjatlar, PDF-lar, rasmlar hamda audio/video ni ixtiyoriy semantik o'tish orqali xaritalaydi. To'liq ro'yxat: **[Qo'llab-quvvatlanadigan kirishlar](https://docs.graphify.com/concepts/supported-inputs)**.

---

## Keng tarqalgan buyruqlar

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

Quyida [to'liq buyruqlar ma'lumotnomasi](#full-command-reference) ga qarang.

---

## Fayllarni e'tiborsiz qoldirish

graphify `.gitignore` ni hurmat qiladi va `--exclude` namunalari hamda loyiha `.graphifyignore` ni qo'llab-quvvatlaydi. Tafsilotlar: **[Konfiguratsiya](https://docs.graphify.com/reference/configuration)**.


## Loyiha konfiguratsiyasi

Bitta ishga emas, balki loyihaga tegishli sozlamalar uchun skanerlash ildizida `.graphifyrc` yarating. Har bir qatorda bitta `key=value`; `#` bilan boshlanadigan qatorlar izohlardir.

**Noaniq kengaytmalar.** Ba'zi kengaytmalar turli loyihalarda turli tillarni anglatadi: `.inc` pfSense da PHP, Delphi daraxtida Pascal, boshqa joylarda SQL yoki assembly; `.h` C yoki C++; `.m` Objective-C yoki MATLAB. graphify bitta global sukut tanlashi kerak, va u noto'g'ri tanlasa fayl muvaffaqiyatsizlikka uchramaydi: u noto'g'ri til sifatida tahlil qilinadi va bir hovuch tasodifiy tugunlar beradi, shunday qilib graf to'ldirilgandek ko'rinadi, holbuki haqiqiy belgilar yo'q. Kengaytma repongizda nimani anglatishini e'lon qiling:

```
# .graphifyrc
# A language name:
language.inc=php
# Or an extension graphify already knows:
language.tpl=.ts
# Baked into the git hooks (see Team setup):
viz_node_limit=0
```

E'lon tasniflash, ekstraktor tanlash, grammatika va aniqlash, importlar, `graphify watch` va AST keshi orqali oqadi (boshqa til ostida qayta tahlil qilingan fayl eski yozuvni hech qachon qayta ishlatmaydi), va xuddi shu `.graphifyrc` ni `extract`, `update`, hooklar, MCP serveri va `/graphify` mahorati o'qiydi. Terish xatosi stderr da bir marta xabar qilinadi va skanerlash sukutlar bilan davom etadi. E'lonlar keshlash, inkremental qayta qurishlar va import aniqlash bilan qanday o'zaro ta'sir qilishi: **[Konfiguratsiya](https://docs.graphify.com/reference/configuration)**.

---

## Jamoa sozlash

Grafni kommit qiling yoki ulashing, shunda butun jamoangiz bir xil kontekstni so'rov qiladi, va pull requestlarni graf konteksti bilan ko'rib chiqing. **[Jamoangiz bilan kontekstni ulashing](https://docs.graphify.com/guides/team-workflows)** va **[Pull requestlarni ko'rib chiqing](https://docs.graphify.com/guides/pull-requests)** ga qarang.

---

## Grafdan to'g'ridan-to'g'ri foydalanish

AI yordamchingizdan tashqari, `graph.json` ni CLI dan to'g'ridan-to'g'ri `graphify query`, `graphify path` va `graphify explain` bilan so'rov qiling. Bir nechta tugunga mos keladigan nom taxmin qilinmasdan nomzodlar ro'yxati bilan rad etiladi. Skriptlar natijani chiqish kodidan o'qiy oladi: `0` javob, `3` noaniq nom, `4` mos keladigan tugun yo'q. **[Yaxshiroq graf savollari bering](https://docs.graphify.com/guides/querying)** va **[so'rov ma'lumotnomasi](https://docs.graphify.com/reference/query)** ga qarang.

---

## Muhit o'zgaruvchilari

Backendlar, API kalitlari, hook xatti-harakati va sozlash muhit o'zgaruvchilari bilan boshqariladi. To'liq jadval: **[Konfiguratsiya](https://docs.graphify.com/reference/configuration)**.

---

## Maxfiylik

- **Kod fayllari**: tree-sitter orqali lokal tarzda ishlanadi. Hech narsa qurilmangizdan chiqmaydi. Faqat kodli korpus API kalitini talab qilmaydi: `graphify extract` to'liq oflayn ishlaydi. Aralash repoda, faqat kodni indekslash va aks holda LLM talab qiladigan hujjatlar/PDF-lar/rasmlarni o'tkazib yuborish uchun `--code-only` qo'shing.
- **Video / audio**: faster-whisper bilan lokal tarzda transkripsiya qilinadi. Hech narsa qurilmangizdan chiqmaydi.
- **Hujjatlar, PDF-lar, rasmlar**: semantik ekstraktsiya uchun AI yordamchingizga yuboriladi (`/graphify` mahorati orqali, IDE sessiyangiz ishlatadigan har qanday modeldan foydalanib). Headless `graphify extract` `GEMINI_API_KEY` / `GOOGLE_API_KEY` (Gemini), `MOONSHOT_API_KEY` (Kimi), `ANTHROPIC_API_KEY` (Claude), `OPENAI_API_KEY` (OpenAI), `DEEPSEEK_API_KEY` (DeepSeek), ishlab turgan Ollama namunasi (`OLLAMA_BASE_URL`), standart provayder zanjiri orqali AWS hisob ma'lumotlari (Bedrock - API kaliti kerak emas, IAM dan foydalanadi) yoki `claude` CLI ikkilik faylini (Claude Code - API kaliti kerak emas, Claude obunangizdan foydalanadi) talab qiladi. `--dedup-llm` bayrog'i xuddi shu kalitdan foydalanadi.
- **Ma'lumotlar rezidentligi**: `graphify extract` qaysi API kaliti o'rnatilganiga qarab qaysi provayderdan foydalanishni avtomatik aniqlaydi (ustuvorlik: Gemini → Kimi → Claude → OpenAI → DeepSeek → Azure → Bedrock → Ollama). Ma'lumotlar rezidentligi talablari bo'lgan kod uchun `--backend ollama` (to'liq lokal) dan foydalaning yoki aniq `--backend` bayrog'ini uzating. Kimi (`MOONSHOT_API_KEY`) Xitoydagi Moonshot AI serverlariga yo'naltiradi.
- **Telemetriya yo'q**, foydalanishni kuzatish yo'q, analitika yo'q.
- **So'rovni jurnalga yozish**: har bir `graphify query`, `graphify path`, `graphify explain` va MCP `query_graph` chaqiruvi `~/.cache/graphify-queries.log` ga JSON Lines formatida yoziladi (vaqt belgisi, savol, korpus, qaytarilgan tugunlar, davomiyligi). To'liq subgraf javoblari sukut bo'yicha saqlan**maydi**. Voz kechish uchun `GRAPHIFY_QUERY_LOG_DISABLE=1` ni o'rnating yoki kod yo'lini o'chirmasdan jim qilish uchun `GRAPHIFY_QUERY_LOG=/dev/null`.

---

## Muammolarni bartaraf etish

Keng tarqalgan o'rnatish va ekstraktsiya muammolari hamda ularning yechimlari: **[Muammolarni bartaraf etish](https://docs.graphify.com/troubleshooting)**.

---

## To'liq buyruqlar ma'lumotnomasi

Har bir buyruq va bayroq, misollar bilan: **[CLI ma'lumotnomasi](https://docs.graphify.com/reference/overview)**.

---

## Ko'proq bilib oling

- [docs.graphify.com](https://docs.graphify.com): to'liq hujjatlar: qo'llanmalar, buyruqlar ma'lumotnomasi va integratsiyalar
- [Qanday ishlaydi](../how-it-works.md): ekstraktsiya quvuri, jamoa aniqlash, ishonch baholash, benchmarklar
- [ARCHITECTURE.md](../../ARCHITECTURE.md): modul tahlili, til qanday qo'shiladi
- [Ixtiyoriy integratsiyalar](../docker-mcp-sqlite.md): Docker MCP Toolkit + SQLite
- [The Memory Layer](https://safishamsi.gumroad.com/l/qetvlo): graphify ortidagi g'oyalar va arxitektura boshidan oxirigacha haqidagi kitob

---

## Graphify Cloud

[**Graphify Cloud**](https://app.graphify.com/login) bu graphify ustiga qurilgan doimiy yoniq qatlam. Har bir papka uchun talab bo'yicha qayta quriladigan graf o'rniga, u butun dasturiy ta'minot ishlab chiqish hayotiy sikli bo'ylab bitta jonli grafni saqlaydi:

- **80% kamroq token**: doimiy yoniq xotira sizning agentlaringiz har sessiyada kod bazasini qayta o'qish va qayta tushuntirishni to'xtatishini anglatadi.
- **Monorepo va repolararo**: har bir xizmat va repozitoriy bo'ylab bitta bog'langan graf, papka uchun graf emas.
- **Rasmiy verifikatsiya**: arxitektura va bog'liqlik invariantlarini jonli grafga nisbatan tekshiring.
- **SDLC-ga qush nigohi bilan kod ko'rib chiqish**: merge qilishdan oldin o'zgarish butun tizim bo'ylab qanday tarqalishini ko'ring.
- **SDLC konnektorlari**: Sentry, Jira va boshqalarni jalb qiling, shunday qilib hodisalar, chiptalar va kod bitta grafda yashaydi.
- **Doimiy yoniq**: kod, hujjatlar va uchrashuvlar bo'ylab fon rejimida uzluksiz yangilanadi.

**[app.graphify.com da bepul 14 kunlik sinovni boshlang &rarr;](https://app.graphify.com/login)**

---

## Hissa qo'shish

Hissalar olqishlanadi. Ishlab chiqish sozlash, test va CI-parity buyruqlari, git ish oqimi va kuchli hissani nima tashkil qilishi (ishlab chiqilgan misollar va ekstraktsiya xato hisobotlari eng foydali) uchun **[CONTRIBUTING.md](../../CONTRIBUTING.md)** ga qarang. Arxitektura va til qanday qo'shiladi: [ARCHITECTURE.md](../../ARCHITECTURE.md).

Bu yerda yangimisiz? [Discord](https://discord.gg/XDnKVpzdXB) da yoki [GitHub Discussions](https://github.com/Graphify-Labs/graphify/discussions) da salom ayting.

---

## Hissa qo'shuvchilar

<a href="https://github.com/Graphify-Labs/graphify/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=Graphify-Labs/graphify" alt="graphify contributors" />
</a>

[contrib.rocks](https://contrib.rocks) bilan yaratilgan.

---

## Tarjimalar

README 32 tilda mavjud. O'z tilingizda o'qish uchun ushbu faylning yuqori qismidagi til almashtirgichidan foydalaning yoki [`docs/translations/`](./) ni ko'rib chiqing. Tarjimani yaxshilash yoki yangisini qo'shish uchun u yerdagi mos faylga qarshi pull request oching.

---

## graphify asosida qurish

graphify ekotizimida biror narsa quryapsizmi? Bu rag'batlantiriladi. Agar loyihangiz nomida "graphify" dan foydalansa (masalan `graphify-dashboard` yoki `graphify-action`), iltimos README ingizga uning jamoa tomonidan qurilgani va Graphify Labs bilan aloqador yoki u tomonidan ma'qullanmaganini aniqlashtiradigan qisqa izoh qo'shing. "graphify" va graphify logotipi Graphify Labs ning belgilari; iltimos ularni rasmiy maqomni anglatadigan tarzda ishlatmang.

---

## Jamoa va havolalar

<p align="center">
  <a href="https://graphify.com"><img src="https://img.shields.io/badge/Website-graphify.com-4c1?style=flat&logo=googlechrome&logoColor=white" alt="Website"/></a>
  <a href="https://discord.gg/XDnKVpzdXB"><img src="https://img.shields.io/badge/Discord-Join-5865F2?style=flat&logo=discord&logoColor=white" alt="Discord"/></a>
  <a href="https://x.com/graphify"><img src="https://img.shields.io/badge/X-graphify-000000?logo=x&logoColor=white" alt="X"/></a>
  <a href="https://www.youtube.com/@graphifylabs"><img src="https://img.shields.io/badge/YouTube-Graphify%20Labs-FF0000?style=flat&logo=youtube&logoColor=white" alt="YouTube"/></a>
  <a href="https://github.com/sponsors/safishamsi"><img src="https://img.shields.io/badge/sponsor-safishamsi-ea4aaa?logo=github-sponsors" alt="Sponsor"/></a>
  <a href="https://safishamsi.gumroad.com/l/qetvlo"><img src="https://img.shields.io/badge/Book-The%20Memory%20Layer-2ea44f?style=flat&logo=gitbook&logoColor=white" alt="The Memory Layer"/></a>
</p>
