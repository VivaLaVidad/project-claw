/**
 * 首页 - 订单列表
 * 工业级标准实现
 */

const { orderAPI } = require('../../api/service')
const app = getApp()

Page({
  data: {
    orders: [],
    loading: false,
    page: 1,
    pageSize: 10,
    hasMore: true,
    userInfo: null,
    refreshing: false
  },

  /**
   * 页面加载
   */
  onLoad() {
    console.log('📄 首页加载')
    this.loadUserInfo()
    this.loadOrders()
  },

  /**
   * 页面显示
   */
  onShow() {
    // 每次显示时刷新用户信息
    this.loadUserInfo()
  },

  /**
   * 加载用户信息
   */
  loadUserInfo() {
    const userInfo = app.getUserInfo()
    if (userInfo) {
      this.setData({ userInfo })
    }
  },

  /**
   * 加载订单列表
   */
  async loadOrders(isRefresh = false) {
    if (this.data.loading) return

    try {
      this.setData({ loading: true })

      // 重置分页
      if (isRefresh) {
        this.setData({ page: 1, orders: [], hasMore: true })
      }

      const response = await orderAPI.getOrderList(this.data.page, this.data.pageSize)

      if (response.code === 200) {
        const newOrders = response.data.orders || []
        const orders = isRefresh ? newOrders : [...this.data.orders, ...newOrders]

        this.setData({
          orders,
          hasMore: newOrders.length === this.data.pageSize,
          page: this.data.page + 1
        })

        console.log(`✓ 加载 ${newOrders.length} 个订单`)
      } else {
        throw new Error(response.message || '加载订单失败')
      }
    } catch (error) {
      console.error('加载订单失败:', error)
      wx.showToast({
        title: '加载失败',
        icon: 'error'
      })
    } finally {
      this.setData({ loading: false, refreshing: false })
      wx.stopPullDownRefresh()
    }
  },

  /**
   * 下拉刷新
   */
  onPullDownRefresh() {
    console.log('🔄 下拉刷新')
    this.setData({ refreshing: true })
    this.loadOrders(true)
  },

  /**
   * 上拉加载更多
   */
  onReachBottom() {
    if (this.data.hasMore && !this.data.loading) {
      console.log('📥 加载更多')
      this.loadOrders()
    }
  },

  /**
   * 查看订单详情
   */
  viewOrderDetail(e) {
    const orderId = e.currentTarget.dataset.orderId
    wx.navigateTo({
      url: `/pages/orders/orders?orderId=${orderId}`
    })
  },

  /**
   * 启动语音对讲
   */
  startVoiceChat(e) {
    const orderId = e.currentTarget.dataset.orderId
    wx.navigateTo({
      url: `/pages/dialogue/dialogue?orderId=${orderId}`
    })
  },

  /**
   * 创建新订单
   */
  createOrder() {
    wx.navigateTo({
      url: '/pages/orders/orders?action=create'
    })
  },

  /**
   * 用户头像点击 - 显示用户菜单
   */
  showUserMenu() {
    wx.showActionSheet({
      itemList: ['个人信息', '设置', '登出'],
      success: (res) => {
        switch (res.tapIndex) {
          case 0:
            wx.navigateTo({ url: '/pages/merchant/merchant' })
            break
          case 1:
            wx.showToast({ title: '设置功能开发中', icon: 'none' })
            break
          case 2:
            this.logout()
            break
        }
      }
    })
  },

  /**
   * 登出
   */
  logout() {
    wx.showModal({
      title: '确认登出',
      content: '确定要登出吗？',
      success: (res) => {
        if (res.confirm) {
          app.logout()
        }
      }
    })
  }
})
