import React from 'react';
import { createRoot } from 'react-dom/client';
import { ConfigProvider, App as AntApp } from 'antd';
import viVN from 'antd/locale/vi_VN';
import App from './App.jsx';
import './styles.css';

const theme = {
  token: {
    colorPrimary: '#2563eb', colorBgBase: '#ffffff',
    colorText: '#172235', colorBorder: '#e5eaf1',
    borderRadius: 12, fontFamily: 'Inter, "Segoe UI", system-ui, sans-serif',
    controlHeight: 40,
  },
  components: {
    Layout: { bodyBg: '#f7f9fc', siderBg: '#fff', headerBg: '#fff' },
    Card: { borderRadiusLG: 16 },
    Menu: { itemSelectedBg: '#eaf2ff', itemSelectedColor: '#205acc' },
  },
};
createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ConfigProvider locale={viVN} theme={theme}>
      <AntApp><App/></AntApp>
    </ConfigProvider>
  </React.StrictMode>
);
