import test from 'node:test';
import assert from 'node:assert/strict';
import { render } from './fixtures/render-components.mjs';
const sentence = {counts: [], final: null, aggregation_rule: null};
const credit = {scope: 'count', count_index: 0, original_amount: 30000,
  reduced_amount: 20000, released: false, status: 'stated', quote: 'Штраф смягчить до 20000 рублей.'};
test('fine credit displays original and judicial amount separately with literal evidence', () => {
  const html = render('SentenceDetails', {sentence: {...sentence, fine_credits: [credit]}});
  assert.match(html, /Назначенный штраф/);
  assert.match(html, /Указано судом после смягчения/);
  assert.match(html, /Эпизод 1/);
  assert.match(html, /Штраф смягчить до 20000 рублей/);
  assert.match(html, /Законность зачёта автоматически не проверена/);
});
test('release and uncertain reading do not display a fabricated zero amount', () => {
  const html = render('SentenceDetails', {sentence: {...sentence, fine_credits: [{...credit,
    scope: 'unassigned', count_index: null, original_amount: null, reduced_amount: null,
    released: true, status: 'requires_review'}]}});
  assert.match(html, /полное освобождение/);
  assert.match(html, /Связь с эпизодом не установлена/);
  assert.match(html, /Чтение требует проверки/);
  assert.doesNotMatch(html, />0 ₽/);
});
test('legacy results without credit metadata remain renderable', () => {
  assert.doesNotMatch(render('SentenceDetails', {sentence}), /Смягчение штрафа/);
});
