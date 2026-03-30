/**
 * Project Claw 小程序应用启动
 * 极客风范的启动系统
 */

const { authAPI, orderAPI } = require('./api/service')
const { NegotiationEngine, WebSocketAdapter } = require('./core/engine')
const { StateManager, CacheManager, EventBus, PerformanceMonitor } = require('./core/state')

/**
 * 应用启动管理器
 */
class AppBootstrapper {
  constructor() {
    this.stateManager = new StateManager({
      user: null,
      sessionId: null,
      isLoggedIn: false,
      isLoading: false,
      error: null,
      orders: [],
      currentIntent: null,
      dialogueState: 'idle' // idle | connecting | active | disconnecting
    })

    this.cacheManager = new CacheManager(100)
    this.eventBus = new EventBus()
    this.performanceMonitor = new PerformanceMonitor()
    
    this.negotiationEngine = null
    this.wsAdapter = null
  }

  /**
   * 启动应用
   */
  async bootstrap() {
    console.log('[AppBootstrapper] 🚀 应用启动中...')
    this.performanceMonitor.mark('app_startup')

    try {
      // 第 1 步：初始化系统
      await this._initializeSystem()

      // 第 2 步：检查认证
      await this._checkAuthentication()

      // 第 3 步：加载初始数据
      await this._loadInitialData()

      // 第 4 步：启动后台服务
      await this._startBackgroundServices()

      this.performanceMonitor.measure('app_startup')
      console.log('[AppBootstrapper] ✓ 应用启动完成')
      
      this.eventBus.emit('app:ready')
      return true
    } catch (error) {
      console.error('[AppBootstrapper] ✗ 应用启动失败:', error)
      this.stateManager.setState({ error: error.message })
      this.eventBus.emit('app:error', error)
      return false
    }
  }

  /**
   * 初始化系统
   */
  async _initializeSystem() {
    console.log('[AppBootstrapper] 初始化系统...')

    // 初始化 WebSocket 适配器
    const app = getApp()
    this.wsAdapter = new WebSocketAdapter(app.globalData.wsBase)

    // 初始化谈判引擎
    this.negotiationEngine = new NegotiationEngine(null, this.wsAdapter)

    // 监听 WebSocket 事件
    this.wsAdapter.on('open', () => {
      console.log('[AppBootstrapper] WebSocket 已连接')
      this.stateManager.setState({ dialogueState: 'active' })
      this.eventBus.emit('ws:open')
    })

    this.wsAdapter.on('close', () => {
      console.log('[AppBootstrapper] WebSocket 已断开')
      this.stateManager.setState({ dialogueState: 'idle' })
      this.eventBus.emit('ws:close')
    })

    this.wsAdapter.on('error', () => {
      console.error('[AppBootstrapper] WebSocket 错误')
      this.stateManager.setState({ dialogueState: 'idle', error: 'WebSocket 连接失败' })
      this.eventBus.emit('ws:error')
    })

    // 监听状态变化
    this.stateManager.subscribe('isLoggedIn', (value) => {
      this.eventBus.emit('auth:changed', value)
    })

    this.stateManager.subscribe('orders', (value) => {
      this.eventBus.emit('orders:updated', value)
    })

    console.log('[AppBootstrapper] ✓ 系统初始化完成')
  }

  /**
   * 检查认证
   */
  async _checkAuthentication() {
    console.log('[AppBootstrapper] 检查认证...')
    this.performanceMonitor.mark('auth_check')

    try {
      const sessionId = wx.getStorageSync('sessionId')

      if (!sessionId) {
        console.log('[AppBootstrapper] 未找到会话，执行登录')
        await this._performLogin()
      } else {
        // 验证会话
        const response = await authAPI.getUserInfo()

        if (response.code === 200) {
          this.stateManager.setState({
            sessionId,
            user: response.data,
            isLoggedIn: true
          })
          console.log('[AppBootstrapper] ✓ 会话验证成功')
        } else {
          throw new Error('会话验证失败')
        }
      }

      this.performanceMonitor.measure('auth_check')
    } catch (error) {
      console.error('[AppBootstrapper] 认证失败:', error)
      throw error
    }
  }

