import test from 'node:test';
import assert from 'node:assert/strict';
import { api, auth } from '../src/api/client.ts';

test('login uses a custom header and subsequent mutations carry session-bound CSRF', async () => {
  const original = globalThis.fetch;
  const requests = [];
  globalThis.fetch = async (url, options) => {
    requests.push({url, ...options});
    return new Response(JSON.stringify(url.endsWith('/login')
      ? {id: 1, username: 'alice', is_admin: false, csrf_token: 'csrf-synthetic'} : {}));
  };
  try {
    await auth.login('alice', 'synthetic-password');
    await api.createCase();
    assert.equal(requests[0].headers.get('X-Requested-With'), 'JudgeAI');
    assert.equal(requests[1].headers.get('X-CSRF-Token'), 'csrf-synthetic');
    assert.equal(requests[1].credentials, 'same-origin');
    await auth.logout();
    await api.createCase();
    assert.equal(requests.at(-1).headers.has('X-CSRF-Token'), false);
  } finally { globalThis.fetch = original; }
});

test('failed login and expired sessions do not retain CSRF from a previous user', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({id:1, username:'alice', csrf_token:'old'}));
  try {
    await auth.login('alice', 'synthetic-password');
    globalThis.fetch = async () => new Response(JSON.stringify({detail:'Требуется вход'}), {status:401});
    await assert.rejects(auth.me(), /Требуется вход/);
    let headers;
    globalThis.fetch = async (_, options) => { headers = options.headers; return new Response('{}'); };
    await api.createCase();
    assert.equal(headers.has('X-CSRF-Token'), false);
  } finally { globalThis.fetch = original; }
});

test('registration posts credentials with the app header and keeps the session CSRF', async () => {
  const original = globalThis.fetch;
  const requests = [];
  globalThis.fetch = async (url, options) => {
    requests.push({url, ...options});
    return new Response(JSON.stringify(url.endsWith('/register')
      ? {id: 2, username: 'ivanov', is_admin: false, csrf_token: 'csrf-new'} : {}), {status: url.endsWith('/register') ? 201 : 200});
  };
  try {
    const user = await auth.register('ivanov', 'synthetic-password-42');
    assert.equal(user.username, 'ivanov');
    assert.equal(requests[0].url, '/api/auth/register');
    assert.equal(requests[0].headers.get('X-Requested-With'), 'JudgeAI');
    assert.deepEqual(JSON.parse(requests[0].body), {username: 'ivanov', password: 'synthetic-password-42'});
    await api.createCase();
    assert.equal(requests[1].headers.get('X-CSRF-Token'), 'csrf-new');
  } finally { globalThis.fetch = original; }
});

test('registration errors from the server reach the form in Russian', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({detail: 'Это имя пользователя уже занято'}), {status: 409});
  try { await assert.rejects(auth.register('ivanov', 'synthetic-password-42'), /уже занято/); }
  finally { globalThis.fetch = original; }
});

test('failed login reads in Russian', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({detail: 'x'}), {status: 401});
  try { await assert.rejects(auth.login('a', 'b'), /Неверное имя пользователя или пароль/); }
  finally { globalThis.fetch = original; }
});

test('account requests use authenticated transport without retaining secret values', async () => {
  const { accountApi } = await import('../src/api/client.ts');
  const original = globalThis.fetch;
  const requests = [];
  globalThis.fetch = async (url, options) => {
    requests.push({url, ...options});
    return new Response(JSON.stringify(url.endsWith('/login') ? {id:1, username:'alice', csrf_token:'profile-csrf'} : {}));
  };
  try {
    await auth.login('alice', 'synthetic-password');
    await accountApi.saveProfile({firstName:'Анна'});
    await accountApi.changePassword('synthetic-old', 'synthetic-new');
    await accountApi.revoke('id/with/slash');
    await accountApi.deleteCases('synthetic-delete', 'УДАЛИТЬ');
    await accountApi.exportData();
    for (const req of requests.slice(1, -1)) assert.equal(req.headers.get('X-CSRF-Token'), 'profile-csrf');
    assert.equal(requests[1].method, 'PUT');
    assert.equal(requests[3].url, '/api/account/sessions/id%2Fwith%2Fslash');
    assert.deepEqual(JSON.parse(requests[4].body), {password:'synthetic-delete', confirmation:'УДАЛИТЬ'});
    assert.equal(requests[5].url, '/api/account/export');
    assert.ok(requests.every(r => r.credentials === 'same-origin'));
  } finally { globalThis.fetch = original; }
});

test('chat search encodes literal user input and forwards cancellation', async () => {
  const original = globalThis.fetch;
  const controller = new AbortController();
  let sent;
  globalThis.fetch = async (url, options) => { sent = {url, ...options}; return new Response('[]'); };
  try {
    await api.listCases('  Протокол 100% & _  ', controller.signal);
    assert.equal(sent.url, `/api/chats?q=${encodeURIComponent('Протокол 100% & _')}`);
    assert.equal(sent.signal, controller.signal);
    await api.listCases('  ');
    assert.equal(sent.url, '/api/chats');
  } finally { globalThis.fetch = original; }
});


test('single chat deletion sends DELETE with CSRF and reports server errors', async () => {
  const original = globalThis.fetch;
  let sent;
  globalThis.fetch = async (url, options) => {
    sent = {url, ...options};
    if (url === '/api/auth/me') return new Response(JSON.stringify({id:1, username:'test', csrf_token:'delete-csrf'}));
    return new Response(JSON.stringify({deleted:1, files_pending:0}));
  };
  try {
    await auth.me();
    assert.deepEqual(await api.deleteCase('12/34'), {deleted:1, files_pending:0});
    assert.equal(sent.url, '/api/chats/12%2F34');
    assert.equal(sent.method, 'DELETE');
    assert.equal(sent.headers.get('X-CSRF-Token'), 'delete-csrf');
    globalThis.fetch = async () => new Response(JSON.stringify({detail:'Дождитесь завершения анализа'}), {status:409});
    await assert.rejects(api.deleteCase('12'), /Дождитесь завершения анализа/);
  } finally { globalThis.fetch = original; }
});
