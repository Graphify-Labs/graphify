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
  <b>Μειώστε τη δαπάνη token των agent κατά 80%.</b> Το Graphify Cloud είναι πάντα ενεργή μνήμη που διακυβερνά τους agent σας, διατηρεί υψηλή την ποιότητα κώδικα, και αποδεικνύει την ορθότητα με τυπική επαλήθευση. <a href="https://app.graphify.com/login"><b>Ξεκινήστε μια δωρεάν δοκιμή 14 ημερών &rarr;</b></a>
</p>

Πληκτρολογήστε `/graphify` στον βοηθό κωδικοποίησης AI σας και αυτός χαρτογραφεί ολόκληρο το έργο σας (κώδικα, έγγραφα, PDF, εικόνες, βίντεο) σε έναν **γράφο γνώσης** τον οποίο μπορείτε να **ρωτάτε αντί να κάνετε grep** στα αρχεία.

- **Ο κώδικας χαρτογραφείται δωρεάν, πλήρως τοπικά.** Ο κώδικας αναλύεται με tree-sitter AST: ντετερμινιστικά, χωρίς LLM, τίποτα δεν φεύγει από το μηχάνημά σας. (Τα έγγραφα, τα PDF, οι εικόνες και το βίντεο χρησιμοποιούν το μοντέλο του βοηθού σας, ή ένα διαμορφωμένο κλειδί API, για ένα σημασιολογικό πέρασμα.)
- **Κάθε ακμή εξηγείται.** Κάθε σύνδεση επισημαίνεται ως `EXTRACTED` (ρητή στην πηγή) ή `INFERRED` (επιλύθηκε από το graphify), ώστε να μπορείτε να διακρίνετε τι διαβάστηκε απευθείας από το τι συμπεράνθηκε.
- **Δεν είναι διανυσματικό ευρετήριο.** Χωρίς embeddings, χωρίς διανυσματικό αποθετήριο: ένας πραγματικός γράφος που διασχίζετε. Κάντε μια ερώτηση, εντοπίστε τη διαδρομή μεταξύ δύο πραγμάτων, ή εξηγήστε μία έννοια.

