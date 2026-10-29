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
import { BusyButton } from './src/components/UiState';
import { TextDocument } from './src/cabinet/TextDocument';
        import { renderToStaticMarkup } from 'react-dom/server';
        import { ChatTimeline } from './src/cabinet/ChatTimeline';
        import { DocumentPanel } from './src/cabinet/DocumentPanel';
        import { Composer } from './src/cabinet/Composer';
        import { NewCaseScreen, ThreadScreen, SentenceDetails } from './src/cabinet/screens';
        import { CaseSkeleton } from './src/cabinet/CaseSkeleton';
        import { AuthGate } from './src/auth/AuthGate';
        import { InfoPage } from './src/info/InfoPage';
        import { CaseWorkflow } from './src/landing/Hero';
        import { DeleteChatDialog } from './src/cabinet/DeleteChatDialog';
        import { Sidebar } from './src/cabinet/Sidebar';
        import { Footer } from './src/landing/Sections';
        export const render = (name, props) => renderToStaticMarkup(createElement({SentenceDetails, BusyButton, TextDocument, ChatTimeline, DocumentPanel, Composer, NewCaseScreen, ThreadScreen, CaseSkeleton, AuthGate, InfoPage, CaseWorkflow, Footer, Sidebar, DeleteChatDialog}[name], props));
      `,
      resolveDir: fileURLToPath(new URL('../..', import.meta.url)), loader: 'tsx',
    },
    external: ['pdfjs-dist'],
    bundle: true, platform: 'node', format: 'cjs', jsx: 'automatic',
    loader: {'.css': 'empty'}, outfile,
  });
  render = createRequire(import.meta.url)(outfile).render;
} finally { await rm(dir, {recursive: true, force: true}); }
