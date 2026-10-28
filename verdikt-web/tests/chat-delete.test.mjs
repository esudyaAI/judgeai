import test from 'node:test';
import assert from 'node:assert/strict';
import { render } from './fixtures/render-components.mjs';

test('sidebar exposes chat action menus instead of standalone delete buttons', () => {
  const html = render('Sidebar', {cases:[{id:'1', title:'Черновик', group:'Ранее', status:'draft'}, {id:'2', title:'Анализ', group:'Ранее', status:'busy'}], activeId:'1', username:'test', deletingId:null});
  assert.match(html, /aria-label="Действия чата «Черновик»"/);
  assert.match(html, /aria-label="Действия чата «Анализ»"[^>]*aria-haspopup="menu"/);
  assert.doesNotMatch(html, /aria-label="Удалить чат/);
  let depth = 0;
  for (const tag of html.matchAll(/<\/?button\b[^>]*>/g)) {
    depth += tag[0].startsWith('</') ? -1 : 1;
    assert.ok(depth >= 0 && depth <= 1, 'buttons must not be nested');
  }
  assert.equal(depth, 0);
});


test('application confirmation names the chat and keeps cancel and delete separate', () => {
  const html = render('DeleteChatDialog', {chat:{id:'1', title:'Мой чат'}, busy:false, error:''});
  assert.match(html, /<dialog[^>]*aria-labelledby="delete-chat-title"/);
  assert.match(html, /Мой чат/);
  assert.match(html, /Восстановить чат не получится/);
  assert.match(html, /Документы в общей базе практики сохранятся/);
  assert.match(html, />Отмена<\/button>/);
  assert.match(html, />Удалить чат<\/button>/);
});

test('pending deletion disables closing and repeats; server errors stay in the dialog', () => {
  const busy = render('DeleteChatDialog', {chat:{id:'1', title:'Чат'}, busy:true, error:''});
  assert.match(busy, /aria-busy="true"/);
  assert.equal((busy.match(/disabled=""/g) || []).length, 3);
  assert.match(busy, /role="status"/);
  const error = render('DeleteChatDialog', {chat:{id:'1', title:'Чат'}, busy:false, error:'Попробуйте снова'});
  assert.match(error, /role="alert">Попробуйте снова/);
});
