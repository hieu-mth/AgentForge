import {useState} from 'react';
import {Button,Card,Space} from 'antd';
import {FolderOpenOutlined,PlayCircleOutlined,SettingOutlined,TeamOutlined,VideoCameraOutlined} from '@ant-design/icons';
import {SectionTitle,SettingsHeading} from '../components/settings.jsx';
import {FilmProduction,MotionClips} from './FilmProduction.jsx';

export function MediaStudio({onNavigate,mutate}){
  const [tool,setTool]=useState(null);
  return <div className="environment-page studio-page">
    <SettingsHeading title="Sản xuất video" eyebrow="STUDIO VIDEO"
      description="Kiểm tra clip chuyển động, tạo giọng đọc và dựng tập phim trên máy này."
      actions={<Button icon={<FolderOpenOutlined/>} onClick={()=>onNavigate('projects')}>Xem dự án video</Button>}/>
    <div className="studio-tools">
      <Card className="env-panel" title={<SectionTitle icon={<PlayCircleOutlined/>} title="Clip chuyển động"
        description="Đối chiếu tiến trình ComfyUI và nhập MP4 từ máy này."/>}>
        <Button type={tool==='motion'?'default':'primary'} aria-expanded={tool==='motion'}
          onClick={()=>setTool(tool==='motion'?null:'motion')}>
          {tool==='motion'?'Đóng clip chuyển động':'Mở clip chuyển động'}
        </Button>
      </Card>
      <Card className="env-panel" title={<SectionTitle icon={<VideoCameraOutlined/>} title="Dựng & kiểm tra tập phim"
        description="Xem hồ sơ từng cảnh, tạo thoại offline và dựng MP4."/>}>
        <Button type={tool==='episode'?'default':'primary'} aria-expanded={tool==='episode'}
          onClick={()=>setTool(tool==='episode'?null:'episode')}>
          {tool==='episode'?'Đóng khu vực dựng':'Mở khu vực dựng'}
        </Button>
      </Card>
    </div>
    {tool==='motion'&&<MotionClips mutate={mutate}/>}
    {tool==='episode'&&<FilmProduction mutate={mutate}/>}
    <Space className="studio-shortcuts" wrap>
      <Button type="text" icon={<TeamOutlined/>} onClick={()=>onNavigate('characters')}>Thư viện nhân vật</Button>
      <Button type="text" icon={<SettingOutlined/>} onClick={()=>onNavigate('models')}>Cấu hình Model AI</Button>
    </Space>
  </div>;
}
