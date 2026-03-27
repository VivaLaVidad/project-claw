// api/request.js - Project Claw 完整 API 层 v3.0

// ─── 基础请求封装 ───
function createRequest(baseUrl, token) {
  return function request({ method = 'GET', path, data, timeout = 12000 } = {}) {
    return new Promise((resolve, reject) => {
      const url = (baseUrl || '').replace(/\/$/, '') + path;
      const header = { 'Content-Type': 'application/json' };
      if (token) header['Authorization'] = `Bearer ${token}`;
      wx.request({
        url, method, data, header,
        timeout,
        success(res) {
          if (res.statusCode >= 200 && res.statusCode < 300) {
            resolve(res.data);
          } else {
            reject({ code: res.statusCode, msg: res.data?.detail || res.data?.message || `HTTP ${res.statusCode}` });
          }
        },
        fail(err) { reject({ code: -1, msg: err.errMsg || '网络错误' }); },
      });
    });
  };
}

// ─── 对话 API ───
function DialogueAPI(request) {
  return {
    upsertClientProfile(payload) {
      return request({ method: 'POST', path: '/a2a/dialogue/profile/client', data: payload });
    },
    upsertMerchantProfile(payload) {
      return request({ method: 'POST', path: '/a2a/dialogue/profile/merchant', data: payload });
    },
    start(payload) {
      return request({ method: 'POST', path: '/a2a/dialogue/start', data: payload });
    },
    clientTurn(payload) {
      return request({ method: 'POST', path: '/a2a/dialogue/client_turn', data: {
        session_id: payload.sessionId,
        client_id: payload.clientId,
        text: payload.text,
        expected_price: payload.expectedPrice || null,
      }});
    },
    getSession(sessionId) {
      return request({ method: 'GET', path: `/a2a/dialogue/${sessionId}` });
    },
    close(sessionId) {
      return request({ method: 'POST', path: `/a2a/dialogue/${sessionId}/close`, data: {} });
    },
  };
}

// ─── 意图广播 API ───
function IntentAPI(request) {
  return {
    broadcast(payload) {
      return request({ method: 'POST', path: '/intent', data: {
        client_id: payload.clientId,
        location: payload.location || '小程序',
        demand_text: payload.demandText,
        max_price: payload.maxPrice,
        timeout: payload.timeout || 3.0,
        client_profile: payload.clientProfile || {},
      }});
    },
  };
}

// ─── 系统 API ───
function SystemAPI(request) {
  return {
    health()  { return request({ method: 'GET', path: '/health', timeout: 4000 }); },
    stats()   { return request({ method: 'GET', path: '/stats',  timeout: 5000 }); },
    orders(limit) { return request({ method: 'GET', path: `/orders?limit=${limit || 50}` }); },
    orderDetail(intentId) { return request({ method: 'GET', path: `/orders/${intentId}` }); },
    metrics() { return request({ method: 'GET', path: '/metrics', timeout: 5000 }); },
  };
}

// ─── B/C Agent 全自动谈判 API ───
function AgentNegotiationAPI(request) {
  return {
    startAutoNegotiation({ clientId, itemName, expectedPrice, maxDistanceKm, clientProfile }) {
      return request({ method: 'POST', path: '/a2a/intent', data: {
        client_id: clientId,
        item_name: itemName,
        expected_price: expectedPrice,
        max_distance_km: maxDistanceKm || 8.0,
        timestamp: Date.now() / 1000,
        client_profile: clientProfile || {},
      }});
    },
    pollResult(intentId) {
      return request({ method: 'GET', path: `/a2a/intent/${intentId}/result` });
    },
    reportSatisfaction({ sessionId, clientId, score, priceScore, timeScore }) {
      return request({ method: 'POST', path: '/a2a/dialogue/satisfaction', data: {
        session_id: sessionId, client_id: clientId,
        overall: score, price: priceScore, time: timeScore,
      }});
    },
    executeTradeOrder({ merchantId, finalPrice, item, clientId, intentId }) {
      return request({ method: 'POST', path: '/execute_trade', data: {
        merchant_id: merchantId, final_price: finalPrice,
        reply_text: item, client_id: clientId,
        intent_id: intentId || '',
        eta_minutes: 20,
      }});
    },
  };
}

// ─── 画像 API ───
function ProfileAPI(request) {
  return {
    getClientProfile(clientId) {
      return request({ method: 'GET', path: `/profiles/client/${clientId}` });
    },
    getMerchantProfile(merchantId) {
      return request({ method: 'GET', path: `/profiles/merchant/${merchantId}` });
    },
    upsertClientProfile(clientId, profile) {
      return request({ method: 'POST', path: '/profiles/client', data: { client_id: clientId, profile } });
    },
    upsertMerchantProfile(merchantId, profile) {
      return request({ method: 'POST', path: '/profiles/merchant', data: { merchant_id: merchantId, profile } });
    },
  };
}

// ─── WebSocket 实时对话监听器 ───
class DialogueWSListener {
  constructor(wsBase, clientId, onTurn, onError) {
    this._wsBase = (wsBase || '').replace(/\/$/, '');
    this._clientId = clientId;
    this._onTurn = onTurn;
    this._onError = onError || (() => {});
    this._task = null;
    this._connected = false;
    this._stopFlag = false;
    this._reconnectTimer = null;
  }

  connect() {
    this._stopFlag = false;
    this._doConnect();
  }

  disconnect() {
    this._stopFlag = true;
    if (this._reconnectTimer) clearTimeout(this._reconnectTimer);
    if (this._task) {
      try { this._task.close(); } catch(e) {}
      this._task = null;
    }
    this._connected = false;
  }

  _doConnect() {
    if (this._stopFlag) return;
    const url = `${this._wsBase}/ws/client/${this._clientId}`;
    this._task = wx.connectSocket({
      url,
      header: { 'Content-Type': 'application/json' },
      complete: () => {},
    });
    this._task.onOpen(() => {
      this._connected = true;
    });
    this._task.onMessage((res) => {
      try {
        const msg = JSON.parse(res.data);
        if (msg.type === 'a2a_dialogue_turn' || msg.type === 'dialogue_turn') {
          this._onTurn(msg.turn || msg);
        } else if (msg.type === 'offers') {
          this._onTurn(msg);
        }
      } catch(e) {}
    });
    this._task.onError((err) => {
      this._connected = false;
      this._onError(err);
      this._scheduleReconnect();
    });
    this._task.onClose(() => {
      this._connected = false;
      this._scheduleReconnect();
    });
  }

  _scheduleReconnect() {
    if (this._stopFlag) return;
    this._reconnectTimer = setTimeout(() => this._doConnect(), 3000);
  }

  send(data) {
    if (this._connected && this._task) {
      this._task.send({ data: JSON.stringify(data) });
    }
  }
}

module.exports = {
  createRequest,
  DialogueAPI,
  IntentAPI,
  SystemAPI,
  AgentNegotiationAPI,
  ProfileAPI,
  DialogueWSListener,
};
