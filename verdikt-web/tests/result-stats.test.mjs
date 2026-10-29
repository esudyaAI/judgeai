import test from 'node:test';
import assert from 'node:assert/strict';
import { render } from './fixtures/render-components.mjs';

const analysis = (stats) => ({stats, fabula: 'Фабула', qualification: null, draft: null, scale: null,
  mitigating: [], aggravating: '', personality: '', legalChecks: [], variants: [], similar: []});

test('word documents without a page count do not show zero pages; time reads in minutes', () => {
  const html = render('ThreadScreen', {analysis: analysis({documents: 1, pages: 0, seconds: 313}), files: [], thinking: false, steps: []});
  assert.doesNotMatch(html, /0 страниц/);
  assert.match(html, /5 мин 13 сек/);
});

test('known page count is still shown', () => {
  const html = render('ThreadScreen', {analysis: analysis({documents: 2, pages: 14, seconds: 40}), files: [], thinking: false, steps: []});
  assert.match(html, /14 страниц/);
  assert.match(html, /40 сек/);
});
