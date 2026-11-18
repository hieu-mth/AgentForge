/** Compact status presentation used by the environment dashboard. */
const GOOD = new Set(['ACTIVE','READY','ASSET_READY','PASS_RUNTIME','INSTALLED']);
const BAD = new Set(['FAILED','PAUSED','BLOCKED','UNAVAILABLE']);
const WARN = new Set(['PENDING','SUBMITTING','COLLECTING','REVIEW_REQUIRED','NEEDS_SETUP']);

export const badge = value => {
  const tone = GOOD.has(value) ? 'good' : BAD.has(value) ? 'bad' :
    WARN.has(value) ? 'warn' : 'info';
  return <span className={'status-pill tone-' + tone}><i/>{value||'UNKNOWN'}</span>;
};
