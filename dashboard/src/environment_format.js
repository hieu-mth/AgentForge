// Pure presentation helpers. Preserve unavailable data instead of guessing.
export function formatGiB(bytes, digits=1) {
  if(typeof bytes!=='number'||!Number.isFinite(bytes)||bytes<0)return 'Chưa xác định';
  return (bytes/(1024**3)).toLocaleString('vi-VN',{maximumFractionDigits:digits})+' GiB';
}
export function formatMiB(value) {
  if(typeof value!=='number'||!Number.isFinite(value)||value<0)return '—';
  return value.toLocaleString('vi-VN',{maximumFractionDigits:0})+' MiB';
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
