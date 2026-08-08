<p align="center">
  <a href="https://graphifylabs.ai"><img src="https://raw.githubusercontent.com/safishamsi/graphify/v4/docs/logo-text.svg" width="260" height="64" alt="Graphify"/></a>
</p>

<p align="center">
  🇺🇸 <a href="../../README.md">English</a> | 🇨🇳 <a href="README.zh-CN.md">简体中文</a> | 🇯🇵 <a href="README.ja-JP.md">日本語</a> | 🇰🇷 <a href="README.ko-KR.md">한국어</a> | 🇩🇪 <a href="README.de-DE.md">Deutsch</a> | 🇫🇷 <a href="README.fr-FR.md">Français</a> | 🇪🇸 <a href="README.es-ES.md">Español</a> | 🇮🇳 <a href="README.hi-IN.md">हिन्दी</a> | 🇧🇷 <a href="README.pt-BR.md">Português</a> | 🇷🇺 <a href="README.ru-RU.md">Русский</a> | 🇸🇦 <a href="README.ar-SA.md">العربية</a> | 🇮🇷 <a href="README.fa-IR.md">فارسی</a> | 🇮🇹 <a href="README.it-IT.md">Italiano</a> | 🇵🇱 <a href="README.pl-PL.md">Polski</a> | 🇳🇱 <a href="README.nl-NL.md">Nederlands</a> | 🇹🇷 <a href="README.tr-TR.md">Türkçe</a> | 🇺🇦 <a href="README.uk-UA.md">Українська</a> | 🇻🇳 <a href="README.vi-VN.md">Tiếng Việt</a> | 🇮🇩 <a href="README.id-ID.md">Bahasa Indonesia</a> | 🇸🇪 <a href="README.sv-SE.md">Svenska</a> | 🇬🇷 <a href="README.el-GR.md">Ελληνικά</a> | 🇷🇴 <a href="README.ro-RO.md">Română</a> | 🇨🇿 <a href="README.cs-CZ.md">Čeština</a> | 🇫🇮 <a href="README.fi-FI.md">Suomi</a> | 🇩🇰 <a href="README.da-DK.md">Dansk</a> | 🇳🇴 <a href="README.no-NO.md">Norsk</a> | 🇭🇺 <a href="README.hu-HU.md">Magyar</a> | 🇹🇭 <a href="README.th-TH.md">ภาษาไทย</a> | 🇺🇿 <a href="README.uz-UZ.md">Oʻzbekcha</a> | 🇹🇼 <a href="README.zh-TW.md">繁體中文</a> | 🇵🇭 <a href="README.fil-PH.md">Filipino</a>
</p>

<p align="center">
  <a href="https://www.ycombinator.com/companies/graphify"><img src="https://img.shields.io/badge/Y%20Combinator-S26%20D%C3%B6nemi-F0652F?style=flat&logo=ycombinator&logoColor=white" alt="YC S26"/></a>
  <a href="https://discord.gg/598Ad9zQZ"><img src="https://img.shields.io/badge/Discord-Kat%C4%B1l-5865F2?style=flat&logo=discord&logoColor=white" alt="Discord'a Katıl"/></a>
  <a href="https://safishamsi.gumroad.com/l/qetvlo"><img src="https://img.shields.io/badge/Kitap-The%20Memory%20Layer-2ea44f?style=flat&logo=gitbook&logoColor=white" alt="Kitap: The Memory Layer"/></a>
  <a href="https://github.com/safishamsi/graphify/actions/workflows/ci.yml"><img src="https://github.com/safishamsi/graphify/actions/workflows/ci.yml/badge.svg?branch=v8" alt="CI Durumu"/></a>
  <a href="https://pypi.org/project/graphifyy/"><img src="https://img.shields.io/pypi/v/graphifyy" alt="PyPI Sürümü"/></a>
  <a href="https://pepy.tech/project/graphifyy"><img src="https://img.shields.io/pepy/dt/graphifyy?color=blue&label=%C4%B0ndirme" alt="İndirme Sayısı"/></a>
  <a href="https://github.com/sponsors/safishamsi"><img src="https://img.shields.io/badge/Sponsor%20Ol-safishamsi-ea4aaa?logo=github-sponsors" alt="Sponsor Ol"/></a>
  <a href="https://www.linkedin.com/company/graphify-labs"><img src="https://img.shields.io/badge/LinkedIn-Graphify%20Labs-0077B5?logo=linkedin" alt="LinkedIn Sayfası"/></a>
  <a href="https://x.com/graphifyy"><img src="https://img.shields.io/badge/X-graphifyy-000000?logo=x&logoColor=white" alt="X Hesabı"/></a>
</p>

**Yapay zeka kod asistanları için bir beceri (skill).** Claude Code, Codex, OpenCode, Kilo Code, Cursor, Antigravity CLI (Gemini CLI), GitHub Copilot CLI, VS Code Copilot Chat, Aider, Amp, OpenClaw, Factory Droid, Trae, Hermes, Kimi Code, Kiro, Pi, Devin CLI veya Google Antigravity'de `/graphify` yazın — projenizi (kodlar, belgeler, PDF'ler, görseller ve videolar) dosyalar arasında arama yapmak (grep) yerine sorgulayabileceğiniz bir bilgi grafiğine (knowledge graph) dönüştürür. Kod tabanını daha hızlı anlayın. Mimari kararların arkasındaki "neden"leri keşfedin.

Tamamen çok modlu (multimodal). Kod, PDF, markdown, ekran görüntüleri, diyagramlar, beyaz tahta fotoğrafları, farklı dillerdeki görsel metinleri veya video ve ses dosyalarını ekleyin — graphify her şeyden kavramları ve ilişkileri çıkarır ve bunları tek bir grafikte birleştirir. Videolar yerel olarak Whisper (faster-whisper) ile metne dönüştürülür. tree-sitter AST aracılığıyla 25 programlama dilini destekler.

