import test from 'node:test';
import assert from 'node:assert/strict';
import {parseSection, hashFor, groupFor} from '../src/navigation.js';
test('video project navigation and retired workspace',()=>{
  assert.equal(parseSection('#/projects'),'projects');
  assert.equal(groupFor('projects'),'products');
  assert.equal(parseSection('#/workspace'),'overview');
  assert.equal(hashFor('workspace'),'#/overview');
});
