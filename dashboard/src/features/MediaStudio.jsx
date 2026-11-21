import {useRef,useState} from 'react';
import {Button,Card,Empty,Radio,Space} from 'antd';
import {FolderOpenOutlined,PlayCircleOutlined,ReloadOutlined,
  SettingOutlined,ToolOutlined,VideoCameraOutlined} from '@ant-design/icons';
import {SectionTitle,SettingsHeading,SettingsStatus} from '../components/settings.jsx';
import {useResource,ResourceStatus} from '../use_resource.jsx';
import {useScreenRefresh} from '../refresh_scope.jsx';
import {FilmProduction,MotionClips} from './FilmProduction.jsx';
import {StudioEpisodeDetails} from './StudioEpisodeDetails.jsx';
import {StudioImages} from './StudioImages.jsx';
import {StudioDrafts} from './StudioDrafts.jsx';

const groups={
  attention:{label:'Cần xử lý',tone:'bad',next:'Kiểm tra lại hồ sơ tập và các clip nguồn.'},
  review:{label:'Chờ xem bản dựng',tone:'warn',next:'Mở tập có bản dựng để kiểm tra và xem MP4.'},
  prepared:{label:'Chờ dựng',tone:'info',next:'Chọn tập đã chuẩn bị để tạo thoại hoặc dựng MP4.'},
};
const filters=[
  {value:'all',label:'Tất cả'},{value:'prepared',label:'Chờ dựng'},
  {value:'review',label:'Chờ xem bản dựng'},{value:'attention',label:'Cần xử lý'},
];

function groupProjects(episodes){
  const byFilm=new Map();
  for(const episode of episodes){
    const film=episode.film_slug;
    if(!byFilm.has(film))byFilm.set(film,[]);
    byFilm.get(film).push(episode);
  }
  return [...byFilm].map(([film,rows])=>{
    const group=rows.some(row=>!['PREPARED_NOT_RENDERED','RENDER_RECEIPT_PRESENT_UNINSPECTED'].includes(row.state))
      ?'attention':rows.some(row=>row.state==='RENDER_RECEIPT_PRESENT_UNINSPECTED')?'review':'prepared';
    return {film,episodes:rows,group};
  });
}

export function MediaStudio({onNavigate,mutate}){
  const episodesResource=useResource('/api/film/productions');
  useScreenRefresh(episodesResource.reload);
  const [tool,setTool]=useState(null);
  const [filter,setFilter]=useState('all');
  const [selected,setSelected]=useState(null);
  const [imageScene,setImageScene]=useState(null);
  const toolsHeading=useRef(null);
  const episodes=episodesResource.data?.episodes;
  const projects=episodes&&groupProjects(episodes);
  const visible=projects?.filter(project=>filter==='all'||project.group===filter);
  const selectedProject=projects?.find(project=>project.film===selected?.film);

  const openAssembly=()=>{
    setSelected(null);
    setTool('episode');
    requestAnimationFrame(()=>toolsHeading.current?.focus());
  };

  return <div className="environment-page studio-page">
    <SettingsHeading title="Sản xuất video" eyebrow="STUDIO VIDEO"
      description="Theo dõi tập phim local, kiểm tra các bản dựng và tiếp tục sản xuất."
      actions={<Button icon={<FolderOpenOutlined/>} onClick={()=>onNavigate('projects')}>Xem dự án video</Button>}/>

    <StudioDrafts mutate={mutate} onCharacters={()=>onNavigate('characters')}/>

    {(projects?.length>0||episodesResource.error)&&<Card className="env-panel studio-projects"
      title={<SectionTitle icon={<FolderOpenOutlined/>} title="Tập phim trong workspace"/>}
      extra={<Button icon={<ReloadOutlined/>} onClick={episodesResource.reload}
        loading={episodesResource.loading}>Làm mới</Button>}>
      <ResourceStatus resource={episodesResource} label="danh sách tập phim"/>
      {projects?.length>0&&<Radio.Group className="studio-filters" aria-label="Lọc theo trạng thái"
        optionType="button" options={filters} value={filter} onChange={event=>setFilter(event.target.value)}/>}
      {visible?.length>0&&<ul className="studio-episode-grid">
        {visible.map(project=><li className="studio-episode" key={project.film}>
          <div className="studio-episode-cover"><VideoCameraOutlined aria-hidden="true"/></div>
          <div className="studio-episode-body">
            <h3>{project.film}</h3>
            <SettingsStatus tone={groups[project.group].tone}>{groups[project.group].label}</SettingsStatus>
            <p>{groups[project.group].next}</p>
            <div className="studio-episode-footer">
              <span>{project.episodes.length} tập trong danh sách</span>
              <Button size="small" aria-label={'Xem dự án '+project.film}
                onClick={()=>setSelected({film:project.film})}>Xem dự án</Button>
            </div>
          </div>
        </li>)}
      </ul>}
      {projects?.length>0&&visible?.length===0&&!episodesResource.loading&&
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Không có dự án ở trạng thái này."/>}
    </Card>}

    <section className="studio-advanced" aria-labelledby="studio-advanced-title">
      <Card className="env-panel" title={<SectionTitle icon={<ToolOutlined/>}
        title={<span id="studio-advanced-title" tabIndex={-1} ref={toolsHeading}>Công cụ nâng cao</span>}
        description="Dùng để đối chiếu, nhập clip hoặc dựng video trên máy"/>}>
        <Space wrap>
          <Button icon={<PlayCircleOutlined/>} aria-expanded={tool==='motion'}
            onClick={()=>setTool(tool==='motion'?null:'motion')}>
            {tool==='motion'?'Đóng clip chuyển động':'Mở clip chuyển động'}
          </Button>
          <Button icon={<VideoCameraOutlined/>} aria-expanded={tool==='episode'}
            onClick={()=>setTool(tool==='episode'?null:'episode')}>
            {tool==='episode'?'Đóng khu vực dựng':'Mở khu vực dựng'}
          </Button>
          <Button aria-expanded={tool==='images'} onClick={()=>{
            setImageScene(null);setTool(tool==='images'?null:'images');
          }}>Ảnh theo cảnh</Button>
          <Button type="text" icon={<SettingOutlined/>} onClick={()=>onNavigate('models')}>Cấu hình Model AI</Button>
        </Space>
      </Card>
      {tool==='motion'&&<MotionClips mutate={mutate}/>}
      {tool==='images'&&<StudioImages key={imageScene?.id??'all'} mutate={mutate}
        scene={imageScene?.id} initialPrompt={imageScene?.prompt}/>}
      {tool==='episode'&&<FilmProduction mutate={mutate} resource={episodesResource}
        onInspect={row=>setSelected({film:row.film_slug,episode:row.episode_id})}/>}
    </section>
    {selectedProject&&<StudioEpisodeDetails key={selectedProject.film} project={selectedProject}
      initialEpisode={selected.episode} onClose={()=>setSelected(null)} onAssembly={openAssembly}
      onImages={(id,prompt)=>{
        setSelected(null);setImageScene({id,prompt});setTool('images');
        requestAnimationFrame(()=>toolsHeading.current?.focus());
      }}/>}
  </div>;
}