> Andrej Karpathy; makaleleri, tweetleri, ekran görüntülerini ve notları biriktirdiği bir `/raw` klasörü tutar. graphify bu probleme yönelik bir çözümdür — ham dosyaları doğrudan okumaya kıyasla sorgu başına **71,5 kat** daha az token tüketir ve oturumlar arasında kalıcıdır.

```
/graphify .
```

```
graphify-out/
├── graph.html       etkileşimli grafik — herhangi bir tarayıcıda açın (tıklayın, filtreleyin, arayın)
├── GRAPH_REPORT.md  özet rapor — merkezi düğümler (god nodes), şaşırtıcı bağlantılar, önerilen sorular
├── graph.json       tüm grafik — dosyaları yeniden okumadan istediğiniz zaman sorgulayın
└── cache/           SHA256 önbelleği — tekrarlanan çalışmalarda yalnızca değiştirilen dosyaları işler
```

## Nasıl Çalışır?

graphify üç aşamada çalışır. İlk olarak, deterministik bir AST analiziyle LLM kullanmadan kod dosyalarından yapısal bilgileri çıkarır. Ardından, video ve ses dosyaları `faster-whisper` ile yerel olarak metne dönüştürülür. Son olarak, paralel çalışan Claude alt ajanları (subagents) belgeleri, makaleleri, görselleri ve transkriptleri analiz eder. Elde edilen tüm veriler bir NetworkX grafiğinde birleştirilir, Leiden algoritması ile kümelenir; etkileşimli HTML, sorgulanabilir JSON ve bir analiz raporu olarak dışa aktarılır.

Her ilişki `EXTRACTED` (çıkarılan), `INFERRED` (tahmin edilen - güven puanıyla birlikte) veya `AMBIGUOUS` (belirsiz) olarak etiketlenir. Böylece hangi verinin doğrudan belgeden alındığını, hangisinin model tarafından tahmin edildiğini bilirsiniz.

## Kurulum

**Gereksinimler:** Python 3.10+ ve uyumlu bir yapay zeka asistanı ([Claude Code](https://claude.ai/code), [Codex](https://openai.com/codex), [OpenCode](https://opencode.ai), [Cursor](https://cursor.com) vb.)

```bash
uv tool install graphifyy && graphify install
# veya pipx ile
pipx install graphifyy && graphify install
# veya pip ile
pip install graphifyy && graphify install
```

> **Resmi Paket:** PyPI üzerindeki paket adı `graphifyy` şeklindedir (çift 'y' ile). Diğer `graphify*` isimli paketlerin bu projeyle bağlantısı yoktur. CLI komutu ise yine `graphify` olarak çağrılır.

## Kullanım

```bash
/graphify .                        # Mevcut dizinde çalıştırır
/graphify ./raw                    # Belirtilen dizinde çalıştırır
/graphify ./raw --update           # Sadece değişen dosyaları günceller
/graphify query "Attention'ı optimizer'a ne bağlıyor?"
/graphify path "DigestAuth" "Response"
graphify hook install              # Git hook'larını yükler (commit sonrası otomatik güncelleme)
graphify update ./src
```

## Ne Elde Edersiniz?

* **Merkezi Düğümler (God Nodes):** En yüksek bağlantı derecesine sahip, sistemin kalbinde yer alan kavramlar.
* **Şaşırtıcı Bağlantılar:** İlgi/ilişki puanına göre sıralanmış beklenmedik ilişkiler.
* **Önerilen Sorular:** Grafiğin benzersiz şekilde cevaplayabildiği 4-5 soru önerisi.
* **"Neden" (Tasarım Gerekçeleri):** Docstring'ler, kod içi açıklamalar (`# NOTE:`, `# WHY:`) ve dokümanlardaki tasarım gerekçeleri `rationale_for` düğümleri olarak çıkarılır. Sadece kodun "ne" yaptığını değil, "neden" öyle yazıldığını da anlarsınız.
* **Token Kıyaslaması (Token Benchmark):** Karma projelerde sorgu başına **71,5 kat** daha az token kullanımı sağlar. İlk çalıştırmadan sonraki sorgularda doğrudan sıkıştırılmış grafiği okuduğu için token tasarrufu sağlar.

## Gizlilik ve Güvenlik

* **Kod Dosyaları:** Tamamen yerel olarak tree-sitter AST aracılığıyla işlenir. Kod içerikleriniz dışarı gönderilmez. Sadece kod içeren projelerde API anahtarı gerekmeden tamamen çevrimdışı (`graphify extract`) çalışabilir.
* **Video / Ses:** Yerel olarak `faster-whisper` ile dönüştürülür. Cihazınızdan dışarı hiçbir veri çıkmaz.
* **Dokümanlar, PDF'ler ve Görseller:** Anlamsal çıkarım için yapay zeka asistanınızın kullandığı API modeline gönderilir.
* **Telemetri Yok:** Herhangi bir kullanım takibi, analiz veya telemetri verisi toplanmaz.

## graphify Üzerine İnşa Edildi: Penpax

[**Penpax**](https://safishamsi.github.io/penpax.ai), graphify tabanlı kurumsal yönetim katmanıdır. **Yakında ücretsiz deneme sürümüyle yayında.** [Bekleme listesine katılın →](https://safishamsi.github.io/penpax.ai)

<p align="center">
  <a href="https://star-history.com/#safishamsi/graphify&Date">
    <img src="https://api.star-history.com/svg?repos=safishamsi/graphify&type=Date" alt="Star History Chart" width="370"/>
  </a>
</p>
