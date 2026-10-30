// Suggestion cards, clipboard paste and the /app/attach dead end.
// Covers: card click types the prompt into the composer (fill, not navigation),
// user typing cancels the animation, pasting a file attaches it without inserting
// the path as text, unsupported formats explain themselves, global paste works
// outside the input, and /app/attach with no files falls back to the dropzone.
async page => {
  await page.unrouteAll({behavior:'ignoreErrors'});
  const created = new Date(Date.now() - 3000).toISOString();
  await page.route('http://127.0.0.1:5183/api/**', route => {
    const path = route.request().url().replace(/^https?:\/\/[^/]+/,'').split('?')[0];
    const json = value => route.fulfill({json:value});
    if (path === '/api/auth/me') return json({id:1,username:'помощник',is_admin:false,csrf_token:'synthetic-only'});
    if (path === '/api/account/profile') return json({first_name:'Александр',last_name:'',email:'',organization:'',position:'',region:'',avatar:null});
    if (path === '/api/chats') return json([]);
    return json({});
  });
  const result = [];
  for (const [width,height,label] of [[1440,1000,'desktop'],[390,844,'mobile']]) {
    await page.setViewportSize({width,height});
    await page.goto('http://127.0.0.1:5183/app');
    await page.locator('.dropzone').waitFor();

    // Snapshot File[] before resetting the native picker: its FileList is live.
    await page.locator('.cab-composer input[type=file]').setInputFiles([{name:'Synthetic verdict.pdf',mimeType:'application/pdf',buffer:Buffer.from('synthetic upload')}]);
    await page.getByRole('button',{name:'Открыть Synthetic verdict.pdf',exact:true}).waitFor();
    await page.getByRole('button',{name:'Удалить файл Synthetic verdict.pdf',exact:true}).click();
    await page.locator('.dropzone').waitFor();

    // Card fills the composer instead of navigating to an empty attach screen;
    // the filled text ends with one space and the caret pinned to the end.
    await page.locator('.sug').first().click();
    const composer = page.locator('.composer-field input');
    await page.waitForFunction(() => {
      const el = document.querySelector('.composer-field input');
      return el && el.value.startsWith('Подготовь проект приговора') && el.value.endsWith('составь текст приговора. ')
        && el.selectionStart === el.value.length;
    }, undefined, {timeout: 5000});
    if (await page.locator('.file-row').count()) throw Error('Suggestion card attached phantom files');
    if (!await composer.evaluate(el => el === document.activeElement)) throw Error('Composer not focused after card click');

    // User typing cancels the animation and keeps their text.
    await page.locator('.sug').nth(1).click();
    await page.waitForTimeout(80);
    await composer.pressSequentially('!', {delay: 0});
    const afterUser = await composer.inputValue();
    await page.waitForTimeout(400);
    if (await composer.inputValue() !== afterUser) throw Error('Typing animation overrode user input');
    if (afterUser === 'Проверь квалификацию по материалам дела: статья, часть и спорные признаки состава. ') throw Error('Animation not cancelled by typing');

    // Pasting a file attaches it; the path must not land in the field as text.
    await page.evaluate(() => {
      const el = document.querySelector('.composer-field input');
      const data = new DataTransfer();
      data.items.add(new File(['материалы дела'], 'Материалы.pdf', {type:'application/pdf'}));
      el.dispatchEvent(new ClipboardEvent('paste', {clipboardData: data, bubbles: true, cancelable: true}));
    });
    await page.locator('.file-row').filter({hasText: 'Материалы.pdf'}).waitFor({timeout: 3000});
    if (await composer.inputValue().then(v => v.includes('Материалы.pdf'))) throw Error('File path pasted as text');
    await page.screenshot({path: 'acceptance-screenshots/' + label + '-paste-attach.png', fullPage: true});

    // Unsupported format produces a readable warning.
    await page.evaluate(() => {
      const el = document.querySelector('.composer-field input');
      const data = new DataTransfer();
      data.items.add(new File(['x'], 'программа.exe', {type:'application/octet-stream'}));
      el.dispatchEvent(new ClipboardEvent('paste', {clipboardData: data, bubbles: true, cancelable: true}));
    });
    await page.locator('.warn-box').filter({hasText: 'формат не поддерживается'}).waitFor({timeout: 3000});
    await page.locator('.warn-box').getByRole('button', {name: 'Понятно', exact: true}).click();
    await page.locator('.warn-box').filter({hasText: 'формат не поддерживается'}).waitFor({state: 'hidden'});

    // Global paste outside the input still attaches files.
    await page.goto('http://127.0.0.1:5183/app');
    await page.locator('.dropzone').waitFor();
    await page.evaluate(() => {
      const data = new DataTransfer();
      data.items.add(new File(['текст дела'], 'obvinenie.txt', {type:'text/plain'}));
      document.body.dispatchEvent(new ClipboardEvent('paste', {clipboardData: data, bubbles: true, cancelable: true}));
    });
    await page.locator('.file-row').filter({hasText: 'obvinenie.txt'}).waitFor({timeout: 3000});

    // /app/attach without files shows the dropzone, not an empty file list.
    await page.goto('http://127.0.0.1:5183/app/attach');
    await page.locator('.dropzone').waitFor({timeout: 3000});
    if (await page.locator('.attach-head').count()) throw Error('Empty attach dead end still rendered');
    if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) throw Error('Horizontal overflow');
    result.push({label, suggestionFill: true, typingCancel: true, pasteAttach: true, formatWarning: true, globalPaste: true, attachDeadEnd: false});
  }
  return result;
}
