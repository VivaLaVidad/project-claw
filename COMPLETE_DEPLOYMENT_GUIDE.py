"""
Project Claw v14.3 - Complete Deployment & Startup Guide
工业级商业项目完整部署方案
"""

# ═══════════════════════════════════════════════════════════════════════════
# 📋 部署清单
# ═══════════════════════════════════════════════════════════════════════════

DEPLOYMENT_CHECKLIST = """
【第一阶段】本地开发环境

1. PostgreSQL + Redis 安装
   - PostgreSQL 14+
   - Redis 7+
   - 执行 schema.sql 初始化数据库

2. Python 依赖安装
   pip install -r requirements.txt

3. 环境变量配置 (.env)
   DATABASE_URL=postgresql://user:password@localhost:5432/claw
   REDIS_URL=redis://localhost:6379/0
   WECHAT_APPID=your_appid
   WECHAT_APPSECRET=your_appsecret
   WECHAT_MCH_ID=your_mch_id
   WECHAT_API_V3_KEY=your_api_v3_key
   WECHAT_PRIVATE_KEY_PATH=/path/to/private_key.pem
   JWT_SECRET=your_jwt_secret
   TAILSCALE_AUTH_KEY=your_tailscale_key

4. 本地启动
   python -m uvicorn cloud_server.api_server_pro:app --host 127.0.0.1 --port 8765 --reload

【第二阶段】Railway 生产部署

1. 创建 Railway 项目
   - 连接 GitHub 仓库
   - 配置环境变量（同上）

2. 添加 PostgreSQL 服务
   - Railway 内置 PostgreSQL
   - 自动生成 DATABASE_URL

3. 添加 Redis 服务
   - Railway 内置 Redis
   - 自动生成 REDIS_URL

4. 部署配置
   - Procfile: web: uvicorn cloud_server.api_server_pro:app --host 0.0.0.0 --port $PORT
   - railway.toml: 配置启动命令

5. 自动部署
   - git push → Railway 自动构建和部署

【第三阶段】本地 5090 集群与 Railway 协同

1. Tailscale 配置
   - 在 4 台 5090 机器上安装 Tailscale
   - 加入同一个 Tailscale 网络
   - 获取虚拟 IP（例如 100.x.x.x）

2. edge_box 部署
   - 在 5090 机器上运行 edge_box 容器
   - 连接到 Railway 的 WebSocket 端点
   - 注册设备 DID

3. 协同流程
   - Railway 接收小程序询价
   - Railway 通过 WebSocket 下发指令到 5090
   - 5090 并行处理 50 个商户的 RAG 检索和价格博弈
   - 5090 返回报价给 Railway
   - Railway 通过 SSE 推送给小程序

【第四阶段】微信支付集成

1. 申请微信支付服务商账户
   - 商户号（mch_id）
   - API v3 密钥
   - 商户证书（private_key.pem）

2. 配置分账关系
   - 商家微信账户
   - 数字包工头微信账户

3. 测试支付流程
   - 创建订单
   - 分账给商家
   - 二级分账给数字包工头

【第五阶段】小程序发布

1. 微信开发者工具
   - 导入 mini_program_app
   - 配置 AppID
   - 上传代码

2. 微信审核
   - 提交审核
   - 等待审核通过（通常 1-3 天）

3. 发布上线
   - 审核通过后发布
   - 用户可在微信搜索小程序名称使用
"""

# ═══════════════════════════════════════════════════════════════════════════
# 🚀 快速启动脚本
# ═══════════════════════════════════════════════════════════════════════════

QUICK_START_COMMANDS = """
【本地开发】

# 1. 启动 PostgreSQL
brew services start postgresql  # macOS
# 或 Windows: 使用 PostgreSQL 安装程序

# 2. 启动 Redis
redis-server

# 3. 初始化数据库
psql -U postgres -d claw < cloud_server/schema.sql

# 4. 启动后端
python -m uvicorn cloud_server.api_server_pro:app --host 127.0.0.1 --port 8765 --reload

# 5. 启动 Streamlit 调试面板
streamlit run streamlit_debug_panel.py

# 6. 微信开发者工具
# - 导入 mini_program_app
# - 清缓存 + 重新编译
# - 在模拟器中测试

【Railway 部署】

# 1. 推送代码
git add .
git commit -m "Production deployment"
git push origin main

# 2. 查看部署日志
# 登录 Railway Dashboard → Deployments → 查看日志

# 3. 验证部署
curl https://your-railway-app.up.railway.app/health

【5090 集群启动】

# 1. 在每台 5090 机器上
docker run -d \\
  -e RAILWAY_URL=https://your-railway-app.up.railway.app \\
  -e DEVICE_SN=box-001 \\
  -e TAILSCALE_IP=100.x.x.x \\
  project-claw:edge-box

# 2. 验证连接
curl http://100.x.x.x:8765/health
"""

