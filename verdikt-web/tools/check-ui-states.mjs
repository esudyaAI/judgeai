// Reuse synthetic browser scenarios locally and in CI without a second test dependency.
import {createRequire} from 'node:module';
import {readFile, mkdir} from 'node:fs/promises';
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {resolve} from 'node:path';
import {runInThisContext} from 'node:vm';
const root=fileURLToPath(new URL('../..',import.meta.url));
const frontend=resolve(root,'verdikt-web');
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const external=process.env.UI_STATES_EXTERNAL==='true';
let server, browser;
try {
  if (!external) {
    server=spawn(process.execPath,[resolve(frontend,'node_modules/vite/bin/vite.js'),'--host','127.0.0.1','--port','5185','--strictPort'],{cwd:frontend,stdio:'ignore'});
    let ready=false;
    for(let n=0;n<100;n++) {
      if(server.exitCode!==null) throw Error('UI test server exited before startup');
      try { const response=await fetch('http://127.0.0.1:5185'); if(response.ok){ready=true;break;} } catch {}
      await new Promise(resolve=>setTimeout(resolve,100));
    }
    if(!ready) throw Error('UI test server did not start');
  }
  await mkdir(resolve(root,'acceptance-screenshots'),{recursive:true});
  browser=await chromium.launch({headless:true,...(process.env.UI_BROWSER_CHANNEL ? {channel:process.env.UI_BROWSER_CHANNEL} : {})});
  for(const filename of ['sidebar-row-flow.js','ui-states-flow.js','ui-races-flow.js','thinking-flow.js','document-panel-flow.js','text-lifecycle-flow.js','composer-flow.js','avatar-profile-flow.js','draft-flow.js']) {
    const context=await browser.newContext();
    const page=await context.newPage(); page.setDefaultTimeout(10000);
    const errors=[]; page.on('pageerror',error=>errors.push(error.message));
    try {
      const source=(await readFile(resolve(frontend,'tests/browser',filename),'utf8')).replaceAll('127.0.0.1:5183','127.0.0.1:5185');
      const flow=runInThisContext('('+source+')',{filename});
      console.log(filename,JSON.stringify(await flow(page)));
      if(errors.length) throw Error(`Browser exceptions: ${errors.join('; ')}`);
    } catch(error) {
      await page.screenshot({path:resolve(root,'acceptance-screenshots',filename+'-failure.png'),fullPage:true}).catch(()=>{});
      throw error;
    } finally { await context.close(); }
  }
} finally {
  await browser?.close();
  if(server && server.exitCode===null) { server.kill('SIGTERM'); await new Promise(resolve=>server.once('exit',resolve)); }
}
