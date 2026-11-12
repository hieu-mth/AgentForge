// Owner navigation: primary workflows have independent sidebar entries.
// No API permissions are changed by client-side navigation.
export const NAV_GROUPS = Object.freeze([
  {key:'overview',label:'Tổng quan',tabs:[['overview','Tổng quan']]},
  {key:'workspace',label:'Giao việc',tabs:[['workspace','Giao việc']]},
  {key:'studio',label:'AI Media Studio',tabs:[['media-studio','Sản xuất video']]},
  {key:'characters',label:'Nhân vật',tabs:[['characters','Thư viện nhân vật']]},
  {key:'products',label:'Sản phẩm',tabs:[
    ['websites','Website'],['projects','Kho thành phẩm & Ảnh AI'],
    ['reviews','Duyệt AI & Video']]},
  {key:'business',label:'Kinh doanh',tabs:[
    ['mattress','Bán nệm'],['growth','Tăng trưởng & Doanh thu'],['finance','Tài chính'],
    ['channels','Kênh phân phối'],['intelligence','Phân tích']]},
  {key:'team',label:'Đội ngũ AI',tabs:[
    ['team','Đội ngũ & Vai trò'],['goals','Kế hoạch & Duyệt'],['tasks','Lịch sử tác vụ']]},
  {key:'settings',label:'Cài đặt',tabs:[
    ['settings','Cấu hình'],['models','Model AI & Điều phối'],['schedules','Lịch chạy'],
    ['operations','Vận hành'],['memory','Bộ nhớ Owner'],['retention','Sao lưu & Dọn dẹp']]},
]);
export const DEFAULT_TAB = Object.freeze({
  overview:'overview',workspace:'workspace',studio:'media-studio',
  characters:'characters',products:'websites',business:'mattress',
  team:'team',settings:'settings',
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
