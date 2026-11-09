import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {acceptedCount, acceptanceLabel, canAccept} from '../src/acceptance.js';

test('execution success is never counted as product acceptance',()=>{
  assert.equal(acceptedCount([{status:'SUCCEEDED'},
    {status:'SUCCEEDED',artifact_acceptance:{status:'NEEDS_REVISION'}},
    {status:'SUCCEEDED',artifact_acceptance:{status:'ACCEPTED'}}]),1);
  assert.equal(canAccept({status:'SUCCEEDED',missing_checks:[]}),false);
  assert.equal(canAccept({status:'NEEDS_VALIDATION',missing_checks:['BUILD_VALID']}),false);
  assert.equal(canAccept({status:'READY_FOR_REVIEW',missing_checks:[]}),true);
});
test('all artifact states have distinct Owner labels and UI exposes both statuses',()=>{
  assert.notEqual(acceptanceLabel('NEEDS_REVISION'),acceptanceLabel('NEEDS_VALIDATION'));
  const workspace=readFileSync(new URL('../src/features/Workspace.jsx',import.meta.url),'utf8');
  assert.match(workspace,/badge\(g.status\)/);
  assert.match(workspace,/acceptanceLabel\(g.artifact_acceptance.status\)/);
  const shared=readFileSync(new URL('../src/components/shared.jsx',import.meta.url),'utf8');
  assert.doesNotMatch(shared,/const GOOD = \['SUCCEEDED'/);
});
