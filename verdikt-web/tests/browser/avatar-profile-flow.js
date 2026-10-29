async page => {
  const base='http://127.0.0.1:5185';
  let saved=null;
  const profile={firstName:'Анна',lastName:'',email:'',position:'',org:'',region:'',avatar:''};
  await page.route(`${base}/api/**`,route=>{
    const path=route.request().url().replace(/^https?:\/\/[^/]+/,'').split('?')[0];
    if(path==='/api/auth/me')return route.fulfill({json:{id:1,username:'tester1',csrf_token:'synthetic'}});
    if(path==='/api/account/profile') {
      if(route.request().method()==='PUT'){saved=route.request().postDataJSON();return route.fulfill({json:saved});}
      return route.fulfill({json:profile});
    }
    return route.fulfill({json:[]});
  });
  await page.goto(`${base}/app/settings`);
  await page.getByRole('button',{name:'Изменить фото',exact:true}).waitFor();
  if(await page.getByText('Данные профиля видны только вам.',{exact:false}).count() || await page.getByText('контактное поле',{exact:false}).count()) throw Error('Removed profile explanations remain');
  const compression=await page.evaluate(async()=>{
    const {prepareAvatar}=await import('/src/cabinet/avatarImage.ts');
    const canvas=document.createElement('canvas');canvas.width=1600;canvas.height=1200;
    const context=canvas.getContext('2d'), image=context.createImageData(1600,1200);
    let seed=7;
    for(let i=0;i<image.data.length;i+=4){for(let n=0;n<3;n++){seed=(seed*1664525+1013904223)>>>0;image.data[i+n]=seed>>>24;}image.data[i+3]=255;}
    context.putImageData(image,0,0);
    const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));
    if(blob.size<=256*1024)throw Error('Fixture is not large enough');
    const output=await prepareAvatar(new File([blob],'Фото.png',{type:'image/png'}));
    const decoded=new Image();decoded.src=output;await decoded.decode();
    const bytes=atob(output.split(',')[1]).length;
    if(bytes>256*1024 || Math.max(decoded.naturalWidth,decoded.naturalHeight)>512)throw Error('Avatar output exceeds server budget');
    let rejected=false;
    try{await prepareAvatar(new File(['broken'],'wrong.png',{type:'image/png'}));}catch{rejected=true;}
    if(!rejected)throw Error('Broken image accepted');
    const transfer=new DataTransfer();transfer.items.add(new File([blob],'Фото.png',{type:'image/png'}));
    const input=document.querySelector('.settings input[type=file]');input.files=transfer.files;input.dispatchEvent(new Event('change',{bubbles:true}));
    return {inputBytes:blob.size,outputBytes:bytes,width:decoded.naturalWidth,height:decoded.naturalHeight,corruptRejected:true};
  });
  await page.getByText('Фото выбрано. Нажмите «Сохранить профиль».',{exact:true}).waitFor();
  if(saved)throw Error('Avatar saved before explicit profile save');
  await page.getByRole('button',{name:'Сохранить профиль',exact:true}).click();
  await page.getByText('Профиль сохранён',{exact:true}).waitFor();
  if(!saved?.avatar?.startsWith('data:image/'))throw Error('Compressed avatar missing from profile');
  const results=[];
  for(const [width,height] of [[1440,1000],[390,844]]){
    await page.setViewportSize({width,height});
    await page.waitForFunction(()=>{const el=document.querySelector('[role=tabpanel]');return el && getComputedStyle(el).opacity==='1';});
    if(await page.locator('.settings .avatar-lg').evaluate(el=>el.getBoundingClientRect().width)!==96)throw Error('Avatar is not 96px');
    await page.screenshot({path:`acceptance-screenshots/profile-avatar-${width}.png`,fullPage:true});
    if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Profile overflow');
    results.push({width,avatar96:true});
  }
  await page.setViewportSize({width:1440,height:1000});
  const icon=await page.getByRole('button',{name:'Свернуть боковое меню',exact:true}).locator('svg').innerHTML();
  await page.getByRole('button',{name:'Свернуть боковое меню',exact:true}).click();
  if(await page.getByRole('button',{name:'Открыть боковое меню',exact:true}).locator('svg').innerHTML()!==icon)throw Error('Sidebar icon changed');
  return {compression,results,stableSidebarIcon:true};
}
