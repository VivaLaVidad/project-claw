/**
 * Project Claw v15.4 - utils/api.js
 * 工业级 HTTP 层：多环境自动切换、JWT 刷新、A2A 双重鉴权、指数退避、SSE 可销毁流
 */

const CONFIG = {
  development: 'http://127.0.0.1:8765',
  tencentCloud: 'https://api.projectclaw.cn',
  railway: 'https://project-claw-production.up.railway.app',
  production: 'https://api.projectclaw.cn',
};

const BASE_URL_PRESETS = {
  tencent: CONFIG.tencentCloud,
  production: CONFIG.production,
  railway: CONFIG.railway,
  zeabur: CONFIG.railway,
  local: CONFIG.development,
};

const BASE_URL_KEY = 'claw_base_url_override';
const TOKEN_KEY = 'claw_token';
const TIMEOUT_MS = 45000;
const MAX_RETRY = 1;

let _customA2ASigner = null;
let _preflightWarnAt = 0;
let _loginPromise = null;

function _getEnvVersion() {
  try {
    const info = wx.getAccountInfoSync && wx.getAccountInfoSync();
    return (info && info.miniProgram && info.miniProgram.envVersion) || 'release';
  } catch (_) {
    return 'release';
  }
}

function _resolveDefaultBaseUrl() {
  const envVersion = _getEnvVersion();
  if (envVersion === 'develop') return CONFIG.tencentCloud;
  if (envVersion === 'trial') return CONFIG.production;
  return CONFIG.production;
}

function getBaseUrl() {
  return (wx.getStorageSync(BASE_URL_KEY) || _resolveDefaultBaseUrl()).replace(/\/$/, '');
}

function setBaseUrl(url) {
  const v = String(url || '').trim();
  if (!v) {
    wx.removeStorageSync(BASE_URL_KEY);
    return _resolveDefaultBaseUrl();
  }
  wx.setStorageSync(BASE_URL_KEY, v.replace(/\/$/, ''));
  return getBaseUrl();
}

function resetBaseUrl() {
  wx.removeStorageSync(BASE_URL_KEY);
  return _resolveDefaultBaseUrl();
}

if (!/^https:\/\//.test(getBaseUrl())) {
  console.warn('[Config] BASE_URL 应为 https 域名，当前值:', getBaseUrl());
}

function getToken() { return wx.getStorageSync(TOKEN_KEY) || ''; }
function setToken(t) { if (t) wx.setStorageSync(TOKEN_KEY, t); }
function clearToken() { wx.removeStorageSync(TOKEN_KEY); }
function getWsBaseUrl() {
  return getBaseUrl().replace(/^https:/, 'wss:').replace(/^http:/, 'ws:');
}

function preflightCheck() {
  const base = getBaseUrl();
  return new Promise((resolve) => {
    wx.request({
      url: `${base}/health`,
      method: 'GET',
      timeout: 3500,
      success: (res) => {
        resolve(res.statusCode >= 200 && res.statusCode < 500);
      },
      fail: () => {
        const now = Date.now();
        if (now - _preflightWarnAt > 20000) {
          _preflightWarnAt = now;
          wx.showToast({ title: '服务连接超时，请切换网络或联系开发人员', icon: 'none', duration: 2500 });
        }
        resolve(false);
      },
    });
  });
}

function setA2ASigner(fn) {
  _customA2ASigner = typeof fn === 'function' ? fn : null;
}

function _getA2ASigner() {
  if (_customA2ASigner) return _customA2ASigner;
  const app = getApp && getApp();
  if (app && app.globalData && typeof app.globalData.a2aRSASigner === 'function') return app.globalData.a2aRSASigner;
  return null;
}

function _calcBackoffMs(retry) {
  const base = 300;
  const cap = 9000;
  const exp = Math.min(cap, base * (2 ** Math.max(0, retry)));
  const jitter = Math.floor(Math.random() * 180);
  return exp + jitter;
}

function _sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function _buildA2AHeaders({ url, method, body }) {
  const signer = _getA2ASigner();
  if (!signer) return {};

  const ts = String(Math.floor(Date.now() / 1000));
  const nonce = Math.random().toString(36).slice(2, 14);
  const keyId = wx.getStorageSync('claw_rsa_key_id') || 'merchant-rsa-k1';
  const bodyText = body ? JSON.stringify(body) : '{}';
  const canonical = [method.toUpperCase(), url, ts, nonce, bodyText].join('\n');
  const signature = await Promise.resolve(signer(canonical));

  if (!signature) throw { code: 0, detail: 'rsa_signature_failed' };

  return {
    'X-A2A-Signature': String(signature),
    'X-A2A-Alg': 'RSA-SHA256',
    'X-A2A-Timestamp': ts,
    'X-A2A-Nonce': nonce,
    'X-A2A-KeyId': String(keyId),
  };
}

