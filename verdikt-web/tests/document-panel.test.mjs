import test from 'node:test';
import assert from 'node:assert/strict';
import { render } from './fixtures/render-components.mjs';

const message = (id, role, content, extra={}) => ({id, role, content, status:'completed', stage:null, result:null, error:null, attachments:[], ...extra});

test('timeline preserves every turn, attachment and failed reply', () => {
  const html = render('ChatTimeline', {messages:[
    message(1,'user','First question', {attachments:[{id:7,filename:'verdict.pdf',page_count:2,extraction_status:'ok'}]}),
    message(2,'assistant','First answer'), message(3,'user','Follow-up'),
    message(4,'assistant',null,{status:'failed',error:'Safe failure'}),
    message(5,'user','Повторить question'), message(6,'assistant',null,{status:'running',stage:'reading'}),
  ], onOpen:()=>{}});
  for (const text of ['First question','First answer','Follow-up','Safe failure','Повторить question','verdict.pdf']) assert.ok(html.includes(text), text);
  assert.match(html, /Открыть verdict.pdf/);
  assert.match(html, /aria-busy="true"/);
  assert.equal((html.match(/data-message-id=/g)||[]).length, 6);
});

test('panel provides Word progress, failure retry and original download', () => {
  const common = {name:'verdict.docx', downloadUrl:'/private/original', onClose:()=>{}, onRetry:()=>{}};
  const waiting = render('DocumentPanel', {...common, status:'converting'});
  assert.match(waiting,/Подготавливаем документ/);
  assert.doesNotMatch(waiting,/<iframe/);
  const failed = render('DocumentPanel', {...common,status:'failed',error:'Conversion failed'});
  assert.match(failed,/Conversion failed/);
  assert.match(failed,/Повторить/);
  assert.match(failed,/\/private\/original/);
  const ready = render('DocumentPanel', {...common,status:'ready',url:'/private/preview'});
  assert.match(ready,/Загружаем просмотр PDF/);
  assert.doesNotMatch(ready,/<iframe/);
});


test('document controls and status messages use Russian', () => {
  const html = render('DocumentPanel', {name:'Документ.docx',status:'converting',downloadUrl:'/private/original',onClose:()=>{},onRetry:()=>{}});
  assert.match(html,/Закрыть документ/);
  assert.match(html,/Скачать оригинал/);
  assert.match(html,/Подготавливаем документ/);
  assert.doesNotMatch(html,/Next|Previous|Download|Preparing|Retry|Preview/);
});
