import { JSDOM, VirtualConsole } from "jsdom";
import { Defuddle } from "defuddle/node";

import {
  type ConversionResult,
  type PageMetadata,
  isMarkdownUsable,
  normalizeMarkdown,
  pickString,
} from "./markdown-conversion-shared.js";

export async function tryDefuddleConversion(
  html: string,
  url: string,
  baseMetadata: PageMetadata
): Promise<{ ok: true; result: ConversionResult } | { ok: false; reason: string }> {
  try {
    const virtualConsole = new VirtualConsole();
    virtualConsole.on("jsdomError", (error: Error & { type?: string }) => {
      if (error.type === "css parsing" || /Could not parse CSS stylesheet/i.test(error.message)) {
        return;
      }
      console.warn(`[url-to-markdown] jsdom: ${error.message}`);
    });

    const dom = new JSDOM(html, { url, virtualConsole });
    const result = await Defuddle(dom, url, { markdown: true });
    const markdown = normalizeMarkdown(result.content || "");

    if (!isMarkdownUsable(markdown, html)) {
      return { ok: false, reason: "Defuddle returned empty or incomplete markdown" };
    }

    return {
      ok: true,
      result: {
        metadata: {
          ...baseMetadata,
          title: pickString(result.title, baseMetadata.title) ?? "",
          description: pickString(result.description, baseMetadata.description) ?? undefined,
          author: pickString(result.author, baseMetadata.author) ?? undefined,
          published: pickString(result.published, baseMetadata.published) ?? undefined,
          coverImage: pickString(result.image, baseMetadata.coverImage) ?? undefined,
          language: pickString(result.language, baseMetadata.language) ?? undefined,
        },
        markdown,
        rawHtml: html,
        conversionMethod: "defuddle",
        variables: result.variables,
      },
    };
  } catch (error) {
    return {
      ok: false,
      reason: error instanceof Error ? error.message : String(error),
    };
  }
}
