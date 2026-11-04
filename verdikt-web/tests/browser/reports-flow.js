async page => {
  const results = [];
  for (const [width, height] of [[1440, 1000], [390, 844]]) {
    await page.unrouteAll({behavior:'ignoreErrors'});
    let failList = true, created = 0, downloaded = 0;
    const analysis = {schema_version:1, stats:{documents:1,pages:1,seconds:1}, prompt:'', fabula:'Сохранённая синтетическая фабула', qualification:null, scale:null, draft:null, mitigating:[], aggravating:null, personality:null, variants:[], similar:[], warnings:[], legal_checks:[], defendants:[]};
    const report = {id:'00000000-0000-4000-8000-000000000014',chat_id:1,source_message_id:2,version:1,snapshot_sha256:'synthetic',docx_sha256:'synthetic',created_at:'2026-11-04T12:00:00Z'};
    await page.route('http://127.0.0.1:5183/api/**', route => {
      const path = new URL(route.request().url()).pathname;
      if (path === '/api/auth/me') return route.fulfill({json:{id:1,username:'synthetic',is_admin:false,csrf_token:'synthetic'}});
      if (path === '/api/chats') return route.fulfill({json:[{id:1,title:'Синтетическое дело',status:'ready',updated_at:report.created_at}]});
      if (path === '/api/reports') return failList ? route.fulfill({status:503,json:{detail:'Повторите загрузку'}}) : route.fulfill({json:[report]});
      if (path.endsWith('/docx')) { downloaded++; return route.fulfill({contentType:'application/vnd.openxmlformats-officedocument.wordprocessingml.document',body:'PKsynthetic'}); }
      if (path === '/api/reports/'+report.id) return route.fulfill({json:{...report,snapshot:{chat_title:'Синтетическое дело',analysis,limitations:['Редакция модели неизвестна'],human_review:{status:'not_reviewed'},materials:[]}}});
      if (path.endsWith('/reports')) { created++; if (route.request().headers()['x-csrf-token'] !== 'synthetic') throw Error('Missing CSRF'); return route.fulfill({status:201,json:report}); }
      if (path.endsWith('/messages/stream')) return route.fulfill({status:503});
      if (path.endsWith('/messages')) return route.fulfill({json:[{id:2,role:'assistant',status:'completed',stage:null,error:null,attachments:[],result:analysis}]});
      return route.fulfill({json:{}});
    });
    await page.setViewportSize({width,height});
    await page.goto('http://127.0.0.1:5183/app/reports');
    await page.getByRole('alert').filter({hasText:'Повторите загрузку'}).waitFor();
    failList = false;
    await page.getByRole('button',{name:'Повторить',exact:true}).click();
    await page.getByRole('button',{name:'Дело 1 · версия 1',exact:true}).click();
    await page.getByText('Не проверено человеком',{exact:true}).waitFor();
    await page.getByText('Редакция модели неизвестна',{exact:true}).waitFor();
    await page.screenshot({path:`acceptance-screenshots/reports-${width}.png`,fullPage:true});
    if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) throw Error('Reports overflow');
    await page.getByRole('button',{name:'Скачать DOCX',exact:true}).first().click();
    await page.goto('http://127.0.0.1:5183/app/case/1/result');
    await page.getByRole('button',{name:'Скачать DOCX',exact:true}).click();
    await page.getByRole('link',{name:'Отчёт · версия 1',exact:true}).waitFor();
    if (created !== 1 || downloaded !== 2) throw Error(`Report requests ${created}/${downloaded}`);
    results.push({width,created,downloaded});
  }
  return results;
}
