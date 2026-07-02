import { Readability } from "@mozilla/readability";
import TurndownService from "turndown";
import { gfm } from "turndown-plugin-gfm";

import {
  type AnyRecord,
  type ConversionResult,
  type PageMetadata,
  GOOD_CONTENT_LENGTH,
  MIN_CONTENT_LENGTH,
  extractPublishedTime,
  extractTextFromHtml,
  extractTitle,
  normalizeMarkdown,
  parseDocument,
  pickString,
  sanitizeHtml,
} from "./markdown-conversion-shared.js";

interface ExtractionCandidate {
  title: string | null;
  byline: string | null;
  excerpt: string | null;
  published: string | null;
  html: string | null;
  textContent: string;
  method: string;
}

const CONTENT_SELECTORS = [
  "article",
  "main article",
  "[role='main'] article",
  "[itemprop='articleBody']",
  ".article-content",
  ".article-body",
  ".post-content",
  ".entry-content",
  ".story-body",
  "main",
  "[role='main']",
  "#content",
  ".content",
];

const REMOVE_SELECTORS = [
  "script",
  "style",
  "noscript",
  "template",
  "iframe",
  "svg",
  "path",
  "nav",
  "aside",
  "footer",
  "header",
  "form",
  ".advertisement",
  ".ads",
  ".social-share",
  ".related-articles",
  ".comments",
  ".newsletter",
  ".cookie-banner",
  ".cookie-consent",
  "[role='navigation']",
  "[aria-label*='cookie' i]",
];

const NEXT_DATA_CONTENT_PATHS = [
  "props.pageProps.content.body",
  "props.pageProps.article.body",
  "props.pageProps.article.content",
  "props.pageProps.post.body",
  "props.pageProps.post.content",
  "props.pageProps.data.body",
  "props.pageProps.story.body.content",
];

const LOW_QUALITY_MARKERS = [
  /Join The Conversation/i,
  /One Community\. Many Voices/i,
  /Read our community guidelines/i,
  /Create a free account to share your thoughts/i,
  /Become a Forbes Member/i,
  /Subscribe to trusted journalism/i,
  /\bComments\b/i,
];

function generateExcerpt(excerpt: string | null, textContent: string | null): string | null {
  if (excerpt) return excerpt;
  if (!textContent) return null;
  const trimmed = textContent.trim();
  if (!trimmed) return null;
  return trimmed.length > 200 ? `${trimmed.slice(0, 200)}...` : trimmed;
}

function parseJsonLdItem(item: AnyRecord): ExtractionCandidate | null {
  const type = Array.isArray(item["@type"]) ? item["@type"][0] : item["@type"];
  if (typeof type !== "string" || !["Article", "NewsArticle", "BlogPosting", "WebPage", "ReportageNewsArticle"].includes(type)) {
    return null;
  }

  const rawContent =
    (typeof item.articleBody === "string" && item.articleBody) ||
    (typeof item.text === "string" && item.text) ||
    (typeof item.description === "string" && item.description) ||
    null;

  if (!rawContent) return null;

  const content = rawContent.trim();
  const htmlLike = /<\/?[a-z][\s\S]*>/i.test(content);
  const textContent = htmlLike ? extractTextFromHtml(content) : content;

  if (textContent.length < MIN_CONTENT_LENGTH) return null;

  return {
    title: pickString(item.headline, item.name),
    byline: extractAuthorFromJsonLd(item.author),
    excerpt: pickString(item.description),
    published: pickString(item.datePublished, item.dateCreated),
    html: htmlLike ? content : null,
    textContent,
    method: "json-ld",
  };
}

function extractAuthorFromJsonLd(authorData: unknown): string | null {
  if (typeof authorData === "string") return authorData;
  if (!authorData || typeof authorData !== "object") return null;

  if (Array.isArray(authorData)) {
    const names = authorData
      .map((author) => extractAuthorFromJsonLd(author))
      .filter((name): name is string => Boolean(name));
    return names.length > 0 ? names.join(", ") : null;
  }

  const author = authorData as AnyRecord;
  return typeof author.name === "string" ? author.name : null;
}

function flattenJsonLdItems(data: unknown): AnyRecord[] {
  if (!data || typeof data !== "object") return [];
  if (Array.isArray(data)) return data.flatMap(flattenJsonLdItems);

  const item = data as AnyRecord;
  if (Array.isArray(item["@graph"])) {
    return (item["@graph"] as unknown[]).flatMap(flattenJsonLdItems);
  }

  return [item];
}

function tryJsonLdExtraction(document: Document): ExtractionCandidate | null {
  const scripts = document.querySelectorAll("script[type='application/ld+json']");

  for (const script of scripts) {
    try {
      const data = JSON.parse(script.textContent ?? "");
      for (const item of flattenJsonLdItems(data)) {
        const extracted = parseJsonLdItem(item);
        if (extracted) return extracted;
      }
    } catch {
      // Ignore malformed blocks.
    }
  }

  return null;
}

