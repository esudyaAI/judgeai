async page => {
  const waitRoute = async read => {
    const deadline = Date.now() + 10000;
    while (!read()) { if (Date.now() > deadline) throw Error('Synthetic request did not reach the route handler'); await page.waitForTimeout(10); }
    return read();
  };
  const base='http://127.0.0.1:5185';
  let chats=[{id:1,title:'Первое дело',status:'ready',updated_at:'2026-10-29T12:00:00Z'}, {id:2,title:'Второе дело',status:'ready',updated_at:'2026-10-29T12:00:00Z'}];
  let holdList=false, stale=null, holdSend=false, sendRoute=null, sendCount=0, holdLogout=false, logoutRoute=null;
  await page.route(`${base}/api/**`,route=>{
    const path=route.request().url().replace(/^https?:\/\/[^/]+/,'').split('?')[0];
    const method=route.request().method();
    if (path==='/api/auth/me') return route.fulfill({json:{id:1,username:'помощник',is_admin:false,csrf_token:'synthetic'}});
    if (path==='/api/auth/logout') { if(holdLogout){logoutRoute=route;return;} return route.fulfill({json:{}}); }
    if (path==='/api/account/profile') return route.fulfill({json:{firstName:'',lastName:'',email:'',position:'',org:'',region:'',avatar:''}});
    if (path==='/api/chats') { if(holdList){stale=route;return;} return route.fulfill({json:chats}); }
    if (path==='/api/chats/1/pin') return route.fulfill({json:{}});
    if (path==='/api/chats/1' && method==='DELETE') {chats=chats.filter(c=>c.id!==1);return route.fulfill({json:{deleted:1,files_pending:0}});}
    if (path==='/api/chats/2/messages') {
      if(method==='POST'){sendCount++; if(holdSend){sendRoute=route;return;} return route.fulfill({json:{}});}
      return route.fulfill({json:[{id:1,role:'user',content:'Текст',status:'completed',attachments:[{id:1,filename:'Материалы.txt',page_count:1,extraction_status:'ok'}]}]});
    }
    if (path.endsWith('/file')) return route.fulfill({body:'Проверка фоновой блокировки',contentType:'text/plain'});
    return route.fulfill({json:[]});
  });
  await page.setViewportSize({width:1440,height:1000});
  await page.goto(`${base}/app/case/2/result`);
  const first=page.getByRole('button',{name:'Действия чата «Первое дело»',exact:true});
  await first.waitFor(); holdList=true;
  await first.click(); await page.getByRole('menuitem',{name:'Закрепить',exact:true}).click();
  await page.getByText('Обновляем закрепление…',{exact:true}).waitFor();
  await first.click(); await page.getByRole('menuitem',{name:'Удалить чат',exact:true}).click();
  await page.getByRole('dialog').getByRole('button',{name:'Удалить чат',exact:true}).click();
  await first.waitFor({state:'detached'});
  if (await page.getByLabel('Список дел',{exact:true}).getAttribute('aria-busy')!=='false') throw Error('Deleted chat left list loading forever');
  await waitRoute(()=>stale); holdList=false; await stale.fulfill({json:[{id:1,title:'Первое дело',status:'ready',updated_at:''},...chats]});
  await page.getByText('Обновляем закрепление…',{exact:true}).waitFor({state:'detached'});
  if (await first.count()) throw Error('Stale list resurrected deleted chat');
  await page.getByRole('button',{name:'Свернуть боковое меню',exact:true}).click();
  await page.getByRole('button',{name:'Открыть боковое меню',exact:true}).click();
  await page.getByRole('button',{name:'Открыть Материалы.txt',exact:true}).click();
  await page.locator('.text-document pre').waitFor();
  await page.setViewportSize({width:390,height:844});
  await page.waitForFunction(()=>document.querySelector('.cab-main').inert);
  await page.setViewportSize({width:800,height:844});
  await page.waitForFunction(()=>document.querySelector('.document-panel').getAttribute('aria-modal')==='true');
  if (!await page.locator('.cab-main').evaluate(el=>el.inert)) throw Error('Resize released an active document lock');
  await page.getByRole('button',{name:'Закрыть документ',exact:true}).click();
  await page.waitForFunction(()=>!document.querySelector('.cab-main').inert);
  await page.setViewportSize({width:1440,height:1000});
  const input=page.getByRole('textbox',{name:'Задача по делу'});
  await input.fill('Сохранить этот запрос при ошибке');
  holdSend=true; await page.getByRole('button',{name:'Отправить',exact:true}).click();
  await page.getByRole('button',{name:'Отправляем запрос',exact:true}).waitFor();
  if (!await input.isDisabled() || !await page.getByRole('button',{name:'Прикрепить файлы',exact:true}).isDisabled()) throw Error('Pending send can mutate draft');
  await page.keyboard.press('Enter');
  await waitRoute(()=>sendRoute);
  if (sendCount!==1) throw Error('Duplicate send');
  holdSend=false; await (await waitRoute(()=>sendRoute)).fulfill({status:503,json:{detail:'Тестовая ошибка отправки'}});
  await page.getByRole('alert').filter({hasText:'Тестовая ошибка отправки'}).waitFor();
  if(await input.inputValue()!=='Сохранить этот запрос при ошибке') throw Error('Send failure lost draft');
  if(sendCount!==1) throw Error('Ambiguous mutation retried automatically');
  holdLogout=true;
  await page.getByRole('button',{name:'Аккаунт',exact:true}).click();
  await page.getByRole('menuitem',{name:'Выйти',exact:true}).click();
  await page.getByText('Выходим из аккаунта…',{exact:true}).waitFor();
  await page.getByRole('button',{name:'Аккаунт',exact:true}).click();
  if (!await page.getByRole('menuitem',{name:'Выйти',exact:true}).isDisabled()) throw Error('Duplicate logout enabled');
  await page.keyboard.press('Escape');
  await waitRoute(()=>logoutRoute); holdLogout=false; await logoutRoute.fulfill({status:503,json:{detail:'Нет связи'}});
  await page.getByRole('alert').filter({hasText:'Не удалось выйти'}).waitFor();
  await page.screenshot({path:'acceptance-screenshots/ui-races.png',fullPage:true});
  return {staleList:true,deleteLoading:true,overlappingInert:true,resize:true,pendingSend:true,preservedDraft:true,noAutoRetry:true,logoutPending:true};
}
