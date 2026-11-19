import {useRef,useState} from 'react';
import {Button,Card,Empty,Radio,Space} from 'antd';
import {ClockCircleOutlined,EyeOutlined,FolderOpenOutlined,PlayCircleOutlined,ReloadOutlined,
  SettingOutlined,TeamOutlined,ToolOutlined,VideoCameraOutlined,WarningOutlined} from '@ant-design/icons';
import {SectionTitle,SettingsHeading,Stat} from '../components/settings.jsx';
import {useResource,ResourceStatus} from '../use_resource.jsx';
import {useScreenRefresh} from '../refresh_scope.jsx';
import {FilmProduction,MotionClips,ProductionStatus} from './FilmProduction.jsx';
import {StudioEpisodeDetails} from './StudioEpisodeDetails.jsx';

const stages={
  PREPARED_NOT_RENDERED:{group:'prepared',next:'Có thể tạo thoại hoặc dựng MP4.'},
  RENDER_RECEIPT_PRESENT_UNINSPECTED:{group:'review',next:'Kiểm tra hồ sơ bản dựng trước khi xem phim.'},
  INVALID_NEEDS_OWNER_REVIEW:{group:'attention',next:'Kiểm tra lại hồ sơ và các clip nguồn.'},
};
const filters=[
  {value:'all',label:'Tất cả'},{value:'prepared',label:'Chờ dựng'},
  {value:'review',label:'Chờ xem bản dựng'},{value:'attention',label:'Cần xử lý'},
];

export function MediaStudio({onNavigate,mutate}){
  const episodesResource=useResource('/api/film/productions');
  useScreenRefresh(episodesResource.reload);
  const [tool,setTool]=useState(null);
  const [filter,setFilter]=useState('all');
  const [selected,setSelected]=useState(null);
  const toolsHeading=useRef(null);
  const episodes=episodesResource.data?.episodes;
  const stageGroup=row=>stages[row.state]?.group??'attention';
  const visible=episodes?.filter(row=>filter==='all'||stageGroup(row)===filter);

  const openAssembly=()=>{
    setSelected(null);
    setTool('episode');
    requestAnimationFrame(()=>toolsHeading.current?.focus());
  };

  return <div className="environment-page studio-page">
    <SettingsHeading title="Sản xuất video" eyebrow="STUDIO VIDEO"
      description="Theo dõi tập phim local, kiểm tra các bản dựng và tiếp tục sản xuất."
      actions={<Button icon={<FolderOpenOutlined/>} onClick={()=>onNavigate('projects')}>Xem dự án video</Button>}/>

    <section className="studio-start">
      <div className="studio-start-icon"><VideoCameraOutlined aria-hidden="true"/></div>
      <div>
        <h3>Bắt đầu một video</h3>
        <p>Studio chưa hỗ trợ tạo video từ ý tưởng nhập trực tiếp. Để bắt đầu, chuẩn bị kế hoạch và clip bằng CLI. Các tập có hồ sơ sẽ xuất hiện tại đây.</p>
      </div>
      <Button onClick={()=>onNavigate('characters')} icon={<TeamOutlined/>}>Thư viện nhân vật</Button>
    </section>

    {episodes&&<div className="env-stat-grid studio-stats" aria-label="Trạng thái trong danh sách tập phim đã tải">
      <Stat icon={<ClockCircleOutlined/>} label="Chờ dựng" value={episodes.filter(row=>stageGroup(row)==='prepared').length}/>
      <Stat icon={<EyeOutlined/>} label="Chờ xem bản dựng" value={episodes.filter(row=>stageGroup(row)==='review').length}/>
      <Stat icon={<WarningOutlined/>} label="Cần xử lý" value={episodes.filter(row=>stageGroup(row)==='attention').length}/>
    </div>}

    <Card className="env-panel studio-projects" title={<SectionTitle icon={<FolderOpenOutlined/>}
      title="Các tập đang theo dõi" description="Trạng thái và việc cần làm trong danh sách tập phim đã tải"/>}
      extra={<Button icon={<ReloadOutlined/>} onClick={episodesResource.reload}
        loading={episodesResource.loading}>Làm mới</Button>}>
      <ResourceStatus resource={episodesResource} label="danh sách tập phim"/>
      {episodes?.length>0&&<Radio.Group className="studio-filters" aria-label="Lọc theo trạng thái"
        optionType="button" options={filters} value={filter} onChange={event=>setFilter(event.target.value)}/>}
      {visible?.length>0&&<ul className="studio-episode-grid">
        {visible.map(row=><li className="studio-episode" key={row.film_slug+':'+row.episode_id}>
          <div className="studio-episode-cover"><VideoCameraOutlined aria-hidden="true"/></div>
          <div className="studio-episode-body">
            <div className="studio-episode-project">{row.film_slug}</div>
            <h3>{row.episode_id}</h3>
            <ProductionStatus state={row.state}/>
            <p>{stages[row.state]?.next??'Mở chi tiết để kiểm tra trạng thái.'}</p>
            <div className="studio-episode-footer">
              <span>{row.shot_count!=null&&row.runtime_seconds!=null
                ?`${row.shot_count} cảnh · dự kiến ${row.runtime_seconds} giây`:'Chưa có thông số tập'}</span>
              <Button size="small" aria-label={'Xem chi tiết '+row.film_slug+' / '+row.episode_id}
                onClick={()=>setSelected(row)}>Xem chi tiết</Button>
            </div>
          </div>
        </li>)}
      </ul>}
      {visible?.length===0&&!episodesResource.loading&&<Empty image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={episodes.length?'Không có tập phim ở trạng thái này.':'Chưa có tập phim trong workspace.'}/>}
    </Card>

    <section className="studio-advanced" aria-labelledby="studio-advanced-title">
      <Card className="env-panel" title={<SectionTitle icon={<ToolOutlined/>}
        title={<span id="studio-advanced-title" tabIndex={-1} ref={toolsHeading}>Công cụ nâng cao</span>}
        description="Dùng khi cần đối chiếu, nhập clip hoặc dựng bản phim local"/>}>
        <Space wrap>
          <Button icon={<PlayCircleOutlined/>} aria-expanded={tool==='motion'}
            onClick={()=>setTool(tool==='motion'?null:'motion')}>
            {tool==='motion'?'Đóng clip chuyển động':'Mở clip chuyển động'}
          </Button>
          <Button icon={<VideoCameraOutlined/>} aria-expanded={tool==='episode'}
            onClick={()=>setTool(tool==='episode'?null:'episode')}>
            {tool==='episode'?'Đóng khu vực dựng':'Mở khu vực dựng'}
          </Button>
          <Button type="text" icon={<SettingOutlined/>} onClick={()=>onNavigate('models')}>Cấu hình Model AI</Button>
        </Space>
      </Card>
      {tool==='motion'&&<MotionClips mutate={mutate}/>}
      {tool==='episode'&&<FilmProduction mutate={mutate} resource={episodesResource} onInspect={setSelected}/>}
    </section>
    {selected&&<StudioEpisodeDetails episode={selected} onClose={()=>setSelected(null)} onAssembly={openAssembly}/>}
  </div>;
}
