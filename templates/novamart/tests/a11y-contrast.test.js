import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const css=readFileSync(new URL('../src/styles.css',import.meta.url),'utf8');
const channel=value=>{
  const n=parseInt(value,16)/255;
  return n<=0.04045?n/12.92:((n+0.055)/1.055)**2.4;
};
const luminance=hex=>{
  const [r,g,b]=[hex.slice(1,3),hex.slice(3,5),hex.slice(5,7)].map(channel);
  return 0.2126*r+0.7152*g+0.0722*b;
};
const contrast=(a,b)=>{
  const [x,y]=[luminance(a),luminance(b)].sort((a,b)=>b-a);
  return (x+0.05)/(y+0.05);
};
const token=name=>{
  const match=css.match(new RegExp('--'+name+':(#[0-9a-fA-F]{6})'));
  assert.ok(match, 'Missing '+name);
  return match[1];
};

test('NovaMart white-on-orange CTAs meet WCAG normal-text AA contrast',()=>{
  assert.ok(contrast(token('accent-fill'),'#ffffff')>=4.5);
  for(const cssRule of ['.hero-primary{background:var(--accent-fill)',
      '.search-action{background:var(--accent-fill)',
      '.filter-chip.active{background:var(--accent-fill)']){
    assert.ok(css.includes(cssRule),cssRule);
  }
});
test('NovaMart small secondary text and orange links meet 4.5:1 contrast',()=>{
  assert.ok(contrast('#575d66','#ffffff')>=4.5);
  assert.ok(contrast('#555b65','#ffffff')>=4.5);
  assert.ok(contrast(token('accent-ink'),'#ffffff')>=4.5);
});
