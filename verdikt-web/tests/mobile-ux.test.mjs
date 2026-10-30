import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

// Mobile UX regressions: the stylesheet rules themselves are the deliverable here,
// so they are guarded the same way nginx.conf is (read the file, check the rule).
const globalCss = await readFile(new URL('../src/styles/global.css', import.meta.url), 'utf8');
const cabinetCss = await readFile(new URL('../src/cabinet/cabinet.css', import.meta.url), 'utf8');

test('touch taps on controls neither flash the platform highlight nor select labels', () => {
  const rule = globalCss.match(/:where\(button, a, select, summary[^}]*\}/)?.[0] ?? '';
  assert.match(rule, /-webkit-tap-highlight-color:\s*transparent/);
  assert.match(rule, /-webkit-touch-callout:\s*none/);
  assert.match(rule, /user-select:\s*none/);
});

test('busy buttons carry a clipped sweep overlay, light surfaces sweep with shade', () => {
  assert.match(globalCss, /@keyframes btn-sweep/);
  assert.match(globalCss, /button\[data-loading='true'\]\s*\{[^}]*overflow:\s*hidden/);
  const overlay = globalCss.match(/button\[data-loading='true'\]::after\s*\{[^}]*\}/)?.[0] ?? '';
  assert.match(overlay, /animation:\s*btn-sweep/);
  assert.match(overlay, /pointer-events:\s*none/);
  assert.match(globalCss, /button\[data-loading='true'\]:where\(\.btn-soft, \.btn-line, \.btn-danger\)::after/);
});

test('the delete dialog stacks confirm over cancel full-width on phones', () => {
  const mobile = cabinetCss.match(/@media \(max-width: 480px\) \{[\s\S]*?\n\}/)?.[0] ?? '';
  assert.match(mobile, /\.delete-chat-actions\s*\{[^}]*flex-direction:\s*column/);
  assert.match(mobile, /\.delete-chat-actions > button\s*\{\s*width:\s*100%/);
});
