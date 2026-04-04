const { ensureToken, requestTradeStream } = require('../../utils/api');

Page({
  data: {
    buyerMeta: 'AI Negotiator / Safe-Mode',
    buyerStatus: '准备进入博弈通道...',
    cotLines: [],
    displayLines: [],
    dialogueFilter: 'all',
    dialogueFilters: [
      { key: 'all', name: '全部' },
      { key: 'buyer', name: '仅C端' },
      { key: 'merchant', name: '仅B端' },
    ],
    scrollTo: '',
    bidItems: [],
    effectMode: '',
    sealed: false,
  },

  onLoad() {
    const app = getApp();
    const pending = app.globalData.pendingTradeRequest;
    if (!pending) {
      wx.showToast({ title: '缺少询价上下文', icon: 'none' });
      setTimeout(() => wx.navigateBack({ delta: 1 }), 500);
      return;
    }
    this._runNegotiation(pending);
  },

  onUnload() {
    if (this._streamTask && typeof this._streamTask.destroy === 'function') {
      this._streamTask.destroy();
    }
    this._streamTask = null;
  },

  async _runNegotiation(payload) {
    await ensureToken(payload.client_id).catch(() => {});
    this.setData({ buyerStatus: `目标商品：${payload.item_name}，启动实时谈判...` });

    try {
      this._streamTask = requestTradeStream(payload, {
        onStart: (evt) => {
          this._pushTypedLine('cognition', 'Cognition', `检测到 ${evt.total_merchants || 0} 个商家在线，正在扫描历史成交曲线...`);
          this._pushTypedLine('strategy', 'Strategy', '建立多方博弈矩阵，优先压缩高报价区间...');
        },
        onOffer: (offer) => {
          this._upsertBid(offer);
          const maxPrice = Number(payload.max_price || 0);
          if (Number(offer.final_price || 0) <= maxPrice * 0.82) {
            this._flashEffect('green');
            this._pushTypedLine('action', 'Action', `商家 ${offer.merchant_id} 降价至 ${offer.final_price}，触发让利跟进。`);
          } else {
            this._flashEffect('red');
            this._pushTypedLine('strategy', 'Strategy', `商家 ${offer.merchant_id} 坚持高价，执行“加蛋博弈”策略...`);
          }
          this._pushTypedLine('action', 'Action', '向 B 端 Agent 发送反向 Offer...');
        },
        onEvent: (evtName, evt) => {
          if (evtName === 'dialogue') {
            const role = evt && evt.role;
            if (role === 'buyer_agent') {
              this._pushTypedLine('buyer', 'C端Agent', String(evt.text || 'C端Agent 发出议价请求'));
            } else if (role === 'merchant_agent') {
              this._pushTypedLine('merchant', 'B端Agent', String(evt.text || 'B端Agent 返回报价意见'));
            }
          }
        },
      });

      const bundle = await this._streamTask;
      getApp().globalData.currentTrade = { request: payload, bundle };
      await this._sealContract();
      wx.navigateTo({ url: '/pages/offers/offers' });
    } catch (e) {
      wx.showModal({ title: '谈判中断', content: String((e && e.detail) || 'stream_failed'), showCancel: false });
      wx.navigateBack({ delta: 1 });
    }
  },

  onChangeDialogueFilter(e) {
    const key = e.currentTarget.dataset.key;
    this.setData({ dialogueFilter: key });
    this._refreshDisplayLines();
  },

  exportDialogue() {
    const app = getApp();
    const trade = app.globalData.currentTrade || {};
    const payload = {
      request: trade.request || null,
      bundle: trade.bundle || null,
      dialogue: this.data.cotLines || [],
      exported_at: Date.now(),
    };
    const fs = wx.getFileSystemManager();
    const path = `${wx.env.USER_DATA_PATH}/negotiation-${Date.now()}.json`;
    fs.writeFile({
      filePath: path,
      data: JSON.stringify(payload, null, 2),
      encoding: 'utf8',
      success: () => wx.showModal({ title: '导出成功', content: path, showCancel: false }),
      fail: () => wx.showToast({ title: '导出失败', icon: 'none' }),
    });
  },

  _refreshDisplayLines() {
    const f = this.data.dialogueFilter;
    const all = this.data.cotLines || [];
    const lines = all.filter((x) => {
      if (f === 'all') return true;
      if (f === 'buyer') return x.type === 'buyer';
      if (f === 'merchant') return x.type === 'merchant';
      return true;
    });
    this.setData({ displayLines: lines });
  },

  _upsertBid(offer) {
    const list = (this.data.bidItems || []).slice();
    const idx = list.findIndex((x) => x.merchant_id === offer.merchant_id);
    const row = { merchant_id: offer.merchant_id || 'unknown', final_price: offer.final_price || '-' };
    if (idx >= 0) list[idx] = row;
    else list.unshift(row);
    this.setData({ bidItems: list.slice(0, 8) });
  },

  _flashEffect(mode) {
    this.setData({ effectMode: mode });
    setTimeout(() => this.setData({ effectMode: '' }), 600);
  },

  _pushTypedLine(type, tag, fullText) {
    const id = `line-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
    const lines = (this.data.cotLines || []).concat([{ id, type, tag, text: '' }]);
    this.setData({ cotLines: lines, scrollTo: id });
    this._refreshDisplayLines();

    let i = 0;
    const timer = setInterval(() => {
      i += 1;
      const next = (this.data.cotLines || []).slice();
      const lineIdx = next.findIndex((x) => x.id === id);
      if (lineIdx >= 0) next[lineIdx].text = fullText.slice(0, i);
      this.setData({ cotLines: next, scrollTo: id });
      this._refreshDisplayLines();
      if (i >= fullText.length) clearInterval(timer);
    }, 18);
  },

  async _sealContract() {
    this._pushTypedLine('action', 'Action', '成交条件满足，准备签署协议...');
    this.setData({ sealed: true, buyerStatus: '协议签定中...' });
    await new Promise((r) => setTimeout(r, 1200));
    this.setData({ buyerStatus: '协议签定完成，进入成交页。' });
  },
});
