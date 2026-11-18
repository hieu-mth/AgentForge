// Real browser smoke: production Vite chunks must mount React, not leave a white page.
import { spawn } from 'node:child_process';
import { chromium } from 'playwright-core';
import { setTimeout as sleep } from 'node:timers/promises';

const port = 5197;
const origin = 'http://127.0.0.1:' + port;
const vite = spawn(process.execPath, ['node_modules/vite/bin/vite.js', 'preview',
  '--host', '127.0.0.1', '--port', String(port), '--strictPort'], {
  cwd: process.cwd(), stdio: 'pipe', windowsHide: true,
});
let browser;
try {
  let ready = false;
  for (let i=0;i<40;i++) {
    if (vite.exitCode !== null) throw new Error('Vite preview exited early');
    try {const r=await fetch(origin+'/dashboard/');if(r.ok){ready=true;break;}}
    catch { /* booting */ }
    await sleep(300);
  }
  if (!ready) throw new Error('Vite production preview not ready');
  browser = await chromium.launch({
    ...(process.env.AGENTFORGE_BROWSER_EXECUTABLE
      ? {executablePath:process.env.AGENTFORGE_BROWSER_EXECUTABLE}
      : {channel:'msedge'}),
    headless:true,
  });
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const responses = [];
  page.on('response',response=>{
    if(response.url().includes('/dashboard/assets/')) responses.push({
      status:response.status(),url:response.url(),
    });
  });
  await page.goto(origin+'/dashboard/',{waitUntil:'networkidle',timeout:30000});
  // Backend is intentionally absent: React must still mount its loading/error shell.
  await page.waitForFunction(()=>{
    const root=document.querySelector('#root');
    return !!root && (root.querySelector('.loading-screen') ||
      root.querySelector('.login-screen') || root.querySelector('.app-shell'));
  },{timeout:12000});
  if(errors.length) throw new Error('React runtime errors: '+errors.join(' | '));
  if(responses.some(r=>r.status!==200)) throw new Error(
    'Missing JS/CSS bundle: '+JSON.stringify(responses.filter(r=>r.status!==200)));
  if(!responses.some(r=>r.url.endsWith('.js'))) throw new Error('No JS bundle requested');
  console.log('React production boot: PASS; '+responses.length+' assets fetched');
  // Video-first routing: retired Workspace deep links must not reopen legacy screens.
  const acceptancePage=await browser.newPage({viewport:{width:1440,height:1000}});
  acceptancePage.on('pageerror',error=>errors.push(error.message));
  await acceptancePage.route('**/api/**',route=>{
    const path=new URL(route.request().url()).pathname;
    const body=path==='/api/session'?{csrf:'fixture-only-csrf'}
      :path==='/api/model-hub'?{
        revision:0,cloud_fallback:false,gpu_auto_start:false,
        profiles:[{id:'local_primary',provider:'ollama',model:'qwen3:8b',enabled:true,
          source:'git',health:'UNVERIFIED'}],
        routes:[{id:'film.motion',label:'Tạo video chuyển động',kind:'video',model_ref:null,
          source:'default',runtime_wired:false,status:'UNCONFIGURED'},
          {id:'ops.monitor',label:'Theo dõi hệ thống',kind:'rules',model_ref:null,
          source:'default',runtime_wired:false,status:'DETERMINISTIC'}],
      }:{goals:[],tasks:[],stats:{},external_actions_enabled:false};
    return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)});
  });
  await acceptancePage.goto(origin+'/dashboard/#/workspace',{waitUntil:'networkidle'});
  await acceptancePage.locator('.app-shell').waitFor();
  if(!acceptancePage.url().includes('#/workspace'))
    throw new Error('Unexpected hash mutation during legacy route fallback');
  await acceptancePage.getByText('Tổng quan',{exact:true}).first().waitFor();
  console.log('Video-first legacy deep link fallback: PASS');
  // Read-only Model Hub browser contract, with explicit mock data. Do not test
  // paid inference or pretend that a model is installed/online.
  await acceptancePage.goto(origin+'/dashboard/#/models',{waitUntil:'networkidle'});
  await acceptancePage.getByText('Model Registry',{exact:true}).waitFor();
  await acceptancePage.getByText('Task Routing',{exact:true}).waitFor();
  await acceptancePage.getByText('Python rules · không cần AI',{exact:true}).first().waitFor();
  if(errors.length)throw new Error('Model Hub runtime errors: '+errors.join(' | '));
  console.log('Model Hub settings render: PASS (fixture, no provider calls)');
} finally {
  if (browser) await browser.close();
  vite.kill();
}
