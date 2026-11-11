// Production UI against synthetic HTTP responses only. No Owner backend or GPU.
import assert from 'node:assert/strict';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright-core';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const output=process.env.UI1A_EVIDENCE_DIR||fs.mkdtempSync(path.join(os.tmpdir(),'agentforge-ui1a-browser-'));
fs.mkdirSync(output,{recursive:true});
const server=http.createServer((req,res)=>{
  const route=new URL(req.url,'http://localhost').pathname;
  const target=path.resolve(root,'dist',route.replace(/^\/dashboard\/?/,'')||'index.html');
  if(!target.startsWith(path.join(root,'dist')+path.sep)||!fs.existsSync(target)||!fs.statSync(target).isFile()){
    res.writeHead(404);return res.end();
  }
  res.setHeader('Content-Type',target.endsWith('.js')?'text/javascript':target.endsWith('.css')?'text/css':'text/html');
  res.end(fs.readFileSync(target));
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const origin=`http://127.0.0.1:${server.address().port}/dashboard/`;
const id='a'.repeat(32), sha='b'.repeat(64);
const goal={goal_id:id,title:'Synthetic reliability plan',status:'PLANNED',template:'website.draft',
  plan_sha256:sha,current_step:0,plan:[],step_runs:[]};
const bootstrap={goals:[],tasks:[],skills:[],datasets:[],growth:[],schedules:[],templates:{},
  workspace_policy:{max_estimated_model_calls:3,website_enabled:true,storyboard_enabled:true}};
const hub={revision:0,profiles:[
  {id:'local_one',provider:'ollama',model:'synthetic:1',enabled:true},
  {id:'local_two',provider:'ollama',model:'synthetic:2',enabled:true}],
  routes:[{id:'web.create',label:'Tạo Website',kind:'text',model_ref:'local_one',runtime_wired:true,status:'ROUTED'}]};
const fixtures={'/api/session':{csrf:'synthetic-only'},'/api/bootstrap':bootstrap,
  '/api/artifacts':{items:[{kind:'website',id:'synthetic-product',status:'LOCAL_FILES_ONLY',bytes:128}],total_items:1},
  '/api/image/health':{status:'UNAVAILABLE',checkpoints:[]},'/api/image/jobs':{jobs:[]},
  '/api/model-hub':hub,'/api/film/motion':{jobs:[]},'/api/film/productions':{episodes:[]},
  '/api/mattress':{leads:[],notices:[],summary:{}},'/api/retention/inventory':{items:[]},
  '/api/retention/backups':{items:[]},'/api/memory':[], '/api/publishing':{releases:[]},
  '/api/ops/preflight':{checks:[]},'/api/ops/health':{},'/api/ops/acceptance':{},
  ['/api/goals/'+id]:goal};
const results=[], errors=[];
let browser;
try {
  browser=await chromium.launch({channel:'msedge',headless:true});
  async function scenario(name,run){
    const page=await browser.newPage({viewport:{width:1366,height:900}});
    const requests=[];const state={status:{},overrides:{},post:()=>({}),handlers:{}};
    page.on('pageerror',e=>errors.push({name,message:e.message}));
    await page.route('**/api/**',async route=>{
      const request=route.request(), p=new URL(request.url()).pathname;
      requests.push({method:request.method(),path:p});
      if(state.handlers[p])return state.handlers[p](route);
      if(request.method()==='POST')return route.fulfill({status:200,json:state.post(p,request.postDataJSON())});
      const status=state.status[p]||200;
      return route.fulfill({status,json:status===200?(state.overrides[p]??fixtures[p]??{}):{error:'synthetic_'+status}});
    });
    const open=async tab=>{await page.goto(origin+'#/'+tab);await page.reload({waitUntil:'networkidle'});};
    const header=()=>page.locator('.app-header').getByRole('button',{name:'Làm mới',exact:true});
    try{await run({page,state,requests,open,header});results.push({name,status:'PASS'});console.log('PASS '+name);}
    catch(error){await page.screenshot({path:path.join(output,'failure-'+results.length+'.png')});throw new Error(name+': '+error.message);}
    finally{await page.close();}
  }
  await scenario('bootstrap 503 / offline -> GET-only recovery',async({page,state,requests,open})=>{
    state.status['/api/bootstrap']=503;await open('overview');
    await page.getByRole('button',{name:'Thử kết nối lại'}).waitFor();
    assert.equal(await page.locator('.loading-screen .ant-spin').count(),0);
    state.status['/api/bootstrap']=200;await page.getByRole('button',{name:'Thử kết nối lại'}).click();
    await page.locator('.app-shell').waitFor();
    assert.ok(requests.every(r=>r.method==='GET'));
  });
  await scenario('offline bootstrap recovers without browser reload or POST',async({page,state,requests,open})=>{
    state.handlers['/api/bootstrap']=route=>route.abort('connectionrefused');
    await open('overview');await page.getByRole('button',{name:'Thử kết nối lại'}).waitFor();
    await page.getByText(/Không kết nối được backend local/).waitFor();
    delete state.handlers['/api/bootstrap'];await page.getByRole('button',{name:'Thử kết nối lại'}).click();
    await page.locator('.app-shell').waitFor();assert.ok(requests.every(r=>r.method==='GET'));
  });
  await scenario('stalled GET reaches terminal timeout instead of infinite spinner',async({page,state,open})=>{
    state.handlers['/api/image/health']=route=>new Promise(resolve=>{
      setTimeout(()=>route.fulfill({status:200,json:{status:'UNAVAILABLE',checkpoints:[]}}).catch(()=>{}).finally(resolve),16000);
    });
    await open('projects');await page.getByText('synthetic-product',{exact:true}).waitFor();
    await page.getByText(/Đọc dữ liệu quá thời gian chờ/).waitFor({timeout:20000});
    assert.ok(await page.getByRole('button',{name:'Thử lại kết nối ảnh'}).isVisible());
  });
  await scenario('artifacts survive health/jobs 503; retry only failed resource',async({page,state,requests,open})=>{
    state.status['/api/image/health']=503;state.status['/api/image/jobs']=503;
    await open('projects');await page.getByText('synthetic-product',{exact:true}).waitFor();
    const before=requests.length;state.status['/api/image/health']=200;
    await page.getByRole('button',{name:'Thử lại kết nối ảnh'}).click();
    await page.getByRole('button',{name:'Thử lại kết nối ảnh'}).waitFor({state:'detached'});
    assert.deepEqual(requests.slice(before),[{method:'GET',path:'/api/image/health'}]);
    assert.ok(await page.getByRole('button',{name:'Thử lại lịch sử ảnh'}).isVisible());
    await page.screenshot({path:path.join(output,'projects-degraded.png'),fullPage:true});
  });
  await scenario('403 is terminal permission error, never login',async({page,state,open})=>{
    state.status['/api/artifacts']=403;await open('projects');
    await page.getByText(/Không có quyền truy cập \(403\)/).waitFor();
    assert.equal(await page.locator('.login-screen').count(),0);
    assert.equal(await page.locator('.ant-table-wrapper .ant-spin-spinning').count(),0);
  });
  for(const [screen,endpoint] of [['projects','/api/artifacts'],['models','/api/model-hub'],
    ['mattress','/api/mattress'],['retention','/api/retention/inventory'],
    ['channels','/api/publishing'],['memory','/api/memory'],['operations','/api/ops/health']]){
    await scenario(screen+' subresource 401 -> login, Owner UI hidden',async({page,state,open})=>{
      state.status[endpoint]=401;await open(screen);await page.locator('.login-screen').waitFor();
      assert.equal(await page.locator('.app-shell').count(),0);
      assert.equal(await page.getByText('synthetic-product',{exact:true}).count(),0);
      const storage=await page.evaluate(()=>({...localStorage}));
      assert.ok(Object.keys(storage).every(key=>key==='agentforge.theme'));
    });
  }
  await scenario('Models Header reloads resources, preserves unsaved route, coalesces fast refresh',async({page,state,requests,open,header})=>{
    await open('models');
    const route=page.locator('.ant-card').filter({has:page.getByText('Task Routing',{exact:true})}).locator('.ant-select').first();
    await route.click();await page.getByText('local_two · ollama',{exact:true}).click();
    state.overrides['/api/model-hub']={...hub,revision:9};
    const before=requests.length;
    await header().evaluate(button=>{button.click();button.click();button.click();});
    await page.getByText('Revision 9',{exact:true}).waitFor();
    assert.ok((await route.innerText()).includes('local_two'));
    assert.equal(requests.slice(before).filter(r=>r.path==='/api/model-hub').length,1);
    assert.equal(requests.slice(before).filter(r=>r.path==='/api/artifacts').length,0);
    // A route save returns its own new hub snapshot. No extra bootstrap/GET replay.
    state.post=()=>({...hub,revision:10});const mutationStart=requests.length;
    await page.getByRole('button',{name:'Lưu route',exact:true}).click();
    await page.getByRole('button',{name:'Xác nhận',exact:true}).click();
    await page.getByText('Revision 10',{exact:true}).waitFor();
    assert.deepEqual(requests.slice(mutationStart).map(r=>r.method),['POST']);
  });
  await scenario('Header refresh preserves unsaved settings form',async({page,open,header})=>{
    await open('settings');const field=page.getByRole('spinbutton').first();await field.fill('2');
    await header().click();await page.waitForTimeout(200);assert.equal(await field.inputValue(),'2');
  });
  await scenario('old artifacts GET arriving last cannot overwrite new snapshot',async({page,state,open,header})=>{
    await open('projects');let release;let calls=0;
    state.handlers['/api/artifacts']=route=>{
      calls++;
      if(calls===1)return new Promise(resolve=>{release=()=>route.fulfill({status:200,json:{items:[{kind:'website',id:'old-synthetic',bytes:1}],total_items:1}}).then(resolve);});
      return route.fulfill({status:200,json:{items:[{kind:'website',id:'new-synthetic',bytes:1}],total_items:1}});
    };
    await page.locator('.ant-card').first().getByRole('button',{name:/Làm mới/}).click();
    await page.waitForFunction(()=>!!document.querySelector('.ant-table-wrapper .ant-spin-spinning'));
    await header().click();await page.getByText('new-synthetic',{exact:true}).waitFor();
    await release();await page.waitForTimeout(150);
    assert.equal(await page.getByText('old-synthetic',{exact:true}).count(),0);
  });
  await scenario('committed POST survives failed refresh with exactly one POST',async({page,state,requests,open})=>{
    await open('workspace');state.post=()=>{state.status['/api/bootstrap']=503;return {status:'PLAN_CREATED',goal_id:id};};
    await page.getByRole('textbox',{name:'Mô tả công việc'}).fill('Tạo website synthetic kiểm tra receipt');
    await page.getByRole('button',{name:/Tạo kế hoạch/}).click();await page.getByRole('dialog').waitFor();
    await page.getByText(/Thao tác đã thành công nhưng chưa làm mới/).waitFor();
    assert.equal(requests.filter(r=>r.method==='POST').length,1);
    assert.ok(await page.getByText('Synthetic reliability plan',{exact:true}).isVisible());
  });
  await scenario('Unicode boundaries have no silent truncation',async({page,open})=>{
    await open('workspace');const field=page.getByRole('textbox',{name:'Mô tả công việc'});
    await field.fill('😀'.repeat(6000));assert.equal([...(await field.inputValue())].length,6000);
    await field.fill('a'.repeat(6001));assert.equal((await field.inputValue()).length,6001);
    assert.ok(await page.getByRole('button',{name:/Tạo kế hoạch/}).isDisabled());
  });
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({status:'PASS',scenarios:results,evidence:output},null,2));
} finally {
  fs.writeFileSync(path.join(output,'results.json'),JSON.stringify({results,errors},null,2));
  if(browser)await browser.close();await new Promise(resolve=>server.close(resolve));
}
