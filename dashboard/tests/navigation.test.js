import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import { NAV_GROUPS, groupFor, defaultSection, tabsFor, parseSection, hashFor, labelFor } from '../src/navigation.js';

const videoScreens = [
  'overview','media-studio','characters','projects','channels',
  'environment','models','orchestrator',
];
const retiredScreens = ['websites','workspace','mattress','growth','finance','team','goals','tasks','intelligence','memory','schedules','reviews'];

test('navigation exposes only video studio workflows and operational settings',()=>{
  assert.deepEqual(NAV_GROUPS.map(x=>x.label),[
    'Tổng quan','Studio video','Nhân vật','Thành phẩm','Phân phối','Cài đặt',
  ]);
  const leaves=NAV_GROUPS.flatMap(g=>g.tabs.map(([key])=>key));
  assert.deepEqual([...leaves].sort(),[...videoScreens].sort());
  assert.equal(new Set(leaves).size,leaves.length);
});

test('each group has a real initial tab',()=>{
  for(const group of NAV_GROUPS)
    assert.ok(tabsFor(group.key).some(x=>x.key===defaultSection(group.key)));
  assert.equal(defaultSection('products'),'projects');
  assert.equal(defaultSection('business'),'channels');
});

test('video-first deep links work, retired links fail closed',()=>{
  for(const name of videoScreens){
    assert.equal(parseSection(hashFor(name)),name);
    assert.ok(groupFor(name));
    assert.ok(labelFor(name));
  }
  for(const name of retiredScreens){
    assert.equal(parseSection('#/'+name),'overview');
    assert.equal(hashFor(name),'#/overview');
  }
  for(const invalid of ['','#/invalid','#/../../data','#/websites?x=1','#/WEBsites','#/'])
    assert.equal(parseSection(invalid),'overview');
});

test('studio and settings remain reachable',()=>{
  assert.equal(groupFor('media-studio'),'studio');
  assert.equal(groupFor('characters'),'characters');
  assert.equal(groupFor('channels'),'business');
  assert.equal(groupFor('models'),'settings');
  assert.equal(parseSection(''),'overview');
});

test('current video shell has no retired UI styles',()=>{
  const css=readFileSync(new URL('../src/styles.css',import.meta.url),'utf8');
  assert.match(css,/\.app-shell\{/);
  assert.match(css,/\.status-pill\{/);
  for(const obsolete of ['workspace-owner','goal-owner','prompt-composer','visual-picker','overview-chart'])
    assert.equal(css.includes('.'+obsolete),false,obsolete);
});
import { productionElapsed,productionProgress } from '../src/features/studioProgress.js';

test('elapsed time excludes gaps between attempts and old review timestamps',()=>{
  const job={started_at:'2026-11-21T19:17:59Z',updated_at:'2026-11-23T07:35:22Z',
    resources:[{before:{checked_at:'2026-11-23T07:30:29Z'},after:{checked_at:'2026-11-23T07:35:22Z'}}]};
  assert.equal(productionElapsed(job,false),'Bước gần nhất · 4 phút 53 giây');
  job.attempt_started_at='2026-11-23T07:30:29Z';
  assert.equal(productionElapsed(job,true,Date.parse('2026-11-23T07:30:35Z')),'6 giây');
  job.attempt_finished_at='2026-11-23T07:35:22Z';
  assert.equal(productionElapsed(job,false),'4 phút 53 giây');
});

test('production progress reflects persisted checkpoints and verified output',()=>{
  assert.equal(productionProgress().percent,0);
  const job={status:'RUNNING',stage:'IMAGES',brief:{mode:'motion',scene_count:2},storyboard_version:1,
    board:{scenes:[{asset:'png'},{}]}};
  const images=productionProgress(job);
  assert.equal(images.images,1);
  assert.equal(images.clips,0);
  const resumed=productionProgress(JSON.parse(JSON.stringify(job)));
  assert.equal(resumed.percent,images.percent);
  job.stage='MOTION';
  job.status='WAITING_RESOURCES';
  assert.equal(productionProgress(job).stages.find(s=>s.key==='MOTION').state,'waiting');
  job.status='FAILED';
  assert.equal(productionProgress(job).stages.find(s=>s.key==='MOTION').state,'error');
  job.stage='VERIFY';
  job.status='REVIEW';
  job.video_sha='video';
  assert.ok(productionProgress(job).percent<100);
  job.receipt_sha='receipt';
  assert.equal(productionProgress(job).percent,100);
});
