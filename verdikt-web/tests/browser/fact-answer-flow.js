async page => {
  // T45.6: what a person sees for answers read by code (T45.4). Synthetic data only.
  const source = 'https://example.invalid/sudact/regular/doc/synthetic-practice-verdict-with-a-long-address-0001';
  const law = 'https://example.invalid/pravo/document/synthetic-criminal-code-edition';
  const messages = [
    {id:1, role:'user', content:'Какой средний срок по ч. 2 ст. 158?', status:'completed', attachments:[]},
    {id:2, role:'assistant', status:'completed', result:null, attachments:[], fact_answer:{kind:'practice', worded_by_model:false},
      content:`По ч. 2 ст. 158 найдено 7 приговоров, учтено 6.\nСредний срок — 1 г. 6 мес.\n\nИсточники:\n1. Синтетический районный суд, 01.02.2026, ${source}.`},
    {id:3, role:'user', content:'Какая санкция по ч. 2 ст. 158?', status:'completed', attachments:[]},
    {id:4, role:'assistant', status:'completed', result:null, attachments:[], fact_answer:{kind:'sanction', worded_by_model:true},
      content:`Лишение свободы на срок до 5 лет.\n\nРедакция: синтетическая, ${law}`},
    {id:5, role:'user', content:'А что думаешь?', status:'completed', attachments:[]},
    {id:6, role:'assistant', status:'completed', result:null, attachments:[], content:'Модель упомянула https://example.invalid/unchecked'},
  ];
  const results = [];
  for (const [width,height,label] of [[1440,1000,'desktop'],[390,844,'mobile']]) {
    await page.unrouteAll({behavior:'ignoreErrors'});
    await page.route('http://127.0.0.1:5183/api/**', route => {
      const path = route.request().url().replace(/^https?:\/\/[^/]+/,'').split('?')[0];
      if (path === '/api/auth/me') return route.fulfill({json:{id:1,username:'помощник',is_admin:false,csrf_token:'synthetic'}});
      if (path === '/api/chats') return route.fulfill({json:[{id:1,title:'Вопросы о практике',status:'ready',updated_at:'2026-11-17T10:00:00Z'}]});
      if (path === '/api/chats/1/messages') return route.fulfill({json:messages.map(m => ({created_at:'2026-11-17T10:00:00Z', stage:null, error:null, ...m}))});
      return route.fulfill({json:{}});
    });
    await page.setViewportSize({width,height});
    await page.goto('http://127.0.0.1:5183/app/case/1/result');
    const answers = page.locator('.chat-message-assistant');
    await answers.nth(2).waitFor();
    const notes = page.getByRole('note');
    if (await notes.count() !== 2) throw Error('Each code-read answer needs exactly one note');
    if (!(await notes.nth(0).textContent()).startsWith('Цифры посчитаны программой')) throw Error('Practice note missing');
    if (!(await notes.nth(1).textContent()).includes('сформулировала языковая модель')) throw Error('Model wording not named');
    for (const [index, href] of [[0, source], [1, law]]) {
      const link = answers.nth(index).getByRole('link', {name:href, exact:true});
      if (await link.getAttribute('href') !== href) throw Error('Source link lost its address');
      if (await link.getAttribute('target') !== '_blank') throw Error('Source opens in the same tab');
      if (!(await link.getAttribute('rel')).split(' ').includes('noopener')) throw Error('Source link lacks noopener');
      const [box, text] = await Promise.all([link.boundingBox(), answers.nth(index).locator('.chat-message-text').boundingBox()]);
      if (box.x + box.width > text.x + text.width + 1) throw Error('Long source address overflows the answer');
    }
    if (await answers.nth(2).locator('a').count()) throw Error('Model text got a link');
    if (await answers.nth(2).getByRole('note').count()) throw Error('Ordinary answer marked as code-read');
    const lines = await answers.nth(0).locator('.chat-message-text').evaluate(el => el.getClientRects().length && getComputedStyle(el).whiteSpace);
    if (!String(lines).startsWith('pre')) throw Error('Source list collapses onto one line');
    const [note, body] = await Promise.all([notes.nth(0).boundingBox(), answers.nth(0).locator('.chat-message-text').boundingBox()]);
    if (note.y + note.height > body.y + 1) throw Error('Note is not above the answer');
    if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) throw Error('Overflow');
    await answers.nth(0).scrollIntoViewIfNeeded();
    await page.screenshot({path:'acceptance-screenshots/'+label+'-fact-answer.png', fullPage:true});
    results.push({label, notes:2, links:2, modelLinks:0, wraps:true});
  }
  return results;
}
