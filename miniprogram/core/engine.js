/**
 * Project Claw 小程序核心引擎
 * 极客风范 + 高效 + 完美适配项目架构
 * 
 * 架构原则：
 * 1. Domain-Driven Design (DDD)
 * 2. 六边形架构 (Hexagonal Architecture)
 * 3. 异步优先 (Async-First)
 * 4. 事件驱动 (Event-Driven)
 */

// ==================== 共享协议层 ====================

/**
 * Bounded Context: MiniProgram
 * 职责：用户交互、本地状态管理、与后端通信
 */

class ClawProtocol {
  /**
   * A2A Trade Intent (聚合根)
   * 代表一次完整的谈判意图
   */
  static TradeIntent = {
    intent_id: String,           // UUID
    tenant_id: String,           // 龙虾盒子 ID
    user_id: String,             // 用户 ID
    dialogue_type: String,       // 'negotiation' | 'inquiry' | 'complaint'
    complexity: String,          // 'low' | 'medium' | 'high'
    state: String,               // 'pending' | 'active' | 'completed' | 'failed'
    created_at: Number,          // 时间戳
    updated_at: Number,
    metadata: Object             // 扩展数据
  }

  /**
   * Audio Frame (值对象)
   * 不可变的音频帧
   */
  static AudioFrame = {
    frame_id: String,
    session_id: String,
    timestamp: Number,
    data: ArrayBuffer,           // 音频数据
    duration: Number,            // 毫秒
    sample_rate: Number          // 采样率
  }

  /**
   * Dialogue Message (实体)
   * 对话消息
   */
  static DialogueMessage = {
    message_id: String,
    intent_id: String,
    sender: String,              // 'user' | 'agent'
    content: String,
    type: String,                // 'text' | 'audio' | 'system'
    confidence: Number,          // 0-1
    timestamp: Number,
    metadata: Object
  }
}

// ==================== 端口适配器层 ====================

/**
 * 输入端口：WebSocket 适配器
 * 负责接收来自后端的实时数据
 */
class WebSocketAdapter {
  constructor(baseUrl) {
    this.baseUrl = baseUrl
    this.socket = null
    this.listeners = new Map()
    this.reconnectAttempts = 0
    this.maxReconnectAttempts = 5
    this.reconnectDelay = 1000
  }

  /**
   * 连接 WebSocket
   */
  async connect(sessionId) {
    return new Promise((resolve, reject) => {
      try {
        const wsUrl = `${this.baseUrl}/ws/audio/${sessionId}`
        
        wx.connectSocket({
          url: wsUrl,
          success: () => {
            console.log(`[WebSocket] 连接成功: ${wsUrl}`)
            this.reconnectAttempts = 0
            resolve()
          },
          fail: (error) => {
            console.error(`[WebSocket] 连接失败:`, error)
            reject(error)
          }
        })

        // 监听打开事件
        wx.onSocketOpen(() => {
          console.log('[WebSocket] Socket 已打开')
          this.emit('open')
        })

        // 监听消息事件
        wx.onSocketMessage((res) => {
          this._handleMessage(res.data)
        })

        // 监听错误事件
        wx.onSocketError(() => {
          console.error('[WebSocket] Socket 错误')
          this.emit('error')
          this._attemptReconnect(sessionId)
        })

        // 监听关闭事件
        wx.onSocketClose(() => {
          console.log('[WebSocket] Socket 已关闭')
          this.emit('close')
        })
      } catch (error) {
        reject(error)
      }
    })
  }

  /**
   * 发送消息
   */
  async send(data) {
    return new Promise((resolve, reject) => {
      wx.sendSocketMessage({
        data,
        success: () => {
          console.log('[WebSocket] 消息已发送')
          resolve()
        },
        fail: (error) => {
          console.error('[WebSocket] 发送失败:', error)
          reject(error)
        }
      })
    })
  }

  /**
   * 处理消息
   */
  _handleMessage(data) {
    try {
      const message = typeof data === 'string' ? JSON.parse(data) : data
      
      // 分发事件
      if (this.listeners.has(message.type)) {
        this.listeners.get(message.type).forEach(callback => {
          callback(message.payload)
        })
      }

      this.emit('message', message)
    } catch (error) {
      console.error('[WebSocket] 消息处理失败:', error)
    }
  }

  /**
   * 尝试重新连接
   */
  async _attemptReconnect(sessionId) {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('[WebSocket] 重连次数已达上限')
      return
    }