function getByPath(value: unknown, path: string): unknown {
  let current = value;
  for (const part of path.split(".")) {
    if (!current || typeof current !== "object") return undefined;
    current = (current as AnyRecord)[part];
  }
  return current;
}

function isContentBlockArray(value: unknown): value is AnyRecord[] {
  if (!Array.isArray(value) || value.length === 0) return false;
  return value.slice(0, 5).some((item) => {
    if (!item || typeof item !== "object") return false;
    const obj = item as AnyRecord;
    return "type" in obj || "text" in obj || "textHtml" in obj || "content" in obj;
  });
}

function extractTextFromContentBlocks(blocks: AnyRecord[]): string {
  const parts: string[] = [];

  function pushParagraph(text: string): void {
    const trimmed = text.trim();
    if (!trimmed) return;
    parts.push(trimmed, "\n\n");
  }

  function walk(node: unknown): void {
    if (!node || typeof node !== "object") return;
    const block = node as AnyRecord;

    if (typeof block.text === "string") {
      pushParagraph(block.text);
      return;
    }

    if (typeof block.textHtml === "string") {
      pushParagraph(extractTextFromHtml(block.textHtml));
      return;
    }

    if (Array.isArray(block.items)) {
      for (const item of block.items) {
        if (item && typeof item === "object") {
          const text = pickString((item as AnyRecord).text);
          if (text) parts.push(`- ${text}\n`);
        }
      }
      parts.push("\n");
    }

    if (Array.isArray(block.components)) {
      for (const component of block.components) {
        walk(component);
      }
    }

    if (Array.isArray(block.content)) {
      for (const child of block.content) {
        walk(child);
      }
    }
  }

  for (const block of blocks) {
    walk(block);
  }

  return parts.join("").replace(/\n{3,}/g, "\n\n").trim();
}

function tryStringBodyExtraction(
  content: string,
  meta: AnyRecord,
  document: Document,
  method: string
): ExtractionCandidate | null {
  if (!content || content.length < MIN_CONTENT_LENGTH) return null;

  const isHtml = /<\/?[a-z][\s\S]*>/i.test(content);
  const html = isHtml ? sanitizeHtml(content) : null;
  const textContent = isHtml ? extractTextFromHtml(html) : content.trim();

  if (textContent.length < MIN_CONTENT_LENGTH) return null;

  return {
    title: pickString(meta.headline, meta.title, extractTitle(document)),
    byline: pickString(meta.byline, meta.author),
    excerpt: pickString(meta.description, meta.excerpt, generateExcerpt(null, textContent)),
    published: pickString(meta.datePublished, meta.publishedAt, extractPublishedTime(document)),
    html,
    textContent,
    method,
  };
}

function tryNextDataExtraction(document: Document): ExtractionCandidate | null {
  try {
    const script = document.querySelector("script#__NEXT_DATA__");
    if (!script?.textContent) return null;

    const data = JSON.parse(script.textContent) as AnyRecord;
    const pageProps = (getByPath(data, "props.pageProps") ?? {}) as AnyRecord;

    for (const path of NEXT_DATA_CONTENT_PATHS) {
      const value = getByPath(data, path);

      if (typeof value === "string") {
        const parentPath = path.split(".").slice(0, -1).join(".");
        const parent = (getByPath(data, parentPath) ?? {}) as AnyRecord;
        const meta = {
          ...pageProps,
          ...parent,
          title: parent.title ?? (pageProps.title as string | undefined),
        };

        const candidate = tryStringBodyExtraction(value, meta, document, "next-data");
        if (candidate) return candidate;
      }

      if (isContentBlockArray(value)) {
        const textContent = extractTextFromContentBlocks(value);
        if (textContent.length < MIN_CONTENT_LENGTH) continue;

        return {
          title: pickString(
            getByPath(data, "props.pageProps.content.headline"),
            getByPath(data, "props.pageProps.article.headline"),
            getByPath(data, "props.pageProps.article.title"),
            getByPath(data, "props.pageProps.post.title"),
            pageProps.title,
            extractTitle(document)
          ),
          byline: pickString(
            getByPath(data, "props.pageProps.author.name"),
            getByPath(data, "props.pageProps.article.author.name")
          ),
          excerpt: pickString(
            getByPath(data, "props.pageProps.content.description"),
            getByPath(data, "props.pageProps.article.description"),
            pageProps.description,
            generateExcerpt(null, textContent)
          ),
          published: pickString(
            getByPath(data, "props.pageProps.content.datePublished"),
            getByPath(data, "props.pageProps.article.datePublished"),
            getByPath(data, "props.pageProps.publishedAt"),
            extractPublishedTime(document)
          ),
          html: null,
          textContent,
          method: "next-data",
        };
      }
    }
  } catch {
    return null;
  }

  return null;
}

