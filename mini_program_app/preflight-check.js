#!/usr/bin/env node
/**
 * Project Claw C-End Preflight Check
 * 发布前自动自检：域名/配置/接口连通/页面结构
 */

const fs = require('fs');
const path = require('path');
const https = require('https');
const http = require('http');

const ROOT = __dirname;
const ok = [];
const warn = [];
const fail = [];

function logBanner() {
  console.log('╔══════════════════════════════════════════════════════════════╗');
  console.log('║             Project Claw C-End Preflight v1.0               ║');
  console.log('╚══════════════════════════════════════════════════════════════╝');
}

function read(filePath) {
  return fs.readFileSync(filePath, 'utf8');
}

function exists(p) {
  return fs.existsSync(p);
}

function parseBaseUrl() {
  const configPath = path.join(ROOT, 'utils', 'config.js');
  if (!exists(configPath)) {
    fail.push(`缺少配置文件: ${configPath}`);
    return null;
  }

  const content = read(configPath);
  const m = content.match(/BASE_URL\s*=\s*['"]([^'"]+)['"]/);
  if (!m) {
    fail.push('未在 utils/config.js 中找到 BASE_URL');
    return null;
  }
  return m[1];
}

function checkProjectConfig() {
  const appJsonPath = path.join(ROOT, 'app.json');
  if (!exists(appJsonPath)) {
    fail.push('缺少 app.json');
    return;
  }

  const appJson = JSON.parse(read(appJsonPath));
  const requiredPages = [
    'pages/index/index',
    'pages/offers/offers',
    'pages/result/result',
    'pages/history/history',
    'pages/privacy/privacy',
  ];

  for (const p of requiredPages) {
    if (!appJson.pages || !appJson.pages.includes(p)) {
      fail.push(`app.json 缺少页面路由: ${p}`);
    }
  }

  if (Array.isArray(appJson.requiredPrivateInfos) && appJson.requiredPrivateInfos.includes('getLocation')) {
    ok.push('已声明定位敏感接口 requiredPrivateInfos:getLocation');
  } else {
    warn.push('建议在 app.json 的 requiredPrivateInfos 中包含 getLocation');
  }

  const projectConfigPath = path.join(ROOT, 'project.config.json');
  if (exists(projectConfigPath)) {
    const projectConfig = JSON.parse(read(projectConfigPath));
    if (!projectConfig.appid || projectConfig.appid === 'touristappid') {
      fail.push('project.config.json 的 appid 无效，请改为正式小程序 appid');
    } else {
      ok.push(`检测到 appid: ${projectConfig.appid}`);
    }
  } else {
    warn.push('缺少 project.config.json（开发者工具本地配置）');
  }
}

function checkPagesFiles() {
  const pages = ['index', 'offers', 'result', 'history', 'privacy'];
  for (const name of pages) {
    const dir = path.join(ROOT, 'pages', name);
    const files = [`${name}.js`, `${name}.wxml`, `${name}.wxss`, `${name}.json`];
    for (const f of files) {
      const fp = path.join(dir, f);
      if (!exists(fp)) fail.push(`缺少页面文件: pages/${name}/${f}`);
    }
  }
}

