// The unsent new-case draft (composer text + attached files) is stored in
// IndexedDB: it survives leaving to another chat and a full page reload, and
// is dropped once the draft is actually sent.
async page => {
  await page.unrouteAll({behavior:'ignoreErrors'});
  const base='http://127.0.0.1:5183';
  const stamp=new Date().toISOString();
  const message={id:1,chat_id:1,role:'user',content:'Старый вопрос',status:'completed',stage:null,error:null,analysis:null,result:null,created_at:stamp,updated_at:null,attachments:[]};
  await page.route(`${base}/api/**`, route => {
    const request=route.request();
    const path=request.url().replace(/^https?:\/\/[^/]+/,'').split('?')[0];
    const json=value=>route.fulfill({json:value});
    if (path==='/api/auth/me') return json({id:1,username:'помощник',is_admin:false,csrf_token:'synthetic-only'});
    if (path==='/api/account/profile') return json({firstName:'',lastName:'',avatar:''});
    if (path==='/api/chats'&&request.method()==='GET') return json([{id:1,title:'Старое дело',status:'ready',is_pinned:false,updated_at:stamp}]);
    if (path==='/api/chats'&&request.method()==='POST') return json({id:7,title:null,status:'draft',is_pinned:false,updated_at:stamp});
    if (path==='/api/chats/1/messages') return json([message]);
    if (path==='/api/chats/7/messages'&&request.method()==='POST') return json({user_message:{...message,id:9,chat_id:7,content:'Проверь сроки давности'},assistant_message:{...message,id:10,chat_id:7,role:'assistant',content:'Готово'}});
    if (path==='/api/chats/7/messages') return json([{...message,id:9,chat_id:7,content:'Проверь сроки давности'},{...message,id:10,chat_id:7,role:'assistant',content:'Готово'}]);
    return json({});
  });
  await page.setViewportSize({width:1440,height:1000});
  await page.goto(`${base}/app`);
  const composer=page.locator('.composer-field input');
  await composer.waitFor();
  await composer.fill('Проверь сроки давности');
  await page.locator('.cab-composer input[type=file]').setInputFiles([{name:'Черновик.txt',mimeType:'text/plain',buffer:Buffer.from('синтетика')}]);
  await page.locator('.file-row').filter({hasText:'Черновик.txt'}).waitFor();
  await page.waitForTimeout(500); // debounced IndexedDB write

  // Leaving to another chat keeps the draft; the case composer stays separate.
  await page.locator('.cab-row').filter({hasText:'Старое дело'}).click();
  await page.waitForFunction(()=>location.pathname==='/app/case/1/result');
  if (await composer.inputValue()!=='') throw Error('Case composer must not show the new-case draft');
  await page.getByRole('button',{name:'Новое дело',exact:true}).click();
  await page.waitForFunction(()=>location.pathname==='/app'||location.pathname==='/app/attach');
  await page.waitForFunction(()=>document.querySelector('.composer-field input')?.value==='Проверь сроки давности');
  await page.locator('.file-row').filter({hasText:'Черновик.txt'}).waitFor();

  // A full reload restores the same draft from IndexedDB.
  await page.reload();
  await page.waitForFunction(()=>document.querySelector('.composer-field input')?.value==='Проверь сроки давности');
  await page.locator('.file-row').filter({hasText:'Черновик.txt'}).waitFor();

  // Sending the draft clears the storage: the next new case starts empty, even after a reload.
  await page.getByRole('button',{name:'Отправить',exact:true}).click();
  await page.waitForFunction(()=>location.pathname==='/app/case/7/analysis');
  await page.getByRole('button',{name:'Новое дело',exact:true}).click();
  await page.waitForFunction(()=>location.pathname==='/app');
  await page.waitForTimeout(500); // a restore would have applied by now
  if (await composer.inputValue()!=='') throw Error('Sent draft must not be restored');
  if (await page.locator('.file-row').count()) throw Error('Sent draft files must not be restored');
  await page.reload();
  await page.waitForTimeout(500);
  if (await composer.inputValue()!=='') throw Error('Sent draft must not survive a reload');
  return {navigated:true,reloaded:true,clearedAfterSend:true};
}
