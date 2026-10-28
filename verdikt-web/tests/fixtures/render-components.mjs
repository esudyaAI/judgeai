import { build } from 'esbuild';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

// Render real components to verify loading/finished states without a live API.
const dir = await mkdtemp(join(tmpdir(), 'judgeai-loading-'));
export let render;
try {
  const outfile = join(dir, 'render.cjs');
  await build({
    stdin: {
      contents: `
        import { createElement } from 'react';
        import { renderToStaticMarkup } from 'react-dom/server';
        import { Composer } from './src/cabinet/Composer';
        import { ThreadScreen } from './src/cabinet/screens';
        import { AuthGate } from './src/auth/AuthGate';
        import { InfoPage } from './src/info/InfoPage';
        import { CaseWorkflow } from './src/landing/Hero';
        import { Sidebar } from './src/cabinet/Sidebar';
        import { Footer } from './src/landing/Sections';
        export const render = (name, props) => renderToStaticMarkup(createElement({Composer, ThreadScreen, AuthGate, InfoPage, CaseWorkflow, Footer, Sidebar}[name], props));
      `,
      resolveDir: fileURLToPath(new URL('../..', import.meta.url)), loader: 'tsx',
    },
    bundle: true, platform: 'node', format: 'cjs', jsx: 'automatic',
    loader: {'.css': 'empty'}, outfile,
  });
  render = createRequire(import.meta.url)(outfile).render;
} finally { await rm(dir, {recursive: true, force: true}); }
