// Execution completion never implies artifact acceptance.
export const ACCEPTANCE_LABELS = Object.freeze({
  DRAFT: 'Bản nháp', NEEDS_VALIDATION: 'Sản phẩm cần kiểm tra',
  NEEDS_REVISION: 'Sản phẩm cần chỉnh sửa', READY_FOR_REVIEW: 'Đủ điều kiện Owner nghiệm thu',
  ACCEPTED: 'Owner đã chấp nhận', REJECTED: 'Owner đã từ chối',
});
export function acceptanceLabel(value) {
  return ACCEPTANCE_LABELS[value] || 'Chưa có bằng chứng nghiệm thu';
}
export function canAccept(acceptance) {
  return acceptance?.status === 'READY_FOR_REVIEW' && acceptance?.missing_checks?.length === 0;
}
export function acceptedCount(goals) {
  return goals.filter(goal => goal.artifact_acceptance?.status === 'ACCEPTED').length;
}
