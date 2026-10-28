import test from 'node:test';
import assert from 'node:assert/strict';
import { pageScale } from '../src/cabinet/pdfViewport.ts';

test('page renderer bounds canvas area and fits the panel', () => {
  const standard = pageScale(612,792,600,2);
  assert.ok(standard.width <= 600);
  assert.ok(standard.width * standard.height * standard.ratio ** 2 <= 4000000);
  const large = pageScale(14400,14400,1400,4);
  assert.ok(large.width * large.height * large.ratio ** 2 <= 4000000);
  for (const args of [[0,10,400,1],[10,Infinity,400,1],[10,10,-1,1]]) assert.throws(()=>pageScale(...args));
});

test('extreme page proportions cannot exceed raster sides or area after rounding', () => {
  for (const dimensions of [[1,14400],[14400,1],[14400,14400]]) {
    const fit = pageScale(...dimensions, 1400, 4);
    assert.ok(fit.pixelWidth <= 4096 && fit.pixelHeight <= 4096);
    assert.ok(fit.pixelWidth * fit.pixelHeight <= 4000000);
  }
  assert.throws(() => pageScale(1,1e12,600,2));
});