function buildReadabilityCandidate(
  article: ReturnType<Readability["parse"]>,
  document: Document,
  method: string
): ExtractionCandidate | null {
  const textContent = article?.textContent?.trim() ?? "";
  if (textContent.length < MIN_CONTENT_LENGTH) return null;

  return {
    title: pickString(article?.title, extractTitle(document)),
    byline: pickString((article as { byline?: string } | null)?.byline),
    excerpt: pickString(article?.excerpt, generateExcerpt(null, textContent)),
    published: pickString((article as { publishedTime?: string } | null)?.publishedTime, extractPublishedTime(document)),
    html: article?.content ? sanitizeHtml(article.content) : null,
    textContent,
    method,
  };
}

function tryReadability(document: Document): ExtractionCandidate | null {
  try {
    const strictClone = document.cloneNode(true) as Document;
    const strictResult = buildReadabilityCandidate(
      new Readability(strictClone).parse(),
      document,
      "readability"
    );
    if (strictResult) return strictResult;

    const relaxedClone = document.cloneNode(true) as Document;
    return buildReadabilityCandidate(
      new Readability(relaxedClone, { charThreshold: 120 }).parse(),
      document,
      "readability-relaxed"
    );
  } catch {
    return null;
  }
}

function trySelectorExtraction(document: Document): ExtractionCandidate | null {
  for (const selector of CONTENT_SELECTORS) {
    const element = document.querySelector(selector);
    if (!element) continue;

    const clone = element.cloneNode(true) as Element;
    for (const removeSelector of REMOVE_SELECTORS) {
      for (const node of clone.querySelectorAll(removeSelector)) {
        node.remove();
      }
    }

    const html = sanitizeHtml(clone.innerHTML);
    const textContent = extractTextFromHtml(html);
    if (textContent.length < MIN_CONTENT_LENGTH) continue;

    return {
      title: extractTitle(document),
      byline: null,
      excerpt: generateExcerpt(null, textContent),
      published: extractPublishedTime(document),
      html,
      textContent,
      method: `selector:${selector}`,
    };
  }

  return null;
}

function tryBodyExtraction(document: Document): ExtractionCandidate | null {
  const body = document.body;
  if (!body) return null;

  const clone = body.cloneNode(true) as Element;
  for (const removeSelector of REMOVE_SELECTORS) {
    for (const node of clone.querySelectorAll(removeSelector)) {
      node.remove();
    }
  }

  const html = sanitizeHtml(clone.innerHTML);
  const textContent = extractTextFromHtml(html);
  if (!textContent) return null;

  return {
    title: extractTitle(document),
    byline: null,
    excerpt: generateExcerpt(null, textContent),
    published: extractPublishedTime(document),
    html,
    textContent,
    method: "body-fallback",
  };
}

function pickBestCandidate(candidates: ExtractionCandidate[]): ExtractionCandidate | null {
  if (candidates.length === 0) return null;

  const methodOrder = [
    "readability",
    "readability-relaxed",
    "next-data",
    "json-ld",
    "selector:",
    "body-fallback",
  ];

  function methodRank(method: string): number {
    const idx = methodOrder.findIndex((entry) =>
      entry.endsWith(":") ? method.startsWith(entry) : method === entry
    );
    return idx === -1 ? methodOrder.length : idx;
  }

  const ranked = [...candidates].sort((a, b) => {
    const rankA = methodRank(a.method);
    const rankB = methodRank(b.method);
    if (rankA !== rankB) return rankA - rankB;
    return (b.textContent.length ?? 0) - (a.textContent.length ?? 0);
  });

  for (const candidate of ranked) {
    if (candidate.textContent.length >= GOOD_CONTENT_LENGTH) {
      return candidate;
    }
  }

  for (const candidate of ranked) {
    if (candidate.textContent.length >= MIN_CONTENT_LENGTH) {
      return candidate;
    }
  }

  return ranked[0];
}

function extractFromHtml(html: string): ExtractionCandidate | null {
  const document = parseDocument(html);

  const readabilityCandidate = tryReadability(document);
  const nextDataCandidate = tryNextDataExtraction(document);
  const jsonLdCandidate = tryJsonLdExtraction(document);
  const selectorCandidate = trySelectorExtraction(document);
  const bodyCandidate = tryBodyExtraction(document);

  const candidates = [
    readabilityCandidate,
    nextDataCandidate,
    jsonLdCandidate,
    selectorCandidate,
    bodyCandidate,
  ].filter((candidate): candidate is ExtractionCandidate => Boolean(candidate));

  const winner = pickBestCandidate(candidates);
  if (!winner) return null;

  return {
    ...winner,
    title: winner.title ?? extractTitle(document),
    published: winner.published ?? extractPublishedTime(document),
    excerpt: winner.excerpt ?? generateExcerpt(null, winner.textContent),
  };
}

