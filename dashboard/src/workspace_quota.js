// V5 prompt planning only. No model call, payment or policy mutation.
// Keep intent detection in sync with agentforge.ai.prompt_intake._fold.
export function normalizedRequest(text) {
  return String(text ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .replace(/[đĐ]/g, 'd').toLowerCase();
}

export function isCompanyRequest(prompt) {
  const normalized = normalizedRequest(prompt);
  const explicit = [
    'ai company v5', 'agentforge v5', 'software company v5',
    'cong ty ai v5', 'multi agent v5',
  ].some(marker => normalized.includes(marker));
  const roles = ['ai architect','ai developer','ai reviewer']
    .every(role => normalized.includes(role));
  const hasQA = /\bqa\b|kiem thu|kiem tra/.test(normalized);
  return explicit || (roles && hasQA);
}

export function isVideoRequest(prompt) {
  const text = normalizedRequest(prompt);
  return ['storyboard','kich ban video','noi dung video','video script'].some(x=>text.includes(x))
    || /\b(?:tao|lam|dung|san xuat|render|xuat|edit|chinh sua)\s+(?:mot|1|video|clip|doan|phim|video ngan|video quang cao)?\s*(?:video|clip|phim|mp4)\b/.test(text)
    || /\b(?:video|clip)\s+(?:quang cao|gioi thieu|tiktok|reels|shorts)\b/.test(text);
}

export function terminalDirectoryForPrompt(prompt) {
  return /^Kiểm tra Python trong workspace\/([a-z0-9_/-]+)$/i.exec(String(prompt ?? '').trim())?.[1] ?? null;
}

export function modelCallsForPrompt(prompt) {
  if (terminalDirectoryForPrompt(prompt)) return 0;
  if (/^Tạo báo cáo workspace\/[^\s]+\s+với nội dung:\s*.+/is.test(String(prompt ?? '').trim())) return 0;
  const normalized = normalizedRequest(prompt);
  const research = normalized.includes('markdown') && normalized.includes('bao cao')
    && ['tra cuu','nghien cuu','nguon cong khai','tim them nguon'].some(x=>normalized.includes(x));
  // Workspace intake may plan adaptive analysis for an explicit local scope.
  const scope = /\bworkspace\/[a-z0-9_-]+(?:\/[a-z0-9_-]+)*(?=[\s,;.!?)\x60]|$)/i.test(prompt);
  const product = /website|landing page|trang web|web ban|web gioi thieu|trang gioi thieu|thiet ke web|ai developer|react tuy bien|web app|webapp|ung dung react tuy bien|ai viet code|shopee|marketplace|thuong mai dien tu|gio hang|ung dung mua sam|ecommerce/.test(normalized)
    || isVideoRequest(prompt);
  return research || isCompanyRequest(prompt) || (scope && !product) ? 3 : 1;
}

export function quotaForPrompt(prompt, currentPolicy) {
  const required = modelCallsForPrompt(prompt);
  const allowed = Number.isInteger(currentPolicy?.max_estimated_model_calls)
    ? currentPolicy.max_estimated_model_calls : 1;
  return {required, allowed, blocked: required > allowed,
    isCompany: isCompanyRequest(prompt)};
}
