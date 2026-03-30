/**
 * Project Claw v14.3 - 极客风范完善版
 * 核心引擎：事件驱动 + 状态管理 + 性能监控
 * 
 * ╔═══════════════════════════════════════════════════════════╗
 * ║  Project Claw - 智能询价系统                              ║
 * ║  MiniProgram Core Engine v1.0                             ║
 * ║  Powered by Event-Driven Architecture                     ║
 * ╚═══════════════════════════════════════════════════════════╝
 */

/**
 * 事件总线 - 全局事件通信
 */
class EventBus {
  constructor() {
    this.events = new Map()
  }

  on(eventName, callback) {
    if (!this.events.has(eventName)) {
      this.events.set(eventName, [])
    }
    this.events.get(eventName).push(callback)
    return () => {
      const callbacks = this.events.get(eventName)
      const index = callbacks.indexOf(callback)
      if (index > -1) callbacks.splice(index, 1)
    }
  }

  once(eventName, callback) {
    const unsubscribe = this.on(eventName, (...args) => {
      callback(...args)
      unsubscribe()
    })
    return unsubscribe
  }

  emit(eventName, ...args) {
    if (this.events.has(eventName)) {
      this.events.get(eventName).forEach(callback => {
        try {
          callback(...args)
        } catch (error) {
          console.error(`[EventBus] 事件 ${eventName} 处理失败:`, error)
        }
      })
    }
  }

  clear(eventName) {
    if (eventName) {
      this.events.delete(eventName)
    } else {
      this.events.clear()
    }
  }
}

/**
 * 状态管理器 - 响应式状态系统
 */
class StateManager {
  constructor(initialState = {}) {
    this.state = initialState
    this.subscribers = new Map()
    this.history = []
    this.maxHistory = 50
  }

  getState(path) {
    if (!path) return this.state
    return path.split('.').reduce((obj, key) => obj?.[key], this.state)
  }

  setState(updates, metadata = {}) {
    const oldState = JSON.parse(JSON.stringify(this.state))
    this.state = this._deepMerge(this.state, updates)

    this.history.push({
      timestamp: Date.now(),
      oldState,
      newState: JSON.parse(JSON.stringify(this.state)),
      updates,
      metadata
    })

    if (this.history.length > this.maxHistory) {
      this.history.shift()
    }

    this._notifySubscribers(updates)
  }

  subscribe(path, callback) {
    if (!this.subscribers.has(path)) {
      this.subscribers.set(path, [])
    }
    this.subscribers.get(path).push(callback)
    return () => {
      const callbacks = this.subscribers.get(path)
      const index = callbacks.indexOf(callback)
      if (index > -1) callbacks.splice(index, 1)
    }
  }

  _notifySubscribers(updates) {
    for (const [path, callbacks] of this.subscribers) {
      if (this._pathMatches(path, updates)) {
        const newValue = this.getState(path)
        callbacks.forEach(callback => {
          try {
            callback(newValue)
          } catch (error) {
            console.error('[StateManager] 订阅回调错误:', error)
          }
        })
      }
    }
  }

  _pathMatches(path, updates) {
    if (path === '*') return true
    const pathParts = path.split('.')
    const updateKeys = Object.keys(updates)
    return updateKeys.some(key => pathParts[0] === key || key.startsWith(pathParts[0] + '.'))
  }

  _deepMerge(target, source) {
    const result = { ...target }
    for (const key in source) {
      if (source.hasOwnProperty(key)) {
        if (typeof source[key] === 'object' && source[key] !== null && !Array.isArray(source[key])) {
          result[key] = this._deepMerge(result[key] || {}, source[key])
        } else {
          result[key] = source[key]
        }
      }
    }
    return result
  }

  undo() {
    if (this.history.length === 0) return false
    const record = this.history.pop()
    this.state = record.oldState
    this._notifySubscribers(record.oldState)
    return true
  }
}

/**
 * 缓存管理器 - 智能 LRU 缓存
 */
class CacheManager {
  constructor(maxSize = 100) {
    this.cache = new Map()
    this.maxSize = maxSize
    this.accessCount = new Map()
  }

  get(key) {
    if (this.cache.has(key)) {
      this.accessCount.set(key, (this.accessCount.get(key) || 0) + 1)
      const item = this.cache.get(key)
      if (item.expiresAt && item.expiresAt < Date.now()) {
        this.cache.delete(key)
        this.accessCount.delete(key)
        return null
      }
      return item.value
    }
    return null
  }

  set(key, value, ttl = 3600000) {
    if (this.cache.size >= this.maxSize && !this.cache.has(key)) {
      const lruKey = Array.from(this.accessCount.entries())
        .sort((a, b) => a[1] - b[1])[0][0]
      this.cache.delete(lruKey)
      this.accessCount.delete(lruKey)
    }

    this.cache.set(key, {
      value,
      expiresAt: Date.now() + ttl
    })
    this.accessCount.set(key, 0)
  }

