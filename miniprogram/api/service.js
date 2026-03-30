/**
 * Project Claw 小程序 API 服务层
 * 统一的网络请求管理、错误处理、拦截器
 */

const app = getApp()

// API 基础配置
const API_CONFIG = {
  timeout: 15000,
  retryCount: 3,
  retryDelay: 1000
}

// 请求拦截器
class APIService {
  constructor() {
    this.requestQueue = []
    this.isRefreshing = false
  }

  /**
   * 统一的 HTTP 请求方法
   */
  async request(options) {
    const {
      url,
      method = 'GET',
      data = null,
      header = {},
      timeout = API_CONFIG.timeout,
      showLoading = true,
      retryCount = 0
    } = options

    // 显示加载提示
    if (showLoading) {
      wx.showLoading({ title: '加载中...' })
    }

    try {
      // 添加认证 token
      const sessionId = wx.getStorageSync('sessionId')
      if (sessionId) {
        header['Authorization'] = `Bearer ${sessionId}`
      }

      // 添加通用请求头
      header['Content-Type'] = 'application/json'
      header['X-Client-Type'] = 'miniprogram'
      header['X-Client-Version'] = '1.0.0'

      // 构建完整 URL
      const fullUrl = url.startsWith('http') 
        ? url 
        : `${app.globalData.serverBase}${url}`

      // 发送请求
      const response = await new Promise((resolve, reject) => {
        wx.request({
          url: fullUrl,
          method,
          data,
          header,
          timeout,
          success: (res) => {
            wx.hideLoading()
            
            // 处理响应
            if (res.statusCode === 200) {
              resolve(res.data)
            } else if (res.statusCode === 401) {
              // 会话过期，重新登录
              this.handleUnauthorized()
              reject(new Error('会话已过期，请重新登录'))
            } else {
              reject(new Error(res.data?.message || `请求失败: ${res.statusCode}`))
            }
          },
          fail: (err) => {
            wx.hideLoading()
            
            // 重试逻辑
            if (retryCount < API_CONFIG.retryCount) {
              console.warn(`请求失败，${API_CONFIG.retryDelay}ms 后重试...`)
              return new Promise(resolve => {
                setTimeout(() => {
                  resolve(this.request({ ...options, retryCount: retryCount + 1 }))
                }, API_CONFIG.retryDelay)
              })
            }
            
            reject(err)
          }
        })
      })

      return response
    } catch (error) {
      console.error('API 请求错误:', error)
      wx.showToast({
        title: error.message || '请求失败',
        icon: 'error',
        duration: 2000
      })
      throw error
    }
  }

  /**
   * GET 请求
   */
  get(url, options = {}) {
    return this.request({ ...options, url, method: 'GET' })
  }

  /**
   * POST 请求
   */
  post(url, data, options = {}) {
    return this.request({ ...options, url, method: 'POST', data })
  }

  /**
   * PUT 请求
   */
  put(url, data, options = {}) {
    return this.request({ ...options, url, method: 'PUT', data })
  }

  /**
   * DELETE 请求
   */
  delete(url, options = {}) {
    return this.request({ ...options, url, method: 'DELETE' })
  }

  /**
   * 处理未授权错误
   */
  handleUnauthorized() {
    wx.removeStorageSync('sessionId')
    app.globalData.sessionId = null
    app.globalData.userInfo = null
    
    wx.showModal({
      title: '会话过期',
      content: '您的登录已过期，请重新登录',
      showCancel: false,
      success: () => {
        wx.reLaunch({ url: '/pages/index/index' })
      }
    })
  }
}

// 创建全局 API 实例
const apiService = new APIService()

// ==================== 认证 API ====================

const authAPI = {
  /**
   * 登录
   */
  login(code) {
    return apiService.post('/auth/login', { code }, { showLoading: true })
  },

  /**
   * 获取用户信息
   */
  getUserInfo() {
    return apiService.get('/auth/user-info', { showLoading: false })
  },

  /**
   * 登出
   */
  logout() {
    return apiService.post('/auth/logout', {}, { showLoading: true })
  }
}

// ==================== 订单 API ====================

const orderAPI = {
  /**
   * 获取订单列表
   */
  getOrderList(page = 1, pageSize = 10) {
    return apiService.get(`/orders/list?page=${page}&pageSize=${pageSize}`, { showLoading: true })
  },

  /**
   * 获取订单详情
   */
  getOrderDetail(orderId) {
    return apiService.get(`/orders/${orderId}`, { showLoading: true })
  },

  /**
   * 创建订单
   */
  createOrder(data) {
    return apiService.post('/orders', data, { showLoading: true })
  },

  /**
   * 更新订单
   */
  updateOrder(orderId, data) {
    return apiService.put(`/orders/${orderId}`, data, { showLoading: true })
  },

  /**
   * 取消订单
   */
  cancelOrder(orderId) {
    return apiService.delete(`/orders/${orderId}`, { showLoading: true })
  }
}

// ==================== 成本 API ====================

const costAPI = {
  /**
   * 获取成本分析
   */
  getCostAnalysis(startDate, endDate) {
    return apiService.get(`/cost/analysis?start_date=${startDate}&end_date=${endDate}`, { showLoading: true })
  },

  /**
   * 获取每日成本统计
   */
  getDailyStats(days = 30) {
    return apiService.get(`/cost/daily-stats?days=${days}`, { showLoading: false })
  }
}

// ==================== 舰队 API ====================

const fleetAPI = {
  /**
   * 获取舰队状态
   */
  getFleetStatus() {
    return apiService.get('/fleet/status', { showLoading: false })
  },

  /**
   * 获取待审批任务
   */
  getPendingTasks(limit = 100) {
    return apiService.get(`/fleet/pending-tasks?limit=${limit}`, { showLoading: true })
  },

  /**
   * 批准任务
   */
  approveTask(taskId, decision, overrideParams = null) {
    return apiService.post('/fleet/approve-task', {
      task_id: taskId,
      decision,
      override_params: overrideParams
    }, { showLoading: true })
  }
}

// 导出 API 服务
module.exports = {
  apiService,
  authAPI,
  orderAPI,
  costAPI,
  fleetAPI
}
