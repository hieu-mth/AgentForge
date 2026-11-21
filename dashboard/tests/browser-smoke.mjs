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
  await page2.getByRole('tooltip').getByText('Ổ đĩa, RAM và VRAM dùng hệ 1.024',{exact:false}).waitFor();
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
  if((await overview.locator('.env-stat-value').allTextContents()).join(',')!=='1,1,1')
    throw new Error('Overview counters do not match project states');
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
  await settings.locator('.draft-resource-details summary').click();
  await settings.getByText('RAM dùng / khả dụng: 24 GB / 8 GB',{exact:true}).waitFor();
  await settings.getByText('VRAM dùng / khả dụng: 9 GB / 3 GB',{exact:true}).waitFor();
  if(await settings.locator('.studio-projects').count())
    throw new Error('Studio displays an empty episode panel');
  await settings.getByText('Tạo video từ ý tưởng',{exact:true}).waitFor();
  await settings.getByText('Chưa có bản nháp',{exact:true}).waitFor();
  let draftFixture=null;
  let cancelledDraft=null;
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
    return route.fulfill({json:{drafts:[draftFixture,cancelledDraft].filter(Boolean)}});
  });
  await settings.reload();
  await settings.getByText(/Backend đang chạy chưa hỗ trợ bản nháp/).waitFor();
  if(await settings.getByText('Chưa có bản nháp',{exact:true}).count())
    throw new Error('Missing draft API was silently displayed as empty');
  draftListStatus=503;
  await settings.getByRole('button',{name:'Thử lại bản nháp',exact:true}).click();
  await settings.getByText('Fixture SQLite unavailable',{exact:true}).waitFor();
  draftListStatus=200;
  await settings.route('**/api/film/drafts/start',route=>{
    const {id,...brief}=route.request().postDataJSON();
    if(!/^[0-9a-f]{32}$/.test(id)||!['Chú mèo cam khám phá khu rừng','Ý tưởng mới'].includes(brief.idea)||
        brief.seconds!==6||brief.scene_count!==3||brief.ratio!=='16:9'||
        brief.mode!=='motion'||brief.motion_approved!==true)
      throw new Error('Unexpected draft submission');
    draftFixture={id,brief,status:'RUNNING',stage:'PLANNING',worker_active:true,
      activity:{operation:'plan',provider:'ollama',model:'fixture-planner'}};
    return route.fulfill({json:draftFixture});
  });
  await settings.getByLabel('Nội dung video',{exact:true}).fill('Chú mèo cam khám phá khu rừng');
  await settings.getByRole('button',{name:'Tạo bản nháp',exact:true}).click();
  await settings.getByRole('button',{name:'Duyệt và tạo phim',exact:true}).click();
  const draftProgress=settings.getByRole('region',{name:'Tiến độ tạo bản nháp'});
  await draftProgress.getByText('Đang lập kế hoạch',{exact:true}).waitFor();
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
  await settings.getByRole('tab',{name:/^Chú mèo cam khám phá khu rừng/}).waitFor();
  draftFixture={...draftFixture,status:'FAILED',worker_active:false,error:'Fixture runtime unavailable'};
  await settings.getByText('Cần xử lý',{exact:true}).click();
  await settings.getByText('Fixture runtime unavailable',{exact:true}).waitFor();
  await settings.route('**/api/film/drafts/*/resume',route=>{
    draftFixture=null;
    draftListStatus=503;
    return route.fulfill({status:404,json:{error:'draft_not_found'}});
  });
  await settings.getByRole('button',{name:'Tiếp tục từ checkpoint'}).click();
  await settings.getByText(/Bản nháp này không còn tồn tại/).waitFor();
  await settings.getByText('Fixture SQLite unavailable',{exact:true}).waitFor();
  await settings.getByRole('tab',{name:/^Chú mèo cam khám phá khu rừng/}).waitFor({state:'hidden'});
  const failedReads=draftReads;
  await sleep(2800);
  if(draftReads!==failedReads)throw new Error('Draft list retried automatically after an API failure');
  draftListStatus=200;
  await settings.getByLabel('Nội dung video',{exact:true}).fill('Ý tưởng mới');
  await settings.getByRole('button',{name:'Tạo bản nháp',exact:true}).click();
  await settings.getByRole('button',{name:'Duyệt và tạo phim',exact:true}).click();
  await settings.getByRole('tab',{name:/^Ý tưởng mới/}).waitFor();
  const scene={seconds:2,description:'Miu quay đầu',character_ids:[],audio:'',asset:'fixture-image'};
  draftFixture={...draftFixture,stage:'MOTION',board:{title:'Ý tưởng mới',scenes:[
    {...scene,motion_sha:'fixture-clip'},scene,scene]},
    activity:{operation:'motion',provider:'comfyui',model:'fixture-ltx',scene:2}};
  await draftProgress.getByText('Đang tạo chuyển động cảnh 2/3',{exact:true}).waitFor();
  await draftProgress.getByText('1/3 clip đã xác minh',{exact:true}).waitFor();
  cancelledDraft={...draftFixture,id:'c'.repeat(32),status:'CANCELLED',worker_active:false,board:null,
    brief:{...draftFixture.brief,idea:'Bản nháp đã hủy'}};
  draftFixture={...draftFixture,status:'REVIEW',worker_active:false,
    created_at:'2026-06-20T03:00:00Z',video_sha:'fixture-video'};
  await settings.locator('.studio-drafts-list').getByRole('button',{name:'Làm mới',exact:false}).click();
  await settings.getByText('Phim hoàn chỉnh · chờ duyệt',{exact:true}).waitFor();
  await settings.locator('.draft-row-meta time[datetime="2026-06-20T03:00:00Z"]').waitFor();
  await settings.getByRole('tab',{name:/^Bản nháp đã hủy/}).waitFor({state:'hidden'});
  await settings.route('**/api/film/drafts/*/preview*',route=>route.fulfill({status:404}));
  await settings.getByRole('button',{name:'Xem bản nháp MP4'}).click();
  const draftPreview=settings.getByRole('dialog',{name:'Ý tưởng mới'});
  await draftPreview.getByRole('button',{name:'Duyệt bản nháp'}).waitFor();
  await draftPreview.getByText('Không phát được MP4').waitFor();
  await settings.keyboard.press('Escape');
  await draftPreview.waitFor({state:'hidden'});
  await settings.getByRole('tab',{name:'Đã kết thúc',exact:true}).click();
  await settings.getByRole('tab',{name:/^Bản nháp đã hủy/}).waitFor();
  const editor=settings.getByLabel('Nội dung video',{exact:true});
  const longScript='Cảnh 1 — Miu ngắm mưa.\n\n'+'Miu đi chậm về phía cửa sổ. 🐱\n\n'.repeat(520);
  await editor.fill(longScript);
  await settings.reload();
  await editor.waitFor();
  if(await editor.inputValue()!==longScript||await editor.count()!==1||await settings.getByRole('radio').count())
    throw new Error('Long Vietnamese script was not restored after refreshing');
  await settings.getByText('Kịch bản khá dày',{exact:false}).waitFor();
  await settings.route('**/api/film/drafts/start',route=>{
    const {id,...brief}=route.request().postDataJSON();
    if(brief.idea!==longScript||Object.keys(brief).sort().join()!=='idea,mode,motion_approved,ratio,scene_count,seconds')
      throw new Error('Studio did not submit the single content field unchanged');
    return route.fulfill({json:{id,brief,status:'QUEUED'}});
  });
  const longSubmit=settings.waitForResponse(r=>r.url().endsWith('/api/film/drafts/start'));
  await settings.getByRole('button',{name:'Tạo bản nháp',exact:true}).click();
  await settings.getByRole('button',{name:'Duyệt và tạo phim',exact:true}).click();
  await longSubmit;
  await settings.getByRole('button',{name:'Duyệt và tạo phim',exact:true}).waitFor({state:'hidden'});
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
  for(const title of ['AI điều phối chính','Phân công AI theo năng lực',
    'Quy tắc tự động điều phối','Quyền hạn & giới hạn']){
    await settings.getByText(title,{exact:true}).waitFor();
  }
  if((await settings.request.post(endpoint,postOptions)).status()!==403)
    throw new Error('Orchestrator mutation is accessible without a CSRF token');
  await settings.getByText('Không khả dụng',{exact:true}).first().waitFor();
  const savePolicy=settings.locator('.orchestrator-header').getByRole('button',{name:'Lưu cấu hình'});
  const openOptions=settings.locator('.ant-select-dropdown:visible .ant-select-item-option-content');
  const motionModel=settings.getByRole('combobox',{name:'Model chính · Tạo chuyển động'});
  await motionModel.click();
  await openOptions.filter({hasText:'Chưa gán'}).waitFor();
  if(await openOptions.filter({hasText:/local_primary|cloud_primary/}).count())
    throw new Error('Video binding offers incompatible text models');
  await motionModel.press('Escape');
  const allowed=settings.getByRole('combobox',{name:'Model được phép đề xuất'});
  if(await allowed.count())throw new Error('Fixed selection shows suggestion options');
  const suggest=settings.getByText('AI đề xuất',{exact:true});
  await suggest.evaluate(node=>node.scrollIntoView({block:'center',behavior:'instant'}));
  const scrollBefore=await settings.evaluate(()=>window.scrollY);
  const controlBefore=await suggest.evaluate(node=>node.getBoundingClientRect().top);
  await suggest.click();
  await allowed.waitFor();
  const scrollAfter=await settings.evaluate(()=>window.scrollY);
  const controlAfter=await suggest.evaluate(node=>node.getBoundingClientRect().top);
  if(Math.abs(scrollAfter-scrollBefore)>2||Math.abs(controlAfter-controlBefore)>2)
    throw new Error('Editing orchestration rules moved the viewport: '+JSON.stringify({
      scrollBefore,scrollAfter,controlBefore,controlAfter,
    }));
  await savePolicy.click();
  await settings.getByText('Chọn model khả dụng cho danh sách đề xuất.',{exact:true}).waitFor();
  await settings.getByRole('button',{name:'Hủy thay đổi'}).click();
  const fallbackMode=settings.getByRole('combobox',{name:'Model không khả dụng'});
  await fallbackMode.click();
  await openOptions.filter({hasText:/^Dùng model local dự phòng đã gán$/}).click();
  await settings.getByText('Chưa gán model dự phòng.',{exact:false}).waitFor();
  await settings.getByRole('button',{name:'Hủy thay đổi'}).click();
  const decompose=settings.getByRole('checkbox',{name:'Tự phân tích và chia nhỏ yêu cầu'});
  await decompose.check();
  await settings.getByText('Có thay đổi chưa lưu',{exact:true}).waitFor();
  await settings.setViewportSize({width:1280,height:850});
  const tabs=settings.locator('.af-section-tabs');
  const modelTab=tabs.locator('[data-node-key="models"] [role="tab"]');
  const discardDialog=settings.getByRole('dialog',{name:'Bỏ thay đổi chưa lưu?'});
  await modelTab.click();
  await discardDialog.getByRole('button',{name:'Ở lại chỉnh sửa'}).click();
  await discardDialog.waitFor({state:'hidden'});
  if(!await decompose.isChecked())throw new Error('Staying on tab discarded the draft');
  await settings.evaluate(()=>{location.hash='#/models';});
  await discardDialog.getByRole('button',{name:'Ở lại chỉnh sửa'}).click();
  await discardDialog.waitFor({state:'hidden'});
  if(!settings.url().endsWith('#/orchestrator')||!await decompose.isChecked())
    throw new Error('Hash navigation discarded the draft');
  await modelTab.click();
  await discardDialog.getByRole('button',{name:'Bỏ thay đổi',exact:true}).click();
  await settings.waitForURL('**/#/models');
  await tabs.locator('[data-node-key="orchestrator"] [role="tab"]').click();
  await decompose.waitFor();
  if(await decompose.isChecked()||await savePolicy.isEnabled())throw new Error('Discard kept edits');
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
  await openOptions.filter({hasText:/^Ollama$/}).click();
  await registerDialog.getByLabel('Tên model',{exact:true}).fill('synthetic-local:8b');
  await registerDialog.getByLabel('Mã hồ sơ',{exact:true}).fill('local_primary');
  const localEndpoint=registerDialog.getByLabel('Địa chỉ runtime local',{exact:true});
  await localEndpoint.fill('http://127.0.0.1:99999');
  await registerDialog.getByRole('button',{name:'Xem lại cấu hình'}).click();
  await registerDialog.getByText('Dùng địa chỉ HTTP loopback với cổng từ 1 đến 65535.').waitFor();
  await localEndpoint.fill('http://127.0.0.1:11434');
  await registerDialog.getByRole('button',{name:'Xem lại cấu hình'}).click();
  await registerDialog.getByText('synthetic-local:8b',{exact:true}).waitFor();
  const beforeSave=await (await settings.request.get(policyOrigin+'/api/model-hub')).json();
  if(beforeSave.profiles.length)throw new Error('Registration saved before Owner confirmation');
  await registerDialog.getByRole('button',{name:'Xác nhận lưu'}).click();
  await registerDialog.waitFor({state:'hidden'});
  const registered=await (await settings.request.get(policyOrigin+'/api/model-hub')).json();
  if(registered.revision!==1||registered.profiles[0]?.provider!=='ollama')
    throw new Error('Owner SQLite profile registration failed');
  console.log('Model adapter selection, validation and real SQLite registration: PASS');
  await settings.goto(policyOrigin+'/dashboard/#/orchestrator');
  await settings.getByRole('heading',{name:'AI điều phối tác vụ',exact:true}).waitFor();
  await settings.getByRole('combobox',{name:'Model điều phối'}).click();
  await openOptions.filter({hasText:/local_primary/}).click();
  await decompose.check();
  const dailyLimit=settings.getByRole('spinbutton',{name:'Lượt gọi API trả phí mỗi ngày'});
  if(await dailyLimit.inputValue()!=='10')throw new Error('Default paid API limit is incorrect');
  await dailyLimit.fill('37');
  const toolsToggle=settings.getByRole('switch',{name:'Chạy công cụ local'});
  const toolsSelect=settings.getByRole('combobox',{name:'Công cụ local được phép'});
  if(await toolsSelect.count())throw new Error('Disabled tools permission shows the allowlist');
  await toolsToggle.click();
  await toolsSelect.click();
  await openOptions.filter({hasText:/^FFmpeg$/}).click();
  await toolsSelect.press('Escape');
  await toolsToggle.click();
  await toolsSelect.waitFor({state:'hidden'});
  const gpuJobs=settings.getByRole('spinbutton',{name:'Tác vụ GPU đồng thời'});
  if(await gpuJobs.count())throw new Error('Serial GPU mode shows concurrency input');
  await settings.getByText('Chạy đồng thời',{exact:true}).click();
  await gpuJobs.fill('3');
  await fallbackMode.click();
  await openOptions.filter({hasText:/^Dùng model local dự phòng đã gán$/}).click();
  await settings.getByRole('combobox',{name:'Model dự phòng · Lập kế hoạch'}).click();
  await openOptions.filter({hasText:/local_primary/}).click();
  await settings.getByText('Đã gán dự phòng cho 1 năng lực: Lập kế hoạch.').waitFor();
  await savePolicy.click();
  await settings.getByRole('dialog').getByRole('button',{name:'Lưu cấu hình'}).click();
  await settings.getByText('Owner tùy chỉnh · Phiên bản 2',{exact:true}).waitFor();
  await settings.reload();
  await settings.getByText('Owner tùy chỉnh · Phiên bản 2',{exact:true}).waitFor();
  if(!await decompose.isChecked()||await dailyLimit.inputValue()!=='37'||await gpuJobs.inputValue()!=='3')
    throw new Error('Settings did not persist after reload');
  const persisted=await (await settings.request.get(policyOrigin+'/api/model-hub')).json();
  if(persisted.orchestrator.policy.permissions.run_tools||
    !persisted.orchestrator.policy.tools.includes('ffmpeg'))
    throw new Error('Hiding the tools allowlist discarded the selection');
  if(persisted.orchestrator.policy.primary!=='local_primary')
    throw new Error('Saved model was not read back from real Model Hub');
  const {csrf}=await (await settings.request.get(policyOrigin+'/api/session')).json();
  const invalid=await settings.request.post(endpoint,{headers:{...postOptions.headers,'X-CSRF-Token':csrf},
    data:{ack:'SAVE_ORCHESTRATOR',expected_revision:2,policy:persisted.orchestrator.policy,
      route_changes:{'film.motion':'local_primary'}}});
  if(invalid.status()!==400)throw new Error('API accepted a text model for video');
  const assignedDelete=await settings.request.post(policyOrigin+'/api/model-hub/profile/delete',{
    headers:{Origin:policyOrigin,'X-CSRF-Token':csrf},
    data:{ack:'DELETE_MODEL_PROFILE',expected_revision:2,profile_id:'local_primary'},
  });
  if(assignedDelete.status()!==400)throw new Error('API deleted assigned AI model');
  await settings.getByRole('button',{name:'Đặt lại mặc định'}).click();
  await settings.getByRole('dialog').getByRole('button',{name:'Đặt lại',exact:true}).click();
  await settings.getByText('Mặc định · Phiên bản 3',{exact:true}).waitFor();
  if(await decompose.isChecked()||await dailyLimit.inputValue()!=='10'||await gpuJobs.count())
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
  await modelRow.getByText('Xóa',{exact:true}).click();
  await settings.getByRole('dialog').getByRole('button',{name:'Xác nhận'}).click();
  await settings.getByText('Chưa đăng ký model. Chọn Đăng ký model để bắt đầu.',{exact:true}).waitFor();
  const cleaned=await (await settings.request.get(policyOrigin+'/api/model-hub')).json();
  if(cleaned.profiles.length!==0||cleaned.revision!==4)
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
    await settings.getByText('Chưa xác minh kết nối',{exact:true}).waitFor();
    await settings.getByText('Đã lưu hồ sơ model',{exact:true}).waitFor();
  }
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
