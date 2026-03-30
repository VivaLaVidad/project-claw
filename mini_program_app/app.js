/**
 * Project Claw v14.3 - 极客风范完善版 app.js
 * 完整的应用启动、状态管理、事件驱动
 */

const { loginAndGetToken, setToken, clearToken } = require('./utils/api')
const { EventBus, StateManager, CacheManager, PerformanceMonitor, TradeEngine } = require('./core/engine')

App({
  // ==================== 全局数据 ====================

  globalData: {
    currentTrade: null,
    clientId: '',
    networkOk: true,
    version: '14.3.0',
    
    // 核心模块
    eventBus: null,
    stateManager: null,
    cacheManager: null,
    performanceMonitor: null,
    tradeEngine: null
  },

  // ==================== 应用生命周期 ====================

  onLaunch() {
    console.log(`
╔════════════════════════════════════════════════════════════╗
║                                                            ║
║  🦞 Project Claw MiniProgram v14.3                        ║
║  智能询价系统 - 极客风范完善版                             ║
║                                                            ║
║  Initializing...                                           ║
║                                                            ║
╚════════════════════════════════════════════════════════════╝
    `)

    this.performanceMonitor = new PerformanceMonitor()
    this.performanceMonitor.mark('app_startup')

    try {
      // 初始化核心模块
      this._initializeCore()
      
      // 初始化客户端
      this._initClientId()
      
      // 监听网络
      this._listenNetwork()
      
      // 启动后台服务
      this._startBackgroundServices()

      const duration = this.performanceMonitor.measure('app_startup')
      console.log(`[App] ✓ 应用启动完成 (${duration}ms)`)
      
      this.globalData.eventBus.emit('app:ready')
    } catch (error) {
      console.error('[App] ✗ 应用启动失败:', error)
      this.globalData.eventBus?.emit('app:error', error)
    }
  },

  onShow() {
    console.log('[App] 应用显示')
    
    const cid = this.globalData.clientId
    if (cid) {
      loginAndGetToken(cid).catch(() => {})
    }
    
    this.globalData.eventBus?.emit('app:show')
  },

  onHide() {
    console.log('[App] 应用隐藏')
    this.globalData.eventBus?.emit('app:hide')
  },

  onError(err) {
    console.error('[App] 应用错误:', err)
    this.globalData.eventBus?.emit('app:error', err)
  },

  onUnhandledRejection(res) {
    console.error('[App] Unhandled Promise Rejection:', res.reason)
    this.globalData.eventBus?.emit('app:rejection', res.reason)
  },

  // ==================== 初始化 ====================

  /**
   * 初始化核心模块
   */
  _initializeCore() {
    console.log('[App] 初始化核心模块...')

    this.globalData.eventBus = new EventBus()
    this.globalData.stateManager = new StateManager({
      clientId: '',
      networkOk: true,
      currentTrade: null,
      tradeStatus: 'idle',
      offers: [],
      merchants: 0,
      healthStatus: 'unknown'
    })
    this.globalData.cacheManager = new CacheManager(100)
    this.globalData.performanceMonitor = new PerformanceMonitor()
    this.globalData.tradeEngine = new TradeEngine(
      this.globalData.eventBus,
      this.globalData.stateManager,
      this.globalData.cacheManager
    )

    // 监听状态变化
    this.globalData.stateManager.subscribe('currentTrade', (trade) => {
      this.globalData.currentTrade = trade
    })

    console.log('[App] ✓ 核心模块初始化完成')
  },

  /**
   * 初始化客户端 ID
   */
  _initClientId() {
    console.log('[App] 初始化客户端 ID...')

    const cached = wx.getStorageSync('claw_client_id')
    if (cached) {
      this.globalData.clientId = cached
      this.globalData.stateManager.setState({ clientId: cached })
      loginAndGetToken(cached).catch(() => {})
      console.log('[App] ✓ 使用缓存的客户端 ID:', cached)
      return
    }

    wx.login({
      success: (res) => {
        const code = res && res.code ? res.code.slice(0, 12) : String(Date.now())
        const suffix = Math.random().toString(36).slice(2, 8)
        const clientId = `wx-${code}-${suffix}`
        this._saveClientId(clientId)
      },
      fail: () => {
        const clientId = `anon-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
        this._saveClientId(clientId)
      }
    })
  },

  _saveClientId(clientId) {
    wx.setStorageSync('claw_client_id', clientId)
    this.globalData.clientId = clientId
    this.globalData.stateManager.setState({ clientId })
    loginAndGetToken(clientId).catch(() => {})
    console.log('[App] ✓ 客户端 ID 已保存:', clientId)
  },

  /**
   * 监听网络状态
   */
  _listenNetwork() {
    console.log('[App] 监听网络状态...')

    wx.getNetworkType({
      success: (res) => {
        const networkOk = res.networkType !== 'none'
        this.globalData.networkOk = networkOk
        this.globalData.stateManager.setState({ networkOk })
      }
    })

    wx.onNetworkStatusChange((res) => {
      this.globalData.networkOk = res.isConnected
      this.globalData.stateManager.setState({ networkOk: res.isConnected })
      
      if (!res.isConnected) {
        wx.showToast({ title: '网络已断开', icon: 'none', duration: 2000 })
        this.globalData.eventBus.emit('network:offline')
      } else {
        this.globalData.eventBus.emit('network:online')
      }
    })

    console.log('[App] ✓ 网络监听已启动')
  },

  /**
   * 启动后台服务
   */
  _startBackgroundServices() {
    console.log('[App] 启动后台服务...')

    // 定期清理缓存
    setInterval(() => {
      const cleaned = this.globalData.cacheManager.cleanup()
      if (cleaned > 0) {
        console.log(`[App] 清除了 ${cleaned} 个过期缓存`)
      }
    }, 60000)

    // 定期输出性能统计
    setInterval(() => {
      const stats = this.globalData.performanceMonitor.getAllStats()
      console.log('[App] 性能统计:', stats)
    }, 300000)

    console.log('[App] ✓ 后台服务已启动')
  },

  // ==================== 公共方法 ====================

  /**
   * 获取事件总线
   */
  getEventBus() {
    return this.globalData.eventBus
  },

  /**
   * 获取状态管理器
   */
  getStateManager() {
    return this.globalData.stateManager
  },

  /**
   * 获取缓存管理器
   */
  getCacheManager() {
    return this.globalData.cacheManager
  },

  /**
   * 获取性能监控器
   */
  getPerformanceMonitor() {
    return this.globalData.performanceMonitor
  },

  /**
   * 获取询价引擎
   */
  getTradeEngine() {
    return this.globalData.tradeEngine
  },

  /**
   * 获取应用状态
   */
  getAppState() {
    return this.globalData.stateManager.getState()
  },

  /**
   * 获取应用统计
   */
  getAppStats() {
    return {
      performance: this.globalData.performanceMonitor.getAllStats(),
      cache: this.globalData.cacheManager.getStats(),
      state: this.globalData.stateManager.history.slice(-5)
    }
  },

  /**
   * 显示加载提示
   */
  showLoading(title = '加载中...') {
    wx.showLoading({ title, mask: true })
  },

  /**
   * 隐藏加载提示
   */
  hideLoading() {
    wx.hideLoading()
  },

  /**
   * 显示提示
   */
  showToast(title, icon = 'none', duration = 2000) {
    wx.showToast({ title, icon, duration })
  },

  /**
   * 显示确认对话框
   */
  showConfirm(title, content) {
    return new Promise((resolve) => {
      wx.showModal({
        title,
        content,
        success: (res) => {
          resolve(res.confirm)
        }
      })
    })
  }
})

console.log(`
╔════════════════════════════════════════════════════════════╗
║                                                            ║
║  ✓ Project Claw MiniProgram 已加载                        ║
║                                                            ║
║  核心特性:                                                 ║
║  • 事件驱动架构 (Event-Driven)                            ║
║  • 响应式状态管理 (Reactive State)                        ║
║  • 智能缓存系统 (Smart Cache)                             ║
║  • 性能监控 (Performance Monitor)                         ║
║  • 询价引擎 (Trade Engine)                                ║
║                                                            ║
║  性能优化:                                                 ║
║  • LRU 缓存策略                                            ║
║  • 自动过期清理                                            ║
║  • 实时性能追踪                                            ║
║  • 完整的错误处理                                          ║
║                                                            ║
╚════════════════════════════════════════════════════════════╝
`)
