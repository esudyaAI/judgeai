import test from 'node:test';
import assert from 'node:assert/strict';
import { render } from './fixtures/render-components.mjs';

test('finished result orders analysis, checks, recommendation and precedents', () => {
  const analysis = {stats: {documents: 1, pages: 1, seconds: 1}, fabula: 'Фабула',
    qualification: null, draft: null, scale: null, mitigating: [], aggravating: '', personality: '',
    legalChecks: [{norm: 'ст. 18 УК РФ', status: 'insufficient_data', value: 'Рецидив',
      explanation: 'Нужна сверка', evidence: ['Цитата суда'], source: 'ст. 18 УК РФ'}],
    variants: [{label: 'Вариант', title: 'Предложение', details: '', rationale: ''}],
    similar: [{punishment: 'Приговор', court: 'Суд', match: 'Квалификация', score: 90}]};
  const html = render('ThreadScreen', {analysis, files: [], thinking: false, steps: []});
  const positions = ['Разбор', 'Сверка', 'Рекомендация', 'Схожие приговоры'].map(s => html.indexOf(s));
  assert.ok(positions.every(p => p >= 0));
  assert.deepEqual([...positions].sort((a,b) => a-b), positions);
  assert.ok(html.indexOf('Цитата суда') < html.indexOf('Предложение'));
});
