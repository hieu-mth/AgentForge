/* Trusted browser QA runner baked into Owner-pinned image.
 * Executes AI code ONLY within the offline, restricted Docker container.
 * No app source code, stdout, URLs, DOM text or exception messages are printed.
 */
import {spawn, spawnSync} from 'node:child_process';
import {setTimeout as sleep} from 'node:timers/promises';
import {chromium} from 'playwright-core';

const cwd='/work', origin='http://127.0.0.1:5198';
function emit(status,code,details={}){
  process.stdout.write(JSON.stringify({format:'agentforge.webapp.browser-smoke.v1',
    status,code, ...details})+'\n');
}
function command(cmd,args,timeout){
  const p=spawnSync(cmd,args,{cwd,stdio:'ignore',timeout,env:{
    PATH:process.env.PATH||'/usr/local/bin:/usr/bin:/bin',HOME:'/tmp',CI:'1',
    npm_config_offline:'true',npm_config_audit:'false'}});
  return !p.error && p.status===0;
}
let server=null, browser=null;
try{
  if(!command('npm',['run','test'],45000)){
    emit('FAIL','NODE_TEST_FAILED');process.exitCode=0;
  }else if(!command('npm',['run','build'],65000)){
    emit('FAIL','VITE_BUILD_FAILED');process.exitCode=0;
  }else{
    server=spawn(process.execPath,
      ['/opt/agentforge/node_modules/vite/bin/vite.js','preview',
       '--host','127.0.0.1','--port','5198','--strictPort'],
      {cwd,stdio:'ignore',env:{PATH:process.env.PATH||'',HOME:'/tmp'}});
    let ready=false;
    for(let i=0;i<45;i++){
      if(server.exitCode!==null)break;
      try{const r=await fetch(origin,{signal:AbortSignal.timeout(1000)});
        if(r.ok){ready=true;break;}}catch{}
      await sleep(200);
    }
    if(!ready){emit('FAIL','PREVIEW_UNAVAILABLE');}
    else{
      browser=await chromium.launch({headless:true,executablePath:'/usr/bin/chromium',
        args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu']});
      const page=await browser.newPage({viewport:{width:1280,height:800},
        deviceScaleFactor:1});
      let errors=0,external=0;
      page.on('pageerror',()=>{errors+=1;});
      page.on('console',m=>{if(m.type()==='error')errors+=1;});
      await page.route('**/*',r=>{
        const url=r.request().url();
        if(url!==origin && !url.startsWith(origin+'/')){
          external+=1;return r.abort();}
        return r.continue();
      });
      await page.goto(origin,{waitUntil:'networkidle',timeout:15000});
      const desktopVisible=await page.locator('main').count()>0;
      const desktopText=await page.locator('body').innerText();
      const desktopButtons=await page.locator('button:visible:not([disabled])').count();
      const desktop=await page.screenshot({type:'png',fullPage:false,
        animations:'disabled',timeout:10000});
      if(desktopButtons>0){
        await page.locator('button:visible:not([disabled])').first().click({timeout:5000});
      }
      await page.setViewportSize({width:375,height:812});
      await page.reload({waitUntil:'networkidle',timeout:15000});
      const mobileText=await page.locator('body').innerText();
      const widthOk=await page.evaluate(()=>
        document.documentElement.scrollWidth<=window.innerWidth+2);
      const mobile=await page.screenshot({type:'png',fullPage:false,
        animations:'disabled',timeout:10000});
      const checks={desktop_main:desktopVisible,body_content:
        desktopText.trim().length>=20 && mobileText.trim().length>=20,
        interactive_button:desktopButtons>0,mobile_no_overflow:widthOk,
        no_page_errors:errors===0,no_external_requests:external===0};
      const pass=Object.values(checks).every(Boolean);
      if(desktop.length>700000 || mobile.length>700000){
        emit('FAIL','SCREENSHOT_TOO_LARGE',{checks});
      }else{
        emit(pass?'PASS_SMOKE_ONLY':'FAIL',
          pass?'BROWSER_SMOKE_ONLY':'BROWSER_ASSERTION_FAILED',
          {checks,desktop_png:desktop.toString('base64'),
            mobile_png:mobile.toString('base64')});
      }
    }
  }
}catch{
  emit('FAIL','BROWSER_RUNTIME_FAILED');
}finally{
  if(browser)await browser.close().catch(()=>{});
  if(server){server.kill('SIGTERM');}
}
