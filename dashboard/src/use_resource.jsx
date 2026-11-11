import {useCallback, useEffect, useRef, useState} from 'react';
import {api} from './api.js';
import {requestError} from './api.js';
import {Alert, Button, Spin} from 'antd';

// Guard existing multi-resource screens without remounting their forms.
export function useReadSequence() {
  const sequence=useRef(0);
  useEffect(()=>()=>{sequence.current++;},[]);
  return useCallback(()=>{
    const request=++sequence.current;
    return ()=>request===sequence.current;
  },[]);
}

// Latest request wins; unmount/auth expiry prevents stale Owner data from returning.
export function useResource(path) {
  const [state, setState] = useState({data:null, loading:true, error:null});
  const sequence = useRef(0);
  const load = useCallback(async () => {
    const request = ++sequence.current;
    setState(previous => ({...previous, loading:true, error:null}));
    try {
      const data = await api(path);
      if (request === sequence.current) setState({data, loading:false, error:null});
      return data;
    } catch (error) {
      if (request === sequence.current) setState(previous => ({...previous, loading:false, error}));
      return null;
    }
  }, [path]);
  useEffect(() => {load(); return () => {sequence.current++;};}, [load]);
  const setData=useCallback(data=>{
    sequence.current++;
    setState({data,loading:false,error:null});
  },[]);
  return {...state, reload:load, setData};
}

export function ResourceStatus({resource, label}) {
  if(resource.loading)return <div role="status"><Spin size="small"/> Đang đọc {label}…</div>;
  if(!resource.error)return null;
  return <Alert type="error" showIcon message={'Không đọc được '+label}
    description={requestError(resource.error)+(resource.data?' Dữ liệu đang hiển thị là bản tải trước.':'')}
    action={<Button onClick={resource.reload}>Thử lại {label}</Button>}/>;
}
