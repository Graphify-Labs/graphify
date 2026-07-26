import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

import { build } from 'esbuild';

const directory = await mkdtemp(resolve(tmpdir(), 'graphify-svelte-schema-'));
try {
  const output = resolve(directory, 'schema-corpus.mjs');
  await build({
    entryPoints: [resolve('test/schema-corpus.ts')],
    bundle: true,
    platform: 'node',
    format: 'esm',
    target: 'node18',
    outfile: output,
    logLevel: 'silent',
  });
  await import(pathToFileURL(output).href);
} finally {
  await rm(directory, { recursive: true, force: true });
}