function _request({ url, method = 'GET', data, auth = true, a2aSign = false, _retry = 0 }) {
  return new Promise((resolve, reject) => {
    const header = { 'Content-Type': 'application/json' };
    if (auth) {
      const t = getToken();
      if (t) header.Authorization = `Bearer ${t}`;
    }

    const doRequest = async () => {
      try {
        if (a2aSign) {
          const signed = await _buildA2AHeaders({ url, method, body: data || {} });
          Object.assign(header, signed);
        }
      } catch (_) {
        // 未配置 RSA 签名器时，允许回退到无签名请求
        return;
      }

      wx.request({
        url: `${getBaseUrl()}${url}`,
        method,
        data,
        header,
        timeout: TIMEOUT_MS,
        success(res) {
          if (res.statusCode >= 200 && res.statusCode < 300) {
            resolve(res.data);
            return;
          }

          if (res.statusCode === 401 && _retry < MAX_RETRY) {
            clearToken();
            const app = getApp();
            const cid = (app && app.globalData && app.globalData.clientId) || '';
            if (!cid) { reject({ code: 401, detail: 'no_client_id' }); return; }
            loginAndGetToken(cid)
              .then(async () => {
                await _sleep(_calcBackoffMs(_retry));
                return _request({ url, method, data, auth, a2aSign, _retry: _retry + 1 });
              })
              .then(resolve)
              .catch(reject);
            return;
          }

          if (res.statusCode >= 500 && _retry < MAX_RETRY) {
            _sleep(_calcBackoffMs(_retry))
              .then(() => _request({ url, method, data, auth, a2aSign, _retry: _retry + 1 }))
              .then(resolve)
              .catch(reject);
            return;
          }

          const body = res.data || {};
          reject({
            code: res.statusCode,
            detail: body.detail || body.message || `HTTP_${res.statusCode}`,
          });
        },
        fail(err) {
          if (_retry < MAX_RETRY) {
            _sleep(_calcBackoffMs(_retry))
              .then(() => _request({ url, method, data, auth, a2aSign, _retry: _retry + 1 }))
              .then(resolve)
              .catch(reject);
            return;
          }
          reject({ code: 0, detail: (err && err.errMsg) || 'network_error' });
        },
      });
    };

    doRequest();
  });
}

function loginAndGetToken(clientId) {
  return _request({
    url: '/api/v1/auth/client',
    method: 'POST',
    data: { client_id: clientId },
    auth: false,
  }).then((res) => {
    setToken(res.token || '');
    const app = getApp();
    if (app && app.globalData) app.globalData.clientId = clientId;
    return res;
  });
}

function ensureToken(clientId) {
  if (getToken()) return Promise.resolve();
  return loginAndGetToken(clientId).then(() => {});
}

function healthCheck() {
  return _request({ url: '/health', auth: false });
}

function getOnlineMerchants() {
  return _request({ url: '/api/v1/merchants/online', auth: false });
}

function requestTrade(payload) {
  return _request({ url: '/api/v1/trade/request', method: 'POST', data: payload, a2aSign: false });
}

async function executeTrade(payload) {
  const rid = payload && payload.request_id;
  const oid = payload && payload.offer_id;
  const price = Number(payload && payload.final_price);
  if (!rid || !oid) throw { code: 0, detail: 'invalid_execute_payload' };

  const snap = await getTradeSnapshot(rid);
  const serverOffer = Array.isArray(snap && snap.offers) ? snap.offers.find((o) => o.offer_id === oid) : null;
  if (!serverOffer) throw { code: 409, detail: 'offer_changed_or_expired' };
  if (Number(serverOffer.final_price) !== price) throw { code: 409, detail: 'offer_price_changed' };

  return _request({ url: '/api/v1/trade/execute', method: 'POST', data: payload, a2aSign: false });
}

function getOrderHistory(limit = 20) {
  return _request({ url: `/api/v1/orders/history?limit=${limit}` });
}

function getTradeSnapshot(rid) {
  return _request({ url: `/api/v1/trade/${rid}` });
}

function _ab2str(buffer) {
  const bytes = new Uint8Array(buffer || new ArrayBuffer(0));
  let out = '';
  for (let i = 0; i < bytes.length; i++) out += String.fromCharCode(bytes[i]);
  return out;
}

