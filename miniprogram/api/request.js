// api/request.js - 工业级 HTTP + WebSocket 通信封装

/**
 * 创建 HTTP 请求工厂
 * @param {string} base  服务器根地址
 * @param {string} token 内部鉴权 token（可选）
 */
function createRequest(base, token) {
  return function request({ method = 'GET', path, data, timeout = 15000 }) {
    return new Promise((resolve, reject) => {
      const headers = { 'Content-Type': 'application/json' };
      if (token) headers['x-internal-token'] = token;

      wx.request({
        url: base.replace(/\/$/, '') + path,
        method,
        data,
        header: headers,
        timeout,
        success(res) {
          if (res.statusCode >= 200 && res.statusCode < 300) {
            resolve(res.data);
          } else {
            reject({ code: res.statusCode, msg: JSON.stringify(res.data) });
          }
        },
        fail(err) {
          reject({ code: -1, msg: err.errMsg || '网络错误' });
        },
      });
    });
  };
}

// ─── A2A 对话 API ───

function DialogueAPI(request) {
  return {
    /** 注册 C 端个性化画像 */
    upsertClientProfile(profile) {
      return request({ method: 'POST', path: '/a2a/dialogue/profile/client', data: profile });
    },

    /** 注册 B 端个性化画像 */
    upsertMerchantProfile(profile) {
      return request({ method: 'POST', path: '/a2a/dialogue/profile/merchant', data: profile });
    },

    /** 发起对话 */
    start({ intent, merchantId, openingText }) {
      return request({
        method: 'POST',
        path: '/a2a/dialogue/start',
        data: { intent, merchant_id: merchantId, opening_text: openingText },
      });
    },

    /** C 端发一轮 */
    clientTurn({ sessionId, clientId, text, expectedPrice }) {
      return request({
        method: 'POST',
        path: '/a2a/dialogue/client_turn',
        data: { session_id: sessionId, client_id: clientId, text, expected_price: expectedPrice },
      });
    },

    /** 获取会话历史 */
    getSession(sessionId) {
      return request({ method: 'GET', path: `/a2a/dialogue/${sessionId}` });
    },

    /** 关闭会话 */
    close(sessionId) {
      return request({ method: 'POST', path: `/a2a/dialogue/${sessionId}/close` });
    },
  };
}

// ─── 意图广播 API ───

function IntentAPI(request) {
  return {
    /** C 端发起意图广播 */
    broadcast({ clientId, location, demandText, maxPrice, timeout = 3.0 }) {
      return request({
        method: 'POST',
        path: '/intent',
        data: {
          client_id: clientId,
          location,
          demand_text: demandText,
          max_price: maxPrice,
          timeout,
        },
      });
    },

    /** A2A 机器谈判意图 */
    a2aIntent({ clientId, itemName, expectedPrice, maxDistanceKm = 8.0 }) {
      return request({
        method: 'POST',
        path: '/a2a/intent',
        data: {
          client_id: clientId,
          item_name: itemName,
          expected_price: expectedPrice,
          max_distance_km: maxDistanceKm,
          timestamp: Date.now() / 1000,
        },
      });
    },
  };
}

// ─── 健康 / 统计 API ───

function SystemAPI(request) {
  return {
    health() {
      return request({ method: 'GET', path: '/health' });
    },
    stats() {
      return request({ method: 'GET', path: '/stats' });
    },
  };
}

// ─── WebSocket 对话监听器 ───

class DialogueWSListener {
  /**
   * @param {string} wsBase        ws://host:port
   * @param {string} clientId      C 端 ID
   * @param {Function} onTurn      收到 turn 回调
   * @param {Function} onError     错误回调
   */
  constructor(wsBase, clientId, onTurn, onError) {
    this._base = wsBase.replace(/\/$/, '');
    this._clientId = clientId;
    this._onTurn = onTurn;
    this._onError = onError || console.error;
    this._socket = null;
    this._closed = false;
    this._reconnectTimer = null;
    this._reconnectDelay = 2000;
  }

  connect() {
    if (this._closed) return;
    const url = `${this._base}/ws/a2a/dialogue/client/${this._clientId}`;
    console.log('[WS] connecting:', url);

    this._socket = wx.connectSocket({ url, fail: err => this._onError(err) });

    this._socket.onOpen(() => {
      console.log('[WS] connected');
      this._reconnectDelay = 2000;
    });

    this._socket.onMessage(({ data }) => {
      try {
        const msg = JSON.parse(data);
        if (msg.type === 'a2a_dialogue_turn' && msg.turn) {
          this._onTurn(msg.turn);
        }
      } catch (e) {
        console.warn('[WS] parse error', e);
      }
    });

    this._socket.onError(err => {
      console.error('[WS] error', err);
      this._onError(err);
      this._scheduleReconnect();
    });

    this._socket.onClose(() => {
      console.warn('[WS] closed');
      if (!this._closed) this._scheduleReconnect();
    });
  }

  _scheduleReconnect() {
    clearTimeout(this._reconnectTimer);
    this._reconnectTimer = setTimeout(() => {
      this._reconnectDelay = Math.min(this._reconnectDelay * 1.5, 30000);
      this.connect();
    }, this._reconnectDelay);
  }

  disconnect() {
    this._closed = true;
    clearTimeout(this._reconnectTimer);
    if (this._socket) {
      try { this._socket.close({}); } catch (e) {}
      this._socket = null;
    }
  }
}

// ─── A2A 全自动谈判 API（B端Agent驱动）───

function AgentNegotiationAPI(request) {
  return {
    /**
     * 启动 B/C 双端 Agent 全自动谈判
     * C端Agent分析预算偏好，B端Agent根据画像自动报价砍价
     */
    startAutoNegotiation({ clientId, itemName, expectedPrice, maxDistanceKm = 8.0 }) {
      return request({
        method: 'POST',
        path: '/a2a/intent',
        data: {
          client_id: clientId,
          item_name: itemName,
          expected_price: expectedPrice,
          max_distance_km: maxDistanceKm,
          timestamp: Date.now() / 1000,
          mode: 'auto',  // 全自动谈判模式
        },
      });
    },

    /** 查询自动谈判结果 */
    pollResult(intentId) {
      return request({ method: 'GET', path: `/a2a/intent/${intentId}/result` });
    },

    /** 获取推荐商家列表（B端Agent排序）*/
    getRecommendedMerchants({ itemName, budget, limit = 5 }) {
      return request({
        method: 'POST',
        path: '/a2a/match',
        data: { item_name: itemName, budget, limit },
      });
    },

    /** C端Agent上报满意度反馈（用于 B端 Agent 学习）*/
    reportSatisfaction({ sessionId, clientId, score, priceScore, timeScore }) {
      return request({
        method: 'POST',
        path: '/a2a/dialogue/satisfaction',
        data: { session_id: sessionId, client_id: clientId,
                overall: score, price: priceScore, time: timeScore },
      });
    },

    /** 触发执行（通知 B端 Edge Box 实际下单）*/
    executeTradeOrder({ merchantId, finalPrice, item, clientId }) {
      return request({
        method: 'POST',
        path: '/api/v1/trade/execute',
        data: { merchant_id: merchantId, final_price: finalPrice, item, client_id: clientId },
      });
    },
  };
}

module.exports = {
  createRequest,
  DialogueAPI,
  IntentAPI,
  SystemAPI,
  AgentNegotiationAPI,
  DialogueWSListener,
};
