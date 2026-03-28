// api/request.js - Project Claw API 层 v5.0（工业级）
// 完整对齐后端所有接口：signaling / dialogue / A2A / profiles / orders

const MAX_RETRIES     = 3;
const RETRY_BASE_MS   = 400;
const DEFAULT_TIMEOUT = 12000;
const NO_RETRY_CODES  = new Set([400, 401, 403, 404, 422]);

// ── 基础请求（带重试+指数退避）──────────────────────────────
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
          if (res.statusCode >= 200 && res.statusCode < 300) resolve(res.data);
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

// ── 系统 API（对齐 /health /stats /orders /metrics）────────
function SystemAPI(request) {
  return {
    health:       ()      => request({ method:'GET', path:'/health', timeout:4000 }),
    stats:        ()      => request({ method:'GET', path:'/stats',  timeout:5000 }),
    orders:       (limit) => request({ method:'GET', path:`/orders?limit=${limit||50}` }),
    orderDetail:  (id)    => request({ method:'GET', path:`/orders/${id}` }),
    metrics:      ()      => request({ method:'GET', path:'/metrics', timeout:5000 }),
  };
}

// ── 信令 API（对齐 /intent /execute_trade）─────────────────
function IntentAPI(request) {
  return {
    // POST /intent  → SignalingResponse { intent_id, offers, total_merchants, responded, elapsed_ms }
    broadcast({ clientId, location, demandText, maxPrice, timeout, clientProfile }) {
      return request({ method:'POST', path:'/intent', data:{
        client_id:      clientId,
        location:       location || '小程序',
        demand_text:    demandText,
        max_price:      maxPrice,
        timeout:        timeout  || 3.0,
        client_profile: clientProfile || {},
      }});
    },
    // POST /execute_trade → { ok, trade_id }
    executeTrade({ intentId, clientId, merchantId, replyText, finalPrice, etaMinutes }) {
      return request({ method:'POST', path:'/execute_trade', data:{
        intent_id:   intentId,
        client_id:   clientId,
        merchant_id: merchantId,
        reply_text:  replyText  || '',
        final_price: finalPrice,
        eta_minutes: etaMinutes || 20,
      }});
    },
  };
}

// ── A2A 全自动谈判 API（对齐 /a2a/intent /a2a/intent/:id/result）
function AgentNegotiationAPI(request) {
  return {
    // POST /a2a/intent
    startAutoNegotiation({ clientId, itemName, expectedPrice, maxDistanceKm, clientProfile }) {
      return request({ method:'POST', path:'/a2a/intent', data:{
        client_id:       clientId,
        item_name:       itemName,
        expected_price:  expectedPrice,
        max_distance_km: maxDistanceKm || 8.0,
        timestamp:       Date.now() / 1000,
        client_profile:  clientProfile || {},
      }});
    },
    // GET /a2a/intent/:id/result
    pollResult: (id) => request({ method:'GET', path:`/a2a/intent/${id}/result` }),
    // POST /a2a/dialogue/satisfaction
    reportSatisfaction({ sessionId, clientId, score, priceScore, timeScore }) {
      return request({ method:'POST', path:'/a2a/dialogue/satisfaction', data:{
        session_id: sessionId,
        client_id:  clientId,
        overall:    score,
        price:      priceScore,
        time:       timeScore,
      }});
    },
  };
}

// ── 对话 API（对齐 /a2a/dialogue/* 全部接口）───────────────
function DialogueAPI(request) {
  return {
    // POST /a2a/dialogue/profile/client
    upsertClientProfile:   (p) => request({ method:'POST', path:'/a2a/dialogue/profile/client',   data:p }),
    // POST /a2a/dialogue/profile/merchant
    upsertMerchantProfile: (p) => request({ method:'POST', path:'/a2a/dialogue/profile/merchant', data:p }),
    // POST /a2a/dialogue/start → { session_id }
    start({ intent, merchantId, openingText }) {
      return request({ method:'POST', path:'/a2a/dialogue/start', data:{
        intent,
        merchant_id:  merchantId,
        opening_text: openingText || '请给我一个更好的方案',
      }});
    },
    // POST /a2a/dialogue/client_turn
    clientTurn({ sessionId, clientId, text, expectedPrice }) {
      return request({ method:'POST', path:'/a2a/dialogue/client_turn', data:{
        session_id:     sessionId,
        client_id:      clientId,
        text,
        expected_price: expectedPrice || null,
      }});
    },
    // GET /a2a/dialogue/:id → { session, turns }
    getSession: (id) => request({ method:'GET', path:`/a2a/dialogue/${id}` }),
    // POST /a2a/dialogue/:id/close
    close: (id) => request({ method:'POST', path:`/a2a/dialogue/${id}/close`, data:{} }),
  };
}

// ── 画像 API（对齐 /profiles/* 接口）───────────────────────
function ProfileAPI(request) {
  return {
    getClient:      (id) => request({ method:'GET',  path:`/profiles/client/${id}` }),
    getMerchant:    (id) => request({ method:'GET',  path:`/profiles/merchant/${id}` }),
    upsertClient:   (id, p) => request({ method:'POST', path:'/profiles/client',   data:{ client_id:id,   profile:p } }),
    upsertMerchant: (id, p) => request({ method:'POST', path:'/profiles/merchant', data:{ merchant_id:id, profile:p } }),
  };
}

// ── WebSocket 实时监听（指数退避重连）───────────────────────
class DialogueWSListener {
  constructor(wsBase, clientId, onMessage, onError) {
    this._base      = (wsBase || '').replace(/\/$/,'');
    this._clientId  = clientId;
    this._onMessage = onMessage;
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
    if (this._task)  { try { this._task.close(); } catch (e) {} this._task = null; }
    this._connected = false;
  }

  send(data) {
    if (this._connected && this._task)
      this._task.send({ data: JSON.stringify(data) });
  }

  _connect() {
    if (this._stopped) return;
    // 对齐后端 /ws/a2a/client/:clientId 路由
    const url = `${this._base}/ws/a2a/client/${this._clientId}`;
    this._task = wx.connectSocket({ url, header: { 'Content-Type': 'application/json' } });

    this._task.onOpen(() => {
      this._connected = true;
      this._retryMs   = 1000;
    });

    this._task.onMessage(res => {
      try {
        const msg = JSON.parse(res.data);
        // 对齐后端消息类型：a2a_dialogue_turn / offers / ping
        if (msg.type === 'a2a_dialogue_turn' || msg.type === 'dialogue_turn') {
          this._onMessage({ ...msg, _msgType: 'turn' });
        } else if (msg.type === 'offers') {
          this._onMessage({ ...msg, _msgType: 'offers' });
        } else if (msg.type === 'ping') {
          this.send({ type: 'pong', ts: Date.now() / 1000 });
        }
      } catch (e) { console.warn('[WS] parse error', e); }
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
    this._retryMs = Math.min(this._retryMs * 2, 30000);
    this._timer = setTimeout(() => this._connect(), delay);
  }
}

module.exports = {
  createRequest,
  SystemAPI, IntentAPI, DialogueAPI,
  AgentNegotiationAPI, ProfileAPI,
  DialogueWSListener,
};
