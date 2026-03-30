/**
 * Project Claw v14.3 - utils/api.js
 * 工业级 HTTP 层：JWT 自动刷新、超时重试、WS 地址转换
 */
const { BASE_URL } = require('./config');

// 小程序必须在 request 合法域名白名单中配置该域名
if (!/^https:\/\//.test(BASE_URL)) {
  console.warn('[Config] BASE_URL 应为 https 域名，当前值:', BASE_URL);
}

const TOKEN_KEY  = 'claw_token';
const TIMEOUT_MS = 45000;
const MAX_RETRY  = 1;

// ── Token 存取 ────────────────────────────────────────────────────────────
function getToken()   { return wx.getStorageSync(TOKEN_KEY) || ''; }
function setToken(t)  { if (t) wx.setStorageSync(TOKEN_KEY, t); }
function clearToken() { wx.removeStorageSync(TOKEN_KEY); }
function getWsBaseUrl() {
  return BASE_URL.replace(/^https:/, 'wss:').replace(/^http:/, 'ws:');
}

// ── 核心请求（支持 401 自动刷新重试） ────────────────────────────────────
function _request({ url, method = 'GET', data, auth = true, _retry = 0 }) {
  return new Promise((resolve, reject) => {
    const header = { 'Content-Type': 'application/json' };
    if (auth) {
      const t = getToken();
      if (t) header['Authorization'] = `Bearer ${t}`;
    }
    wx.request({
      url: `${BASE_URL}${url}`,
      method,
      data,
      header,
      timeout: TIMEOUT_MS,
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data);
          return;
        }
        // 401: token 过期，自动刷新后重试一次
        if (res.statusCode === 401 && _retry < MAX_RETRY) {
          clearToken();
          const app = getApp();
          const cid = (app && app.globalData && app.globalData.clientId) || '';
          if (!cid) { reject({ code: 401, detail: 'no_client_id' }); return; }
          loginAndGetToken(cid)
            .then(() => _request({ url, method, data, auth, _retry: _retry + 1 }))
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
          setTimeout(() => {
            _request({ url, method, data, auth, _retry: _retry + 1 })
              .then(resolve)
              .catch(reject);
          }, 300);
          return;
        }
        reject({ code: 0, detail: (err && err.errMsg) || 'network_error' });
      },
    });
  });
}

// ── Auth ──────────────────────────────────────────────────────────────────
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

// ── 业务接口 ──────────────────────────────────────────────────────────────
function healthCheck() {
  return _request({ url: '/health', auth: false });
}

function getOnlineMerchants() {
  return _request({ url: '/api/v1/merchants/online', auth: false });
}

function requestTrade(payload) {
  return _request({ url: '/api/v1/trade/request', method: 'POST', data: payload });
}

function executeTrade(payload) {
  return _request({ url: '/api/v1/trade/execute', method: 'POST', data: payload });
}

function getOrderHistory(limit = 20) {
  return _request({ url: `/api/v1/orders/history?limit=${limit}` });
}

function getTradeSnapshot(rid) {
  return _request({ url: `/api/v1/trade/${rid}` });
}

module.exports = {
  BASE_URL,
  getToken,
  setToken,
  clearToken,
  getWsBaseUrl,
  loginAndGetToken,
  ensureToken,
  healthCheck,
  getOnlineMerchants,
  requestTrade,
  executeTrade,
  getOrderHistory,
  getTradeSnapshot,
};
