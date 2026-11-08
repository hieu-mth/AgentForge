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

export function modelCallsForPrompt(prompt) {
  return isCompanyRequest(prompt) ? 3 : 1;
}

export function quotaForPrompt(prompt, currentPolicy) {
  const required = modelCallsForPrompt(prompt);
  const allowed = Number.isInteger(currentPolicy?.max_estimated_model_calls)
    ? currentPolicy.max_estimated_model_calls : 1;
  return {required, allowed, blocked: required > allowed,
    isCompany: isCompanyRequest(prompt)};
}
