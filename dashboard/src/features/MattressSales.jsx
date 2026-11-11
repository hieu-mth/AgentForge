import { useCallback, useEffect, useRef, useState } from 'react';
import { App as AntApp, Alert, Button, Card, Checkbox, Col, Descriptions,
  Divider, Drawer, Form, Input, InputNumber, Row, Select, Space, Statistic,
  Table, Tag, Typography } from 'antd';
import { api } from '../api.js';

const { Text, Paragraph } = Typography;
const STATES = {
  NEW: 'Mới tiếp nhận', CONTACTED: 'Đã liên hệ', QUOTED: 'Đã báo giá',
  OWNER_CONFIRMED: 'Đã xác nhận đơn', DELIVERY_PLANNED: 'Đã lên lịch giao',
  DELIVERED: 'Đã giao', LOST: 'Không chốt', CANCELLED: 'Đã hủy',
};
const COLORS = {
  NEW: 'blue', CONTACTED: 'cyan', QUOTED: 'gold',
  OWNER_CONFIRMED: 'green', DELIVERY_PLANNED: 'geekblue',
  DELIVERED: 'success', LOST: 'default', CANCELLED: 'error',
};
const NOTICES = {
  PENDING: 'Chưa gửi', DISPATCHING: 'Chờ đối soát (không tự gửi lại)',
  NEEDS_REVIEW: 'Không chắc đã gửi — cần đối soát',
  SENT: 'Telegram đã xác nhận', SENT_MANUAL: 'Owner xác nhận gửi thủ công',
};
const money = amount => amount == null ? 'Chưa xác nhận' :
  new Intl.NumberFormat('vi-VN').format(amount) + ' ₫';

function ConfirmButton({title,explanation,onConfirm,children,danger=false,disabled=false}) {
  const {modal}=AntApp.useApp();
  return <Button danger={danger} disabled={disabled}
    onClick={()=>modal.confirm({
      title, content: explanation,
      okText: 'Tôi xác nhận',cancelText:'Hủy',
      onOk:onConfirm,
    })}>{children}</Button>;
}

