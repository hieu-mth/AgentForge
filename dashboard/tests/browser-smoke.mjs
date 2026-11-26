// Real browser smoke: production Vite chunks must mount React, not leave a white page.
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { mkdtemp, rm, rmdir } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createInterface } from 'node:readline';
import { chromium } from 'playwright-core';
import { setTimeout as sleep } from 'node:timers/promises';

const port = 5197;
const origin = 'http://127.0.0.1:' + port;
const vite = spawn(process.execPath, ['node_modules/vite/bin/vite.js', 'preview',
  '--host', '127.0.0.1', '--port', String(port), '--strictPort'], {
  cwd: process.cwd(), stdio: 'pipe', windowsHide: true,
});
let browser, policyServer, policyTemp;
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
      disk:{free_bytes:696_990_000_000,total_bytes:1_000_190_000_000},
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
  let projectRows=[];
  let overviewDrafts=[];
  let clipRequests=0;
  let episodeRequests=0;
  const studioEpisodes=[
    {film_slug:'demo',episode_id:'ep01',episode_sha256:'example-episode',
      state:'PREPARED_NOT_RENDERED',shot_count:1,runtime_seconds:4},
    {film_slug:'demo',episode_id:'ep02',episode_sha256:'example-draft',
      state:'RENDER_RECEIPT_PRESENT_UNINSPECTED',shot_count:1,runtime_seconds:4},
    {film_slug:'invalid-demo',episode_id:'ep03',state:'INVALID_NEEDS_OWNER_REVIEW'},
    {film_slug:'prepared-demo',episode_id:'ep04',state:'PREPARED_NOT_RENDERED',
      episode_sha256:'example-prepared',shot_count:2,runtime_seconds:8},
  ];
  let studioReadError=false;
  let service={state:'RUNNING',managed:false,configured:true,can_manage:true,
    endpoint:'http://127.0.0.1:8192',devices:[]};
  const serviceActions=[];
  await page2.route('**/api/**',async route=>{
    const p=new URL(route.request().url()).pathname;
    if(p==='/api/ops/discovery')environmentRequests++;
    if(p==='/api/ops/comfyui/control'){
      const request=route.request().postDataJSON();
      serviceActions.push(request.action);
      service={...service,state:'RUNNING',managed:true,pid:4210};
      return route.fulfill({json:service});
    }
    if(p==='/api/ops/comfyui')return route.fulfill({json:service});
    if(p==='/api/film/motion')clipRequests++;
    if(p==='/api/film/productions')episodeRequests++;
    if(p==='/api/film/productions'&&studioReadError){
      await sleep(300);
      return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'fixture_error'})});
    }
    if(p==='/api/film/productions/demo/ep02/preview')return route.fulfill({
      status:404,contentType:'application/json',body:JSON.stringify({error:'film_preview_unavailable'}),
    });
    const payload=p==='/api/session'?{csrf:'fixture-only-csrf'}:
      p==='/api/video-studio/projects'?{projects:projectRows,canonical_engine:'film_studio'}:
      p==='/api/film/drafts'?{drafts:overviewDrafts}:
      p==='/api/characters'?{characters:[]}:
      p==='/api/film/motion'?{gpu:{status:'COMFYUI_UNAVAILABLE'},jobs:[{job_id:'demo-job',film_slug:'demo',shot_id:'001',
        status:'COMPLETE_UNVERIFIED',state:'COMPLETE_UNVERIFIED',plan_sha:'example-plan',
        workflow_sha:'example-workflow',mp4_technical_verified:false}]}:
      p==='/api/film/productions'?{episodes:studioEpisodes}:
      p==='/api/film/productions/demo/ep01'?{proposal:{...studioEpisodes[0],shots:[]},render:null}:
      p==='/api/film/productions/demo/ep02'?{proposal:{...studioEpisodes[1],
        shots:[{shot_id:'001',action_camera:'Máy quay tiến gần',caption:'Bắt đầu hành trình'}]},
        render:{video_sha256:'fixture-render-sha'}}:
      p==='/api/model-hub'?{revision:2,
        profiles:[{id:'local-text',provider:'ollama',model:'qwen3:8b',enabled:true,source:'git'}],
        routes:[{id:'draft',label:'Soạn nháp',kind:'text',status:'CONFIG_ONLY',model_ref:'local-text'}],
      }:
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
  if(clipRequests||!episodeRequests)throw new Error('Studio did not separate production reads from motion tools');
  await page2.setViewportSize({width:390,height:850});
  const studio=page2.locator('.studio-page');
  await studio.getByText('Tập phim trong workspace',{exact:true}).waitFor();
  if(await studio.locator('.studio-episode').count()!==3||!await studio.getByLabel('Nội dung video').isEnabled())
    throw new Error('Studio duplicated projects or disabled the idea input');
  for(const width of [1440,1280,900,390]){
    await page2.setViewportSize({width,height:850});
    await page2.waitForFunction(()=>document.documentElement.scrollWidth<=window.innerWidth+2);
  }
  await page2.getByRole('button',{name:'Sáng'}).click();
  await page2.waitForFunction(()=>document.documentElement.dataset.theme==='light');
  await page2.getByRole('button',{name:'Tối'}).click();
  await page2.waitForFunction(()=>document.documentElement.dataset.theme==='dark');
  await studio.locator('.studio-filters').getByText('Chờ xem bản dựng',{exact:true}).click();
  if(await studio.locator('.studio-episode').count()!==1)throw new Error('Studio review filter is incorrect');
  await studio.getByRole('button',{name:'Xem dự án demo',exact:true}).click();
  const episodeDrawer=page2.locator('.studio-episode-drawer');
  await episodeDrawer.getByText('Phụ đề: Bắt đầu hành trình',{exact:true}).waitFor();
  const download=episodeDrawer.getByRole('link',{name:'Tải MP4'});
  if(await download.getAttribute('href')!=='/api/film/productions/demo/ep02/preview')
    throw new Error('Studio download did not use authenticated media route');
  await episodeDrawer.getByRole('button',{name:'Xem bản dựng',exact:true}).click();
  await episodeDrawer.getByText('Không phát được MP4',{exact:true}).waitFor();
  await episodeDrawer.getByText('Vị trí lưu trên máy',{exact:true}).click();
  await episodeDrawer.getByText('workspace/films/demo/productions/ep02/episode.mp4',{exact:true}).waitFor();
  await episodeDrawer.getByText('Thông tin kỹ thuật và mã SHA',{exact:true}).click();
  await episodeDrawer.getByText('SHA bản dựng: fixture-render-sha',{exact:true}).waitFor();
  await page2.keyboard.press('Escape');
  await episodeDrawer.waitFor({state:'hidden'});
  studioReadError=true;
  await studio.locator('.studio-projects').getByRole('button',{name:'Làm mới',exact:false}).click();
  await studio.getByText('Đang đọc danh sách tập phim…',{exact:true}).waitFor();
  await studio.getByText('Không đọc được danh sách tập phim',{exact:true}).waitFor();
  studioReadError=false;
  await studio.getByRole('button',{name:'Thử lại danh sách tập phim'}).click();
  await studio.getByText('Không đọc được danh sách tập phim',{exact:true}).waitFor({state:'hidden'});
  const loadedEpisodeRequests=episodeRequests;
  await page2.getByRole('button',{name:'Mở clip chuyển động'}).click();
  await page2.getByText('Chờ xác minh MP4',{exact:true}).waitFor();
  await studio.getByText('Thông tin GPU của lần kiểm tra',{exact:true}).click();
  await studio.getByText('Tình trạng: COMFYUI_UNAVAILABLE',{exact:true}).waitFor();
  await page2.getByRole('button',{name:'Đối chiếu ComfyUI'}).waitFor();
  if(!clipRequests||episodeRequests!==loadedEpisodeRequests)throw new Error('Opening clips loaded the wrong tool');
  await studio.locator('.studio-filters').getByText('Tất cả',{exact:true}).click();
  await studio.getByRole('button',{name:'Xem dự án demo',exact:true}).click();
  await episodeDrawer.getByRole('combobox',{name:'Chọn tập phim'}).click();
  const episodeOption=page2.locator('.ant-select-dropdown:visible .ant-select-item-option')
    .filter({hasText:/^ep01 · Chờ dựng$/});
  await episodeOption.evaluate(option=>option.click());
  await episodeDrawer.getByRole('button',{name:'Mở công cụ dựng'}).click();
  await episodeDrawer.waitFor({state:'hidden'});
  await page2.getByText('Tập phim & bản dựng',{exact:true}).waitFor();
  await page2.locator('tr[data-row-key="demo:ep01"]')
    .getByRole('button',{name:'Dựng MP4',exact:true}).click();
  const renderDialog=page2.getByRole('dialog',{name:'Kiểm tra và dựng MP4 local bằng FFmpeg?'});
  await renderDialog.getByRole('button',{name:'Hủy',exact:true}).click();
  await renderDialog.waitFor({state:'hidden'});
  if(episodeRequests!==loadedEpisodeRequests||await page2.getByText('Danh sách clip chuyển động',{exact:true}).count())
    throw new Error('Episode workspace did not replace the clips workspace');
  const studioOverflow=await page2.locator('.studio-table .ant-table-content').evaluate(
    table=>table.scrollWidth>table.clientWidth+2);
  if(studioOverflow)throw new Error('Studio table overflows on mobile');
  await page2.setViewportSize({width:1440,height:900});
  await page2.getByRole('button',{name:'Cấu hình Model AI'}).click();
  await page2.waitForURL('**/#/models');
  const hub=page2.locator('.model-hub');
  await hub.getByText('Đã bật',{exact:true}).waitFor();
  await hub.getByRole('button',{name:'Khôi phục phiên bản trước'}).click();
  const restoreDialog=page2.getByRole('dialog',{name:'Khôi phục cấu hình về phiên bản 1?'});
  await restoreDialog.getByRole('button',{name:'Hủy'}).click();
  await page2.setViewportSize({width:390,height:850});
  const modelDetails=hub.locator('.hub-table').first().getByText('Chi tiết',{exact:true});
  await modelDetails.click();
  await hub.getByText('qwen3:8b',{exact:true}).waitFor();
  const hubOverflow=await hub.locator('.ant-table-content').evaluateAll(
    tables=>tables.some(table=>table.scrollWidth>table.clientWidth+2));
  if(hubOverflow)throw new Error('Model tables overflow on mobile');
  await page2.setViewportSize({width:1440,height:900});
  // Environment runs against the actual discovery contract, with no invented READY state.
  await page2.goto(origin+'/dashboard/#/environment',{waitUntil:'networkidle'});
  const env=page2.locator('[data-testid="environment-page"]');
  await env.getByRole('heading',{name:'Môi trường & Tài nguyên'}).waitFor();
  await env.locator('.env-stat-grid .env-stat').first().waitFor();
  const comfyCard=env.locator('.ant-card').filter({hasText:'Dịch vụ ComfyUI'});
  const stop=comfyCard.getByRole('button',{name:'Dừng',exact:true});
  const start=comfyCard.getByRole('button',{name:'Khởi động',exact:true});
  const check=comfyCard.getByRole('button',{name:'Kiểm tra ComfyUI',exact:true});
  await comfyCard.getByText('Chạy bên ngoài',{exact:false}).waitFor();
  if(!await stop.isDisabled()||!await start.isDisabled())throw new Error('External ComfyUI is controllable');
  service={...service,state:'STOPPED'};
  await check.click();
  await comfyCard.getByText('Đã dừng',{exact:true}).waitFor();
  await start.click();
  await comfyCard.getByText('PID 4210',{exact:false}).waitFor();
  if(serviceActions.join()!=='start'||!await stop.isEnabled())
    throw new Error('Managed ComfyUI controls did not follow the API');
  service={...service,busy:true};
  await check.click();
  await comfyCard.getByText('Đang có tác vụ',{exact:false}).waitFor();
  if(!await stop.isDisabled())throw new Error('Stop was enabled during active production');
  service={...service,state:'STOPPED',managed:false,pid:null,busy:false};
  await comfyCard.getByText('Đã dừng',{exact:true}).waitFor({timeout:15000});
  console.log('ComfyUI controls, external ownership and active job protection: PASS');
  if(await env.locator('.env-stat').count()!==4)throw new Error('Missing four resource tiles');
  await env.getByText('NVIDIA GeForce RTX 5070').first().waitFor();
  await env.getByText('8,47 GB').first().waitFor();
  await env.getByText('11,94 GB').first().waitFor();
  await env.getByText('32 GB',{exact:false}).first().waitFor();
  await env.getByText('931,5 GB',{exact:false}).waitFor();
  await env.getByRole('button',{name:'Quy ước đơn vị dung lượng'}).focus();
  await page2.locator('.af-tooltip').getByRole('tooltip')
    .getByText('Ổ đĩa, RAM và VRAM dùng hệ 1.024',{exact:false}).waitFor();
  if(/\b(?:MiB|GiB)\b/.test(await env.innerText()))
    throw new Error('Technical capacity units leaked into the Environment UI');
  await env.getByText('Gián đoạn',{exact:true}).waitFor();
  const timeoutDiagnostic=env.getByText('Dịch vụ phản hồi quá chậm',{exact:true}).filter({visible:true});
  await timeoutDiagnostic.click();
  await env.getByText('TIMEOUT',{exact:true}).filter({visible:true}).waitFor();
  const serviceRows=env.locator('.env-table').nth(1).locator('tbody tr[data-row-key]');
  if(!(await serviceRows.first().innerText()).includes('comfyui'))
    throw new Error('Degraded service is not listed first');
  await env.getByText('qwen3:8b').first().waitFor();
  await env.getByText('Chưa xác minh khả năng chạy',{exact:true}).waitFor();
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
  await serviceRows.first().getByText('Chi tiết',{exact:true}).click();
  await serviceRows.first().getByText('Dịch vụ phản hồi quá chậm',{exact:true}).click();
  await serviceRows.first().getByText('TIMEOUT',{exact:true}).waitFor();
  const tableOverflow=await env.locator('.ant-table-content').evaluateAll(
    tables=>tables.some(table=>table.scrollWidth>table.clientWidth+2));
  if(tableOverflow)throw new Error('Environment tables overflow on mobile');
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
  const overview=page2.locator('.overview-page');
  await overview.getByText('Chưa có video đã dựng hoặc tập phim trong workspace',{exact:true}).waitFor();
  await overview.getByRole('button',{name:'Mở Video Studio'}).click();
  await page2.waitForURL('**/#/media-studio');
  overviewDrafts=[{id:'d'.repeat(32),board:{title:'Video đã duyệt'},status:'APPROVED',video_sha:'fixture'}];
  await page2.goto(origin+'/dashboard/#/overview',{waitUntil:'networkidle'});
  await overview.getByText('Video đã duyệt',{exact:true}).waitFor();
  await overview.getByRole('button',{name:'Xem MP4',exact:true}).waitFor();
  if(await overview.getByText('Chưa có video đã dựng hoặc tập phim trong workspace').count())
    throw new Error('Overview displayed an empty state despite a rendered draft');
  projectRows=[
    {project_id:'film:demo:ep01',film_slug:'demo',episode_id:'ep01',state:'PREPARED_NOT_RENDERED'},
    {project_id:'film:demo:ep02',film_slug:'demo',episode_id:'ep02',state:'RENDER_RECEIPT_PRESENT_UNINSPECTED'},
    {project_id:'film:demo:ep03',film_slug:'demo',episode_id:'ep03',state:'INVALID_NEEDS_OWNER_REVIEW'},
  ];
  await page2.setViewportSize({width:390,height:850});
  await page2.reload({waitUntil:'networkidle'});
  await overview.getByText('Cần Owner xem bản dựng',{exact:true}).waitFor();
  await overview.getByText('Cần kiểm tra hồ sơ tập',{exact:true}).waitFor();
  const overviewStats=overview.locator('.overview-stats');
  if((await overviewStats.nth(0).locator('.env-stat-value').allTextContents()).join(',')!=='1,1,1')
    throw new Error('Overview counters do not match project states');
  if((await overviewStats.nth(1).locator('.env-stat-value').allTextContents()).join(',')!=='1/1,—,—,—')
    throw new Error('Overview must distinguish missing usage counters from measured zero');
  await overview.getByText('Có số liệu lượt cloud: 0/1;', {exact:false}).waitFor();
  const overviewOverflow=await overview.locator('.ant-table-content').evaluateAll(
    tables=>tables.some(table=>table.scrollWidth>table.clientWidth+2));
  if(overviewOverflow)throw new Error('Overview table overflows on mobile');
  await overview.getByRole('button',{name:'Xem dự án',exact:true}).click();
  await page2.waitForURL('**/#/projects');
  if(errors2.length)throw new Error('Video Studio runtime errors: '+errors2.join(' | '));
  console.log('Overview data, mobile layout and Studio navigation: PASS');

  // Serve the built dashboard and real authenticated API against isolated SQLite.
  policyTemp=await mkdtemp(join(tmpdir(),'agentforge-policy-'));
  const ownerCode='fixture-orchestrator-owner';
  const policyDb=join(policyTemp,'hub.sqlite3');
  policyServer=spawn('python',['-u','-c',[
    'import sys', 'from pathlib import Path', 'from functools import partial',
    'from agentforge.ai import model_hub', 'from agentforge.api.server import create_server',
    'from agentforge.features.film_studio import production, draft_pipeline',
    'model_hub.DB_PATH = Path(sys.argv[1])',
    'draft_pipeline.DB = Path(sys.argv[1]).parent / "drafts.sqlite3"',
    'production.list_episodes = partial(production.list_episodes, film_root=Path(sys.argv[1]).parent / "films")',
    'server = create_server(0, owner_code=sys.argv[2])',
    'print(server.server_port, flush=True)', 'server.serve_forever()',
  ].join('\n'),policyDb,ownerCode],{cwd:'..',stdio:['ignore','pipe','inherit'],windowsHide:true});
  const output=createInterface({input:policyServer.stdout});
  const [policyPort]=await once(output,'line',{signal:AbortSignal.timeout(10000)});
  const policyOrigin='http://127.0.0.1:'+policyPort;
  const settings=await browser.newPage({viewport:{width:390,height:850}});
  const settingsErrors=[];
  settings.on('pageerror',error=>settingsErrors.push(error.message));
  const postOptions={headers:{Origin:policyOrigin},
    data:{ack:'RESET_ORCHESTRATOR',expected_revision:0}};
  const endpoint=policyOrigin+'/api/model-hub/orchestrator';
  if((await settings.request.post(endpoint,postOptions)).status()!==401)
    throw new Error('Orchestrator mutation is accessible without an Owner session');
  await settings.goto(policyOrigin+'/dashboard/#/orchestrator');
  await settings.getByLabel('Mã Owner',{exact:true}).fill(ownerCode);
  await settings.getByRole('button',{name:'Mở dashboard'}).click();
  await settings.route('**/api/film/drafts/resources',route=>route.fulfill({json:{
    ram_total:32*1024**3,ram_available:8*1024**3,
    vram_total_mib:12*1024,vram_free_mib:3*1024,
  }}));
  await settings.goto(policyOrigin+'/dashboard/#/media-studio',{waitUntil:'networkidle'});
  await settings.getByText('Tài nguyên',{exact:true}).click();
  await settings.getByText('RAM dùng / khả dụng: 24 GB / 8 GB',{exact:true}).waitFor();
  await settings.getByText('VRAM dùng / khả dụng: 9 GB / 3 GB',{exact:true}).waitFor();
  if(await settings.locator('.studio-projects').count())
    throw new Error('Studio displays an empty episode panel');
  await settings.getByText('Tạo video mới',{exact:true}).waitFor();
  await settings.getByText('Chưa có bản nháp',{exact:true}).waitFor();
  let draftFixture=null;
  let cancelledDraft=null;
  let archivedDrafts=[];
  let draftListStatus=404;
  let draftReads=0;
  let holdDraftRead;
  await settings.route('**/api/film/drafts',async route=>{
    draftReads++;
    if(holdDraftRead)await holdDraftRead;
    if(draftListStatus===404)return route.fulfill({status:404,json:{error:'not_found'}});
    if(draftListStatus===503)return route.fulfill({status:503,json:{
      error:'draft_storage_unavailable',message:'Fixture SQLite unavailable',
    }});
    return route.fulfill({json:{drafts:[draftFixture,cancelledDraft,...archivedDrafts].filter(Boolean)}});
  });
  await settings.reload();
  await settings.getByText(/Backend đang chạy chưa hỗ trợ bản nháp/).waitFor();
  if(await settings.getByText('Chưa có bản nháp',{exact:true}).count())
    throw new Error('Missing draft API was silently displayed as empty');
  draftListStatus=503;
  await settings.getByRole('button',{name:'Thử lại bản nháp',exact:true}).click();
  await settings.getByText('Fixture SQLite unavailable',{exact:true}).waitFor();
  draftListStatus=200;
  const formattedBrief='**Tên phim: Chú mèo cam khám phá khu rừng** Phong cách: Hoạt hình. **Nhân vật:** Miu. **Kịch bản:** Miu thức dậy.\nMiu đi tìm bạn.';
  await settings.route('**/api/film/drafts/start',route=>{
    const {id,...brief}=route.request().postDataJSON();
    if(!/^[0-9a-f]{32}$/.test(id)||![formattedBrief,'Ý tưởng mới'].includes(brief.idea)||
        brief.seconds!==null||brief.scene_count!==null||brief.duration_mode!=='auto'||brief.ratio!=='16:9'||
        brief.mode!=='motion'||'motion_approved' in brief)
      throw new Error('Unexpected draft submission');
    draftFixture={id,brief:{...brief,seconds:6,scene_count:3},status:'RUNNING',stage:'PLANNING',worker_active:true,
      activity:{operation:'plan',provider:'ollama',model:'fixture-planner'}};
    return route.fulfill({json:draftFixture});
  });
  await settings.getByLabel('Nội dung video',{exact:true}).fill(formattedBrief);
  await settings.getByRole('button',{name:'Tạo storyboard',exact:true}).click();
  const draftProgress=settings.getByRole('region',{name:'Tiến độ tạo bản nháp'});
  await draftProgress.getByText('Đang lập kế hoạch',{exact:true}).waitFor();
  await settings.getByRole('button',{name:'Hủy tác vụ',exact:true}).waitFor();
  if(await settings.getByRole('button',{name:/^(Tác vụ đang chạy|Xóa bản nháp)$/}).count())
    throw new Error('Running draft shows a pause or delete control');
  await draftProgress.getByRole('heading',{name:'Chú mèo cam khám phá khu rừng',exact:true}).waitFor();
  await settings.getByRole('button',{name:'Xem nội dung video',exact:true}).click();
  const scriptReader=settings.getByRole('dialog',{name:'Nội dung video',exact:true});
  await scriptReader.getByRole('heading',{name:'Nhân vật:',exact:true}).waitFor();
  const scriptParagraph=scriptReader.locator('section p').filter({hasText:'Miu thức dậy.'});
  if(await scriptParagraph.textContent()!=='Miu thức dậy.\nMiu đi tìm bạn.')
    throw new Error('Script lost the original line break');
  await scriptReader.locator('.ant-modal-footer').getByRole('button',{name:'Đóng',exact:true}).click();
  await scriptReader.waitFor({state:'hidden'});
  const briefEditor=settings.getByLabel('Nội dung video',{exact:true});
  if(await briefEditor.inputValue()!=='')throw new Error('Submitted storyboard left text in the composer');
  await draftProgress.getByText('Ollama · fixture-planner',{exact:true}).waitFor();
  let releaseDraftRead;
  holdDraftRead=new Promise(resolve=>{releaseDraftRead=resolve;});
  try {
    await settings.waitForRequest(request=>new URL(request.url()).pathname==='/api/film/drafts');
    if(await settings.getByText('Đang đọc bản nháp…',{exact:true}).count())
      throw new Error('Draft progress refresh displayed the initial loading indicator');
    await draftProgress.getByText('Ollama · fixture-planner',{exact:true}).waitFor();
  } finally {
    releaseDraftRead();
    holdDraftRead=null;
  }
  await settings.reload();
  await briefEditor.waitFor();
  if(await briefEditor.inputValue()!=='')throw new Error('Submitted storyboard text was restored after refresh');
  await settings.getByRole('tab',{name:/^Chú mèo cam khám phá khu rừng/}).waitFor();
  const draftActionPosition=name=>settings.getByRole('button',{name,exact:true}).evaluate(button=>{
    const item=button.closest('.ant-collapse-item').getBoundingClientRect();
    const rect=button.getBoundingClientRect();
    return [item.right-rect.right,rect.top-item.top,rect.width,rect.height];
  });
  const cancelPosition=await draftActionPosition('Hủy tác vụ');
  draftFixture={...draftFixture,status:'FAILED',worker_active:false,error:'Fixture runtime unavailable',
    duration_plan:{recommended_shot_count:9},storyboard_checkpoint:{shots:Array.from({length:7},()=>({}))}};
  await settings.getByText('Fixture runtime unavailable',{exact:true}).waitFor();
  await draftProgress.getByText('7/9 shot storyboard đã lưu',{exact:true}).waitFor();
  if(await draftProgress.getByRole('progressbar').count())
    throw new Error('Partial storyboard showed a synthetic production percentage');
  const deletePosition=await draftActionPosition('Xóa bản nháp');
  if(cancelPosition.some((value,index)=>Math.abs(value-deletePosition[index])>1))
    throw new Error(`Draft controls do not align: cancel ${cancelPosition}; delete ${deletePosition}`);
  await settings.route('**/api/film/drafts/*/resume',route=>{
    draftFixture=null;
    draftListStatus=503;
    return route.fulfill({status:404,json:{error:'draft_not_found'}});
  });
  const failedDraftRow=settings.getByRole('tab',{name:/^Chú mèo cam khám phá khu rừng/});
  await failedDraftRow.click();
  await draftProgress.waitFor({state:'hidden'});
  const resumeButton=failedDraftRow.getByRole('button',{name:'Tiếp tục từ checkpoint'});
  await resumeButton.hover();
  await settings.locator('.af-tooltip').getByRole('tooltip').getByText('Tiếp tục từ checkpoint',{exact:true}).waitFor();
  await resumeButton.click();
  await settings.getByText(/Bản nháp này không còn tồn tại/).waitFor();
  await settings.getByText('Fixture SQLite unavailable',{exact:true}).waitFor();
  await settings.getByRole('tab',{name:/^Chú mèo cam khám phá khu rừng/}).waitFor({state:'hidden'});
  const failedReads=draftReads;
  await sleep(2800);
  if(draftReads!==failedReads)throw new Error('Draft list retried automatically after an API failure');
  draftListStatus=200;
  await settings.getByLabel('Nội dung video',{exact:true}).fill('Ý tưởng mới');
  await settings.getByRole('button',{name:'Tạo storyboard',exact:true}).click();
  await settings.getByRole('tab',{name:/^Ý tưởng mới/}).waitFor();
  const scene={seconds:2,description:'Miu quay đầu',character_ids:[],audio:'',asset:'fixture-image'};
  draftFixture={...draftFixture,status:'STORYBOARD_REVIEW',stage:'STORYBOARD',worker_active:false,
    storyboard_version:1,storyboard_sha:'a'.repeat(64),
    editor_constraints:{layout_editable:true,duration_editable:true,min_scenes:3,max_scenes:6,duration:{min:4,max:60}},
    brief:{...draftFixture.brief,idea:'Miu tìm đường về nhà.\n'.repeat(450)},
    duration_plan:{estimated_duration_seconds:6,recommended_shot_count:3,duration_reasoning:'Ba hành động chính.'},
    board:{title:'Ý tưởng mới',scenes:[scene,scene,scene]}};
  await settings.route('**/api/film/drafts/*/storyboard-approve',route=>{
    const {sha256}=route.request().postDataJSON();
    if(sha256!==draftFixture.storyboard_sha)throw new Error('Approval did not use exact storyboard SHA');
    draftFixture={...draftFixture,status:'RUNNING',stage:'MOTION',worker_active:true,
      board:{title:'Ý tưởng mới',scenes:[{...scene,motion_sha:'fixture-clip'},scene,scene]},
      activity:{operation:'motion',provider:'comfyui',model:'fixture-ltx',scene:2}};
    return route.fulfill({json:draftFixture});
  });
  await settings.locator('.studio-drafts-list').getByRole('button',{name:'Làm mới',exact:false}).click();
  await draftProgress.locator('.production-header').getByText('Storyboard chờ duyệt',{exact:true}).waitFor();
  async function checkDraftIconsAligned(row, labels){
    const bounds=await row.evaluate((element,names)=>names.map(name=>{
      const button=[...element.querySelectorAll('button')].find(item=>item.getAttribute('aria-label')===name);
      if(!button)throw new Error('Missing draft action: '+name);
      const svg=button.querySelector('svg');
      const paths=[...svg.querySelectorAll('path')];
      const glyph=paths[0].getBoundingClientRect();
      const viewport=svg.getBoundingClientRect();
      const intact=paths.every(path=>{
        const rect=path.getBoundingClientRect();
        return rect.width>0&&rect.height>0&&rect.left>=viewport.left-.1&&rect.right<=viewport.right+.1&&
          rect.top>=viewport.top-.1&&rect.bottom<=viewport.bottom+.1&&getComputedStyle(path).fill!=='none';
      });
      const box=button.getBoundingClientRect();
      return {middle:glyph.top+glyph.height/2,height:glyph.height,intact,buttonTop:box.top,
        iconTop:button.querySelector('.ant-btn-icon').getBoundingClientRect().top};
    }),labels);
    if(bounds.some(glyph=>!glyph.intact)||Math.abs(bounds[0].middle-bounds[1].middle)>0.75||
      Math.abs(bounds[0].height-bounds[1].height)>1.1)
      throw new Error(`Draft icons differ in alignment or visible height: ${JSON.stringify(bounds)}`);
  }
  await checkDraftIconsAligned(settings.getByRole('tab',{name:/^Ý tưởng mới/}),['Xem storyboard','Xóa bản nháp']);
  await settings.getByRole('button',{name:'Xem storyboard',exact:true}).click();
  const storyboardDialog=settings.getByRole('dialog',{name:'Ý tưởng mới'});
  await storyboardDialog.getByText('Nội dung & phiên bản',{exact:true}).click({trial:true});
  const storyboardHeight=()=>storyboardDialog.locator('.ant-modal-container').evaluate(panel=>panel.offsetHeight);
  const sceneHeight=await storyboardHeight();
  await storyboardDialog.getByText('Nội dung & phiên bản',{exact:true}).click();
  await storyboardDialog.getByText('Ba hành động chính.',{exact:true}).waitFor();
  const sourceHeight=await storyboardHeight();
  const [sourceContent,sourceViewport]=await storyboardDialog.getByRole('region',{name:'Nội dung video và phiên bản'})
    .evaluate(panel=>[panel.scrollHeight,panel.clientHeight]);
  if(sceneHeight!==sourceHeight||sourceContent<=sourceViewport)
    throw new Error(`Storyboard heights: scenes ${sceneHeight}, source ${sourceHeight}, scroll ${sourceContent}/${sourceViewport}`);
  await storyboardDialog.getByRole('button',{name:'Cập nhật thời lượng',exact:true}).waitFor();
  const durationField=storyboardDialog.getByRole('spinbutton',{name:'Thời lượng storyboard'});
  if(await durationField.getAttribute('aria-valuemax')!=='60')
    throw new Error('Storyboard duration does not expose the 60-second limit');
  await durationField.locator('..').locator('.ant-input-number-actions').waitFor();
  await durationField.hover();
  if(!await durationField.evaluate(input=>{
    const field=input.closest('.dashboard-number-field');
    const suffix=field.querySelector('.ant-input-number-suffix').getBoundingClientRect();
    const actions=field.querySelector('.ant-input-number-actions').getBoundingClientRect();
    return input.getBoundingClientRect().right<=suffix.left&&suffix.right<=actions.left&&actions.width>20;
  }))throw new Error('Storyboard number, unit and controls overlap on hover');
  await storyboardDialog.getByText('Các cảnh',{exact:true}).click();
  await storyboardDialog.getByRole('button',{name:/Cảnh 02/}).click();
  await storyboardDialog.getByRole('heading',{name:'Cảnh 2',exact:true}).waitFor();
  const reviewViewport=settings.viewportSize();
  if(process.env.AGENTFORGE_STORYBOARD_SCREENSHOT){
    await settings.setViewportSize({width:1440,height:1000});
    await storyboardDialog.screenshot({path:process.env.AGENTFORGE_STORYBOARD_SCREENSHOT});
  }
  await settings.setViewportSize({width:390,height:844});
  if(await storyboardDialog.evaluate(node=>{
    const rect=node.getBoundingClientRect();
    return node.scrollWidth>node.clientWidth+1||rect.left<0||rect.right>window.innerWidth+1;
  }))
    throw new Error('Storyboard review overflows mobile');
  if(reviewViewport)await settings.setViewportSize(reviewViewport);
  await storyboardDialog.getByRole('button',{name:'Duyệt và bắt đầu sản xuất',exact:true}).click();
  await storyboardDialog.waitFor({state:'hidden'});
  await draftProgress.getByText('Đang tạo chuyển động cảnh 2/3',{exact:true}).waitFor();
  await draftProgress.getByText('1/3 clip đã xác minh',{exact:true}).waitFor();
  const viewport=settings.viewportSize();
  if(process.env.AGENTFORGE_PROGRESS_SCREENSHOT)
    await draftProgress.screenshot({path:process.env.AGENTFORGE_PROGRESS_SCREENSHOT});
  await settings.setViewportSize({width:390,height:844});
  if(await draftProgress.evaluate(node=>node.scrollWidth>node.clientWidth+1))
    throw new Error('Production progress overflows mobile');
  if(viewport)await settings.setViewportSize(viewport);
  cancelledDraft={...draftFixture,id:'c'.repeat(32),status:'CANCELLED',worker_active:false,board:null,
    brief:{...draftFixture.brief,idea:'Bản nháp đã hủy'}};
  draftFixture={...draftFixture,status:'REVIEW',worker_active:false,
    created_at:'2026-06-20T03:00:00Z',video_sha:'fixture-video',receipt_sha:'fixture-receipt'};
  await settings.locator('.studio-drafts-list').getByRole('button',{name:'Làm mới',exact:false}).click();
  await settings.locator('.production-header').getByText('Video hoàn chỉnh · chờ duyệt',{exact:true}).waitFor();
  await draftProgress.getByText('100%',{exact:true}).waitFor();
  await settings.locator('.draft-row-meta time[datetime="2026-06-20T03:00:00Z"]').waitFor();
  await settings.getByRole('tab',{name:/^Bản nháp đã hủy/}).waitFor({state:'hidden'});
  await settings.route('**/api/film/drafts/*/preview*',route=>route.fulfill({status:404}));
  await settings.getByRole('button',{name:'Xem video',exact:true}).click();
  const draftPreview=settings.getByRole('dialog',{name:'Ý tưởng mới'});
  await draftPreview.getByRole('button',{name:'Duyệt bản nháp'}).waitFor();
  await draftPreview.getByText('Không phát được MP4').waitFor();
  await settings.keyboard.press('Escape');
  await draftPreview.waitFor({state:'hidden'});
  const authoredParts=['**Cảnh 1 — Phát hiện bướm (0–3 giây)**\nMiu nhìn con bướm.\n',
    '**Cảnh 2 — Theo dấu bướm (3–6 giây)**\nMiu bước qua vườn.'];
  const authoredShots=authoredParts.flatMap((part,i)=>[1,2].map(shot=>({...scene,seconds:1.5,
    content_scene:i+1,content_shot:shot,content_shot_count:2,motion_sha:'verified',
    creative_shot:1,segment:shot,segment_count:2,creative_camera:'Camera cố định',
    script_range:i?[authoredParts[0].length,authoredParts.join('').length]:[0,part.length]})));
  archivedDrafts=[
    {...draftFixture,id:'d'.repeat(32),status:'REJECTED',storyboard_version:undefined,
      brief:{...draftFixture.brief,mode:'still'},board:{...draftFixture.board,title:'Bản ảnh tĩnh đã từ chối'}},
    {...draftFixture,id:'e'.repeat(32),status:'APPROVED',
      board:{...draftFixture.board,title:'Storyboard đã duyệt'}},
    {...draftFixture,id:'f'.repeat(32),status:'APPROVED',duration_plan:{content_scene_count:2,
      creative_plan:{scenes:[{creative_shots:[{}]},{creative_shots:[{}]}]}},
      brief:{...draftFixture.brief,idea:authoredParts.join(''),scene_count:4},
      board:{...draftFixture.board,title:'Mèo và bướm - Cảnh 1: Phát hiện bướm',scenes:authoredShots}},
  ];
  await settings.locator('.studio-drafts-list').getByRole('button',{name:'Làm mới',exact:false}).click();
  await settings.getByRole('tab',{name:'Đã kết thúc',exact:true}).click();
  const rejectedRow=settings.getByRole('tab',{name:/^Bản ảnh tĩnh đã từ chối/});
  await rejectedRow.waitFor();
  if(await rejectedRow.getAttribute('aria-expanded')!=='true')await rejectedRow.locator('.draft-row-label').click();
  await draftProgress.getByRole('heading',{name:'Bản ảnh tĩnh đã từ chối',exact:true}).waitFor();
  if(await settings.getByRole('button',{name:/^Sửa cảnh \d/}).count())
    throw new Error('Rejected legacy video shows scene edit controls');
  await settings.getByRole('tab',{name:/^Storyboard đã duyệt/}).getByRole('button',{name:'Xem storyboard'}).click();
  const archivedStoryboard=settings.getByRole('dialog',{name:'Storyboard đã duyệt'});
  await archivedStoryboard.getByRole('heading',{name:'Cảnh 1',exact:true}).waitFor();
  if(await archivedStoryboard.getByRole('button',{name:/^(Sửa cảnh|AI viết lại|Thêm cảnh|Bỏ cảnh)$/}).count())
    throw new Error('Approved storyboard shows editing controls');
  await settings.keyboard.press('Escape');
  await archivedStoryboard.waitFor({state:'hidden'});
  const authoredRow=settings.getByRole('tab',{name:/^Mèo và bướm/});
  await checkDraftIconsAligned(authoredRow,['Xem storyboard','Xem video']);
  if(await authoredRow.getAttribute('aria-expanded')!=='true')await authoredRow.locator('.draft-row-label').click();
  await draftProgress.getByText('2/2 cảnh hoàn thành · 4/4 shot đã xác minh',{exact:true}).waitFor();
  await draftProgress.getByRole('heading',{name:'Cảnh 01 · Phát hiện bướm',exact:true}).waitFor();
  await authoredRow.getByRole('button',{name:'Xem storyboard'}).click();
  const authoredStoryboard=settings.getByRole('dialog',{name:'Mèo và bướm',exact:true});
  await authoredStoryboard.getByRole('heading',{name:'Theo dấu bướm',exact:true}).waitFor();
  await authoredStoryboard.getByRole('button',{name:'Cảnh 02 · Góc 1 · Segment 2/2',exact:true}).waitFor();
  await authoredStoryboard.getByText('Góc máy · Camera cố định',{exact:true}).waitFor();
  const sourceText=authoredStoryboard.locator('.storyboard-original-scene');
  if((await sourceText.innerText()).includes('**')||await sourceText.getByText('Miu nhìn con bướm.',{exact:true}).count()!==1)
    throw new Error('Original authored scene was duplicated or shown without formatting');
  await settings.keyboard.press('Escape');
  await authoredStoryboard.waitFor({state:'hidden'});
  const cancelledTab=settings.getByRole('tab',{name:/^Bản nháp đã hủy/});
  await cancelledTab.waitFor();
  await settings.route('**/api/film/drafts/*/delete',route=>{
    if(!route.request().url().endsWith('/'+cancelledDraft.id+'/delete'))
      throw new Error('Incorrect draft selected for deletion');
    const {id}=cancelledDraft;
    cancelledDraft=null;
    return route.fulfill({json:{id,deleted:true}});
  });
  const deleteButton=settings.getByRole('button',{name:'Xóa bản nháp',exact:true});
  if(await deleteButton.getAttribute('title'))throw new Error('Draft delete still uses a native tooltip');
  await deleteButton.focus();
  await settings.locator('.af-tooltip').getByRole('tooltip').getByText('Xóa bản nháp',{exact:true}).waitFor();
  await deleteButton.click();
  const deleteDialog=settings.getByRole('dialog',{name:'Xóa bản nháp?'});
  await deleteDialog.getByRole('button',{name:'Giữ lại',exact:true}).click();
  await deleteDialog.waitFor({state:'hidden'});
  await cancelledTab.waitFor();
  await settings.getByRole('button',{name:'Xóa bản nháp',exact:true}).click();
  await deleteDialog.getByRole('button',{name:'Xóa bản nháp',exact:true}).click();
  await cancelledTab.waitFor({state:'hidden'});
  const editor=settings.getByLabel('Nội dung video',{exact:true});
  const longScript='Cảnh 1 — Miu ngắm mưa.\n\n'+'Miu đi chậm về phía cửa sổ. 🐱\n\n'.repeat(520);
  await editor.fill(longScript);
  await settings.reload();
  await editor.waitFor();
  if(await editor.inputValue()!==longScript||await editor.count()!==1||await settings.getByRole('radio').count())
    throw new Error('Long Vietnamese script was not restored after refreshing');
  await settings.getByText('Thời lượng · AI tự đề xuất',{exact:true}).waitFor();
  await settings.route('**/api/film/drafts/start',route=>{
    const {id,...brief}=route.request().postDataJSON();
    if(brief.idea!==longScript||Object.keys(brief).sort().join()!=='duration_mode,idea,mode,ratio,scene_count,seconds')
      throw new Error('Studio did not submit the single content field unchanged');
    return route.fulfill({json:{id,brief,status:'QUEUED'}});
  });
  const longSubmit=settings.waitForResponse(r=>r.url().endsWith('/api/film/drafts/start'));
  await settings.getByRole('button',{name:'Tạo storyboard',exact:true}).click();
  await longSubmit;
  await editor.fill('đ'.repeat(20001));
  await settings.locator('button.draft-submit:disabled').waitFor();
  // Fresh checkout starts with zero registered model profiles.
  await settings.goto(policyOrigin+'/dashboard/#/models',{waitUntil:'networkidle'});
  await settings.getByText('Chưa đăng ký model. Chọn Đăng ký model để bắt đầu.',{exact:true}).waitFor();
  const freshHub=await (await settings.request.get(policyOrigin+'/api/model-hub')).json();
  if(freshHub.revision!==0||freshHub.profiles.length!==0)
    throw new Error('Fresh Owner Model Hub must not preload any model');
  await settings.goto(policyOrigin+'/dashboard/#/orchestrator',{waitUntil:'networkidle'});
  await settings.getByRole('heading',{name:'AI điều phối tác vụ',exact:true}).waitFor();
  for(const title of ['Chế độ thực thi','Phân công model',
    'An toàn runtime','Quyền thực thi']){
    await settings.getByText(title,{exact:true}).waitFor();
  }
  if((await settings.request.post(endpoint,postOptions)).status()!==403)
    throw new Error('Orchestrator mutation is accessible without a CSRF token');
  if(await settings.getByRole('combobox',{name:/Model chính/}).count())
    throw new Error('Duplicate model assignment editor in policy screen');
  const savePolicy=settings.locator('.orchestrator-header').getByRole('button',{name:'Lưu cấu hình'});
  const openOptions=settings.locator('.ant-select-dropdown:visible .ant-select-item-option-content');
  const motionModel=settings.getByRole('combobox',{name:'Model cho Tạo chuyển động'});
  await motionModel.click();
  await openOptions.filter({hasText:'Chưa gán'}).waitFor();
  if(await openOptions.filter({hasText:/local_primary|cloud_primary/}).count())
    throw new Error('Video binding offers incompatible text models');
  await motionModel.press('Escape');
  for(const name of ['Model điều phối','Model không khả dụng','Model được phép đề xuất',
    'Tác vụ GPU đồng thời','Lượt gọi API trả phí mỗi ngày','Số lần thử lại tối đa']){
    if(await settings.getByLabel(name,{exact:true}).count())throw new Error('Retired control still visible: '+name);
  }
  const planToggle=settings.getByRole('switch',{name:'Lập kế hoạch',exact:true});
  await planToggle.click();
  await settings.getByText('Có thay đổi chưa lưu',{exact:true}).waitFor();
  if(await motionModel.isEnabled())throw new Error('Assignment can overwrite unsaved policy edits');
  await settings.setViewportSize({width:1280,height:850});
  const tabs=settings.locator('.af-section-tabs');
  const modelTab=tabs.locator('[data-node-key="models"] [role="tab"]');
  const discardDialog=settings.getByRole('dialog',{name:'Bỏ thay đổi chưa lưu?'});
  await modelTab.click();
  await discardDialog.getByRole('button',{name:'Ở lại chỉnh sửa'}).click();
  await discardDialog.waitFor({state:'hidden'});
  if((await planToggle.getAttribute('aria-checked'))!=='true')throw new Error('Staying on tab discarded the draft');
  await settings.evaluate(()=>{location.hash='#/models';});
  await discardDialog.getByRole('button',{name:'Ở lại chỉnh sửa'}).click();
  await discardDialog.waitFor({state:'hidden'});
  if(!settings.url().endsWith('#/orchestrator')||(await planToggle.getAttribute('aria-checked'))!=='true')
    throw new Error('Hash navigation discarded the draft');
  await modelTab.click();
  await discardDialog.getByRole('button',{name:'Bỏ thay đổi',exact:true}).click();
  await settings.waitForURL('**/#/models');
  await tabs.locator('[data-node-key="orchestrator"] [role="tab"]').click();
  await planToggle.waitFor();
  if((await planToggle.getAttribute('aria-checked'))==='true'||await savePolicy.isEnabled())throw new Error('Discard kept edits');
  await settings.setViewportSize({width:390,height:850});
  await settings.goto(policyOrigin+'/dashboard/#/models');
  await settings.getByRole('button',{name:'Đăng ký model'}).click();
  const registerDialog=settings.getByRole('dialog');
  await registerDialog.getByText('Cloud',{exact:true}).click();
  await registerDialog.getByText('Anthropic-compatible',{exact:true}).waitFor();
  await registerDialog.getByLabel('Endpoint Cloud',{exact:true}).waitFor();
  await registerDialog.getByLabel('API key',{exact:true}).waitFor();
  await registerDialog.getByRole('button',{name:'Dùng biến môi trường'}).click();
  await registerDialog.getByLabel('Biến môi trường chứa API key',{exact:true}).waitFor();
  await registerDialog.getByRole('button',{name:'Nhập trực tiếp'}).click();
  if(await registerDialog.getByLabel('Địa chỉ runtime local',{exact:true}).count())
    throw new Error('Cloud registration exposed the local endpoint field');
  await registerDialog.getByText('Local',{exact:true}).click();
  await registerDialog.getByRole('combobox',{name:'Runtime'}).click();
  await openOptions.filter({hasText:/^ComfyUI$/}).evaluate(option=>option.click());
  await registerDialog.getByLabel('Mã checkpoint',{exact:true}).waitFor();
  await registerDialog.getByRole('combobox',{name:'Runtime'}).click();
  await openOptions.filter({hasText:/^Ollama$/}).evaluate(option=>option.click());
  await registerDialog.getByLabel('Tên model',{exact:true}).fill('synthetic-local:8b');
  await registerDialog.getByLabel('Mã hồ sơ',{exact:true}).fill('local_primary');
  const localEndpoint=registerDialog.getByLabel('Địa chỉ runtime local',{exact:true});
  await localEndpoint.fill('http://127.0.0.1:99999');
  await registerDialog.getByRole('button',{name:'Xem lại cấu hình'}).click();
  await registerDialog.getByText('Dùng địa chỉ HTTP loopback với cổng từ 1 đến 65535.').waitFor();
  await localEndpoint.fill('http://127.0.0.1:11434');
  await settings.route('**/api/model-hub/profile/preview',route=>route.fulfill({
    status:400,json:{message:'MODEL_HUB_REVISION_CONFLICT'},
  }),{times:1});
  await registerDialog.getByRole('button',{name:'Xem lại cấu hình'}).click();
  await registerDialog.getByRole('button',{name:'Tải lại cấu hình',exact:true}).click();
  await registerDialog.getByText('Phiên bản này chưa có hồ sơ mang mã local_primary.').waitFor();
  await registerDialog.getByRole('button',{name:'Dùng phiên bản này để tiếp tục'}).click();
  if(await registerDialog.getByLabel('Tên model',{exact:true}).inputValue()!=='synthetic-local:8b')
    throw new Error('Reloading a stale revision discarded pending model edits');
  await registerDialog.getByRole('button',{name:'Xem lại cấu hình'}).click();
  await registerDialog.getByText('synthetic-local:8b',{exact:true}).waitFor();
  const beforeSave=await (await settings.request.get(policyOrigin+'/api/model-hub')).json();
  if(beforeSave.profiles.length)throw new Error('Registration saved before Owner confirmation');
  const registeredRow=settings.locator('tr[data-row-key="local_primary"]');
  let checks=0;
  let unblockCheck;
  const checkGate=new Promise(resolve=>{unblockCheck=resolve;});
  await settings.route('**/api/model-hub/readiness',async route=>{
    const body=route.request().postDataJSON();
    if(body.expected_revision!==1||body.capability!=='general.text'||body.profile_id!=='local_primary')
      throw new Error('Readiness did not use the current model and revision');
    checks++;
    if(checks===1){
      const registered=await (await settings.request.get(policyOrigin+'/api/model-hub')).json();
      if(registered.revision!==1||registered.profiles[0]?.provider!=='ollama')
        throw new Error('Readiness started before Owner profile was committed to SQLite');
      await checkGate;
      return route.fulfill({status:503,json:{error:'fixture'}});
    }
    const [status,reason]=[
      ['UNAVAILABLE','UNAVAILABLE'],['MISSING_DEPENDENCY','MODEL_NOT_INSTALLED'],
      ['METADATA_COMPATIBLE',null],
    ][checks-2];
    return route.fulfill({json:{revision:1,profile_id:body.profile_id,capability:body.capability,
      status,reason,checked_at:'2026-01-01T08:00:00Z'}});
  });
  await registerDialog.getByRole('button',{name:'Lưu và kiểm tra',exact:true}).click();
  await registerDialog.waitFor({state:'hidden'});
  await registeredRow.getByText('Đang kiểm tra…',{exact:true}).waitFor();
  unblockCheck();
  await registeredRow.getByRole('button',{name:'Thử lại',exact:true}).click();
  await registeredRow.getByText('Runtime không khả dụng',{exact:true}).waitFor();
  await registeredRow.getByRole('button',{name:'Kiểm tra',exact:true}).click();
  await registeredRow.getByText('Thiếu điều kiện',{exact:true}).waitFor();
  await registeredRow.getByRole('button',{name:'Kiểm tra',exact:true}).click();
  await registeredRow.getByText('Metadata tương thích',{exact:true}).waitFor();
  await registeredRow.locator('time').waitFor();
  if(checks!==4||await registeredRow.getByText('Đã chạy thử thành công').count())
    throw new Error('Metadata was presented as inference or retried automatically');
  await settings.unroute('**/api/model-hub/readiness');
  console.log('Model adapter selection, validation and real SQLite registration: PASS');
  const planModel=settings.getByRole('combobox',{name:'Model cho Lập kế hoạch'});
  if(await planModel.count())throw new Error('Duplicate assignment editor in Model AI');
  await settings.goto(policyOrigin+'/dashboard/#/orchestrator');
  await planModel.click();
  await openOptions.filter({hasText:/local_primary/}).click();
  await settings.getByRole('dialog').getByRole('button',{name:'Xác nhận'}).click();
  await settings.getByRole('dialog').waitFor({state:'hidden'});
  await settings.goto(policyOrigin+'/dashboard/#/orchestrator');
  await settings.getByRole('heading',{name:'AI điều phối tác vụ',exact:true}).waitFor();
  await planToggle.click();
  const cloudToggle=settings.getByRole('switch',{name:'Gọi AI cloud',exact:true});
  await cloudToggle.click();
  const cloudLimit=settings.getByRole('spinbutton',{name:'Giới hạn lượt gọi cloud mỗi production'});
  await cloudLimit.fill('12');
  const toolsToggle=settings.getByRole('switch',{name:'Chạy công cụ local'});
  const toolsSelect=settings.getByRole('combobox',{name:'Công cụ local được phép'});
  if(await toolsSelect.count())throw new Error('Disabled tools permission shows the allowlist');
  await toolsToggle.click();
  await toolsSelect.click();
  await openOptions.filter({hasText:/^FFmpeg$/}).click();
  await toolsSelect.press('Escape');
  await toolsToggle.click();
  await toolsSelect.waitFor({state:'hidden'});
  await savePolicy.click();
  await settings.getByRole('dialog').getByRole('button',{name:'Lưu cấu hình'}).click();
  await settings.getByText('Owner tùy chỉnh · Phiên bản 3',{exact:true}).waitFor();
  await settings.reload();
  await settings.getByText('Owner tùy chỉnh · Phiên bản 3',{exact:true}).waitFor();
  if((await planToggle.getAttribute('aria-checked'))!=='true')
    throw new Error('Settings did not persist after reload');
  const persisted=await (await settings.request.get(policyOrigin+'/api/model-hub')).json();
  if(!persisted.orchestrator.policy.permissions.call_cloud||
    persisted.orchestrator.policy.permissions.call_local||persisted.orchestrator.policy.cloud_call_limit!==12)
    throw new Error('Independent cloud permission or call budget did not persist');
  if(persisted.orchestrator.policy.permissions.run_tools||
    !persisted.orchestrator.policy.tools.includes('ffmpeg'))
    throw new Error('Hiding the tools allowlist discarded the selection');
  if(persisted.routes.find(row=>row.id==='general.text')?.model_ref!=='local_primary'||
    'primary' in persisted.orchestrator.policy||'gpu_concurrency' in persisted.orchestrator.policy)
    throw new Error('Saved model was not read back from real Model Hub');
  const {csrf}=await (await settings.request.get(policyOrigin+'/api/session')).json();
  const invalid=await settings.request.post(policyOrigin+'/api/model-hub/route',{headers:{...postOptions.headers,'X-CSRF-Token':csrf},
    data:{ack:'SET_MODEL_ROUTE',expected_revision:3,task_id:'film.motion',model_ref:'local_primary'}});
  if(invalid.status()!==400)throw new Error('API accepted a text model for video');
  const obsolete=await settings.request.post(endpoint,{headers:{...postOptions.headers,'X-CSRF-Token':csrf},
    data:{ack:'SAVE_ORCHESTRATOR',expected_revision:3,policy:persisted.orchestrator.policy,
      route_changes:{'film.motion':'local_primary'}}});
  if(obsolete.status()===200)throw new Error('Retired policy assignment API accepted a write');
  const assignedDelete=await settings.request.post(policyOrigin+'/api/model-hub/profile/delete',{
    headers:{Origin:policyOrigin,'X-CSRF-Token':csrf},
    data:{ack:'DELETE_MODEL_PROFILE',expected_revision:3,profile_id:'local_primary'},
  });
  if(assignedDelete.status()!==400)throw new Error('API deleted assigned AI model');
  await settings.getByRole('button',{name:'Đặt lại mặc định'}).click();
  await settings.getByRole('dialog').getByRole('button',{name:'Đặt lại',exact:true}).click();
  await settings.getByText('Mặc định · Phiên bản 4',{exact:true}).waitFor();
  if((await planToggle.getAttribute('aria-checked'))==='true'||(await cloudToggle.getAttribute('aria-checked'))==='true')
    throw new Error('Reset did not restore defaults');
  for(const width of [390,900,1440]){
    await settings.setViewportSize({width,height:850});
    await settings.waitForFunction(()=>document.documentElement.scrollWidth<=window.innerWidth+2);
  }
  await settings.getByRole('button',{name:'Sáng'}).click();
  await settings.waitForFunction(()=>document.documentElement.dataset.theme==='light');
  await settings.getByRole('button',{name:'Tối'}).click();
  await settings.waitForFunction(()=>document.documentElement.dataset.theme==='dark');
  // Real Model Hub UI can delete an unassigned Owner profile; never touches weights.
  await settings.goto(policyOrigin+'/dashboard/#/models',{waitUntil:'networkidle'});
  const modelRow=settings.locator('tr[data-row-key="local_primary"]');
  await settings.getByRole('button',{name:'Sáng'}).click();
  await settings.waitForFunction(()=>document.documentElement.dataset.theme==='light');
  await modelRow.getByRole('button',{name:'Sửa'}).click();
  await registerDialog.getByText('Chỉnh sửa hồ sơ model',{exact:true}).waitFor();
  if(await registerDialog.getByLabel('Tên model',{exact:true}).inputValue()!=='synthetic-local:8b')
    throw new Error('Editor did not load the persisted model');
  await registerDialog.getByRole('button',{name:'Hủy',exact:true}).click();
  await registerDialog.waitFor({state:'hidden'});
  // Resetting permissions must not unassign the model. Unassign at AI điều phối.
  await settings.goto(policyOrigin+'/dashboard/#/orchestrator');
  await planModel.waitFor();
  if(!(await settings.locator('.model-route').filter({has:planModel}).innerText()).includes('local_primary'))throw new Error('Policy reset removed the assignment');
  await planModel.click();
  await openOptions.filter({hasText:'Chưa gán'}).click();
  await settings.getByRole('dialog').getByRole('button',{name:'Xác nhận'}).click();
  await settings.getByRole('dialog').waitFor({state:'hidden'});
  await settings.goto(policyOrigin+'/dashboard/#/models');
  await modelRow.getByText('Xóa',{exact:true}).click();
  await settings.getByRole('dialog').getByRole('button',{name:'Xác nhận'}).click();
  await settings.getByText('Chưa đăng ký model. Chọn Đăng ký model để bắt đầu.',{exact:true}).waitFor();
  const cleaned=await (await settings.request.get(policyOrigin+'/api/model-hub')).json();
  if(cleaned.profiles.length!==0||cleaned.revision!==6)
    throw new Error('Owner profile removal did not persist in SQLite');
  if(process.platform==='win32'){
    const fixtureKey='smoke-credential-not-a-real-key';
    await settings.getByRole('button',{name:'Đăng ký model'}).click();
    await registerDialog.getByText('Cloud',{exact:true}).click();
    await registerDialog.getByLabel('Model ID',{exact:true}).fill('fixture-cloud');
    await registerDialog.getByLabel('Endpoint Cloud',{exact:true}).fill('https://api.example.com');
    await registerDialog.getByLabel('API key',{exact:true}).fill(fixtureKey);
    await registerDialog.getByLabel('Mã hồ sơ',{exact:true}).fill('cloud_fixture');
    await registerDialog.getByRole('button',{name:'Xem lại cấu hình'}).click();
    await registerDialog.getByText('••••••••',{exact:true}).waitFor();
    await settings.route('**/api/model-hub/profile',route=>route.fulfill({
      status:400,contentType:'application/json',
      body:JSON.stringify({error:'ValueError',message:'Endpoint không hợp lệ cho hồ sơ này.'}),
    }),{times:1});
    await registerDialog.getByRole('button',{name:'Xác nhận lưu'}).click();
    await registerDialog.getByText('Endpoint không hợp lệ cho hồ sơ này.',{exact:true}).waitFor();
    await registerDialog.getByRole('button',{name:'Xác nhận lưu'}).click();
    await registerDialog.waitFor({state:'hidden'});
    const cloud=await (await settings.request.get(policyOrigin+'/api/model-hub')).json();
    if(cloud.profiles[0]?.has_api_key!==true||JSON.stringify(cloud).includes(fixtureKey))
      throw new Error('Direct Cloud registration failed or exposed the key');
    await settings.getByText('Chưa kiểm tra',{exact:true}).first().waitFor();
    await settings.getByText('Đã lưu hồ sơ model',{exact:true}).waitFor();
  }
  const concurrent=await browser.newContext();
  const login2=await concurrent.request.post(policyOrigin+'/api/login',{
    headers:{Origin:policyOrigin},data:{code:ownerCode},
  });
  if(!login2.ok())throw new Error('Second Owner session could not log in');
  const concurrentHeaders={Origin:policyOrigin,'X-CSRF-Token':(await login2.json()).csrf};
  const readModels=async()=>(await settings.request.get(policyOrigin+'/api/model-hub')).json();
  const localProfile=(id,model)=>({id,model,provider:'ollama',enabled:true,base_url:'http://127.0.0.1:11434'});
  const concurrentSave=async(profile,intent)=>{
    const {revision}=await readModels();
    const r=await concurrent.request.post(policyOrigin+'/api/model-hub/profile',{
      headers:concurrentHeaders,data:{ack:'SAVE_MODEL_PROFILE',expected_revision:revision,profile,intent},
    });
    if(!r.ok())throw new Error('Concurrent fixture mutation failed: '+r.status());
    return (await r.json()).revision;
  };
  await concurrentSave(localProfile('conflict_model','initial:8b'),'create');
  await settings.getByRole('button',{name:'Làm mới',exact:true}).click();
  const conflictRow=settings.locator('tr[data-row-key="conflict_model"]');
  await conflictRow.getByRole('button',{name:'Sửa',exact:true}).click();
  await registerDialog.getByLabel('Tên model',{exact:true}).fill('owner-draft:8b');
  await registerDialog.getByRole('button',{name:'Xem lại cấu hình'}).click();
  await registerDialog.getByText('owner-draft:8b',{exact:true}).waitFor();
  await concurrentSave(localProfile('conflict_model','server-edit:8b'),'edit');
  await registerDialog.getByRole('button',{name:'Xác nhận lưu'}).click();
  await registerDialog.getByRole('button',{name:'Tải lại cấu hình'}).click();
  const comparison=registerDialog.getByRole('region',{name:'Đối chiếu hồ sơ model'});
  await comparison.getByText(/owner-draft:8b/).waitFor();
  await comparison.getByText(/server-edit:8b/).waitFor();
  if((await readModels()).profiles.find(p=>p.id==='conflict_model').model!=='server-edit:8b')
    throw new Error('Reloading an edit conflict overwrote the server profile');
  await registerDialog.getByRole('button',{name:'Dùng phiên bản này để tiếp tục'}).click();
  if(await registerDialog.getByLabel('Tên model',{exact:true}).inputValue()!=='owner-draft:8b')
    throw new Error('Comparing a conflict discarded the Owner draft');
  await registerDialog.getByRole('button',{name:'Xem lại cấu hình'}).click();
  await registerDialog.getByRole('button',{name:'Xác nhận lưu'}).click();
  await registerDialog.waitFor({state:'hidden'});

  await settings.getByRole('button',{name:'Đăng ký model'}).click();
  await registerDialog.getByLabel('Tên model',{exact:true}).fill('pending:8b');
  await registerDialog.getByLabel('Mã hồ sơ',{exact:true}).fill('shared_model');
  await registerDialog.getByRole('button',{name:'Xem lại cấu hình'}).click();
  await registerDialog.getByText('pending:8b',{exact:true}).waitFor();
  await concurrentSave(localProfile('shared_model','claimed:8b'),'create');
  await registerDialog.getByRole('button',{name:'Xác nhận lưu'}).click();
  await registerDialog.getByRole('button',{name:'Tải lại cấu hình'}).click();
  await comparison.getByText(/claimed:8b/).waitFor();
  await registerDialog.getByRole('button',{name:'Đổi mã hồ sơ'}).click();
  await registerDialog.getByRole('button',{name:'Xem lại cấu hình'}).click();
  await registerDialog.getByText('Mã hồ sơ đã tồn tại. Hãy chọn mã khác.').waitFor();
  await registerDialog.getByLabel('Mã hồ sơ',{exact:true}).fill('renamed_model');
  await registerDialog.getByRole('button',{name:'Xem lại cấu hình'}).click();
  await registerDialog.getByRole('button',{name:'Xác nhận lưu'}).click();
  await registerDialog.waitFor({state:'hidden'});
  const afterRename=await readModels();
  if(afterRename.profiles.find(p=>p.id==='shared_model').model!=='claimed:8b'||
     afterRename.profiles.find(p=>p.id==='renamed_model').model!=='pending:8b')
    throw new Error('Creating with an occupied ID overwrote the other Owner session');

  let finishReadiness;
  const staleReadinessGate=new Promise(resolve=>{finishReadiness=resolve;});
  await settings.route('**/api/model-hub/readiness',async route=>{
    const {profile_id,capability,expected_revision:revision}=route.request().postDataJSON();
    await staleReadinessGate;
    return route.fulfill({json:{profile_id,capability,revision,status:'METADATA_COMPATIBLE',
      checked_at:'2026-01-01T08:00:00Z'}});
  });
  await conflictRow.getByRole('button',{name:'Kiểm tra',exact:true}).click();
  await conflictRow.getByText('Đang kiểm tra…',{exact:true}).waitFor();
  const newRevision=await concurrentSave(localProfile('conflict_model','new-revision:8b'),'edit');
  await settings.getByRole('button',{name:'Làm mới',exact:true}).click();
  await conflictRow.getByText('new-revision:8b',{exact:true}).waitFor();
  const staleResponse=settings.waitForResponse(response=>response.url().endsWith('/api/model-hub/readiness'));
  finishReadiness();
  await (await staleResponse).finished();
  await settings.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  await conflictRow.getByText('Chưa kiểm tra',{exact:true}).waitFor();
  if(newRevision<=afterRename.revision||await conflictRow.getByText('Metadata tương thích',{exact:true}).count())
    throw new Error('An old readiness response leaked into the new revision');
  await settings.unroute('**/api/model-hub/readiness');
  await concurrent.close();
  console.log('Model Hub concurrent Owner edits, create ID collision and stale readiness isolation: PASS');
  if(settingsErrors.length)throw new Error('Orchestrator runtime errors: '+settingsErrors.join(' | '));
  console.log('Orchestrator authenticated API, SQLite persistence, reset and responsive Edge: PASS');

  const fluxPage=await browser.newPage({viewport:{width:1280,height:850}});
  await fluxPage.route('**/api/session',route=>route.fulfill({json:{csrf:'fixture'}}));
  await fluxPage.route('**/api/model-hub',route=>route.fulfill({json:{
    revision:4,adapters:[{id:'comfyui',label:'ComfyUI',connection:'local'}],
    profiles:[{id:'fixture_flux',provider:'comfyui',model:'fixture.gguf',enabled:true,
      flux:{max_resolution:768,max_steps:4,timeout_seconds:60}}],
  }}));
  let probes=0, finishProbe;
  await fluxPage.route('**/api/model-hub/probe',async route=>{
    const body=route.request().postDataJSON();
    if(body.ack!=='RUN_FLUX_MODEL_PROBE'||body.profile_id!=='fixture_flux'||
        body.expected_revision!==4||body.width!==768||body.height!==768||body.steps!==4||
        'seed' in body)throw new Error('Unexpected FLUX probe payload');
    probes++;
    if(probes===1)return route.fulfill({status:400,json:{message:'COMFYUI_TIMEOUT'}});
    await new Promise(resolve=>{finishProbe=resolve;});
    return route.fulfill({json:{status:'ASSET_READY',duration_seconds:1,seed:7,width:768,
      height:768,steps:4,preview_url:'/api/visuals/fixture/preview',
      workspace_path:'workspace/visuals/fixture.png'}});
  });
  await fluxPage.route('**/api/visuals/fixture/preview',route=>route.fulfill({
    contentType:'image/png',
    body:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aL4sAAAAASUVORK5CYII=','base64'),
  }));
  await fluxPage.goto(origin+'/dashboard/#/models');
  await fluxPage.getByRole('button',{name:'Chạy thử',exact:true}).click();
  const fluxDialog=fluxPage.getByRole('dialog',{name:'Chạy thử · fixture_flux'});
  await fluxDialog.getByLabel('Prompt',{exact:true}).fill('An image fixture');
  const createImage=fluxDialog.locator('button[type="submit"]');
  await createImage.click();
  await fluxDialog.getByText('ComfyUI phản hồi quá chậm',{exact:true}).waitFor();
  await createImage.click();
  await fluxDialog.getByText(/Đang tạo và xác minh ảnh/).waitFor();
  if(await fluxDialog.getByLabel('Prompt',{exact:true}).isEnabled())
    throw new Error('FLUX form remains editable during dispatch');
  for(let i=0;!finishProbe&&i<20;i++)await sleep(50);
  if(!finishProbe)throw new Error('FLUX probe was not dispatched');
  finishProbe();
  const image=fluxDialog.getByRole('img',{name:'Ảnh chạy thử FLUX'});
  await image.waitFor();
  await fluxPage.waitForFunction(()=>document.querySelector('img[alt="Ảnh chạy thử FLUX"]')?.naturalWidth===1);
  await fluxDialog.getByText('workspace/visuals/fixture.png',{exact:true}).waitFor();
  if(probes!==2)throw new Error('Unexpected number of FLUX submissions');
  await fluxPage.close();
  console.log('FLUX Model Hub dialog loading, error, retry and preview UI: PASS');
} finally {
  if (browser) await browser.close();
  vite.kill();
  if(policyServer&&policyServer.exitCode===null&&policyServer.signalCode===null){
    const exited=once(policyServer,'exit');
    if(policyServer.kill())await exited;
  }
  if(policyTemp){
    await rm(join(policyTemp,'hub.sqlite3'),{force:true});
    await rmdir(policyTemp);
  }
}
