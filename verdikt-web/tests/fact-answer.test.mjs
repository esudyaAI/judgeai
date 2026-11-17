import test from 'node:test';
import assert from 'node:assert/strict';
import { factAnswerNote, linkSegments } from '../src/cabinet/factAnswerPresentation.ts';
import { render } from './fixtures/render-components.mjs';

test('practice answer is marked as counted by code', () => {
  assert.equal(factAnswerNote({kind:'practice', worded_by_model:false}),
    'Цифры посчитаны программой по приговорам базы практики. Источники — ниже.');
});

test('model wording is named and said to be checked against the numbers', () => {
  assert.equal(factAnswerNote({kind:'practice', worded_by_model:true}),
    'Цифры посчитаны программой по приговорам базы практики. Текст сформулировала языковая модель; каждое число в нём сверено с расчётом. Источники — ниже.');
});

test('sanction answer names the law base', () => {
  assert.equal(factAnswerNote({kind:'sanction', worded_by_model:false}),
    'Санкция прочитана программой из базы законов. Редакция и источник — ниже.');
});

test('no marker or an unknown kind gives no note', () => {
  assert.equal(factAnswerNote(null), null);
  assert.equal(factAnswerNote(undefined), null);
  assert.equal(factAnswerNote({kind:'other', worded_by_model:false}), null);
});

test('http(s) addresses become links, trailing punctuation stays text', () => {
  assert.deepEqual(linkSegments('см. https://sudact.ru/regular/doc/abc. и (http://x.invalid/a?b=1),'), [
    {text:'см. '},
    {text:'https://sudact.ru/regular/doc/abc', href:'https://sudact.ru/regular/doc/abc'},
    {text:'. и ('},
    {text:'http://x.invalid/a?b=1', href:'http://x.invalid/a?b=1'},
    {text:'),'},
  ]);
});

test('other schemes and plain text are never links', () => {
  assert.deepEqual(linkSegments('javascript:alert(1) ftp://x.invalid'), [{text:'javascript:alert(1) ftp://x.invalid'}]);
  assert.deepEqual(linkSegments('https://'), [{text:'https://'}]);
  assert.deepEqual(linkSegments(''), []);
});

const answer = (extra) => ({id:1, role:'assistant', status:'completed', stage:null, error:null, result:null,
  attachments:[], created_at:'2026-11-17T10:00:00Z',
  content:'Среднее 2 г.\n\nИсточники:\n1. Суд, https://example.invalid/sudact/1', ...extra});

test('timeline marks a fact answer and opens its sources as links', () => {
  const html = render('ChatTimeline', {messages:[answer({fact_answer:{kind:'practice', worded_by_model:false}})], onOpen() {}});
  assert.match(html, /<p class="fact-answer-note" role="note">Цифры посчитаны программой/);
  assert.match(html, /<a href="https:\/\/example.invalid\/sudact\/1" target="_blank" rel="noopener noreferrer">https:\/\/example.invalid\/sudact\/1<\/a>/);
  assert.match(html, /Среднее 2 г\./);
});

test('an ordinary text answer has no note and no links made from its text', () => {
  const html = render('ChatTimeline', {messages:[answer({})], onOpen() {}});
  assert.doesNotMatch(html, /fact-answer-note/);
  assert.doesNotMatch(html, /<a href="https:\/\/example.invalid/);
  assert.match(html, /https:\/\/example.invalid\/sudact\/1/);
});
