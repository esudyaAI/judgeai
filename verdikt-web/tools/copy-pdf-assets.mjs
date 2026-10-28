import { cp, mkdir, readFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const {version} = JSON.parse(await readFile(resolve(root, 'node_modules/pdfjs-dist/package.json'), 'utf8'));
const destination = resolve(root, 'public/pdfjs', version);
for (const folder of ['cmaps', 'standard_fonts', 'wasm']) {
  const target = resolve(destination, folder);
  await mkdir(target, {recursive:true});
  await cp(resolve(root, 'node_modules/pdfjs-dist', folder), target, {recursive:true});
}
await cp(resolve(root, 'node_modules/pdfjs-dist/LICENSE'), resolve(destination, 'LICENSE'));
await cp(resolve(root, 'node_modules/pdfjs-dist/build/pdf.worker.min.mjs'), resolve(destination, 'pdf.worker.min.mjs'));
