/**
 * Project Claw v14.3 - pages/result/result.js
 * 成交结果页：展示成交详情、设备执行状态、分享、重新下单
 */
Page({
  data: {
    ok: false,
    request: null,
    picked: null,
    result: null,
    deviceAck: null,
    errMsg: '',
    shareReady: false,
  },

  onLoad(query) {
    const app = getApp();
    const t = app.globalData.currentTrade || {};
    const ok = query.ok === '1';
    this.setData({
      ok,
      request: t.request || null,
      picked: t.picked || null,
      result: t.result || null,
      deviceAck: t.deviceAck || null,
      errMsg: this._resolveErrMsg(t.error),
      shareReady: ok,
    });

    // 成功或失败都保存历史，便于排障
    if (t.request) {
      this._updateHistory(t, ok);
    }
  },

  _resolveErrMsg(err) {
    if (!err) return '成交失败，请稍后再试';
    if (typeof err === 'string') return err;
    return err.detail || err.message || err.errMsg || '成交失败，请稍后再试';
  },

  _updateHistory(t, ok) {
    try {
      const history = wx.getStorageSync('claw_history') || [];
      const idx = history.findIndex(h => h.request_id === t.request.request_id);
      const entry = {
        request_id: t.request.request_id,
        item_name: t.request.item_name,
        max_price: t.request.max_price,
        final_price: t.picked ? t.picked.final_price : null,
        merchant_id: t.picked ? t.picked.merchant_id : '',
        offer_count: (t.bundle && t.bundle.offers) ? t.bundle.offers.length : 0,
        status: ok ? 'success' : 'failed',
        error_reason: ok ? '' : this._resolveErrMsg(t.error),
        ts: Date.now(),
      };
      if (idx >= 0) history[idx] = entry;
      else history.unshift(entry);
      wx.setStorageSync('claw_history', history.slice(0, 50));
    } catch (_) {}
  },

  backHome() {
    wx.reLaunch({ url: '/pages/index/index' });
  },

  goHistory() {
    wx.navigateTo({ url: '/pages/history/history' });
  },

  onShareAppMessage() {
    const picked = this.data.picked;
    return {
      title: picked ? `我在 Project Claw 订了${picked.item_name || '美食'}，仅 ${picked.final_price} 元！` : 'Project Claw 实惠询价',
      path: '/pages/index/index',
    };
  },
});
