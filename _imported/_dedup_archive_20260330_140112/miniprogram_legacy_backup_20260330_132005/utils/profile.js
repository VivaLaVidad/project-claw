// utils/profile.js - Project Claw 画像管理 v4.0（工业级）
// 对齐后端 A2A_TradeIntent / A2A_DialogueSession 协议

const PROFILE_VERSION  = 4;
const KEY_CLIENT       = `claw_client_profile_v${PROFILE_VERSION}`;
const KEY_MERCHANT     = `claw_merchant_profile_v${PROFILE_VERSION}`;
const KEY_HISTORY      = 'claw_search_history_v4';
const KEY_ORDERS       = 'claw_local_orders_v4';
const KEY_SESSIONS     = 'claw_sessions_v4';
const PROFILE_TTL_MS   = 7 * 24 * 3600 * 1000;
const MAX_HISTORY      = 20;
const MAX_LOCAL_ORDERS = 100;
const MAX_SESSIONS     = 50;

function defaultClientProfile(clientId) {
  return {
    _v: PROFILE_VERSION, _ts: Date.now(),
    client_id: clientId || 'unknown',
    nickname: '买手',
    budget_min: 10.0, budget_max: 30.0,
    price_sensitivity: 0.8, time_urgency: 0.5, quality_preference: 0.6,
    preferred_categories: [], custom_tags: [],
    created_at: Date.now() / 1000,
  };
}

function defaultMerchantProfile(merchantId) {
  return {
    _v: PROFILE_VERSION, _ts: Date.now(),
    merchant_id: merchantId || 'unknown',
    name: '我的店铺',
    bottom_price: 10.0, normal_price: 18.0,
    max_discount_rate: 0.15, delivery_time_minutes: 20,
    quality_score: 0.85, service_score: 0.80,
    inventory_status: {}, custom_tags: [],
    description: '', is_open: true,
  };
}

function _safeGet(key, fallback) {
  try { const v = wx.getStorageSync(key); return (v !== '' && v != null) ? v : fallback; }
  catch (e) { return fallback; }
}
function _safeSet(key, val) {
  try { wx.setStorageSync(key, val); return true; }
  catch (e) { console.error('[Profile] set failed:', key, e); return false; }
}
function _safeRemove(key) { try { wx.removeStorageSync(key); } catch (e) {} }
function _isExpired(p) { return !p || !p._ts || (Date.now() - p._ts) > PROFILE_TTL_MS; }

function saveClientProfile(profile) {
  if (!profile) return false;
  return _safeSet(KEY_CLIENT, { ...profile, _v: PROFILE_VERSION, _ts: Date.now() });
}
function loadClientProfile(clientId) {
  const s = _safeGet(KEY_CLIENT, null);
  if (s && s._v === PROFILE_VERSION && !_isExpired(s)) return s;
  const def = defaultClientProfile(clientId);
  if (s) ['nickname','budget_min','budget_max','price_sensitivity','time_urgency',
    'quality_preference','preferred_categories','custom_tags']
    .forEach(k => { if (s[k] !== undefined) def[k] = s[k]; });
  saveClientProfile(def);
  return def;
}
function updateClientProfile(clientId, patch) {
  const cur = loadClientProfile(clientId);
  const upd = { ...cur, ...patch };
  saveClientProfile(upd);
  return upd;
}

function saveMerchantProfile(profile) {
  if (!profile) return false;
  return _safeSet(KEY_MERCHANT, { ...profile, _v: PROFILE_VERSION, _ts: Date.now() });
}
function loadMerchantProfile(merchantId) {
  const s = _safeGet(KEY_MERCHANT, null);
  if (s && s._v === PROFILE_VERSION && !_isExpired(s)) return s;
  const def = defaultMerchantProfile(merchantId);
  if (s) ['name','bottom_price','normal_price','max_discount_rate','delivery_time_minutes',
    'quality_score','service_score','custom_tags','description','is_open']
    .forEach(k => { if (s[k] !== undefined) def[k] = s[k]; });
  saveMerchantProfile(def);
  return def;
}

function addSearchHistory(item) {
  if (!item) return;
  const h = _safeGet(KEY_HISTORY, []);
  _safeSet(KEY_HISTORY, [item.trim(), ...h.filter(x => x !== item.trim())].slice(0, MAX_HISTORY));
}
function getSearchHistory() { return _safeGet(KEY_HISTORY, []); }
function clearSearchHistory() { _safeRemove(KEY_HISTORY); }

