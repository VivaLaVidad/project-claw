/**
 * Project Claw v14.3 - pages/offers/offers.js
 * 报价页：可操作倒计时 + 快照同步 + 成交确认
 */
const { ensureToken, executeTrade, getToken, getWsBaseUrl, getTradeSnapshot } = require('../../utils/api');

Page({
  data: {
    request: null,
    bundle: null,
    offers: [],
    selectedIndex: -1,
    selectedOfferId: '',
    loading: false,
    remainSec: 0,
    remainMs: 0,
    remainDeci: '0',
    expired: false,
    deviceAckStatus: '',
    streamStatus: 'waiting',
    errorMsg: '',
  },

  onLoad() {
    const app = getApp();
    const trade = app.globalData.currentTrade;
    if (!trade || !trade.bundle) {
      wx.showToast({ title: '请先发起询价', icon: 'none' });
      setTimeout(() => wx.reLaunch({ url: '/pages/index/index' }), 800);
      return;
    }

    const offers = (trade.bundle.offers || []).slice().sort((a, b) => b.match_score - a.match_score);
    this.setData({ request: trade.request, bundle: trade.bundle, offers });
    this._startCountdown();
    this._openWs(trade.request.client_id);
    this._startSnapshotSync();
  },

  onUnload() {
    this._stopCountdown();
    this._stopSnapshotSync();
    this._closeWs();
  },

  // 报价页可操作窗口：10分钟（与 Hub SNAPSHOT_TTL 对齐）
  _startCountdown() {
    const OPERATE_TTL_SEC = 600;
    const start = Date.now();
    const deadline = start + OPERATE_TTL_SEC * 1000;

    const tick = () => {
      const now = Date.now();
      const remain = Math.max(0, deadline - now);
      this.setData({
        remainSec: Math.floor(remain / 1000),
        remainMs: remain % 1000,
        remainDeci: String(Math.floor((remain % 1000) / 100)),
        expired: remain <= 0,
      });
      if (remain <= 0) this._stopCountdown();
    };

    tick();
    this._countdownTimer = setInterval(tick, 100);
  },

  _stopCountdown() {
    if (this._countdownTimer) {
      clearInterval(this._countdownTimer);
      this._countdownTimer = null;
    }
  },

  _startSnapshotSync() {
    this._syncSnapshotOnce();
    this._snapshotTimer = setInterval(() => this._syncSnapshotOnce(), 2000);
  },

  _stopSnapshotSync() {
    if (this._snapshotTimer) {
      clearInterval(this._snapshotTimer);
      this._snapshotTimer = null;
    }
  },

  async _syncSnapshotOnce() {
    const req = this.data.request;
    if (!req || !req.request_id) return;

    try {
      const snap = await getTradeSnapshot(req.request_id);
      const offers = (snap.offers || []).slice().sort((a, b) => b.match_score - a.match_score);

      const selectedOfferId = this.data.selectedOfferId;
      let selectedIndex = -1;
      if (selectedOfferId) {
        selectedIndex = offers.findIndex(o => o.offer_id === selectedOfferId);
      }

      this.setData({
        offers,
        selectedIndex,
        bundle: Object.assign({}, this.data.bundle || {}, {
          responded: offers.length,
          total_merchants: (this.data.bundle && this.data.bundle.total_merchants) || (offers.length || 0),
        }),
      });
    } catch (_) {
      // 快照同步失败不打断主流程
    }
  },

  _openWs(clientId) {
    const token = getToken();
    if (!token || !clientId) return;

    const url = `${getWsBaseUrl()}/ws/client/${clientId}?token=${encodeURIComponent(token)}`;

    try {
      this._ws = wx.connectSocket({ url, timeout: 10000, tcpNoDelay: true });

      this._ws.onOpen(() => this._wsHeartbeat());

      this._ws.onMessage((evt) => {
        try {
          const env = JSON.parse(evt.data || '{}');
          if (env.msg_type === 'ack' && env.payload) {
            const p = env.payload;
            if (p.request_id !== (this.data.request && this.data.request.request_id)) return;
            if (p.type === 'execute_result') {
              this.setData({ deviceAckStatus: p.ok ? 'ok' : 'failed' });
              const app = getApp();
              if (app.globalData.currentTrade) app.globalData.currentTrade.deviceAck = p;
            }
          }
        } catch (_) {}
      });

      this._ws.onError(() => {
        this._wsReconnectTimer = setTimeout(() => this._openWs(clientId), 5000);
      });
    } catch (_) {}
  },

  _wsHeartbeat() {
    if (this._wsHeartbeatTimer) clearInterval(this._wsHeartbeatTimer);
    this._wsHeartbeatTimer = setInterval(() => {
      if (this._ws) {
        try { this._ws.send({ data: JSON.stringify({ type: 'ping' }) }); } catch (_) {}
      }
    }, 30000);
  },

  _closeWs() {
    if (this._wsHeartbeatTimer) clearInterval(this._wsHeartbeatTimer);
    if (this._wsReconnectTimer) clearTimeout(this._wsReconnectTimer);
    if (this._ws) {
      try { this._ws.close(); } catch (_) {}
      this._ws = null;
    }
  },

  selectOffer(e) {
    const idx = Number(e.currentTarget.dataset.index);
    const next = this.data.selectedIndex === idx ? -1 : idx;
    const picked = next >= 0 ? this.data.offers[next] : null;
    this.setData({
      selectedIndex: next,
      selectedOfferId: picked ? picked.offer_id : '',
    });
  },

  async confirmTrade() {
    if (this.data.loading) return;
    if (this.data.expired) {
      wx.showModal({ title: '报价已过期', content: '请返回重新发起询价', showCancel: false });
      return;
    }

    await this._syncSnapshotOnce();

    const req = this.data.request;
    const selectedOfferId = this.data.selectedOfferId;
    const picked = (this.data.offers || []).find(o => o.offer_id === selectedOfferId);

    if (!picked) {
      wx.showToast({ title: '该报价已变化，请重新选择', icon: 'none' });
      this.setData({ selectedIndex: -1, selectedOfferId: '' });
      return;
    }

    await ensureToken(req.client_id).catch(() => {});

    wx.showModal({
      title: '确认成交',
      content: `商家：${picked.merchant_id}\n金额：${picked.final_price} 元\n\n${picked.reply_text || ''}`,
      confirmText: '确认付款',
      cancelText: '再想想',
      success: async (r) => {
        if (!r.confirm) return;
        this.setData({ loading: true });
        wx.showLoading({ title: '提交中…', mask: true });
        try {
          const result = await executeTrade({
            request_id: req.request_id,
            offer_id: picked.offer_id,
            merchant_id: picked.merchant_id,
            client_id: req.client_id,
            final_price: picked.final_price,
            trace_id: req.trace_id || `trace-${req.request_id}`,
            idempotency_key: `exec-${req.request_id}-${picked.offer_id}`,
          });
          const app = getApp();
          app.globalData.currentTrade = Object.assign({}, app.globalData.currentTrade, { picked, result });
          wx.hideLoading();
          this._closeWs();
          wx.navigateTo({ url: '/pages/result/result?ok=1' });
        } catch (e) {
          wx.hideLoading();
          const app = getApp();
          app.globalData.currentTrade = Object.assign({}, app.globalData.currentTrade, { picked, error: e });
          wx.navigateTo({ url: '/pages/result/result?ok=0' });
        } finally {
          this.setData({ loading: false });
        }
      },
    });
  },

  backHome() {
    wx.reLaunch({ url: '/pages/index/index' });
  },
});
