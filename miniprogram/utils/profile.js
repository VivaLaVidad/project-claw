// utils/profile.js - C/B 端个性化画像管理 v2.0

const STORAGE_KEY_CLIENT   = 'claw_client_profile_v2';
const STORAGE_KEY_MERCHANT = 'claw_merchant_profile_v2';
const STORAGE_KEY_HISTORY  = 'claw_search_history';
const STORAGE_KEY_ORDERS   = 'claw_local_orders';

function defaultClientProfile(clientId) {
  return {
    client_id: clientId,
    nickname: '买手',
    budget_min: 10.0,
    budget_max: 30.0,
    price_sensitivity: 0.8,
    time_urgency: 0.5,
    quality_preference: 0.6,
    preferred_categories: [],
    custom_tags: [],
    created_at: Date.now() / 1000,
  };
}

function defaultMerchantProfile(merchantId) {
  return {
    merchant_id: merchantId,
    name: '我的店铺',
    bottom_price: 10.0,
    normal_price: 18.0,
    max_discount_rate: 0.15,
    delivery_time_minutes: 20,
    quality_score: 0.85,
    service_score: 0.80,
    inventory_status: {},
    custom_tags: [],
    description: '',
    is_open: true,
  };
}

function saveClientProfile(profile) {
  try { wx.setStorageSync(STORAGE_KEY_CLIENT, profile); } catch(e) {}
}

function loadClientProfile(clientId) {
  try {
    return wx.getStorageSync(STORAGE_KEY_CLIENT) || defaultClientProfile(clientId);
  } catch(e) { return defaultClientProfile(clientId); }
}

function saveMerchantProfile(profile) {
  try { wx.setStorageSync(STORAGE_KEY_MERCHANT, profile); } catch(e) {}
}

function loadMerchantProfile(merchantId) {
  try {
    return wx.getStorageSync(STORAGE_KEY_MERCHANT) || defaultMerchantProfile(merchantId);
  } catch(e) { return defaultMerchantProfile(merchantId); }
}

// 搜索历史
function addSearchHistory(item) {
  try {
    let history = wx.getStorageSync(STORAGE_KEY_HISTORY) || [];
    history = [item, ...history.filter(h => h !== item)].slice(0, 10);
    wx.setStorageSync(STORAGE_KEY_HISTORY, history);
  } catch(e) {}
}
function getSearchHistory() {
  try { return wx.getStorageSync(STORAGE_KEY_HISTORY) || []; } catch(e) { return []; }
}
function clearSearchHistory() {
  try { wx.removeStorageSync(STORAGE_KEY_HISTORY); } catch(e) {}
}

// 本地订单缓存（离线时展示）
function saveLocalOrder(order) {
  try {
    let orders = wx.getStorageSync(STORAGE_KEY_ORDERS) || [];
    orders = [order, ...orders].slice(0, 100);
    wx.setStorageSync(STORAGE_KEY_ORDERS, orders);
  } catch(e) {}
}
function getLocalOrders() {
  try { return wx.getStorageSync(STORAGE_KEY_ORDERS) || []; } catch(e) { return []; }
}

// 满意度计算
function calcClientSatisfaction(profile, offeredPrice, deliveryTime) {
  const priceScore = offeredPrice <= profile.budget_min
    ? 1.0
    : offeredPrice <= profile.budget_max
      ? 1.0 - (offeredPrice - profile.budget_min) / (profile.budget_max - profile.budget_min) * 0.3
      : Math.max(0, 0.5 - (offeredPrice - profile.budget_max) / profile.budget_max);
  const timeScore = Math.max(0, 1.0 - (deliveryTime / 40.0) * profile.time_urgency);
  const overall = priceScore * 0.6 + timeScore * 0.4;
  return {
    overall: Math.round(overall * 100),
    price:   Math.round(priceScore * 100),
    time:    Math.round(timeScore * 100),
  };
}

// 构建 intent
function buildIntent(clientId, itemName, expectedPrice, maxDistanceKm) {
  return {
    intent_id: 'mp_' + Date.now() + '_' + Math.random().toString(36).slice(2, 7),
    client_id: clientId,
    item_name: itemName,
    expected_price: expectedPrice,
    max_distance_km: maxDistanceKm || 8.0,
    timestamp: Date.now() / 1000,
  };
}

// 格式化时间
function formatTime(ts) {
  if (!ts) return '-';
  const d = new Date(Number(ts) * 1000);
  const now = new Date();
  const diffH = (now - d) / 3600000;
  if (diffH < 1) return Math.floor(diffH * 60) + '分钟前';
  if (diffH < 24) return Math.floor(diffH) + '小时前';
  return `${d.getMonth()+1}/${d.getDate()} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;
}

// 状态映射
const STATUS_TEXT  = { created:'已创建', broadcasted:'广播中', executing:'执行中', executed:'已成交', failed:'失败', OPEN:'进行中', CLOSED:'已结束' };
const STATUS_CLASS = { created:'gray', broadcasted:'blue', executing:'orange', executed:'green', failed:'red', OPEN:'blue', CLOSED:'gray' };
function statusText(s)  { return STATUS_TEXT[s]  || s; }
function statusClass(s) { return 'status-' + (STATUS_CLASS[s] || 'gray'); }

module.exports = {
  defaultClientProfile, defaultMerchantProfile,
  saveClientProfile, loadClientProfile,
  saveMerchantProfile, loadMerchantProfile,
  addSearchHistory, getSearchHistory, clearSearchHistory,
  saveLocalOrder, getLocalOrders,
  calcClientSatisfaction, buildIntent,
  formatTime, statusText, statusClass,
};
