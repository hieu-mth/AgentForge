import test from 'node:test';
import assert from 'node:assert/strict';
import { NAV_GROUPS, DEFAULT_TAB, groupFor, defaultSection,
  tabsFor, parseSection, hashFor, labelFor } from '../src/navigation.js';

const originalScreens=[
  'workspace','overview','goals','tasks','reviews','websites','projects','retention',
  'team','intelligence','growth','schedules','operations','channels','finance','settings','memory','models',
];
test('sidebar contains exactly six business-facing groups',()=>{
  assert.deepEqual(NAV_GROUPS.map(x=>x.label),[
    'Tổng quan','Giao việc','Dự án & Thành phẩm','Kinh doanh','Đội ngũ AI','Cài đặt'
  ]);
});
test('every original screen is present once; no accidental deletion',()=>{
  const leaves=NAV_GROUPS.flatMap(g=>g.tabs.map(([key])=>key));
  assert.equal(leaves.length,originalScreens.length);
  assert.deepEqual([...new Set(leaves)].sort(),[...originalScreens].sort());
});
test('every group selects a real initial tab',()=>{
  for(const group of NAV_GROUPS){
    assert.ok(tabsFor(group.key).some(x=>x.key===defaultSection(group.key)));
  }
});
test('deep links preserve each feature and recover from invalid input',()=>{
  for(const name of originalScreens){
    assert.equal(parseSection(hashFor(name)),name);
    assert.ok(groupFor(name));
    assert.ok(labelFor(name));
  }
  for(const invalid of ['','#/invalid','#/../../data','#/websites?x=1','#/WEBsites','#/']) {
    assert.equal(parseSection(invalid),'overview');
  }
});
test('business and owner tools remain reachable in expected groups',()=>{
  assert.equal(groupFor('websites'),'projects');
  assert.equal(groupFor('reviews'),'projects');
  assert.equal(groupFor('retention'),'projects');
  assert.equal(groupFor('growth'),'business');
  assert.equal(groupFor('finance'),'business');
  assert.equal(groupFor('goals'),'team');
  assert.equal(groupFor('tasks'),'team');
  assert.equal(groupFor('operations'),'settings');
  assert.equal(groupFor('memory'),'settings');
  assert.equal(groupFor('models'),'settings');
  assert.equal(parseSection('#/models'),'models');
  assert.equal(defaultSection('unknown'),'overview');
});

test('overview is the initial landing, while existing deep links stay stable',()=>{
  assert.equal(parseSection(''),'overview');
  assert.equal(parseSection('#/'),'overview');
  assert.equal(parseSection('#/workspace'),'workspace');
  assert.equal(hashFor('overview'),'#/overview');
  assert.equal(NAV_GROUPS[0].key,'overview');
});
