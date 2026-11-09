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
  browser = await chromium.launch({channel:'msedge',headless:true});
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
  // Real rendering with explicit API fixtures; this is not a real login test.
  const states=['NEEDS_REVISION','NEEDS_VALIDATION','READY_FOR_REVIEW','ACCEPTED'];
  const acceptancePage=await browser.newPage({viewport:{width:1440,height:1000}});
  acceptancePage.on('pageerror',error=>errors.push(error.message));
  await acceptancePage.route('**/api/**',route=>{
    const path=new URL(route.request().url()).pathname;
    const body=path==='/api/session'?{csrf:'fixture-only-csrf'}:{
      goals:states.map((status,index)=>({goal_id:String(index+1).repeat(32),
        title:'Acceptance fixture '+status,template:'webapp.company',status:'SUCCEEDED',
        artifact_acceptance:{status}})),tasks:[],stats:{},
      external_actions_enabled:false,
    };
    return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)});
  });
  await acceptancePage.goto(origin+'/dashboard/#/workspace',{waitUntil:'networkidle'});
  for(const label of ['Sản phẩm cần chỉnh sửa','Sản phẩm cần kiểm tra',
    'Đủ điều kiện Owner nghiệm thu','Owner đã chấp nhận']){
    await acceptancePage.getByText(label,{exact:true}).waitFor();
  }
  const completed=acceptancePage.locator('.status-pill').filter({hasText:'Đã thực thi xong'});
  if(await completed.count()!==4)throw new Error('Execution status labels missing');
  if(await completed.evaluateAll(nodes=>nodes.some(node=>node.classList.contains('tone-good')))){
    throw new Error('Execution success incorrectly styled as product acceptance');
  }
  const acceptedTile=acceptancePage.locator('.stat-tile').filter({hasText:'Đã nghiệm thu'});
  if((await acceptedTile.locator('.stat-value').innerText())!=='1'){
    throw new Error('Workflow success counted as accepted product');
  }
  if(errors.length)throw new Error('React runtime errors: '+errors.join(' | '));
  await acceptancePage.screenshot({path:'../docs/verification/phase1/acceptance-workspace.png',fullPage:true});
  console.log('React acceptance states: PASS (API fixtures; execution separate from Owner acceptance)');
} finally {
  if (browser) await browser.close();
  vite.kill();
}
