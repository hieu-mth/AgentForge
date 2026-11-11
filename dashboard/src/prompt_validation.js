export const PROMPT_MAX = 6000;
export function promptValidation(prompt) {
  const raw = String(prompt ?? '');
  const text = raw.trim();
  const characters = [...text].length; // Python len: Unicode code points, not UTF-16 units.
  const bytes = new TextEncoder().encode(text).length;
  const error = characters < 20 ? 'Yêu cầu cần ít nhất 20 ký tự.'
    : characters > PROMPT_MAX ? 'Yêu cầu vượt 6.000 ký tự. Hãy chia thành các công việc nhỏ hơn.'
    : /[\u0000-\u0008\u000b\u000c\u000e-\u001f]/u.test(raw) ? 'Yêu cầu chứa ký tự điều khiển không hợp lệ.'
      : null;
  return {characters, bytes, error};
}
