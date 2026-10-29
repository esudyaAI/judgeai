async page => {
  await page.unrouteAll({behavior:'ignoreErrors'});
  const base='http://127.0.0.1:5185';
  let logged=true, listFail=false, chats=[], hold='', held=null, failText=true;
  const calls={};
  const profile={firstName:'Анна',lastName:'',email:'',position:'',org:'',region:'',avatar:''};
  await page.route(`${base}/api/**`, route=>{
    const path=route.request().url().replace(/^https?:\/\/[^/]+/,'').split('?')[0];
    calls[path]=(calls[path]||0)+1;
    if (hold===path && route.request().method() !== 'GET') { held=route; return; }
    if (hold==='list' && path==='/api/chats') { held=route; return; }
    if (path==='/api/auth/me') return route.fulfill(logged ? {json:{id:1,username:'помощник',is_admin:false,csrf_token:'synthetic'}} : {status:401,json:{detail:'Требуется вход'}});
    if (path==='/api/account/profile') return route.fulfill({json:profile});
    if (path==='/api/account/sessions') return route.fulfill({json:[]});
    if (path==='/api/chats') return listFail ? route.fulfill({status:503,json:{detail:'Тестовая ошибка списка'}}) : route.fulfill({json:chats});
    if (path==='/api/chats/1/messages') return route.fulfill({json:[{id:1,role:'user',content:'Материалы',status:'completed',attachments:[{id:1,filename:'Материалы.md',page_count:null,extraction_status:'ok'},{id:2,filename:'Другой.txt',page_count:null,extraction_status:'empty'}]}]});
    if (path.endsWith('/attachments/1/file')) return failText ? route.fulfill({status:503,body:'fail'}) : route.fulfill({body:'Безопасный текст <script>window.untrusted=true</script>',contentType:'text/plain'});
    if (path.endsWith('/attachments/2/file')) return route.fulfill({body:'',contentType:'text/plain'});
    return route.fulfill({json:{}});
  });
  const results=[];
  for (const [width,height] of [[1440,1000],[390,844]]) {
    await page.setViewportSize({width,height});
    await page.emulateMedia({reducedMotion:'no-preference'});
    logged=false;
    await page.goto(`${base}/app`);
    const submit=page.locator('form').getByRole('button',{name:'Войти',exact:true});
    await submit.waitFor();
    if (!await submit.isDisabled()) throw Error('Empty login can submit');
    await page.getByLabel('Имя пользователя',{exact:true}).fill('test-user');
    await page.getByLabel('Пароль',{exact:true}).fill('synthetic');
    hold='/api/auth/login'; held=null; await submit.click();
    await page.getByRole('button',{name:'Входим…',exact:true}).waitFor();
    if (!await page.getByRole('button',{name:'Входим…',exact:true}).isDisabled()) throw Error('Pending login unlocked');
    hold=''; await held.fulfill({status:401,json:{detail:'Неверный пароль'}});
    await page.getByRole('alert').waitFor();
    if (await page.getByLabel('Пароль',{exact:true}).inputValue()!=='') throw Error('Password not cleared');
    logged=true; hold='list'; held=null; chats=[];
    await page.goto(`${base}/app`);
    if (width<761) await page.getByRole('button',{name:'Открыть боковое меню',exact:true}).click();
    await page.getByText('Загружаем дела…',{exact:true}).waitFor();
    hold=''; await held.fulfill({json:[]});
    await page.getByText('Здесь появятся ваши дела. Начните новое дело.',{exact:true}).waitFor();
    if (width<761) {
      if (!await page.locator('.cab-main').evaluate(el=>el.inert)) throw Error('Drawer background not inert');
      await page.getByRole('button',{name:'Аккаунт',exact:true}).click();
      await page.keyboard.press('Escape');
      if (!await page.getByLabel('Дела',{exact:true}).isVisible()) throw Error('Menu Escape closed drawer too');
      await page.keyboard.press('Escape');
      if (await page.locator('.cab-main').evaluate(el=>el.inert)) throw Error('Drawer left background inert');
    }
    await page.getByRole('button',{name:'Проверить квалификацию',exact:false}).click();
    if (await page.getByRole('textbox',{name:'Задача по делу'}).inputValue()!=='Проверить квалификацию') throw Error('Suggestion ignored');
    listFail=true; await page.goto(`${base}/app`);
    if (width<761) await page.getByRole('button',{name:'Открыть боковое меню',exact:true}).click();
    await page.getByRole('alert').filter({hasText:'Тестовая ошибка списка'}).waitFor();
    listFail=false; await page.getByRole('button',{name:'Повторить',exact:true}).click();
    await page.getByText('Здесь появятся ваши дела. Начните новое дело.',{exact:true}).waitFor();
    await page.goto(`${base}/app/settings`);
    await page.getByLabel('Имя',{exact:true}).waitFor();
    hold='/api/account/profile'; held=null;
    await page.getByRole('button',{name:'Сохранить профиль',exact:true}).click();
    await page.getByRole('button',{name:'Сохраняем…',exact:true}).waitFor();
    if (!await page.getByRole('tab',{name:'Безопасность',exact:true}).isDisabled()) throw Error('Pending settings can switch tab');
    hold=''; await held.fulfill({status:503,json:{detail:'Тестовая ошибка сохранения'}});
    await page.getByRole('alert').filter({hasText:'Тестовая ошибка сохранения'}).waitFor();
    await page.getByRole('button',{name:'Сохранить профиль',exact:true}).click();
    await page.getByText('Профиль сохранён',{exact:true}).waitFor();
    await page.getByRole('tab',{name:'Профиль',exact:true}).focus(); await page.keyboard.press('ArrowRight');
    const change=page.getByRole('button',{name:'Изменить пароль',exact:true});
    await change.waitFor();
    if (!await change.isDisabled()) throw Error('Empty password form can submit');
    await page.getByLabel('Текущий пароль',{exact:true}).fill('old');
    await page.getByLabel('Новый пароль',{exact:true}).fill('synthetic-new-pass');
    await page.getByLabel('Повторите новый пароль',{exact:true}).fill('different');
    if (!await change.isDisabled()) throw Error('Mismatch password enabled');
    await page.getByLabel('Повторите новый пароль',{exact:true}).fill('synthetic-new-pass');
    if (await change.isDisabled()) throw Error('Valid password disabled');
    await page.waitForFunction(()=>{const el=document.querySelector('[role=tabpanel]');return el && getComputedStyle(el).opacity==='1' && getComputedStyle(el).transform==='none';});
    await page.screenshot({path:`acceptance-screenshots/security-states-${width}.png`,fullPage:true});
    chats=[{id:1,title:'Очень длинное русское название материалов уголовного дела для проверки интерфейса',status:'ready',updated_at:'2026-10-29T12:00:00Z'}];
    failText=true; await page.goto(`${base}/app/case/1/result`);
    await page.getByRole('button',{name:'Открыть Материалы.md',exact:true}).click();
    await page.getByRole('alert').filter({hasText:'Не удалось загрузить текст'}).waitFor();
    failText=false; await page.getByRole('button',{name:'Повторить',exact:true}).click();
    await page.locator('.text-document pre').waitFor();
    if (await page.evaluate(()=>window.untrusted)) throw Error('Markdown executed HTML');
    await page.emulateMedia({reducedMotion:'reduce'});
    await page.screenshot({path:`acceptance-screenshots/text-states-${width}.png`,fullPage:true});
    await page.keyboard.press('Escape');
    await page.getByRole('button',{name:'Открыть Другой.txt',exact:true}).click();
    await page.getByText('В документе нет текста для просмотра. Вы можете скачать оригинал.',{exact:true}).waitFor();
    await page.keyboard.press('Escape');
    if (await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)) throw Error('Overflow');
    results.push({width,login:true,listStates:true,drawer:true,suggestion:true,settings:true,password:true,textRetry:true,escapedText:true,emptyText:true});
  }
  return results;
}
