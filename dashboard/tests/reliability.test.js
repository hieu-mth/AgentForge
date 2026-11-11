import test from 'node:test';
import assert from 'node:assert/strict';
import {api, onAuthExpired, requestError} from '../src/api.js';
import {promptValidation} from '../src/prompt_validation.js';

test('Unicode code points match Python and byte budget is never silently truncated',()=>{
  assert.equal(promptValidation('😀'.repeat(20)).characters,20);
  assert.equal(promptValidation('😀'.repeat(20)).bytes,80);
  assert.equal(promptValidation('  '+'ệ'.repeat(20)+'  ').characters,20);
  assert.equal(promptValidation('a'.repeat(6000)).error,null);
  assert.match(promptValidation('a'.repeat(6001)).error,/6.000/);
  assert.ok(promptValidation('short').error);
  assert.ok(promptValidation('Tạo website nội dung\u0000 không hợp lệ').error);
});

test('401 is global, 403 is not auth expiry, and stale GET cannot resurrect Owner data',async()=>{
  const original=globalThis.fetch;
  let expired=0, finish;
  const unsubscribe=onAuthExpired(()=>expired++);
  try {
    globalThis.fetch=async path=>path==='/api/slow'
      ?new Promise(resolve=>{finish=()=>resolve(Response.json({private:'synthetic'}));})
      :Response.json({error:'denied'},{status:path==='/api/expired'?401:403});
    const slow=api('/api/slow').catch(error=>error);
    await assert.rejects(api('/api/forbidden'),error=>error.status===403);
    assert.equal(expired,0);
    await assert.rejects(api('/api/expired'),error=>error.status===401);
    assert.equal(expired,1);
    finish();
    assert.equal((await slow).status,401);
    assert.match(requestError({status:403}),/403/);
    assert.match(requestError({status:503}),/503/);
  } finally {unsubscribe();globalThis.fetch=original;}
});

test('GET timeout/offline are explicit and no mutation is retried',async()=>{
  const original=globalThis.fetch;
  let posts=0;
  try {
    globalThis.fetch=(_path,options)=>new Promise((_resolve,reject)=>
      options.signal.addEventListener('abort',()=>reject(new DOMException('aborted','AbortError'))));
    await assert.rejects(api('/api/slow',{timeoutMs:5}),error=>error.code==='GET_TIMEOUT');
    globalThis.fetch=async(_path,options)=>{if(options.method==='POST')posts++;throw new TypeError('offline');};
    await assert.rejects(api('/api/action',{method:'POST',body:{ack:'SYNTHETIC'}}),error=>error.code==='NETWORK_UNAVAILABLE');
    assert.equal(posts,1);
  } finally {globalThis.fetch=original;}
});

test('GET timeout includes a stalled body and a 401 expires before reading its body',async()=>{
  const original=globalThis.fetch;
  let expired=0;
  const unsubscribe=onAuthExpired(()=>expired++);
  try {
    globalThis.fetch=async(_path,options)=>({status:401,ok:false,json:()=>new Promise((_resolve,reject)=>
      options.signal.addEventListener('abort',()=>reject(new DOMException('aborted','AbortError'))))});
    await assert.rejects(api('/api/stalled-body',{timeoutMs:5}),error=>error.code==='GET_TIMEOUT');
    assert.equal(expired,1);
  } finally {globalThis.fetch=original;unsubscribe();}
});

test('HTML fallback with HTTP 200 is a terminal API error, not a connected dashboard',async()=>{
  const original=globalThis.fetch;
  try {
    globalThis.fetch=async()=>new Response('<html>synthetic fallback</html>',{status:200});
    await assert.rejects(api('/api/bootstrap'),error=>error.code==='INVALID_API_RESPONSE');
  } finally {globalThis.fetch=original;}
});