> [!NOTE]
> **Το θέλετε πάντα ενεργό;** Το [Graphify Cloud](https://app.graphify.com/login) διατηρεί τον γράφο ζωντανό σε ολόκληρο τον SDLC σας: υποστήριξη monorepo και cross-repo, τυπική επαλήθευση, και έλεγχο κώδικα με πανοραμική εικόνα του SDLC σας, συν connectors για Sentry, Jira, και άλλα ώστε τα συμβάντα και τα tickets να βρίσκονται στον ίδιο γράφο με τον κώδικά σας. **[Ξεκινήστε μια δωρεάν δοκιμή 14 ημερών στο app.graphify.com](https://app.graphify.com/login)**.

<p align="center">
  <img src="https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/graph-hero.png" alt="graphify's interactive graph.html showing the FastAPI codebase as a force-directed knowledge graph with a legend of detected communities" width="900">
</p>
<p align="center">
  <em>Η βάση κώδικα του FastAPI χαρτογραφημένη από το graphify. Κάθε κόμβος είναι μια έννοια, τα χρώματα είναι εντοπισμένες κοινότητες, και το σύνολο είναι clickable στο graph.html.</em>
</p>

**Ξεκινήστε** (30 δευτερόλεπτα). Χρειάζεται Python 3.10+ και uv (ή pipx):

```bash
uv tool install graphifyy      # install the CLI (or: pipx install graphifyy)
graphify install               # detects your assistant and registers the skill
```

Στη συνέχεια, στον βοηθό AI σας:

```
/graphify .
```

Αυτό ήταν. Λαμβάνετε **τρία αρχεία**:

```
graphify-out/
├── graph.html       open in any browser: click nodes, filter, search
├── GRAPH_REPORT.md  the highlights: key concepts, surprising connections, suggested questions
└── graph.json       the full graph: query it anytime without re-reading your files
```

Ο αποθηκευμένος γράφος περιλαμβάνει το `graph.schema_version` ώστε οι ενσωματώσεις να μπορούν να εντοπίζουν ασύμβατες αλλαγές μορφής, συν το `graph.graphify_version` που προσδιορίζει την έκδοση Graphify που τον παρήγαγε.

**Μία εγκατάσταση, οποιοσδήποτε βοηθός, οποιοδήποτε OS.** Claude Code, Cursor, Codex, Gemini CLI, GitHub Copilot, και 20+ ακόμη, σε macOS, Linux, και Windows: [επιλέξτε την πλατφόρμα σας](#install).

---

## Δείτε το σε δράση

<p align="center">
  <img src="https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/demo-path.svg" alt="graphify path query: a terminal asks for the shortest path between FastAPI and ModelField, and the answer lights up hop by hop across the knowledge graph" width="900">
</p>

Μόλις κατασκευαστεί ο γράφος, τον ρωτάτε αντί να διαβάζετε αρχεία. Πραγματική έξοδος, το graphify εκτελέστηκε στη βάση κώδικα του FastAPI που φαίνεται παραπάνω:

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

Κάθε ακμή φέρει μια **ετικέτα εμπιστοσύνης** (`EXTRACTED` = ρητή στην πηγή, `INFERRED` = προκύπτει από επίλυση), ώστε να μπορείτε να διακρίνετε τι διαβάστηκε απευθείας από το τι συμπεράνθηκε. Το `graphify query "<question>"` επιστρέφει έναν οριοθετημένο υπογράφο για μια ερώτηση σε απλή γλώσσα, και το `graphify path A B` εντοπίζει πώς συνδέονται οποιαδήποτε δύο πράγματα.

---

## Τι κάνει

Τι λαμβάνετε εκτός συσκευασίας:

| Δυνατότητα | Τι λαμβάνετε |
|---|---|
| **God nodes** | Οι πιο συνδεδεμένες έννοιες, ώστε να βλέπετε μέσα από τι ρέουν όλα |
| **Κοινότητες** | Ο γράφος χωρισμένος σε υποσυστήματα (Leiden), με ετικέτες χωρίς LLM |
| **Σύνδεσμοι μεταξύ αρχείων** | `calls` / `imports` / `inherits` / `mixes_in` επιλυμένοι σε ~40 γλώσσες μέσω tree-sitter AST |
| **Query, path, explain** | Κάντε μια ερώτηση, εντοπίστε τη διαδρομή μεταξύ δύο πραγμάτων, ή εξηγήστε μία έννοια, όλα πάνω στο `graph.json` |
| **Σκεπτικό + αναφορές εγγράφων** | Τα σχόλια `# NOTE:` / `# WHY:` και οι παραπομπές ADR/RFC γίνονται κόμβοι πρώτης κατηγορίας συνδεδεμένοι με τον κώδικα |
| **Πέρα από τον κώδικα** | Έγγραφα, PDF, εικόνες, και βίντεο/ήχος χαρτογραφούνται όλα στον ίδιο γράφο |
| **Local-first** | Ο κώδικας αναλύεται τοπικά με tree-sitter (χωρίς LLM, τίποτα δεν φεύγει από το μηχάνημά σας)· μόνο το σημασιολογικό πέρασμα πάνω σε έγγραφα/μέσα καλεί ένα backend, και μόνο αν διαμορφώσετε ένα |

> [!TIP]
> Το εκτελείτε σε πολλά repos ή σε monorepo; Το [Graphify Cloud](https://app.graphify.com/login) το κάνει συνεχώς και μειώνει τη δαπάνη token των agent κατά 80%, με συνδέσμους cross-repo, έλεγχο κώδικα σε όλο τον SDLC, τυπική επαλήθευση, και connectors Sentry/Jira. [Ξεκινήστε μια δωρεάν δοκιμή 14 ημερών &rarr;](https://app.graphify.com/login)

---

## Benchmarks: 0.497 recall@10, 0 LLM credits

| Benchmark | Μετρική | graphify | Πεδίο |
|---|---|---|---|
| LOCOMO (n=300) | recall@10 | **0.497** | mem0 0.048, supermemory 0.149 |
| LOCOMO (n=300) | ακρίβεια QA | 45.3% | supermemory 49.7%, mem0 27.3% |
| LongMemEval-S (n=50) | ακρίβεια QA | **76%** | ισοβαθμία με dense RAG |
| ERPNext cross-tool (n=6) | κάλυψη βασικών γεγονότων | **82.0%** | grep/read baseline 70.8% |
| Κατασκευή γράφου | μονάδες LLM | **0** | ανά token για τα περισσότερα συστήματα |

Κάθε σύστημα εκτελέστηκε στο ίδιο harness με το ίδιο μοντέλο και τους ίδιους προϋπολογισμούς, βαθμολογήθηκε από έναν κριτή τυφλά επικυρωμένο έναντι ενός δεύτερου κριτή (90.6% συμφωνία, Cohen's kappa 0.81). Πλήρεις πίνακες ανά σύστημα, το αποτέλεσμα code-intelligence, και εντολές αναπαραγωγής: **[BENCHMARKS.md](../../BENCHMARKS.md)**.

---

## Documentation

Πλήρεις οδηγοί και αναφορά βρίσκονται στο **[docs.graphify.com](https://docs.graphify.com)**:

- **[Quickstart](https://docs.graphify.com/quickstart)**: κατασκευάστε τον πρώτο σας γράφο
- **[CLI reference](https://docs.graphify.com/reference/overview)**: κάθε εντολή και σημαία
- **[Ask better graph questions](https://docs.graphify.com/guides/querying)**: μοτίβα ερωτημάτων
- **[Configuration](https://docs.graphify.com/reference/configuration)**: μεταβλητές περιβάλλοντος και ρύθμιση
- **[Supported inputs](https://docs.graphify.com/concepts/supported-inputs)**: γλώσσες και τύποι αρχείων
- **[Team workflows](https://docs.graphify.com/guides/team-workflows)** και **[PR review](https://docs.graphify.com/guides/pull-requests)**
- **[Troubleshooting](https://docs.graphify.com/troubleshooting)** και **[How it works](https://docs.graphify.com/concepts/architecture)**

---

## Προαπαιτούμενα

| Απαίτηση | Ελάχιστο | Έλεγχος | Εγκατάσταση |
|---|---|---|---|
| Python | 3.10+ | `python --version` | [python.org](https://www.python.org/downloads/) |
| uv *(συνιστάται)* | οποιαδήποτε | `uv --version` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| pipx *(εναλλακτικά)* | οποιαδήποτε | `pipx --version` | `pip install pipx` |

**Γρήγορη εγκατάσταση macOS (Homebrew):**
```bash
brew install python@3.12 uv
```

**Γρήγορη εγκατάσταση Windows:**
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
> **Επίσημο πακέτο:** Το πακέτο PyPI είναι `graphifyy` (με διπλό y). Άλλα πακέτα `graphify*` στο PyPI δεν σχετίζονται. Η εντολή CLI παραμένει `graphify`.

Το επίσημο αποθετήριο πηγαίου κώδικα είναι το [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify).

Η γρήγορη εκκίνηση δύο εντολών βρίσκεται στην κορυφή αυτού του README. Αυτή η ενότητα καλύπτει τις μεθόδους εγκατάστασης, τις εγκαταστάσεις με εμβέλεια έργου, και κάθε υποστηριζόμενη πλατφόρμα.

**Μέθοδοι εγκατάστασης** (επιλέξτε μία):

```bash
uv tool install graphifyy   # recommended, isolated env (if 'graphify' isn't found after, run: uv tool update-shell)
pipx install graphifyy      # alternative
pip install graphifyy       # may need PATH setup, see Troubleshooting below
```

Στη συνέχεια εκτελέστε `graphify install` μία φορά. Εντοπίζει ποιον βοηθό εκτελείτε και καταχωρεί το skill, οπότε δεν υπάρχει ρύθμιση ανά βοηθό. Ανοίξτε τον βοηθό AI σας και πληκτρολογήστε `/graphify .`

Για να εγκαταστήσετε το skill του βοηθού στο τρέχον αποθετήριο αντί στο προφίλ χρήστη σας, προσθέστε `--project`:

```bash
graphify install --project
graphify install --project --platform codex
```

Οι εγκαταστάσεις με εμβέλεια έργου γράφουν κάτω από τον τρέχοντα κατάλογο, για παράδειγμα `.claude/skills/graphify/SKILL.md` ή `.agents/skills/graphify/SKILL.md` (συν ένα sidecar `references/` που το skill φορτώνει κατ' απαίτηση), και εκτυπώνουν μια υπόδειξη `git add` για αρχεία που μπορούν να γίνουν commit. Οι εντολές ανά πλατφόρμα που υποστηρίζουν εγκαταστάσεις με εμβέλεια έργου δέχονται την ίδια σημαία, για παράδειγμα `graphify claude install --project` ή `graphify codex install --project`.

> [!TIP]
> Αντιμετωπίζετε `command not found`, ένα πρόβλημα `pip` σε Mac/Windows, quoting στο PowerShell, χρήση `uvx`, ιδιαιτερότητες PATH σε git-hook, ή strict mode; Δείτε **[Installation](https://docs.graphify.com/installation)** και **[Troubleshooting](https://docs.graphify.com/troubleshooting)**.

<details>
<summary><b>Επιλέξτε την πλατφόρμα σας</b> (20+ βοηθοί, κάντε κλικ για ανάπτυξη)</summary>

| Πλατφόρμα | Εντολή εγκατάστασης |
|----------|----------------|
| Claude Code (Linux/Mac) | `graphify install` |
| Claude Code (Windows) | `graphify install` (αυτόματα εντοπισμένο) ή `graphify install --platform windows` |
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
| Agent Skills (cross-framework) | `graphify install --platform agents` (ψευδώνυμο `--platform skills`) |
| Kiro IDE/CLI | `graphify kiro install` |
| Pi coding agent | `graphify install --platform pi`, συν `graphify pi guard install` για τον εγγενή guard |
| Cursor | `graphify cursor install` |
| Devin CLI | `graphify devin install` |
| Google Antigravity | `graphify antigravity install` |

Οι χρήστες Codex χρειάζονται επίσης `multi_agent = true` κάτω από `[features]` στο `~/.codex/config.toml` για παράλληλη εξαγωγή. Το CodeBuddy χρησιμοποιεί τον ίδιο μηχανισμό Agent tool και PreToolUse hook με το Claude Code. Το Factory Droid χρησιμοποιεί το εργαλείο `Task` για παράλληλη αποστολή subagent. Το OpenClaw και το Aider χρησιμοποιούν σειριακή εξαγωγή (η υποστήριξη παράλληλων agent είναι ακόμη πρώιμη σε αυτές τις πλατφόρμες). Το Trae χρησιμοποιεί το Agent tool για παράλληλη αποστολή subagent και **δεν** υποστηρίζει `PreToolUse` hooks, οπότε το AGENTS.md είναι ο πάντα ενεργός μηχανισμός.

Το `--platform agents` (ψευδώνυμο `--platform skills`) στοχεύει τις γενικές τοποθεσίες [Agent-Skills](https://github.com/anthropics/skills) πολλαπλών framework: το user-global `~/.agents/skills/` της προδιαγραφής (διαβάζεται από `npx skills` και framework συμβατά με την προδιαγραφή) για μια καθολική εγκατάσταση, και το `./.agents/skills/` για μια εγκατάσταση έργου (`--project`). Το σκέτο `graphify install` παραμένει μίας πλατφόρμας (Claude Code) εκ σχεδιασμού: χρησιμοποιήστε την ονομασμένη πλατφόρμα `agents` όταν θέλετε το skill να είναι ανιχνεύσιμο από οποιοδήποτε framework διαβάζει `.agents/skills`.

Το Pi δεν έχει `PreToolUse` hook, οπότε το `graphify pi guard install` καταχωρεί μια εγγενή επέκταση Pi (μέσω του ίδιου του `pi install <package directory>` του Pi) που εκτελεί το εγκατεστημένο `graphify hook-guard` πριν από τις κλήσεις `read`, `grep`, `find` και τύπου αναζήτησης `bash` του Pi. Οι αποφάσεις φρέσκου/παλαιού γράφου και η άρνηση indexed-read μία φορά ανά συνεδρία με `GRAPHIFY_HOOK_STRICT=1` προέρχονται από την ίδια πολιτική, οπότε το Pi ταιριάζει με τη συμπεριφορά hook του Claude Code· η καθοδήγηση φτάνει ως μήνυμα κατεύθυνσης `<system-reminder source="graphify">`. Χρειάζεται Pi 0.58.4 ή νεότερο: παλαιότερες εκδόσεις επέτρεπαν σε ένα μήνυμα κατεύθυνσης να παρακάμπτει το υπόλοιπο μιας παράλληλης παρτίδας κλήσεων εργαλείων. Το πακέτο παρέχεται μέσα στην εγκατάσταση Graphify, οπότε εγκαταστήστε το Graphify μόνιμα (`uv tool install graphifyy` ή `pipx install graphifyy`, όχι `uvx`), επανεκκινήστε το Pi μετά την εγκατάσταση ή την αναβάθμιση, και αφαιρέστε το με `graphify pi guard uninstall`. Επιθεωρούνται μόνο τοπικοί στόχοι αρχείων· το hook χρειάζεται το `graphify` σε μια απόλυτη καταχώρηση `PATH` εκτός του έργου, περιορίζεται σε κλήση δύο δευτερολέπτων, 256 KiB-in/64 KiB-out, και αποτυγχάνει ανοιχτά (fails open). Το ίδιο πακέτο φορτώνεται επίσης στο [Oh My Pi](https://github.com/can1357/oh-my-pi): `omp plugin install "$(graphify pi guard path)"`. Η καταχωρημένη διαδρομή περιέχει την έκδοση Python και το venv, οπότε εκτελέστε ξανά το `graphify pi guard install` μετά την αλλαγή οποιουδήποτε από τα δύο, και αφαιρέστε την παλιά καταχώρηση με `pi remove <old path>`.

> Το Codex χρησιμοποιεί `$graphify` αντί για `/graphify`.

</details>

<details>
<summary><b>Προαιρετικά extras</b> (εγκαταστήστε μόνο ό,τι χρειάζεστε)</summary>

| Extra | Τι προσθέτει | Εγκατάσταση |
|---|---|---|
| `pdf` | εξαγωγή PDF | `uv tool install "graphifyy[pdf]"` |
| `office` | υποστήριξη `.docx` και `.xlsx` | `uv tool install "graphifyy[office]"` |
| `google` | απόδοση Google Sheets | `uv tool install "graphifyy[google]"` |
| `video` | μεταγραφή βίντεο/ήχου (faster-whisper + yt-dlp) | `uv tool install "graphifyy[video]"` |
| `mcp` | διακομιστής MCP stdio | `uv tool install "graphifyy[mcp]"` |
| `neo4j` | υποστήριξη push Neo4j | `uv tool install "graphifyy[neo4j]"` |
| `falkordb` | υποστήριξη push FalkorDB | `uv tool install "graphifyy[falkordb]"` |
| `svg` | εξαγωγή γράφου SVG | `uv tool install "graphifyy[svg]"` |
| `leiden` | εντοπισμός κοινοτήτων Leiden (graspologic σε Python < 3.13· εγγενές backend σε 3.13+) | `uv tool install "graphifyy[leiden]"` |
| `ollama` | τοπική εξαγωγή συμπερασμάτων Ollama | `uv tool install "graphifyy[ollama]"` |
| `openai` | OpenAI / APIs συμβατά με OpenAI | `uv tool install "graphifyy[openai]"` |
| `gemini` | API Google Gemini | `uv tool install "graphifyy[gemini]"` |
| `anthropic` | API Anthropic Claude (`--backend claude`, χρησιμοποιεί `ANTHROPIC_API_KEY`) | `uv tool install "graphifyy[anthropic]"` |
| `bedrock` | AWS Bedrock (χρησιμοποιεί IAM, χωρίς κλειδί API) | `uv tool install "graphifyy[bedrock]"` |
| `azure` | Azure OpenAI Service (`--backend azure`, χρησιμοποιεί `AZURE_OPENAI_API_KEY` + `AZURE_OPENAI_ENDPOINT`) | `uv tool install "graphifyy[openai]"` |
| `sql` | εξαγωγή σχήματος SQL | `uv tool install "graphifyy[sql]"` |
| `postgres` | ζωντανή ενδοσκόπηση PostgreSQL (`--postgres DSN`) | `uv tool install "graphifyy[postgres]"` |
| `dm` | εξαγωγή AST BYOND DreamMaker `.dm`/`.dme` (μπορεί να χρειαστεί μεταγλωττιστής C + `python3-dev` αν δεν ταιριάζει wheel με την πλατφόρμα σας) | `uv tool install "graphifyy[dm]"` |
| `terraform` | εξαγωγή AST Terraform / HCL `.tf`/`.tfvars`/`.hcl` | `uv tool install "graphifyy[terraform]"` |
| `pascal` | εξαγωγή AST Pascal / Delphi `.pas`/`.dpr`/`.dpk`/`.inc` (πιο ακριβείς ακμές `calls`/`inherits`· επιστρέφει σε έναν εξαγωγέα regex όταν απουσιάζει) | `uv tool install "graphifyy[pascal]"` |
| `ocaml` | εξαγωγή AST OCaml `.ml`/`.mli` | `uv tool install "graphifyy[ocaml]"` |
| `commonlisp` | εξαγωγή AST Common Lisp `.lisp`/`.cl`/`.lsp`/`.asd` | `uv tool install "graphifyy[commonlisp]"` |
| `robot` | εξαγωγή Robot Framework `.robot`/`.resource` (σουίτες, test cases, keywords, ακμές keyword-call και resource/library import) | `uv tool install "graphifyy[robot]"` |
| `chinese` | κατάτμηση ερωτημάτων κινεζικών (jieba) | `uv tool install "graphifyy[chinese]"` |
| `all` | Όλα τα παραπάνω | `uv tool install "graphifyy[all]"` |

</details>

---

## Κάντε τον βοηθό σας να χρησιμοποιεί πάντα τον γράφο

Εκτελέστε το μία φορά στο έργο σας αφού κατασκευάσετε έναν γράφο:

Εκτελέστε `graphify <platform> install` μία φορά στο έργο σας, για παράδειγμα `graphify claude install` ή `graphify codex install` (ή `graphify install --platform <name>`).

Αυτό γράφει ένα μικρό αρχείο ρυθμίσεων που λέει στον βοηθό σας να συμβουλεύεται τον γράφο γνώσης για ερωτήσεις σχετικά με τη βάση κώδικα, προτιμώντας οριοθετημένα ερωτήματα όπως `graphify query "<question>"` αντί να διαβάζει την πλήρη αναφορά ή να κάνει grep σε ακατέργαστα αρχεία.

- **Πλατφόρμες hook** (Claude Code, Gemini CLI): ένα hook ενεργοποιείται αυτόματα πριν από κλήσεις εργαλείων τύπου αναζήτησης (και, στο Claude Code, πριν από την ανάγνωση αρχείων πηγής ένα προς ένα μέσω των εργαλείων Read/Glob) και ωθεί τον βοηθό σας προς τη διαδρομή του γράφου.
- **Πλατφόρμες αρχείων οδηγιών** (Codex, OpenCode, Cursor, κ.λπ.): μόνιμα αρχεία οδηγιών (`AGENTS.md`, `.cursor/rules/`, κ.λπ.) παρέχουν την ίδια καθοδήγηση query-first.

Το `GRAPH_REPORT.md` παραμένει διαθέσιμο για ευρύ έλεγχο αρχιτεκτονικής.

Ακριβώς ποια αρχεία γράφει κάθε πλατφόρμα (το `CODEBUDDY.md` + `PreToolUse` hooks του CodeBuddy, το `AGENTS.md` του Codex, το εγγενές plugin `.kilo` του Kilo, ο κανόνας `alwaysApply` του Cursor, κ.ο.κ.) καλύπτεται στο **[Always-on setup](https://docs.graphify.com/guides/always-on)**.

Για να αφαιρέσετε το graphify από όλες τις πλατφόρμες ταυτόχρονα: `graphify uninstall` (προσθέστε `--purge` για να διαγράψετε επίσης το `graphify-out/`). Ή χρησιμοποιήστε την εντολή ανά πλατφόρμα (π.χ. `graphify claude uninstall`).

### CLI skills ή οδηγίες MCP;

Οι οδηγίες που εγκαθίστανται από το `graphify install` και αυτές που παρέχονται με μια σύνδεση Graphify MCP περιγράφουν διαφορετικούς τρόπους ερωτήματος ενός γράφου:

| Ρύθμιση | Οδηγίες προς χρήση | Πρόσβαση ερωτημάτων |
|---|---|---|
| Τοπικό CLI και εγκατεστημένο skill βοηθού | Οι οδηγίες πλατφόρμας που γράφει το `graphify install` | Εκτελέστε `graphify query`, `graphify path`, και `graphify explain` πάνω στον τοπικό γράφο (`graphify-out/` από προεπιλογή). |
| Συνδεδεμένος διακομιστής Graphify MCP | Οι οδηγίες της σύνδεσης και τα εργαλεία που παραθέτει αυτός ο διακομιστής | Καλέστε τα παρατιθέμενα εργαλεία MCP πάνω στον γράφο που εξυπηρετεί αυτή η σύνδεση. Τα ονόματα και οι περιγραφές των εργαλείων προέρχονται από τον διακομιστή. |

Και οι δύο ενθαρρύνουν οριοθετημένα ερωτήματα γράφου πριν από ευρείες αναζητήσεις πηγαίου κώδικα. Επιλέξτε τις οδηγίες που ταιριάζουν με τα εργαλεία στα οποία έχει πραγματικά πρόσβαση ο βοηθός σας· κανένα από τα δύο μπλοκ δεν θεσπίζει έναν καθολικό κανόνα προτεραιότητας για τα αρχεία οδηγιών του βοηθού σας. Αν χρησιμοποιείτε και τις δύο ενσωματώσεις, προσδιορίστε ποιον γράφο ρωτά η καθεμία και επιλέξτε μια κύρια διαδρομή ερωτημάτων αντί να αντιγράψετε δύο άνευ όρων μπλοκ οδηγιών στο `AGENTS.md`.

Το `graphify install` εγκαθιστά την τοπική ενσωμάτωση βοηθού· δεν δημιουργεί σύνδεση MCP. Ένας πελάτης MCP δεν χρειάζεται να εκτελεί τοπικά ερωτήματα CLI για να χρησιμοποιήσει τον συνδεδεμένο διακομιστή του. Ένας τοπικά φιλοξενούμενος διακομιστής εξακολουθεί να χρειάζεται τη δική του εγκατάσταση Graphify και γράφο, ενώ μια φιλοξενούμενη σύνδεση μπορεί να εξυπηρετεί έναν γράφο που δεν υπάρχει στον κατάλογο εργασίας του πελάτη. Αν λείπουν τα αναμενόμενα εργαλεία, ελέγξτε τη σχετική εγκατάσταση CLI ή τη σύνδεση MCP αντί να αντιμετωπίζετε τις οδηγίες της άλλης ρύθμισης ως εναλλάξιμες.

---

## Τι περιέχει η αναφορά

Το `GRAPH_REPORT.md` συνοψίζει τους god nodes, τις κοινότητες, και τις βασικές διαδρομές για ευρύ έλεγχο αρχιτεκτονικής. Πώς κατασκευάζεται ο γράφος και τι περιέχει: **[How graphify works](https://docs.graphify.com/concepts/architecture)**.

---

## Ποια αρχεία χειρίζεται: ~40 languages

Το graphify αναλύει ~40 γλώσσες προγραμματισμού τοπικά με tree-sitter AST, και χαρτογραφεί έγγραφα, PDF, εικόνες, και ήχο/βίντεο μέσω ενός προαιρετικού σημασιολογικού περάσματος. Πλήρης λίστα: **[Supported inputs](https://docs.graphify.com/concepts/supported-inputs)**.

---

## Συνηθισμένες εντολές

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

Δείτε την [πλήρη αναφορά εντολών](#full-command-reference) παρακάτω.

---

## Αγνόηση αρχείων

Το graphify τηρεί το `.gitignore` και υποστηρίζει μοτίβα `--exclude` και ένα `.graphifyignore` έργου. Λεπτομέρειες: **[Configuration](https://docs.graphify.com/reference/configuration)**.


## Διαμόρφωση έργου

Δημιουργήστε ένα `.graphifyrc` στη ρίζα σάρωσης για ρυθμίσεις που ανήκουν στο έργο αντί σε μία εκτέλεση. Ένα `key=value` ανά γραμμή· οι γραμμές που αρχίζουν με `#` είναι σχόλια.

**Ασαφείς επεκτάσεις.** Ορισμένες επεκτάσεις σημαίνουν διαφορετικές γλώσσες σε διαφορετικά έργα: το `.inc` είναι PHP στο pfSense, Pascal σε ένα δέντρο Delphi, SQL ή assembly αλλού· το `.h` είναι C ή C++· το `.m` είναι Objective-C ή MATLAB. Το graphify πρέπει να επιλέξει μία καθολική προεπιλογή, και όταν επιλέξει λάθος το αρχείο δεν αποτυγχάνει: αναλύεται ως λάθος γλώσσα και αποδίδει μια χούφτα συμπτωματικών κόμβων, οπότε ο γράφος φαίνεται γεμάτος ενώ τα πραγματικά σύμβολα λείπουν. Δηλώστε τι σημαίνει η επέκταση στο repo σας:

```
# .graphifyrc
# A language name:
language.inc=php
# Or an extension graphify already knows:
language.tpl=.ts
# Baked into the git hooks (see Team setup):
viz_node_limit=0
```

Η δήλωση διαπερνά την ταξινόμηση, την επιλογή εξαγωγέα, τη γραμματική και την επίλυση, τα imports, το `graphify watch`, και την κρυφή μνήμη AST (ένα αρχείο που αναλύεται ξανά υπό διαφορετική γλώσσα δεν επαναχρησιμοποιεί ποτέ την παλιά καταχώρηση), και το ίδιο `.graphifyrc` διαβάζεται από τα `extract`, `update`, τα hooks, τον διακομιστή MCP, και το skill `/graphify`. Ένα τυπογραφικό λάθος αναφέρεται μία φορά στο stderr και η σάρωση συνεχίζεται με τις προεπιλογές. Πώς αλληλεπιδρούν οι δηλώσεις με την κρυφή μνήμη, τις σταδιακές ανακατασκευές, και την επίλυση imports: **[Configuration](https://docs.graphify.com/reference/configuration)**.

---

## Ρύθμιση ομάδας

Κάντε commit ή μοιραστείτε τον γράφο ώστε όλη η ομάδα σας να ρωτά το ίδιο πλαίσιο, και ελέγξτε pull requests με πλαίσιο γράφου. Δείτε **[Share context with your team](https://docs.graphify.com/guides/team-workflows)** και **[Review pull requests](https://docs.graphify.com/guides/pull-requests)**.

---

## Χρήση του γράφου απευθείας

Πέρα από τον βοηθό AI σας, ρωτήστε το `graph.json` απευθείας από το CLI με `graphify query`, `graphify path`, και `graphify explain`. Ένα όνομα που ταιριάζει με πολλούς κόμβους απορρίπτεται με τους υποψηφίους να παρατίθενται αντί να γίνεται εικασία. Τα σενάρια μπορούν να διαβάσουν το αποτέλεσμα από τον κωδικό εξόδου: `0` μια απάντηση, `3` ένα ασαφές όνομα, `4` κανένας κόμβος που να ταιριάζει. Δείτε **[Ask better graph questions](https://docs.graphify.com/guides/querying)** και την **[query reference](https://docs.graphify.com/reference/query)**.

---

## Μεταβλητές περιβάλλοντος

Τα backends, τα κλειδιά API, η συμπεριφορά hook, και η ρύθμιση ελέγχονται από μεταβλητές περιβάλλοντος. Πλήρης πίνακας: **[Configuration](https://docs.graphify.com/reference/configuration)**.

---

## Απόρρητο

- **Αρχεία κώδικα**: επεξεργάζονται τοπικά μέσω tree-sitter. Τίποτα δεν φεύγει από το μηχάνημά σας. Ένα σώμα μόνο κώδικα δεν απαιτεί κλειδί API: το `graphify extract` εκτελείται πλήρως εκτός σύνδεσης. Σε ένα μικτό repo, προσθέστε `--code-only` για να ευρετηριάσετε μόνο τον κώδικα και να παραλείψετε τα έγγραφα/PDF/εικόνες που διαφορετικά θα χρειάζονταν ένα LLM.
- **Βίντεο / ήχος**: μεταγράφονται τοπικά με faster-whisper. Τίποτα δεν φεύγει από το μηχάνημά σας.
- **Έγγραφα, PDF, εικόνες**: αποστέλλονται στον βοηθό AI σας για σημασιολογική εξαγωγή (μέσω του skill `/graphify`, χρησιμοποιώντας όποιο μοντέλο εκτελεί η συνεδρία IDE σας). Το headless `graphify extract` απαιτεί `GEMINI_API_KEY` / `GOOGLE_API_KEY` (Gemini), `MOONSHOT_API_KEY` (Kimi), `ANTHROPIC_API_KEY` (Claude), `OPENAI_API_KEY` (OpenAI), `DEEPSEEK_API_KEY` (DeepSeek), μια εκτελούμενη εγκατάσταση Ollama (`OLLAMA_BASE_URL`), διαπιστευτήρια AWS μέσω της τυπικής αλυσίδας παρόχων (Bedrock - δεν χρειάζεται κλειδί API, χρησιμοποιεί IAM), ή το δυαδικό CLI `claude` (Claude Code - δεν χρειάζεται κλειδί API, χρησιμοποιεί τη συνδρομή Claude σας). Η σημαία `--dedup-llm` χρησιμοποιεί το ίδιο κλειδί.
- **Τοποθεσία δεδομένων**: το `graphify extract` εντοπίζει αυτόματα ποιον πάροχο να χρησιμοποιήσει με βάση το ποιο κλειδί API έχει οριστεί (προτεραιότητα: Gemini → Kimi → Claude → OpenAI → DeepSeek → Azure → Bedrock → Ollama). Για κώδικα με απαιτήσεις τοποθεσίας δεδομένων, χρησιμοποιήστε `--backend ollama` (πλήρως τοπικό) ή περάστε μια ρητή σημαία `--backend`. Το Kimi (`MOONSHOT_API_KEY`) δρομολογεί σε διακομιστές Moonshot AI στην Κίνα.
- **Χωρίς τηλεμετρία**, χωρίς παρακολούθηση χρήσης, χωρίς analytics.
- **Καταγραφή ερωτημάτων**: κάθε κλήση `graphify query`, `graphify path`, `graphify explain`, και MCP `query_graph` καταγράφεται στο `~/.cache/graphify-queries.log` σε μορφή JSON Lines (χρονοσήμανση, ερώτηση, σώμα, κόμβοι που επιστράφηκαν, διάρκεια). Οι πλήρεις αποκρίσεις υπογράφου **δεν** αποθηκεύονται από προεπιλογή. Ορίστε `GRAPHIFY_QUERY_LOG_DISABLE=1` για εξαίρεση, ή `GRAPHIFY_QUERY_LOG=/dev/null` για σίγαση χωρίς απενεργοποίηση της διαδρομής κώδικα.

---

## Αντιμετώπιση προβλημάτων

Συνηθισμένα προβλήματα εγκατάστασης και εξαγωγής και οι λύσεις τους: **[Troubleshooting](https://docs.graphify.com/troubleshooting)**.

---

## Full command reference

Κάθε εντολή και σημαία, με παραδείγματα: **[CLI reference](https://docs.graphify.com/reference/overview)**.

---

## Μάθετε περισσότερα

- [docs.graphify.com](https://docs.graphify.com): πλήρης τεκμηρίωση: οδηγοί, αναφορά εντολών, και ενσωματώσεις
- [How it works](../how-it-works.md): ο αγωγός εξαγωγής, ο εντοπισμός κοινοτήτων, η βαθμολόγηση εμπιστοσύνης, τα benchmarks
- [ARCHITECTURE.md](../../ARCHITECTURE.md): ανάλυση modules, πώς να προσθέσετε μια γλώσσα
- [Optional integrations](../docker-mcp-sqlite.md): Docker MCP Toolkit + SQLite
- [The Memory Layer](https://safishamsi.gumroad.com/l/qetvlo): το βιβλίο για τις ιδέες πίσω από το graphify, την αρχιτεκτονική από άκρη σε άκρη

---

## Graphify Cloud

Το [**Graphify Cloud**](https://app.graphify.com/login) είναι το πάντα ενεργό επίπεδο που είναι χτισμένο πάνω στο graphify. Αντί για έναν γράφο που ανακατασκευάζετε κατ' απαίτηση ανά φάκελο, διατηρεί έναν ζωντανό γράφο σε ολόκληρο τον κύκλο ζωής ανάπτυξης λογισμικού σας:

- **80% λιγότερα tokens**: η πάντα ενεργή μνήμη σημαίνει ότι οι agent σας σταματούν να ξαναδιαβάζουν και να ξαναεξηγούν τη βάση κώδικα σε κάθε συνεδρία.
- **Monorepo και cross-repo**: ένας συνδεδεμένος γράφος σε κάθε υπηρεσία και αποθετήριο, όχι ένας γράφος ανά φάκελο.
- **Τυπική επαλήθευση**: ελέγξτε αρχιτεκτονικές και εξαρτησιακές αναλλοίωτες έναντι του ζωντανού γράφου.
- **Έλεγχος κώδικα με πανοραμική εικόνα του SDLC σας**: δείτε πώς μια αλλαγή διαδίδεται σε όλο το σύστημα πριν κάνετε merge.
- **Connectors SDLC**: ενσωματώστε Sentry, Jira, και άλλα, ώστε τα συμβάντα, τα tickets, και ο κώδικας να ζουν σε έναν γράφο.
- **Πάντα ενεργό**: ενημερώνεται συνεχώς στο παρασκήνιο σε κώδικα, έγγραφα, και συσκέψεις.

**[Ξεκινήστε μια δωρεάν δοκιμή 14 ημερών στο app.graphify.com &rarr;](https://app.graphify.com/login)**

---

## Συνεισφορά

Οι συνεισφορές είναι ευπρόσδεκτες. Δείτε το **[CONTRIBUTING.md](../../CONTRIBUTING.md)** για τη ρύθμιση ανάπτυξης, τις εντολές test και CI-parity, τη ροή εργασίας git, και τι κάνει μια ισχυρή συνεισφορά (τα δουλεμένα παραδείγματα και οι αναφορές σφαλμάτων εξαγωγής είναι τα πιο χρήσιμα). Αρχιτεκτονική και πώς να προσθέσετε μια γλώσσα: [ARCHITECTURE.md](../../ARCHITECTURE.md).

Νέοι εδώ; Πείτε ένα γεια στο [Discord](https://discord.gg/XDnKVpzdXB) ή στα [GitHub Discussions](https://github.com/Graphify-Labs/graphify/discussions).

---

## Συνεισφέροντες

<a href="https://github.com/Graphify-Labs/graphify/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=Graphify-Labs/graphify" alt="graphify contributors" />
</a>

Φτιάχτηκε με [contrib.rocks](https://contrib.rocks).

---

## Μεταφράσεις

Το README είναι διαθέσιμο σε 32 γλώσσες. Χρησιμοποιήστε τον επιλογέα γλώσσας στην κορυφή αυτού του αρχείου για να το διαβάσετε στη δική σας, ή περιηγηθείτε στο [`docs/translations/`](./). Για να βελτιώσετε μια μετάφραση ή να προσθέσετε μια νέα, ανοίξτε ένα pull request στο αντίστοιχο αρχείο εκεί.

---

## Building on graphify

Φτιάχνετε κάτι στο οικοσύστημα graphify; Αυτό ενθαρρύνεται. Αν το έργο σας χρησιμοποιεί το "graphify" στο όνομά του (για παράδειγμα `graphify-dashboard` ή `graphify-action`), προσθέστε μια σύντομη σημείωση στο README σας διευκρινίζοντας ότι είναι community-built και δεν σχετίζεται ούτε υποστηρίζεται από τη Graphify Labs. Το "graphify" και το λογότυπο graphify είναι σήματα της Graphify Labs· παρακαλούμε μην τα χρησιμοποιείτε με τρόπο που υπονοεί επίσημη ιδιότητα.

---

## Κοινότητα και σύνδεσμοι

<p align="center">
  <a href="https://graphify.com"><img src="https://img.shields.io/badge/Website-graphify.com-4c1?style=flat&logo=googlechrome&logoColor=white" alt="Website"/></a>
  <a href="https://discord.gg/XDnKVpzdXB"><img src="https://img.shields.io/badge/Discord-Join-5865F2?style=flat&logo=discord&logoColor=white" alt="Discord"/></a>
  <a href="https://x.com/graphify"><img src="https://img.shields.io/badge/X-graphify-000000?logo=x&logoColor=white" alt="X"/></a>
  <a href="https://www.youtube.com/@graphifylabs"><img src="https://img.shields.io/badge/YouTube-Graphify%20Labs-FF0000?style=flat&logo=youtube&logoColor=white" alt="YouTube"/></a>
  <a href="https://github.com/sponsors/safishamsi"><img src="https://img.shields.io/badge/sponsor-safishamsi-ea4aaa?logo=github-sponsors" alt="Sponsor"/></a>
  <a href="https://safishamsi.gumroad.com/l/qetvlo"><img src="https://img.shields.io/badge/Book-The%20Memory%20Layer-2ea44f?style=flat&logo=gitbook&logoColor=white" alt="The Memory Layer"/></a>
</p>
