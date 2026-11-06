// Owner-facing copy, separate from the backend's stable permission identifiers.
// Unknown permissions must never silently receive consent.
export const PERMISSIONS = Object.freeze({
  'workspace.read': {
    title: 'Đọc dữ liệu trong workspace',
    description: 'Xem dữ liệu mà công việc cần. Không được sửa hoặc xóa.',
    impact: 'Chỉ đọc', risk: 'low',
  },
  'workspace.propose': {
    title: 'Tạo bản nháp để bạn xem',
    description: 'Lưu đề xuất hoặc website nháp trong máy. Chưa áp dụng thành sản phẩm và chưa đăng lên Internet.',
    impact: 'Tạo bản nháp local', risk: 'low',
  },
  'workspace.write': {
    title: 'Ghi dữ liệu vào workspace',
    description: 'Cho phép tạo hoặc cập nhật dữ liệu trong workspace theo skill. Có thay đổi trên ổ đĩa; hãy kiểm tra kế hoạch.',
    impact: 'Thay đổi file/dữ liệu local', risk: 'medium',
  },
  'model.invoke': {
    title: 'Cho AI tạo nội dung',
    description: 'Gửi yêu cầu cho model đã cấu hình (Ollama local hoặc nhà cung cấp cloud). Cloud có thể gửi dữ liệu ra ngoài và phát sinh chi phí.',
    impact: 'Gọi AI một lượt theo giới hạn kế hoạch', risk: 'high',
  },
  'network.search': {
    title: 'Tìm kiếm thông tin trên Internet',
    description: 'Cho phép truy vấn công cụ tìm kiếm đã cấu hình. Từ khóa tìm kiếm có thể được gửi ra ngoài.',
    impact: 'Có kết nối Internet', risk: 'high',
  },
  'network.read': {
    title: 'Đọc nội dung từ website bên ngoài',
    description: 'Truy cập nguồn web được chính sách cho phép; dữ liệu và địa chỉ truy cập có thể đi qua mạng.',
    impact: 'Có kết nối Internet', risk: 'high',
  },
  'browser.run': {
    title: 'Chạy trình duyệt để kiểm tra',
    description: 'Khởi động browser tự động để mở và kiểm thử trang được cho phép. Có thể phát sinh truy cập mạng tùy mục tiêu.',
    impact: 'Chạy trình duyệt trên máy', risk: 'high',
  },
  'process.run': {
    title: 'Chạy công cụ ngoài trên máy',
    description: 'Cho phép skill gọi tiến trình được hệ thống cho phép (ví dụ FFmpeg); không đồng nghĩa quyền chạy lệnh bất kỳ.',
    impact: 'Chạy tiến trình local', risk: 'high',
  },
});
export const WORKERS = Object.freeze({
  product_builder: 'AI xây dựng website',
  opportunity_researcher: 'AI nghiên cứu cơ hội',
  source_reviewer: 'AI kiểm tra nguồn',
  media_producer: 'AI sản xuất nội dung',
  analytics_analyst: 'AI phân tích dữ liệu',
  growth_operator: 'AI hỗ trợ kinh doanh',
});
export const SKILLS = Object.freeze({
  'web.create': 'Tạo bản nháp website',
  'web.quality_check': 'Kiểm tra chất lượng website',
  'web.browser_test': 'Kiểm thử website trên trình duyệt',
  'research.opportunity': 'Nghiên cứu cơ hội kinh doanh',
  'research.source_review': 'Kiểm tra và đối chiếu nguồn thông tin',
  'media.compose': 'Tạo hình ảnh và tư liệu video',
  'media.copy_draft': 'Soạn kịch bản video nháp',
  'media.image_edit': 'Chỉnh sửa hình ảnh local',
  'media.quality_check': 'Kiểm tra chất lượng tư liệu',
  'media.video_render': 'Dựng video MP4',
  'media.tts': 'Tạo giọng đọc cho video',
  'analytics.import': 'Nhập dữ liệu để phân tích',
  'analytics.quality_check': 'Kiểm tra dữ liệu phân tích',
  'analytics.content_report': 'Báo cáo hiệu quả nội dung',
  'analytics.trend_report': 'Phân tích xu hướng nội bộ',
  'analytics.experiment_report': 'Đánh giá thử nghiệm',
  'analytics.finance_report': 'Báo cáo thu chi ghi nhận',
  'analytics.opportunity_score': 'Đánh giá tín hiệu cơ hội',
  'growth.campaign_create': 'Tạo chiến dịch kinh doanh',
  'growth.bundle_prepare': 'Chuẩn bị gói nội dung đăng thủ công',
  'growth.record_event': 'Ghi nhận hoạt động kinh doanh',
  'growth.report': 'Tổng hợp hiệu quả chiến dịch',
  'growth.quality_check': 'Kiểm tra dữ liệu chiến dịch',
  'growth.reconcile': 'Đối chiếu dữ liệu chiến dịch',
});
export function requiredPermissions(plan) {
  return [...new Set((plan || []).flatMap(step=>step.required_permissions||[]))]
    .filter(permission=>permission!=='workspace.read');
}
export function permissionsKnown(permissions) {
  return permissions.every(permission=>Object.hasOwn(PERMISSIONS, permission));
}
export function executionConsent(required, accepted) {
  const granted = required.filter(permission=>accepted.includes(permission));
  return {
    grants: granted,
    confirmModel: granted.includes('model.invoke'),
    confirmBrowser: granted.includes('browser.run'),
    confirmProcess: granted.includes('process.run'),
    sensitive: granted.some(permission=>PERMISSIONS[permission]?.risk==='high'),
  };
}
