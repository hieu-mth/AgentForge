// Presentation-only statuses: neither UI labels nor buttons grant tool permissions.
export function preflightTone(status) {
  if(status==='BLOCKED')return 'error';
  if(status==='REVIEW_REQUIRED'||status==='NEEDS_SETUP')return 'warning';
  if(status==='READY'||status==='READY_LOCAL_UNVERIFIED')return 'success';
  return 'default';
}
export function preflightLabel(status) {
  return ({
    BLOCKED:'Cần khắc phục',REVIEW_REQUIRED:'Cần kiểm tra',
    NEEDS_SETUP:'Chưa sẵn sàng',READY:'Đạt',
    READY_LOCAL_UNVERIFIED:'Sẵn sàng local (chưa thử model)',
    AVAILABLE_UNVERIFIED:'Đã tìm thấy · chưa xác minh phiên bản',
  })[status]||'Chưa xác minh';
}
