import test from 'node:test';
import assert from 'node:assert/strict';
import {
  createDraftSaver,
  memoryDraftStorage,
  noopDraftStorage,
  parseStoredDraft,
  serializeDraft,
} from '../src/cabinet/draftStore.ts';

const tick = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

test('draft round-trips with file names, types, sizes and bytes', async () => {
  const file = new File(['текст дела'], 'Материалы дела.txt', { type: 'text/plain', lastModified: 1730000000000 });
  const parsed = parseStoredDraft(serializeDraft({ prompt: 'Проверь ', files: [file] }));
  assert.equal(parsed.prompt, 'Проверь ');
  assert.equal(parsed.files.length, 1);
  assert.equal(parsed.files[0].name, 'Материалы дела.txt');
  assert.equal(parsed.files[0].type, 'text/plain');
  assert.equal(parsed.files[0].lastModified, 1730000000000);
  assert.equal(await parsed.files[0].text(), 'текст дела');
});

test('malformed stored records are dropped, never partially applied', () => {
  assert.equal(parseStoredDraft(null), null);
  assert.equal(parseStoredDraft('строка'), null);
  assert.equal(parseStoredDraft({ v: 2, prompt: 'x', files: [] }), null);
  assert.equal(parseStoredDraft({ v: 1, prompt: 5, files: [] }), null);
  assert.equal(parseStoredDraft({ v: 1, prompt: 'x', files: [{ name: 'a.txt' }] }), null);
  assert.equal(parseStoredDraft({ v: 1, prompt: 'x', files: [{ name: 1, data: new Blob(['a']) }] }), null);
  const ok = parseStoredDraft({ v: 1, prompt: 'x', files: [{ name: 'a.txt', data: new Blob(['a']) }] });
  assert.equal(ok.files.length, 1);
  assert.equal(ok.files[0].type, '');
});

test('saver debounces: only the latest draft is written', async () => {
  const storage = memoryDraftStorage();
  const writes = [];
  const spying = { ...storage, save: (d) => { writes.push(d); return storage.save(d); } };
  const saver = createDraftSaver(spying, 10);
  saver.schedule({ prompt: 'пе', files: [] });
  saver.schedule({ prompt: 'пер', files: [] });
  saver.schedule({ prompt: 'первая версия', files: [] });
  await tick(40);
  assert.deepEqual(writes.map((d) => d.prompt), ['первая версия']);
  assert.equal((await storage.load()).prompt, 'первая версия');
});

test('empty draft clears the storage instead of saving blank state', async () => {
  const storage = memoryDraftStorage();
  const saver = createDraftSaver(storage, 5);
  await storage.save({ prompt: 'черновик', files: [] });
  saver.schedule({ prompt: '   ', files: [] });
  await tick(30);
  assert.equal(await storage.load(), null);
});

test('flush persists immediately and clear drops everything', async () => {
  const storage = memoryDraftStorage();
  const saver = createDraftSaver(storage, 10_000);
  saver.schedule({ prompt: 'срочно', files: [] });
  saver.flush();
  await tick(5);
  assert.equal((await storage.load()).prompt, 'срочно');
  saver.schedule({ prompt: 'ещё', files: [] });
  saver.clear();
  await tick(5);
  assert.equal(await storage.load(), null);
});

test('noop storage silently keeps every operation a no-op', async () => {
  const storage = noopDraftStorage();
  await storage.save({ prompt: 'x', files: [] });
  await storage.clear();
  assert.equal(await storage.load(), null);
});
