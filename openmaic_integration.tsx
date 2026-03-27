/**
 * openmaic_integration.tsx - Project Claw 与 OpenMAIC 的集成组件
 * 放在 OpenMAIC/components/agent/ 目录下
 * 
 * 使用方式：
 * import { LobsterAgent } from '@/components/agent/openmaic_integration'
 * <LobsterAgent />
 */

'use client'

import React, { useState, useEffect, useRef } from 'react'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { AlertCircle, Play, Send, Zap, TrendingUp } from 'lucide-react'

interface AgentMessage {
  type: 'agent_start' | 'agent_result' | 'agent_complete' | 'agent_error' | 'message' | 'send_result'
  content?: string
  result?: any
  success?: boolean
  error?: string
  timestamp: string
}

interface Stats {
  total_messages: number
  successful_replies: number
  failed_replies: number
  feishu_synced: number
}

export function LobsterAgent() {
  const [isConnected, setIsConnected] = useState(false)
  const [isRunning, setIsRunning] = useState(false)
  const [messages, setMessages] = useState<AgentMessage[]>([])
  const [stats, setStats] = useState<Stats>({
    total_messages: 0,
    successful_replies: 0,
    failed_replies: 0,
    feishu_synced: 0
  })
  const [inputText, setInputText] = useState('')
  const wsRef = useRef<WebSocket | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // 连接 WebSocket
  useEffect(() => {
    const connectWebSocket = () => {
      try {
        wsRef.current = new WebSocket('ws://localhost:8000/ws/agent-stream')

        wsRef.current.onopen = () => {
          console.log('✅ WebSocket 已连接')
          setIsConnected(true)
        }

        wsRef.current.onmessage = (event) => {
          const data: AgentMessage = JSON.parse(event.data)
          setMessages((prev) => [...prev, data])

          // 更新统计信息
          if (data.type === 'agent_complete' && data.success) {
            setStats((prev) => ({
              ...prev,
              successful_replies: prev.successful_replies + 1,
              feishu_synced: prev.feishu_synced + 1
            }))
          } else if (data.type === 'agent_error') {
            setStats((prev) => ({
              ...prev,
              failed_replies: prev.failed_replies + 1
            }))
          }

          // 自动滚动到底部
          setTimeout(() => {
            messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
          }, 100)
        }

        wsRef.current.onerror = (error) => {
          console.error('❌ WebSocket 错误:', error)
          setIsConnected(false)
        }

        wsRef.current.onclose = () => {
          console.log('❌ WebSocket 已断开')
          setIsConnected(false)
          // 5 秒后重新连接
          setTimeout(connectWebSocket, 5000)
        }
      } catch (error) {
        console.error('❌ WebSocket 连接失败:', error)
        setIsConnected(false)
      }
    }

    connectWebSocket()

    return () => {
      if (wsRef.current) {
        wsRef.current.close()
      }
    }
  }, [])

  // 启动 Agent
  const handleStartAgent = () => {
    if (!isConnected || !wsRef.current) {
      alert('WebSocket 未连接')
      return
    }

    setIsRunning(true)
    wsRef.current.send(JSON.stringify({ action: 'start_agent' }))
    setStats((prev) => ({ ...prev, total_messages: prev.total_messages + 1 }))
  }

  // 获取最新消息
  const handleGetMessage = () => {
    if (!isConnected || !wsRef.current) {
      alert('WebSocket 未连接')
      return
    }

    wsRef.current.send(JSON.stringify({ action: 'get_message' }))
  }

  // 发送消息
  const handleSendMessage = () => {
    if (!inputText.trim()) {
      alert('请输入消息')
      return
    }

    if (!isConnected || !wsRef.current) {
      alert('WebSocket 未连接')
      return
    }

    wsRef.current.send(
      JSON.stringify({
        action: 'send_message',
        text: inputText
      })
    )

    setInputText('')
  }

  // 清空日志
  const handleClearMessages = () => {
    setMessages([])
  }

  return (
    <div className="w-full max-w-4xl mx-auto p-6 space-y-6">
      {/* 标题 */}
      <div className="space-y-2">
        <h1 className="text-3xl font-bold">🦞 Project Claw - 龙虾自动回复</h1>
        <p className="text-gray-600">多智能体协同系统 + OpenMAIC 可视化</p>
      </div>

      {/* 连接状态 */}
      <Card className="p-4 bg-gradient-to-r from-blue-50 to-indigo-50">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div
              className={`w-3 h-3 rounded-full ${
                isConnected ? 'bg-green-500 animate-pulse' : 'bg-red-500'
              }`}
            />
            <span className="font-semibold">
              {isConnected ? '✅ 已连接' : '❌ 未连接'}
            </span>
          </div>
          <span className="text-sm text-gray-600">ws://localhost:8000/ws/agent-stream</span>
        </div>
      </Card>

      {/* 统计信息 */}
      <div className="grid grid-cols-4 gap-4">
        <Card className="p-4">
          <div className="flex items-center gap-2 mb-2">
            <TrendingUp className="w-4 h-4 text-blue-500" />
            <span className="text-sm text-gray-600">总消息</span>
          </div>
          <p className="text-2xl font-bold">{stats.total_messages}</p>
        </Card>

        <Card className="p-4">
          <div className="flex items-center gap-2 mb-2">
            <Zap className="w-4 h-4 text-green-500" />
            <span className="text-sm text-gray-600">成功回复</span>
          </div>
          <p className="text-2xl font-bold text-green-600">{stats.successful_replies}</p>
        </Card>

        <Card className="p-4">
          <div className="flex items-center gap-2 mb-2">
            <AlertCircle className="w-4 h-4 text-red-500" />
            <span className="text-sm text-gray-600">失败</span>
          </div>
          <p className="text-2xl font-bold text-red-600">{stats.failed_replies}</p>
        </Card>

        <Card className="p-4">
          <div className="flex items-center gap-2 mb-2">
            <Zap className="w-4 h-4 text-purple-500" />
            <span className="text-sm text-gray-600">飞书同步</span>
          </div>
          <p className="text-2xl font-bold text-purple-600">{stats.feishu_synced}</p>
        </Card>
      </div>

      {/* 控制按钮 */}
      <Card className="p-4 space-y-4">
        <h2 className="font-semibold">控制面板</h2>

        <div className="grid grid-cols-2 gap-4">
          <Button
            onClick={handleStartAgent}
            disabled={!isConnected || isRunning}
            className="bg-blue-600 hover:bg-blue-700"
          >
            <Play className="w-4 h-4 mr-2" />
            启动 Agent
          </Button>

          <Button
            onClick={handleGetMessage}
            disabled={!isConnected}
            variant="outline"
          >
            获取最新消息
          </Button>
        </div>

        <div className="flex gap-2">
          <Input
            placeholder="输入要发送的消息..."
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && handleSendMessage()}
            disabled={!isConnected}
          />
          <Button
            onClick={handleSendMessage}
            disabled={!isConnected || !inputText.trim()}
            className="bg-green-600 hover:bg-green-700"
          >
            <Send className="w-4 h-4" />
          </Button>
        </div>

        <Button
          onClick={handleClearMessages}
          variant="outline"
          className="w-full"
        >
          清空日志
        </Button>
      </Card>

      {/* 日志输出 */}
      <Card className="p-4 space-y-4">
        <h2 className="font-semibold">实时日志</h2>

        <div className="bg-gray-900 text-gray-100 p-4 rounded-lg h-96 overflow-y-auto font-mono text-sm space-y-2">
          {messages.length === 0 ? (
            <p className="text-gray-500">等待消息...</p>
          ) : (
            messages.map((msg, idx) => (
              <div key={idx} className="space-y-1">
                <div className="flex items-center gap-2">
                  <Badge
                    variant={
                      msg.type === 'agent_complete'
                        ? 'default'
                        : msg.type === 'agent_error'
                          ? 'destructive'
                          : 'secondary'
                    }
                  >
                    {msg.type}
                  </Badge>
                  <span className="text-gray-500 text-xs">{msg.timestamp}</span>
                </div>

                {msg.content && <p className="text-blue-400">{msg.content}</p>}
                {msg.error && <p className="text-red-400">❌ {msg.error}</p>}
                {msg.result && (
                  <pre className="text-green-400 text-xs overflow-x-auto">
                    {JSON.stringify(msg.result, null, 2)}
                  </pre>
                )}
              </div>
            ))
          )}
          <div ref={messagesEndRef} />
        </div>
      </Card>

      {/* 文档链接 */}
      <Card className="p-4 bg-amber-50">
        <p className="text-sm text-gray-700">
          📖 API 文档：
          <a
            href="http://localhost:8000/docs"
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-600 hover:underline ml-2"
          >
            http://localhost:8000/docs
          </a>
        </p>
      </Card>
    </div>
  )
}
