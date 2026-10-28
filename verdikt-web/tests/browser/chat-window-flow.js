async page => {
  await page.unrouteAll({behavior:'ignoreErrors'});
  const chats = [{id:1,title:'Проверка материалов дела',is_pinned:false,status:'ready',updated_at:'2026-10-29T12:00:00Z'},{id:2,title:'Обсуждение договора',is_pinned:false,status:'draft',updated_at:'2026-10-29T11:00:00Z'}];
  let failPin = true;
  await page.route('http://127.0.0.1:5183/api/**',route => {
    const path = route.request().url().replace(/^https?:\/\/[^/]+/,'').split('?')[0];
    const json = value => route.fulfill({json:value});
    if (path === '/api/auth/me') return json({id:1,username:'помощник',is_admin:false,csrf_token:'synthetic-only'});
    if (path === '/api/account/profile') return json({first_name:'Александр',last_name:'',email:'',organization:'',position:'',region:'',avatar:null});
    if (path === '/api/account/sessions') return json([]);
    if (path === '/api/chats') return json([...(route.request().url().includes('?q=') ? chats.slice(0,1) : chats)].sort((a,b)=>Number(b.is_pinned)-Number(a.is_pinned)));
    if (path === '/api/chats/1/pin') { if (failPin) { failPin = false; return route.fulfill({status:503,json:{detail:'Тестовая ошибка закрепления'}}); } chats[0].is_pinned = route.request().postDataJSON().pinned; return json(chats[0]); }
    if (path === '/api/chats/1/messages') return json([{id:1,role:'user',content:'Проверь материалы и поясни выводы.',status:'completed',attachments:[{id:1,filename:'Материалы.pdf',page_count:2,extraction_status:'ok'}]}, {id:2,role:'assistant',content:'Материалы прочитаны. Здесь продолжается переписка по делу.',status:'completed',attachments:[]}]);
    return json({});
  });
  const result = [];
  for (const [width,height,label] of [[1440,1000,'desktop'],[390,844,'mobile']]) {
    chats[0].is_pinned = false; failPin = true;
    await page.setViewportSize({width,height});
    await page.goto('http://127.0.0.1:5183/app/case/1/result');
    await page.locator('[data-message-id="2"]').waitFor();
    if (await page.locator('.cab-header').getByText('Выйти',{exact:true}).count()) throw Error('Logout still in header');
    if (await page.locator('.cab-header').getByText('Экспорт',{exact:false}).count()) throw Error('Export still in header');
    if (label === 'mobile') await page.getByRole('button',{name:'Открыть боковое меню',exact:true}).click();
    await page.getByRole('button',{name:'Свернуть боковое меню',exact:true}).click();
    await page.getByRole('complementary',{name:'Дела',exact:true}).waitFor({state:'hidden'});
    await page.getByRole('button',{name:'Открыть боковое меню',exact:true}).click();
    await page.getByPlaceholder('Поиск по чатам').fill('Проверка материалов дела');
    const trigger = page.getByRole('button',{name:'Действия чата «Проверка материалов дела»',exact:true});
    await trigger.click();
    await page.getByRole('menuitem',{name:'Закрепить',exact:true}).waitFor();
    await page.keyboard.press('Escape');
    if (!await trigger.evaluate(el => el === document.activeElement)) throw Error('Menu focus not restored');
    await trigger.click();
    await page.getByRole('menuitem',{name:'Закрепить',exact:true}).click();
    await page.getByText('Тестовая ошибка закрепления',{exact:true}).waitFor();
    await trigger.click();
    await page.getByRole('menuitem',{name:'Закрепить',exact:true}).click();
    await page.getByText('Закреплённые',{exact:true}).waitFor();
    if (!await trigger.evaluate(el => el === document.activeElement)) throw Error('Pin lost keyboard focus');
    await page.reload();
    if (label === 'mobile') await page.getByRole('button',{name:'Открыть боковое меню',exact:true}).click();
    await page.getByText('Закреплённые',{exact:true}).waitFor();
    await trigger.click();
    await page.screenshot({path:'acceptance-screenshots/'+label+'-chat-actions.png',fullPage:true});
    await page.getByRole('menuitem',{name:'Открепить',exact:true}).click();
    await page.getByText('Закреплённые',{exact:true}).waitFor({state:'hidden'});
    await page.getByRole('button',{name:'Аккаунт',exact:true}).click();
    await page.getByRole('menuitem',{name:'Выйти',exact:true}).waitFor();
    await page.screenshot({path:'acceptance-screenshots/'+label+'-account-menu.png',fullPage:true});
    await page.keyboard.press('Escape');
    if (await page.evaluate(()=>document.documentElement.scrollWidth > innerWidth)) throw Error('Horizontal overflow');
    result.push({label,collapse:true,pinReload:true,menus:true,headerClean:true});
  }
  return result;
}
