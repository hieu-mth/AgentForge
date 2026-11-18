// Pure presentation helpers. Preserve unavailable data instead of guessing.
// Dashboard uses familiar decimal GB/MB; raw API units remain unchanged.
// System RAM/disk/model sizes arrive in bytes, NVIDIA VRAM arrives in MiB.
export function formatCapacity(bytes, digits=2) {
  if(typeof bytes!=='number'||!Number.isFinite(bytes)||bytes<0)return 'Chưa xác định';
  const inGB=bytes>=1e9;
  return (bytes/(inGB?1e9:1e6)).toLocaleString('vi-VN',{
    maximumFractionDigits:digits,
  })+(inGB?' GB':' MB');
}
export function formatVram(mib, digits=2) {
  if(typeof mib!=='number'||!Number.isFinite(mib)||mib<0)return '—';
  return formatCapacity(mib*(1024**2),digits);
}
export function percentUsed(free,total) {
  if(typeof free!=='number'||typeof total!=='number'||
      !Number.isFinite(free)||!Number.isFinite(total)||total<=0||free<0||free>total)return null;
  return Math.max(0,Math.min(100,Math.round((total-free)*100/total)));
}
export function formatChecked(value) {
  if(!value)return 'Chưa có dữ liệu';
  const date=new Date(value);
  return Number.isNaN(date.getTime())?'Chưa có dữ liệu':
    date.toLocaleString('vi-VN',{hour:'2-digit',minute:'2-digit',day:'2-digit',
      month:'2-digit',year:'numeric'});
}
export function displayStatus(value) {
  const labels={
    READY:'Sẵn sàng',RUNNING:'Đang chạy',INSTALLED:'Đã cài đặt',
    DEGRADED:'Gián đoạn',STOPPED:'Đã dừng',NOT_INSTALLED:'Chưa cài đặt',
    UNAVAILABLE:'Không kết nối',UNKNOWN:'Chưa xác minh',ERROR:'Có lỗi',
    DISABLED:'Đã tắt',NO_CHECKPOINT:'Thiếu checkpoint',NOT_CHECKED:'Chưa kiểm tra',
    LOCAL_MODEL_FOUND:'Đã phát hiện',MODEL_NOT_INSTALLED:'Chưa cài đặt',
  };
  return labels[value]||value||'Chưa rõ';
}
export function statusTone(value) {
  if(['READY','RUNNING','INSTALLED','LOCAL_MODEL_FOUND'].includes(value))return 'good';
  if(['DEGRADED','STOPPED','NO_CHECKPOINT','NOT_INSTALLED','MODEL_NOT_INSTALLED'].includes(value))return 'warn';
  if(['ERROR','UNAVAILABLE','FAILED','BLOCKED'].includes(value))return 'bad';
  return 'info';
}
