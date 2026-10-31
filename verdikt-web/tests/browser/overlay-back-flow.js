// Mobile «back» closes overlays instead of navigating away: the drawer, the
// delete dialog above it (nested order), and the document panel. UI closes
// (Escape, «Отмена») keep the history balanced — a later back press is a no-op.
async page => {
  await page.unrouteAll({behavior:'ignoreErrors'});
  const base='http://127.0.0.1:5183';
  const stamp=new Date().toISOString();
  await page.route(`${base}/api/**`, route=>{
    const path=route.request().url().replace(/^https?:\/\/[^/]+/,'').split('?')[0];
    const json=v=>route.fulfill({json:v});
    if (path==='/api/auth/me') return json({id:1,username:'помощник',is_admin:false,csrf_token:'synthetic-only'});
    if (path==='/api/account/profile') return json({firstName:'',lastName:'',avatar:''});
    if (path==='/api/chats') return json([{id:1,title:'Дело с документом',status:'ready',is_pinned:false,updated_at:stamp}]);
    if (path==='/api/chats/1/messages') return json([{id:1,chat_id:1,role:'user',content:'Документ',status:'completed',stage:null,error:null,analysis:null,result:null,created_at:stamp,updated_at:null,attachments:[{id:1,filename:'Документ.txt',page_count:null,extraction_status:'ok'}]}]);
    if (path.endsWith('/attachments/1/file')) return route.fulfill({body:'Текст документа',contentType:'text/plain'});
    return json({});
  });
  await page.setViewportSize({width:390,height:844});
  // Start with two real history entries: /app, then the case via in-app navigation.
  await page.goto(`${base}/app`);
  await page.getByRole('button',{name:'Открыть боковое меню',exact:true}).click();
  await page.locator('.cab-row').filter({hasText:'Дело с документом'}).click();
  await page.waitForFunction(()=>location.pathname==='/app/case/1/result');
  const url=`${base}/app/case/1/result`;
  const back=async()=>{ await page.evaluate(()=>history.back()); await page.waitForTimeout(120); };
  const drawerOpen=()=>page.locator('.cab-side.open').count();
  const dialogOpen=()=>page.locator('dialog[open]').count();
  const panelOpen=()=>page.locator('.document-panel:not([inert])').count();
  await page.getByRole('button',{name:'Открыть Документ.txt',exact:true}).waitFor();

  // Back closes the drawer; the page stays.
  await page.getByRole('button',{name:'Открыть боковое меню',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('.cab-side')?.classList.contains('open'));
  await back();
  if (await drawerOpen()) throw Error('Back did not close the drawer');
  if (page.url()!==url) throw Error('Back navigated away instead of closing the drawer');

  // Nested: drawer + delete dialog — back closes the topmost first.
  await page.getByRole('button',{name:'Открыть боковое меню',exact:true}).click();
  await page.getByRole('button',{name:'Действия чата «Дело с документом»',exact:true}).click();
  await page.getByRole('menuitem',{name:'Удалить чат',exact:true}).click();
  await page.locator('dialog[open]').waitFor();
  await back();
  if (await dialogOpen()) throw Error('Back did not close the dialog');
  if (!await drawerOpen()) throw Error('Back closed the drawer under the dialog — order broken');
  await back();
  if (await drawerOpen()) throw Error('Second back did not close the drawer');
  if (page.url()!==url) throw Error('Back navigated away from the case');

  // Back closes the fullscreen document panel.
  await page.getByRole('button',{name:'Открыть Документ.txt',exact:true}).click();
  await page.getByText('Текст документа',{exact:true}).waitFor();
  if (!await panelOpen()) throw Error('Document panel did not open');
  await back();
  await page.waitForFunction(()=>document.querySelectorAll('.document-panel:not([inert])').length===0);
  if (page.url()!==url) throw Error('Back navigated away instead of closing the document');

  // UI closes pop their sentinel: one later back press must land on the
  // previous real page (/app) — not be swallowed by a leftover overlay entry.
  await page.getByRole('button',{name:'Открыть боковое меню',exact:true}).click();
  await page.keyboard.press('Escape');
  await page.waitForFunction(()=>!document.querySelector('.cab-side')?.classList.contains('open'));
  await back();
  if (page.url()!==`${base}/app`) throw Error('UI close left a dangling history entry: '+page.url());

  // Desktop: the dialog and the document panel close on back as well (the
  // desktop sidebar is not an overlay and keeps its own rules).
  await page.setViewportSize({width:1440,height:1000});
  await page.goto(url);
  await page.getByRole('button',{name:'Открыть Документ.txt',exact:true}).waitFor();
  await page.getByRole('button',{name:'Действия чата «Дело с документом»',exact:true}).click();
  await page.getByRole('menuitem',{name:'Удалить чат',exact:true}).click();
  await page.locator('dialog[open]').waitFor();
  await back();
  if (await dialogOpen()) throw Error('Back did not close the dialog on desktop');
  if (page.url()!==url) throw Error('Desktop back navigated away instead of closing the dialog');
  await page.getByRole('button',{name:'Открыть Документ.txt',exact:true}).click();
  await page.getByText('Текст документа',{exact:true}).waitFor();
  await back();
  await page.waitForFunction(()=>document.querySelectorAll('.document-panel:not([inert])').length===0);
  if (page.url()!==url) throw Error('Desktop back navigated away instead of closing the document');
  return {drawer:true,nested:true,document:true,balanced:true,desktop:true};
}
