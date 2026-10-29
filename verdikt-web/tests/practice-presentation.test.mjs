import test from 'node:test';
import assert from 'node:assert/strict';
import { mapAnalysis } from '../src/api/client.ts';
import { practiceSummary, precedentSourceNote, shareLabel } from '../src/cabinet/practicePresentation.ts';

const base = { total: 6, with_term: 5, enough_data: true, min_months: 6, p25_months: 12,
  median_months: 18, p75_months: 24, max_months: 30, conditional_share: 0.5, art64_share: 0,
  art73_share: 0.5, draft_months: 54, draft_percentile: 100, position: 'above',
  candidates: 7, excluded: 1, vector_used: false };

test('position of the draft is stated against the interquartile range', () => {
  const s = practiceSummary(base);
  assert.match(s.headline, /выше/);
  assert.match(s.headline, /4 г\. 6 мес\./);
  assert.equal(s.range, '1 г. – 2 г.');
  assert.equal(s.median, '1 г. 6 мес.');
  assert.match(s.basis, /5 из 6/);
});

test('too few comparable terms give no verdict on the position', () => {
  const s = practiceSummary({ ...base, with_term: 2, enough_data: false, position: null });
  assert.match(s.headline, /Недостаточно/);
  assert.match(s.headline, /2 из 5/);
});

test('no comparable precedents at all', () => {
  const s = practiceSummary({ ...base, total: 0, with_term: 0, enough_data: false, position: null,
    min_months: null, p25_months: null, median_months: null, p75_months: null, max_months: null,
    conditional_share: null, art64_share: null, art73_share: null, draft_percentile: null });
  assert.match(s.headline, /не найдены/);
  assert.equal(s.median, null);
});

test('shares are whole percents and unknown stays a dash', () => {
  assert.equal(shareLabel(0.5), '50 %');
  assert.equal(shareLabel(0.3333), '33 %');
  assert.equal(shareLabel(null), '—');
});

test('source notes explain fallback and missing practice', () => {
  assert.equal(precedentSourceNote('cards'), null);
  assert.match(precedentSourceNote('text'), /по тексту/);
  assert.match(precedentSourceNote('none'), /не найдены/);
  assert.equal(precedentSourceNote(null), null);
});

test('analysis mapping keeps precedents and practice, old results default to empty', () => {
  const minimal = { schema_version: 1, stats: {documents: 1, pages: 0, seconds: 1},
    prompt: 'x', fabula: 'y', scale: null, mitigating: [], variants: [], similar: [] };
  const old = mapAnalysis(minimal);
  assert.deepEqual(old.precedents, []);
  assert.equal(old.practice, null);
  assert.equal(old.precedentSource, null);
  const fresh = mapAnalysis({ ...minimal, precedent_source: 'cards', practice: base,
    precedents: [{ card_id: 1, qualifications: ['ч. 1 ст. 158 УК РФ'], score: 0.8 }] });
  assert.equal(fresh.precedentSource, 'cards');
  assert.equal(fresh.practice.median_months, 18);
  assert.equal(fresh.precedents[0].card_id, 1);
});

test('episode comparisons map independently and legacy results remain readable', () => {
  const minimal = { schema_version: 1, stats: {documents: 1, pages: 0, seconds: 1},
    prompt: 'x', fabula: 'y', scale: null, mitigating: [], variants: [], similar: [] };
  assert.deepEqual(mapAnalysis(minimal).practiceEpisodes, []);
  const result = mapAnalysis({...minimal, practice_episodes: [
    {...base, qualification: 'ч. 2 ст. 158 УК РФ', draft_months: 24},
    {...base, qualification: 'ч. 2 ст. 162 УК РФ', draft_months: 60},
  ]});
  assert.deepEqual(result.practiceEpisodes.map(p => p.draft_months), [24, 60]);
});

test('fractional-month bounds retain their fraction instead of rounding up a month', async () => {
  const {formatMonths} = await import('../src/lib/format.ts');
  assert.equal(formatMonths(5.25),'5,25 мес.');
  assert.equal(formatMonths(17.5),'17,5 мес.');
});
