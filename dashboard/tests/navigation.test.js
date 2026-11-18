import test from 'node:test';
import assert from 'node:assert/strict';
import { NAV_GROUPS, groupFor, defaultSection, tabsFor, parseSection, hashFor, labelFor } from '../src/navigation.js';

const videoScreens = [
  'overview','media-studio','characters','projects','reviews','channels',
  'environment','models',
];
const retiredScreens = ['websites','workspace','mattress','growth','finance','team','goals','tasks','intelligence','memory','schedules'];

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
  assert.equal(groupFor('reviews'),'products');
  assert.equal(groupFor('channels'),'business');
  assert.equal(groupFor('models'),'settings');
  assert.equal(groupFor('models'),'settings');
  assert.equal(parseSection(''),'overview');
});
