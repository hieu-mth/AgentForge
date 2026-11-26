// Measure the actual Vite entry graph, excluding on-demand route chunks.
import assert from 'node:assert/strict';
import {readFileSync,statSync} from 'node:fs';
import {join} from 'node:path';

const manifest=JSON.parse(readFileSync('dist/.vite/manifest.json','utf8'));
const entries=Object.keys(manifest).filter(key=>manifest[key].isEntry);
assert.equal(entries.length,1,'Dashboard must have one HTML entry');
const visited=new Set();
function visit(key){
  if(visited.has(key))return;
  assert.ok(manifest[key],'Missing manifest import: '+key);
  visited.add(key);
  for(const dependency of manifest[key].imports??[])visit(dependency);
}
visit(entries[0]);
const files=new Set([...visited].map(key=>manifest[key].file).filter(file=>file.endsWith('.js')));
const bytes=[...files].reduce((sum,file)=>sum+statSync(join('dist',file)).size,0);
for(const name of ['MediaStudio','CharacterLibrary','Projects','Models','Orchestrator','Environment','Publishing','Overview']){
  const key='src/features/'+name+'.jsx';
  assert.equal(manifest[key]?.isDynamicEntry,true,'Missing on-demand screen: '+name);
  assert.ok(!visited.has(key),'Screen eagerly loaded: '+name);
}
console.log('Dashboard initial JS: '+bytes+' bytes across '+files.size+' assets');
console.log('All 8 screens load on demand; baseline initial JS: 1355410 bytes');
assert.ok(bytes<1355410,'Initial JS did not improve over the audited baseline');