function requestTradeStream(payload, handlers = {}, opts = {}) {
  let requestTask = null;
  let destroyed = false;
  let reconnectTimer = null;
  let sseBuffer = '';
  let doneBundle = null;
  let retryCount = 0;
  const maxReconnect = typeof opts.maxReconnect === 'number' ? opts.maxReconnect : 4;

  const cleanup = () => {
    if (reconnectTimer) clearTimeout(reconnectTimer);
    reconnectTimer = null;
    if (requestTask && requestTask.abort) {
      try { requestTask.abort(); } catch (_) {}
    }
    requestTask = null;
    sseBuffer = '';
  };

  const streamPromise = new Promise((resolve, reject) => {
    const token = getToken();

    const parseChunk = (chunkText) => {
      sseBuffer += String(chunkText || '').replace(/\r\n/g, '\n');
      let idx = sseBuffer.indexOf('\n\n');
      while (idx >= 0) {
        const block = sseBuffer.slice(0, idx).trim();
        sseBuffer = sseBuffer.slice(idx + 2);
        if (block) {
          const lines = block.split('\n');
          let eventName = 'message';
          const dataLines = [];
          lines.forEach((line) => {
            if (line.startsWith('event:')) eventName = line.slice(6).trim();
            if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
          });
          const dataText = dataLines.join('\n');
          let dataObj = null;
          try { dataObj = dataText ? JSON.parse(dataText) : null; } catch (_) { dataObj = { raw: dataText }; }

          if (eventName === 'start' && handlers.onStart) handlers.onStart(dataObj || {});
          if (eventName === 'offer' && handlers.onOffer) handlers.onOffer(dataObj || {});
          if (eventName === 'done') {
            doneBundle = dataObj || {};
            if (handlers.onDone) handlers.onDone(doneBundle);
          }
          if (handlers.onEvent) handlers.onEvent(eventName, dataObj || {});
        }
        idx = sseBuffer.indexOf('\n\n');
      }
    };

    const startOnce = async () => {
      if (destroyed) return;

      let signed = {};
      try {
        signed = await _buildA2AHeaders({ url: '/api/v1/trade/request/stream', method: 'POST', body: payload || {} });
      } catch (_) {
        // 未配置 RSA 签名器时，允许回退到无签名请求
        return;
      }

      requestTask = wx.request({
        url: `${getBaseUrl()}/api/v1/trade/request/stream`,
        method: 'POST',
        data: payload,
        timeout: TIMEOUT_MS,
        enableChunked: true,
        responseType: 'arraybuffer',
        header: Object.assign({
          'Content-Type': 'application/json',
          Accept: 'text/event-stream',
          'Cache-Control': 'no-cache',
          'X-Stream-Mode': 'sse',
          Authorization: `Bearer ${token}`,
        }, signed),
        success(res) {
          if (destroyed) return;
          if (res.statusCode >= 200 && res.statusCode < 300) {
            if (doneBundle) {
              cleanup();
              resolve(doneBundle);
              return;
            }
            if (res.data) parseChunk(typeof res.data === 'string' ? res.data : _ab2str(res.data));
            if (doneBundle) {
              cleanup();
              resolve(doneBundle);
            } else if (retryCount < maxReconnect) {
              retryCount += 1;
              reconnectTimer = setTimeout(startOnce, _calcBackoffMs(retryCount));
            } else {
              cleanup();
              reject({ code: 0, detail: 'stream_done_without_bundle' });
            }
            return;
          }
          cleanup();
          reject({ code: res.statusCode, detail: (res.data && (res.data.detail || res.data.message)) || `HTTP_${res.statusCode}` });
        },
        fail(err) {
          if (destroyed) return;
          if (retryCount < maxReconnect) {
            retryCount += 1;
            reconnectTimer = setTimeout(startOnce, _calcBackoffMs(retryCount));
            return;
          }
          cleanup();
          reject({ code: 0, detail: (err && err.errMsg) || 'stream_network_error' });
        },
      });

      if (requestTask && requestTask.onChunkReceived) {
        requestTask.onChunkReceived((res) => {
          if (destroyed) return;
          parseChunk(_ab2str(res.data));
        });
      }
    };

    startOnce();
  });

  streamPromise.destroy = () => {
    destroyed = true;
    cleanup();
  };

  return streamPromise;
}

module.exports = {
  CONFIG,
  BASE_URL: _resolveDefaultBaseUrl(),
  BASE_URL_PRESETS,
  getBaseUrl,
  setBaseUrl,
  resetBaseUrl,
  getToken,
  setToken,
  clearToken,
  getWsBaseUrl,
  preflightCheck,
  setA2ASigner,
  loginAndGetToken,
  ensureToken,
  healthCheck,
  getOnlineMerchants,
  requestTrade,
  requestTradeStream,
  executeTrade,
  getOrderHistory,
  getTradeSnapshot,
};
