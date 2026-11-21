import {useState} from 'react';
import {Alert,Button,Space,Tooltip} from 'antd';
import {DownloadOutlined} from '@ant-design/icons';

export function StudioPreview({url,filename,label,reviewActions,initiallyOpen=false}){
  const [preview,setPreview]=useState(initiallyOpen?'open':'idle');
  return <>
    <div className="studio-preview-actions">
      <Space wrap>
        {preview!=='open'&&<Button type={reviewActions?'default':'primary'} onClick={()=>setPreview('open')}>
          {preview==='error'?'Thử xem lại':label}
        </Button>}
        {reviewActions}
      </Space>
      <Tooltip title="Tải MP4">
        <Button size="small" aria-label="Tải MP4" icon={<DownloadOutlined aria-hidden="true"/>}
          href={url} download={filename}/>
      </Tooltip>
    </div>
    {preview==='open'&&<video className="studio-preview" controls playsInline preload="metadata"
      aria-label={label} src={url} onError={()=>setPreview('error')}/>}
    {preview==='error'&&<Alert type="error" showIcon message="Không phát được MP4"
      description="Hãy kiểm tra lại tính toàn vẹn của clip và phiên đăng nhập."/>}
  </>;
}
