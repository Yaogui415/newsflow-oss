import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { ConfigProvider, theme } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ConfigProvider
      locale={zhCN}
      theme={{
        algorithm: theme.darkAlgorithm,
        token: {
          colorPrimary: '#D4A853',
          colorInfo: '#D4A853',
          colorBgBase: '#0A0A0A',
          colorBgLayout: '#0A0A0A',
          colorBgContainer: '#141414',
          colorBgElevated: '#141414',
          colorText: '#F5F5F5',
          colorTextSecondary: 'rgba(245,245,245,0.65)',
          colorBorder: 'rgba(212,168,83,0.18)',
          colorFillSecondary: 'rgba(245,245,245,0.08)',
          borderRadius: 8,
        },
      }}
    >
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </ConfigProvider>
  </React.StrictMode>,
)
