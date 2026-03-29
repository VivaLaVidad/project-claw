// admin-dashboard/src/pages/CostAnalysis.tsx
import React, { useEffect, useState } from 'react'
import { Card, Table, Select, DatePicker, Button, Space, Statistic, Row, Col, Spin } from 'antd'
import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import dayjs from 'dayjs'
import axios from 'axios'

interface CostRecord {
  tenant_id: string
  model_id: string
  cost_usd: number
  cost_cny: number
  total_tokens: number
  request_count: number
}

export const CostAnalysis: React.FC = () => {
  const [costData, setCostData] = useState<CostRecord[]>([])
  const [modelBreakdown, setModelBreakdown] = useState<any[]>([])
  const [totalCost, setTotalCost] = useState(0)
  const [selectedTenant, setSelectedTenant] = useState<string>('')
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs]>([dayjs().subtract(30, 'days'), dayjs()])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    loadCostData()
  }, [selectedTenant, dateRange])

  const loadCostData = async () => {
    try {
      setLoading(true)
      
      const params = {
        start_date: dateRange[0].format('YYYY-MM-DD'),
        end_date: dateRange[1].format('YYYY-MM-DD')
      }

      if (selectedTenant) {
        params.tenant_id = selectedTenant
      }

      // 获取成本数据
      const res = await axios.get('/api/cost/analysis', { params })
      setCostData(res.data.data.by_tenant || [])
      setModelBreakdown(res.data.data.by_model || [])
      setTotalCost(res.data.data.total_cost_usd || 0)
    } catch (error) {
      console.error('加载成本数据失败:', error)
    } finally {
      setLoading(false)
    }
  }

  const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884D8']

  return (
    <div style={{ padding: '24px' }}>
      <h1>成本分析</h1>

      {/* 筛选器 */}
      <Card style={{ marginBottom: '24px' }}>
        <Space>
          <Select
            placeholder="选择租户"
            style={{ width: 200 }}
            value={selectedTenant}
            onChange={setSelectedTenant}
            allowClear
          />
          <DatePicker.RangePicker
            value={dateRange}
            onChange={(dates) => dates && setDateRange([dates[0]!, dates[1]!])}
          />
          <Button type="primary" onClick={loadCostData}>查询</Button>
        </Space>
      </Card>

      {/* KPI */}
      <Row gutter={16} style={{ marginBottom: '24px' }}>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="总成本 (USD)"
              value={totalCost}
              precision={2}
              suffix="$"
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="总成本 (CNY)"
              value={totalCost * 7}
              precision={2}
              suffix="¥"
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="平均单客成本"
              value={totalCost / (costData.length || 1)}
              precision={4}
              suffix="$"
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="总 Token 数"
              value={costData.reduce((sum, item) => sum + item.total_tokens, 0)}
            />
          </Card>
        </Col>
      </Row>

      {/* 图表 */}
      <Row gutter={16} style={{ marginBottom: '24px' }}>
        <Col xs={24} lg={12}>
          <Card title="租户成本分布">
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={costData}
                  dataKey="cost_usd"
                  nameKey="tenant_id"
                  cx="50%"
                  cy="50%"
                  outerRadius={80}
                  label
                >
                  {costData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="模型成本分布">
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={modelBreakdown}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="model_id" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Bar dataKey="cost_usd" fill="#1890ff" name="USD 成本" />
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </Col>
      </Row>

      {/* 详细表格 */}
      <Card title="成本详情">
        <Table
          columns={[
            { title: '租户 ID', dataIndex: 'tenant_id', key: 'tenant_id' },
            { title: '模型', dataIndex: 'model_id', key: 'model_id' },
            { title: '成本 (USD)', dataIndex: 'cost_usd', key: 'cost_usd', render: (val) => `$${val.toFixed(4)}` },
            { title: '成本 (CNY)', dataIndex: 'cost_cny', key: 'cost_cny', render: (val) => `¥${val.toFixed(2)}` },
            { title: 'Token 数', dataIndex: 'total_tokens', key: 'total_tokens' },
            { title: '请求数', dataIndex: 'request_count', key: 'request_count' }
          ]}
          dataSource={costData}
          loading={loading}
          pagination={{ pageSize: 20 }}
        />
      </Card>
    </div>
  )
}

export default CostAnalysis
