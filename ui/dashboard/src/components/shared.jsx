import { Empty, Tag } from 'antd';

function stateColor(status) {
  if (['SUCCEEDED', 'ACTIVE', 'APPROVED', 'ATTACHED', 'PASS_HEURISTIC'].includes(status)) return 'green';
  if (['FAILED', 'INTERRUPTED', 'REJECTED'].includes(status)) return 'red';
  if (['PLANNED', 'WAITING_APPROVAL', 'PENDING', 'PROPOSED_NOT_APPLIED'].includes(status)) return 'gold';
  return 'blue';
}
export const badge = value => <Tag color={stateColor(value)}>{value || 'UNKNOWN'}</Tag>;
export const clip = id => String(id || '').slice(0, 12);
export const needPreviewId = id => /^[a-f0-9]{32}$/.test(String(id || ''));
export const fallback = text => <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={text}/>;

