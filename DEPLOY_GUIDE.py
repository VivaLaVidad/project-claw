"""
Project Claw v14.3 - 云端部署指南
不需要 Linux 服务器，推荐使用 Railway 或 Zeabur
"""

# ==================== 方案一：Railway（推荐，$5/月）====================

"""
【Railway 部署步骤】

1. 注册账号
   https://railway.app  （支持 GitHub 登录）

2. 安装 Railway CLI（PowerShell）
   npm install -g @railway/cli
   railway login

3. 初始化并部署
   cd d:/desktop/Project_Claw_v14
   railway init          # 创建新项目
   railway up            # 上传并部署（使用 Dockerfile）

4. 设置环境变量（Railway Dashboard → Variables）
   HUB_JWT_SECRET       = 你自己生成的随机字符串（至少32位）
   HUB_MERCHANT_KEY     = 你设置的商家密钥
   HUB_RATE_LIMIT_PER_MIN = 30
   HUB_DB_PATH          = /data/claw_orders.db
   HUB_AUDIT_LOG        = /data/hub_audit.log

5. 获取域名
   Railway Dashboard → Settings → Networking → Generate Domain
   会得到类似: https://project-claw-hub-production.up.railway.app

6. 更新小程序配置
   编辑: mini_program_app/utils/config.js
   const BASE_URL = 'https://你的域名.up.railway.app';

7. 更新 edge_box/.env
   SIGNALING_URL=wss://你的域名.up.railway.app
"""

# ==================== 方案二：Zeabur（中文，¥20/月起）====================

"""
【Zeabur 部署步骤】

1. 注册账号
   https://zeabur.com  （支持微信登录）

2. 新建项目 → 添加服务 → Git 部署
   - 先把项目推到 GitHub（见下方 Git 步骤）
   - 或选择「Docker 镜像」直接上传

3. 设置环境变量（Zeabur Dashboard → Variables）
   同上 Railway 环境变量

4. 绑定域名
   Zeabur 自动分配 xxx.zeabur.app 域名 + HTTPS

5. 更新 config.js 和 .env 同上
"""

# ==================== Git 推送步骤（两个平台都需要）====================

"""
【首次推送到 GitHub】

在 PowerShell 执行：

  cd d:\桌面\Project_Claw_v14

  git init
  git add .
  git commit -m "feat: Project Claw v14.3 商业版"

  # 在 GitHub.com 新建仓库后：
  git remote add origin https://github.com/你的用户名/project-claw.git
  git push -u origin main

注意：.gitignore 已配置好，.env 和私钥不会被上传
"""

# ==================== 本地测试（cpolar 临时方案）====================

"""
【继续使用 cpolar 临时测试】

1. 启动 Hub
   ./start_all.ps1 -SkipEdge

2. cpolar 保持稳定的步骤（升级到付费版可固定域名）
   - 免费版：每次重启域名会变，需手动更新 config.js
   - 付费版（¥15/月）：固定二级域名，推荐

3. 升级到 Railway 后，只需改 config.js 一行
"""

# ==================== 环境变量生成工具 ====================

import secrets
if __name__ == "__main__":
    print("[自动生成生产环境密钥]")
    print(f"HUB_JWT_SECRET={secrets.token_urlsafe(32)}")
    print(f"HUB_MERCHANT_KEY={secrets.token_urlsafe(16)}")
    print("\n请将以上值复制到 Railway/Zeabur 环境变量中")
