const { getBaseUrl } = require('./api');

const B_TOKEN_KEY = 'claw_b_token';
const B_MID_KEY = 'claw_b_merchant_id';
const B_TIMEOUT_MS = 30000;

function getMerchantToken() { return wx.getStorageSync(B_TOKEN_KEY) || ''; }
function setMerchantToken(t) { if (t) wx.setStorageSync(B_TOKEN_KEY, t); }
function clearMerchantToken() { wx.removeStorageSync(B_TOKEN_KEY); }
function getMerchantId() { return wx.getStorageSync(B_MID_KEY) || ''; }
function setMerchantId(mid) { if (mid) wx.setStorageSync(B_MID_KEY, mid); }

function _bRequest({ url, method = 'GET', data }) {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${getBaseUrl()}${url}`,
      method,
      data,
      timeout: B_TIMEOUT_MS,
      header: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${getMerchantToken()}`,
      },
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300) return resolve(res.data);
        if (res.statusCode === 401) clearMerchantToken();
        reject({ code: res.statusCode, detail: (res.data && (res.data.detail || res.data.message)) || `HTTP_${res.statusCode}` });
      },
      fail(err) { reject({ code: 0, detail: (err && err.errMsg) || 'network_error' }); },
    });
  });
}

function merchantLogin(merchantId, key, promoterId = '') {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${getBaseUrl()}/api/v1/auth/merchant`,
      method: 'POST',
      timeout: B_TIMEOUT_MS,
      data: {
        merchant_id: merchantId,
        key,
        promoter_id: promoterId,
      },
      header: { 'Content-Type': 'application/json' },
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300 && res.data && res.data.token) {
          setMerchantToken(res.data.token);
          setMerchantId(merchantId);
          resolve(res.data);
          return;
        }
        reject({ code: res.statusCode, detail: (res.data && (res.data.detail || res.data.message)) || 'merchant_auth_failed' });
      },
      fail(err) { reject({ code: 0, detail: (err && err.errMsg) || 'network_error' }); },
    });
  });
}

function merchantDashboard() {
  return _bRequest({ url: '/api/v1/merchant/dashboard' });
}

function merchantOrders(limit = 50, status = '') {
  const q = status ? `?limit=${limit}&status=${encodeURIComponent(status)}` : `?limit=${limit}`;
  return _bRequest({ url: `/api/v1/merchant/orders${q}` });
}

function merchantSetAccepting(accepting) {
  return _bRequest({ url: '/api/v1/merchant/status', method: 'POST', data: { accepting: !!accepting } });
}

function merchantWallet() {
  return _bRequest({ url: '/api/v1/merchant/wallet' });
}

function merchantDeviceStatus() {
  return _bRequest({ url: '/api/v1/merchant/device-status' });
}

module.exports = {
  getMerchantToken,
  clearMerchantToken,
  getMerchantId,
  merchantLogin,
  merchantDashboard,
  merchantOrders,
  merchantSetAccepting,
  merchantWallet,
  merchantDeviceStatus,
};