function checkWxmlRisk() {
  const riskPatterns = [
    /\{\{[^\n]*String\(/,
    /\{\{[^\n]*\.slice\(/,
    /\{\{[^\n]*\.padStart\(/,
    /\{\{[^\n]*\?\.[^\n]*\}\}/,
  ];

  const pagesDir = path.join(ROOT, 'pages');
  const stack = [pagesDir];
  while (stack.length) {
    const current = stack.pop();
    const entries = fs.readdirSync(current, { withFileTypes: true });
    for (const e of entries) {
      const p = path.join(current, e.name);
      if (e.isDirectory()) {
        stack.push(p);
      } else if (e.isFile() && e.name.endsWith('.wxml')) {
        const c = read(p);
        for (const rp of riskPatterns) {
          if (rp.test(c)) {
            warn.push(`WXML 存在高风险表达式，建议改为 JS 预计算: ${path.relative(ROOT, p)}`);
            break;
          }
        }
      }
    }
  }
}

function probe(url, timeoutMs = 8000) {
  return new Promise((resolve, reject) => {
    const client = url.startsWith('https://') ? https : http;
    const req = client.get(url, { timeout: timeoutMs }, (res) => {
      let data = '';
      res.on('data', (chunk) => data += chunk);
      res.on('end', () => resolve({ statusCode: res.statusCode, body: data }));
    });
    req.on('timeout', () => {
      req.destroy(new Error('timeout'));
    });
    req.on('error', reject);
  });
}

async function checkBackend(baseUrl) {
  if (!baseUrl) return;

  if (!/^https:\/\//.test(baseUrl)) {
    fail.push(`BASE_URL 必须为 https：${baseUrl}`);
    return;
  }

  ok.push(`BASE_URL: ${baseUrl}`);

  const health = `${baseUrl.replace(/\/$/, '')}/health`;
  try {
    const res = await probe(health);
    if (res.statusCode >= 200 && res.statusCode < 300) {
      ok.push(`/health 可用 (${res.statusCode})`);
    } else {
      fail.push(`/health 不可用，状态码 ${res.statusCode}`);
    }
  } catch (e) {
    fail.push(`/health 请求失败: ${e.message}`);
  }

  const onlineMerchants = `${baseUrl.replace(/\/$/, '')}/api/v1/merchants/online`;
  try {
    const res = await probe(onlineMerchants);
    if (res.statusCode >= 200 && res.statusCode < 300) {
      ok.push(`/api/v1/merchants/online 可用 (${res.statusCode})`);
    } else if (res.statusCode === 404) {
      ok.push('/api/v1/merchants/online 未开放，使用 /health.merchants 作为在线商家来源');
    } else {
      warn.push(`/api/v1/merchants/online 返回 ${res.statusCode}，请确认公开访问策略`);
    }
  } catch (e) {
    warn.push(`/api/v1/merchants/online 请求失败: ${e.message}`);
  }
}

function checkContractFile() {
  const contractPath = path.join(ROOT, '..', 'cloud_server', 'miniprogram_contract.json');
  if (!exists(contractPath)) {
    warn.push('未找到 cloud_server/miniprogram_contract.json，建议补齐以保持前后端协议一致');
    return;
  }

  try {
    const contract = JSON.parse(read(contractPath));
    const endpoints = Array.isArray(contract.endpoints) ? contract.endpoints : [];
    const mustHave = [
      '/health',
      '/api/v1/merchants/online',
      '/api/v1/trade/request',
      '/api/v1/trade/{request_id}',
      '/api/v1/trade/execute',
    ];

    for (const p of mustHave) {
      const hit = endpoints.some((e) => e.path === p);
      if (!hit) warn.push(`协议文件缺少端点定义: ${p}`);
    }

    ok.push('已检测 cloud_server/miniprogram_contract.json');
  } catch (e) {
    warn.push(`读取 miniprogram_contract.json 失败: ${e.message}`);
  }
}

function printResult() {
  console.log('\n✅ PASS');
  ok.forEach(i => console.log('  - ' + i));

  console.log('\n⚠️ WARN');
  if (!warn.length) console.log('  - 无');
  warn.forEach(i => console.log('  - ' + i));

  console.log('\n❌ FAIL');
  if (!fail.length) console.log('  - 无');
  fail.forEach(i => console.log('  - ' + i));

  if (fail.length) {
    console.log('\n结果：未通过，请先修复 FAIL 项。');
    process.exitCode = 1;
    return;
  }

  console.log('\n结果：通过，可进入真机回归和提审阶段。');
}

(async function main() {
  logBanner();
  checkProjectConfig();
  checkPagesFiles();
  checkWxmlRisk();
  checkContractFile();
  const baseUrl = parseBaseUrl();
  await checkBackend(baseUrl);
  printResult();
})();
