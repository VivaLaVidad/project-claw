// miniprogram/pages/voice-chat/voice-chat.js
const app = getApp()

Page({
  data: {
    isConnected: false,
    isRecording: false,
    sessionId: null,
    messages: [],
    status: '未连接'
  },

  onLoad(options) {
    this.orderId = options.orderId
    this.initAudio()
  },

  initAudio() {
    this.audioContext = wx.createInnerAudioContext()
    this.audioContext.onPlay(() => {
      console.log('音频播放开始')
    })
    this.audioContext.onError((res) => {
      console.error('音频错误:', res)
    })
  },

  async startVoiceChat() {
    try {
      // 请求麦克风权限
      const res = await wx.requestRecordPermission()
      if (res.errMsg !== 'requestRecordPermission:ok') {
        wx.showToast({ title: '需要麦克风权限', icon: 'error' })
        return
      }

      // 生成会话 ID
      this.data.sessionId = `voice_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`

      // 连接 WebSocket
      this.connectWebSocket()

      this.setData({
        isConnected: true,
        isRecording: true,
        status: '对讲中...'
      })

      wx.showToast({ title: '语音对讲已启动', icon: 'success' })
    } catch (error) {
      console.error('启动语音对讲失败:', error)
      wx.showToast({ title: '启动失败', icon: 'error' })
    }
  },

  connectWebSocket() {
    const wsUrl = `${app.globalData.wsBase}/ws/audio/${this.data.sessionId}`
    
    wx.connectSocket({
      url: wsUrl,
      success: () => {
        console.log('WebSocket 连接成功')
      }
    })

    wx.onSocketOpen(() => {
      console.log('WebSocket 已打开')
      this.startRecording()
    })

    wx.onSocketMessage((res) => {
      if (typeof res.data === 'string') {
        const data = JSON.parse(res.data)
        if (data.type === 'audio') {
          this.playAudio(data.data)
        }
      }
    })

    wx.onSocketError(() => {
      console.error('WebSocket 错误')
      this.setData({ status: '连接错误' })
    })

    wx.onSocketClose(() => {
      console.log('WebSocket 已关闭')
      this.setData({ isConnected: false, isRecording: false, status: '已断开' })
    })
  },

  startRecording() {
    const recorder = wx.getRecorderManager()
    
    recorder.onStart(() => {
      console.log('录音开始')
    })

    recorder.onFrameRecorded((res) => {
      const { frameBuffer } = res
      // 发送音频帧到服务器
      wx.sendSocketMessage({
        data: frameBuffer,
        success: () => {
          console.log('音频帧已发送')
        }
      })
    })

    recorder.onStop((res) => {
      console.log('录音停止')
    })

    recorder.start({
      duration: 60000,
      sampleRate: 16000,
      numberOfChannels: 1,
      encodeBitRate: 96000,
      audioSource: 'mic'
    })
  },

  playAudio(audioData) {
    // 解码并播放音频
    this.audioContext.src = `data:audio/wav;base64,${audioData}`
    this.audioContext.play()
  },

  stopVoiceChat() {
    wx.closeSocket()
    this.setData({
      isConnected: false,
      isRecording: false,
      status: '已结束'
    })
    wx.showToast({ title: '语音对讲已结束', icon: 'success' })
  },

  onUnload() {
    if (this.data.isConnected) {
      wx.closeSocket()
    }
  }
})
