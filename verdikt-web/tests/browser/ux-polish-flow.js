// UX polish acceptance: switching documents keeps the panel mounted (the previous
// viewer stays on screen while the next one prepares), «Показать все» expands the
// similar list smoothly, the sidebar collapses with a width animation, settings tabs
// swap instantly (opacity fade only), and case loading shows a shimmer skeleton
// instead of a flashing «Загружаем дело…» notice.
async page => {
  await page.unrouteAll({behavior:'ignoreErrors'});
  const pdfBytes = "%PDF-1.7\n%1234\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R 5 0 R] /Count 2 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 7 0 R >> >> >>\nendobj\n4 0 obj\n<< /Length 50 >>\nstream\nBT /F1 12 Tf 72 720 Td (Synthetic judgment.) Tj ET\nendstream\nendobj\n5 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 6 0 R /Resources << /Font << /F1 7 0 R >> >> >>\nendobj\n6 0 obj\n<< /Length 50 >>\nstream\nBT /F1 12 Tf 72 720 Td (Synthetic judgment.) Tj ET\nendstream\nendobj\n7 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\nxref\n0 8\n0000000000 65535 f\n0000000015 00000 n\n0000000064 00000 n\n0000000127 00000 n\n0000000253 00000 n\n0000000353 00000 n\n0000000479 00000 n\n0000000579 00000 n\ntrailer\n<< /Size 8 /Root 1 0 R >>\nstartxref\n649\n%%EOF\n";
  const created = new Date(Date.now() - 300000).toISOString();
  const similar = Array.from({length: 8}, (_, i) => ({verdict_id: i + 101, punishment: `Наказание ${i + 1}`, court: `Суд ${i}`, match: '158 ч.2', score: 90 - i}));
  const analysis = {schema_version: 2, fabula: 'Фабула для проверки переключения документов.', prompt: 'Проверь материалы.',
    stats: {documents: 2, pages: 10, seconds: 120}, warnings: [], similar, variants: [], mitigating: [], legal_checks: []};
  const messages = delay => [
    {id: 1, role: 'user', content: 'Проверь материалы дела.', status: 'completed', attachments: [{id: 11, filename: 'Материалы.pdf', page_count: 2, extraction_status: 'ok'}, {id: 12, filename: 'Word.docx', page_count: 2, extraction_status: 'ok'}], created_at: created, error: null, stage: null, result: null},
    {id: 2, role: 'assistant', content: null, status: 'completed', stage: null, created_at: created, error: null, analysis, attachments: []},
  ];
  let slowVerdict = 0;
  let wordReady = false;
  let chat2Delay = 0;
  await page.route('http://127.0.0.1:5183/api/**', async route => {
    const path = route.request().url().replace(/^https?:\/\/[^/]+/, '').split('?')[0];
    const json = value => route.fulfill({json: value});
    if (path === '/api/auth/me') return json({id:1,username:'synthetic-user',is_admin:false,csrf_token:'synthetic-only'});
    if (path === '/api/account/profile') return json({first_name:'Александр',last_name:'',email:'',organization:'',position:'',region:'',avatar:null});
    if (path === '/api/account/sessions') return json([]);
    if (path === '/api/chats') return json([{id:1,title:'Дело с документами',is_pinned:false,status:'ready',updated_at:created},{id:2,title:'Второе дело',is_pinned:false,status:'ready',updated_at:created}]);
    if (path === '/api/chats/1/messages') return json(messages(0));
    if (path === '/api/chats/2/messages') { if (chat2Delay) await new Promise(resolve => setTimeout(resolve, chat2Delay)); return json(messages(0)); }
    if (path.startsWith('/api/knowledge/verdicts/') && path.endsWith('/text')) {
      const id = Number(path.split('/')[4]);
      if (slowVerdict === id) await new Promise(resolve => setTimeout(resolve, 700));
      return route.fulfill({body: `Текст приговора ${id} для панельного теста.`, contentType: 'text/plain'});
    }
    if (path.endsWith('/attachments/11/file')) return route.fulfill({body: pdfBytes, contentType: 'application/pdf'});
    if (path.endsWith('/attachments/12/preview')) { wordReady = false; return json({id:'word-preview',filename:'Word.docx',status:'queued',error:null}); }
    if (path === '/api/document-previews/word-preview') return json({id:'word-preview',filename:'Word.docx',status:(wordReady = !wordReady) ? 'ready' : 'converting',error:null});
    if (path.startsWith('/api/document-previews/word-preview/file')) return route.fulfill({body: pdfBytes, contentType: 'application/pdf'});
    if (path.endsWith('/attachments/12/file')) return route.fulfill({body: 'word-bytes', contentType: 'application/octet-stream'});
    return json({});
  });
  const result = [];
  for (const [width,height,label] of [[1440,1000,'desktop'],[390,844,'mobile']]) {
    const mobile = label === 'mobile';
    const closePanel = async () => {
      await page.getByRole('button', {name: 'Закрыть документ', exact: true}).click();
      await page.waitForFunction(() => document.querySelectorAll('.document-panel').length === 0);
    };
    await page.setViewportSize({width, height});
    await page.goto('http://127.0.0.1:5183/app/case/1/result');
    await page.locator('.similar-row').first().waitFor();

    // Documents: the panel must not unmount while switching.
    await page.getByRole('button', {name: 'Открыть Материалы.pdf', exact: true}).click();
    await page.locator('.document-panel .pdf-page-slot').first().waitFor();
    await page.locator('.document-panel').evaluate(el => { el.dataset.flow = 'kept'; });
    if (mobile) await closePanel();
    await page.getByRole('button', {name: 'Открыть Word.docx', exact: true}).click();
    if (mobile) {
      await page.locator('.document-panel-progress').waitFor({timeout: 3000}).catch(() => {});
      await page.locator('.document-panel .pdf-page-slot').first().waitFor({timeout: 8000});
      await closePanel();
    } else {
      await page.locator('.document-panel-progress').waitFor({timeout: 3000});
      const kept = await page.locator('.document-panel').evaluate(el => el.dataset.flow === 'kept');
      if (!kept) throw Error('Document panel remounted on switch');
      if (!await page.locator('.document-panel .pdf-page-slot').count()) throw Error('Previous document vanished during conversion');
      await page.waitForTimeout(2500);
      if (await page.locator('.document-panel').count() !== 1) throw Error('More than one document panel');
    }
    await page.locator('.similar-row').nth(0).click();
    await page.locator('.text-document pre').waitFor();
    if (mobile) await closePanel(); else await page.locator('.document-panel').evaluate(el => { el.dataset.flow = 'kept2'; });
    slowVerdict = 102;
    await page.locator('.similar-row').nth(1).click();
    if (!mobile) {
      await page.waitForTimeout(150);
      if (!await page.locator('.document-panel').evaluate(el => el.dataset.flow === 'kept2')) throw Error('Verdict switch remounted the panel');
    }
    await page.locator('.text-document pre').filter({hasText: 'Текст приговора 102'}).waitFor();
    await closePanel();
    await page.screenshot({path: 'acceptance-screenshots/' + label + '-document-switch.png', fullPage: true});

    // «Показать все»/«Свернуть»: rows expand and collapse, nothing jumps.
    if (await page.locator('.similar-row').count() !== 5) throw Error('Expected 5 similar rows by default');
    await page.getByRole('button', {name: /Показать все \(8\)/}).click();
    await page.locator('.similar-more').waitFor();
    if (await page.locator('.similar-row').count() !== 8) throw Error('Expand lost rows');
    await page.getByRole('button', {name: 'Свернуть', exact: true}).click();
    await page.waitForTimeout(500);
    if (await page.locator('.similar-row').count() !== 5 || await page.locator('.similar-more').count()) throw Error('Collapse left rows behind');

    // Sidebar: desktop collapses with an animated margin, mobile keeps the drawer.
    if (!mobile) {
      await page.getByRole('button', {name: 'Свернуть боковое меню', exact: true}).click();
      const margin = await page.locator('.cab-side').evaluate(el => getComputedStyle(el).marginLeft);
      if (margin !== '-272px') throw Error('Sidebar collapse is not animated to the margin: ' + margin);
    }

    // Settings tabs: instant swap, opacity fade only.
    await page.goto('http://127.0.0.1:5183/app/settings');
    await page.locator('[role="tabpanel"]').waitFor();
    await page.getByRole('tab', {name: 'Безопасность', exact: true}).click();
    await page.waitForFunction(() => document.querySelector('[role="tabpanel"]')?.textContent.includes('Изменить пароль'));
    const panelStyle = await page.locator('[role="tabpanel"]').evaluate(el => ({transform: getComputedStyle(el).transform, animationName: getComputedStyle(el).animationName}));
    if (panelStyle.transform !== 'none') throw Error('Tab panel still slides/scales');
    if (panelStyle.animationName !== 'set-panel-in') throw Error('Tab fade animation missing');

    // Case loading: skeleton with shimmer, not a flashing text notice.
    chat2Delay = 900;
    await page.goto('http://127.0.0.1:5183/app/case/1/result');
    await page.locator('.similar-row').first().waitFor();
    if (mobile) await page.getByRole('button', {name: 'Открыть боковое меню', exact: true}).click();
    await page.locator('.cab-row').filter({hasText: 'Второе дело'}).click();
    await page.locator('.case-skeleton').waitFor();
    const skeleton = await page.locator('.case-skeleton').evaluate(el => ({role: el.getAttribute('role'), busy: el.getAttribute('aria-busy'), notice: el.querySelector('.state-notice') !== null, announce: el.querySelector('.sr-only')?.textContent}));
    if (skeleton.role !== 'status' || skeleton.busy !== 'true' || skeleton.notice || skeleton.announce !== 'Загружаем дело…') throw Error('Case skeleton wrong: ' + JSON.stringify(skeleton));
    await page.locator('.similar-row').first().waitFor();
    if (await page.locator('.case-skeleton').count()) throw Error('Skeleton stayed after loading');
    if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) throw Error('Horizontal overflow');
    result.push({label, documentSwitch: !mobile || 'fullscreen close/open', similarExpand: true, sidebar: mobile ? 'drawer' : 'animated', tabs: 'fade', caseSkeleton: true});
  }
  return result;
}
