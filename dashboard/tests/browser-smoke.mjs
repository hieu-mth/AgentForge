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
  await page2.route('**/api/**',route=>{
    const p=new URL(route.request().url()).pathname;
    if(p==='/api/ops/discovery')environmentRequests++;
    const payload=p==='/api/session'?{csrf:'fixture-only-csrf'}:
      p==='/api/video-studio/projects'?{projects:projectRows,canonical_engine:'film_studio'}:
      p==='/api/characters'?{characters:[]}:
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
  await page2.getByRole('button',{name:'Xem bản dựng'}).click();
  await page2.getByText('Film Studio · Continuity & Dựng phim',{exact:true}).waitFor();
  await page2.getByRole('button',{name:'Mở model & cấu hình'}).click();
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
  await overview.getByText('Chưa tìm thấy tập phim trong workspace',{exact:true}).waitFor();
  await overview.getByRole('button',{name:'Mở Video Studio'}).click();
  await page2.waitForURL('**/#/media-studio');
  projectRows=[
    {project_id:'film:demo:ep01',film_slug:'demo',episode_id:'ep01',state:'PREPARED_NOT_RENDERED'},
    {project_id:'film:demo:ep02',film_slug:'demo',episode_id:'ep02',state:'RENDER_RECEIPT_PRESENT_UNINSPECTED'},
    {project_id:'film:demo:ep03',film_slug:'demo',episode_id:'ep03',state:'INVALID_NEEDS_OWNER_REVIEW'},
  ];
  await page2.setViewportSize({width:390,height:850});
  await page2.goto(origin+'/dashboard/#/overview',{waitUntil:'networkidle'});
  await overview.getByText('Cần Owner xem bản dựng',{exact:true}).waitFor();
  await overview.getByText('Cần kiểm tra hồ sơ tập',{exact:true}).waitFor();
  if((await overview.locator('.env-stat-value').allTextContents()).join(',')!=='3,1,1')
    throw new Error('Overview counters do not match project states');
  const overviewOverflow=await overview.locator('.ant-table-content').evaluate(
    table=>table.scrollWidth>table.clientWidth+2);
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
    'import sys', 'from pathlib import Path',
    'from agentforge.ai import model_hub', 'from agentforge.api.server import create_server',
    'model_hub.DB_PATH = Path(sys.argv[1])',
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
  await openOptions.filter({hasText:/^ComfyUI$/}).click();
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
