// 统一后端地址配置（默认走生产）
// 运行时可在小程序内通过 setBaseUrl 覆盖
const BASE_URL = 'https://project-claw-production.up.railway.app';

const BASE_URL_PRESETS = {
  railway: 'https://project-claw-production.up.railway.app',
  zeabur: 'https://project-claw-hub.zeabur.app',
  local: 'http://127.0.0.1:8765',
};

module.exports = {
  BASE_URL,
  BASE_URL_PRESETS,
};
