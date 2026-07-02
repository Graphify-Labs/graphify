import { parseHTML } from "linkedom";

export interface PageMetadata {
  url: string;
  title: string;
  description?: string;
  author?: string;
  published?: string;
  coverImage?: string;
  language?: string;
  captured_at: string;
}

export interface ConversionResult {
  metadata: PageMetadata;
  markdown: string;
  rawHtml: string;
  conversionMethod: string;
  fallbackReason?: string;
  variables?: Record<string, string>;
}

export type AnyRecord = Record<string, unknown>;

export const MIN_CONTENT_LENGTH = 120;
export const GOOD_CONTENT_LENGTH = 900;

const PUBLISHED_TIME_SELECTORS = [
  "meta[property='article:published_time']",
  "meta[name='pubdate']",
  "meta[name='publishdate']",
  "meta[name='date']",
  "time[datetime]",
];

const ARTICLE_TYPES = new Set([
  "Article",
  "NewsArticle",
  "BlogPosting",
  "WebPage",
  "ReportageNewsArticle",
]);

export function pickString(...values: unknown[]): string | null {
  for (const value of values) {
    if (typeof value === "string") {
      const trimmed = value.trim();
      if (trimmed) return trimmed;
    }
  }
  return null;
}

export function normalizeMarkdown(markdown: string): string {
  return markdown
    .replace(/\r\n/g, "\n")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

export function parseDocument(html: string): Document {
  const normalized = /<\s*html[\s>]/i.test(html)
    ? html
    : `<!doctype html><html><body>${html}</body></html>`;
  return parseHTML(normalized).document as unknown as Document;
}

export function sanitizeHtml(html: string): string {
  const { document } = parseHTML(`<div id="__root">${html}</div>`);
  const root = document.querySelector("#__root");
  if (!root) return html;

  for (const selector of ["script", "style", "iframe", "noscript", "template", "svg", "path"]) {
    for (const el of root.querySelectorAll(selector)) {
      el.remove();
    }
  }

  return root.innerHTML;
}

export function extractTextFromHtml(html: string): string {
  const { document } = parseHTML(`<!doctype html><html><body>${html}</body></html>`);
  for (const selector of ["script", "style", "noscript", "template", "iframe", "svg", "path"]) {
    for (const el of document.querySelectorAll(selector)) {
      el.remove();
    }
  }
  return document.body?.textContent?.replace(/\s+/g, " ").trim() ?? "";
}

export function getMetaContent(document: Document, names: string[]): string | null {
  for (const name of names) {
    const element =
      document.querySelector(`meta[name="${name}"]`) ??
      document.querySelector(`meta[property="${name}"]`);
    const content = element?.getAttribute("content");
    if (content && content.trim()) return content.trim();
  }
  return null;
}

function normalizeLanguageTag(value: string | null): string | null {
  if (!value) return null;

  const trimmed = value.trim();
  if (!trimmed) return null;

  const primary = trimmed.split(/[,\s;]/, 1)[0]?.trim();
  if (!primary) return null;

  return primary.replace(/_/g, "-");
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

function parseJsonLdScripts(document: Document): AnyRecord[] {
  const results: AnyRecord[] = [];
  const scripts = document.querySelectorAll("script[type='application/ld+json']");

  for (const script of scripts) {
    try {
      const data = JSON.parse(script.textContent ?? "");
      results.push(...flattenJsonLdItems(data));
    } catch {
      // Ignore malformed blocks.
    }
  }

  return results;
}

function isArticleType(item: AnyRecord): boolean {
  const value = Array.isArray(item["@type"]) ? item["@type"][0] : item["@type"];
  return typeof value === "string" && ARTICLE_TYPES.has(value);
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

function extractPrimaryJsonLdMeta(document: Document): Partial<PageMetadata> {
  for (const item of parseJsonLdScripts(document)) {
    if (!isArticleType(item)) continue;

    return {
      title: pickString(item.headline, item.name) ?? undefined,
      description: pickString(item.description) ?? undefined,
      author: extractAuthorFromJsonLd(item.author) ?? undefined,
      published: pickString(item.datePublished, item.dateCreated) ?? undefined,
      coverImage:
        pickString(
          item.image,
          (item.image as AnyRecord | undefined)?.url,
          (Array.isArray(item.image) ? item.image[0] : undefined) as unknown
        ) ?? undefined,
    };
  }

  return {};
}

export function extractPublishedTime(document: Document): string | null {
  for (const selector of PUBLISHED_TIME_SELECTORS) {
    const el = document.querySelector(selector);
    if (!el) continue;
    const value = el.getAttribute("content") ?? el.getAttribute("datetime");
    if (value && value.trim()) return value.trim();
  }
  return null;
}

export function extractTitle(document: Document): string | null {
  const ogTitle = document.querySelector("meta[property='og:title']")?.getAttribute("content");
  if (ogTitle && ogTitle.trim()) return ogTitle.trim();

  const twitterTitle = document.querySelector("meta[name='twitter:title']")?.getAttribute("content");
  if (twitterTitle && twitterTitle.trim()) return twitterTitle.trim();

  const title = document.querySelector("title")?.textContent?.trim();
  if (title) {
    const cleaned = title.split(/\s*[-|–—]\s*/)[0]?.trim();
    if (cleaned) return cleaned;
  }

  const h1 = document.querySelector("h1")?.textContent?.trim();
  return h1 || null;
}

export function extractMetadataFromHtml(html: string, url: string, capturedAt: string): PageMetadata {
  const document = parseDocument(html);
  const jsonLd = extractPrimaryJsonLdMeta(document);
  const timeEl = document.querySelector("time[datetime]");
  const htmlLang = normalizeLanguageTag(document.documentElement?.getAttribute("lang"));
  const metaLanguage = normalizeLanguageTag(
    pickString(
      getMetaContent(document, ["language", "content-language", "og:locale"]),
      document.querySelector("meta[http-equiv='content-language']")?.getAttribute("content")
    )
  );

  return {
    url,
    title:
      pickString(
        getMetaContent(document, ["og:title", "twitter:title"]),
        jsonLd.title,
        document.querySelector("h1")?.textContent,
        document.title
      ) ?? "",
    description:
      pickString(
        getMetaContent(document, ["description", "og:description", "twitter:description"]),
        jsonLd.description
      ) ?? undefined,
    author:
      pickString(
        getMetaContent(document, ["author", "article:author", "twitter:creator"]),
        jsonLd.author
      ) ?? undefined,
    published:
      pickString(
        timeEl?.getAttribute("datetime"),
        getMetaContent(document, ["article:published_time", "datePublished", "publishdate", "date"]),
        jsonLd.published,
        extractPublishedTime(document)
      ) ?? undefined,
    coverImage:
      pickString(
        getMetaContent(document, ["og:image", "twitter:image", "twitter:image:src"]),
        jsonLd.coverImage
      ) ?? undefined,
    language: pickString(htmlLang, metaLanguage) ?? undefined,
    captured_at: capturedAt,
  };
}

export function isMarkdownUsable(markdown: string, html: string): boolean {
  const normalized = normalizeMarkdown(markdown);
  if (!normalized) return false;

  const htmlTextLength = extractTextFromHtml(html).length;
  if (htmlTextLength < MIN_CONTENT_LENGTH) return true;

  if (normalized.length >= 80) return true;
  return normalized.length >= Math.min(200, Math.floor(htmlTextLength * 0.2));
}

export function isYouTubeUrl(url: string): boolean {
  try {
    const hostname = new URL(url).hostname.toLowerCase();
    return hostname === "youtu.be" || hostname.endsWith(".youtube.com") || hostname === "youtube.com";
  } catch {
    return false;
  }
}

function escapeYamlValue(value: string): string {
  return value.replace(/\\/g, "\\\\").replace(/"/g, '\\"').replace(/\r?\n/g, "\\n");
}

export function formatMetadataYaml(meta: PageMetadata): string {
  const lines = ["---"];
  lines.push(`url: ${meta.url}`);
  lines.push(`title: "${escapeYamlValue(meta.title)}"`);
  if (meta.description) lines.push(`description: "${escapeYamlValue(meta.description)}"`);
  if (meta.author) lines.push(`author: "${escapeYamlValue(meta.author)}"`);
  if (meta.published) lines.push(`published: "${escapeYamlValue(meta.published)}"`);
  if (meta.coverImage) lines.push(`coverImage: "${escapeYamlValue(meta.coverImage)}"`);
  if (meta.language) lines.push(`language: "${escapeYamlValue(meta.language)}"`);
  lines.push(`captured_at: "${escapeYamlValue(meta.captured_at)}"`);
  lines.push("---");
  return lines.join("\n");
}

export function createMarkdownDocument(result: ConversionResult): string {
  const yaml = formatMetadataYaml(result.metadata);
  const escapedTitle = result.metadata.title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const titleRegex = new RegExp(`^#\\s+${escapedTitle}\\s*(\\n|$)`, "i");
  const hasTitle = titleRegex.test(result.markdown.trimStart());
  const title = result.metadata.title && !hasTitle ? `\n\n# ${result.metadata.title}\n\n` : "\n\n";
  return yaml + title + result.markdown;
}
