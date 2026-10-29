import test from 'node:test';
import assert from 'node:assert/strict';
import { validateFiles, filesFromClipboard, ACCEPT, MAX_FILE_BYTES } from '../src/lib/files.ts';

test('accept attribute covers exactly the supported formats', () => {
  assert.equal(ACCEPT, '.pdf,.docx,.dotx,.txt,.md');
});

test('accepts supported formats and matches extensions case-insensitively', () => {
  const file = (name, size = 10) => ({ name, size });
  const { accepted, rejections } = validateFiles([file('materials.pdf'), file('Word.docx'.toLowerCase()), file('scan.PDF'), file('note.txt'), file('draft.md')]);
  assert.equal(accepted.length, 5);
  assert.deepEqual(rejections, []);
});

test('rejects unsupported extensions and files above the 50 MB cap', () => {
  const file = (name, size) => ({ name, size });
  const { accepted, rejections } = validateFiles([file('photo.exe', 10), file('big.pdf', MAX_FILE_BYTES + 1), file('ok.dotx', 10)]);
  assert.equal(accepted.length, 1);
  assert.equal(accepted[0].name, 'ok.dotx');
  assert.match(rejections.find((r) => r.name === 'photo.exe').reason, /формат не поддерживается/);
  assert.match(rejections.find((r) => r.name === 'big.pdf').reason, /больше 50 МБ/);
});

test('empty input stays empty', () => {
  assert.deepEqual(validateFiles([]), { accepted: [], rejections: [] });
});

test('clipboard files are extracted; text-only clipboard yields nothing', () => {
  assert.equal(filesFromClipboard(null).length, 0);
  assert.deepEqual(filesFromClipboard({ files: [] }), []);
  const file = new File(['x'], 'a.txt');
  assert.equal(filesFromClipboard({ files: [file] })[0].name, 'a.txt');
});
