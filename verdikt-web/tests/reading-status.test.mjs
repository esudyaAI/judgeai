import test from 'node:test';
import assert from 'node:assert/strict';
import { fileReadingLabel, fileReadingWarning } from '../src/cabinet/fileReadingPresentation.ts';

test('unreadable files never receive a successful reading label', () => {
  for (const status of ['empty', 'error', 'unsupported', 'pending']) {
    const label = fileReadingLabel({pages: 2, recognition: status});
    assert.doesNotMatch(label, /Текст прочитан/);
  }
  assert.match(fileReadingLabel({pages: 0, recognition:'ok'}), /Текст прочитан/);
  assert.match(fileReadingLabel({pages: 2, recognition:'partial'}), /^2 стр\. · Прочитан частично$/);
});

test('warnings describe reading limitations without inventing case facts', () => {
  assert.match(fileReadingWarning('empty'), /OCR|текстовым слоем/);
  assert.match(fileReadingWarning('error'), /не удалось прочитать/);
  assert.match(fileReadingWarning('unsupported'), /не поддерживается/);
  assert.match(fileReadingWarning('partial'), /не полностью/);
  assert.equal(fileReadingWarning('ok'), null);
  assert.equal(fileReadingWarning('pending'), null);
});

test('every reading label and warning is in Russian', () => {
  for (const status of ['pending', 'ok', 'partial', 'empty', 'error', 'unsupported']) {
    assert.doesNotMatch(fileReadingLabel({pages: 0, recognition: status}), /[A-Za-z]{3,}/);
    assert.doesNotMatch(fileReadingWarning(status) ?? '', /[A-Za-z]{4,}/);  // "OCR" is allowed
  }
});
