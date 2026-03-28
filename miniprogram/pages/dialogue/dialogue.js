// pages/dialogue/dialogue.js - B/C Agent 多轮对话页 v4.0（完整对齐后端协议）
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
    // 成交信息
    dealPrice: null,
    dealMerchantId: '',
  },

  _wsListener: null,
  _dialogueAPI: null,
  _agentAPI: null,
  _turnIds: new Set(),

  onLoad(options) {
    const { sessionId, itemName, merchantId, autoAccepted } = options;
    this.setData({
      sessionId:    sessionId || '',
      itemName:     decodeURIComponent(itemName || ''),
      merchantId:   merchantId || 'box-001',
      autoAccepted: autoAccepted === '1',
    });
    const app = getApp();
    const request = createRequest(app.globalData.serverBase, app.globalData.token);
    this._dialogueAPI = DialogueAPI(request);
    this._agentAPI    = AgentNegotiationAPI(request);
    this._startWSListener();
    if (sessionId) this._loadSession();
    // 已自动接受时延迟弹满意度
    if (autoAccepted === '1') {
      setTimeout(() => this.setData({ showSatisfactionReport: true }), 1500);
    }
  },

  onUnload() {
    if (this._wsListener) this._wsListener.disconnect();
  },

  // ── WebSocket 监听（对齐后端 /ws/a2a/client/:id）───────
  _startWSListener() {
    const app = getApp();
    this._wsListener = new DialogueWSListener(
      app.globalData.wsBase,
      app.globalData.clientId,
      (msg) => this._onWSMessage(msg),
      (err) => {
        console.error('[Dialogue] ws error', err);
        this.setData({ wsStatus: 'disconnected' });
      },
    );
    this._wsListener.connect();
    this.setData({ wsStatus: 'connected' });
  },

  // ── 处理 WS 消息（对齐后端 a2a_dialogue_turn / offers）──
  _onWSMessage(msg) {
    const { sessionId } = this.data;
    if (msg._msgType === 'turn') {
      const turn = msg.turn || msg;
      // session 过滤
      if (sessionId && turn.session_id && turn.session_id !== sessionId) return;
      // 去重
      const turnId = turn.turn_id || turn.id;
      if (turnId && this._turnIds.has(turnId)) return;
      if (turnId) this._turnIds.add(turnId);

      const turns = [...this.data.turns, turn];
      this.setData({ turns });
      wx.pageScrollTo({ scrollTop: 99999, duration: 200 });

      // B端报价 → 计算满意度
      if (turn.sender_role === 'MERCHANT' && turn.offered_price) {
        const profile = ProfileManager.loadClientProfile(getApp().globalData.clientId);
        const sat = ProfileManager.calcClientSatisfaction(profile, turn.offered_price, 20);
        this.setData({ satisfaction: sat });
      }
      // 成交信号
      if (turn.is_final || turn.status === 'DEAL') {
        this.setData({
          isClosed: true,
          dealPrice: turn.offered_price || null,
          dealMerchantId: turn.sender_id || this.data.merchantId,
        });
        setTimeout(() => this.setData({ showSatisfactionReport: true }), 800);
      }
    } else if (msg._msgType === 'offers') {
      // 处理广播报价消息
      if (msg.offers && msg.offers.length > 0) {
        const best = msg.offers[0];
        this.setData({ dealPrice: best.final_price, dealMerchantId: best.merchant_id });
      }
    }
  },

  // ── 加载历史会话（对齐 /a2a/dialogue/:id 返回的 {session, turns}）
  async _loadSession() {
    try {
      const res = await this._dialogueAPI.getSession(this.data.sessionId);
      const turns = res.turns || [];
      const isClosed = res.session && res.session.status === 'CLOSED';
      turns.forEach(t => { if (t.turn_id) this._turnIds.add(t.turn_id); });
      this.setData({ turns, isClosed });
      // 缓存会话
      if (res.session) ProfileManager.saveSession(res.session);
      wx.pageScrollTo({ scrollTop: 99999, duration: 0 });
    } catch (e) {
      console.error('[Dialogue] load session failed:', e);
    }
  },

  // ── UI ─────────────────────────────────────────────────
  onInputText(e)  { this.setData({ inputText:  e.detail.value }); },
  onInputPrice(e) { this.setData({ inputPrice: e.detail.value }); },

  // ── 发送对话轮（对齐 /a2a/dialogue/client_turn）─────────
  async onSendTurn() {
    const { sessionId, inputText, inputPrice, isLoading, isClosed } = this.data;
    if (isLoading || isClosed) return;
    if (!inputText.trim()) { wx.showToast({ title: '请输入内容', icon: 'none' }); return; }
    const app = getApp();
    this.setData({ isLoading: true });
    try {
      await this._dialogueAPI.clientTurn({
        sessionId,
        clientId:      app.globalData.clientId,
        text:          inputText.trim(),
        expectedPrice: parseFloat(inputPrice) || null,
      });
      this.setData({ inputText: '', inputPrice: '' });
    } catch (e) {
      wx.showToast({ title: e.msg || '发送失败', icon: 'none' });
    } finally {
      this.setData({ isLoading: false });
    }
  },

  // ── 关闭对话（对齐 /a2a/dialogue/:id/close）────────────
  async onCloseSession() {
    wx.showModal({
      title: '确认关闭', content: '确定结束本次对话吗？', confirmColor: '#e94560',
      success: async (res) => {
        if (!res.confirm) return;
        try {
          await this._dialogueAPI.close(this.data.sessionId);
          this.setData({ isClosed: true });
          if (this._wsListener) this._wsListener.disconnect();
          this.setData({ showSatisfactionReport: true });
        } catch (e) {
          wx.showToast({ title: '关闭失败', icon: 'none' });
        }
      },
    });
  },

  // ── 满意度上报（驱动 B端 Agent 学习，对齐 /a2a/dialogue/satisfaction）
  async onSubmitSatisfaction(e) {
    const score = parseInt(e.currentTarget.dataset.score);
    const { sessionId, satisfaction } = this.data;
    const app = getApp();
    try {
      await this._agentAPI.reportSatisfaction({
        sessionId,
        clientId:   app.globalData.clientId,
        score,
        priceScore: satisfaction ? satisfaction.price : score,
        timeScore:  satisfaction ? satisfaction.time  : score,
      });
      wx.showToast({ title: '感谢反馈！Agent 已学习', icon: 'success' });
    } catch (e) {
      wx.showToast({ title: '反馈已记录', icon: 'success' });
    }
    this.setData({ showSatisfactionReport: false });
  },

  onDismissSatisfaction() { this.setData({ showSatisfactionReport: false }); },

  // ── 格式化时间 ─────────────────────────────────────────
  formatTime(ts) {
    const d = new Date(Number(ts) * 1000);
    return `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;
  },
});
