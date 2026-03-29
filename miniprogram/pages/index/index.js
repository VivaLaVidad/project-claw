// miniprogram/pages/index/index.js
const app = getApp()

Page({
  data: {
    orders: [],
    loading: false,
    userInfo: null
  },

  onLoad() {
    this.loadOrders()
    this.setData({ userInfo: app.globalData.userInfo })
  },

  loadOrders() {
    this.setData({ loading: true })
    wx.request({
      url: `${app.globalData.serverBase}/orders/list`,
      header: { 'Authorization': `Bearer ${app.globalData.sessionId}` },
      success: (response) => {
        if (response.statusCode === 200) {
          this.setData({ orders: response.data.orders })
        }
      },
      complete: () => {
        this.setData({ loading: false })
      }
    })
  },

  startVoiceChat(e) {
    const orderId = e.currentTarget.dataset.orderId
    wx.navigateTo({
      url: `/pages/voice-chat/voice-chat?orderId=${orderId}`
    })
  },

  viewOrderDetail(e) {
    const orderId = e.currentTarget.dataset.orderId
    wx.navigateTo({
      url: `/pages/order-detail/order-detail?orderId=${orderId}`
    })
  },

  onPullDownRefresh() {
    this.loadOrders()
    wx.stopPullDownRefresh()
  }
})
