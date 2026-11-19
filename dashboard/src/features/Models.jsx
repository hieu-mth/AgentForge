import { useMemo, useState } from 'react';
import { App as AntApp, Alert, Button, Card, Col, Empty, Form, Grid, Input,
  Modal, Row, Select, Space, Switch, Table, Tag, Tooltip, Typography } from 'antd';
import {useResource, ResourceStatus} from '../use_resource.jsx';
import {useScreenRefresh} from '../refresh_scope.jsx';
import {displayStatus} from '../environment_format.js';
import { compatibleProfiles, exposureFor, KIND_LABELS, profilePayload,
  PROVIDERS, STATUS_LABELS } from '../model_hub_ui.js';

const { Text, Title, Paragraph } = Typography;
const PROVIDER_LABELS = Object.fromEntries(PROVIDERS.map(p=>[p.value,p.label]));
const desktopColumns=['md'];

function stateTag(status) {
  const tone = status==='DETERMINISTIC'?'green'
    :status==='INCOMPATIBLE'||status==='INVALID_CONFIG'?'red'
      :status==='UNCONFIGURED'?'default':'blue';
  return <Tag color={tone}>{STATUS_LABELS[status]||status}</Tag>;
}

export function ModelHub({mutate}) {
  const {message,modal}=AntApp.useApp();
  const {md:desktop}=Grid.useBreakpoint();
  const hubResource=useResource('/api/model-hub');
  const setHub=hubResource.setData;
  const hub=hubResource.data;
  const loading=hubResource.loading;
  const [drafts,setDrafts]=useState({});
  const [checked,setChecked]=useState({});
  const [probes,setProbes]=useState({});
  const [editorOpen,setEditorOpen]=useState(false);
  const [editing,setEditing]=useState(null);
  const [form]=Form.useForm();
  const provider=Form.useWatch('provider',form);

  const reload=hubResource.reload;
  useScreenRefresh(reload);

  const profiles=hub?.profiles||[];
  const profileById=useMemo(()=>Object.fromEntries(profiles.map(p=>[p.id,p])),[profiles]);
  const routes=hub?.routes||[];
  const configured=routes.filter(r=>r.status==='CONFIG_ONLY').length;
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
            setChecked(old=>({...old,[body.profile_id]:{status:result.status,revision:hub?.revision}}));
          }else if(path==='/api/model-hub/probe') {
            setProbes(old=>({...old,[body.profile_id]:result}));
          }else {
            setHub(result);setDrafts({});setChecked({});setProbes({});
          }
          if(path!=='/api/model-hub/probe') {
            message.success(path==='/api/model-hub/check'?'Đã kiểm tra metadata local':'Đã lưu cấu hình local');
          }
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
    exposureFor(selected)+' Route này chỉ lưu cấu hình; chưa nối vào inference.',
    null);
  };

  const resetRoute=(route)=>update('/api/model-hub/reset',{
    ack:'RESET_MODEL_ROUTE',expected_revision:hub.revision,task_id:route.id,
  },'Khôi phục route mặc định?','Chỉ xóa override của một tác vụ; mặc định config/task_routes.toml được áp dụng trở lại.');

  const rollback=()=>update('/api/model-hub/rollback',{
    ack:'ROLLBACK_MODEL_HUB',expected_revision:hub.revision,target_revision:hub.revision-1,
  },'Khôi phục cấu hình về phiên bản '+(hub.revision-1)+'?',
  'Danh sách model và thiết lập điều phối sẽ được khôi phục cùng nhau. Hệ thống sẽ lưu kết quả thành một phiên bản mới.');

  const profileActions=row=><Space wrap size={6}>
    {row.provider==='ollama'&&<>
      <Tooltip title="Đọc danh sách model từ Ollama local">
        <Button size="small" onClick={()=>update('/api/model-hub/check',{
          ack:'CHECK_LOCAL_MODEL',profile_id:row.id,
        },'Kiểm tra Ollama local?','Chỉ đọc danh sách model từ localhost trong 3 giây; không inference, không tải model.')}>
          Kiểm tra
        </Button>
      </Tooltip>
      <Button size="small" disabled={!row.enabled} onClick={()=>update('/api/model-hub/probe',{
        ack:'RUN_LOCAL_MODEL_PROBE',profile_id:row.id,expected_revision:hub.revision,
      },'Chạy thử model Ollama?',
      'Gọi một lượt local tối đa 32 token đầu ra bằng câu kiểm tra cố định. Có thể nạp model vào RAM hoặc VRAM. Backend cần bật quyền công cụ ngoài.')}>
        Chạy thử
      </Button>
    </>}
    <Button size="small" onClick={()=>editProfile(row)}>Sửa</Button>
  </Space>;

  return <Space className="model-hub" direction="vertical" size={18} style={{width:'100%'}}>
    <div className="hub-toolbar">
      <div><Title level={2}>Model AI &amp; Điều phối</Title>
        <Text type="secondary">Quản lý model và gán model cho từng công việc.</Text>
      </div>
      <Space wrap>
        <Button onClick={reload} loading={loading}>Làm mới</Button>
        <Button disabled={!hub?.revision} onClick={rollback}>Khôi phục phiên bản trước</Button>
      </Space>
    </div>
    <ResourceStatus resource={hubResource} label="cấu hình model"/>
    <Row gutter={[12,12]}>
      <Col xs={12} md={6}><Card size="small"><Text type="secondary">Model đã đăng ký</Text>
        <div className="hub-stat">{hub?profiles.length:'—'}</div></Card></Col>
      <Col xs={12} md={6}><Card size="small"><Text type="secondary">Profile chạy local</Text>
        <div className="hub-stat">{hub?localProfiles:'—'}</div></Card></Col>
      <Col xs={12} md={6}><Card size="small"><Text type="secondary">Đã gán · chưa nối runtime</Text>
        <div className="hub-stat">{hub?configured:'—'}</div></Card></Col>
      <Col xs={12} md={6}><Card size="small"><Text type="secondary">Phiên bản cấu hình</Text>
        <div className="hub-stat">{hub?.revision??'—'}</div></Card></Col>
    </Row>
    <Card title="Danh sách model" loading={loading}
      extra={<Button type="primary" disabled={!hub} onClick={()=>editProfile(null)}>Đăng ký model</Button>}>
      <Table className="hub-table" size="middle" rowKey="id" dataSource={profiles} scroll={desktop?{x:980}:undefined}
        pagination={{pageSize:8,hideOnSinglePage:true}} locale={{emptyText:<Empty description="Chưa có model"/>}}
        columns={[
          {title:'Profile',dataIndex:'id',width:200,render:(id,row)=><Space direction="vertical" size={2}>
            <Text strong code>{id}</Text>
            {desktop?<Text type="secondary">{row.source==='git'?'Mặc định':'Owner tùy chỉnh'}</Text>:
              <details className="hub-details"><summary>Chi tiết</summary>
                <div>{PROVIDER_LABELS[row.provider]||row.provider}</div>
                <div>{row.model}</div>
                <div>{row.source==='git'?'Mặc định':'Owner tùy chỉnh'}</div>
              </details>}
            {!desktop&&profileActions(row)}
          </Space>},
          {title:'Nhà cung cấp',dataIndex:'provider',width:205,responsive:desktopColumns,
            render:p=><Tag>{PROVIDER_LABELS[p]||p}</Tag>},
          {title:'Model / Checkpoint',dataIndex:'model',width:220,responsive:desktopColumns,render:m=><Text>{m}</Text>},
          {title:'Trạng thái',width:145,render:(_,row)=><Space direction="vertical" size={2}>
            <Tag color={row.enabled?'blue':'default'}>{row.enabled?'Đã bật':'Đã tắt'}</Tag>
            {row.provider==='ollama'&&<Text type="secondary" style={{fontSize:12}}>
              {checked[row.id]&&checked[row.id].revision===hub?.revision
                ?checked[row.id].status==='LOCAL_MODEL_FOUND'?'Đã phát hiện qua Ollama':displayStatus(checked[row.id].status)
                :'Chưa kiểm tra Ollama'}
            </Text>}
            {probes[row.id]&&probes[row.id].revision===hub?.revision&&<Text type="secondary" style={{fontSize:11}}>
              {probes[row.id].status==='PASS_RUNTIME'?'Đã chạy thử thành công':'Chạy thử: '+displayStatus(probes[row.id].status)}
              {' · '}{new Date(probes[row.id].checked_at).toLocaleTimeString('vi-VN')}
            </Text>}
          </Space>},
          {title:'Thao tác',width:250,responsive:desktopColumns,render:(_,row)=>profileActions(row)},
        ]}/>
    </Card>
    <Card title="Điều phối tác vụ" loading={loading}>
      <Alert showIcon type="warning" style={{marginBottom:16}}
        message="Gán model không phải cấp quyền chạy"
        description="Cloud cần Owner duyệt từng lượt. Tuyến video và ảnh chỉ lưu cấu hình."/>
      <Table className="hub-table" size="middle" rowKey="id" dataSource={routes} scroll={desktop?{x:840}:undefined}
        pagination={false}
        columns={[
          {title:'Công việc',dataIndex:'label',width:225,render:(v,r)=><Space direction="vertical" size={2}>
            <Text strong>{v}</Text>
            {desktop?<Text code type="secondary">{r.id}</Text>:<>
              {stateTag(r.status)}
              <details className="hub-details"><summary>Chi tiết</summary>
                <div>{KIND_LABELS[r.kind]||r.kind}</div><div>{r.id}</div>
              </details>
            </>}
          </Space>},
          {title:'Loại',dataIndex:'kind',width:115,responsive:desktopColumns,render:v=>KIND_LABELS[v]||v},
          {title:'Trạng thái',dataIndex:'status',width:200,responsive:desktopColumns,render:stateTag},
          {title:'Model được gán',width:295,render:(_,r)=>{
            if(r.kind==='rules')return <Text type="secondary">—</Text>;
            const options=compatibleProfiles(r,profiles).map(p=>({
              label:p.id+' · '+p.provider,value:p.id,
            }));
            return <Space direction="vertical" style={{width:'100%'}} size={2}>
              <Select style={{width:'100%'}} size="middle" allowClear={false}
                placeholder="Chọn model..." options={options}
                value={drafts[r.id]??r.model_ref??undefined}
                onChange={v=>setDrafts(x=>({...x,[r.id]:v}))}/>
              <Space wrap size={6}>
                <Button size="small" type="primary"
                  disabled={!drafts[r.id]||drafts[r.id]===r.model_ref}
                  onClick={()=>saveRoute(r)}>Lưu</Button>
                {r.source==='owner'&&<Button size="small" onClick={()=>resetRoute(r)}>Về mặc định</Button>}
              </Space>
            </Space>;
          }},
        ]}/>
    </Card>
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
