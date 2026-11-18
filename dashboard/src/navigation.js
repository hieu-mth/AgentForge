// Video-first Owner navigation. Legacy feature APIs are not removed here;
// backend dependency cleanup must be verified independently.
export const NAV_GROUPS = Object.freeze([
  {key:'overview',label:'Tổng quan',tabs:[['overview','Tổng quan']]},
  {key:'studio',label:'Studio video',tabs:[['media-studio','Sản xuất video']]},
  {key:'characters',label:'Nhân vật',tabs:[['characters','Thư viện nhân vật']]},
  {key:'products',label:'Thành phẩm',tabs:[
    ['projects','Kho tài nguyên & thành phẩm'],['reviews','Duyệt video']]},
  {key:'business',label:'Phân phối',tabs:[['channels','Kênh phân phối']]},
  {key:'settings',label:'Cài đặt',tabs:[
    ['settings','Cấu hình'],['environment','Môi trường & Tài nguyên'],
    ['models','Model AI & Điều phối'],['operations','Vận hành'],
    ['retention','Sao lưu & Dọn dẹp']]},
]);
export const DEFAULT_TAB = Object.freeze({
  overview:'overview',studio:'media-studio',characters:'characters',
  products:'projects',business:'channels',settings:'settings',
});
const ROUTES = Object.fromEntries(NAV_GROUPS.flatMap(group=>
  group.tabs.map(([key,label])=>[key,{group:group.key,label}])
));
export function groupFor(section) {
  return ROUTES[section]?.group || 'overview';
}
export function labelFor(section) {
  return ROUTES[section]?.label || 'Tổng quan';
}
export function defaultSection(group) {
  return DEFAULT_TAB[group] || 'overview';
}
export function tabsFor(group) {
  return (NAV_GROUPS.find(x=>x.key===group)?.tabs || []).map(([key,label])=>({key,label}));
}
export function parseSection(hash) {
  const match = /^#\/?([a-z][a-z0-9-]*)$/.exec(hash || '');
  return match && ROUTES[match[1]] ? match[1] : 'overview';
}
export function hashFor(section) {
  return '#/'+(ROUTES[section] ? section : 'overview');
}
