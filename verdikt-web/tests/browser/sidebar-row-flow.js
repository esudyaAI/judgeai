async page => {
  const base = 'http://127.0.0.1:5185';
  await page.route(`${base}/api/**`, route => {
    const path = route.request().url().replace(/^https?:\/\/[^/]+/,'').split('?')[0];
    if (path === '/api/auth/me') return route.fulfill({json:{id:1,username:'помощник',is_admin:false,csrf_token:'synthetic'}});
    if (path === '/api/account/profile') return route.fulfill({json:{first_name:'',last_name:'',email:'',position:'',organization:'',region:'',avatar:null}});
    if (path === '/api/chats') return route.fulfill({json:[{id:1,title:'Дело без названия',status:'ready',updated_at:'2026-10-29T12:00:00Z'}, {id:2,title:'ч. 2 ст. 162 УК РФ',status:'ready',updated_at:'2026-10-29T11:00:00Z'}]});
    return route.fulfill({json:[]});
  });
  const results = [];
  for (const [width,height] of [[1440,1000],[390,844]]) {
    await page.setViewportSize({width,height});
    await page.goto(`${base}/app/case/1/result`);
    if (width < 761) await page.getByRole('button',{name:'Открыть боковое меню',exact:true}).click();
    const row = page.locator('.cab-chat-row').first();
    const dots = row.getByRole('button',{name:'Действия чата «Дело без названия»',exact:true});
    const main = row.locator('.cab-row');
    await dots.waitFor();
    const read = () => row.evaluate(row => {
      const main = row.querySelector('.cab-row'), dots = row.querySelector('.cab-chat-actions');
      return {row:getComputedStyle(row).backgroundColor, main:getComputedStyle(main).backgroundColor,
        dots:getComputedStyle(dots).backgroundColor, color:getComputedStyle(dots).color,
        mainOutline:getComputedStyle(main).outlineStyle, rowOutline:getComputedStyle(row).outlineStyle};
    });
    await page.mouse.move(width-5,height-5);
    const normal = await read();
    if (normal.main !== 'rgba(0, 0, 0, 0)' || normal.dots !== 'rgba(0, 0, 0, 0)') throw Error('Nested controls split the row background');
    await dots.hover();
    await page.waitForFunction(color => getComputedStyle(document.querySelector('.cab-chat-actions')).color !== color,normal.color);
    const hover = await read();
    if (hover.dots !== normal.dots || hover.color === normal.color) throw Error('Dots hover must change glyph color only '+JSON.stringify({normal,hover}));
    await page.keyboard.press('Tab');
    await main.focus();
    const focused = await read();
    if (focused.mainOutline !== 'none' || focused.rowOutline === 'none') throw Error('Keyboard focus must outline the complete row');
    await dots.click();
    await page.getByRole('menuitem',{name:'Закрепить',exact:true}).waitFor();
    await page.keyboard.press('Escape');
    if (!await dots.evaluate(el=>el === document.activeElement)) throw Error('Menu lost focus');
    await page.screenshot({path:`acceptance-screenshots/sidebar-unified-${width}.png`,fullPage:true});
    const account = page.getByRole('button',{name:'Аккаунт',exact:true});
    await account.click();
    const menu = page.getByRole('menu',{name:'Аккаунт',exact:true});
    await menu.waitFor();
    await page.waitForFunction(()=>getComputedStyle(document.querySelector('.cab-action-menu')).transform === 'none');
    const triggerBox = await account.boundingBox(), menuBox = await menu.boundingBox();
    if (Math.abs(triggerBox.width-menuBox.width)>1 || Math.abs(triggerBox.x-menuBox.x)>1 || menuBox.y+menuBox.height > triggerBox.y-7) throw Error('Account menu must match profile width above its trigger');
    if (await menu.getByRole('menuitem').count() !== 2) throw Error('Unexpected account actions');
    await page.screenshot({path:`acceptance-screenshots/account-above-${width}.png`,fullPage:true});
    await page.keyboard.press('Escape');
    if (!await account.evaluate(el=>el === document.activeElement)) throw Error('Account focus not restored');
    if (await page.evaluate(()=>document.documentElement.scrollWidth > innerWidth)) throw Error('Horizontal overflow');
    results.push({width,unified:true,glyphHover:true,keyboard:true,accountAbove:true});
  }
  return results;
}
