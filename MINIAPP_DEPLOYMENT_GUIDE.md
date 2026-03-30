# Project Claw MiniApp 双轨部署指南

## 🎯 目标
- **本地调试**: Streamlit 面板 + 本地 signaling_hub
- **生产环境**: Railway 自动部署 + 公网访问

---

## 📋 快速开始

### 方案 A：本地调试（推荐开发时使用）

#### 步骤 1：启动后端
```bash
# Windows
START_MINIAPP_LOCAL.bat

# macOS / Linux
uvicorn cloud_server.signaling_hub:app --host 0.0.0.0 --port 8765 --reload
```

#### 步骤 2：打开 Streamlit 调试面板
```bash
streamlit run streamlit_debug_panel.py
```
访问: http://localhost:8501

#### 步骤 3：配置微信开发者工具
1. 导入项目: `d:\桌面\Project Claw\mini_program_app`
2. 详情 → 本地设置 → 勾选 **"不校验合法域名"**
3. 清缓存 + 重新编译
4. 模拟器应该能看到首页表单

---

### 方案 B：Railway 生产部署（自动）

#### 步骤 1：确认部署配置已更新
检查以下文件是否已改为 `signaling_hub`:

```bash
# Procfile
web: uvicorn cloud_server.signaling_hub:app --host 0.0.0.0 --port $PORT --workers 1 --log-level info

# railway.toml
startCommand = "uvicorn cloud_server.signaling_hub:app --host 0.0.0.0 --port 8765 --workers 1"

# Dockerfile
CMD ["uvicorn", "cloud_server.signaling_hub:app", "--host", "0.0.0.0", "--port", "8765"]
```

#### 步骤 2：推送到 GitHub
```bash
git add .
git commit -m "Switch to signaling_hub for miniapp"
git push origin main
```

#### 步骤 3：Railway 自动部署
- Railway 会自动检测 Procfile 变更
- 部署时间: 2-5 分钟
- 查看部署日志: Railway Dashboard → Deployments

#### 步骤 4：验证部署成功
```bash
# 检查健康状态
curl https://project-claw-production.up.railway.app/health

# 应该返回:
# {"status": "ok", "merchants": N, "merchant_ids": [...], "ts": ...}
```

#### 步骤 5：小程序配置（生产）
1. 微信开发者工具
2. 详情 → 本地设置 → **取消勾选** "不校验合法域名"
3. 清缓存 + 重新编译
4. 模拟器应该能看到首页表单

---

## 🔄 环境切换

### 本地 → Railway
```bash
# 1. 确认 mini_program_app/utils/config.js 是生产地址
const BASE_URL = 'https://project-claw-production.up.railway.app';

# 2. 推送代码
git push

# 3. 等待 Railway 部署完成
```

### Railway → 本地
```bash
# 1. 运行本地启动脚本
START_MINIAPP_LOCAL.bat

# 脚本会自动:
# - 切换 config.js 为本地地址
# - 启动 signaling_hub
# - 退出时恢复原配置
```

---

## 🧪 测试清单

### 本地调试验证
- [ ] `START_MINIAPP_LOCAL.bat` 启动无错误
- [ ] Streamlit 面板能访问 http://localhost:8501
- [ ] 面板中 `/health` 检查返回 200
- [ ] 面板中 `/api/v1/merchants/online` 返回商家数
- [ ] 微信开发者工具能看到首页表单
- [ ] 首页能显示"服务正常"和在线商家数
- [ ] 点击"立即询价"能成功提交

### Railway 生产验证
- [ ] Railway Dashboard 显示部署成功
- [ ] `curl https://project-claw-production.up.railway.app/health` 返回 200
- [ ] 小程序配置为生产地址
- [ ] 微信开发者工具能看到首页表单
- [ ] 首页能显示"服务正常"和在线商家数
- [ ] 点击"立即询价"能成功提交

---

## 📊 Streamlit 调试面板功能

### 🏥 健康检查
- 检查 `/health` 端点
- 检查在线商家数

### 📊 系统状态
- 实时显示服务状态
- 在线商家数
- 当前时间戳
- 环境标识

### 🧪 API 测试
- 测试 `/health`
- 测试 `/api/v1/merchants/online`
- 测试 `/api/v1/auth/client` (POST)

### 📋 配置管理
- 显示当前配置
- 快速启动指南

---

## 🚨 常见问题

### Q: 本地调试时 404 错误
**A:** 检查:
1. `START_MINIAPP_LOCAL.bat` 是否正在运行
2. 微信开发者工具是否勾选"不校验合法域名"
3. 小程序配置是否为 `http://127.0.0.1:8765`

### Q: Railway 部署后仍然 404
**A:** 检查:
1. Procfile / railway.toml 是否已推送
2. Railway Dashboard 部署是否完成
3. 小程序配置是否为生产地址
4. 是否取消勾选"不校验合法域名"

### Q: 如何查看 Railway 部署日志
**A:** 
1. 登录 Railway Dashboard
2. 选择项目 → Deployments
3. 点击最新部署查看日志

### Q: 小程序能被别人使用吗
**A:** 是的，只要:
1. 使用生产地址 (Railway)
2. 取消勾选"不校验合法域名"
3. 提交微信审核并发布
4. 别人可以在微信搜索小程序名称使用

---

## 📞 支持

- 本地调试问题: 检查 Streamlit 面板
- Railway 部署问题: 查看 Railway Dashboard 日志
- 小程序问题: 检查微信开发者工具 Console

---

**Project Claw v14.3** | 极客风范完善版 | 🦞 智能询价系统
