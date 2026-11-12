// Format server timestamps explicitly in Vietnam time, independent of browser timezone.
export function formatVietnamDateTime(value) {
  if (typeof value !== 'string' || !value.trim()) return 'Chưa có thời gian';
  const date=new Date(value);
  if (!Number.isFinite(date.getTime())) return 'Thời gian không hợp lệ';
  const parts=new Intl.DateTimeFormat('vi-VN',{
    timeZone:'Asia/Ho_Chi_Minh',hour:'2-digit',minute:'2-digit',
    day:'2-digit',month:'2-digit',year:'numeric',hourCycle:'h23',
  }).formatToParts(date);
  const get=type=>parts.find(x=>x.type===type)?.value;
  return `${get('hour')}:${get('minute')} · ${get('day')}/${get('month')}/${get('year')}`;
}
