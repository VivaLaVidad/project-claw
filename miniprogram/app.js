/**
 * Project Claw 小程序应用入口
 * 极客风范 + 高效 + 完美适配项目架构
 * 
 * ╔═══════════════════════════════════════════════════════════╗
 * ║  Project Claw - 龙虾盒子智能谈判系统                      ║
 * ║  MiniProgram Core - v1.0.0                                ║
 * ║  Powered by DDD + Hexagonal Architecture                  ║
 * ╚═══════════════════════════════════════════════════════════╝
 */

const { appBootstrapper } = require('./core/bootstrap')
const { authAPI } = require('./api/service')

App({
  // ==================== 全局数据 ====================
  
  globalData: {
    // 服务器配置
    serverBase: 'http://localhost:8765',
    wsBase: 'ws://localhost:8765',
    
    // 应用信息
    appVersion: '1.0.0',
    appName: 'Project Claw',
    
    // 系统信息
    platform: wx.getSystemInfoSync().platform,
    systemInfo: null,
    
    // 应用启动器
    bootstrapper: appBootstrapper,
    
    // 快捷访问
    stateManager: null,
    cacheManager: null,
    eventBus: null,
    negotiationEngine: null
  },

  // ==================== 应用生命周期 ====================

  /**
   * 应用启动
   */
  async onLaunch() {
    console.log(`
╔════════════════════════════════════════════════════════════╗
║                                                            ║
║  🦞 Project Claw MiniProgram                              ║
║  Version: ${this.globalData.appVersion}                                      ║
║  Platform: ${this.globalData.platform}                                    ║
║                                                            ║
║  Initializing...                                           ║
║                                                            ║
╚════════════════════════════════════════════════════════════╝
    `)

    try {
      // 获取系统信息
      this.globalData.systemInfo = wx.getSystemInfoSync()
      console.log('[App] 系统信息:', this.globalData.systemInfo)

      // 启动应用
      const success = await this.globalData.bootstrapper.bootstrap()

      if (success) {
        // 将管理器挂载到全局数据
        this.globalData.stateManager = this.globalData.bootstrapper.getStateManager()
        this.globalData.cacheManager = this.globalData.bootstrapper.getCacheManager()
        this.globalData.eventBus = this.globalData.bootstrapper.getEventBus()
        this.globalData.negotiationEngine = this.globalData.bootstrapper.getNegotiationEngine()

        console.log('[App] ✓ 应用启动成功')
      } else {
        console.error('[App] ✗ 应用启动失败')
        this._showErrorPage('应用启动失败，请重试')
      }
    } catch (error) {
      console.error('[App] 应用启动异常:', error)
      this._showErrorPage('应用启动异常')
    }
  },

  /**
   * 应用显示
   */
  onShow() {
    console.log('[App] 应用显示')
    
    // 刷新用户信息
    this._refreshUserInfo()
    
    // 发出事件
    this.globalData.eventBus?.emit('app:show')
  },

  /**
   * 应用隐藏
   */
  onHide() {
    console.log('[App] 应用隐藏')
    
    // 发出事件
    this.globalData.eventBus?.emit('app:hide')
  },

  /**
   * 应用错误
   */
  onError(error) {
    console.error('[App] 应用错误:', error)
    
    // 发出事件
    this.globalData.eventBus?.emit('app:error', error)
    
    // 上报错误
    this._reportError(error)
  },

  /**
   * 页面不存在
   */
  onPageNotFound(res) {
    console.error('[App] 页面不存在:', res.path)
    
    wx.redirectTo({
      url: '/pages/index/index'
    })
  },

  // ==================== 工具方法 ====================

  /**
   * 刷新用户信息
   */
  async _refreshUserInfo() {
    try {
      const response = await authAPI.getUserInfo()
      
      if (response.code === 200) {
        this.globalData.stateManager?.setState({
          user: response.data
        })
      }
    } catch (error) {
      console.warn('[App] 刷新用户信息失败:', error)
    }
  },

  /**
   * 显示错误页面
   */
  _showErrorPage(message) {
    wx.showModal({
      title: '错误',
      content: message,
      showCancel: false,
      success: () => {
        wx.exitMiniProgram()
      }
    })
  },

  /**
   * 上报错误
   */
  _reportError(error) {
    // 这里可以集成错误追踪服务
    console.log('[App] 错误已记录:', {
      message: error.message,
      stack: error.stack,
      timestamp: Date.now()
    })
  },

  // ==================== 公共方法 ====================

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
   * 获取事件总线
   */
  getEventBus() {
    return this.globalData.eventBus
  },

  /**
   * 获取谈判引擎
   */
  getNegotiationEngine() {
    return this.globalData.negotiationEngine
  },

  /**
   * 获取应用状态
   */
  getAppState() {
    return this.globalData.stateManager?.getState()
  },

  /**
   * 检查登录状态
   */
  isLoggedIn() {
    return this.globalData.stateManager?.getState('isLoggedIn') || false
  },

  /**
   * 获取用户信息
   */
  getUserInfo() {
    return this.globalData.stateManager?.getState('user')
  },

  /**
   * 获取会话 ID
   */
  getSessionId() {
    return this.globalData.stateManager?.getState('sessionId')
  },

  /**
   * 执行登出
   */
  async logout() {
    return await this.globalData.bootstrapper.logout()
  },

  /**
   * 显示加载提示
   */
  showLoading(title = '加载中...') {
    wx.showLoading({
      title,
      mask: true
    })
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
    wx.showToast({
      title,
      icon,
      duration
    })
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
  },

  /**
   * 获取性能统计
   */
  getPerformanceStats() {
    return this.globalData.bootstrapper?.getPerformanceMonitor().getAllStats()
  },

  /**
   * 获取缓存统计
   */
  getCacheStats() {
    return this.globalData.cacheManager?.getStats()
  },

  /**
   * 获取应用统计
   */
  getAppStats() {
    return {
      performance: this.getPerformanceStats(),
      cache: this.getCacheStats(),
      state: this.globalData.stateManager?.getHistory(5)
    }
  }
})

console.log(`
╔════════════════════════════════════════════════════════════╗
║                                                            ║
║  ✓ Project Claw MiniProgram 已加载                        ║
║                                                            ║
║  核心模块:                                                 ║
║  • DDD (Domain-Driven Design)                             ║
║  • 六边形架构 (Hexagonal Architecture)                    ║
║  • 事件驱动 (Event-Driven)                                ║
║  • 异步优先 (Async-First)                                 ║
║                                                            ║
║  性能优化:                                                 ║
║  • 智能缓存管理                                            ║
║  • 响应式状态系统                                          ║
║  • 性能监控                                                ║
║  • 错误追踪                                                ║
║                                                            ║
╚════════════════════════════════════════════════════════════╝
`)
