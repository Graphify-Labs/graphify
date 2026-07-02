#!/usr/bin/env node
"use strict";

const SCAN_KINDS = [
  { subdir: "entities", pageType: "entity", applicable: true },
  { subdir: "topics", pageType: "topic", applicable: true },
  { subdir: "sources", pageType: "source", applicable: true },
  { subdir: "comparisons", pageType: "comparison", applicable: true },
  { subdir: "queries", pageType: "query", applicable: false },
  { subdir: "synthesis", pageType: "synthesis", applicable: false }
];

function sortedUnique(values) {
  return Array.from(new Set(values)).sort();
}

function extractFrontmatter(text) {
  if (!text.startsWith("---\n") && !text.startsWith("---\r\n")) {
    return { hasFrontmatter: false, frontmatter: "", body: text };
  }

  const match = text.match(/^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)([\s\S]*)$/);
  if (!match) {
    return { hasFrontmatter: false, frontmatter: "", body: text };
  }

  return {
    hasFrontmatter: true,
    frontmatter: match[1],
    body: match[2]
  };
}

function normalizeSourceToken(token) {
  const trimmed = String(token || "").trim();
  if (!trimmed) return null;

  let value = trimmed;
  if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
    value = value.slice(1, -1).trim();
  }

  return value || null;
}

function parseInlineSources(raw) {
  const trimmed = raw.trim();
  if (trimmed === "[]") return { ok: true, values: [] };
  if (!(trimmed.startsWith("[") && trimmed.endsWith("]"))) {
    return { ok: false, values: [] };
  }

  const inner = trimmed.slice(1, -1).trim();
  if (!inner) return { ok: true, values: [] };

  const values = inner
    .split(",")
    .map(normalizeSourceToken)
    .filter(Boolean);

  return { ok: true, values };
}

function parseSourcesFrontmatter(frontmatter) {
  if (!frontmatter) {
    return { hasField: false, parsed: false, sources: [], signalAvailable: false };
  }

  const lines = frontmatter.split(/\r?\n/);

  for (let index = 0; index < lines.length; index += 1) {
    const match = lines[index].match(/^sources:\s*(.*)$/);
    if (!match) continue;

    const rest = match[1].trim();
    if (rest) {
      if (!rest.startsWith("[")) {
        const single = normalizeSourceToken(rest);
        return {
          hasField: true,
          parsed: Boolean(single),
          sources: single ? [single] : [],
          signalAvailable: Boolean(single)
        };
      }

      const parsedInline = parseInlineSources(rest);
      return {
        hasField: true,
        parsed: parsedInline.ok,
        sources: parsedInline.ok ? sortedUnique(parsedInline.values) : [],
        signalAvailable: parsedInline.ok && parsedInline.values.length > 0
      };
    }

    const collected = [];
    let parsed = true;
    let consumed = 0;

    for (let cursor = index + 1; cursor < lines.length; cursor += 1) {
      const line = lines[cursor];
      if (!line.trim()) {
        consumed += 1;
        continue;
      }
      if (/^[^\s-]/.test(line)) break;
      const itemMatch = line.match(/^\s*-\s*(.+)$/);
      if (!itemMatch) {
        parsed = false;
        consumed += 1;
        continue;
      }
      const token = normalizeSourceToken(itemMatch[1]);
      if (token) collected.push(token);
      consumed += 1;
    }

    index += consumed;
    return {
      hasField: true,
      parsed,
      sources: parsed ? sortedUnique(collected) : [],
      signalAvailable: parsed && collected.length > 0
    };
  }

  return { hasField: false, parsed: false, sources: [], signalAvailable: false };
}

function evaluateSourceSignalEligibility({ pageType, frontmatter }) {
  const kind = SCAN_KINDS.find((k) => k.pageType === pageType);
  if (!kind || !kind.applicable) {
    return { eligible: false, reason: "not_applicable", sources: [] };
  }

  const parsed = parseSourcesFrontmatter(frontmatter);

  if (!parsed.hasField) {
    return { eligible: false, reason: "missing_sources", sources: [] };
  }
  if (!parsed.parsed) {
    return { eligible: false, reason: "invalid_sources", sources: [] };
  }
  if (parsed.sources.length === 0) {
    return { eligible: false, reason: "empty_sources", sources: [] };
  }

  return { eligible: true, reason: "ok", sources: parsed.sources };
}

module.exports = {
  SCAN_KINDS,
  extractFrontmatter,
  evaluateSourceSignalEligibility,
  normalizeSourceToken,
  parseSourcesFrontmatter,
  sortedUnique
};
