// utils/profile.js - C/B 端个性化画像管理

const STORAGE_KEY_CLIENT = 'claw_client_profile';
const STORAGE_KEY_MERCHANT = 'claw_merchant_profile';

/**
 * 默认 C 端画像
 */
function defaultClientProfile(clientId) {
  return {
    client_id: clientId,
    budget_min: 10.0,
    budget_max: 30.0,
    price_sensitivity: 0.8,
    time_urgency: 0.5,
    quality_preference: 0.6,
    custom_tags: [],
  };
}

/**
 * 默认 B 端画像
 */
function defaultMerchantProfile(merchantId) {
  return {
    merchant_id: merchantId,
    bottom_price: 10.0,
    normal_price: 18.0,
    max_discount_rate: 0.15,
    delivery_time_minutes: 20,
    quality_score: 0.85,
    service_score: 0.80,
    inventory_status: {},
    custom_tags: [],
  };
}

/**
 * 保存 C 端画像到本地
 */
function saveClientProfile(profile) {
  wx.setStorageSync(STORAGE_KEY_CLIENT, profile);
}

/**
 * 读取 C 端画像
 */
function loadClientProfile(clientId) {
  return wx.getStorageSync(STORAGE_KEY_CLIENT) || defaultClientProfile(clientId);
}

/**
 * 保存 B 端画像到本地
 */
function saveMerchantProfile(profile) {
  wx.setStorageSync(STORAGE_KEY_MERCHANT, profile);
}

/**
 * 读取 B 端画像
 */
function loadMerchantProfile(merchantId) {
  return wx.getStorageSync(STORAGE_KEY_MERCHANT) || defaultMerchantProfile(merchantId);
}

/**
 * 计算 C 端满意度（前端本地版）
 */
function calcClientSatisfaction(profile, offeredPrice, deliveryTime) {
  const priceScore = offeredPrice <= profile.budget_min
    ? 1.0
    : offeredPrice <= profile.budget_max
      ? 1.0 - (offeredPrice - profile.budget_min) / (profile.budget_max - profile.budget_min) * 0.3
      : 0.0;
  const timeScore = Math.max(0, 1.0 - (deliveryTime / 30.0) * profile.time_urgency);
  const overall = priceScore * 0.6 + timeScore * 0.4;
  return {
    overall: Math.round(overall * 100),
    price: Math.round(priceScore * 100),
    time: Math.round(timeScore * 100),
  };
}

/**
 * 构造 intent 对象
 */
function buildIntent(clientId, itemName, expectedPrice, maxDistanceKm = 8.0) {
  return {
    intent_id: 'mp_' + Date.now() + '_' + Math.random().toString(36).slice(2, 7),
    client_id: clientId,
    item_name: itemName,
    expected_price: expectedPrice,
    max_distance_km: maxDistanceKm,
    timestamp: Date.now() / 1000,
  };
}

module.exports = {
  defaultClientProfile,
  defaultMerchantProfile,
  saveClientProfile,
  loadClientProfile,
  saveMerchantProfile,
  loadMerchantProfile,
  calcClientSatisfaction,
  buildIntent,
};
