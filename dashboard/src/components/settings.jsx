import {Progress,Typography} from 'antd';

const {Title,Paragraph}=Typography;

export function SettingsHeading({title,description,eyebrow,actions,className=''}){
  return <div className={['env-page-heading',className].filter(Boolean).join(' ')}>
    <div>
      {eyebrow&&<div className="env-eyebrow"><span className="env-eyebrow-dot" aria-hidden="true"/> {eyebrow}</div>}
      <Title level={2} className="env-page-title">{title}</Title>
      <Paragraph className="env-page-subtitle">{description}</Paragraph>
    </div>
    {actions&&<div className="env-page-actions">{actions}</div>}
  </div>;
}

export function SectionTitle({icon,title,description}){
  return <div className="env-section-heading">
    <span className="env-section-icon" aria-hidden="true">{icon}</span>
    <div><div className="env-section-title">{title}</div>
      <div className="env-section-description">{description}</div></div>
  </div>;
}

export function Stat({icon,label,value,sub,progress}){
  return <div className="env-stat">
    <div className="env-stat-top"><span className="env-stat-icon" aria-hidden="true">{icon}</span>
      <span className="env-stat-label">{label}</span></div>
    <div className="env-stat-value" title={value}>{value}</div>
    <div className="env-stat-sub">{sub}</div>
    {progress!==null&&progress!==undefined&&
      <Progress percent={progress} showInfo={false} size="small" strokeColor="#7776ee"
        trailColor="var(--env-track)" aria-label={'Đã sử dụng '+progress+'%'} />}
  </div>;
}

export function SettingsStatus({tone='info',children,title}){
  return <span className={'env-status tone-'+tone} title={title}>
    <span className="env-status-dot" aria-hidden="true"/>{children}
  </span>;
}
