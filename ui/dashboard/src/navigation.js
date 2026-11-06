// A single declarative route map: six sidebar destinations, all 17 features preserved.
// No API permissions are changed by client-side navigation.
export const NAV_GROUPS = Object.freeze([
  {key:'workspace',label:'Giao việc',tabs:[['workspace','Giao việc']]},
  {key:'overview',label:'Tổng quan',tabs:[['overview','Tổng quan']]},
  {key:'projects',label:'Dự án & Thành phẩm',tabs:[
    ['websites','Websites'],['projects','Kho thành phẩm & Ảnh AI'],
    ['reviews','Duyệt AI & Video'],['retention','Sao lưu & Cleanup']]},
  {key:'business',label:'Kinh doanh',tabs:[
    ['growth','Growth & Revenue'],['finance','Finance'],
    ['channels','Channels'],['intelligence','Intelligence']]},
  {key:'team',label:'Đội ngũ AI',tabs:[
    ['team','Team & Roles'],['goals','Kế hoạch & Duyệt'],['tasks','Task History']]},
  {key:'settings',label:'Cài đặt',tabs:[
    ['settings','Cấu hình'],['schedules','Lịch chạy'],
    ['operations','Vận hành'],['memory','Owner Memory']]},
]);
export const DEFAULT_TAB = Object.freeze({
  workspace:'workspace',overview:'overview',projects:'websites',
  business:'growth',team:'team',settings:'settings',
});
const ROUTES = Object.fromEntries(NAV_GROUPS.flatMap(group=>
  group.tabs.map(([key,label])=>[key,{group:group.key,label}])
));
export function groupFor(section) {
  return ROUTES[section]?.group || 'workspace';
}
export function labelFor(section) {
  return ROUTES[section]?.label || 'Giao việc';
}
export function defaultSection(group) {
  return DEFAULT_TAB[group] || 'workspace';
}
export function tabsFor(group) {
  return (NAV_GROUPS.find(x=>x.key===group)?.tabs || []).map(([key,label])=>({key,label}));
}
export function parseSection(hash) {
  // A previously bookmarked page remains valid; unknown paths fail closed to Workspace.
  const match = /^#\/?([a-z][a-z0-9-]*)$/.exec(hash || '');
  return match && ROUTES[match[1]] ? match[1] : 'workspace';
}
export function hashFor(section) {
  return '#/'+(ROUTES[section] ? section : 'workspace');
}
