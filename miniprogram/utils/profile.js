// utils/profile.js - Project Claw 画像管理 v3.0（工业级）
// 改进：版本迁移、TTL过期、类型校验、画像diff更新

const PROFILE_VERSION     = 3;
const KEY_CLIENT          = `claw_client_profile_v${PROFILE_VERSION}`;
const KEY_MERCHANT        = `claw_merchant_profile_v${PROFILE_VERSION}`;
const KEY_HISTORY         = 'claw_search_history_v3';
const KEY_ORDERS          = 'claw_local_orders_v3';
const PROFILE_TTL_MS      = 7 * 24 * 3600 * 1000; // 7天
const MAX_HISTORY         = 20;
const MAX_LOCAL_ORDERS    = 100;

// ─── 默认画像 ──────────────────────────────────────────────
function defaultClientProfile(clientId) {
  return {
    _v: PROFILE_VERSION,
    _ts: Date.now(),
    client_id:            clientId || 'unknown',
    nickname:             '买手',
    budget_min:           10.0,
    budget_max:           30.0,
    price_sensitivity:    0.8,
    time_urgency:         0.5,
    quality_preference:   0.6,
    preferred_categories: [],
    custom_tags:          [],
    created_at:           Date.now() / 1000,
  };
}

function defaultMerchantProfile(merchantId) {
  return {
    _v: PROFILE_VERSION,
    _ts: Date.now(),
    merchant_id:           merchantId || 'unknown',
    name:                  '我的店铺',
    bottom_price:          10.0,
    normal_price:          18.0,
    max_discount_rate:     0.15,
    delivery_time_minutes: 20,
    quality_score:         0.85,
    service_score:         0.80,
    inventory_status:      {},
    custom_tags:           [],
    description:           '',
    is_open:               true,
  };
}

// ─── 存储工具 ─────────────────────────────────────────────
function _safeGet(key, fallback) {
  try {
    const val = wx.getStorageSync(key);
    return (val !== '' && val !== null && val !== undefined) ? val : fallback;
  } catch(e) { return fallback; }
}

function _safeSet(key, val) {
  try { wx.setStorageSync(key, val); return true; }
  catch(e) { console.error('[Profile] setStorage failed:', key, e); return false; }
}

function _safeRemove(key) {
  try { wx.removeStorageSync(key); } catch(e) {}
}

// ─── TTL 校验 ─────────────────────────────────────────────
function _isExpired(profile) {
  if (!profile || !profile._ts) return true;
  return (Date.now() - profile._ts) > PROFILE_TTL_MS;
}

// ─── C端画像 ─────────────────────────────────────────────
function saveClientProfile(profile) {
  if (!profile || typeof profile !== 'object') return false;
  return _safeSet(KEY_CLIENT, { ...profile, _v: PROFILE_VERSION, _ts: Date.now() });
}

function loadClientProfile(clientId) {
  const stored = _safeGet(KEY_CLIENT, null);
  if (stored && stored._v === PROFILE_VERSION && !_isExpired(stored)) return stored;
  // 版本不匹配或已过期：重建默认画像，保留已知字段
  const def = defaultClientProfile(clientId);
  if (stored) {
    const safe = ['nickname','budget_min','budget_max','price_sensitivity',
                  'time_urgency','quality_preference','preferred_categories','custom_tags'];
    safe.forEach(k => { if (stored[k] !== undefined) def[k] = stored[k]; });
  }
  saveClientProfile(def);
  return def;
}

function updateClientProfile(clientId, patch) {
  const current = loadClientProfile(clientId);
  const updated  = { ...current, ...patch };
  saveClientProfile(updated);
  return updated;
}

// ─── B端画像 ─────────────────────────────────────────────
function saveMerchantProfile(profile) {
  if (!profile || typeof profile !== 'object') return false;
  return _safeSet(KEY_MERCHANT, { ...profile, _v: PROFILE_VERSION, _ts: Date.now() });
}

function loadMerchantProfile(merchantId) {
  const stored = _safeGet(KEY_MERCHANT, null);
  if (stored && stored._v === PROFILE_VERSION && !_isExpired(stored)) return stored;
  const def = defaultMerchantProfile(merchantId);
  if (stored) {
    const safe = ['name','bottom_price','normal_price','max_discount_rate',
                  'delivery_time_minutes','quality_score','service_score','custom_tags','description','is_open'];
    safe.forEach(k => { if (stored[k] !== undefined) def[k] = stored[k]; });
  }
  saveMerchantProfile(def);
  return def;
}

