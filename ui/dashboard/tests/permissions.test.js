import test from 'node:test';
import assert from 'node:assert/strict';
import { PERMISSIONS, requiredPermissions, permissionsKnown, executionConsent } from '../src/permissions.js';

test('every grant has an owner-facing title, effect, and risk level',()=>{
  for (const permission of ['workspace.read','workspace.write','workspace.propose','model.invoke',
    'network.search','network.read','browser.run','process.run']) {
    assert.ok(PERMISSIONS[permission].title);
    assert.ok(PERMISSIONS[permission].description);
    assert.ok(PERMISSIONS[permission].impact);
    assert.ok(['low','medium','high'].includes(PERMISSIONS[permission].risk));
  }
});
test('only requested write/action permissions are presented, once',()=>{
  const plan=[
    {required_permissions:['workspace.read','model.invoke','workspace.propose']},
    {required_permissions:['workspace.propose','workspace.write']},
  ];
  assert.deepEqual(requiredPermissions(plan),['model.invoke','workspace.propose','workspace.write']);
});
test('one explicit tick grants model and required confirmation; no implicit permissions',()=>{
  const required=['model.invoke','workspace.propose'];
  assert.deepEqual(executionConsent(required,[]),{
    grants:[],confirmModel:false,confirmBrowser:false,confirmProcess:false,sensitive:false,
  });
  assert.deepEqual(executionConsent(required,['model.invoke','process.run']),{
    grants:['model.invoke'],confirmModel:true,confirmBrowser:false,confirmProcess:false,sensitive:true,
  });
});
test('browser/process confirmations match selected required permissions only',()=>{
  const selected=executionConsent(['browser.run','process.run'],['browser.run','process.run']);
  assert.equal(selected.confirmBrowser,true);
  assert.equal(selected.confirmProcess,true);
  assert.equal(selected.confirmModel,false);
  assert.deepEqual(selected.grants,['browser.run','process.run']);
});
test('unknown permissions are fail closed, never treated as explained',()=>{
  assert.equal(permissionsKnown(['workspace.write']),true);
  assert.equal(permissionsKnown(['workspace.write','admin.root']),false);
});
