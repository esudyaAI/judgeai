import test from 'node:test';
import assert from 'node:assert/strict';
import { render } from './fixtures/render-components.mjs';

test('analysis composer has no sweep, stays busy and preserves background action', () => {
  const props = {files: [], value: '', onChange() {}, onFiles() {}, onSend() {}, onStop() {}};
  const busy = render('Composer', {...props, mode: 'thinking'});
  assert.doesNotMatch(busy, /data-loading=|shimmer/);
  assert.match(busy, /aria-busy="true"/);
  assert.match(busy, /aria-label="Продолжить в фоне"/);
  const idle = render('Composer', {...props, mode: 'idle'});
  assert.doesNotMatch(idle, /data-loading=/);
  assert.match(idle, /aria-busy="false"/);
});

test('only the heading and its timer shimmer; finished thread clears loading indicators', () => {
  const props = {analysis: null, files: [{name: 'test.txt', ext: 'TXT', pages: 1, recognition: 'ok'}], steps: [
    {label: 'Прочитано', done: true, active: false},
    {label: 'Анализируем', done: false, active: true},
    {label: 'Ожидание', done: false, active: false},
  ]};
  const busy = render('ThreadScreen', {...props, thinking: true});
  assert.doesNotMatch(busy, /data-loading=|file-meta shimmer|class="shimmer/);
  assert.equal((busy.match(/text-shimmer/g) ?? []).length, 2);
  const finished = render('ThreadScreen', {...props, thinking: false});
  assert.doesNotMatch(finished, /data-loading=|file-meta shimmer|aria-busy="true"/);
});

test('session check has an accessible loading status', () => {
  const html = render('AuthGate', {children: () => null});
  assert.match(html, /class="auth-status" role="status" aria-busy="true"/);
  assert.match(html, /Проверяем сеанс/);
});


test('thinking uses text shimmer and a seconds timer', () => {
  const busy = render('ThreadScreen', {thinking:true, files:[], steps:[{label:'Анализируем',done:false,active:true}], analysis:null});
  assert.match(busy, /steps-title text-shimmer/);
  assert.match(busy, /analysis-timer text-shimmer" role="timer"[^>]*>0 сек/);
  assert.match(busy, /class="step-active"/);
  assert.doesNotMatch(busy, /step-active text-shimmer/);
});


test('finished answer has no disabled followup suggestions', () => {
 const html = render('ThreadScreen', {thinking:false,files:[],steps:[],analysis:{variants:[],mitigating:[],similar:[],stats:{documents:0,pages:0,seconds:2},fabula:'Ответ готов'}});
 assert.doesNotMatch(html, /followups|Сравнить с практикой региона|Позиция защиты|Подробнее об обстоятельствах/);
 assert.doesNotMatch(html, /role="timer"|text-shimmer/);
});

test('elapsed time reads as minutes and seconds', () => {
  const started = new Date(Date.now() - 90_200).toISOString();
  const messages = [{id:1, role:'assistant', status:'running', stage:'reading', content:'', error:null, result:null, attachments:[], created_at:started}];
  const html = render('ChatTimeline', {messages, onOpen() {}});
  assert.match(html, /role="timer"[^>]*>1 мин 3[01] сек</);
  assert.doesNotMatch(html, />9[01] с/);
});

test('analysis steps follow the order of the work', () => {
  const messages = [{id:1, role:'assistant', status:'running', stage:'checking', content:'', error:null, result:null, attachments:[], created_at:new Date().toISOString()}];
  const html = render('ChatTimeline', {messages, onOpen() {}});
  const order = ['Читаем документы', 'Извлекаем факты', 'Сверяем с законом', 'Ищем похожие дела', 'Готовим рекомендацию'];
  const positions = order.map(label => html.indexOf(label));
  assert.ok(positions.every(p => p >= 0), positions.join(','));
  assert.deepEqual([...positions].sort((a, b) => a - b), positions);
  assert.match(html, /step-done">Извлекаем факты</);
  assert.match(html, /step-active">Сверяем с законом</);
  assert.match(html, /step-pending">Ищем похожие дела</);
});