function saveLocalOrder(order) {
  if (!order || !order.intent_id) return;
  const orders = _safeGet(KEY_ORDERS, []);
  _safeSet(KEY_ORDERS, [{ ...order, _cached_at: Date.now() },
    ...orders.filter(o => o.intent_id !== order.intent_id)].slice(0, MAX_LOCAL_ORDERS));
}
function getLocalOrders() { return _safeGet(KEY_ORDERS, []); }
function clearLocalOrders() { _safeRemove(KEY_ORDERS); }

function saveSession(session) {
  if (!session || !session.session_id) return;
  const sessions = _safeGet(KEY_SESSIONS, []);
  _safeSet(KEY_SESSIONS, [{ ...session, _cached_at: Date.now() },
    ...sessions.filter(s => s.session_id !== session.session_id)].slice(0, MAX_SESSIONS));
}
function getSessions() { return _safeGet(KEY_SESSIONS, []); }

function calcClientSatisfaction(profile, offeredPrice, deliveryMinutes) {
  const p = profile || {};
  const bMin = Number(p.budget_min) || 10;
  const bMax = Number(p.budget_max) || 30;
  const tu   = Number(p.time_urgency) || 0.5;
  let ps;
  if (offeredPrice <= bMin)       ps = 1.0;
  else if (offeredPrice <= bMax)  ps = 1.0 - ((offeredPrice-bMin)/Math.max(1,bMax-bMin))*0.4;
  else                            ps = Math.max(0, 0.6-(offeredPrice-bMax)/Math.max(1,bMax)*0.5);
  const ts = Math.max(0, 1.0-(deliveryMinutes/45.0)*tu);
  const ov = ps*0.65 + ts*0.35;
  return {
    overall: Math.round(Math.min(100, Math.max(0, ov*100))),
    price:   Math.round(Math.min(100, Math.max(0, ps*100))),
    time:    Math.round(Math.min(100, Math.max(0, ts*100))),
  };
}

// 对齐后端 /intent 接口 ClientIntent 模型
function buildIntent(clientId, itemName, expectedPrice) {
  return {
    client_id:      clientId,
    location:       '小程序',
    demand_text:    String(itemName).trim(),
    max_price:      Number(expectedPrice),
    timeout:        3.0,
    client_profile: {},
  };
}

// 对齐后端 A2A_TradeIntent（/a2a/intent 接口）
function buildA2AIntent(clientId, itemName, expectedPrice, maxDistanceKm) {
  return {
    client_id:       clientId,
    item_name:       String(itemName).trim(),
    expected_price:  Number(expectedPrice),
    max_distance_km: Number(maxDistanceKm) || 8.0,
    timestamp:       Date.now() / 1000,
  };
}

function formatTime(ts) {
  if (!ts) return '-';
  const d = new Date(Number(ts) * 1000);
  const now = new Date();
  const diffH = (now - d) / 3600000;
  if (diffH < 1/60)  return '刚刚';
  if (diffH < 1)     return `${Math.floor(diffH*60)}分钟前`;
  if (diffH < 24)    return `${Math.floor(diffH)}小时前`;
  if (diffH < 48)    return '昨天';
  return `${d.getMonth()+1}/${d.getDate()} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;
}

const STATUS_TEXT  = { created:'已创建', broadcasted:'广播中', offered:'报价中', executing:'执行中', executed:'已成交', failed:'失败', OPEN:'进行中', CLOSED:'已结束' };
const STATUS_CLASS = { created:'gray', broadcasted:'blue', offered:'orange', executing:'orange', executed:'green', failed:'red', OPEN:'blue', CLOSED:'gray' };
function statusText(s)  { return STATUS_TEXT[s]  || s || '-'; }
function statusClass(s) { return `status-${STATUS_CLASS[s] || 'gray'}`; }

module.exports = {
  defaultClientProfile, defaultMerchantProfile,
  saveClientProfile, loadClientProfile, updateClientProfile,
  saveMerchantProfile, loadMerchantProfile,
  addSearchHistory, getSearchHistory, clearSearchHistory,
  saveLocalOrder, getLocalOrders, clearLocalOrders,
  saveSession, getSessions,
  calcClientSatisfaction, buildIntent, buildA2AIntent,
  formatTime, statusText, statusClass,
};
