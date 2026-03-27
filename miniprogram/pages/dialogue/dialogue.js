// pages/dialogue/dialogue.js - B/C Agent 多轮对话页（满意度上报版）
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
    this._agentAPI = AgentNegotiationAPI(request);
    this._startWSListener();
    if (sessionId) this._loadSession();
    // 若是自动接受，显示满意度上报
    if (autoAccepted === '1') {
      setTimeout(() => this.setData({ showSatisfactionReport: true }), 1200);
    }
  },

  onUnload() {
    if (this._wsListener) this._wsListener.disconnect();
  },

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
    if (this.data.sessionId && turn.session_id !== this.data.sessionId) return;
    const turns = [...this.data.turns];
    if (turns.some(t => t.turn_id === turn.turn_id)) return;
    turns.push(turn);
    this.setData({ turns });
    wx.pageScrollTo({ scrollTop: 99999, duration: 200 });
    // B端Agent报价 → 实时计算满意度
    if (turn.sender_role === 'MERCHANT' && turn.offered_price) {
      const profile = ProfileManager.loadClientProfile(getApp().globalData.clientId);
      const satisfaction = ProfileManager.calcClientSatisfaction(profile, turn.offered_price, 20);
      this.setData({ satisfaction });
    }
    // B端Agent宣布成交 → 弹出满意度上报
    if (turn.is_final || turn.status === 'DEAL') {
      this.setData({ isClosed: true });
      setTimeout(() => this.setData({ showSatisfactionReport: true }), 800);
    }
  },

  async _loadSession() {
    try {
      const res = await this._dialogueAPI.getSession(this.data.sessionId);
      const turns = res.turns || [];
      this.setData({ turns, isClosed: res.session && res.session.status === 'CLOSED' });
      wx.pageScrollTo({ scrollTop: 99999, duration: 0 });
    } catch (e) { console.error('[Dialogue] load session failed', e); }
  },

  onInputText(e)  { this.setData({ inputText: e.detail.value }); },
  onInputPrice(e) { this.setData({ inputPrice: e.detail.value }); },

  async onSendTurn() {
    const { sessionId, inputText, inputPrice, isLoading, isClosed } = this.data;
    if (isLoading || isClosed) return;
    if (!inputText.trim()) { wx.showToast({ title: '请输入内容', icon: 'none' }); return; }
    const app = getApp();
    const price = parseFloat(inputPrice) || null;
    this.setData({ isLoading: true });
    try {
      await this._dialogueAPI.clientTurn({
        sessionId, clientId: app.globalData.clientId,
        text: inputText.trim(), expectedPrice: price,
      });
      this.setData({ inputText: '', inputPrice: '' });
    } catch (e) {
      wx.showToast({ title: e.msg || '发送失败', icon: 'none' });
    } finally {
      this.setData({ isLoading: false });
    }
  },

  async onCloseSession() {
    wx.showModal({
      title: '确认关闭',
      content: '确定结束本次对话吗？',
      confirmColor: '#e94560',
      success: async (res) => {
        if (!res.confirm) return;
        try {
          await this._dialogueAPI.close(this.data.sessionId);
          this.setData({ isClosed: true, showSatisfactionReport: true });
          if (this._wsListener) this._wsListener.disconnect();
        } catch (e) {
          wx.showToast({ title: '关闭失败', icon: 'none' });
        }
      },
    });
  },

  // ─── 满意度上报（C端Agent反馈给系统，驱动B端Agent学习）───
  async onSubmitSatisfaction(e) {
    const score = e.currentTarget.dataset.score;
    const { sessionId, satisfaction } = this.data;
    const app = getApp();
    try {
      await this._agentAPI.reportSatisfaction({
        sessionId,
        clientId: app.globalData.clientId,
        score: score,
        priceScore: satisfaction ? satisfaction.price : score,
        timeScore: satisfaction ? satisfaction.time : score,
      });
      wx.showToast({ title: '感谢反馈！Agent已学习', icon: 'success' });
    } catch (e) {
      wx.showToast({ title: '反馈已记录（本地）', icon: 'success' });
    }
    this.setData({ showSatisfactionReport: false });
  },

  onDismissSatisfaction() {
    this.setData({ showSatisfactionReport: false });
  },
});

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
    wsStatus: 'connecting',  // 'connecting' | 'connected' | 'disconnected'
    satisfaction: null,
  },

  _wsListener: null,
  _dialogueAPI: null,

  onLoad(options) {
    const { sessionId, itemName, merchantId } = options;
    this.setData({
      sessionId: sessionId || '',
      itemName: decodeURIComponent(itemName || ''),
      merchantId: merchantId || 'box-001',
    });

    const app = getApp();
    const request = createRequest(app.globalData.serverBase, app.globalData.token);
    this._dialogueAPI = DialogueAPI(request);

    this._startWSListener();
    this._loadSession();
  },

  onUnload() {
    if (this._wsListener) this._wsListener.disconnect();
  },

  // ─── WebSocket 监听 ───

  _startWSListener() {
    const app = getApp();
    this._wsListener = new DialogueWSListener(
      app.globalData.wsBase,
      app.globalData.clientId,
      (turn) => this._onNewTurn(turn),
      (err) => {
        console.error('[Dialogue] ws error', err);
        this.setData({ wsStatus: 'disconnected' });
      },
    );
    this._wsListener.connect();
    this.setData({ wsStatus: 'connected' });
  },

  _onNewTurn(turn) {
    if (turn.session_id !== this.data.sessionId) return;

    const turns = [...this.data.turns];
    // 防止重复
    if (turns.some(t => t.turn_id === turn.turn_id)) return;
    turns.push(turn);
    this.setData({ turns });

    // 滚动到底部
    wx.pageScrollTo({ scrollTop: 99999, duration: 200 });

    // 若是商家报价，实时计算满意度
    if (turn.sender_role === 'MERCHANT' && turn.offered_price) {
      const profile = ProfileManager.loadClientProfile(getApp().globalData.clientId);
      const satisfaction = ProfileManager.calcClientSatisfaction(
        profile,
        turn.offered_price,
        20,
      );
      this.setData({ satisfaction });
    }
  },

  // ─── 加载历史会话 ───

  async _loadSession() {
    if (!this.data.sessionId) return;
    try {
      const res = await this._dialogueAPI.getSession(this.data.sessionId);
      const turns = res.turns || [];
      this.setData({
        turns,
        isClosed: res.session && res.session.status === 'CLOSED',
      });
      wx.pageScrollTo({ scrollTop: 99999, duration: 0 });
    } catch (e) {
      console.error('[Dialogue] load session failed', e);
    }
  },

  // ─── UI 输入 ───

  onInputText(e) { this.setData({ inputText: e.detail.value }); },
  onInputPrice(e) { this.setData({ inputPrice: e.detail.value }); },

  // ─── 发送一轮 ───

  async onSendTurn() {
    const { sessionId, inputText, inputPrice, isLoading, isClosed } = this.data;
    if (isLoading || isClosed) return;
    if (!inputText.trim()) {
      wx.showToast({ title: '请输入内容', icon: 'none' }); return;
    }
    const app = getApp();
    const price = parseFloat(inputPrice) || null;

    this.setData({ isLoading: true });
    try {
      await this._dialogueAPI.clientTurn({
        sessionId,
        clientId: app.globalData.clientId,
        text: inputText.trim(),
        expectedPrice: price,
      });
      this.setData({ inputText: '', inputPrice: '' });
    } catch (e) {
      console.error('[Dialogue] send turn failed', e);
      wx.showToast({ title: e.msg || '发送失败', icon: 'none' });
    } finally {
      this.setData({ isLoading: false });
    }
  },

  // ─── 关闭对话 ───

  async onCloseSession() {
    wx.showModal({
      title: '确认关闭',
      content: '确定结束本次对话吗？',
      confirmColor: '#e94560',
      success: async (res) => {
        if (!res.confirm) return;
        try {
          await this._dialogueAPI.close(this.data.sessionId);
          this.setData({ isClosed: true });
          wx.showToast({ title: '对话已关闭', icon: 'success' });
          if (this._wsListener) this._wsListener.disconnect();
        } catch (e) {
          wx.showToast({ title: '关闭失败', icon: 'none' });
        }
      },
    });
  },

  // ─── 工具 ───

  formatTime(ts) {
    const d = new Date(ts * 1000);
    const h = String(d.getHours()).padStart(2, '0');
    const m = String(d.getMinutes()).padStart(2, '0');
    return `${h}:${m}`;
  },
});
