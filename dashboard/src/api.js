// Same-origin, cookie-authenticated Python API. Never store owner codes or tokens.
const authListeners = new Set();
let authRevision = 0;
export const onAuthExpired = listener => {
  authListeners.add(listener);
  return () => authListeners.delete(listener);
};
export const sessionRevision = () => authRevision;
export function requestError(error) {
  if (error?.status === 403) return 'Không có quyền truy cập (403). Phiên đăng nhập không bị thay đổi.';
  if (error?.status === 503) return 'Dịch vụ local chưa sẵn sàng (503). Hãy kiểm tra backend rồi thử lại.';
  return error?.message || 'Không kết nối được backend local. Hãy kiểm tra AgentForge đang chạy.';
}
export async function api(path, {method='GET', body, csrf, timeoutMs=15000} = {}) {
  if (!path.startsWith('/api/') || path.includes('://') || path.includes('..')) {
    throw new Error('Invalid local API route');
  }
  const headers = {};
  if (method !== 'GET') {
    headers['Content-Type'] = 'application/json';
    if (csrf) headers['X-CSRF-Token'] = csrf;
  }
  const revision = authRevision;
  const controller = new AbortController();
  // POST may run a long Owner-authorized tool. Never time it out and imply it failed.
  const timer = method === 'GET' ? setTimeout(() => controller.abort(), timeoutMs) : null;
  let response, payload;
  try {
    response = await fetch(path, { method, credentials:'same-origin', signal:controller.signal,
      headers, body: method === 'GET' ? undefined : JSON.stringify(body ?? {}) });
    // Expire on headers, even if an unauthorized response body stalls or is invalid.
    if(response.status===401&&revision===authRevision){
      authRevision++;
      for(const listener of authListeners)listener();
    }
    payload = await response.json().catch(error => {
      if(error.name==='AbortError')throw error;
      if(response.ok){
        const invalid=new Error('Backend trả về dữ liệu không hợp lệ. Hãy kiểm tra địa chỉ localhost rồi thử lại.');
        invalid.code='INVALID_API_RESPONSE';
        throw invalid;
      }
      return {error:'invalid_api_response'};
    });
  } catch (cause) {
    if(cause.code==='INVALID_API_RESPONSE')throw cause;
    const error = new Error(method!=='GET'
      ? 'Chưa xác định kết quả thao tác do mất kết nối. Không gửi lại; hãy kiểm tra lịch sử trước.'
      : cause.name === 'AbortError'
      ? 'Đọc dữ liệu quá thời gian chờ. Hãy thử lại kết nối local.'
      : 'Không kết nối được backend local. Hãy kiểm tra AgentForge đang chạy rồi thử lại.');
    error.code = cause.name === 'AbortError' ? 'GET_TIMEOUT' : 'NETWORK_UNAVAILABLE';
    throw error;
  } finally { if (timer !== null) clearTimeout(timer); }
  if (method === 'GET' && revision !== authRevision && response.ok) {
    const error = new Error('Phiên đã hết hạn; dữ liệu cũ đã được bỏ qua.');
    error.status = 401;
    throw error;
  }
  if (!response.ok) {
    const error = new Error(payload.message || payload.error || ('HTTP '+response.status));
    error.status = response.status;
    error.code = payload.error;
    throw error;
  }
  return payload;
}
