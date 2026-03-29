# Project Claw 一键启动脚本使用指南

## 🚀 快速启动

### 方式 1：启动所有服务（推荐）
```powershell
cd "d:\桌面\Project Claw"
.\start_all.ps1
```

然后选择菜单选项 `1` 启动所有服务

---

### 方式 2：使用命令行参数

#### 启动所有服务
```powershell
.\start_all.ps1 -All
```

#### 仅启动后端 API
```powershell
.\start_all.ps1 -Backend
```

#### 仅启动融资路演大屏
```powershell
.\start_all.ps1 -Dashboard
```

#### 仅启动 Redis
```powershell
.\start_all.ps1 -Redis
```

#### 仅启动小程序
```powershell
.\start_all.ps1 -MiniProgram
```

---

## 📋 菜单选项

运行 `.\start_all.ps1` 后，会显示以下菜单：

```
选择启动模式：
  1. 🚀 启动所有服务（推荐）
  2. 🔧 仅启动后端 API
  3. 📊 仅启动融资路演大屏
  4. 💾 仅启动 Redis
  5. 📱 仅启动小程序
  6. 🔄 启动后端 + 大屏 + Redis
  0. ❌ 退出
```

输入对应的数字即可启动相应的服务

---

## 📍 启动后可访问的地址

```
后端 API：http://localhost:8765
API 文档：http://localhost:8765/docs
融资路演大屏：http://localhost:8501
Redis：localhost:6379
小程序：微信开发者工具模拟器
```

---

## 🎯 完整的启动命令

### 后端 API
```powershell
python -m uvicorn cloud_server.api_server_pro:app --host 0.0.0.0 --port 8765 --reload
```

### 融资路演大屏
```powershell
streamlit run cloud_server/god_dashboard.py --server.port 8501
```

### Redis
```powershell
docker run -d -p 6379:6379 redis:latest
```

### 小程序
```
微信开发者工具 → 打开项目 → 编译 → 预览
```

---

## ✅ 启动检查清单

启动后应该看到：
- [ ] 后端 API 运行在 http://localhost:8765
- [ ] 融资路演大屏运行在 http://localhost:8501
- [ ] Redis 运行在 localhost:6379
- [ ] 小程序在微信开发者工具中预览
- [ ] 没有错误信息

---

## 🛑 停止所有服务

### 方式 1：关闭终端窗口
```
关闭所有启动的命令行窗口
```

### 方式 2：使用 PowerShell 命令
```powershell
# 停止所有 Python 进程
Stop-Process -Name python -Force

# 停止所有 streamlit 进程
Stop-Process -Name streamlit -Force

# 停止 Redis 容器
docker stop $(docker ps -q --filter ancestor=redis:latest)
```

---

## 💡 常见问题

### Q1：脚本无法执行
```
错误：无法加载文件 start_all.ps1，因为在此系统上禁止执行脚本

解决：
1. 以管理员身份打开 PowerShell
2. 运行：Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
3. 输入 Y 确认
4. 重新运行脚本
```

### Q2：Docker 未安装
```
错误：Docker 未安装或未运行

解决：
1. 下载 Docker Desktop：https://www.docker.com/products/docker-desktop
2. 安装并启动 Docker Desktop
3. 重新运行脚本
```

### Q3：端口被占用
```
错误：Address already in use

解决：
1. 检查是否已有服务在运行
2. 修改端口号
3. 或关闭占用端口的程序
```

---

## 🎉 现在就启动吧！

```powershell
cd "d:\桌面\Project Claw"
.\start_all.ps1
```

选择菜单选项 `1` 启动所有服务！