export function MattressSales({mutate}) {
  const {message,modal}=AntApp.useApp();
  const [data,setData]=useState(null);
  const [loading,setLoading]=useState(false);
  const [selected,setSelected]=useState(null);
  const [noticeText,setNoticeText]=useState(null);
  const [leadForm]=Form.useForm();
  const [quoteForm]=Form.useForm();
  const [shippingForm]=Form.useForm();
  const leadRequestId=useRef(null);
  const load=useCallback(async()=>{
    setLoading(true);
    try {setData(await api('/api/mattress'));}
    catch(e){message.error(e.status===401?'Phiên Owner đã hết hạn':'Không đọc được dữ liệu bán nệm.');}
    finally{setLoading(false);}
  },[message]);
  useEffect(()=>{load();},[load]);

  const write=async(path,body)=>{
    const result=await mutate(path,body);
    if(result){
      await load();
      if(result.lead?.lead_id)setSelected(result.lead);
    }
    return result;
  };
  const addLead=async(values)=>{
    // Preserve the same idempotency key on any retry of a failed/ambiguous POST.
    if(!leadRequestId.current)leadRequestId.current=crypto.randomUUID().replaceAll('-','');
    const out=await write('/api/mattress/leads',{
      ack:'OWNER_RECORD_CONSENTED_LEAD',
      lead:{
        request_id:leadRequestId.current,source:values.source,
        source_ref:null,customer_name:values.customer_name,phone:values.phone,
        interest:values.interest||'',area:values.area||'',
        consent_to_contact:values.consent_to_contact===true,
      },
    });
    if(out){
      leadRequestId.current=null;leadForm.resetFields();
      message.success(out.created?'Đã lưu khách mới, có thông báo cần xử lý':
        'Yêu cầu trùng đã được nhận diện; không tạo lead thứ hai');
    }
  };
  const action=(lead,status,ack)=>{
    return write('/api/mattress/leads/'+lead.lead_id+'/status',{status,ack});
  };
  const quote=values=>{
    if(!selected)return;
    return write('/api/mattress/leads/'+selected.lead_id+'/quote',{
      ack:'OWNER_SET_QUOTE',product:values.product,
      price_vnd:values.price_vnd,
    }).then(result=>{if(result){quoteForm.resetFields();message.success('Đã lưu báo giá do Owner xác nhận');}});
  };
  const shipping=values=>{
    if(!selected)return;
    const fee=values.coverage==='SUPPORTED'?values.fee_vnd:null;
    return write('/api/mattress/leads/'+selected.lead_id+'/shipping',{
      ack:'OWNER_CHECKED_CARRIER',coverage:values.coverage,
      fee_vnd:fee,note:values.note,
    }).then(result=>{if(result)message.success('Đã ghi nhận xác minh đơn vị vận chuyển');});
  };
  const confirmOrder=()=>{
    if(!selected)return;
    return write('/api/mattress/leads/'+selected.lead_id+'/confirm',{
      ack:'OWNER_CONFIRM_ORDER',customer_agreed:true,
    }).then(result=>{if(result)message.success('Đơn được xác nhận thủ công; chưa tạo vận đơn');});
  };
  const previewNotice=async notice=>{
    try{
      const result=await api('/api/mattress/notices/'+notice.notice_id+'/message');
      setNoticeText({notice,message:result.message});
    }catch{message.error('Không đọc được nội dung thông báo');}
  };
  const copyNotice=async()=>{
    if(!noticeText)return;
    try{
      await navigator.clipboard.writeText(noticeText.message);
      message.success('Đã sao chép. Hãy gửi qua Zalo/SMS rồi xác nhận bên dưới.');
    }catch{
      message.warning('Không sao chép tự động được. Chọn và sao chép tin nhắn thủ công.');
    }
  };
  const attestNotice=async()=>{
    if(!noticeText)return;
    const result=await write('/api/mattress/notices/'+noticeText.notice.notice_id+'/mark',{
      ack:'OWNER_ATTEST_ACTUALLY_NOTIFIED',
    });
    if(result){setNoticeText(null);message.success('Đã ghi nhận Owner thực sự gửi thông báo');}
  };
  const leads=data?.leads||[],notices=data?.notices||[],totals=data?.summary||{};
  const selectedLead=leads.find(x=>x.lead_id===selected?.lead_id)||selected;

  return <Space direction="vertical" size={18} style={{width:'100%'}}>
    <Alert type="info" showIcon message="MVP bán nệm — tiếp nhận qua người quen và liên hệ trực tiếp"
      description="Đây là sổ theo dõi khách/đơn local-first. Website công khai chưa nối form tự động; chỉ Owner có quyền ghi lead vào máy. Chưa có báo giá, phạm vi giao hay thanh toán nào được AI tự xác nhận."/>
    <Row gutter={[14,14]}>
      <Col xs={12} md={6}><Card><Statistic title="Khách đã ghi nhận" value={totals.total||0}/></Card></Col>
      <Col xs={12} md={6}><Card><Statistic title="Đơn Owner xác nhận" value={totals.confirmed_orders||0}/></Card></Col>
      <Col xs={12} md={6}><Card><Statistic title="Thông báo chưa gửi" value={totals.pending_notices||0}/></Card></Col>
      <Col xs={12} md={6}><Card><Statistic title="Cần đối soát thông báo" value={totals.needs_review_notices||0}/></Card></Col>
    </Row>
    <Card title="Thêm khách từ giới thiệu / khách đến trực tiếp" extra={
      <Button onClick={load} loading={loading}>Làm mới</Button>
    }>
      <Form layout="vertical" form={leadForm} onFinish={addLead}
        initialValues={{source:'REFERRAL',consent_to_contact:false}}>
        <Row gutter={14}>
          <Col xs={24} md={12}>
            <Form.Item label="Tên khách" name="customer_name"
              rules={[{required:true,min:2,max:100}]}><Input maxLength={100}/></Form.Item>
          </Col>
          <Col xs={24} md={12}>
            <Form.Item label="Số điện thoại" name="phone"
              rules={[{required:true,pattern:/^(?:0[0-9]{9,10}|\+84[0-9]{9,10})$/}]}>
              <Input maxLength={15} placeholder="SĐT khách đã đồng ý cung cấp"/></Form.Item>
          </Col>
          <Col xs={24} md={12}>
            <Form.Item label="Nguồn" name="source" rules={[{required:true}]}>
              <Select options={[
                {value:'REFERRAL',label:'Người quen giới thiệu'},
                {value:'WALK_IN',label:'Khách trực tiếp'},
              ]}/></Form.Item>
          </Col>
          <Col xs={24} md={12}>
            <Form.Item label="Sản phẩm đang quan tâm (chưa xác nhận)" name="interest">
              <Input maxLength={160} placeholder="Ví dụ: nệm theo kích thước khách hỏi"/></Form.Item>
          </Col>
          <Col xs={24} md={12}>
            <Form.Item label="Khu vực dự kiến giao (chưa xác minh)" name="area">
              <Input maxLength={100} placeholder="Không mặc định giao toàn quốc"/></Form.Item>
          </Col>
        </Row>
        <Form.Item name="consent_to_contact" valuePropName="checked"
          rules={[{validator:(_,value)=>value?Promise.resolve():Promise.reject(
            new Error('Chỉ ghi khách đã đồng ý để người bán liên hệ.'))}]}>
          <Checkbox>Tôi xác nhận khách đồng ý để người bán liên hệ tư vấn</Checkbox>
        </Form.Item>
        <Button type="primary" htmlType="submit">Lưu khách &amp; tạo thông báo chờ gửi</Button>
      </Form>
    </Card>
    <Card title="Khách hàng & tiến trình" extra={<Text type="secondary">Tối đa 100 bản ghi gần nhất</Text>}>
      <Table rowKey="lead_id" dataSource={leads} loading={loading}
        scroll={{x:800}} pagination={{pageSize:10}}
        columns={[
          {title:'Khách',dataIndex:'customer_name',render:(value,row)=>
            <Button type="link" onClick={()=>{setSelected(row);quoteForm.resetFields();shippingForm.resetFields();}}>{value}</Button>},
          {title:'Liên hệ',dataIndex:'phone',render:value=>
            <Text>{value?.replace(/^(.{3}).+(.{2})$/,'$1•••••$2')}</Text>},
          {title:'Nguồn',dataIndex:'source',
            render:value=>value==='REFERRAL'?'Giới thiệu':value==='WALK_IN'?'Trực tiếp':'Import từ form'},
          {title:'Tình trạng',dataIndex:'status',
            render:value=><Tag color={COLORS[value]||'default'}>{STATES[value]||value}</Tag>},
          {title:'Đã báo giá',dataIndex:'quoted_vnd',render:money},
          {title:'Giao hàng',dataIndex:'shipping_coverage',render:value=>
            value==='SUPPORTED'?'Đơn vị vận chuyển đã xác minh':value==='UNSUPPORTED'?
              'Không hỗ trợ':'Chưa kiểm tra'},
        ]}/>
    </Card>
    <Card title="Thông báo cho người phụ trách">
      <Alert type="warning" showIcon style={{marginBottom:15}}
        message="Gửi Zalo/SMS thủ công là mặc định"
        description="Bấm xem và sao chép, gửi thật cho người nhận, rồi mới ghi nhận đã gửi. Telegram tự động là tùy chọn qua CLI có cấu hình và đồng ý rõ ràng; chưa có Zalo OA tự động."/>
      <Table rowKey="notice_id" dataSource={notices} pagination={{pageSize:8}}
        columns={[
          {title:'Lead',dataIndex:'lead_id',render:x=><code>{x.slice(0,8)}</code>},
          {title:'Loại',dataIndex:'kind',render:v=>v==='NEW_LEAD'?'Khách mới':'Đơn đã xác nhận'},
          {title:'Trạng thái',dataIndex:'status',render:x=><Tag>{NOTICES[x]||x}</Tag>},
          {title:'Xử lý',render:(_,notice)=><Button onClick={()=>previewNotice(notice)}>
            Xem tin nhắn</Button>},
        ]}/>
    </Card>
    <Drawer title="Thông tin khách / xác nhận đơn" open={!!selectedLead}
      size={650} onClose={()=>setSelected(null)}>
      {selectedLead&&<Space direction="vertical" style={{width:'100%'}} size={18}>
        <Descriptions column={1} size="small" bordered items={[
          {key:'name',label:'Khách',children:selectedLead.customer_name},
          {key:'phone',label:'Liên hệ',children:selectedLead.phone},
          {key:'interest',label:'Quan tâm',children:selectedLead.interest||'Chưa xác định'},
          {key:'area',label:'Khu vực',children:selectedLead.area||'Chưa xác định'},
          {key:'state',label:'Trạng thái',children:STATES[selectedLead.status]},
          {key:'quote',label:'Giá đã báo',children:money(selectedLead.quoted_vnd)},
          {key:'shipping',label:'Phí giao',children:money(selectedLead.shipping_fee_vnd)},
          {key:'carrier',label:'Đơn vị vận chuyển',children:selectedLead.shipping_note||'Chưa xác nhận'},
        ]}/>
        {selectedLead.status==='NEW'&&<ConfirmButton title="Đã liên hệ với khách?"
          explanation="Chỉ xác nhận sau khi thực sự gọi/nhắn tin. Không tự liên hệ."
          onConfirm={()=>action(selectedLead,'CONTACTED','OWNER_CONTACTED_CUSTOMER')}>
          Ghi nhận đã liên hệ</ConfirmButton>}
        {selectedLead.status==='CONTACTED'&&<Card title="Báo giá theo sản phẩm và giá đã kiểm tra">
          <Form form={quoteForm} layout="vertical" onFinish={quote}>
            <Form.Item label="Tên sản phẩm đã xác minh" name="product"
              rules={[{required:true,min:2,max:140}]}><Input maxLength={140}/></Form.Item>
            <Form.Item label="Giá bán đã thống nhất (VND)" name="price_vnd"
              rules={[{required:true}]}><InputNumber min={1} max={100000000000}
              precision={0} style={{width:'100%'}}/></Form.Item>
            <Button type="primary" htmlType="submit">Owner lưu báo giá</Button>
          </Form>
        </Card>}
        {selectedLead.status==='QUOTED'&&<Card title="Kiểm tra vận chuyển trước khi chốt">
          <Alert type="warning" showIcon style={{marginBottom:14}}
            message="Không tự giả định phạm vi hoặc giá vận chuyển"
            description="Hãy liên hệ đơn vị vận chuyển để xác minh khu vực và phí thực tế."/>
          <Form form={shippingForm} layout="vertical" onFinish={shipping}
            initialValues={{coverage:'SUPPORTED'}}>
            <Form.Item label="Kết quả hỏi đơn vị vận chuyển" name="coverage"
              rules={[{required:true}]}>
              <Select options={[{value:'SUPPORTED',label:'Có hỗ trợ, phí đã xác minh'},
                {value:'UNSUPPORTED',label:'Không hỗ trợ địa điểm này'}]}/></Form.Item>
            <Form.Item noStyle shouldUpdate={(a,b)=>a.coverage!==b.coverage}>
              {({getFieldValue})=>getFieldValue('coverage')==='SUPPORTED'&&
                <Form.Item label="Phí giao hàng đã kiểm tra (VND)" name="fee_vnd"
                  rules={[{required:true}]}><InputNumber min={0} max={100000000000}
                  precision={0} style={{width:'100%'}}/></Form.Item>}
            </Form.Item>
            <Form.Item label="Ghi chú xác minh vận chuyển" name="note"
              rules={[{required:true,min:2,max:250}]}><Input.TextArea maxLength={250}/></Form.Item>
            <Button htmlType="submit">Lưu kết quả vận chuyển</Button>
          </Form>
          <Divider/>
          <ConfirmButton title="Xác nhận đơn với khách?"
            explanation="Chỉ bấm nếu khách đã đồng ý giá và đơn vị vận chuyển xác nhận khu vực cùng phí giao. Đơn sẽ được ghi local, chưa tạo vận đơn."
            disabled={selectedLead.shipping_coverage!=='SUPPORTED'}
            onConfirm={confirmOrder}>Owner xác nhận đơn</ConfirmButton>
        </Card>}
        {selectedLead.status==='OWNER_CONFIRMED'&&<ConfirmButton title="Đã thống nhất lịch giao?"
          explanation="Owner đã phối hợp trực tiếp với bên vận chuyển, chưa đồng nghĩa hàng đã giao."
          onConfirm={()=>action(selectedLead,'DELIVERY_PLANNED','OWNER_PLANNED_DELIVERY')}>
          Xác nhận đã lên lịch giao</ConfirmButton>}
        {selectedLead.status==='DELIVERY_PLANNED'&&<ConfirmButton title="Đơn thực sự giao thành công?"
          explanation="Chỉ ghi nhận sau khi khách hoặc vận chuyển xác nhận đã nhận hàng."
          onConfirm={()=>action(selectedLead,'DELIVERED','OWNER_CONFIRMED_DELIVERY')}>
          Xác nhận đã giao</ConfirmButton>}
        {['NEW','CONTACTED','QUOTED'].includes(selectedLead.status)&&
          <ConfirmButton danger title="Đánh dấu không chốt?"
            explanation="Không thể tự khôi phục trạng thái LOST; Owner cần kiểm tra."
            onConfirm={()=>action(selectedLead,'LOST','OWNER_MARKED_LOST')}>
            Không chốt đơn</ConfirmButton>}
        {['OWNER_CONFIRMED','DELIVERY_PLANNED'].includes(selectedLead.status)&&
          <ConfirmButton danger title="Hủy đơn?"
            explanation="Owner cần thông báo cho khách và đơn vị vận chuyển thủ công."
            onConfirm={()=>action(selectedLead,'CANCELLED','OWNER_CANCELLED_ORDER')}>
            Hủy đơn</ConfirmButton>}
      </Space>}
    </Drawer>
    <Drawer title="Nội dung thông báo" open={!!noticeText}
      onClose={()=>setNoticeText(null)} size={520}>
      {noticeText&&<Space direction="vertical" size={16} style={{width:'100%'}}>
        <Alert type="info" showIcon message={NOTICES[noticeText.notice.status]||'Thông báo'}
          description="Chỉ Owner xem được nội dung số điện thoại. Chỉ chia sẻ với người phụ trách đã được khách đồng ý liên hệ."/>
        <pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere',padding:18,
          background:'var(--panel,rgba(128,128,128,.08))',borderRadius:12}}>
          {noticeText.message}
        </pre>
        <Button onClick={copyNotice}>Sao chép để gửi qua Zalo/SMS</Button>
        <ConfirmButton title="Bạn đã thực sự gửi cho người phụ trách?"
          explanation="Sao chép tin chưa phải là đã gửi. Chỉ xác nhận sau khi tin được gửi thật; không có gửi Zalo tự động."
          disabled={!['PENDING','NEEDS_REVIEW'].includes(noticeText.notice.status)}
          onConfirm={attestNotice}>Đã gửi thực tế — ghi nhận</ConfirmButton>
      </Space>}
    </Drawer>
  </Space>;
}
