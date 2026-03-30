/**
 * Project Claw 小程序状态管理
 * 极客风范的响应式状态系统
 */

/**
 * 事件驱动的状态管理器
 * 使用观察者模式实现响应式更新
 */
class StateManager {
  constructor(initialState = {}) {
    this.state = initialState
    this.subscribers = new Map()
    this.history = []
    this.maxHistory = 50
  }

  /**
   * 获取状态
   */
  getState(path) {
    if (!path) return this.state
    
    return path.split('.').reduce((obj, key) => obj?.[key], this.state)
  }

  /**
   * 设置状态（带历史记录）
   */
  setState(updates, metadata = {}) {
    const oldState = JSON.parse(JSON.stringify(this.state))
    
    // 深度合并
    this.state = this._deepMerge(this.state, updates)

    // 记录历史
    this.history.push({
      timestamp: Date.now(),
      oldState,
      newState: JSON.parse(JSON.stringify(this.state)),
      updates,
      metadata
    })

    // 限制历史记录大小
    if (this.history.length > this.maxHistory) {
      this.history.shift()
    }

    // 通知订阅者
    this._notifySubscribers(updates)

    console.log('[StateManager] 状态已更新:', updates)
  }

  /**
   * 订阅状态变化
   */
  subscribe(path, callback) {
    if (!this.subscribers.has(path)) {
      this.subscribers.set(path, [])
    }
    
    this.subscribers.get(path).push(callback)

    // 返回取消订阅函数
    return () => {
      const callbacks = this.subscribers.get(path)
      const index = callbacks.indexOf(callback)
      if (index > -1) {
        callbacks.splice(index, 1)
      }
    }
  }

  /**
   * 通知订阅者
   */
  _notifySubscribers(updates) {
    // 通知所有订阅者
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

  /**
   * 检查路径是否匹配
   */
  _pathMatches(path, updates) {
    if (path === '*') return true
    
    const pathParts = path.split('.')
    const updateKeys = Object.keys(updates)

    return updateKeys.some(key => {
      return pathParts[0] === key || key.startsWith(pathParts[0] + '.')
    })
  }

  /**
   * 深度合并对象
   */
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

  /**
   * 获取历史记录
   */
  getHistory(limit = 10) {
    return this.history.slice(-limit)
  }

  /**
   * 撤销操作
   */
  undo() {
    if (this.history.length === 0) return false

    const record = this.history.pop()
    this.state = record.oldState
    this._notifySubscribers(record.oldState)

    console.log('[StateManager] 已撤销操作')
    return true
  }
}

/**
 * 缓存管理器
 * 智能缓存策略
 */
class CacheManager {
  constructor(maxSize = 100) {
    this.cache = new Map()
    this.maxSize = maxSize
    this.accessCount = new Map()
  }

  /**
   * 获取缓存
   */
  get(key) {
    if (this.cache.has(key)) {
      // 更新访问计数
      this.accessCount.set(key, (this.accessCount.get(key) || 0) + 1)
      return this.cache.get(key)
    }
    return null
  }

  /**
   * 设置缓存
   */
  set(key, value, ttl = 3600000) {
    // 如果缓存已满，删除最少使用的项
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

  /**
   * 清除过期缓存
   */
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

    console.log(`[CacheManager] 清除了 ${cleaned} 个过期缓存`)
  }

  /**
   * 清空缓存
   */
  clear() {
    this.cache.clear()
    this.accessCount.clear()
    console.log('[CacheManager] 缓存已清空')
  }

  /**
   * 获取缓存统计
   */
  getStats() {
    return {
      size: this.cache.size,
      maxSize: this.maxSize,
      hitRate: this._calculateHitRate()
    }
  }

  /**
   * 计算命中率
   */
  _calculateHitRate() {
    const total = Array.from(this.accessCount.values()).reduce((a, b) => a + b, 0)
    return total > 0 ? (total / this.cache.size).toFixed(2) : 0
  }
}

/**
 * 事件总线
 * 全局事件通信
 */
class EventBus {
  constructor() {
    this.events = new Map()
  }

  /**
   * 监听事件
   */
  on(eventName, callback) {
    if (!this.events.has(eventName)) {
      this.events.set(eventName, [])
    }

    this.events.get(eventName).push(callback)

    // 返回取消监听函数
    return () => {
      const callbacks = this.events.get(eventName)
      const index = callbacks.indexOf(callback)
      if (index > -1) {
        callbacks.splice(index, 1)
      }
    }
  }

  /**
   * 监听一次事件
   */
  once(eventName, callback) {
    const unsubscribe = this.on(eventName, (...args) => {
      callback(...args)
      unsubscribe()
    })

    return unsubscribe
  }

  /**
   * 发出事件
   */
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

    console.log(`[EventBus] 事件已发出: ${eventName}`)
  }

  /**
   * 移除所有监听
   */
  clear(eventName) {
    if (eventName) {
      this.events.delete(eventName)
    } else {
      this.events.clear()
    }
  }
}

/**
 * 性能监控器
 * 追踪关键性能指标
 */
class PerformanceMonitor {
  constructor() {
    this.metrics = new Map()
    this.marks = new Map()
  }

  /**
   * 标记开始
   */
  mark(name) {
    this.marks.set(name, Date.now())
  }

  /**
   * 标记结束并记录
   */
  measure(name) {
    if (!this.marks.has(name)) {
      console.warn(`[PerformanceMonitor] 未找到标记: ${name}`)
      return
    }

    const duration = Date.now() - this.marks.get(name)
    
    if (!this.metrics.has(name)) {
      this.metrics.set(name, [])
    }

    this.metrics.get(name).push(duration)
    this.marks.delete(name)

    console.log(`[PerformanceMonitor] ${name}: ${duration}ms`)
  }

  /**
   * 获取统计信息
   */
  getStats(name) {
    if (!this.metrics.has(name)) {
      return null
    }

    const durations = this.metrics.get(name)
    const avg = durations.reduce((a, b) => a + b, 0) / durations.length
    const min = Math.min(...durations)
    const max = Math.max(...durations)

    return {
      count: durations.length,
      avg: avg.toFixed(2),
      min,
      max
    }
  }

  /**
   * 获取所有统计
   */
  getAllStats() {
    const stats = {}
    for (const [name, durations] of this.metrics) {
      stats[name] = this.getStats(name)
    }
    return stats
  }

  /**
   * 清空数据
   */
  clear() {
    this.metrics.clear()
    this.marks.clear()
  }
}

// ==================== 导出 ====================

module.exports = {
  StateManager,
  CacheManager,
  EventBus,
  PerformanceMonitor
}