const turndown = new TurndownService({
  headingStyle: "atx",
  hr: "---",
  bulletListMarker: "-",
  codeBlockStyle: "fenced",
  emDelimiter: "*",
  strongDelimiter: "**",
  linkStyle: "inlined",
});

turndown.use(gfm);
turndown.remove(["script", "style", "iframe", "noscript", "template", "svg", "path"]);

turndown.addRule("collapseFigure", {
  filter: "figure",
  replacement(content) {
    return `\n\n${content.trim()}\n\n`;
  },
});

turndown.addRule("dropInvisibleAnchors", {
  filter(node) {
    return node.nodeName === "A" && !(node as Element).textContent?.trim();
  },
  replacement() {
    return "";
  },
});

function convertHtmlToMarkdown(html: string): string {
  if (!html || !html.trim()) return "";

  try {
    const sanitized = sanitizeHtml(html);
    return turndown.turndown(sanitized);
  } catch {
    return "";
  }
}

function fallbackPlainText(html: string): string {
  const document = parseDocument(html);
  for (const selector of ["script", "style", "noscript", "template", "iframe", "svg", "path"]) {
    for (const el of document.querySelectorAll(selector)) {
      el.remove();
    }
  }
  const text = document.body?.textContent ?? document.documentElement?.textContent ?? "";
  return normalizeMarkdown(text.replace(/\s+/g, " "));
}

function countBylines(markdown: string): number {
  return (markdown.match(/(^|\n)By\s+/g) || []).length;
}

function countUsefulParagraphs(markdown: string): number {
  const paragraphs = normalizeMarkdown(markdown).split(/\n{2,}/);
  let count = 0;

  for (const paragraph of paragraphs) {
    const trimmed = paragraph.trim();
    if (!trimmed) continue;
    if (/^!?\[[^\]]*\]\([^)]+\)$/.test(trimmed)) continue;
    if (/^#{1,6}\s+/.test(trimmed)) continue;
    if ((trimmed.match(/\b[\p{L}\p{N}']+\b/gu) || []).length < 8) continue;
    count++;
  }

  return count;
}

function countMarkerHits(markdown: string, markers: RegExp[]): number {
  let hits = 0;
  for (const marker of markers) {
    if (marker.test(markdown)) hits++;
  }
  return hits;
}

export function scoreMarkdownQuality(markdown: string): number {
  const normalized = normalizeMarkdown(markdown);
  const wordCount = (normalized.match(/\b[\p{L}\p{N}']+\b/gu) || []).length;
  const usefulParagraphs = countUsefulParagraphs(normalized);
  const headingCount = (normalized.match(/^#{1,6}\s+/gm) || []).length;
  const markerHits = countMarkerHits(normalized, LOW_QUALITY_MARKERS);
  const bylineCount = countBylines(normalized);
  const staffCount = (normalized.match(/\bForbes Staff\b/gi) || []).length;

  return (
    Math.min(wordCount, 4000) +
    usefulParagraphs * 40 +
    headingCount * 10 -
    markerHits * 180 -
    Math.max(0, bylineCount - 1) * 120 -
    Math.max(0, staffCount - 1) * 80
  );
}

export function shouldCompareWithLegacy(markdown: string): boolean {
  const normalized = normalizeMarkdown(markdown);
  return (
    countMarkerHits(normalized, LOW_QUALITY_MARKERS) > 0 ||
    countBylines(normalized) > 1 ||
    countUsefulParagraphs(normalized) < 6
  );
}

export function convertWithLegacyExtractor(html: string, baseMetadata: PageMetadata): ConversionResult {
  const extracted = extractFromHtml(html);

  let markdown = extracted?.html ? convertHtmlToMarkdown(extracted.html) : "";
  if (!markdown.trim()) {
    markdown = extracted?.textContent?.trim() || fallbackPlainText(html);
  }

  return {
    metadata: {
      ...baseMetadata,
      title: pickString(extracted?.title, baseMetadata.title) ?? "",
      description: pickString(extracted?.excerpt, baseMetadata.description) ?? undefined,
      author: pickString(extracted?.byline, baseMetadata.author) ?? undefined,
      published: pickString(extracted?.published, baseMetadata.published) ?? undefined,
    },
    markdown: normalizeMarkdown(markdown),
    rawHtml: html,
    conversionMethod: extracted ? `legacy:${extracted.method}` : "legacy:plain-text",
  };
}
