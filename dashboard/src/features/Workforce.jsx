import {Alert, Button, Card, Descriptions, Space, Table, Tabs, Typography} from 'antd';
import {useResource, ResourceStatus} from '../use_resource.jsx';
import {useScreenRefresh} from '../refresh_scope.jsx';
import {SKILLS, WORKERS} from '../permissions.js';
import {badge} from '../components/shared.jsx';

const {Text} = Typography;
const join = values => values.length ? values.join(', ') : '—';

export function Workforce({onNavigate}) {
  const resource = useResource('/api/workforce');
  useScreenRefresh(resource.reload);
  const data = resource.data;
  return <Card title="Đội ngũ, năng lực và phụ thuộc" extra={<Space wrap>
    <Button onClick={()=>onNavigate('environment')}>Môi trường</Button>
    <Button onClick={()=>onNavigate('models')}>Cấu hình model</Button>
  </Space>}>
    <ResourceStatus resource={resource} label="danh mục đội ngũ"/>
    {data && <>
      <Alert showIcon type="info" message="Danh mục lấy từ manifest và policy đang dùng"
        description="Đổi model tại Model Hub. Đổi skill, rule và hướng dẫn worker qua Git."/>
      <Tabs items={[
        {key:'agents', label:'Agents', children:<Table rowKey="id" size="small" scroll={{x:640}}
          dataSource={data.agents} columns={[
            {title:'Vai trò',render:(_,r)=>WORKERS[r.id]||r.id},
            {title:'Model',render:(_,r)=>r.model?.model||r.model_ref||'Theo skill · không cần model'},
            {title:'Kiểm tra model',dataIndex:'model_readiness',render:badge},
            {title:'Skills',render:(_,r)=>r.skills.length},
          ]}
          expandable={{expandedRowRender:r=><Descriptions column={1} size="small" items={[
            {key:'cap', label:'Năng lực khai báo', children:join(r.capabilities)},
            {key:'paths',label:'Cấu hình',children:<Text code>{r.manifest}</Text>},
            {key:'instructions',label:'Hướng dẫn',children:<Text code>{r.instructions_path}</Text>},
            {key:'skills',label:'Skills',children:join(r.skills)},
            {key:'rules',label:'Quyền',children:join(r.permissions)},
            {key:'tools',label:'Tools',children:join(r.tools)},
            {key:'history',label:'Thực thi gần đây',children:join(r.recent_executions.map(x=>x.skill_id+' · '+x.status))},
          ]}/>}}/>},
        {key:'models', label:'Models', children:<Table rowKey="id" size="small" scroll={{x:560}}
          dataSource={data.models} columns={[
            {title:'Profile',dataIndex:'id'}, {title:'Provider',dataIndex:'provider'},
            {title:'Model',dataIndex:'model'},
            {title:'Cấu hình',dataIndex:'enabled',render:x=>x?'Bật':'Tắt'},
            {title:'Kiểm tra',dataIndex:'health',render:badge},
          ]}/>},
        {key:'skills', label:'Skills & phụ thuộc', children:<Table rowKey="id" size="small" scroll={{x:640}}
          dataSource={data.skills} columns={[
            {title:'Skill',render:(_,s)=>SKILLS[s.id]||s.id},
            {title:'Agent',dataIndex:'worker_id'},
            {title:'Adapter',dataIndex:'adapter_status',render:badge},
          ]}
          expandable={{expandedRowRender:s=><Descriptions column={1} size="small" items={[
            {key:'manifest',label:'Manifest',children:<Text code>{s.manifest}</Text>},
            {key:'schema',label:'Input / Output bắt buộc',children:join(s.input_schema.required)+' → '+join(s.output_schema.required)},
            {key:'model',label:'Model',children:s.model_ref||'Không cần model'},
            {key:'tools',label:'Tools',children:join(s.required_tools)},
            {key:'permissions',label:'Rules và QA',children:join([...s.required_permissions,...s.quality_checks])},
            {key:'observed',label:'Workflow trong 30 kế hoạch gần đây',children:join(s.observed_workflows)},
          ]}/>}}/>},
        {key:'rules',label:'Rules',children:<Table rowKey="id" size="small" scroll={{x:560}}
          dataSource={data.rules} columns={[
            {title:'Quyền',dataIndex:'id'},{title:'Nơi kiểm soát',dataIndex:'source'},
            {title:'Skills áp dụng',dataIndex:'skills',render:join},
          ]}/>},
        {key:'tools',label:'Tools',children:<Table rowKey="id" size="small" scroll={{x:560}}
          dataSource={data.tools} columns={[
            {title:'Tool',dataIndex:'id'},{title:'Phụ thuộc',dataIndex:'runtime_dependencies',render:join},
            {title:'Skills sử dụng',dataIndex:'skills',render:join},
          ]}/>},
      ]}/>
    </>}
  </Card>;
}