// ─── 搜索历史 ────────────────────────────────────────────
function addSearchHistory(item) {
  if (!item || typeof item !== 'string') return;
  const history = _safeGet(KEY_HISTORY, []);
  const deduped = [item.trim(), ...history.filter(h => h !== item.trim())].slice(0, MAX_HISTORY);
  _safeSet(KEY_HISTORY, deduped);
}

function getSearchHistory() { return _safeGet(KEY_HISTORY, []); }
function clearSearchHistory() { _safeRemove(KEY_HISTORY); }

// ─── 本地订单缓存 ────────────────────────────────────────
function saveLocalOrder(order) {
  if (!order || !order.intent_id) return;
  const orders = _safeGet(KEY_ORDERS, []);
  // 去重：同 intent_id 更新
  const filtered = orders.filter(o => o.intent_id !== order.intent_id);
  _safeSet(KEY_ORDERS, [{ ...order, _cached_at: Date.now() }, ...filtered].slice(0, MAX_LOCAL_ORDERS));
}

function getLocalOrders() { return _safeGet(KEY_ORDERS, []); }

function clearLocalOrders() { _safeRemove(KEY_ORDERS); }

// ─── 满意度计算 ──────────────────────────────────────────
function calcClientSatisfaction(profile, offeredPrice, deliveryTime) {
  const p = profile || {};
  const budgetMin = Number(p.budget_min) || 10;
  const budgetMax = Number(p.budget_max) || 30;
  const timeUrgency = Number(p.time_urgency) || 0.5;

  let priceScore;
  if (offeredPrice <= budgetMin) {
    priceScore = 1.0;
  } else if (offeredPrice <= budgetMax) {
    priceScore = 1.0 - ((offeredPrice - budgetMin) / Math.max(1, budgetMax - budgetMin)) * 0.4;
  } else {
    priceScore = Math.max(0, 0.6 - (offeredPrice - budgetMax) / Math.max(1, budgetMax) * 0.5);
  }

  const timeScore = Math.max(0, 1.0 - (deliveryTime / 45.0) * timeUrgency);
  const overall   = priceScore * 0.65 + timeScore * 0.35;

  return {
    overall: Math.round(Math.min(100, Math.max(0, overall * 100))),
    price:   Math.round(Math.min(100, Math.max(0, priceScore * 100))),
    time:    Math.round(Math.min(100, Math.max(0, timeScore  * 100))),
  };
}

// ─── 构建 Intent ─────────────────────────────────────────
function buildIntent(clientId, itemName, expectedPrice, maxDistanceKm) {
  return {
    intent_id:       `mp_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
    client_id:       clientId,
    item_name:       String(itemName).trim(),
    expected_price:  Number(expectedPrice),
    max_distance_km: Number(maxDistanceKm) || 8.0,
    timestamp:       Date.now() / 1000,
  };
}

// ─── 时间格式化 ──────────────────────────────────────────
function formatTime(ts) {
  if (!ts) return '-';
  const d    = new Date(Number(ts) * 1000);
  const now  = new Date();
  const diffH = (now - d) / 3600000;
  if (diffH < 1/60) return '刚刚';
  if (diffH < 1)    return `${Math.floor(diffH * 60)}分钟前`;
  if (diffH < 24)   return `${Math.floor(diffH)}小时前`;
  if (diffH < 48)   return '昨天';
  const hh = String(d.getHours()).padStart(2,'0');
  const mm  = String(d.getMinutes()).padStart(2,'0');
  return `${d.getMonth()+1}/${d.getDate()} ${hh}:${mm}`;
}

// ─── 状态映射 ────────────────────────────────────────────
const STATUS_TEXT = {
  created:'已创建', broadcasted:'广播中', offered:'报价中',
  executing:'执行中', executed:'已成交', failed:'失败',
  OPEN:'进行中', CLOSED:'已结束',
};
const STATUS_CLASS = {
  created:'gray', broadcasted:'blue', offered:'orange',
  executing:'orange', executed:'green', failed:'red',
  OPEN:'blue', CLOSED:'gray',
};
function statusText(s)  { return STATUS_TEXT[s]  || s || '-'; }
function statusClass(s) { return `status-${STATUS_CLASS[s] || 'gray'}`; }

module.exports = {
  defaultClientProfile, defaultMerchantProfile,
  saveClientProfile, loadClientProfile, updateClientProfile,
  saveMerchantProfile, loadMerchantProfile,
  addSearchHistory, getSearchHistory, clearSearchHistory,
  saveLocalOrder, getLocalOrders, clearLocalOrders,
  calcClientSatisfaction, buildIntent,
  formatTime, statusText, statusClass,
};
