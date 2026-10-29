import test from 'node:test';
import assert from 'node:assert/strict';
import {actionMenuPosition} from '../src/cabinet/actionMenuPosition.ts';
const anchor = {left:16,right:256,top:820,bottom:880,width:240};
test('account menu matches the profile width and opens above with a gap',()=> {
  assert.deepEqual(actionMenuPosition(anchor, {width:1440,height:1000}, 104, 'above', true), {left:16,top:708,width:240,maxHeight:984});
});
test('chat menu remains compact and aligned to trigger right',()=> {
  const p=actionMenuPosition(anchor,{width:1440,height:1000},104);
  assert.equal(p.width,210); assert.equal(p.left,46); assert.equal(p.top,888);
});
test('menu flips above when there is no room below',()=> {
  const p=actionMenuPosition(anchor,{width:390,height:900},104);
  assert.equal(p.top,708);
});
test('small viewport clamps menu width and height without overflow',()=> {
  const p=actionMenuPosition(anchor,{width:180,height:90},104,'above',true);
  assert.deepEqual(p,{left:8,top:8,width:164,maxHeight:74});
});
test('preferred above flips below when trigger is at the top',()=> {
  const p=actionMenuPosition({...anchor,top:4,bottom:48},{width:390,height:844},104,'above',true);
  assert.equal(p.top,56);
});
