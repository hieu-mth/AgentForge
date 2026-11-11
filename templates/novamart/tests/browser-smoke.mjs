/** Real MS Edge smoke: prove React marketplace does more than render a landing page. */
import { spawn } from 'node:child_process';
import { chromium } from 'playwright-core';
import assert from 'node:assert/strict';
import { setTimeout as sleep } from 'node:timers/promises';

const port=5199, origin='http://127.0.0.1:'+port;
const vite=spawn(process.execPath,['node_modules/vite/bin/vite.js','preview',
  '--host','127.0.0.1','--port',String(port),'--strictPort'],{
  cwd:process.cwd(),stdio:'pipe',windowsHide:true,
});
let browser;
try{
  let ready=false;
  for(let i=0;i<50;i++){
    if(vite.exitCode!==null)throw new Error('Vite preview exited early');
    try{const res=await fetch(origin);if(res.ok){ready=true;break;}}catch{}
    await sleep(300);
  }
  if(!ready)throw new Error('NovaMart preview did not start');
  browser=await chromium.launch({channel:'msedge',headless:true});
  const page=await browser.newPage({viewport:{width:1280,height:900}});
  const errors=[],outside=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',route=>{
    const url=route.request().url();
    if(!url.startsWith(origin+'/')&&url!==origin){
      outside.push(url);return route.abort();
    }
    return route.continue();
  });
  await page.goto(origin,{waitUntil:'networkidle'});
  assert.match(await page.title(),/NovaMart/);
  assert.equal(await page.locator('.product-card').count(),12);
  await page.getByRole('searchbox').fill('Tai nghe');
  assert.equal(await page.locator('.product-card').count(),1);
  const inspectTrigger=page.getByRole('button',{name:'Xem chi tiết Tai nghe không dây Aurora'});
  await inspectTrigger.click();
  const detail=page.getByRole('dialog',{name:/Chi tiết Tai nghe không dây Aurora/});
  await detail.waitFor();
  assert.equal(await detail.getByRole('button',{name:'Đóng chi tiết'}).evaluate(
    el=>el===document.activeElement),true);
  assert.equal(await page.locator('.site-header').evaluate(el=>el.inert),true);
  await page.keyboard.press('Shift+Tab');
  assert.equal(await detail.evaluate(el=>el.contains(document.activeElement)),true);
  await page.keyboard.press('Tab');
  assert.equal(await detail.getByRole('button',{name:'Đóng chi tiết'}).evaluate(
    el=>el===document.activeElement),true);
  await page.keyboard.press('Escape');
  assert.equal(await detail.count(),0);
  assert.equal(await inspectTrigger.evaluate(el=>el===document.activeElement),true);
  await page.getByRole('button',{name:'Thêm Tai nghe không dây Aurora vào giỏ demo'}).click();
  await page.getByRole('button',{name:/Mở giỏ hàng demo/}).click();
  const cart=page.getByRole('dialog',{name:'Giỏ hàng demo'});
  await cart.waitFor();
  assert.equal(await cart.getByRole('button',{name:'Đóng giỏ hàng'}).evaluate(
    el=>el===document.activeElement),true);
  assert.equal(await page.locator('.site-header').evaluate(el=>el.inert),true);
  assert.match(await cart.locator('.cart-total').innerText(),/349.000/);
  await cart.getByRole('button',{name:/Tăng số lượng Tai nghe/}).click();
  assert.match(await cart.locator('.cart-total').innerText(),/698.000/);
  await cart.getByRole('button',{name:/Giảm số lượng Tai nghe/}).click();
  await cart.getByRole('button',{name:'Xóa'}).click();
  assert.match(await cart.locator('.cart-empty').innerText(),/Giỏ hàng đang trống/);
  assert.equal(await cart.getByRole('button',{name:/Thanh toán chưa được hỗ trợ/}).isDisabled(),true);
  await cart.getByRole('button',{name:'Đóng giỏ hàng'}).click();
  assert.equal(await page.getByRole('button',{name:/Mở giỏ hàng demo/}).evaluate(
    el=>el===document.activeElement),true);
  await page.getByRole('searchbox').fill('');
  await page.getByRole('button',{name:'Thể thao'}).first().click();
  assert.equal(await page.locator('.product-card').count(),2);
  await page.setViewportSize({width:375,height:812});
  await page.reload({waitUntil:'networkidle'});
  assert.equal(await page.locator('.product-card').count(),12);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+2),true);
  assert.deepEqual(outside,[]);
  assert.deepEqual(errors,[]);
  console.log('NovaMart Edge interaction smoke: PASS (search/detail/cart/keyboard-focus/filters/mobile/offline)');
}finally{
  if(browser)await browser.close();
  vite.kill();
}