# ═══════════════════════════════════════════════════════════════════════════
# 💰 商业模式数学
# ═══════════════════════════════════════════════════════════════════════════

BUSINESS_MODEL = """
【用户支付 20 元的分配】

用户支付: 20.00 元
├─ 商家收到: 19.80 元 (99%)
│  └─ 数字包工头分润: 0.12 元 (0.6% of 20)
│  └─ 商家保留: 19.68 元
└─ 平台保留: 0.20 元 (1% 路由费)
   ├─ 数字包工头分润: 0.12 元 (60% of 0.20)
   └─ 平台保留: 0.08 元 (40% of 0.20)

【日均财务预测】(基于 2000 笔成交)

日均成交笔数: 2,000
平均客单价: 30 元
日均 GMV: 60,000 元

平台收入:
├─ 1% 路由费: 600 元
├─ 数字包工头分润: 360 元 (60% of 600)
└─ 平台毛利: 240 元 (40% of 600)

月度财务:
├─ 月均 GMV: 1,800,000 元
├─ 月均平台收入: 18,000 元
└─ 月均平台毛利: 7,200 元

【融资故事】

"虽然日订单只有 2000 笔，但我们的核心是 A2A 暗网博弈。
每 1 个消费者的询价，会同时唤醒周边 50 家店的 Agent 参与竞标。
2000 笔成交，意味着后台每天发生着 10 万次的大模型检索与多轮谈判！

这就是为什么我花了 10 万块钱买了 4 张 RTX 5090。
如果我们把这 10 万次谈判全走大厂云端 API，光 Token 费就能吃光我们所有的 1% 利润！
通过本地 5090 集群硬扛博弈算力，才是我们真正的毛利护城河！"
"""

# ═══════════════════════════════════════════════════════════════════════════
# 📊 核心 API 端点
# ═══════════════════════════════════════════════════════════════════════════

API_ENDPOINTS = """
【C 端（小程序）】

POST /api/v1/auth/client
  请求: { code: "wx_login_code" }
  响应: { client_id, token, expires_in }

POST /api/v1/trade/request
  请求: { request_id, client_id, item_name, demand_text, max_price, ... }
  响应: { request_id, offers: [...], elapsed_ms }

GET /api/v1/trade/request/stream
  SSE 流式报价
  事件: start, offer, end

POST /api/v1/trade/execute
  请求: { trade_id, offer_id, merchant_id, final_price, ... }
  响应: { trade_id, status, wechat_trade_no }

GET /api/v1/merchants/online
  响应: { online_merchants: 50, merchant_ids: [...] }

【B 端（龙虾盒子）】

POST /api/v1/auth/merchant
  请求: { merchant_id, device_sn, signature }
  响应: { merchant_id, token, tailscale_ip }

WebSocket /ws/merchant/{merchant_id}
  接收指令: INTENT_BROADCAST, EXECUTE_TRADE, CANCEL_TRADE
  发送报价: { type: "quote", offer_id, final_price, ... }

【支付】

POST /api/v1/payment/create
  请求: { trade_id, client_openid, final_price, ... }
  响应: { prepay_id, wechat_trade_no }

POST /api/v1/payment/notify
  微信支付回调

POST /api/v1/payment/profit-sharing
  请求: { trade_id, merchant_id, promoter_id, ... }
  响应: { status, profit_sharing_no }

【监控】

GET /health
  响应: { status: "ok", merchants: 50, ts: ... }

GET /api/v1/system/metrics
  响应: { merchants_online, trades_today, gmv_today, ... }
"""

# ═══════════════════════════════════════════════════════════════════════════
# 🔐 安全检查清单
# ═══════════════════════════════════════════════════════════════════════════

SECURITY_CHECKLIST = """
【认证安全】
- [ ] JWT Token 有效期设置为 24 小时
- [ ] 设备 DID 私钥加密存储
- [ ] 微信 OpenID 与 client_id 绑定
- [ ] 防止 token 重放攻击

【金融安全】
- [ ] 所有交易使用幂等键（idempotency_key）
- [ ] 交易状态使用行级排他锁（SELECT FOR UPDATE）
- [ ] 审计哈希不可篡改（SHA256）
- [ ] 分账金额精确到分

【数据安全】
- [ ] PostgreSQL 使用 SSL 连接
- [ ] Redis 使用密码认证
- [ ] 敏感数据加密存储
- [ ] 定期备份数据库

【API 安全】
- [ ] 速率限制（Rate Limiting）
- [ ] 请求签名验证
- [ ] CORS 配置正确
- [ ] SQL 注入防护

【部署安全】
- [ ] 环境变量不提交到 Git
- [ ] 使用 HTTPS/WSS
- [ ] 防火墙配置
- [ ] 定期安全审计
"""

print(DEPLOYMENT_CHECKLIST)
print(QUICK_START_COMMANDS)
print(BUSINESS_MODEL)
print(API_ENDPOINTS)
print(SECURITY_CHECKLIST)
