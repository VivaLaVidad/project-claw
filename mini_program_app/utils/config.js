// 统一后端地址配置（腾讯云优先）
// 注意：请替换成你已备案并配置 HTTPS 的腾讯云域名
const BASE_URL = 'https://api.projectclaw.cn';

const BASE_URL_PRESETS = {
  tencent: 'https://api.projectclaw.cn',
  railway: 'https://project-claw-production.up.railway.app',
  zeabur: 'https://project-claw-hub.zeabur.app',
  local: 'http://127.0.0.1:8765',
};

module.exports = {
  BASE_URL,
  BASE_URL_PRESETS,
};
