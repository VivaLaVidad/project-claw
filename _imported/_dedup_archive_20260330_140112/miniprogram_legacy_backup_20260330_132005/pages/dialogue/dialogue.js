/**
 * 语音对讲页面
 * 工业级标准实现
 */

const app = getApp()

Page({
  data: {
    orderId: '',
    isConnected: false,
    isRecording: false,
    sessionId: null,
    messages: [],
    status: '未连接',
    recordingTime: 0,
    recordingTimer: null,
    wsUrl: '',
    audioContext: null
  },

  /**
   * 页面加载
   */
  onLoad(options) {
    console.log('🎤 语音对讲页面加载')
    
    this.setData({
      orderId: options.orderId || '',
      sessionId: `voice_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
    })

    this.initAudio()
  },

  /**
   * 初始化音频
   */
  initAudio() {
    try {
      this.audioContext = wx.createInnerAudioContext()
      
      this.audioContext.onPlay(() => {
        console.log('🔊 音频播放开始')
      })

      this.audioContext.onError((res) => {
        console.error('❌ 音频错误:', res)
        wx.showToast({
          title: '音频错误',
          icon: 'error'
        })
      })

      console.log('✓ 音频已初始化')
    } catch (error) {
      console.error('初始化音频失败:', error)
    }
  },

  /**
   * 启动语音对讲
   */
  async startVoiceChat() {
    try {
      // 第 1 步：请求麦克风权限
      const permRes = await new Promise((resolve, reject) => {
        wx.requestRecordPermission({
          success: resolve,
          fail: reject
        })
      })

      if (permRes.errMsg !== 'requestRecordPermission:ok') {
        wx.showToast({
          title: '需要麦克风权限',
          icon: 'error'
        })
        return
      }

      // 第 2 步：连接 WebSocket
      this.connectWebSocket()

      this.setData({
        isConnected: true,
        isRecording: true,
        status: '对讲中...'
      })

      wx.showToast({
        title: '语音对讲已启动',
        icon: 'success',
        duration: 1000
      })

      console.log('✓ 语音对讲已启动')
    } catch (error) {
      console.error('启动语音对讲失败:', error)
      wx.showToast({
        title: '启动失败',
        icon: 'error'
      })
    }
  },

  /**
   * 连接 WebSocket
   */
  connectWebSocket() {
    const wsUrl = `${app.globalData.wsBase}/ws/audio/${this.data.sessionId}`
    
    console.log('🔗 连接 WebSocket:', wsUrl)

    wx.connectSocket({
      url: wsUrl,
      success: () => {
        console.log('✓ WebSocket 连接成功')
      },
      fail: (error) => {
        console.error('❌ WebSocket 连接失败:', error)
        this.setData({ status: '连接失败' })
      }
    })

    // WebSocket 打开
    wx.onSocketOpen(() => {
      console.log('✓ WebSocket 已打开')
      this.setData({ status: '已连接' })
      this.startRecording()
    })

    // WebSocket 消息
    wx.onSocketMessage((res) => {
      if (typeof res.data === 'string') {
        try {
          const data = JSON.parse(res.data)
          if (data.type === 'audio') {
            this.playAudio(data.data)
          }
        } catch (error) {
          console.error('解析消息失败:', error)
        }
      }
    })

    // WebSocket 错误
    wx.onSocketError(() => {
      console.error('❌ WebSocket 错误')
      this.setData({ status: '连接错误' })
    })

    // WebSocket 关闭
    wx.onSocketClose(() => {
      console.log('✓ WebSocket 已关闭')
      this.setData({ isConnected: false, isRecording: false, status: '已断开' })
    })
  },

  /**
   * 开始录音
   */
  startRecording() {
    try {
      const recorder = wx.getRecorderManager()

      recorder.onStart(() => {
        console.log('🎙️ 录音开始')
        this.startRecordingTimer()
      })

      recorder.onFrameRecorded((res) => {
        const { frameBuffer } = res
        
        // 发送音频帧到服务器
        wx.sendSocketMessage({
          data: frameBuffer,
          success: () => {
            console.log('📤 音频帧已发送')
          },
          fail: (error) => {
            console.error('发送音频帧失败:', error)
          }
        })
      })

      recorder.onStop((res) => {
        console.log('🛑 录音停止')
        this.stopRecordingTimer()
      })

      recorder.onError((error) => {
        console.error('❌ 录音错误:', error)
        wx.showToast({
          title: '录音错误',
          icon: 'error'
        })
      })

      // 开始录音
      recorder.start({
        duration: 60000,
        sampleRate: 16000,
        numberOfChannels: 1,
        encodeBitRate: 96000,
        audioSource: 'mic'
      })

      console.log('✓ 录音已启动')
    } catch (error) {
      console.error('启动录音失败:', error)
    }
  },

  /**
   * 播放音频
   */
  playAudio(audioData) {
    try {
      if (!this.audioContext) {
        this.initAudio()
      }

      // 将 base64 转换为可播放的格式
      this.audioContext.src = `data:audio/wav;base64,${audioData}`
      this.audioContext.play()

      console.log('🔊 播放音频')
    } catch (error) {
      console.error('播放音频失败:', error)
    }
  },

  /**
   * 停止语音对讲
   */
  stopVoiceChat() {
    try {
      // 关闭 WebSocket
      wx.closeSocket()

      // 停止录音
      const recorder = wx.getRecorderManager()
      recorder.stop()

      this.setData({
        isConnected: false,
        isRecording: false,
        status: '已结束'
      })

      wx.showToast({
        title: '语音对讲已结束',
        icon: 'success',
        duration: 1000
      })

      console.log('✓ 语音对讲已停止')

      // 返回上一页
      setTimeout(() => {
        wx.navigateBack()
      }, 1000)
    } catch (error) {
      console.error('停止语音对讲失败:', error)
    }
  },

  /**
   * 开始录音计时
   */
  startRecordingTimer() {
    this.data.recordingTimer = setInterval(() => {
      this.setData({
        recordingTime: this.data.recordingTime + 1
      })
    }, 1000)
  },

  /**
   * 停止录音计时
   */
  stopRecordingTimer() {
    if (this.data.recordingTimer) {
      clearInterval(this.data.recordingTimer)
      this.data.recordingTimer = null
    }
  },

  /**
   * 格式化时间
   */
  formatTime(seconds) {
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
  },

  /**
   * 页面卸载
   */
  onUnload() {
    if (this.data.isConnected) {
      wx.closeSocket()
    }
    
    if (this.audioContext) {
      this.audioContext.destroy()
    }

    this.stopRecordingTimer()
  }
})
