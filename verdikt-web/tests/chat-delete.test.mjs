import test from 'node:test';
import assert from 'node:assert/strict';
import { render } from './fixtures/render-components.mjs';

test('sidebar has separate accessible delete controls; busy chats cannot be deleted', () => {
  const html = render('Sidebar', {cases:[{id:'1', title:'Черновик', group:'Ранее', status:'draft'}, {id:'2', title:'Анализ', group:'Ранее', status:'busy'}], activeId:'1', username:'test', deletingId:null});
  assert.match(html, /aria-label="Удалить чат «Черновик»"/);
  assert.match(html, /aria-label="Удалить чат «Анализ»"[^>]*disabled/);
  let depth = 0;
  for (const tag of html.matchAll(/<\/?button\b[^>]*>/g)) {
    depth += tag[0].startsWith('</') ? -1 : 1;
    assert.ok(depth >= 0 && depth <= 1, 'buttons must not be nested');
  }
  assert.equal(depth, 0);
});
