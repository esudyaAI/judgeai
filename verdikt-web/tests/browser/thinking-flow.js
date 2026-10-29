async page => {
  const results = [];
  for (const [width,height,label] of [[1440,1000,'desktop'],[390,844,'mobile']]) {
    await page.unrouteAll({behavior:'ignoreErrors'});
    let stage = 'reading'; let complete = false;
    const created_at = new Date(Date.now() - 3000).toISOString();
    await page.route('http://127.0.0.1:5183/api/**',route => {
      const path = route.request().url().replace(/^https?:\/\/[^/]+/,'').split('?')[0];
      if (path === '/api/auth/me') return route.fulfill({json:{id:1,username:'помощник',is_admin:false,csrf_token:'synthetic'}});
      if (path === '/api/chats') return route.fulfill({json:[{id:1,title:'Проверка материалов дела',status:complete?'ready':'busy',updated_at:created_at}]});
      if (path === '/api/chats/1/messages') return route.fulfill({json:[{id:1,role:'user',content:'Проверь материалы дела.',status:'completed',attachments:[]},{id:2,role:'assistant',content:complete?'Анализ завершён.':null,status:complete?'completed':'running',stage,created_at,attachments:[]}]});
      return route.fulfill({json:{}});
    });
    await page.setViewportSize({width,height});
    await page.emulateMedia({reducedMotion:'no-preference'});
    await page.goto('http://127.0.0.1:5183/app/case/1/result');
    const timer = page.getByRole('timer');
    await timer.waitFor();
    const first = parseInt(await timer.textContent());
    if (first < 3) throw Error('Timer ignored message creation time');
    await page.waitForFunction(n => parseInt(document.querySelector('[role="timer"]').textContent) > n, first);
    stage = 'checking';
    await page.locator('.step-active').filter({hasText:'Сверяем с законом'}).waitFor();
    if (parseInt(await timer.textContent()) < first) throw Error('Stage reset timer');
    if (await page.locator('.cab-knowledge').count()) throw Error('Checkbox remains');
    const title = page.locator('.steps-title');
    if (await title.evaluate(el => getComputedStyle(el).animationName) !== 'text-shimmer') throw Error('Text shimmer missing');
    await page.screenshot({path:'acceptance-screenshots/'+label+'-thinking.png',fullPage:true});
    await page.emulateMedia({reducedMotion:'reduce'});
    if (await title.evaluate(el => getComputedStyle(el).animationName) !== 'none') throw Error('Reduced motion ignored');
    await page.reload();
    await timer.waitFor();
    if (parseInt(await timer.textContent()) < first) throw Error('Reload reset timer');
    complete = true;
    await timer.waitFor({state:'detached'});
    await page.getByText('Анализ завершён.',{exact:true}).waitFor();
    if (await page.locator('.followups').count()) throw Error('Placeholder actions remain');
    if (await page.evaluate(()=>document.documentElement.scrollWidth > innerWidth)) throw Error('Overflow');
    results.push({label,timer:true,stage:true,reload:true,completed:true,reducedMotion:true});
  }
  return results;
}
