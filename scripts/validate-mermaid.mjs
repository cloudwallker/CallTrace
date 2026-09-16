import { readFile, readdir } from 'node:fs/promises';
import { join } from 'node:path';
import { JSDOM } from 'jsdom';

const dom = new JSDOM('<!doctype html><html><body></body></html>');
globalThis.window = dom.window;
globalThis.document = dom.window.document;
const { default: mermaid } = await import('mermaid');
mermaid.initialize({ startOnLoad: false, securityLevel: 'strict' });

async function* files(directory) {
  for (const entry of (await readdir(directory, { withFileTypes: true })).sort((a, b) => a.name.localeCompare(b.name))) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) yield* files(path);
    else if (entry.name.endsWith('.mmd')) yield path;
  }
}
let count = 0;
for await (const path of files(process.argv[2] || 'artifacts/mermaid')) {
  const result = await mermaid.parse(await readFile(path, 'utf8'));
  if (result.diagramType !== 'sequence') throw new Error(`Unexpected diagram type in ${path}`);
  count++;
}
if (!count) throw new Error('No Mermaid files found; validation would be vacuous');
console.log(`Validated ${count} diagrams with Mermaid 11.12.0`);
