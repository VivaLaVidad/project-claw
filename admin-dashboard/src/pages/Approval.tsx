// admin-dashboard/src/pages/Approval.tsx
import React, { useEffect, useState } from 'react'
import { Card, Table, Button, Modal, Form, Input, Select, Space, Tag, Spin, message } from 'antd'
import { CheckCircleOutlined, CloseCircleOutlined } from '@ant-design/icons'
import axios from 'axios'

interface PendingTask {
  task_id: string
  box_id: string
  confidence: number
  reason: string
  created_at: number
  state_data: any
}

export const Approval: React.FC = () => {
  const [tasks, setTasks] = useState<PendingTask[]>([])
  const [loading, setLoading] = useState(false)
  const [selectedTask, setSelectedTask] = useState<PendingTask | null>(null)
  const [isModalVisible, setIsModalVisible] = useState(false)
  const [form] = Form.useForm()

  useEffect(() => {
    loadPendingTasks()
    // 每 10 秒刷新一次
    const interval = setInterval(loadPendingTasks, 10000)
    return () => clearInterval(interval)
  }, [])

  const loadPendingTasks = async () => {
    try {
      setLoading(true)
      const res = await axios.get('/api/fleet/pending-tasks?limit=100')
      setTasks(res.data.data || [])
    } catch (error) {
      console.error('加载待审批任务失败:', error)
      message.error('加载任务失败')
    } finally {
      setLoading(false)
    }
  }

  const handleApprove = (task: PendingTask) => {
    setSelectedTask(task)
    form.resetFields()
    setIsModalVisible(true)
  }

  const handleSubmitApproval = async (values: any) => {
    if (!selectedTask) return

    try {
      const decision = {
        task_id: selectedTask.task_id,
        decision: values.decision,
        override_params: values.decision === 'override' ? JSON.parse(values.override_params || '{}') : null,
        notes: values.notes,
        approved_by: 'admin'
      }

      await axios.post('/api/fleet/approve-task', decision)
      message.success('任务已批准')
      setIsModalVisible(false)
      loadPendingTasks()
    } catch (error) {
      console.error('批准任务失败:', error)
      message.error('批准失败')
    }
  }

  const columns = [
    { title: '任务 ID', dataIndex: 'task_id', key: 'task_id', width: 200 },
    { title: '设备 ID', dataIndex: 'box_id', key: 'box_id' },
    { title: '置信度', dataIndex: 'confidence', key: 'confidence', render: (conf: number) => (
      <Tag color={conf > 0.7 ? 'green' : conf > 0.5 ? 'orange' : 'red'}>
        {(conf * 100).toFixed(1)}%
      </Tag>
    )},
    { title: '原因', dataIndex: 'reason', key: 'reason' },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', render: (time: number) => new Date(time * 1000).toLocaleString() },
    { title: '操作', key: 'action', render: (_, record: PendingTask) => (
      <Space>
        <Button type="primary" size="small" onClick={() => handleApprove(record)}>
          <CheckCircleOutlined /> 审批
        </Button>
      </Space>
    )}
  ]

  return (
    <div style={{ padding: '24px' }}>
      <h1>人工干预审批</h1>

      <Card>
        <Space style={{ marginBottom: '16px' }}>
          <Button type="primary" onClick={loadPendingTasks} loading={loading}>
            刷新
          </Button>
          <span>待审批任务: {tasks.length}</span>
        </Space>

        <Table
          columns={columns}
          dataSource={tasks}
          loading={loading}
          rowKey="task_id"
          pagination={{ pageSize: 20 }}
        />
      </Card>

      <Modal
        title="审批任务"
        visible={isModalVisible}
        onOk={() => form.submit()}
        onCancel={() => setIsModalVisible(false)}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleSubmitApproval}
        >
          <Form.Item label="任务 ID">
            <Input value={selectedTask?.task_id} disabled />
          </Form.Item>

          <Form.Item
            label="决策"
            name="decision"
            rules={[{ required: true, message: '请选择决策' }]}
          >
            <Select placeholder="选择决策">
              <Select.Option value="accept">接受</Select.Option>
              <Select.Option value="override">覆盖</Select.Option>
              <Select.Option value="reject">拒绝</Select.Option>
            </Select>
          </Form.Item>

          <Form.Item
            label="覆盖参数 (JSON)"
            name="override_params"
            tooltip="仅在选择'覆盖'时需要"
          >
            <Input.TextArea placeholder='{"key": "value"}' rows={4} />
          </Form.Item>

          <Form.Item
            label="备注"
            name="notes"
          >
            <Input.TextArea placeholder="输入审批备注" rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default Approval
