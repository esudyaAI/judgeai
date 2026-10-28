import test from 'node:test';
import assert from 'node:assert/strict';
import { render } from './fixtures/render-components.mjs';

test('analysis composer shows busy sweep and preserves background action; idle has no sweep', () => {
  const props = {files: [], value: '', onChange() {}, onFiles() {}, onSend() {}, onStop() {}};
  const busy = render('Composer', {...props, mode: 'thinking'});
  assert.match(busy, /data-loading="true" aria-busy="true"/);
  assert.match(busy, /aria-label="Продолжить в фоне"/);
  const idle = render('Composer', {...props, mode: 'idle'});
  assert.doesNotMatch(idle, /data-loading=/);
  assert.match(idle, /aria-busy="false"/);
});

test('only the active analysis step shimmers; finished thread clears loading indicators', () => {
  const props = {analysis: null, files: [{name: 'test.txt', ext: 'TXT', pages: 1, recognition: 'ok'}], steps: [
    {label: 'Прочитано', done: true, active: false},
    {label: 'Анализируем', done: false, active: true},
    {label: 'Ожидание', done: false, active: false},
  ]};
  const busy = render('ThreadScreen', {...props, thinking: true});
  assert.equal((busy.match(/data-loading="true"/g) ?? []).length, 1);
  assert.match(busy, /file-meta shimmer/);
  const finished = render('ThreadScreen', {...props, thinking: false});
  assert.doesNotMatch(finished, /data-loading=|file-meta shimmer|aria-busy="true"/);
});

test('session check has an accessible loading status', () => {
  const html = render('AuthGate', {children: () => null});
  assert.match(html, /class="auth-status shimmer" role="status" aria-busy="true"/);
  assert.match(html, /Проверяем сеанс/);
});
