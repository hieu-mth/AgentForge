// Only implemented Video Studio sections are routable.
export const NAV_GROUPS = Object.freeze([
  {key:'overview',label:'Tổng quan',tabs:[['overview','Tổng quan']]},
  {key:'studio',label:'Studio video',tabs:[['media-studio','Sản xuất video']]},
  {key:'characters',label:'Nhân vật',tabs:[['characters','Thư viện nhân vật']]},
  {key:'products',label:'Thành phẩm',tabs:[['projects','Dự án video']]},
  {key:'business',label:'Phân phối',tabs:[['channels','Kênh xuất bản']]},
  {key:'settings',label:'Cài đặt',tabs:[
    ['models','Model AI'],['orchestrator','AI điều phối tác vụ'],['environment','Môi trường & Tài nguyên']]},
]);
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
  return NAV_GROUPS.find(item=>item.key===group)?.tabs[0]?.[0] || 'overview';
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
