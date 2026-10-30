import test from 'node:test';
import assert from 'node:assert/strict';
import { render } from './fixtures/render-components.mjs';
import { suggestionFill } from '../src/cabinet/suggestionFill.ts';

test('suggestion cards render as buttons that fill the composer, not as navigation', () => {
  const html = render('NewCaseScreen', { onFiles() {}, onSuggestion() {} });
  assert.equal((html.match(/class="sug"/g) ?? []).length, 4);
  for (const title of ['Подготовить проект приговора', 'Проверить квалификацию', 'Найти схожие приговоры', 'Оценить позицию защиты']) {
    assert.match(html, new RegExp(`<span class="sug-title">${title}</span>`));
  }
  assert.match(html, /Перетащите материалы дела или выберите файлы/);
  assert.match(html, /до 50 МБ на файл/);
});

test('file input accepts exactly the supported formats', () => {
  const html = render('NewCaseScreen', { onFiles() {}, onSuggestion() {} });
  assert.match(html, /type="file" multiple="" accept="\.pdf,\.docx,\.dotx,\.txt,\.md"/);
});

test('a suggestion fills the composer ending with exactly one space for continued typing', () => {
  assert.equal(suggestionFill('Проверь квалификацию по материалам дела.'), 'Проверь квалификацию по материалам дела. ');
  assert.equal(suggestionFill('Уже с пробелом '), 'Уже с пробелом ');
  assert.equal(suggestionFill(''), '');
});
