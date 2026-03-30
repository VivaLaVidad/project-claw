import React from 'react'
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom'
import { Layout, Menu } from 'antd'
import { DashboardOutlined, DollarOutlined, CheckCircleOutlined, SettingOutlined } from '@ant-design/icons'
import Dashboard from './pages/Dashboard'
import CostAnalysis from './pages/CostAnalysis'
import Approval from './pages/Approval'

const { Header, Sider, Content } = Layout

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <Layout style={{ minHeight: '100vh' }}>
        <Sider width={200} style={{ background: '#fff' }}>
          <div style={{ padding: '20px', textAlign: 'center', fontWeight: 'bold', fontSize: '18px' }}>
            Project Claw
          </div>
          <Menu mode="inline" defaultSelectedKeys={['dashboard']}>
            <Menu.Item key="dashboard" icon={<DashboardOutlined />}>
              <Link to="/">仪表板</Link>
            </Menu.Item>
            <Menu.Item key="cost" icon={<DollarOutlined />}>
              <Link to="/cost">成本分析</Link>
            </Menu.Item>
            <Menu.Item key="approval" icon={<CheckCircleOutlined />}>
              <Link to="/approval">人工干预</Link>
            </Menu.Item>
            <Menu.Item key="settings" icon={<SettingOutlined />}>
              <Link to="/settings">系统设置</Link>
            </Menu.Item>
          </Menu>
        </Sider>
        <Layout>
          <Header style={{ background: '#fff', boxShadow: '0 2px 8px rgba(0,0,0,0.1)' }}>
            <h1 style={{ margin: 0 }}>Project Claw 管理后台</h1>
          </Header>
          <Content style={{ padding: '24px', background: '#f5f5f5' }}>
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/cost" element={<CostAnalysis />} />
              <Route path="/approval" element={<Approval />} />
              <Route path="/settings" element={<div>系统设置 (开发中)</div>} />
            </Routes>
          </Content>
        </Layout>
      </Layout>
    </BrowserRouter>
  )
}

export default App
