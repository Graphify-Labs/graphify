import { build } from 'esbuild';
import { access, readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const output = resolve(here, '../../graphify/vendor/svelte_ast_bridge.mjs');
const result = await build({
  absWorkingDir: here,
  entryPoints: [resolve(here, 'src/bridge.ts')],
  bundle: true,
  platform: 'node',
  format: 'esm',
  target: 'node18',
  outfile: output,
  legalComments: 'eof',
  metafile: true,
  banner: {
    js: [
      "import { createRequire as __graphifyCreateRequire } from 'node:module';",
      "import { fileURLToPath as __graphifyFileURLToPath } from 'node:url';",
      "import { dirname as __graphifyDirname } from 'node:path';",
      "const require = __graphifyCreateRequire(import.meta.url);",
      "const __filename = __graphifyFileURLToPath(import.meta.url);",
      "const __dirname = __graphifyDirname(__filename);",
    ].join(' '),
  },
});

async function packageRoot(input) {
  let current = dirname(resolve(here, input));
  const dependencyRoot = resolve(here, 'node_modules');
  while (current.startsWith(dependencyRoot)) {
    try {
      await access(resolve(current, 'package.json'));
      return current;
    } catch {
      current = dirname(current);
    }
  }
  return null;
}

const packages = new Map();
for (const input of Object.keys(result.metafile.inputs)) {
  if (!input.includes('node_modules/')) continue;
  const root = await packageRoot(input);
  if (!root) continue;
  const manifest = JSON.parse(await readFile(resolve(root, 'package.json'), 'utf8'));
  packages.set(`${manifest.name}@${manifest.version}`, { root, manifest });
}

const notices = [
  'Third-party notices for graphify/vendor/svelte_ast_bridge.mjs',
  'Generated from tools/svelte-ast-bridge/package-lock.json.',
];
for (const [identity, { root, manifest }] of [...packages].sort(([a], [b]) => a.localeCompare(b))) {
  let license = null;
  for (const candidate of ['LICENSE', 'LICENSE.md', 'LICENSE.txt', 'license']) {
    try {
      license = (await readFile(resolve(root, candidate), 'utf8')).trim();
      break;
    } catch {
      // Try the next conventional published license filename.
    }
  }
  license ??= (
    `The published package declares ${manifest.license ?? 'no'} license but does not include a `
    + `license file. Upstream repository: ${manifest.repository?.url ?? 'not declared'}`
  );
  notices.push(
    '',
    '='.repeat(78),
    `${identity} (${manifest.license ?? 'license not declared'})`,
    '='.repeat(78),
    license,
  );
}
await writeFile(`${output}.NOTICES.txt`, `${notices.join('\n')}\n`, 'utf8');
