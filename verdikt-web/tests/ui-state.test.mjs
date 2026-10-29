import test from 'node:test';
import assert from 'node:assert/strict';
import {canAuthenticate, canChangePassword} from '../src/auth/formValidity.ts';
import {render} from './fixtures/render-components.mjs';
test('empty and malformed auth data cannot submit; login permits existing short passwords',()=> {
  assert.equal(canAuthenticate('login','','x'),false);
  assert.equal(canAuthenticate('login','user','x'),true);
  assert.equal(canAuthenticate('register','ab','123456789012'),false);
  assert.equal(canAuthenticate('register','имя','123456789012'),false);
  assert.equal(canAuthenticate('register','valid.name','123456789012'),true);
});
test('password change needs current password, length and matching confirmation',()=> {
  assert.equal(canChangePassword('','123456789012','123456789012'),false);
  assert.equal(canChangePassword('old','short','short'),false);
  assert.equal(canChangePassword('old','123456789012','123456789013'),false);
  assert.equal(canChangePassword('old','123456789012','123456789012'),true);
});
test('pending button names its operation, locks itself and announces progress',()=> {
  const html=render('BusyButton',{pending:true,pendingLabel:'Сохраняем…',children:'Сохранить'});
  assert.match(html,/disabled/); assert.match(html,/aria-busy="true"/); assert.match(html,/Сохраняем…/);
});
test('initial text document is loading, not an unobservable iframe',()=> {
  const html=render('TextDocument',{url:'/synthetic',name:'Материалы.md'});
  assert.match(html,/Загружаем текст/); assert.doesNotMatch(html,/<iframe/);
});
