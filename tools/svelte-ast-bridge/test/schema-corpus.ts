import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';

import { walk } from 'estree-walker';
import type { Node as EstreeNode } from 'estree';
import { parse, VERSION } from 'svelte/compiler';

import {
  structuralNodePolicy,
  templateNodePolicy,
  type SchemaPolicy,
} from '../src/schema-policy.js';

const here = resolve(process.cwd(), 'test');
const fixtures = ['modern.svelte', 'legacy-elements.svelte'];
const seenTemplate = new Set<string>();
const seenStructural = new Set<string>();

function observeTemplate(type: string): void {
  if (Object.hasOwn(templateNodePolicy, type)) seenTemplate.add(type);
}

for (const fixture of fixtures) {
  const path = resolve(here, 'fixtures', fixture);
  const source = await readFile(path, 'utf8');
  const ast = parse(source, { filename: path, modern: true });
  observeTemplate(ast.type);
  seenStructural.add(ast.fragment.type);
  if (ast.module) seenStructural.add(ast.module.type);
  if (ast.instance) seenStructural.add(ast.instance.type);
  walk(ast.fragment as unknown as EstreeNode, {
    enter(node) { observeTemplate(node.type); },
  });
}

function validatePolicy(
  family: string,
  policy: Readonly<Record<string, SchemaPolicy>>,
  seen: ReadonlySet<string>,
): void {
  const missing = Object.entries(policy)
    .filter(([type, requirement]) => requirement === 'fixture' && !seen.has(type))
    .map(([type]) => type);
  const unexpectedIntermediate = Object.entries(policy)
    .filter(([type, requirement]) => requirement === 'intermediate' && seen.has(type))
    .map(([type]) => type);
  const unknown = [...seen].filter((type) => !Object.hasOwn(policy, type));
  if (missing.length || unexpectedIntermediate.length || unknown.length) {
    throw new Error([
      `Svelte ${VERSION} ${family} schema corpus policy failed.`,
      missing.length ? `missing fixture variants: ${missing.join(', ')}` : '',
      unexpectedIntermediate.length
        ? `intermediate variants appeared in final AST: ${unexpectedIntermediate.join(', ')}`
        : '',
      unknown.length ? `fixture-only names outside pinned schema: ${unknown.join(', ')}` : '',
    ].filter(Boolean).join(' '));
  }
}

validatePolicy('template', templateNodePolicy, seenTemplate);
validatePolicy('structural', structuralNodePolicy, seenStructural);

process.stdout.write(
  `Svelte ${VERSION} schema corpus covers ${seenTemplate.size} template and `
  + `${seenStructural.size} structural author AST variants.\n`,
);
