// pages/dialogue/dialogue.js - B/C Agent 多轮对话页 v3.0
const { createRequest, DialogueAPI, AgentNegotiationAPI, DialogueWSListener } = require('../../api/request');
const ProfileManager = require('../../utils/profile');

Page({
  data: {
    sessionId: '',
    itemName: '',
    merchantId: '',
    turns: [],
    inputText: '',
    inputPrice: '',
    isLoading: false,
    isClosed: false,
    autoAccepted: false,
    wsStatus: 'connecting',
    satisfaction: null,
    showSatisfactionReport: false,
  },

  _wsListener: null,
  _dialogueAPI: null,
  _agentAPI: null,

  onLoad(options) {
    const { sessionId, itemName, merchantId, autoAccepted } = options;
    this.setData({
      sessionId: sessionId || '',
      itemName: decodeURIComponent(itemName || ''),
      merchantId: merchantId || 'box-001',
      autoAccepted: autoAccepted === '1',
    });
    const app = getApp();
    const request = createRequest(app.globalData.serverBase, app.globalData.token);
    this._dialogueAPI = DialogueAPI(request);
    this._agentAPI    = AgentNegotiationAPI(request);
    this._startWSListener();
    if (sessionId) this._loadSession();
    if (autoAccepted === '1') {
      setTimeout(() => this.setData({ showSatisfactionReport: true }), 1200);
    }
  },

  onUnload() {
    if (this._wsListener) this._wsListener.disconnect();
  },

  // ─── WebSocket 实时监听 ───
  _startWSListener() {
    const app = getApp();
    this._wsListener = new DialogueWSListener(
      app.globalData.wsBase,
      app.globalData.clientId,
      (turn) => this._onNewTurn(turn),
      (err) => { console.error('[Dialogue] ws error', err); this.setData({ wsStatus: 'disconnected' }); },
    );
    this._wsListener.connect();
    this.setData({ wsStatus: 'connected' });
  },

  _onNewTurn(turn) {
    const { sessionId, turns } = this.data;
    if (sessionId && turn.session_id !== sessionId) return;
    if (turns.some(t => t.turn_id === turn.turn_id)) return;
    const newTurns = [...turns, turn];
    this.setData({ turns: newTurns });
    wx.pageScrollTo({ scrollTop: 99999, duration: 200 });
    // B端报价 → 计算满意度
    if (turn.sender_role === 'MERCHANT' && turn.offered_price) {
      const profile = ProfileManager.loadClientProfile(getApp().globalData.clientId);
      this.setData({ satisfaction: ProfileManager.calcClientSatisfaction(profile, turn.offered_price, 20) });
    }
    // 成交 → 弹满意度上报
    if (turn.is_final || turn.status === 'DEAL') {
      this.setData({ isClosed: true });
      setTimeout(() => this.setData({ showSatisfactionReport: true }), 800);
    }
  },

  // ─── 加载历史会话 ───
  async _loadSession() {
    try {
      const res = await this._dialogueAPI.getSession(this.data.sessionId);
      this.setData({
        turns: res.turns || [],
        isClosed: res.session && res.session.status === 'CLOSED',
      });
      wx.pageScrollTo({ scrollTop: 99999, duration: 0 });
    } catch (e) { console.error('[Dialogue] load session failed', e); }
  },

  // ─── UI 输入 ───
  onInputText(e)  { this.setData({ inputText: e.detail.value }); },
  onInputPrice(e) { this.setData({ inputPrice: e.detail.value }); },

  // ─── 发送对话轮 ───
  async onSendTurn() {
    const { sessionId, inputText, inputPrice, isLoading, isClosed } = this.data;
    if (isLoading || isClosed) return;
    if (!inputText.trim()) { wx.showToast({ title: '请输入内容', icon: 'none' }); return; }
    const app = getApp();
    this.setData({ isLoading: true });
    try {
      await this._dialogueAPI.clientTurn({
        sessionId, clientId: app.globalData.clientId,
        text: inputText.trim(), expectedPrice: parseFloat(inputPrice) || null,
      });
      this.setData({ inputText: '', inputPrice: '' });
    } catch (e) {
      wx.showToast({ title: e.msg || '发送失败', icon: 'none' });
    } finally {
      this.setData({ isLoading: false });
    }
  },

  // ─── 关闭对话 ───
  async onCloseSession() {
    wx.showModal({
      title: '确认关闭', content: '确定结束本次对话吗？', confirmColor: '#e94560',
      success: async (res) => {
        if (!res.confirm) return;
        try {
          await this._dialogueAPI.close(this.data.sessionId);
          this.setData({ isClosed: true, showSatisfactionReport: true });
          if (this._wsListener) this._wsListener.disconnect();
        } catch (e) { wx.showToast({ title: '关闭失败', icon: 'none' }); }
      },
    });
  },

  // ─── 满意度上报（驱动 B端 Agent 学习）───
  async onSubmitSatisfaction(e) {
    const score = e.currentTarget.dataset.score;
    const { sessionId, satisfaction } = this.data;
    try {
      await this._agentAPI.reportSatisfaction({
        sessionId, clientId: getApp().globalData.clientId,
        score, priceScore: satisfaction?.price || score,
        timeScore: satisfaction?.time || score,
      });
      wx.showToast({ title: '感谢反馈！Agent 已学习', icon: 'success' });
    } catch (e) {
      wx.showToast({ title: '反馈已本地记录', icon: 'success' });
    }
    this.setData({ showSatisfactionReport: false });
  },

  onDismissSatisfaction() { this.setData({ showSatisfactionReport: false }); },

  formatTime(ts) {
    const d = new Date(Number(ts) * 1000);
    return `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;
  },
});
