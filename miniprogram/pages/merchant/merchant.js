// pages/merchant/merchant.js - B端控制台 v5.0 工业级实现
// 完整对接 C端 Agent，实现实时意图监听、对话、成交

const { createRequest, DialogueAPI, AgentNegotiationAPI, DialogueWSListener } = require('../../api/request');
const ProfileManager = require('../../utils/profile');

Page({
  data: {
    merchantId: 'box-001',
    profile: null,
    agentRunning: false,
    wsConnected: false,
    signalingUrl: '',
    currentNegotiationRound: 0,
    avgDealPrice: 0,
    totalIntents: 0,
    totalOffers: 0,
    totalRevenue: 0,

    // 实时意图
    currentIntent: null,
    intentQueue: [],

    // 实时对话
    currentDialogue: null,
    dialogueMap: {},
    replyText: '',
    replyPrice: '',

    // 今日订单
    todayOrders: [],
  },

  _wsListener: null,
  _dialogueAPI: null,
  _agentAPI: null,
  _intentBuffer: [],
  _stats: {
    totalIntents: 0,
    totalOffers: 0,
    totalRevenue: 0,
    dealPrices: [],
  },

  onLoad() {
    const app = getApp();
    const request = createRequest(app.globalData.serverBase, app.globalData.token);
    this._dialogueAPI = DialogueAPI(request);
    this._agentAPI = AgentNegotiationAPI(request);

    const profile = ProfileManager.loadMerchantProfile(this.data.merchantId);
    this.setData({
      profile,
      signalingUrl: app.globalData.serverBase,
    });

    // 上传 B端画像
    this._uploadMerchantProfile(profile);

    // 启动 WS 监听
    this._startWSListener();

    // 加载今日订单
    this._loadTodayOrders();
  },

  onUnload() {
    if (this._wsListener) this._wsListener.disconnect();
  },

  // ── 上传 B端画像 ──────────────────────────────────────────
  async _uploadMerchantProfile(profile) {
    try {
      await this._dialogueAPI.upsertMerchantProfile({
        merchant_id: this.data.merchantId,
        profile: profile,
      });
    } catch (e) {
      console.warn('[Merchant] upload profile failed:', e);
    }
  },

  // ── 启动 WS 监听 ──────────────────────────────────────────
  _startWSListener() {
    const app = getApp();
    this._wsListener = new DialogueWSListener(
      app.globalData.wsBase,
      this.data.merchantId,
      (msg) => this._onWSMessage(msg),
      (err) => {
        console.error('[Merchant] ws error', err);
        this.setData({ wsConnected: false });
      },
    );
    this._wsListener.connect();
    this.setData({ wsConnected: true, agentRunning: true });
  },

  // ── 处理 WS 消息 ──────────────────────────────────────────
  _onWSMessage(msg) {
    if (msg._msgType === 'offers') {
      // 意图广播消息
      this._handleIntentBroadcast(msg);
    } else if (msg._msgType === 'turn') {
      // 对话轮次消息
      this._handleDialogueTurn(msg);
    }
  },

  // ── 处理意图广播 ──────────────────────────────────────────
  _handleIntentBroadcast(msg) {
    const intent = msg.intent || msg;
    if (!intent.intent_id) return;

    this._intentBuffer.push(intent);
    this._stats.totalIntents++;

    // 显示最新意图
    if (!this.data.currentIntent) {
      this.setData({ currentIntent: intent });
    }

    // 更新统计
    this.setData({ totalIntents: this._stats.totalIntents });

    // 自动生成报价（可选）
    this._autoGenerateOffer(intent);
  },

  // ── 自动生成报价 ──────────────────────────────────────────
  async _autoGenerateOffer(intent) {
    try {
      const profile = this.data.profile;
      const { item_name, expected_price } = intent;

      // 简单策略：底价 + 10% 利润
      const offeredPrice = Math.max(
        profile.bottom_price,
        expected_price * 0.85
      );

      // 调用 LLM 生成文案（可选）
      const replyText = `新鲜现做，${offeredPrice}块钱给你来一份，保证好吃！`;

      // 返回报价给 signaling
      if (this._wsListener) {
        this._wsListener.send({
          type: 'a2a_merchant_offer',
          offer: {
            offer_id: `offer-${Date.now()}`,
            intent_id: intent.intent_id,
            merchant_id: this.data.merchantId,
            offered_price: offeredPrice,
            reply_text: replyText,
            is_accepted: true,
            eta_minutes: profile.delivery_time_minutes,
          },
        });
        this._stats.totalOffers++;
        this.setData({ totalOffers: this._stats.totalOffers });
      }
    } catch (e) {
      console.error('[Merchant] auto offer failed:', e);
    }
  },

  // ── 处理对话轮次 ──────────────────────────────────────────
  _handleDialogueTurn(msg) {
    const turn = msg.turn || msg;
    if (!turn.session_id) return;

    const sessionId = turn.session_id;
    const dialogue = this.data.dialogueMap[sessionId] || {
      session_id: sessionId,
      client_id: turn.receiver_id || turn.sender_id,
      round: 0,
      turns: [],
    };

    dialogue.turns.push(turn);
    dialogue.round = turn.round || dialogue.round + 1;

    // 更新对话映射
    const newDialogueMap = { ...this.data.dialogueMap, [sessionId]: dialogue };
    this.setData({
      dialogueMap: newDialogueMap,
      currentDialogue: dialogue,
    });

    // 如果是客户消息，自动生成回复
    if (turn.sender_role === 'CLIENT') {
      this._autoReplyDialogue(dialogue, turn);
    }

    // 更新统计
    if (turn.offered_price) {
      this._stats.dealPrices.push(turn.offered_price);
      const avg = this._stats.dealPrices.reduce((a, b) => a + b, 0) / this._stats.dealPrices.length;
      this.setData({ avgDealPrice: avg.toFixed(2) });
    }
  },

  // ── 自动回复对话 ──────────────────────────────────────────
  async _autoReplyDialogue(dialogue, clientTurn) {
    try {
      const profile = this.data.profile;
      const { text, expected_price } = clientTurn;

      // 简单策略：根据客户预算生成报价
      let offeredPrice = expected_price;
      if (expected_price > profile.normal_price) {
        offeredPrice = profile.normal_price;
      } else if (expected_price < profile.bottom_price) {
        offeredPrice = profile.bottom_price;
      }

      // 生成回复文案
      const replyText = `兄弟，新鲜现做，${offeredPrice}块钱给你来一份，保证好吃！`;
      const isAccepted = offeredPrice <= expected_price * 0.9;

      // 发送回复
      await this._dialogueAPI.clientTurn({
        sessionId: dialogue.session_id,
        clientId: this.data.merchantId,
        text: replyText,
        expectedPrice: offeredPrice,
      });

      // 如果成交，记录订单
      if (isAccepted) {
        this._recordOrder(dialogue, offeredPrice);
      }
    } catch (e) {
      console.error('[Merchant] auto reply failed:', e);
    }
  },

  // ── 记录订单 ──────────────────────────────────────────────
  _recordOrder(dialogue, finalPrice) {
    const order = {
      trade_id: `trade-${Date.now()}`,
      intent_id: dialogue.session_id,
      client_id: dialogue.client_id,
      merchant_id: this.data.merchantId,
      item_name: dialogue.item_name || '商品',
      final_price: finalPrice,
      created_at: Date.now() / 1000,
      status: 'EXECUTED',
    };

    ProfileManager.saveLocalOrder(order);
    this._stats.totalRevenue += finalPrice;
    this.setData({ totalRevenue: this._stats.totalRevenue });

    // 添加到今日订单
    const todayOrders = [order, ...this.data.todayOrders].slice(0, 20);
    this.setData({ todayOrders });
  },

  // ── 加载今日订单 ──────────────────────────────────────────
  async _loadTodayOrders() {
    try {
      const orders = ProfileManager.getLocalOrders();
      const today = new Date();
      today.setHours(0, 0, 0, 0);

      const todayOrders = orders.filter(o => {
        const orderDate = new Date(o.created_at * 1000);
        orderDate.setHours(0, 0, 0, 0);
        return orderDate.getTime() === today.getTime() && o.status === 'EXECUTED';
      });

      const totalRevenue = todayOrders.reduce((sum, o) => sum + (o.final_price || 0), 0);
      this.setData({ todayOrders, totalRevenue });
    } catch (e) {
      console.error('[Merchant] load orders failed:', e);
    }
  },

  // ── UI 事件 ────────────────────────────────────────────────
  onAcceptIntent() {
    if (!this.data.currentIntent) return;
    this._autoGenerateOffer(this.data.currentIntent);
    // 移到下一个意图
    if (this._intentBuffer.length > 0) {
      this._intentBuffer.shift();
      this.setData({ currentIntent: this._intentBuffer[0] || null });
    }
  },

  onDeclineIntent() {
    if (this._intentBuffer.length > 0) {
      this._intentBuffer.shift();
      this.setData({ currentIntent: this._intentBuffer[0] || null });
    }
  },

  onReplyInput(e) { this.setData({ replyText: e.detail.value }); },
  onPriceInput(e) { this.setData({ replyPrice: e.detail.value }); },

  async onSendReply() {
    const { currentDialogue, replyText, replyPrice } = this.data;
    if (!currentDialogue || !replyText.trim()) return;

    try {
      await this._dialogueAPI.clientTurn({
        sessionId: currentDialogue.session_id,
        clientId: this.data.merchantId,
        text: replyText,
        expectedPrice: parseFloat(replyPrice) || null,
      });
      this.setData({ replyText: '', replyPrice: '' });
    } catch (e) {
      wx.showToast({ title: '发送失败', icon: 'none' });
    }
  },

  onCopyId(e) {
    const { id } = e.currentTarget.dataset;
    wx.setClipboardData({ data: id, success: () => wx.showToast({ title: '已复制', icon: 'success' }) });
  },

  onEditBottomPrice() { wx.showToast({ title: '编辑功能开发中', icon: 'none' }); },
  onEditNormalPrice() { wx.showToast({ title: '编辑功能开发中', icon: 'none' }); },
  onEditDiscount() { wx.showToast({ title: '编辑功能开发中', icon: 'none' }); },
  onEditDeliveryTime() { wx.showToast({ title: '编辑功能开发中', icon: 'none' }); },
  onToggleOpen() {
    const profile = { ...this.data.profile, is_open: !this.data.profile.is_open };
    ProfileManager.saveMerchantProfile(profile);
    this.setData({ profile });
  },

  formatTime(ts) { return ProfileManager.formatTime(ts); },
});
