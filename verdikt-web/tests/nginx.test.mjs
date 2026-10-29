import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

// Production regression: the pdf.js module worker was served as application/octet-stream,
// so browsers refused it and no PDF or Word preview opened in the document panel.
test('nginx serves pdf.js modules and wasm with their MIME types', async () => {
  const conf = await readFile(new URL('../nginx.conf', import.meta.url), 'utf8');
  const block = conf.match(/location \/pdfjs\/ \{[\s\S]*?\n    \}/)?.[0] ?? '';
  assert.match(block, /text\/javascript\s+js\s+mjs;/);
  assert.match(block, /application\/wasm\s+wasm;/);
});
