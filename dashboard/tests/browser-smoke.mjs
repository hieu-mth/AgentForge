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
  const page2=await browser.newPage();
  const errors2=[];
  page2.on('pageerror',error=>errors2.push(error.message));
  let environmentRequests=0;
  const environmentSnapshot={
    checked_at:'2026-11-19T00:05:00+07:00',
    config_error:null,endpoints_truncated:false,
    hardware:{
      os:'Windows',os_release:'11',cpu:'Intel Core i5',logical_cpu_count:12,
      architecture:'AMD64',
      memory:{available_bytes:18*1024**3,total_bytes:32*1024**3},
      disk:{free_bytes:600*1024**3,total_bytes:1000*1024**3},
      gpu:{status:'RUNNING',cuda_toolkit:{status:'NOT_INSTALLED'},devices:[
        {name:'NVIDIA GeForce RTX 5070',driver_version:'621.01',
          vram_free_mib:8673,vram_total_mib:12227}
      ]},
    },
    software:[
      {id:'python',status:'READY',version:'3.13.17',scope:'active virtualenv'},
      {id:'ollama',status:'INSTALLED',scope:'CLI in PATH'},
    ],
    services:[
      {id:'ollama',status:'RUNNING',endpoint:'http://127.0.0.1:11434'},
      {id:'comfyui',status:'DEGRADED',endpoint:'http://127.0.0.1:8188',error:'TIMEOUT'},
    ],
    models:[
      {id:'ollama:local:qwen3',name:'qwen3:8b',provider:'ollama',type:'ollama_model',
       size_bytes:5905580032,status:'INSTALLED',loadability:'UNKNOWN',
       endpoint:'http://127.0.0.1:11434',family:'qwen3'},
    ],
    configured_models:[
      {id:'local_primary',name:'qwen3:8b',provider:'ollama',status:'INSTALLED'},
    ],
  };
  await page2.route('**/api/**',route=>{
    const p=new URL(route.request().url()).pathname;
    if(p==='/api/ops/discovery')environmentRequests++;
    const payload=p==='/api/session'?{csrf:'fixture-only-csrf'}:
      p==='/api/video-studio/projects'?{projects:[],canonical_engine:'film_studio'}:
      p==='/api/characters'?{characters:[]}:
      p==='/api/ops/discovery'?environmentSnapshot:{};
    return route.fulfill({status:200,contentType:'application/json',
      body:JSON.stringify(payload)});
  });
  await page2.goto(origin+'/dashboard/#/projects',{waitUntil:'networkidle'});
  await page2.getByText('Dự án & tập phim',{exact:true}).waitFor();
  await page2.goto(origin+'/dashboard/#/media-studio',{waitUntil:'networkidle'});
  await page2.getByRole('button',{name:'Xem dự án video'}).click();
  await page2.waitForURL('**/#/projects');
  await page2.getByText('Dự án & tập phim',{exact:true}).waitFor();
  await page2.goto(origin+'/dashboard/#/media-studio',{waitUntil:'networkidle'});
  await page2.getByRole('button',{name:'Xem bản dựng'}).click();
  await page2.waitForURL('**/#/models');
  // Environment runs against the actual discovery contract, with no invented READY state.
  await page2.goto(origin+'/dashboard/#/environment',{waitUntil:'networkidle'});
  const env=page2.locator('[data-testid="environment-page"]');
  await env.getByRole('heading',{name:'Môi trường & Tài nguyên'}).waitFor();
  await env.locator('.env-stat-grid .env-stat').first().waitFor();
  if(await env.locator('.env-stat').count()!==4)throw new Error('Missing four resource tiles');
  await env.getByText('NVIDIA GeForce RTX 5070').first().waitFor();
  await env.getByText('9,09 GB').first().waitFor();
  await env.getByText('12,82 GB').first().waitFor();
  if(/\b(?:MiB|GiB)\b/.test(await env.innerText()))
    throw new Error('Technical capacity units leaked into the Environment UI');
  await env.getByText('Gián đoạn',{exact:true}).waitFor();
  await env.getByText('TIMEOUT',{exact:true}).waitFor();
  await env.getByText('qwen3:8b').first().waitFor();
  if(environmentRequests<1)throw new Error('Environment did not request actual discovery API');
  const refreshResponse=page2.waitForResponse(r=>
    r.url().includes('/api/ops/discovery')&&r.status()===200);
  await env.getByRole('button',{name:'Quét lại'}).click();
  await refreshResponse;
  if(environmentRequests<2)throw new Error('Quét lại did not refresh environment data');
  // Responsive acceptance: one document scrollbar, tables may scroll horizontally.
  for(const width of [1440,900,390]){
    await page2.setViewportSize({width,height:850});
    await page2.waitForTimeout(150);
    const overflow=await page2.evaluate(()=>
      document.documentElement.scrollWidth>window.innerWidth+2);
    if(overflow)throw new Error('Environment page overflows viewport at '+width+'px');
  }
  await page2.getByRole('button',{name:'Mở điều hướng'}).click();
  await page2.getByText('LOCAL-FIRST AI STUDIO').last().waitFor();
  await page2.keyboard.press('Escape');
  await page2.getByRole('button',{name:'Sáng'}).click();
  await page2.waitForFunction(()=>document.documentElement.dataset.theme==='light');
  await page2.getByRole('button',{name:'Tối'}).click();
  await page2.waitForFunction(()=>document.documentElement.dataset.theme==='dark');
  await page2.setViewportSize({width:1440,height:900});
  console.log('Environment layout, live discovery data and refresh: PASS');
  await page2.goto(origin+'/dashboard/#/workspace',{waitUntil:'networkidle'});
  await page2.getByText('Tổng quan Video Studio',{exact:true}).waitFor();
  if(errors2.length)throw new Error('Video Studio runtime errors: '+errors2.join(' | '));
  console.log('Video-only project and retired route smoke: PASS');
} finally {
  if (browser) await browser.close();
  vite.kill();
}
