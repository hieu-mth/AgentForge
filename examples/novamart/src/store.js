/** Pure, unit-testable commerce interaction primitives. No payment or network. */
export const currency = value => new Intl.NumberFormat('vi-VN',{
  style:'currency',currency:'VND',maximumFractionDigits:0,
}).format(value);

export function listProducts(products, {search='',category='all',sort='featured'}={}) {
  const query=String(search).trim().toLocaleLowerCase('vi-VN');
  const subset=products.filter(product=>
    (category==='all'||product.category===category) &&
    product.name.toLocaleLowerCase('vi-VN').includes(query));
  if(sort==='price-asc')return [...subset].sort((a,b)=>a.price-b.price||a.id.localeCompare(b.id));
  if(sort==='price-desc')return [...subset].sort((a,b)=>b.price-a.price||a.id.localeCompare(b.id));
  return subset;
}

export function changeCart(cart,id,delta,knownIds) {
  if(!knownIds.has(id)||!Number.isInteger(delta)||Math.abs(delta)!==1)return cart;
  const current=cart[id]||0;
  const next=Math.max(0,Math.min(99,current+delta));
  const result={...cart};
  if(next===0)delete result[id];
  else result[id]=next;
  return result;
}

export function removeFromCart(cart,id) {
  if(!Object.hasOwn(cart,id))return cart;
  const result={...cart};delete result[id];return result;
}

export function cartTotals(cart,products) {
  return products.reduce((acc,product)=>{
    const count=cart[product.id]||0;
    if(!Number.isInteger(count)||count<0||count>99)return acc;
    return {items:acc.items+count,total:acc.total+product.price*count};
  },{items:0,total:0});
}
