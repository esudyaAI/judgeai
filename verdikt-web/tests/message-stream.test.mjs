import test from 'node:test';
import assert from 'node:assert/strict';
import { subscribeMessages } from '../src/cabinet/messageStream.ts';

test('stream snapshots, completion, fallback and cleanup', () => {
  const original = globalThis.EventSource;
  let source;
  globalThis.EventSource = class {
    handlers = {}; closed = false;
    constructor(url) { this.url = url; source = this; }
    addEventListener(name, fn) { this.handlers[name] = fn; }
    close() { this.closed = true; }
  };
  try {
    let snapshots = [], completed = 0, failed = 0;
    const subscribe = () => subscribeMessages('42', v => snapshots.push(v), () => completed++, () => failed++);
    let stop = subscribe();
    assert.equal(source.url, '/api/chats/42/messages/stream');
    source.handlers.messages({data: '[{"id":1}]'});
    assert.deepEqual(snapshots, [[{id:1}]]);
    source.handlers.done(); source.onerror();
    assert.equal(completed, 1); assert.equal(failed, 0); assert.ok(source.closed);
    stop();
    stop = subscribe();
    source.onerror(); source.onerror();
    assert.equal(failed, 1);
    stop = subscribe(); stop();
    source.handlers.messages({data:'[]'}); source.onerror();
    assert.equal(snapshots.length, 1); assert.equal(failed, 1);
    subscribe(); source.handlers.messages({data:'invalid'});
    assert.equal(failed, 2);
    delete globalThis.EventSource;
    assert.equal(subscribe(), null);
  } finally { globalThis.EventSource = original; }
});

test('native reconnect recovers, deadline falls back once, cleanup cancels timer', t => {
  t.mock.timers.enable({apis:['setTimeout']});
  const original = globalThis.EventSource;
  let source, failures = 0;
  globalThis.EventSource = class {
    handlers = {}; readyState = 0;
    constructor() { source = this; }
    addEventListener(name, callback) { this.handlers[name] = callback; }
    close() {}
  };
  try {
    const subscribe = () => subscribeMessages('1', () => {}, () => {}, () => failures++);
    subscribe();
    t.mock.timers.tick(10000);
    assert.equal(failures, 1, 'initial connection timeout');
    let stop = subscribe(); source.onopen();
    source.onerror(); t.mock.timers.tick(9000); source.onopen();
    t.mock.timers.tick(2000);
    assert.equal(failures, 1, 'reconnected without polling');
    source.onerror(); t.mock.timers.tick(10000);
    assert.equal(failures, 2);
    stop = subscribe(); stop(); t.mock.timers.tick(10000);
    assert.equal(failures, 2);
    subscribe(); source.handlers.access_revoked();
    assert.equal(failures, 3);
  } finally { globalThis.EventSource = original; }
});
