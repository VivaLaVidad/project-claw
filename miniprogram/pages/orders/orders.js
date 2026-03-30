/**
 * 订单页面
 * 工业级标准实现
 */

const { orderAPI } = require('../../api/service')

Page({
  data: {
    orderId: '',
    order: null,
    loading: false,
    action: 'view' // view 或 create
  },

  /**
   * 页面加载
   */
  onLoad(options) {
    console.log('📋 订单页面加载')
    
    const action = options.action || 'view'
    const orderId = options.orderId || ''

    this.setData({ action, orderId })

    if (action === 'view' && orderId) {
      this.loadOrderDetail()
    }
  },

  /**
   * 加载订单详情
   */
  async loadOrderDetail() {
    try {
      this.setData({ loading: true })

      const response = await orderAPI.getOrderDetail(this.data.orderId)

      if (response.code === 200) {
        this.setData({ order: response.data })
        console.log('✓ 订单详情加载成功')
      } else {
        throw new Error(response.message || '加载订单失败')
      }
    } catch (error) {
      console.error('加载订单详情失败:', error)
      wx.showToast({
        title: '加载失败',
        icon: 'error'
      })
    } finally {
      this.setData({ loading: false })
    }
  },

  /**
   * 返回上一页
   */
  goBack() {
    wx.navigateBack()
  }
})
