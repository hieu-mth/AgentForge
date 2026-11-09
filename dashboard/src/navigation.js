// A single declarative route map: six sidebar destinations; 17 original screens + Model Hub.
// No API permissions are changed by client-side navigation.
export const NAV_GROUPS = Object.freeze([
  {key:'overview',label:'Tổng quan',tabs:[['overview','Tổng quan']]},
  {key:'workspace',label:'Giao việc',tabs:[['workspace','Giao việc']]},
  {key:'projects',label:'Dự án & Thành phẩm',tabs:[
    ['websites','Websites'],['projects','Kho thành phẩm & Ảnh AI'],
    ['reviews','Duyệt AI & Video'],['retention','Sao lưu & Cleanup']]},
  {key:'business',label:'Kinh doanh',tabs:[
    ['growth','Growth & Revenue'],['finance','Finance'],
    ['channels','Channels'],['intelligence','Intelligence']]},
  {key:'team',label:'Đội ngũ AI',tabs:[
    ['team','Team & Roles'],['goals','Kế hoạch & Duyệt'],['tasks','Task History']]},
  {key:'settings',label:'Cài đặt',tabs:[
    ['settings','Cấu hình'],['models','AI Models & Routing'],['schedules','Lịch chạy'],
    ['operations','Vận hành'],['memory','Owner Memory']]},
]);
export const DEFAULT_TAB = Object.freeze({
  overview:'overview',workspace:'workspace',projects:'websites',
  business:'growth',team:'team',settings:'settings',
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
  // A previously bookmarked page remains valid; unknown paths fail closed to Workspace.
  const match = /^#\/?([a-z][a-z0-9-]*)$/.exec(hash || '');
  return match && ROUTES[match[1]] ? match[1] : 'overview';
}
export function hashFor(section) {
  return '#/'+(ROUTES[section] ? section : 'overview');
}
