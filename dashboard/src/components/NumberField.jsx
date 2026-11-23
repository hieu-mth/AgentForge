import {InputNumber} from 'antd';

export function NumberField({className, ...props}) {
  return <InputNumber {...props} changeOnWheel={false}
    className={['dashboard-number-field', className].filter(Boolean).join(' ')}/>;
}
