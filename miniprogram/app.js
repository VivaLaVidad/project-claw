// miniprogram/app.js
App({
  globalData: {
    userInfo: null,
    sessionId: null,
    serverBase: 'http://localhost:8765',
    wsBase: 'ws://localhost:8765'
  },

  onLaunch() {
    // 检查登录状态
    wx.checkSession({
      success: () => {
        this.getUserInfo()
      },
      fail: () => {
        this.login()
      }
    })
  },

  login() {
    wx.login({
      success: (res) => {
        if (res.code) {
          // 发送 code 到后端获取 session
          wx.request({
            url: `${this.globalData.serverBase}/auth/login`,
            method: 'POST',
            data: { code: res.code },
            success: (response) => {
              if (response.statusCode === 200) {
                this.globalData.sessionId = response.data.session_id
                this.globalData.userInfo = response.data.user_info
                wx.setStorageSync('sessionId', response.data.session_id)
              }
            }
          })
        }
      }
    })
  },

  getUserInfo() {
    const sessionId = wx.getStorageSync('sessionId')
    if (sessionId) {
      this.globalData.sessionId = sessionId
      wx.request({
        url: `${this.globalData.serverBase}/auth/user-info`,
        header: { 'Authorization': `Bearer ${sessionId}` },
        success: (response) => {
          if (response.statusCode === 200) {
            this.globalData.userInfo = response.data
          }
        }
      })
    }
  }
})
