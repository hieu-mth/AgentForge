import test from 'node:test';
import assert from 'node:assert/strict';
import { PRODUCTS } from '../src/catalog.js';
import { cartTotals, changeCart, currency, listProducts, removeFromCart } from '../src/store.js';

test('search and category filters work together without mutating source',()=>{
  const baseline=[...PRODUCTS];
  const found=listProducts(PRODUCTS,{search:'Tai nghe'});
  assert.equal(found.length,1);
  assert.equal(found[0].id,'p001');
  assert.equal(listProducts(PRODUCTS,{search:'zzzz'}) .length,0);
  assert.equal(listProducts(PRODUCTS,{category:'sports'}).length,2);
  assert.equal(listProducts(PRODUCTS,{category:'electronics',search:'Đèn'}).length,1);
  assert.deepEqual(PRODUCTS,baseline);
});

test('price sorting uses actual numeric price and stable IDs',()=>{
  const ascending=listProducts(PRODUCTS,{sort:'price-asc'});
  const descending=listProducts(PRODUCTS,{sort:'price-desc'});
  assert.equal(ascending[0].price,150000);
  assert.equal(descending[0].price,590000);
  assert.deepEqual(ascending.map(x=>x.id).reverse(),descending.map(x=>x.id));
  assert.ok(currency(345000).includes('345.000'));
});

test('cart increments, decrements, removes and never becomes negative',()=>{
  const ids=new Set(PRODUCTS.map(x=>x.id));
  const one=changeCart({},'p001',1,ids);
  assert.deepEqual(one,{p001:1});
  const two=changeCart(one,'p001',1,ids);
  assert.equal(two.p001,2);
  assert.equal(cartTotals(two,PRODUCTS).total,698000);
  assert.equal(cartTotals(two,PRODUCTS).items,2);
  const step=changeCart(two,'p001',-1,ids);
  assert.equal(step.p001,1);
  assert.deepEqual(changeCart(step,'p001',-1,ids),{});
  assert.deepEqual(changeCart({},'p001',-1,ids),{});
  assert.deepEqual(removeFromCart(two,'p001'),{});
});

test('cart refuses unknown products, large increments and abuse',()=>{
  const ids=new Set(PRODUCTS.map(x=>x.id));
  assert.deepEqual(changeCart({},'../secrets',1,ids),{});
  assert.deepEqual(changeCart({},'p001',101,ids),{});
  assert.deepEqual(changeCart({},'p001',1.5,ids),{});
  assert.deepEqual(cartTotals({p001:999,p002:-2},PRODUCTS),{items:0,total:0});
  let cart={};
  for(let i=0;i<120;i++)cart=changeCart(cart,'p001',1,ids);
  assert.equal(cart.p001,99);
});

test('all reference products are bounded with unique IDs and demo copy',()=>{
  assert.equal(new Set(PRODUCTS.map(x=>x.id)).size,PRODUCTS.length);
  for(const p of PRODUCTS){
    assert.match(p.id,/^p\d{3}$/);
    assert.ok(p.name.length>6 && p.name.length<=80);
    assert.ok(p.price>0 && p.price<100000000);
    assert.ok(p.description.includes('demo')||p.description.includes('mẫu')||p.description.includes('minh họa')||p.description.includes('giả lập')||p.description.includes('mô phỏng'));
  }
});