  /**
   * 执行登录
   */
  async _performLogin() {
    console.log('[AppBootstrapper] 执行登录...')
    this.performanceMonitor.mark('login')

    try {
      // 获取登录 code
      const loginRes = await new Promise((resolve, reject) => {
        wx.login({
          success: resolve,
          fail: reject
        })
      })

      if (!loginRes.code) {
        throw new Error('获取登录 code 失败')
      }

      // 发送 code 到后端
      const response = await authAPI.login(loginRes.code)

      if (response.code === 200) {
        const { session_id, user_info } = response.data

        // 保存会话
        wx.setStorageSync('sessionId', session_id)
        wx.setStorageSync('userInfo', JSON.stringify(user_info))

        this.stateManager.setState({
          sessionId: session_id,
          user: user_info,
          isLoggedIn: true
        })

        console.log('[AppBootstrapper] ✓ 登录成功')
        this.performanceMonitor.measure('login')
      } else {
        throw new Error(response.message || '登录失败')
      }
    } catch (error) {
      console.error('[AppBootstrapper] 登录失败:', error)
      throw error
    }
  }

  /**
   * 加载初始数据
   */
  async _loadInitialData() {
    console.log('[AppBootstrapper] 加载初始数据...')
    this.performanceMonitor.mark('load_data')

    try {
      this.stateManager.setState({ isLoading: true })

      // 加载订单列表
      const response = await orderAPI.getOrderList(1, 10)

      if (response.code === 200) {
        this.stateManager.setState({
          orders: response.data.orders || [],
          isLoading: false
        })

        console.log(`[AppBootstrapper] ✓ 加载了 ${response.data.orders.length} 个订单`)
        this.performanceMonitor.measure('load_data')
      } else {
        throw new Error(response.message || '加载数据失败')
      }
    } catch (error) {
      console.error('[AppBootstrapper] 加载数据失败:', error)
      this.stateManager.setState({ isLoading: false, error: error.message })
    }
  }

  /**
   * 启动后台服务
   */
  async _startBackgroundServices() {
    console.log('[AppBootstrapper] 启动后台服务...')

    // 定期清理缓存
    setInterval(() => {
      this.cacheManager.cleanup()
    }, 60000) // 每分钟清理一次

    // 定期输出性能统计
    setInterval(() => {
      const stats = this.performanceMonitor.getAllStats()
      console.log('[AppBootstrapper] 性能统计:', stats)
    }, 300000) // 每 5 分钟输出一次

    console.log('[AppBootstrapper] ✓ 后台服务已启动')
  }

  /**
   * 获取状态管理器
   */
  getStateManager() {
    return this.stateManager
  }

  /**
   * 获取缓存管理器
   */
  getCacheManager() {
    return this.cacheManager
  }

  /**
   * 获取事件总线
   */
  getEventBus() {
    return this.eventBus
  }

  /**
   * 获取谈判引擎
   */
  getNegotiationEngine() {
    return this.negotiationEngine
  }

  /**
   * 获取性能监控器
   */
  getPerformanceMonitor() {
    return this.performanceMonitor
  }

  /**
   * 获取应用状态
   */
  getAppState() {
    return this.stateManager.getState()
  }

  /**
   * 登出
   */
  async logout() {
    console.log('[AppBootstrapper] 执行登出...')

    try {
      await authAPI.logout()

      // 清除本地数据
      wx.removeStorageSync('sessionId')
      wx.removeStorageSync('userInfo')

      // 重置状态
      this.stateManager.setState({
        user: null,
        sessionId: null,
        isLoggedIn: false,
        orders: [],
        currentIntent: null
      })

      console.log('[AppBootstrapper] ✓ 登出成功')
      this.eventBus.emit('auth:logout')

      // 返回首页
      wx.reLaunch({ url: '/pages/index/index' })
    } catch (error) {
      console.error('[AppBootstrapper] 登出失败:', error)
    }
  }
}

// 创建全局应用启动器实例
const appBootstrapper = new AppBootstrapper()

// ==================== 导出 ====================

module.exports = {
  AppBootstrapper,
  appBootstrapper
}
