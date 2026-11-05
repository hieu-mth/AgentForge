// Same-origin, cookie-authenticated Python API. Never store owner codes or tokens.
export async function api(path, {method='GET', body, csrf} = {}) {
  if (!path.startsWith('/api/') || path.includes('://') || path.includes('..')) {
    throw new Error('Invalid local API route');
  }
  const headers = {};
  if (method !== 'GET') {
    headers['Content-Type'] = 'application/json';
    if (csrf) headers['X-CSRF-Token'] = csrf;
  }
  const response = await fetch(path, { method, credentials:'same-origin',
    headers, body: method === 'GET' ? undefined : JSON.stringify(body ?? {}) });
  const payload = await response.json().catch(() => ({error:'invalid_api_response'}));
  if (!response.ok) {
    const error = new Error(payload.message || payload.error || ('HTTP '+response.status));
    error.status = response.status;
    throw error;
  }
  return payload;
}
