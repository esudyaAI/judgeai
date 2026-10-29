import test from 'node:test';
import assert from 'node:assert/strict';
import { messagesFingerprint } from '../src/cabinet/messagesFingerprint.ts';

const message = (overrides = {}) => ({
  id: 2,
  role: 'assistant',
  content: null,
  status: 'running',
  stage: 'reading',
  error: null,
  result: null,
  attachments: [],
  created_at: '2026-10-29T00:00:00Z',
  ...overrides,
});

test('byte-identical polls produce the identical fingerprint', () => {
  const first = [message({ id: 1, role: 'user', content: 'Вопрос' }), message()];
  const second = [message({ id: 1, role: 'user', content: 'Вопрос' }), message()];
  assert.equal(messagesFingerprint(first), messagesFingerprint(second));
});

test('stage, status, error and result transitions change the fingerprint', () => {
  const base = [message()];
  assert.notEqual(messagesFingerprint([message({ stage: 'searching' })]), messagesFingerprint(base));
  assert.notEqual(messagesFingerprint([message({ status: 'completed', stage: null, result: { any: 1 } })]), messagesFingerprint(base));
  assert.notEqual(messagesFingerprint([message({ status: 'failed', stage: null, error: 'сбой' })]), messagesFingerprint(base));
});

test('attachment reading progress changes the fingerprint', () => {
  const pending = [message({ id: 1, role: 'user', attachments: [{ id: 11, filename: 'a.pdf', page_count: 0, extraction_status: 'pending' }] })];
  const read = [message({ id: 1, role: 'user', attachments: [{ id: 11, filename: 'a.pdf', page_count: 12, extraction_status: 'ok' }] })];
  assert.notEqual(messagesFingerprint(pending), messagesFingerprint(read));
});

test('new messages change the fingerprint, message order is preserved', () => {
  const one = [message()];
  const two = [message(), message({ id: 3, status: 'pending' })];
  assert.notEqual(messagesFingerprint(one), messagesFingerprint(two));
  assert.notEqual(
    messagesFingerprint([message(), message({ id: 3 })]),
    messagesFingerprint([message({ id: 3 }), message()]),
  );
});
