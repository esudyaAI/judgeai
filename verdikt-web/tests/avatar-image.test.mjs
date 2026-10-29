import test from 'node:test';
import assert from 'node:assert/strict';
import {avatarSize} from '../src/cabinet/avatarImage.ts';
test('avatar dimensions preserve aspect ratio and cap the longest side',()=>{
 assert.deepEqual(avatarSize(4000,3000),{width:512,height:384});
 assert.deepEqual(avatarSize(100,200),{width:100,height:200});
 assert.throws(()=>avatarSize(0,20),/размер/);
 assert.throws(()=>avatarSize(10000,10000),/слишком большое/);
});
