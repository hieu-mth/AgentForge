import { Empty } from 'antd';

const GOOD = ['SUCCEEDED', 'ACTIVE', 'APPROVED', 'ATTACHED', 'PASS_HEURISTIC', 'READY', 'ASSET_READY'];
const BAD = ['FAILED', 'INTERRUPTED', 'REJECTED', 'PAUSED'];
const WARN = ['PLANNED', 'WAITING_APPROVAL', 'PENDING', 'PROPOSED_NOT_APPLIED', 'SUBMITTING', 'COLLECTING', 'ATTACHING'];

export function stateTone(status) {
  if (GOOD.includes(status)) return 'good';
  if (BAD.includes(status)) return 'bad';
  if (WARN.includes(status)) return 'warn';
  return 'info';
}
export const badge = value =>
  <span className={'status-pill tone-' + stateTone(value)}><i/>{value || 'UNKNOWN'}</span>;
export const clip = id => String(id || '').slice(0, 12);
export const needPreviewId = id => /^[a-f0-9]{32}$/.test(String(id || ''));
export const fallback = text => <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={text}/>;

/** Page-level heading used by every screen. */
export function PageHeader({eyebrow, title, subtitle, extra}) {
  return <div className="page-heading">
    <div>
      {eyebrow && <div className="eyebrow">{eyebrow}</div>}
      <h1 className="page-title">{title}</h1>
      {subtitle && <p className="page-subtitle">{subtitle}</p>}
    </div>
    {extra && <div className="page-extra">{extra}</div>}
  </div>;
}

/** KPI tile: label, big value, optional icon and hint. */
export function StatTile({label, value, icon, hint, tone = 'info'}) {
  return <div className={'stat-tile tone-' + tone}>
    <div className="stat-top"><span className="stat-label">{label}</span>
      {icon && <span className="stat-icon">{icon}</span>}</div>
    <div className="stat-value">{value}</div>
    {hint && <div className="stat-hint">{hint}</div>}
  </div>;
}
