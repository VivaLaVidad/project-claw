"""
Project Claw v14.3 - PostgreSQL Schema
工业级数据库设计：支撑 1% 路由费 + A2A 博弈 + 分润系统
"""

# 执行这个 SQL 脚本到你的 PostgreSQL 数据库

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ═══════════════════════════════════════════════════════════════════════════
-- 👥 用户表 (Clients) - C端消费者
-- ═══════════════════════════════════════════════════════════════════════════
CREATE TABLE clients (
    client_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    wechat_openid VARCHAR(128) UNIQUE NOT NULL,
    wechat_unionid VARCHAR(128),
    nickname VARCHAR(64),
    avatar_url TEXT,
    
    -- 🔥 核心资产：1024维用户画像向量
    persona_vector FLOAT8[] CHECK (array_length(persona_vector, 1) = 1024),
    
    -- 风控分（0-100，越高越可信）
    risk_score INT DEFAULT 50 CHECK (risk_score >= 0 AND risk_score <= 100),
    
    -- 账户状态
    status VARCHAR(32) DEFAULT 'active' CHECK (status IN ('active', 'frozen', 'deleted')),
    
    -- 统计字段
    total_trades INT DEFAULT 0,
    total_spent DECIMAL(12, 2) DEFAULT 0,
    avg_satisfaction FLOAT DEFAULT 0,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_wechat_openid (wechat_openid),
    INDEX idx_risk_score (risk_score),
    INDEX idx_created_at (created_at)
);

-- ═══════════════════════════════════════════════════════════════════════════
-- 🏪 商家表 (Merchants) - B端龙虾盒子
-- ═══════════════════════════════════════════════════════════════════════════
CREATE TABLE merchants (
    merchant_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- 🔥 裂变引擎：绑定的"数字包工头"ID
    promoter_id VARCHAR(64),
    
    merchant_name VARCHAR(128) NOT NULL,
    merchant_phone VARCHAR(20),
    
    -- 地理位置
    latitude FLOAT NOT NULL,
    longitude FLOAT NOT NULL,
    address TEXT,
    
    -- 盒子状态
    box_status VARCHAR(32) DEFAULT 'offline' CHECK (box_status IN ('online', 'offline', 'frozen', 'maintenance')),
    
    -- 🔥 预充值的龙虾币余额（用于支付 API 调用费）
    routing_token_balance DECIMAL(12, 2) DEFAULT 0,
    
    -- 🔥 加密暗网虚拟 IP（Tailscale）
    tailscale_ip VARCHAR(64),
    
    -- 设备级认证密钥（DID）
    device_did_public_key TEXT,
    device_did_private_key_encrypted TEXT,  -- 加密存储
    
    -- 商家画像向量（用于 A2A 匹配）
    merchant_vector FLOAT8[] CHECK (array_length(merchant_vector, 1) = 1024),
    
    -- 统计字段
    total_offers INT DEFAULT 0,
    total_accepted INT DEFAULT 0,
    avg_response_time_ms INT DEFAULT 0,
    
    -- 合规字段
    business_license_url TEXT,
    verified_at TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_promoter_id (promoter_id),
    INDEX idx_box_status (box_status),
    INDEX idx_location (latitude, longitude),
    INDEX idx_tailscale_ip (tailscale_ip)
);

-- ═══════════════════════════════════════════════════════════════════════════
-- 🧾 交易流水表 (TradeLedger) - 金融级账本
-- ═══════════════════════════════════════════════════════════════════════════
CREATE TABLE trade_ledger (
    trade_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- 幂等性保证
    idempotency_key VARCHAR(256) UNIQUE NOT NULL,
    
    -- 全链路追踪
    trace_id VARCHAR(256),
    
    -- 交易双方
    client_id UUID NOT NULL REFERENCES clients(client_id),
    merchant_id UUID NOT NULL REFERENCES merchants(merchant_id),
    
    -- 价格信息
    original_price DECIMAL(10, 2) NOT NULL,
    final_price DECIMAL(10, 2) NOT NULL,
    
    -- 🔥 状态机：PENDING ➔ NEGOTIATING ➔ ACCEPTED ➔ VISUAL_ACK ➔ SETTLED
    status VARCHAR(32) DEFAULT 'pending' CHECK (status IN (
        'pending', 'negotiating', 'accepted', 'visual_ack', 'settled', 'failed', 'cancelled'
    )),
    
    -- 🔥 合规防线：基于 SHA256 的不可篡改交易快照哈希
    audit_hash VARCHAR(256),
    
    -- 分润信息
    platform_fee DECIMAL(10, 2),  -- 1% 路由费
    promoter_commission DECIMAL(10, 2),  -- 数字包工头分润
    
    -- 支付信息
    wechat_trade_no VARCHAR(256),  -- 微信支付订单号
    payment_status VARCHAR(32) DEFAULT 'unpaid',
    
    -- 时间戳
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    negotiation_start_at TIMESTAMP,
    accepted_at TIMESTAMP,
    settled_at TIMESTAMP,
    
    INDEX idx_client_id (client_id),
    INDEX idx_merchant_id (merchant_id),
    INDEX idx_status (status),
    INDEX idx_trace_id (trace_id),
    INDEX idx_created_at (created_at)
);

