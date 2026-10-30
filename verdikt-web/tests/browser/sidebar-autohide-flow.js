// Empty history auto-collapses the desktop sidebar (nothing to show a new
// user); sending the first request expands it back with the new chat listed.
// Manual toggles still work; the mobile drawer is untouched by this rule.
async page => {
  await page.unrouteAll({behavior:'ignoreErrors'});
  const base='http://127.0.0.1:5183';
  const stamp=new Date().toISOString();
  let chats=[];
  const message={id:1,chat_id:9,role:'user',content:'Первый запрос',status:'completed',stage:null,error:null,analysis:null,result:null,created_at:stamp,updated_at:null,attachments:[]};
  await page.route(`${base}/api/**`, route=>{
    const request=route.request();
    const path=request.url().replace(/^https?:\/\/[^/]+/,'').split('?')[0];
    const json=v=>route.fulfill({json:v});
    if (path==='/api/auth/me') return json({id:1,username:'помощник',is_admin:false,csrf_token:'synthetic-only'});
    if (path==='/api/account/profile') return json({firstName:'',lastName:'',avatar:''});
    if (path==='/api/chats'&&request.method()==='GET') return json(chats);
    if (path==='/api/chats'&&request.method()==='POST') { chats=[{id:9,title:null,status:'busy',is_pinned:false,updated_at:stamp}]; return json(chats[0]); }
    if (path==='/api/chats/9/messages'&&request.method()==='POST') return json({user_message:message,assistant_message:{...message,id:2,role:'assistant',content:'Готово'}});
    if (path==='/api/chats/9/messages') return json([message,{...message,id:2,role:'assistant',content:'Готово'}]);
    return json({});
  });
  const collapsed=()=>page.locator('.cab-side').evaluate(el=>el.classList.contains('collapsed'));

  await page.setViewportSize({width:1440,height:1000});
  await page.goto(`${base}/app`);
  // The header menu button is visible only while the sidebar is collapsed.
  const opener=page.getByRole('button',{name:'Открыть боковое меню',exact:true});
  await opener.waitFor();
  if (!await collapsed()) throw Error('Empty history must auto-collapse the sidebar');

  // A manual peek still works and stays until the next empty/non-empty transition.
  await opener.click();
  if (await collapsed()) throw Error('Manual open did not expand the sidebar');
  await page.getByText('Здесь появятся ваши дела. Начните новое дело.',{exact:true}).waitFor();
  await page.getByRole('button',{name:'Свернуть боковое меню',exact:true}).click();
  if (!await collapsed()) throw Error('Manual collapse broken');

  // Sending the first request expands the sidebar and lists the new chat.
  await page.getByRole('textbox',{name:'Задача по делу'}).fill('Первый запрос');
  await page.getByRole('button',{name:'Отправить',exact:true}).click();
  await page.waitForFunction(()=>location.pathname==='/app/case/9/analysis');
  await page.waitForFunction(()=>!document.querySelector('.cab-side').classList.contains('collapsed'));
  await page.waitForFunction(()=>document.querySelectorAll('.cab-chat-row').length===1);

  // The mobile drawer keeps its own rules: closed unless explicitly opened.
  await page.setViewportSize({width:390,height:844});
  await page.waitForTimeout(300);
  if (await page.locator('.cab-side.open').count()) throw Error('Mobile drawer must not auto-open');
  return {collapsedOnEmpty:true,manualToggle:true,expandedOnSend:true,mobileUntouched:true};
}
