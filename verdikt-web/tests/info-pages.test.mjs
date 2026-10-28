import test from 'node:test';
import assert from 'node:assert/strict';
import { render } from './fixtures/render-components.mjs';
import { INFO_PAGES, findInfoPage } from '../src/info/content.ts';

test('each information route resolves directly and with a trailing slash', () => {
  for (const page of INFO_PAGES) {
    assert.equal(findInfoPage(page.path), page);
    assert.equal(findInfoPage(`${page.path}/`), page);
  }
  assert.equal(findInfoPage('/app'), undefined);
  assert.equal(findInfoPage('/privacy/other'), undefined);
});

test('information pages have titles, navigation, and exactly one current link', () => {
  for (const page of INFO_PAGES) {
    const html = render('InfoPage', {page});
    assert.ok(html.includes(`<h1>${page.title}</h1>`));
    assert.equal((html.match(/aria-current="page"/g) ?? []).length, 1);
    for (const item of INFO_PAGES) assert.ok(html.includes(`href="${item.path}"`));
    assert.match(html, /href="\/">Вернуться на главную/);
    assert.doesNotMatch(html, /\[УТОЧНИТЬ|\[НАЗВАНИЕ/);
  }
});

test('footer exposes actual information pages rather than placeholder links', () => {
  const html = render('Footer', {});
  for (const page of INFO_PAGES) assert.ok(html.includes(`href="${page.path}"`));
  assert.doesNotMatch(html, /href="#top"|НАЗВАНИЕ КОМПАНИИ/);
});

test('hero follow-up explains work tasks without advertising crime names', () => {
  const html = render('CaseWorkflow', {});
  assert.match(html, /Работа с делом — по существу/);
  assert.match(html, /Окончательное решение — за человеком/);
  assert.equal((html.match(/<li /g) ?? []).length, 3);
  assert.doesNotMatch(html, /Присвоение|Взяточничество|Разбой|Хулиганство|Уклонение от налогов|marquee/);
});
