import {
  createMarkdownDocument,
  extractMetadataFromHtml,
  formatMetadataYaml,
  type ConversionResult,
  type PageMetadata,
  isYouTubeUrl,
} from "./markdown-conversion-shared.js";
import { tryDefuddleConversion } from "./defuddle-converter.js";
import {
  convertWithLegacyExtractor,
  scoreMarkdownQuality,
  shouldCompareWithLegacy,
} from "./legacy-converter.js";

export type { ConversionResult, PageMetadata };
export { createMarkdownDocument, formatMetadataYaml };

export const absolutizeUrlsScript = String.raw`
(function() {
  const baseUrl = document.baseURI || location.href;
  const htmlClone = document.documentElement.cloneNode(true);

  function materializeShadowDom(sourceRoot, cloneRoot) {
    const sourceElements = Array.from(sourceRoot.querySelectorAll("*"));
    const cloneElements = Array.from(cloneRoot.querySelectorAll("*"));

    for (let i = sourceElements.length - 1; i >= 0; i--) {
      const sourceEl = sourceElements[i];
      const cloneEl = cloneElements[i];
      const shadowRoot = sourceEl && sourceEl.shadowRoot;
      if (!shadowRoot || !cloneEl || !shadowRoot.innerHTML) continue;

      if (cloneEl.tagName && cloneEl.tagName.includes("-")) {
        const wrapper = document.createElement("div");
        wrapper.setAttribute("data-shadow-host", cloneEl.tagName.toLowerCase());
        wrapper.innerHTML = shadowRoot.innerHTML;
        cloneEl.replaceWith(wrapper);
      } else {
        cloneEl.innerHTML = shadowRoot.innerHTML;
      }
    }
  }

  function toAbsolute(url) {
    if (!url) return url;
    try { return new URL(url, baseUrl).href; } catch { return url; }
  }

  function absAttr(root, sel, attr) {
    root.querySelectorAll(sel).forEach(el => {
      const v = el.getAttribute(attr);
      if (v) {
        const a = toAbsolute(v);
        if (a) el.setAttribute(attr, a);
      }
    });
  }

  function absSrcset(root, sel) {
    root.querySelectorAll(sel).forEach(el => {
      const s = el.getAttribute("srcset");
      if (!s) return;
      el.setAttribute("srcset", s.split(",").map(p => {
        const t = p.trim();
        if (!t) return "";
        const [url, ...d] = t.split(/\s+/);
        return d.length ? toAbsolute(url) + " " + d.join(" ") : toAbsolute(url);
      }).filter(Boolean).join(", "));
    });
  }

  materializeShadowDom(document.documentElement, htmlClone);

  htmlClone.querySelectorAll("img[data-src], video[data-src], audio[data-src], source[data-src]").forEach(el => {
    const ds = el.getAttribute("data-src");
    if (ds && (!el.getAttribute("src") || el.getAttribute("src") === "" || el.getAttribute("src")?.startsWith("data:"))) {
      el.setAttribute("src", ds);
    }
  });

  absAttr(htmlClone, "a[href]", "href");
  absAttr(htmlClone, "img[src], video[src], audio[src], source[src], iframe[src]", "src");
  absAttr(htmlClone, "video[poster]", "poster");
  absSrcset(htmlClone, "img[srcset], source[srcset]");

  return { html: "<!doctype html>\n" + htmlClone.outerHTML };
})()
`;

function shouldPreferDefuddle(result: ConversionResult): boolean {
  if (isYouTubeUrl(result.metadata.url)) {
    return true;
  }

  const transcript = result.variables?.transcript?.trim();
  if (transcript) {
    return true;
  }

  return /^##?\s+transcript\b/im.test(result.markdown);
}

export async function extractContent(html: string, url: string): Promise<ConversionResult> {
  const capturedAt = new Date().toISOString();
  const baseMetadata = extractMetadataFromHtml(html, url, capturedAt);

  const defuddleResult = await tryDefuddleConversion(html, url, baseMetadata);
  if (defuddleResult.ok) {
    if (shouldPreferDefuddle(defuddleResult.result)) {
      return defuddleResult.result;
    }

    if (shouldCompareWithLegacy(defuddleResult.result.markdown)) {
      const legacyResult = convertWithLegacyExtractor(html, baseMetadata);
      const legacyScore = scoreMarkdownQuality(legacyResult.markdown);
      const defuddleScore = scoreMarkdownQuality(defuddleResult.result.markdown);

      if (legacyScore > defuddleScore + 120) {
        return {
          ...legacyResult,
          fallbackReason: "Legacy extractor produced higher-quality markdown than Defuddle",
        };
      }
    }

    return defuddleResult.result;
  }

  const fallbackResult = convertWithLegacyExtractor(html, baseMetadata);
  return {
    ...fallbackResult,
    fallbackReason: defuddleResult.reason,
  };
}
