// Pinning/unpinning must slide the row between groups (FLIP movement): the row
// never disappears and never teleports — its Y is sampled on every frame.
async page => {
  await page.unrouteAll({behavior:'ignoreErrors'});
  const base='http://127.0.0.1:5183';
  const chats=[
    {id:1,title:'Первое дело',status:'ready',is_pinned:false,updated_at:'2026-10-29T12:00:00Z'},
    {id:2,title:'Второе дело',status:'ready',is_pinned:false,updated_at:'2026-10-29T11:00:00Z'},
    {id:3,title:'Третье дело',status:'ready',is_pinned:false,updated_at:'2026-10-29T10:00:00Z'},
  ];
  await page.route(`${base}/api/**`, route=>{
    const path=route.request().url().replace(/^https?:\/\/[^/]+/,'').split('?')[0];
    const json=v=>route.fulfill({json:v});
    const pin=path.match(/^\/api\/chats\/(\d+)\/pin$/);
    if (path==='/api/auth/me') return json({id:1,username:'помощник',is_admin:false,csrf_token:'synthetic-only'});
    if (path==='/api/account/profile') return json({firstName:'',lastName:'',avatar:''});
    if (pin) {
      const chat=chats.find(c=>c.id===Number(pin[1]));
      chat.is_pinned=route.request().postDataJSON().pinned;
      return json(chat);
    }
    if (path==='/api/chats') return json([...chats].sort((a,b)=>Number(b.is_pinned)-Number(a.is_pinned)));
    return json({});
  });
  await page.setViewportSize({width:1440,height:1000});
  await page.goto(`${base}/app`);
  await page.locator('.cab-chat-row').nth(2).waitFor();

  const order=()=>page.locator('.cab-chat-row .cab-row-title').allTextContents();
  const watch=title=>page.evaluate(async t=>{
    const row=()=>[...document.querySelectorAll('.cab-chat-row')].find(r=>r.textContent.includes(t));
    const ys=[]; let minRows=Infinity;
    const start=performance.now();
    while (performance.now()-start<1000) {
      await new Promise(requestAnimationFrame);
      const el=row(); ys.push(el?el.getBoundingClientRect().y:-1);
      minRows=Math.min(minRows,document.querySelectorAll('.cab-chat-row').length);
    }
    return {ys,minRows};
  },title);
  const assertMoved=({ys,minRows},settled,label)=>{
    if (minRows!==3) throw Error(`${label}: a row disappeared during the move (minRows=${minRows})`);
    const last=ys.at(-1);
    if (Math.abs(last-settled)>2) throw Error(`${label}: row settled at ${last}, expected ${settled}`);
    const range=Math.max(...ys)-Math.min(...ys);
    if (range<30) throw Error(`${label}: row barely moved (range=${range}px)`);
    let maxDelta=0;
    for (let i=1;i<ys.length;i++) maxDelta=Math.max(maxDelta,Math.abs(ys[i]-ys[i-1]));
    if (maxDelta>range*0.6) throw Error(`${label}: row teleported — jump of ${Math.round(maxDelta)}px in one frame over range ${Math.round(range)}px`);
  };

  const yOf=async title=>await page.evaluate(t=>{
    const row=[...document.querySelectorAll('.cab-chat-row')].find(r=>r.textContent.includes(t));
    return row?row.getBoundingClientRect().y:-1;
  },title);

  // Pin «Третье дело»: it slides from the bottom of «Недавние» into «Закреплённые».
  const before=await yOf('Третье дело');
  await page.getByRole('button',{name:'Действия чата «Третье дело»',exact:true}).click();
  await page.getByRole('menuitem',{name:'Закрепить',exact:true}).click();
  const pinned=await watch('Третье дело');
  const afterPin=await yOf('Третье дело');
  if (afterPin>=before) throw Error('Pinned row must end up higher in the list');
  assertMoved(pinned,afterPin,'pin');
  const titles=await order();
  if (titles[0]!=='Третье дело') throw Error('Pinned chat must lead the list, got '+titles.join('|'));
  if (await page.getByText('Обновляем',{exact:false}).count()) throw Error('Pin must not flash a layout-shifting status line');

  // Unpin: it slides back down, again without vanishing or teleporting.
  await page.getByRole('button',{name:'Действия чата «Третье дело»',exact:true}).click();
  await page.getByRole('menuitem',{name:'Открепить',exact:true}).click();
  const unpinned=await watch('Третье дело');
  const afterUnpin=await yOf('Третье дело');
  assertMoved(unpinned,afterUnpin,'unpin');
  if (Math.abs(afterUnpin-before)>2) throw Error('Unpinned row must return to its original slot');
  return {pin:true,unpin:true,smooth:true};
}
