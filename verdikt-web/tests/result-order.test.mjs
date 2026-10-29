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

test('several defendants keep their own checks, terms and intermediate totals', () => {
  const sentence = {counts:[{qualification:'ч. 1 ст. 158 УК РФ',punishment:'1 год',additional:[],quote:'Цитата'}],
    intermediate:'2 года',intermediate_rule:'ч. 3 ст. 69 УК РФ',final:'2 года 3 месяца',aggregation_rule:'ст. 70 УК РФ',
    unserved:'1 год',joined:'3 месяца'};
  const person = (label,word) => ({label,imposed_sentence:sentence,legal_checks:[{
    norm:'ст. 18 УК РФ',status:'insufficient_data',value:word,explanation:'Проверка',source:'ст. 18 УК РФ',evidence:[word]}],
    mitigating:[],aggravating:null,practice_episodes:[],similar:[],warnings:[]});
  const analysis={stats:{documents:1,pages:1,seconds:1},fabula:'Два осуждённых',scale:null,qualification:null,
    draft:null,mitigating:[],aggravating:'',personality:'',variants:[],similar:[],defendants:[
      person('Осуждённый 1','Рецидива нет'),person('Осуждённый 2','Опасный рецидив')]};
  const html=render('ThreadScreen',{analysis,files:[],thinking:false,steps:[]});
  const first=html.slice(html.indexOf('aria-label="Осуждённый 1"'),html.indexOf('aria-label="Осуждённый 2"'));
  const second=html.slice(html.indexOf('aria-label="Осуждённый 2"'));
  assert.match(first,/Рецидива нет/); assert.doesNotMatch(first,/Опасный рецидив/);
  assert.match(second,/Опасный рецидив/);
  assert.match(first,/Промежуточный итог/); assert.match(first,/Присоединено: 3 месяца/);
});
