/**
 * Project Claw 小程序主应用
 * 工业级标准实现
 */

const { authAPI } = require('./api/service')

App({
  globalData: {
    userInfo: null,
    sessionId: null,
    serverBase: 'http://localhost:8765',
    wsBase: 'ws://localhost:8765',
    appVersion: '1.0.0',
    platform: wx.getSystemInfoSync().platform
  },

  /**
   * 应用启动
   */
  onLaunch() {
    console.log('🚀 Project Claw 小程序启动')
    
    // 初始化应用
    this.initApp()
  },

  /**
   * 初始化应用
   */
  async initApp() {
    try {
      // 第 1 步：检查登录状态
      const sessionId = wx.getStorageSync('sessionId')
      
      if (sessionId) {
        this.globalData.sessionId = sessionId
        
        // 第 2 步：验证会话是否有效
        await this.verifySession()
      } else {
        // 第 3 步：执行登录
        await this.login()
      }
      
      console.log('✓ 应用初始化完成')
    } catch (error) {
      console.error('应用初始化失败:', error)
      wx.showToast({
        title: '初始化失败，请重试',
        icon: 'error'
      })
    }
  },

  /**
   * 验证会话
   */
  async verifySession() {
    try {
      const response = await authAPI.getUserInfo()
      
      if (response.code === 200) {
        this.globalData.userInfo = response.data
        console.log('✓ 会话验证成功')
        return true
      } else {
        throw new Error('会话验证失败')
      }
    } catch (error) {
      console.warn('会话验证失败，重新登录')
      wx.removeStorageSync('sessionId')
      this.globalData.sessionId = null
      return this.login()
    }
  },

  /**
   * 登录
   */
  async login() {
    try {
      // 第 1 步：获取登录 code
      const loginRes = await new Promise((resolve, reject) => {
        wx.login({
          success: resolve,
          fail: reject
        })
      })

      if (!loginRes.code) {
        throw new Error('获取登录 code 失败')
      }

      // 第 2 步：发送 code 到后端
      const response = await authAPI.login(loginRes.code)

      if (response.code === 200) {
        // 第 3 步：保存会话信息
        const { session_id, user_info } = response.data
        
        this.globalData.sessionId = session_id
        this.globalData.userInfo = user_info
        
        wx.setStorageSync('sessionId', session_id)
        wx.setStorageSync('userInfo', JSON.stringify(user_info))
        
        console.log('✓ 登录成功')
        return true
      } else {
        throw new Error(response.message || '登录失败')
      }
    } catch (error) {
      console.error('登录失败:', error)
      wx.showToast({
        title: '登录失败，请重试',
        icon: 'error'
      })
      return false
    }
  },

  /**
   * 登出
   */
  async logout() {
    try {
      await authAPI.logout()
      
      // 清除本地数据
      wx.removeStorageSync('sessionId')
      wx.removeStorageSync('userInfo')
      
      this.globalData.sessionId = null
      this.globalData.userInfo = null
      
      console.log('✓ 登出成功')
      
      // 返回首页
      wx.reLaunch({ url: '/pages/index/index' })
    } catch (error) {
      console.error('登出失败:', error)
    }
  },

  /**
   * 获取用户信息
   */
  getUserInfo() {
    return this.globalData.userInfo
  },

  /**
   * 获取会话 ID
   */
  getSessionId() {
    return this.globalData.sessionId
  },

  /**
   * 检查是否已登录
   */
  isLoggedIn() {
    return !!this.globalData.sessionId && !!this.globalData.userInfo
  },

  /**
   * 应用显示
   */
  onShow() {
    console.log('应用显示')
  },

  /**
   * 应用隐藏
   */
  onHide() {
    console.log('应用隐藏')
  },

  /**
   * 应用错误
   */
  onError(error) {
    console.error('应用错误:', error)
    wx.showToast({
      title: '应用出错',
      icon: 'error'
    })
  }
})
