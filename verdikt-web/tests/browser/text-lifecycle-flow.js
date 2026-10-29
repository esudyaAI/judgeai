async page => {
  const waitRoute = async read => {
    const deadline = Date.now() + 10000;
    while (!read()) { if (Date.now() > deadline) throw Error('Synthetic request did not reach the route handler'); await page.waitForTimeout(10); }
    return read();
  };
  const base='http://127.0.0.1:5185';
  let mode='delayed', held=null;
  await page.route(`${base}/api/**`,route=>{
    const path=route.request().url().replace(/^https?:\/\/[^/]+/,'').split('?')[0];
    if(path==='/api/auth/me')return route.fulfill({json:{id:1,username:'помощник',csrf_token:'synthetic'}});
    if(path==='/api/account/profile')return route.fulfill({json:{firstName:'',lastName:'',avatar:''}});
    if(path==='/api/chats')return route.fulfill({json:[]});
    if(path.endsWith('/messages'))return route.fulfill({json:[{id:1,role:'user',content:'Тексты',status:'completed',attachments:[{id:1,filename:'Первый.txt',extraction_status:'ok'},{id:2,filename:'Второй.txt',extraction_status:'ok'}]}]});
    if(path.includes('/attachments/1/file')) {
      if(mode==='delayed'){held=route;return;}
      if(mode==='large')return route.fulfill({body:'a'.repeat(5*1024*1024+1),contentType:'text/plain'});
      if(mode==='offline')return route.abort('internetdisconnected');
    }
    if(path.includes('/attachments/2/file'))return route.fulfill({body:'Текст второго документа',contentType:'text/plain'});
    return route.fulfill({json:{}});
  });
  await page.setViewportSize({width:390,height:844});
  await page.goto(`${base}/app/case/1/result`);
  await page.getByRole('button',{name:'Открыть Первый.txt',exact:true}).click();
  await page.getByText('Загружаем текст…',{exact:true}).waitFor();
  await waitRoute(()=>held);
  await page.getByRole('button',{name:'Закрыть документ',exact:true}).click();
  await page.getByRole('button',{name:'Открыть Второй.txt',exact:true}).click();
  await page.getByText('Текст второго документа',{exact:true}).waitFor();
  await held.fulfill({body:'Устаревший ответ'}).catch(()=>{});
  if(await page.getByText('Устаревший ответ',{exact:true}).count())throw Error('Late response replaced the current text');
  await page.keyboard.press('Escape');
  mode='large'; await page.getByRole('button',{name:'Открыть Первый.txt',exact:true}).click();
  await page.getByRole('alert').filter({hasText:'Текст слишком большой'}).waitFor();
  await page.keyboard.press('Escape');
  mode='offline'; await page.getByRole('button',{name:'Открыть Первый.txt',exact:true}).click();
  await page.getByRole('alert').filter({hasText:'Нет связи с сервером'}).waitFor();
  await page.keyboard.press('Escape');
  await page.clock.install(); mode='delayed';
  await page.getByRole('button',{name:'Открыть Первый.txt',exact:true}).click();
  await page.getByText('Загружаем текст…',{exact:true}).waitFor();
  await page.clock.fastForward(31000);
  await page.getByRole('alert').filter({hasText:'Загрузка текста заняла слишком много времени'}).waitFor();
  await page.screenshot({path:'acceptance-screenshots/text-timeout-mobile.png',fullPage:true});
  await page.keyboard.press('Escape');
  return {lateResponse:true,sizeLimit:true,offlineRussian:true,timeout:true};
}
