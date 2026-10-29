import test from 'node:test';
import assert from 'node:assert/strict';
import { api, mapAnalysis } from '../src/api/client.ts';

test('null legal fields stay null and warnings survive mapping', () => {
  const result = mapAnalysis({ schema_version: 1, stats: {documents: 1, pages: 0, seconds: 1},
    prompt: 'Check', fabula: 'Summary', qualification: null, scale: null, draft: null,
    mitigating: [], variants: [], similar: [], warnings: ['Partial extraction'], legal_checks: [] });
  assert.equal(result.scale, null);
  assert.equal(result.draft, null);
  assert.equal(result.qualification, null);
  assert.deepEqual(result.warnings, ['Partial extraction']);
});

test('server validation error is readable', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({detail: 'Unsupported format'}), {status: 415});
  try { await assert.rejects(api.listCases(), /Unsupported format/); }
  finally { globalThis.fetch = original; }
});

test('sending a case uploads original bytes and text using backend field names', async () => {
  const original = globalThis.fetch;
  let request;
  globalThis.fetch = async (url, options) => {
    request = {url, ...options};
    return new Response(JSON.stringify({assistant_message:{id:7}}), {status:202});
  };
  try {
    await api.sendCase('3', 'Check this verdict', [new File(['tail evidence'], 'verdict.txt')]);
    assert.equal(request.url, '/api/chats/3/messages');
    assert.equal(request.body.get('content'), 'Check this verdict');
    assert.equal(await request.body.get('files').text(), 'tail evidence');
    assert.equal(request.body.get('use_knowledge_base'), 'false');
  } finally { globalThis.fetch = original; }
});

test('pin action persists a boolean and listing maps the account pin', async () => {
  const original = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push({url,options});
    return new Response(JSON.stringify(options?.method === 'PATCH' ? {id:3,is_pinned:true} : [{id:3,title:'Pinned',is_pinned:true,status:'ready'}]));
  };
  try {
    await api.pinCase('3',true);
    assert.equal(calls[0].url,'/api/chats/3/pin');
    assert.equal(calls[0].options.method,'PATCH');
    assert.deepEqual(JSON.parse(calls[0].options.body),{pinned:true});
    assert.equal((await api.listCases())[0].pinned,true);
  } finally { globalThis.fetch = original; }
});

test('recalculate posts to the message recalculate endpoint', async () => {
  const original = globalThis.fetch;
  let request;
  globalThis.fetch = async (url, options) => {
    request = {url, ...options};
    return new Response(JSON.stringify({id: 9, status: 'pending'}), {status: 202});
  };
  try {
    const message = await api.recalculate('3', 9);
    assert.equal(request.url, '/api/chats/3/messages/9/recalculate');
    assert.equal(request.method, 'POST');
    assert.equal(message.status, 'pending');
  } finally { globalThis.fetch = original; }
});

test('network failure is translated into a Russian recovery message', async()=> {
  const original=globalThis.fetch;
  globalThis.fetch=async()=>{throw new TypeError('Failed to fetch');};
  try {await assert.rejects(api.listCases(),/Нет связи с сервером/);}
  finally {globalThis.fetch=original;}
});