    this.reconnectAttempts++
    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1)
    
    console.log(`[WebSocket] ${delay}ms 后进行第 ${this.reconnectAttempts} 次重连`)
    
    await new Promise(resolve => setTimeout(resolve, delay))
    await this.connect(sessionId)
  }

  /**
   * 监听事件
   */
  on(type, callback) {
    if (!this.listeners.has(type)) {
      this.listeners.set(type, [])
    }
    this.listeners.get(type).push(callback)
  }

  /**
   * 发出事件
   */
  emit(type, data) {
    if (this.listeners.has(type)) {
      this.listeners.get(type).forEach(callback => {
        callback(data)
      })
    }
  }

  /**
   * 断开连接
   */
  disconnect() {
    wx.closeSocket()
    console.log('[WebSocket] 已断开连接')
  }
}

// ==================== 业务逻辑层 ====================

/**
 * 谈判引擎 (Negotiator)
 * 核心业务逻辑
 */
class NegotiationEngine {
  constructor(apiService, wsAdapter) {
    this.apiService = apiService
    this.wsAdapter = wsAdapter
    this.currentIntent = null
    this.audioBuffer = []
    this.isRecording = false
  }

  /**
   * 创建谈判意图
   */
  async createTradeIntent(tenantId, dialogueType) {
    try {
      const intentId = this._generateUUID()
      
      const intent = {
        intent_id: intentId,
        tenant_id: tenantId,
        user_id: wx.getStorageSync('userId'),
        dialogue_type: dialogueType,
        complexity: 'medium',
        state: 'pending',
        created_at: Date.now(),
        updated_at: Date.now(),
        metadata: {}
      }

      // 持久化到本地
      wx.setStorageSync(`intent_${intentId}`, JSON.stringify(intent))
      
      this.currentIntent = intent
      console.log(`[NegotiationEngine] 创建意图: ${intentId}`)
      
      return intent
    } catch (error) {
      console.error('[NegotiationEngine] 创建意图失败:', error)
      throw error
    }
  }

  /**
   * 启动对话会话
   */
  async startDialogue(intent) {
    try {
      // 连接 WebSocket
      await this.wsAdapter.connect(intent.intent_id)

      // 更新意图状态
      intent.state = 'active'
      intent.updated_at = Date.now()
      wx.setStorageSync(`intent_${intent.intent_id}`, JSON.stringify(intent))

      console.log(`[NegotiationEngine] 对话已启动: ${intent.intent_id}`)
      
      return intent
    } catch (error) {
      console.error('[NegotiationEngine] 启动对话失败:', error)
      throw error
    }
  }

  /**
   * 处理音频帧
   */
  async processAudioFrame(frameData) {
    try {
      const frame = {
        frame_id: this._generateUUID(),
        session_id: this.currentIntent.intent_id,
        timestamp: Date.now(),
        data: frameData,
        duration: 0,
        sample_rate: 16000
      }

      // 发送到后端
      await this.wsAdapter.send(JSON.stringify({
        type: 'audio_frame',
        payload: frame
      }))

      console.log(`[NegotiationEngine] 音频帧已发送: ${frame.frame_id}`)
      
      return frame
    } catch (error) {
      console.error('[NegotiationEngine] 处理音频帧失败:', error)
      throw error
    }
  }

  /**
   * 结束对话
   */
  async endDialogue() {
    try {
      if (!this.currentIntent) {
        throw new Error('没有活跃的对话')
      }

      // 断开 WebSocket
      this.wsAdapter.disconnect()

      // 更新意图状态
      this.currentIntent.state = 'completed'
      this.currentIntent.updated_at = Date.now()
      wx.setStorageSync(`intent_${this.currentIntent.intent_id}`, JSON.stringify(this.currentIntent))

      console.log(`[NegotiationEngine] 对话已结束: ${this.currentIntent.intent_id}`)
      
      const completedIntent = this.currentIntent
      this.currentIntent = null
      
      return completedIntent
    } catch (error) {
      console.error('[NegotiationEngine] 结束对话失败:', error)
      throw error
    }
  }

  /**
   * 生成 UUID
   */
  _generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
      const r = Math.random() * 16 | 0
      const v = c === 'x' ? r : (r & 0x3 | 0x8)
      return v.toString(16)
    })
  }
}

// ==================== 导出 ====================

module.exports = {
  ClawProtocol,
  WebSocketAdapter,
  NegotiationEngine
}
