import React from 'react';
import { createRoot } from 'react-dom/client';
import { ConfigProvider, App as AntApp } from 'antd';
import viVN from 'antd/locale/vi_VN';
import App from './App.jsx';
import { ThemeProvider } from './theme.jsx';
import { RefreshScope } from './refresh_scope.jsx';
import './styles.css';

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ThemeProvider render={theme =>
      <ConfigProvider locale={viVN} theme={theme}>
        <AntApp className="app-root"><RefreshScope><App/></RefreshScope></AntApp>
      </ConfigProvider>}/>
  </React.StrictMode>
);
