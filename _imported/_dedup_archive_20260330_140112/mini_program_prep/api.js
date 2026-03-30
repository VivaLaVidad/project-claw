// mini_program_prep/api.js
// 微信小程序端 API 适配层（可直接迁移到 miniprogram/utils/api.js）

const BASE_URL = 'https://your-domain.com';

function request({ url, method = 'GET', data }) {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${BASE_URL}${url}`,
      method,
      data,
      timeout: 12000,
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data);
        } else {
          reject(res.data || { detail: `HTTP_${res.statusCode}` });
        }
      },
      fail: reject,
    });
  });
}

export function getOnlineMerchants() {
  return request({ url: '/api/v1/merchants/online' });
}

export function requestTrade(payload) {
  return request({ url: '/api/v1/trade/request', method: 'POST', data: payload });
}

export function getTradeSnapshot(requestId) {
  return request({ url: `/api/v1/trade/${requestId}` });
}

export function executeTrade(payload) {
  return request({ url: '/api/v1/trade/execute', method: 'POST', data: payload });
}
