// admin-dashboard/src/pages/Dashboard.tsx
import React, { useEffect, useState } from 'react'
import { Row, Col, Card, Statistic, Table, Tag, Button, Space, Spin } from 'antd'
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { UserOutlined, DollarOutlined, RobotOutlined, CheckCircleOutlined } from '@ant-design/icons'
import axios from 'axios'

interface FleetStats {
  total_boxes: number
  idle_boxes: number
  busy_boxes: number
  error_boxes: number
  total_orders: number
  avg_confidence: number
  pending_tasks: number
}

interface CostData {
  date: string
  cost_usd: number
  cost_cny: number
}

export const Dashboard: React.FC = () => {
  const [stats, setStats] = useState<FleetStats | null>(null)
  const [costData, setCostData] = useState<CostData[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadDashboardData()
  }, [])

  const loadDashboardData = async () => {
    try {
      setLoading(true)
      
      // 获取舰队状态
      const statsRes = await axios.get('/api/fleet/status')
      setStats(statsRes.data.data)

      // 获取成本数据
      const costRes = await axios.get('/api/cost/daily-stats?days=30')
      setCostData(costRes.data.data)
    } catch (error) {
      console.error('加载数据失败:', error)
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return <Spin size="large" style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }} />
  }

  return (
    <div style={{ padding: '24px' }}>
      <h1>Project Claw 指挥中心</h1>

      {/* KPI 卡片 */}
      <Row gutter={16} style={{ marginBottom: '24px' }}>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="在线设备"
              value={stats?.total_boxes || 0}
              prefix={<RobotOutlined />}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="今日订单"
              value={stats?.total_orders || 0}
              prefix={<CheckCircleOutlined />}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="待审批任务"
              value={stats?.pending_tasks || 0}
              prefix={<UserOutlined />}
              valueStyle={{ color: '#faad14' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="平均置信度"
              value={(stats?.avg_confidence || 0) * 100}
              suffix="%"
              prefix={<DollarOutlined />}
              valueStyle={{ color: '#722ed1' }}
            />
          </Card>
        </Col>
      </Row>

      {/* 图表 */}
      <Row gutter={16} style={{ marginBottom: '24px' }}>
        <Col xs={24} lg={12}>
          <Card title="成本趋势 (USD)">
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={costData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Line type="monotone" dataKey="cost_usd" stroke="#1890ff" name="USD 成本" />
              </LineChart>
            </ResponsiveContainer>
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="设备状态分布">
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={[
                { name: '空闲', value: stats?.idle_boxes || 0 },
                { name: '忙碌', value: stats?.busy_boxes || 0 },
                { name: '错误', value: stats?.error_boxes || 0 }
              ]}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" />
                <YAxis />
                <Tooltip />
                <Bar dataKey="value" fill="#1890ff" />
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </Col>
      </Row>

      {/* 设备列表 */}
      <Card title="在线设备列表">
        <Table
          columns={[
            { title: '设备 ID', dataIndex: 'box_id', key: 'box_id' },
            { title: '状态', dataIndex: 'status', key: 'status', render: (status) => {
              const colors = { idle: 'green', busy: 'blue', error: 'red', suspended: 'orange' }
              return <Tag color={colors[status] || 'default'}>{status}</Tag>
            }},
            { title: '今日订单', dataIndex: 'daily_orders', key: 'daily_orders' },
            { title: '置信度', dataIndex: 'confidence', key: 'confidence', render: (conf) => `${(conf * 100).toFixed(1)}%` },
            { title: '操作', key: 'action', render: () => (
              <Space>
                <Button type="primary" size="small">监控</Button>
                <Button size="small">控制</Button>
              </Space>
            )}
          ]}
          dataSource={stats?.boxes || []}
          pagination={{ pageSize: 10 }}
        />
      </Card>
    </div>
  )
}

export default Dashboard
