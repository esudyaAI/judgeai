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
