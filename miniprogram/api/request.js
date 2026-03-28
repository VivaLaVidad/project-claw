// api/request.js - Project Claw API 层 v4.0（工业级）
// 改进：请求重试+指数退避，统一错误处理，WS指数退避重连

const MAX_RETRIES     = 3;
const RETRY_BASE_MS   = 400;
const DEFAULT_TIMEOUT = 12000;
const NO_RETRY_CODES  = new Set([400, 401, 403, 404, 422]);

// ─── 基础请求（带重试+指数退避）────────────────────────────
function createRequest(baseUrl, token) {
  const base = (baseUrl || '').replace(/\/$/,'');

  function _sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

  function _raw({ method='GET', path, data, timeout=DEFAULT_TIMEOUT }) {
    return new Promise((resolve, reject) => {
      const header = { 'Content-Type': 'application/json' };
      if (token) header['Authorization'] = `Bearer ${token}`;
      wx.request({
        url: base + path, method, data, header, timeout,
        success(res) {
          if (res.statusCode >= 200 && res.statusCode < 300) { resolve(res.data); }
          else reject({ code: res.statusCode, msg: res.data?.detail || `HTTP ${res.statusCode}`, noRetry: NO_RETRY_CODES.has(res.statusCode) });
        },
        fail(err) { reject({ code: -1, msg: err.errMsg || '网络错误', noRetry: false }); },
      });
    });
  }

  async function request(opts) {
    let lastErr;
    for (let i = 0; i < MAX_RETRIES; i++) {
      try { return await _raw(opts); }
      catch (err) {
        lastErr = err;
        if (err.noRetry) throw err;
        if (i < MAX_RETRIES - 1) await _sleep(RETRY_BASE_MS * Math.pow(2, i) + Math.random() * 100);
      }
    }
    throw lastErr;
  }
  return request;
}

// ─── 对话 API ────────────────────────────────────────────────
function DialogueAPI(request) {
  return {
    upsertClientProfile: p => request({ method:'POST', path:'/a2a/dialogue/profile/client', data:p }),
    upsertMerchantProfile: p => request({ method:'POST', path:'/a2a/dialogue/profile/merchant', data:p }),
    start: p => request({ method:'POST', path:'/a2a/dialogue/start', data:p }),
    clientTurn({ sessionId, clientId, text, expectedPrice }) {
      return request({ method:'POST', path:'/a2a/dialogue/client_turn',
        data:{ session_id:sessionId, client_id:clientId, text, expected_price:expectedPrice||null } });
    },
    getSession: id => request({ method:'GET', path:`/a2a/dialogue/${id}` }),
    close: id => request({ method:'POST', path:`/a2a/dialogue/${id}/close`, data:{} }),
  };
}

// ─── 意图广播 API ─────────────────────────────────────────────
function IntentAPI(request) {
  return {
    broadcast({ clientId, location, demandText, maxPrice, timeout, clientProfile }) {
      return request({ method:'POST', path:'/intent', data:{
        client_id:clientId, location:location||'小程序', demand_text:demandText,
        max_price:maxPrice, timeout:timeout||3.0, client_profile:clientProfile||{},
      }});
    },
  };
}

// ─── 系统 API ─────────────────────────────────────────────────
function SystemAPI(request) {
  return {
    health:  () => request({ method:'GET', path:'/health',  timeout:4000 }),
    stats:   () => request({ method:'GET', path:'/stats',   timeout:5000 }),
    orders:  (limit) => request({ method:'GET', path:`/orders?limit=${limit||50}` }),
    metrics: () => request({ method:'GET', path:'/metrics', timeout:5000 }),
  };
}

// ─── Agent 全自动谈判 API ──────────────────────────────────────
function AgentNegotiationAPI(request) {
  return {
    startAutoNegotiation({ clientId, itemName, expectedPrice, maxDistanceKm, clientProfile }) {
      return request({ method:'POST', path:'/a2a/intent', data:{
        client_id:clientId, item_name:itemName, expected_price:expectedPrice,
        max_distance_km:maxDistanceKm||8.0, timestamp:Date.now()/1000,
        client_profile:clientProfile||{},
      }});
    },
    pollResult: id => request({ method:'GET', path:`/a2a/intent/${id}/result` }),
    reportSatisfaction({ sessionId, clientId, score, priceScore, timeScore }) {
      return request({ method:'POST', path:'/a2a/dialogue/satisfaction', data:{
        session_id:sessionId, client_id:clientId,
        overall:score, price:priceScore, time:timeScore,
      }});
    },
    executeTradeOrder({ merchantId, finalPrice, item, clientId, intentId }) {
      return request({ method:'POST', path:'/execute_trade', data:{
        merchant_id:merchantId, final_price:finalPrice, reply_text:item,
        client_id:clientId, intent_id:intentId||'', eta_minutes:20,
      }});
    },
  };
}

// ─── 画像 API ─────────────────────────────────────────────────
function ProfileAPI(request) {
  return {
    getClient:   id => request({ method:'GET', path:`/profiles/client/${id}` }),
    getMerchant: id => request({ method:'GET', path:`/profiles/merchant/${id}` }),
    upsertClient:   (id, p) => request({ method:'POST', path:'/profiles/client',   data:{ client_id:id, profile:p } }),
    upsertMerchant: (id, p) => request({ method:'POST', path:'/profiles/merchant', data:{ merchant_id:id, profile:p } }),
  };
}

// ─── WebSocket 实时监听（指数退避重连）────────────────────────
class DialogueWSListener {
  constructor(wsBase, clientId, onTurn, onError) {
    this._base      = (wsBase||'').replace(/\/$/,'');
    this._clientId  = clientId;
    this._onTurn    = onTurn;
    this._onError   = onError || (() => {});
    this._task      = null;
    this._connected = false;
    this._stopped   = false;
    this._retryMs   = 1000;
    this._timer     = null;
  }

  connect() { this._stopped = false; this._connect(); }

  disconnect() {
    this._stopped = true;
    if (this._timer) { clearTimeout(this._timer); this._timer = null; }
    if (this._task)  { try { this._task.close(); } catch(e) {} this._task = null; }
    this._connected = false;
  }

  send(data) {
    if (this._connected && this._task)
      this._task.send({ data: JSON.stringify(data) });
  }

  _connect() {
    if (this._stopped) return;
    const url = `${this._base}/ws/a2a/client/${this._clientId}`;
    this._task = wx.connectSocket({ url, header:{ 'Content-Type':'application/json' } });

    this._task.onOpen(() => {
      this._connected = true;
      this._retryMs   = 1000; // 重置退避
    });
    this._task.onMessage(res => {
      try {
        const msg = JSON.parse(res.data);
        if (msg.type === 'a2a_dialogue_turn' || msg.type === 'dialogue_turn') this._onTurn(msg.turn || msg);
        else if (msg.type === 'offers') this._onTurn(msg);
      } catch(e) {}
    });
    this._task.onError(err => {
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
    if (this._stopped) return;
    const delay = Math.min(this._retryMs, 30000);
    this._retryMs = Math.min(this._retryMs * 2, 30000); // 指数退避，最大30s
    this._timer = setTimeout(() => this._connect(), delay);
  }
}

module.exports = {
  createRequest,
  DialogueAPI, IntentAPI, SystemAPI,
  AgentNegotiationAPI, ProfileAPI,
  DialogueWSListener,
};
