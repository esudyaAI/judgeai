import test from 'node:test';
import assert from 'node:assert/strict';
import {acquireInert} from '../src/cabinet/inertLayers.ts';
test('overlapping drawer and document retain background lock until both release',()=> {
  const background={inert:false};
  const drawer=acquireInert(background), document=acquireInert(background);
  drawer(); assert.equal(background.inert,true);
  document(); assert.equal(background.inert,false);
});
test('release is idempotent and preserves an existing lock',()=> {
  const background={inert:true}; const release=acquireInert(background);
  release(); release(); assert.equal(background.inert,true);
});
test('reacquiring after resize does not restore a stale flag',()=> {
  const background={inert:false};
  const doc=acquireInert(background); const drawer=acquireInert(background);
  drawer(); const reopened=acquireInert(background); doc();
  assert.equal(background.inert,true); reopened(); assert.equal(background.inert,false);
});
