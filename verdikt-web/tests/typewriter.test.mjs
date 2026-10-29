import test from 'node:test';
import assert from 'node:assert/strict';
import { createTypewriter, prefersReducedMotion } from '../src/cabinet/typewriter.ts';

function manualScheduler() {
  const frames = [];
  let nextId = 0;
  let time = 0;
  return {
    schedule: (callback) => {
      nextId += 1;
      frames.push({ id: nextId, callback });
      return nextId;
    },
    cancel: (handle) => {
      const index = frames.findIndex((f) => f.id === handle);
      if (index >= 0) frames.splice(index, 1);
    },
    now: () => time,
    advance: (ms) => {
      time += ms;
      const due = frames.splice(0, frames.length);
      for (const frame of due) frame.callback(time);
    },
    pending: () => frames.length,
  };
}

test('prints prefixes progressively and ends with the exact text', () => {
  const scheduler = manualScheduler();
  const values = [];
  const typer = createTypewriter((v) => values.push(v), scheduler);
  const text = 'Проверь квалификацию по материалам дела';
  typer.print(text);
  scheduler.advance(60);
  scheduler.advance(60);
  assert.ok(values.length >= 2, 'typed at least twice');
  assert.ok(values.every((v) => text.startsWith(v)), 'only prefixes are printed');
  assert.ok(values.at(-1).length < text.length, 'still mid-way after 120 ms');
  scheduler.advance(600);
  assert.equal(values.at(-1), text);
  assert.equal(scheduler.pending(), 0, 'animation finished');
});

test('a new print cancels the run in progress', () => {
  const scheduler = manualScheduler();
  const values = [];
  const typer = createTypewriter((v) => values.push(v), scheduler);
  typer.print('Первый длинный запрос для проверки отмены');
  scheduler.advance(60);
  typer.print('Второй запрос');
  assert.equal(scheduler.pending(), 1, 'only the second run is scheduled');
  scheduler.advance(1000);
  assert.equal(values.at(-1), 'Второй запрос');
});

test('cancel keeps the printed prefix and stops scheduling', () => {
  const scheduler = manualScheduler();
  const values = [];
  const typer = createTypewriter((v) => values.push(v), scheduler);
  const text = 'Подготовь проект приговора по материалам дела';
  typer.print(text);
  scheduler.advance(60);
  typer.cancel();
  const stopped = values.at(-1);
  assert.ok(text.startsWith(stopped) && stopped.length < text.length);
  scheduler.advance(1000);
  assert.equal(values.at(-1), stopped, 'no further ticks after cancel');
  assert.equal(scheduler.pending(), 0);
});

test('instant mode sets the whole text without animation', () => {
  const scheduler = manualScheduler();
  const values = [];
  const typer = createTypewriter((v) => values.push(v), scheduler);
  typer.print('Мгновенно', { instant: true });
  assert.deepEqual(values, ['Мгновенно']);
  assert.equal(scheduler.pending(), 0);
});

test('empty text is set instantly', () => {
  const values = [];
  const typer = createTypewriter((v) => values.push(v), manualScheduler());
  typer.print('');
  assert.deepEqual(values, ['']);
});

test('reduced motion is reported as false without a window', () => {
  assert.equal(prefersReducedMotion(), false);
});
