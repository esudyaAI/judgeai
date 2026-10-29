import test from 'node:test';
import assert from 'node:assert/strict';
import {loadDocumentText} from '../src/api/documentText.ts';
test('text transport returns literal markup and empty text without interpretation',async()=> {
  const original=globalThis.fetch;
  globalThis.fetch=async()=>new Response('<script>unsafe()</script>');
  try {assert.equal(await loadDocumentText('/synthetic',new AbortController().signal),'<script>unsafe()</script>');}
  finally {globalThis.fetch=original;}
});
test('text transport enforces its byte budget and localizes network errors',async()=> {
  const original=globalThis.fetch;
  try {
    globalThis.fetch=async()=>new Response('привет');
    await assert.rejects(loadDocumentText('/x',new AbortController().signal,3),/слишком большой/);
    globalThis.fetch=async()=>{throw new TypeError('Failed to fetch');};
    await assert.rejects(loadDocumentText('/x',new AbortController().signal),/Нет связи/);
    globalThis.fetch=async()=>new Response('no',{status:403});
    await assert.rejects(loadDocumentText('/x',new AbortController().signal),/Проверьте доступ/);
  } finally {globalThis.fetch=original;}
});
test('an interrupted response stream never exposes a system English error',async()=> {
  const original=globalThis.fetch;
  globalThis.fetch=async()=>new Response(new ReadableStream({start(controller){controller.error(new TypeError('terminated'));}}));
  try {await assert.rejects(loadDocumentText('/x',new AbortController().signal),/Не удалось прочитать текст/);}
  finally {globalThis.fetch=original;}
});