  cleanup() {
    const now = Date.now()
    let cleaned = 0
    for (const [key, item] of this.cache) {
      if (item.expiresAt < now) {
        this.cache.delete(key)
        this.accessCount.delete(key)
        cleaned++
      }
    }
    return cleaned
  }

  clear() {
    this.cache.clear()
    this.accessCount.clear()
  }

  getStats() {
    return {
      size: this.cache.size,
      maxSize: this.maxSize
    }
  }
}

/**
 * 性能监控器
 */
class PerformanceMonitor {
  constructor() {
    this.metrics = new Map()
    this.marks = new Map()
  }

  mark(name) {
    this.marks.set(name, Date.now())
  }

  measure(name) {
    if (!this.marks.has(name)) return
    const duration = Date.now() - this.marks.get(name)
    if (!this.metrics.has(name)) {
      this.metrics.set(name, [])
    }
    this.metrics.get(name).push(duration)
    this.marks.delete(name)
    return duration
  }

  getStats(name) {
    if (!this.metrics.has(name)) return null
    const durations = this.metrics.get(name)
    const avg = durations.reduce((a, b) => a + b, 0) / durations.length
    return {
      count: durations.length,
      avg: avg.toFixed(2),
      min: Math.min(...durations),
      max: Math.max(...durations)
    }
  }

  getAllStats() {
    const stats = {}
    for (const [name] of this.metrics) {
      stats[name] = this.getStats(name)
    }
    return stats
  }

  clear() {
    this.metrics.clear()
    this.marks.clear()
  }
}

/**
 * 询价引擎 - 核心业务逻辑
 */
class TradeEngine {
  constructor(eventBus, stateManager, cacheManager) {
    this.eventBus = eventBus
    this.stateManager = stateManager
    this.cacheManager = cacheManager
    this.currentTrade = null
  }

  /**
   * 创建询价请求
   */
  createTradeRequest(payload) {
    const requestId = `r-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`
    
    const request = {
      request_id: requestId,
      ...payload,
      created_at: Date.now(),
      status: 'pending'
    }

    this.currentTrade = request
    this.stateManager.setState({
      currentTrade: request,
      tradeStatus: 'pending'
    })

    this.eventBus.emit('trade:created', request)
    console.log('[TradeEngine] 询价请求已创建:', requestId)

    return request
  }

  /**
   * 更新询价状态
   */
  updateTradeStatus(status, metadata = {}) {
    if (!this.currentTrade) return

    this.currentTrade.status = status
    this.currentTrade.updated_at = Date.now()

    this.stateManager.setState({
      currentTrade: this.currentTrade,
      tradeStatus: status
    }, metadata)

    this.eventBus.emit(`trade:${status}`, this.currentTrade)
    console.log('[TradeEngine] 询价状态已更新:', status)
  }

  /**
   * 处理报价结果
   */
  handleOffers(offers) {
    if (!this.currentTrade) return

    this.currentTrade.offers = offers
    this.currentTrade.offer_count = offers.length

    this.stateManager.setState({
      currentTrade: this.currentTrade,
      offers: offers
    })

    this.eventBus.emit('trade:offers_received', offers)
    console.log('[TradeEngine] 已收到', offers.length, '个报价')
  }

  /**
   * 完成询价
   */
  completeTrade(result) {
    if (!this.currentTrade) return

    this.currentTrade.result = result
    this.currentTrade.status = 'completed'
    this.currentTrade.completed_at = Date.now()

    this.stateManager.setState({
      currentTrade: this.currentTrade,
      tradeStatus: 'completed'
    })

    this.eventBus.emit('trade:completed', this.currentTrade)
    console.log('[TradeEngine] 询价已完成')

    // 保存到历史
    this._saveToHistory(this.currentTrade)
  }

  /**
   * 保存到历史记录
   */
  _saveToHistory(trade) {
    try {
      const history = wx.getStorageSync('claw_history') || []
      history.unshift({
        request_id: trade.request_id,
        item_name: trade.item_name,
        max_price: trade.max_price,
        offer_count: trade.offer_count || 0,
        ts: Date.now()
      })
      wx.setStorageSync('claw_history', history.slice(0, 50))
      this.eventBus.emit('history:updated', history)
    } catch (error) {
      console.error('[TradeEngine] 保存历史失败:', error)
    }
  }

  /**
   * 获取当前询价
   */
  getCurrentTrade() {
    return this.currentTrade
  }

  /**
   * 重置询价
   */
  reset() {
    this.currentTrade = null
    this.stateManager.setState({
      currentTrade: null,
      tradeStatus: 'idle',
      offers: []
    })
    this.eventBus.emit('trade:reset')
  }
}

// ==================== 导出 ====================

module.exports = {
  EventBus,
  StateManager,
  CacheManager,
  PerformanceMonitor,
  TradeEngine
}
