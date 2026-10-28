async page => {
  await page.unrouteAll({behavior:'ignoreErrors'});
  const pdfBytes = "%PDF-1.7\n%1234\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R 5 0 R] /Count 2 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 7 0 R >> >> >>\nendobj\n4 0 obj\n<< /Length 50 >>\nstream\nBT /F1 12 Tf 72 720 Td (Synthetic judgment.) Tj ET\nendstream\nendobj\n5 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 6 0 R /Resources << /Font << /F1 7 0 R >> >> >>\nendobj\n6 0 obj\n<< /Length 50 >>\nstream\nBT /F1 12 Tf 72 720 Td (Synthetic judgment.) Tj ET\nendstream\nendobj\n7 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\nxref\n0 8\n0000000000 65535 f \n0000000015 00000 n \n0000000064 00000 n \n0000000127 00000 n \n0000000253 00000 n \n0000000353 00000 n \n0000000479 00000 n \n0000000579 00000 n \ntrailer\n<< /Size 8 /Root 1 0 R >>\nstartxref\n649\n%%EOF\n";
  const messages = [
    {id:1,role:'user',content:'Review this synthetic verdict.',status:'completed',attachments:[{id:11,filename:'Synthetic verdict.pdf',page_count:1,extraction_status:'ok'},{id:12,filename:'Word judgment.docx',page_count:2,extraction_status:'ok'}]},
    {id:2,role:'assistant',content:'Initial assessment of the synthetic case.',status:'completed',attachments:[]},
    {id:3,role:'user',content:'Explain the previous conclusion.',status:'completed',attachments:[]},
    {id:4,role:'assistant',content:'Follow-up explanation uses the earlier documents.',status:'completed',attachments:[]},
    {id:5,role:'user',content:'A failed earlier attempt.',status:'completed',attachments:[]},
    {id:6,role:'assistant',error:'Synthetic analysis failure',status:'failed',attachments:[]},
  ];
  let wordPolls = 0;
  let fileRequests = 0;
  await page.route('http://127.0.0.1:5183/api/**', async route => {
    const path = route.request().url().replace(/^https?:\/\/[^/]+/, '').split('?')[0];
    const json = value => route.fulfill({json:value});
    if (path === '/api/auth/me') return json({id:1,username:'synthetic-user',is_admin:false,csrf_token:'synthetic-only'});
    if (path === '/api/account/profile') return json({first_name:'',last_name:'',organization:'',position:'',phone:''});
    if (path === '/api/chats') return json([{id:1,title:'Synthetic case · document workspace',status:'ready',updated_at:'2026-10-28T12:00:00Z'}]);
    if (path === '/api/chats/1/messages') return json(messages);
    if (path.endsWith('/preview')) { wordPolls = 0; return json({id:'word-preview',filename:'Word judgment.docx',status:'queued',error:null}); }
    if (path === '/api/document-previews/word-preview') return json({id:'word-preview',filename:'Word judgment.docx',status:++wordPolls > 1 ? 'ready' : 'converting',error:null});
    if (path.endsWith('/file')) { if (++fileRequests === 1) return route.fulfill({status:404,json:{detail:'Synthetic transient failure'}}); return route.fulfill({body:pdfBytes,contentType:'application/pdf'}); }
    return json({});
  });
  const results = [];
  for (const [width,height,label] of [[1440,1000,'desktop'],[390,844,'mobile']]) {
    fileRequests = 0;
    await page.setViewportSize({width,height});
    await page.goto('http://127.0.0.1:5183/app/case/1/result');
    await page.locator('[data-message-id="6"]').waitFor();
    if (await page.locator('[data-message-id]').count() !== 6) throw Error('History truncated');
    await page.getByRole('button',{name:'Открыть Synthetic verdict.pdf',exact:true}).click();
    await page.getByRole('button',{name:'Повторить загрузку PDF',exact:true}).waitFor();
    await page.getByRole('button',{name:'Повторить загрузку PDF',exact:true}).click();
    await page.locator('.document-panel canvas[data-rendered="true"]').first().waitFor();
    if (await page.getByRole('button',{name:'Следующая',exact:true}).count()) throw Error('Page navigation buttons must be absent');
    await page.locator('[data-pdf-page="2"]').scrollIntoViewIfNeeded();
    await page.locator('[data-pdf-page="2"] canvas[data-rendered="true"]').waitFor();
    if (await page.locator('.pdf-pages').evaluate(el => el.scrollTop) <= 0) throw Error('Pages did not scroll vertically');
    await page.locator('[data-pdf-page="1"]').scrollIntoViewIfNeeded();
    await page.locator('[data-pdf-page="1"] canvas[data-rendered="true"]').waitFor();
    const panel = await page.locator('.document-panel').boundingBox();
    if (width > 900 && panel.x < width/2) throw Error('Desktop document not on right');
    if (width <= 900 && (panel.x !== 0 || panel.width !== width)) throw Error('Mobile panel not full screen');
    if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) throw Error('Horizontal overflow');
    await page.screenshot({path:'acceptance-screenshots/'+label+'-document-panel.png',fullPage:true});
    await page.getByRole('button',{name:'Закрыть документ',exact:true}).click();
    await page.getByRole('button',{name:'Открыть Word judgment.docx',exact:true}).click();
    await page.getByText('Подготавливаем документ',{exact:true}).waitFor();
    await page.locator('.document-panel canvas[data-rendered="true"]').first().waitFor();
    await page.screenshot({path:'acceptance-screenshots/'+label+'-word-preview.png',fullPage:true});
    await page.getByRole('button',{name:'Закрыть документ',exact:true}).focus();
    await page.keyboard.press('Escape');
    if (await page.locator('.document-panel').count()) throw Error('Escape did not close preview');
    if (await page.getByRole('button',{name:'Открыть Word judgment.docx',exact:true}).evaluate(el => el !== document.activeElement)) throw Error('Focus was not restored');
    await page.reload();
    await page.locator('[data-message-id="6"]').waitFor();
    if (await page.locator('[data-message-id]').count() !== 6) throw Error('History lost on reload');
    results.push({label,width,history:6,pdf:true,word:true,focus:true,reload:true});
  }
  return results;
}
