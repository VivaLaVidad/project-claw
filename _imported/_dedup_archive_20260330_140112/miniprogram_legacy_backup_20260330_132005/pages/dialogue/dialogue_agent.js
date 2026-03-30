// miniprogram/pages/dialogue/dialogue.js - C端Agent对话页面
// 与B端Agent进行实时对话

const { createRequest, DialogueAPI } = require('../../api/request');
const ProfileManager = require('../../utils/profile');

Page({
  data: {
    sessionId: '',
    itemName: '',
    merchantId: '',
    messages: [],
    inputText: '',
    isLoading: false,
    dialogueStatus: 'active',
    bestOffer: null,
    
    // 个性化设置
    clientProfile: {
      price_sensitivity: 0.5,
      time_urgency: 0.5,
      quality_preference: 0.5,
      brand_preferences: [],
    },
    
    // WebSocket
    ws: null,
    wsConnected: false,
  },

  onLoad(options) {
    const app = getApp();
    this._request = createRequest(app.globalData.serverBase, app.globalData.token);
    
    // 从参数获取信息
    const { sessionId, itemName, merchantId } = options;
    
    this.setData({
      sessionId: sessionId || '',
      itemName: decodeURIComponent(itemName || ''),
      merchantId: merchantId || 'box-001',
    });
    
    // 加载用户个性化设置
    this._loadClientProfile();
    
    // 连接 WebSocket
    if (sessionId) {
      this._connectWebSocket(sessionId);
    }
  },

  onUnload() {
    if (this.data.ws) {
      this.data.ws.close();
    }
  },

  // ── 个性化设置 ──────────────────────────────────────────
  _loadClientProfile() {
    const app = getApp();
    const profile = ProfileManager.loadClientProfile(app.globalData.clientId);
    
    if (profile) {
      this.setData({ clientProfile: profile });
    }
  },

  onProfileChange(e) {
    const key = e.currentTarget.dataset.key;
    const value = e.detail.value;
    
    const profile = { ...this.data.clientProfile };
    profile[key] = typeof value === 'string' ? parseFloat(value) : value;
    
    this.setData({ clientProfile: profile });
    ProfileManager.saveClientProfile(profile);
  },

  // ── WebSocket 连接 ──────────────────────────────────────
  _connectWebSocket(sessionId) {
    const app = getApp();
    const wsUrl = `${app.globalData.wsBase}/a2a/dialogue/ws/${sessionId}`;
    
    console.log('[Dialogue] 连接 WebSocket:', wsUrl);
    
    const ws = wx.connectSocket({
      url: wsUrl,
      header: { 'Content-Type': 'application/json' },
    });

    ws.onOpen(() => {
      console.log('[Dialogue] WebSocket 已连接');
      this.setData({ wsConnected: true });
      
      // 请求对话历史
      ws.send({
        data: JSON.stringify({
          type: 'get_history',
          session_id: sessionId,
        }),
      });
    });

    ws.onMessage((res) => {
      try {
        const message = JSON.parse(res.data);
        console.log('[Dialogue] 收到消息:', message);
        
        if (message.type === 'history') {
          // 加载对话历史
          this._loadDialogueHistory(message.turns);
        } else if (message.type === 'update') {
          // 更新对话
          this.setData({
            dialogueStatus: message.status,
            bestOffer: message.best_offer,
          });
          
          // 添加新消息
          if (message.turns && message.turns.length > this.data.messages.length) {
            const newTurns = message.turns.slice(this.data.messages.length);
            newTurns.forEach(turn => {
              this._addMessage(turn);
            });
          }
        } else if (message.type === 'error') {
          wx.showToast({
            title: message.message,
            icon: 'none',
          });
        }
      } catch (e) {
        console.error('[Dialogue] 消息解析错误:', e);
      }
    });

    ws.onError((err) => {
      console.error('[Dialogue] WebSocket 错误:', err);
      this.setData({ wsConnected: false });
    });

    ws.onClose(() => {
      console.log('[Dialogue] WebSocket 已关闭');
      this.setData({ wsConnected: false });
    });

    this.setData({ ws });
  },

  // ── 对话管理 ────────────────────────────────────────────
  _loadDialogueHistory(turns) {
    const messages = turns.map(turn => ({
      id: turn.turn_id,
      speaker: turn.speaker === 'client_agent' ? 'client' : 'merchant',
      text: turn.text,
      timestamp: turn.timestamp,
      metadata: turn.metadata || {},
    }));
    
    this.setData({ messages });
    
    // 滚动到底部
    wx.nextTick(() => {
      this.setData({
        scrollTop: 999999,
      });
    });
  },

  _addMessage(turn) {
    const message = {
      id: turn.turn_id,
      speaker: turn.speaker === 'client_agent' ? 'client' : 'merchant',
      text: turn.text,
      timestamp: turn.timestamp,
      metadata: turn.metadata || {},
    };
    
    const messages = [...this.data.messages, message];
    this.setData({ messages });
    
    // 滚动到底部
    wx.nextTick(() => {
      this.setData({
        scrollTop: 999999,
      });
    });
  },

  // ── 用户交互 ────────────────────────────────────────────
  onInputChange(e) {
    this.setData({ inputText: e.detail.value });
  },

  async onSendMessage() {
    const { inputText, sessionId, isLoading, ws, wsConnected } = this.data;
    
    if (!inputText.trim() || isLoading) return;
    
    if (!wsConnected) {
      wx.showToast({
        title: '未连接到服务器',
        icon: 'none',
      });
      return;
    }
    
    // 添加用户消息
    this._addMessage({
      turn_id: this.data.messages.length,
      speaker: 'client_agent',
      text: inputText,
      timestamp: Date.now() / 1000,
    });
    
    this.setData({ inputText: '' });
    
    // 通过 WebSocket 发送继续对话请求
    ws.send({
      data: JSON.stringify({
        type: 'continue',
        session_id: sessionId,
        max_turns: 5,
      }),
    });
  },

  // ── 对话操作 ────────────────────────────────────────────
  async onAcceptOffer() {
    const { bestOffer, itemName, merchantId } = this.data;
    
    if (!bestOffer) {
      wx.showToast({
        title: '没有可接受的报价',
        icon: 'none',
      });
      return;
    }
    
    wx.showModal({
      title: '确认下单',
      content: `确认购买 ${itemName}，价格 ¥${bestOffer.price}？`,
      confirmText: '确认',
      cancelText: '取消',
      success: (res) => {
        if (res.confirm) {
          // 保存订单
          ProfileManager.saveLocalOrder({
            item_name: itemName,
            merchant_id: merchantId,
            price: bestOffer.price,
            status: 'completed',
            created_at: Date.now() / 1000,
          });
          
          wx.showToast({
            title: '订单已创建',
            icon: 'success',
          });
          
          // 返回首页
          setTimeout(() => {
            wx.navigateBack();
          }, 1500);
        }
      },
    });
  },

  onContinueNegotiation() {
    const { ws, sessionId } = this.data;
    
    if (!ws) {
      wx.showToast({
        title: '连接已断开',
        icon: 'none',
      });
      return;
    }
    
    this.setData({ isLoading: true });
    
    ws.send({
      data: JSON.stringify({
        type: 'continue',
        session_id: sessionId,
        max_turns: 3,
      }),
    });
  },

  onEndDialogue() {
    const { ws } = this.data;
    
    if (ws) {
      ws.send({
        data: JSON.stringify({
          type: 'close',
        }),
      });
    }
    
    wx.navigateBack();
  },

  // ── 页面事件 ────────────────────────────────────────────
  onShow() {
    console.log('[Dialogue] 页面显示');
  },

  onHide() {
    console.log('[Dialogue] 页面隐藏');
  },
});
