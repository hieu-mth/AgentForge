import { useCallback, useMemo, useState } from 'react';
import { App as AntApp, Alert, Button, Card, Col, Empty, Form, Input,
  Modal, Row, Select, Space, Switch, Table, Tag, Tooltip, Typography } from 'antd';
import { api } from '../api.js';
import {useResource, ResourceStatus} from '../use_resource.jsx';
import {useScreenRefresh} from '../refresh_scope.jsx';
import { compatibleProfiles, exposureFor, KIND_LABELS, profilePayload,
  PROVIDERS, STATUS_LABELS } from '../model_hub_ui.js';

const { Text, Paragraph } = Typography;
const PROVIDER_LABELS = Object.fromEntries(PROVIDERS.map(p=>[p.value,p.label]));

function stateTag(status) {
  const tone = status==='ROUTED'||status==='DETERMINISTIC'?'green'
    :status==='INCOMPATIBLE'||status==='INVALID_CONFIG'?'red'
      :status==='UNCONFIGURED'?'default':'blue';
  return <Tag color={tone}>{STATUS_LABELS[status]||status}</Tag>;
}

export function ModelHub({mutate}) {
  const {message,modal}=AntApp.useApp();
  const hubResource=useResource('/api/model-hub');
  const motionResource=useResource('/api/film/motion');
  const productionResource=useResource('/api/film/productions');
  const setHub=hubResource.setData;
  const hub=hubResource.data;
  const loading=hubResource.loading;
  const [actionError,setError]=useState(null);
  const error=actionError;
  const [drafts,setDrafts]=useState({});
  const [checked,setChecked]=useState({});
  const motion=motionResource.data;
  const motionBusy=motionResource.loading;
  const [motionFilename,setMotionFilename]=useState({});
  const productions=productionResource.data?.episodes||[];
  const productionBusy=productionResource.loading;
  const [voiceEngine,setVoiceEngine]=useState('windows');
  const [voiceName,setVoiceName]=useState('');
  const [editorOpen,setEditorOpen]=useState(false);
  const [editing,setEditing]=useState(null);
  const [form]=Form.useForm();
  const provider=Form.useWatch('provider',form);

  const reload=useCallback(async()=>{
    const next=await hubResource.reload();
    if(next)setError(null);
  },[hubResource.reload]);
  const reloadMotion=motionResource.reload;
  const reloadProductions=productionResource.reload;
  useScreenRefresh(()=>Promise.all([reload(),reloadMotion(),reloadProductions()]));
  const filmProductionAction=(episode,action)=>{
    modal.confirm({
      title:action==='render'?'Kiểm tra và dựng MP4 local bằng FFmpeg?':'Tạo thoại offline bằng engine đã cài?',
      content:<Space direction="vertical" style={{width:'100%'}}>
        <Text strong>{episode.film_slug} / {episode.episode_id}</Text>
        <Text code>Episode SHA: {episode.episode_sha256}</Text>
        <Text>{episode.shot_count} clips · ~{episode.runtime_seconds} giây</Text>
        {action==='voice'&&<Text>Engine: {voiceEngine} · voice: {voiceName||'mặc định'}</Text>}
        <Alert showIcon type="warning"
          message="Thực thi local, cần quyền Owner và xem đầy đủ source manifest"
          description="Backend sẽ đọc lại SHA của từng clip gốc và chỉ chạy FFmpeg/TTS đã cài. Không gọi model hoặc GPU. Dựng kỹ thuật thành công KHÔNG chứng minh nhân vật đồng nhất hay phim đạt chất lượng."/>
      </Space>,okText:'Kiểm tra SHA và xác nhận',cancelText:'Hủy',
      onOk:async()=>{
        const detail=await api('/api/film/productions/'+episode.film_slug+'/'+episode.episode_id);
        if(detail.proposal.episode_sha256!==episode.episode_sha256)
          throw new Error('Episode SHA đã thay đổi; không thực thi');
        const result=await mutate('/api/film/productions/'+action,{
          ack:action==='render'?'ASSEMBLE_LOCAL_FILM':'SYNTHESIZE_LOCAL_VOICE',
          film_slug:episode.film_slug,episode_id:episode.episode_id,
          episode_sha:episode.episode_sha256,
          ...(action==='voice'?{engine:voiceEngine,voice_name:voiceName.trim()||null}:{}),
        });
        if(result){message.success(action==='render'?'Đã dựng MP4; Owner vẫn cần xem phim':'Tạo audio offline; chưa QA ngôn ngữ');await reloadProductions();}
      },
    });
  };
  const actionMotion=(job,action)=>{
    const filename=(motionFilename[job.job_id]||'').trim();
    if(action==='collect'&&(!filename.startsWith('af_motion_'+job.job_id+'_')
        || !filename.endsWith('.mp4'))){
      message.warning('Nhập tên MP4 đúng job trong thư mục ComfyUI output');
      return;
    }
    modal.confirm({
      title:action==='collect'?'Kiểm tra và nhập MP4 local?':'Kiểm tra lịch sử ComfyUI?',
      content:<Space direction="vertical">
        <Text>Shot: {job.film_slug} / {job.shot_id}</Text>
        <Text code>Plan SHA: {job.plan_sha}</Text>
        <Text code>Workflow SHA: {job.workflow_sha}</Text>
        {action==='collect'&&<Text code>File: {filename}</Text>}
        <Alert type="warning" showIcon message="Cần Owner xem video trước khi chấp nhận"
          description="Lệnh chỉ xác minh history hoặc chạy ffprobe/FFmpeg local; không gọi model, không xuất bản và không tự duyệt chất lượng."/>
      </Space>,okText:'Xác nhận',cancelText:'Hủy',
      onOk:async()=>{
        const inspected=await api('/api/film/motion/job/'+job.job_id);
        if(inspected.plan_sha!==job.plan_sha || inspected.workflow_sha!==job.workflow_sha)
          throw new Error('Motion job đã thay đổi; tải lại và kiểm tra SHA');
        const result=await mutate('/api/film/motion/'+(action==='collect'?'collect':'poll'),{
          ack:action==='collect'?'IMPORT_LOCAL_COMFY_MP4':'CHECK_LOCAL_COMFY_HISTORY',
          job_id:job.job_id,plan_sha:job.plan_sha,workflow_sha:job.workflow_sha,
          ...(action==='collect'?{filename}:{}),
        });
        if(result){message.success(action==='collect'?'MP4 đã kiểm tra kỹ thuật':'Đã đối chiếu lịch sử ComfyUI');await reloadMotion();}
      },
    });
  };

  const profiles=hub?.profiles||[];
  const profileById=useMemo(()=>Object.fromEntries(profiles.map(p=>[p.id,p])),[profiles]);
  const routes=hub?.routes||[];
  const configured=routes.filter(r=>r.status==='ROUTED'||r.status==='CONFIG_ONLY').length;
  const localProfiles=profiles.filter(p=>p.provider!=='anthropic').length;

  const update=(path,body,title,description,onSuccess)=>{
    modal.confirm({
      title,content:<Space direction="vertical" style={{width:'100%'}}>
        <Paragraph>{description}</Paragraph>
        <Alert type="info" showIcon message={'Revision đang lưu: '+(hub?.revision??'?')}
          description="Nếu Dashboard khác đã đổi cấu hình, backend sẽ từ chối revision cũ. Không tự retry."/>
      </Space>,
      okText:'Xác nhận',cancelText:'Hủy',
      onOk:async()=>{
        const result=await mutate(path,body);
        if(result){
          if(path==='/api/model-hub/check') {
            setChecked(old=>({...old,[body.profile_id]:result.status}));
          }else {
            setHub(result);setDrafts({});setChecked({});setError(null);
          }
          message.success(path==='/api/model-hub/check'?'Đã kiểm tra metadata local':'Đã lưu cấu hình local');
          onSuccess?.();
        } else {
          await reload();
        }
      },
    });
  };

  const editProfile=(item)=>{
    setEditing(item||null);
    form.resetFields();
    form.setFieldsValue(item?{
      id:item.id,provider:item.provider,model:item.model,enabled:item.enabled,
      base_url:item.base_url||'',
      base_url_env:item.base_url_env||'ANTHROPIC_BASE_URL',
      api_key_env:item.api_key_env||'ANTHROPIC_AUTH_TOKEN',
    }:{
      provider:'ollama',enabled:true,base_url:'http://127.0.0.1:11434',
      base_url_env:'ANTHROPIC_BASE_URL',api_key_env:'ANTHROPIC_AUTH_TOKEN',
    });
    setEditorOpen(true);
  };

  const saveProfile=(values)=>{
    const payload=profilePayload(values);
    update('/api/model-hub/profile',{
      ack:'SAVE_MODEL_PROFILE',expected_revision:hub.revision,profile:payload,
    },editing?'Cập nhật model profile?':'Đăng ký model profile?',
    exposureFor(payload)+' Không lưu token/API key, không tự chạy tác vụ hoặc download model.',
    ()=>setEditorOpen(false));
  };

  const saveRoute=(route)=>{
    const model_ref=drafts[route.id]??route.model_ref;
    const selected=profileById[model_ref];
    update('/api/model-hub/route',{
      ack:'SET_MODEL_ROUTE',expected_revision:hub.revision,
      task_id:route.id,model_ref,
    },'Gán model cho '+route.label+'?',
    exposureFor(selected)+(route.runtime_wired
      ? ' Route này được LLM runtime sử dụng ở lần thực thi kế tiếp; công việc đã chạy không bị thay đổi.'
      : ' Route hiện CHỈ là cấu hình, chưa nối vào engine render.'),
    null);
  };

  const resetRoute=(route)=>update('/api/model-hub/reset',{
    ack:'RESET_MODEL_ROUTE',expected_revision:hub.revision,task_id:route.id,
  },'Khôi phục route mặc định?','Chỉ xóa override của một tác vụ; mặc định Git/worker.toml được áp dụng trở lại.');

  const rollback=()=>update('/api/model-hub/rollback',{
    ack:'ROLLBACK_MODEL_HUB',expected_revision:hub.revision,target_revision:hub.revision-1,
  },'Khôi phục snapshot cấu hình trước?',
  'Toàn bộ profile và task route sẽ được khôi phục về revision '+(hub.revision-1)+
  '. Đây là một revision mới, không xóa lịch sử.');

  return <Space direction="vertical" size={18} style={{width:'100%'}}>
    <Alert showIcon type="info" message="Model Hub · cấu hình local, không tự gọi AI"
      description="models.toml + worker.toml là defaults; thay đổi trên Dashboard lưu trong SQLite local có version/rollback. Cloud không có auto-fallback; Video/Image hiện là cấu hình, chưa chứng minh GPU/ComfyUI chạy thật."/>
    {error&&<Alert type="error" showIcon message="Không đọc được Model Hub" description={error}
      action={<Button onClick={reload}>Thử lại</Button>}/>}
    <Row gutter={[12,12]}>
      <Col xs={12} md={6}><Card size="small"><Text type="secondary">Profiles</Text>
        <div className="hub-stat">{profiles.length}</div><Text type="secondary">Đăng ký</Text></Card></Col>
      <Col xs={12} md={6}><Card size="small"><Text type="secondary">Local</Text>
        <div className="hub-stat">{localProfiles}</div><Text type="secondary">Ollama / ComfyUI</Text></Card></Col>
      <Col xs={12} md={6}><Card size="small"><Text type="secondary">Configured routes</Text>
        <div className="hub-stat">{configured}/{routes.length}</div><Text type="secondary">Không phải online</Text></Card></Col>
      <Col xs={12} md={6}><Card size="small"><Text type="secondary">Config revision</Text>
        <div className="hub-stat">{hub?.revision??'—'}</div><Text type="secondary">SQLite local</Text></Card></Col>
    </Row>
    <Card title="Model Registry" loading={loading}
      extra={<Space>
        <Button onClick={reload}>Làm mới</Button>
        <Button type="primary" onClick={()=>editProfile(null)}>+ Đăng ký model</Button>
      </Space>}>
      <ResourceStatus resource={hubResource} label="Model Hub"/>
      <Table size="middle" rowKey="id" dataSource={profiles} scroll={{x:820}}
        pagination={{pageSize:8,hideOnSinglePage:true}} locale={{emptyText:<Empty description="Chưa có model"/>}}
        columns={[
          {title:'Profile',dataIndex:'id',width:200,render:(id,row)=><Space direction="vertical" size={2}>
            <Text strong code>{id}</Text>
            <Text type="secondary" style={{fontSize:12}}>{row.source==='git'?'Git default':'Owner local'}</Text>
          </Space>},
          {title:'Provider',dataIndex:'provider',width:205,
            render:p=><Tag>{PROVIDER_LABELS[p]||p}</Tag>},
          {title:'Model / Checkpoint',dataIndex:'model',width:220,render:m=><Text>{m}</Text>},
          {title:'Trạng thái',width:145,render:(_,row)=><Space direction="vertical" size={2}>
            <Tag color={row.enabled?'blue':'default'}>{row.enabled?'Enabled':'Disabled'}</Tag>
            <Text type="secondary" style={{fontSize:11}}>{checked[row.id]||'Chưa kiểm chứng'}</Text>
          </Space>},
          {title:'Thao tác',width:205,render:(_,row)=><Space>
            <Tooltip title={row.provider==='ollama'?'Chỉ GET /api/tags trên localhost':'Không kiểm tra cloud hoặc GPU tự động'}>
              <Button size="small" disabled={row.provider!=='ollama'}
                onClick={()=>update('/api/model-hub/check',{
                  ack:'CHECK_LOCAL_MODEL',profile_id:row.id,
                },'Kiểm tra Ollama local?','Chỉ đọc danh sách model từ localhost trong 3 giây; không inference, không tải model.')}>
                Kiểm tra</Button>
            </Tooltip>
            <Button size="small" onClick={()=>editProfile(row)}>Sửa</Button>
          </Space>},
        ]}/>
    </Card>
    <Card title="Task Routing" loading={loading}
      extra={<Space>
        <Text type="secondary">Revision {hub?.revision??'—'}</Text>
        <Button disabled={!hub?.revision} onClick={rollback}>Hoàn tác lần sửa gần nhất</Button>
      </Space>}>
      <Alert showIcon type="warning" style={{marginBottom:16}}
        message="Gán model không phải cấp quyền chạy"
        description="Chọn model theo loại công việc. Cloud cần Owner duyệt từng lượt và môi trường đã cấp consent; Video/Image chỉ lưu mapping, chưa kích hoạt GPU."/>
      <Table size="middle" rowKey="id" dataSource={routes} scroll={{x:960}}
        pagination={false}
        columns={[
          {title:'Công việc',dataIndex:'label',width:225,render:(v,r)=><Space direction="vertical" size={2}>
            <Text strong>{v}</Text><Text code type="secondary" style={{fontSize:11}}>{r.id}</Text>
          </Space>},
          {title:'Loại',dataIndex:'kind',width:115,render:v=>KIND_LABELS[v]||v},
          {title:'Trạng thái',dataIndex:'status',width:200,render:stateTag},
          {title:'Model được gán',width:295,render:(_,r)=>{
            if(r.kind==='rules')return <Text type="secondary">Python rules · Không dùng AI</Text>;
            const options=compatibleProfiles(r,profiles).map(p=>({
              label:p.id+' · '+p.provider,value:p.id,
            }));
            return <Space direction="vertical" style={{width:'100%'}} size={2}>
              <Select style={{width:'100%'}} size="middle" allowClear={false}
                placeholder="Chọn model..." options={options}
                value={drafts[r.id]??r.model_ref??undefined}
                onChange={v=>setDrafts(x=>({...x,[r.id]:v}))}/>
              <Text type="secondary" style={{fontSize:11}}>
                {r.source==='owner'?'Owner override':'Default'} · {r.runtime_wired?'Runtime đã nối':'Config-only'}
              </Text>
            </Space>;
          }},
          {title:'Thao tác',width:145,render:(_,r)=>r.kind==='rules'?null:<Space direction="vertical">
            <Button size="small" type="primary"
              disabled={!((drafts[r.id]??r.model_ref) && drafts[r.id]!==undefined &&
                drafts[r.id]!==r.model_ref)}
              onClick={()=>saveRoute(r)}>Lưu route</Button>
            {r.source==='owner'&&<Button size="small" onClick={()=>resetRoute(r)}>Reset</Button>}
          </Space>},
        ]}/>
    </Card>
    <Card title="Film Studio · Motion pilot 4 giây" extra={
      <Button onClick={reloadMotion} loading={motionBusy}>Làm mới GPU / Jobs</Button>}>
      <ResourceStatus resource={motionResource} label="motion jobs"/>
      <Alert type="warning" showIcon style={{marginBottom:12}}
        message="Wan 2.2 5B chạy bằng CLI do Owner kiểm soát"
        description="Model Hub video vẫn CONFIG_ONLY; phải tự cài ComfyUI/checkpoint và duyệt workflow SHA, không có auto-download/gọi GPU. QA kỹ thuật không phải duyệt chất lượng phim."/>
      <Space wrap style={{marginBottom:12}}>
        <Tag>{motion?.gpu?.status||'CHƯA KIỂM TRA GPU'}</Tag>
        <Text>Tổng VRAM: {motion?.gpu?.vram_gib??'—'} GiB</Text>
        <Text>VRAM rảnh (snapshot): {motion?.gpu?.vram_free_snapshot_gib??'—'} GiB</Text>
        <Text>Peak VRAM: chưa đo tự động</Text>
        <Text>Route: {routes.find(r=>r.id==='film.motion')?.model_ref||'CHƯA GÁN'}</Text>
      </Space>
      <Table size="small" rowKey="job_id" dataSource={motion?.jobs||[]}
        loading={motionBusy} scroll={{x:980}}
        pagination={{pageSize:6,hideOnSinglePage:true}}
        columns={[
          {title:'Shot',width:180,render:(_,r)=><Space direction="vertical" size={0}>
            <Text strong>{r.film_slug} / {r.shot_id}</Text>
            <Text code>{r.job_id.slice(0,12)}</Text></Space>},
          {title:'State',dataIndex:'status',width:260,render:v=><Tag>{v}</Tag>},
          {title:'Decode MP4',dataIndex:'mp4_technical_verified',width:145,
            render:v=>v?<Tag color="green">PASS kỹ thuật</Tag>:<Tag>Chưa đạt</Tag>},
          {title:'History',width:125,render:(_,r)=>
            <Button size="small" onClick={()=>actionMotion(r,'poll')}>Đối chiếu</Button>},
          {title:'Import MP4',width:270,render:(_,r)=><Space direction="vertical" style={{width:'100%'}}>
            <Input size="small" value={motionFilename[r.job_id]||''}
              placeholder={'af_motion_'+r.job_id+'_00001.mp4'}
              onChange={e=>setMotionFilename(old=>({...old,[r.job_id]:e.target.value}))}/>
            <Button size="small" disabled={r.mp4_technical_verified||r.state!=='COMPLETE_UNVERIFIED'}
              onClick={()=>actionMotion(r,'collect')}>Xác minh & nhập file</Button>
          </Space>},
        ]}/>
      <Text type="secondary">Để nhập file trên Dashboard, đặt AGENTFORGE_COMFY_OUTPUT_DIR trước khi khởi động với --allow-external-tools. Muốn đo peak VRAM thật hãy theo dõi nvidia-smi và khai báo thủ công qua CLI. Chưa có benchmark GPU 12 GB thực.</Text>
    </Card>
    <Card title="Film Studio · Đợt 9 (Continuity & Dựng phim)"
      extra={<Button loading={productionBusy} onClick={reloadProductions}>Làm mới Episodes</Button>}>
      <ResourceStatus resource={productionResource} label="episodes"/>
      <Alert type="warning" showIcon style={{marginBottom:14}}
        message="Chỉ ghép clip Wave 8 đã có MP4 kỹ thuật"
        description="Tạo episode-plan bằng CLI từ receipt clip thật; mỗi cảnh cần ghi identity/reference/costume/location/action/camera/caption. Không tự render GPU. 3–5 shot xem continuity (~12–20s), 15–22 shot làm pilot 60–90s. Các kiểm tra metadata KHÔNG thay thế quan sát nhân vật bằng mắt."/>
      <Space wrap style={{marginBottom:14}}>
        <Text>Giọng đọc:</Text>
        <Select size="small" style={{minWidth:150}} value={voiceEngine}
          onChange={setVoiceEngine}
          options={[{label:'Windows SAPI local',value:'windows'},{label:'Piper offline',value:'piper'}]}/>
        <Input size="small" style={{minWidth:210}} placeholder="Tên voice hoặc file .onnx (tùy chọn)"
          value={voiceName} onChange={e=>setVoiceName(e.target.value)}/>
      </Space>
      <Table rowKey={r=>r.film_slug+':'+r.episode_id}
        dataSource={productions} loading={productionBusy}
        scroll={{x:960}} pagination={{pageSize:8,hideOnSinglePage:true}}
        columns={[
          {title:'Episode',width:190,render:(_,r)=><Space direction="vertical" size={0}>
            <Text strong>{r.film_slug} / {r.episode_id}</Text>
            {r.episode_sha256&&<Text code>{r.episode_sha256.slice(0,14)}</Text>}
          </Space>},
          {title:'Phạm vi',width:150,render:(_,r)=><Text>
            {r.shot_count??'—'} shot · {r.runtime_seconds??'—'} giây
          </Text>},
          {title:'Trạng thái',dataIndex:'state',width:295,render:v=><Tag>{v}</Tag>},
          {title:'Kiểm tra & dựng',width:300,render:(_,r)=><Space wrap>
            <Button size="small" disabled={!r.episode_sha256} onClick={async()=>{
              try{
                const detail=await api('/api/film/productions/'+r.film_slug+'/'+r.episode_id);
                modal.info({title:'Episode continuity & shot SHA',
                  width:720,content:<Space direction="vertical" style={{width:'100%'}}>
                    <Text code>{detail.proposal.episode_sha256}</Text>
                    <Text>Reference/costume/location là metadata Owner nhập, chưa được thị giác máy xác nhận.</Text>
                    <pre className="source-text">{JSON.stringify(detail.proposal.shots,null,2)}</pre>
                    {detail.render&&<Text>Render SHA: {detail.render.video_sha256}</Text>}
                  </Space>});
              }catch(e){message.error(e.message||'Không đọc được episode');}
            }}>Xem shot SHA</Button>
            <Button size="small" disabled={!r.episode_sha256||r.state!=='PREPARED_NOT_RENDERED'}
              onClick={()=>filmProductionAction(r,'voice')}>TTS local</Button>
            <Button size="small" type="primary"
              disabled={!r.episode_sha256||r.state!=='PREPARED_NOT_RENDERED'}
              onClick={()=>filmProductionAction(r,'render')}>Dựng FFmpeg</Button>
          </Space>},
        ]}/>
      <Text type="secondary">Bản dựng nằm trong workspace/films/&lt;film&gt;/productions/&lt;episode&gt;/episode.mp4 cùng captions.srt và render-receipt.json. Không tự publish hoặc đánh dấu QA hình ảnh PASS.</Text>
    </Card>
    <Alert showIcon type="info" message="Ranh giới vận hành"
      description="Trạng thái 'Đã gán' không xác nhận model đã cài, API key hoạt động, đủ VRAM, hiệu năng hay phí provider. Route Video Motion/Ảnh vẫn đòi hỏi adapter và QA riêng ở Film Studio."/>
    <Modal open={editorOpen} title={editing?'Chỉnh sửa model profile':'Đăng ký model mới'}
      onCancel={()=>setEditorOpen(false)} footer={null} destroyOnHidden>
      <Form form={form} layout="vertical" onFinish={saveProfile} requiredMark={false}>
        <Form.Item name="id" label="Profile ID" rules={[{required:true,pattern:/^[a-z][a-z0-9_]{2,39}$/}]}>
          <Input disabled={!!editing} placeholder="coding_local"/>
        </Form.Item>
        <Form.Item name="provider" label="Provider" rules={[{required:true}]}>
          <Select disabled={!!editing} options={PROVIDERS}/>
        </Form.Item>
        <Form.Item name="model" label="Model name / checkpoint ID"
          rules={[{required:true,max:160,pattern:/^[A-Za-z0-9][A-Za-z0-9._:/+-]*$/}]}>
          <Input placeholder={provider==='comfyui'?'wan2.2_5b':'qwen3-coder:7b'}/>
        </Form.Item>
        {provider==='anthropic'?<>
          <Alert style={{marginBottom:12}} showIcon type="warning"
            message="Cloud credentials chỉ tham chiếu tên biến môi trường. Không nhập API key tại đây."/>
          <Form.Item name="base_url_env" label="Endpoint env" rules={[{required:true,pattern:/^[A-Z_][A-Z0-9_]*$/}]}>
            <Input placeholder="ANTHROPIC_BASE_URL"/>
          </Form.Item>
          <Form.Item name="api_key_env" label="API key env" rules={[{required:true,pattern:/^[A-Z_][A-Z0-9_]*$/}]}>
            <Input placeholder="ANTHROPIC_AUTH_TOKEN"/>
          </Form.Item>
        </>:<Form.Item name="base_url" label="Local endpoint"
          rules={[{required:true,pattern:/^http:\/\/(127\.0\.0\.1|localhost|\[::1\]):[0-9]{1,5}\/?$/}]}>
          <Input placeholder={provider==='comfyui'?'http://127.0.0.1:8188':'http://127.0.0.1:11434'}/>
        </Form.Item>}
        <Form.Item name="enabled" label="Cho phép lựa chọn profile" valuePropName="checked">
          <Switch/>
        </Form.Item>
        <Alert type="info" showIcon style={{marginBottom:16}} message={exposureFor({provider})}/>
        <Space style={{justifyContent:'flex-end',width:'100%'}}>
          <Button onClick={()=>setEditorOpen(false)}>Hủy</Button>
          <Button type="primary" htmlType="submit">Xem xác nhận & Lưu</Button>
        </Space>
      </Form>
    </Modal>
  </Space>;
}
