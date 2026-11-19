import {useState} from 'react';
import {Alert,Button,Space} from 'antd';

export function StudioPreview({url,filename,label}){
  const [preview,setPreview]=useState('idle');
  return <>
    <Space wrap className="studio-preview-actions">
      {preview!=='open'&&<Button type="primary" onClick={()=>setPreview('open')}>
        {preview==='error'?'Thử xem lại':label}
      </Button>}
      <Button href={url} download={filename}>Tải MP4</Button>
    </Space>
    {preview==='open'&&<video className="studio-preview" controls playsInline preload="metadata"
      aria-label={label} src={url} onError={()=>setPreview('error')}/>}
    {preview==='error'&&<Alert type="error" showIcon message="Không phát được MP4"
      description="Hãy kiểm tra lại tính toàn vẹn của clip và phiên đăng nhập."/>}
  </>;
}