-- ═══════════════════════════════════════════════════════════════════════════
-- 💬 A2A 谈判记录表 (NegotiationLog)
-- ═══════════════════════════════════════════════════════════════════════════
CREATE TABLE negotiation_log (
    negotiation_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    trade_id UUID NOT NULL REFERENCES trade_ledger(trade_id),
    
    -- 谈判轮次
    round INT NOT NULL,
    
    -- 发言方
    speaker_role VARCHAR(32) CHECK (speaker_role IN ('client', 'merchant', 'agent')),
    
    -- 内容
    message TEXT NOT NULL,
    
    -- 价格建议
    suggested_price DECIMAL(10, 2),
    
    -- 模型推理信息
    model_name VARCHAR(64),  -- 使用的大模型
    inference_time_ms INT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_trade_id (trade_id),
    INDEX idx_round (round)
);

-- ═══════════════════════════════════════════════════════════════════════════
-- 💰 分润表 (CommissionLedger) - 数字包工头分账
-- ═══════════════════════════════════════════════════════════════════════════
CREATE TABLE commission_ledger (
    commission_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    trade_id UUID NOT NULL REFERENCES trade_ledger(trade_id),
    promoter_id VARCHAR(64) NOT NULL,
    
    -- 分润金额
    commission_amount DECIMAL(10, 2) NOT NULL,
    
    -- 分润状态
    status VARCHAR(32) DEFAULT 'pending' CHECK (status IN ('pending', 'settled', 'failed')),
    
    -- 微信分账单号
    wechat_profit_sharing_no VARCHAR(256),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    settled_at TIMESTAMP,
    
    INDEX idx_promoter_id (promoter_id),
    INDEX idx_status (status)
);

-- ═══════════════════════════════════════════════════════════════════════════
-- 🔐 设备认证表 (DeviceDID) - 龙虾盒子设备级认证
-- ═══════════════════════════════════════════════════════════════════════════
CREATE TABLE device_did (
    device_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    merchant_id UUID NOT NULL REFERENCES merchants(merchant_id),
    
    -- 设备标识
    device_sn VARCHAR(128) UNIQUE NOT NULL,
    device_model VARCHAR(64),
    
    -- 非对称密钥对
    public_key TEXT NOT NULL,
    private_key_encrypted TEXT NOT NULL,
    
    -- 认证状态
    status VARCHAR(32) DEFAULT 'active',
    
    last_heartbeat_at TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_merchant_id (merchant_id),
    INDEX idx_device_sn (device_sn)
);

-- ═══════════════════════════════════════════════════════════════════════════
-- 📊 实时状态表 (RealtimeStatus) - Redis 备份
-- ═══════════════════════════════════════════════════════════════════════════
CREATE TABLE realtime_status (
    entity_id VARCHAR(256) PRIMARY KEY,
    entity_type VARCHAR(32),  -- 'client' / 'merchant'
    
    -- 状态 JSON
    status_json JSONB,
    
    -- TTL（秒）
    ttl_seconds INT DEFAULT 300,
    
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_entity_type (entity_type),
    INDEX idx_updated_at (updated_at)
);

-- ═══════════════════════════════════════════════════════════════════════════
-- 创建索引和约束
-- ═══════════════════════════════════════════════════════════════════════════

-- 行级排他锁示例（在应用层使用）
-- SELECT * FROM trade_ledger WHERE trade_id = $1 FOR UPDATE;

-- 创建视图：日结算报表
CREATE VIEW daily_settlement AS
SELECT 
    DATE(created_at) as settlement_date,
    COUNT(*) as total_trades,
    SUM(final_price) as total_gmv,
    SUM(platform_fee) as platform_revenue,
    SUM(promoter_commission) as promoter_payout,
    AVG(final_price - original_price) as avg_discount
FROM trade_ledger
WHERE status = 'settled'
GROUP BY DATE(created_at);

-- 创建视图：商家排行
CREATE VIEW merchant_leaderboard AS
SELECT 
    m.merchant_id,
    m.merchant_name,
    COUNT(tl.trade_id) as total_accepted,
    AVG(tl.final_price) as avg_final_price,
    SUM(tl.final_price) as total_gmv,
    m.avg_response_time_ms
FROM merchants m
LEFT JOIN trade_ledger tl ON m.merchant_id = tl.merchant_id AND tl.status = 'settled'
GROUP BY m.merchant_id, m.merchant_name, m.avg_response_time_ms
ORDER BY total_gmv DESC;
