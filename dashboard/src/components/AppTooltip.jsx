import {Tooltip} from 'antd';

export function AppTooltip({title,children}){
  return <Tooltip title={title} trigger={['hover','focus']} mouseEnterDelay={0.3}
    classNames={{root:'af-tooltip'}}>{children}</Tooltip>;
}
