# Project Claw 完整启动指南

## 整体架构

```
微信小程序（C端/B端）
      ↓ HTTPS
  后端服务 (signaling_hub)
  ├─ 本地：http://127.0.0.1:8765
  └─ 生产：https://project-claw-production.up.railway.app
```

---

## 一、本地开发启动（推荐调试用）

### 第 1 步：启动后端

在 Cursor 终端或 PowerShell 执行：

```bash
cd "d:\桌面\Project Claw"
.\START_MINIAPP_LOCAL.bat
```

看到以下输出说明启动成功：
```
INFO: Uvicorn running on http://127.0.0.1:8765
```

验证后端：
```bash
powershell -Command "(Invoke-WebRequest http://127.0.0.1:8765/health).Content"
```

### 第 2 步：启动 Streamlit 调试面板（可选）

新开一个终端：
```bash
streamlit run streamlit_debug_panel.py
```
打开浏览器 http://localhost:8501 可以实时监控后端状态。

### 第 3 步：打开微信开发者工具

1. 下载安装：https://developers.weixin.qq.com/miniprogram/dev/devtools/download.html
2. 登录你的微信账号
3. 点击「导入项目」
4. 目录选择：`d:\桌面\Project Claw\mini_program_app`
5. AppID 填写：`wx1f7d608c84f6da6d`
6. 进入项目后点「详情」→「本地设置」→ 勾选「不校验合法域名」
7. 点「清缓存」→「全部清除」
8. 点「编译」

---

## 二、C 端小程序使用

C 端就是普通用户侧，打开微信开发者工具默认看到的就是 C 端。

**页面路径：**
- 首页：`pages/index/index`（询价入口）
- 报价页：`pages/offers/offers`
- 结果页：`pages/result/result`
- 历史订单：`pages/history/history`

**使用流程：**
1. 首页输入商品名称（或点快捷选品）
2. 填写预算
3. 点「立即询价」
4. 等待报价（需要有 B 端商家在线）
5. 选择报价 → 成交

---

## 三、B 端小程序使用

B 端是商家侧。从 C 端首页底部点「B端入口」进入，或直接在开发者工具导航到：

```
pages/b-dashboard/b-dashboard
```

**登录所需：**
- `merchant_id`：商家 ID（任意字符串，如 `merchant-001`）
- `merchant_key`：即后端环境变量 `HUB_MERCHANT_KEY` 的值
  - 本地默认值：`merchant-shared-key`
  - 生产环境：你在 Railway 设置的值

**B 端页面功能：**

| 页面 | 功能 |
|------|------|
| 工作台 | 今日订单/收入、接单开关、在线状态 |
| 订单列表 | 查看所有订单、按状态筛选 |
| 钱包 | 收益统计、账本余额 |
| 设置 | 切换后端地址、设备状态、退出 |

---

## 四、切换 C/B 端（开发者工具操作）

方法 1：顶部菜单栏 → 「页面路径」手动输入
```
pages/b-dashboard/b-dashboard
```

方法 2：编辑 `app.json`，把 B 端页面移到 `pages` 第一个，重新编译即可。

---

## 五、生产环境启动（部署到 Railway）

### 所需环境变量：
```
LEDGER_ENABLED=0
CLEARING_ENABLED=0
SOCIAL_ENABLED=0
HUB_JWT_SECRET=claw-prod-secret-2026-change-me
HUB_MERCHANT_KEY=merchant-prod-key-2026
WECHAT_APPID=wx1f7d608c84f6da6d
HUB_RATE_LIMIT_PER_MIN=60
```

### 部署步骤：
1. 代码推到 GitHub：`git push origin main`
2. Railway 自动部署（需 2-5 分钟）
3. 验证：
   ```bash
   curl https://project-claw-production.up.railway.app/health
   ```

### 小程序切换生产地址：
编辑 `mini_program_app/utils/config.js`：
```javascript
const BASE_URL = 'https://project-claw-production.up.railway.app';
```
或在 B 端小程序「设置」页面点「使用 Railway」按钮即可切换。

---

## 六、一键预检

发布前执行：
```bash
node mini_program_app/preflight-check.js
```

全部 FAIL 为「无」才能发布。

---

## 七、常见问题

**Q：后端无法连接？**
- 本地：确认 `START_MINIAPP_LOCAL.bat` 正在运行，端口 8765
- 生产：确认 Railway 部署成功，访问 `/health`

**Q：B 端登录失败（403）？**
- 检查 `merchant_key` 是否与 `HUB_MERCHANT_KEY` 一致

**Q：C 端询价显示「暂无在线商家」？**
- B 端需要有商家通过 WebSocket 连接上线（`/ws/merchant/{id}`）
- 或通过 edge_box 模拟商家上线

**Q：开发者工具报「域名不合法」？**
- 点「详情」→「本地设置」→ 勾选「不校验合法域名」

---

*Project Claw v14.3 · 智能询价系统 · B+C 双端*
