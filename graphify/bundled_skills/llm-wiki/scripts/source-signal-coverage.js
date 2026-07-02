#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");
const {
  SCAN_KINDS,
  extractFrontmatter,
  evaluateSourceSignalEligibility
} = require("./lib/source-signal-eligibility");

function scanWiki(wikiRoot) {
  const wikiDir = path.join(wikiRoot, "wiki");
  if (!fs.existsSync(wikiDir)) {
    console.error(`ERROR: wiki 目录不存在：${wikiDir}`);
    process.exit(1);
  }

  const pages = [];
  const summary = {
    applicable_total: 0,
    ok: 0,
    missing_sources: 0,
    empty_sources: 0,
    invalid_sources: 0,
    not_applicable: 0
  };

  for (const kind of SCAN_KINDS) {
    const dir = path.join(wikiDir, kind.subdir);
    if (!fs.existsSync(dir)) continue;

    const files = fs.readdirSync(dir)
      .filter((f) => f.endsWith(".md"))
      .sort();

    for (const file of files) {
      const id = path.basename(file, ".md");
      if (["index", "log", "purpose", ".wiki-schema", "README"].includes(id)) continue;

      const filePath = path.join(dir, file);
      const raw = fs.readFileSync(filePath, "utf8");
      const { frontmatter } = extractFrontmatter(raw);
      const result = evaluateSourceSignalEligibility({
        pageType: kind.pageType,
        frontmatter
      });

      pages.push({
        path: path.relative(wikiRoot, filePath),
        id,
        pageType: kind.pageType,
        eligible: result.eligible,
        reason: result.reason,
        sourceCount: result.sources.length
      });

      summary[result.reason] += 1;
      if (result.reason !== "not_applicable") {
        summary.applicable_total += 1;
      }
    }
  }

  return { summary, pages };
}

function main(argv) {
  if (argv.length < 3) {
    console.error("Usage: node scripts/source-signal-coverage.js <wiki_root>");
    process.exit(1);
  }

  const wikiRoot = path.resolve(argv[2]);
  const result = scanWiki(wikiRoot);
  console.log(JSON.stringify(result, null, 2));
}

if (require.main === module) {
  main(process.argv);
}

module.exports = { scanWiki };
