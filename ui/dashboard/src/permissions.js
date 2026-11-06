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
