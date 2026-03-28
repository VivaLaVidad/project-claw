# Project Claw 缺失清单和行动步骤

## 📋 当前状态

### ✅ 已有的
```
✓ Python 3.12.7
✓ Git 2.53.0
✓ Node.js v24.14.0
✓ npm 11.9.0
✓ SQLite 3.50.4
✓ 项目代码
✓ requirements.txt
✓ .env 配置文件
✓ 启动脚本
✓ 配置脚本
```

### ❌ 缺失的（需要立即完成）

```
1. ❌ 虚拟环境 (venv)
2. ❌ Python 依赖包（65 个）
3. ❌ 审计数据库 (audit.db)
4. ❌ 死信队列数据库 (dlq.db)
5. ❌ Redis 服务器
```

---

## 🎯 具体行动步骤

### 步骤 1：打开 PowerShell（以管理员身份）

**怎么做：**
1. 按 `Win + X`
2. 选择 "Windows PowerShell (管理员)"
3. 点击 "是" 确认

---

### 步骤 2：进入项目目录

**命令：**
```powershell
cd d:\桌面\Project\ Claw
```

**验证：**
```powershell
# 应该看到项目文件
ls
```

---

### 步骤 3：允许执行脚本

**命令：**
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

**提示：**
- 会询问是否确认，输入 `Y` 然后按 Enter

---

### 步骤 4：运行完整配置脚本

**命令：**
```powershell
.\complete_setup.ps1
```

**这个脚本会自动完成：**
```
[1/8] 检查 Python ✓
[2/8] 创建虚拟环境 ✓
[3/8] 激活虚拟环境 ✓
[4/8] 安装项目依赖 ✓
[5/8] 初始化数据库 ✓
[6/8] 安装 Redis ✓
[7/8] 验证安装 ✓
[8/8] 启动所有服务 ✓
```

**预计时间：** 5-10 分钟

---

## 📊 脚本执行后会创建的文件

```
venv/                    # 虚拟环境目录
audit.db                 # 审计数据库
dlq.db                   # 死信队列数据库
```

---

## 🚀 脚本启动的服务

```
✅ Redis 服务器
   地址：localhost:6379
   
✅ 后端 API 服务
   地址：http://localhost:8765
   文档：http://localhost:8765/docs
   
✅ 融资路演大屏
   地址：http://localhost:8501
   
✅ 浏览器
   自动打开上述地址
```

---

## ⚠️ 如果脚本失败

### 问题 1：执行策略错误
```powershell
# 错误信息：cannot be loaded because running scripts is disabled

# 解决方案：
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### 问题 2：Python 不在 PATH
```powershell
# 错误信息：python: The term 'python' is not recognized

# 解决方案：
# 重新安装 Python，勾选 "Add Python to PATH"
# 或手动添加 Python 到 PATH
```

### 问题 3：Chocolatey 安装失败
```powershell
# 脚本会自动尝试安装 Chocolatey
# 如果失败，手动安装：
Set-ExecutionPolicy Bypass -Scope Process -Force
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
```

### 问题 4：Redis 安装失败
```powershell
# 手动安装 Redis：
choco install redis-64 -y

# 或从这里下载：
# https://github.com/microsoftarchive/redis/releases
```

---

## ✅ 验证配置是否成功

### 检查虚拟环境
```powershell
# 应该看到 (venv) 前缀
# 如果没有，运行：
venv\Scripts\activate.bat
```

### 检查依赖
```powershell
pip list
# 应该看到 65 个包
```

### 检查数据库
```powershell
# 应该看到两个文件
ls *.db
```

### 检查 Redis
```powershell
redis-cli ping
# 应该返回 PONG
```

### 检查后端服务
```powershell
curl http://localhost:8765/docs
# 应该返回 Swagger UI 页面
```

---

## 🎯 完整的行动清单

- [ ] 打开 PowerShell（管理员）
- [ ] 进入项目目录：`cd d:\桌面\Project\ Claw`
- [ ] 允许执行脚本：`Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`
- [ ] 运行配置脚本：`.\complete_setup.ps1`
- [ ] 等待脚本完成（5-10 分钟）
- [ ] 验证所有服务已启动
- [ ] 访问 http://localhost:8765/docs
- [ ] 访问 http://localhost:8501
- [ ] 开始开发

---

## 📍 启动后的服务地址

```
后端 API：http://localhost:8765
API 文档：http://localhost:8765/docs
融资路演大屏：http://localhost:8501
Redis：localhost:6379
```

---

## 🛑 停止服务

```powershell
# 关闭对应的命令行窗口
# 或在 Redis 窗口中按 Ctrl+C
```

---

## 🔄 下次启动项目

```powershell
# 激活虚拟环境
venv\Scripts\activate.bat

# 启动后端服务
python -m uvicorn cloud_server.api_server_pro:app --host 0.0.0.0 --port 8765 --reload

# 在新终端启动大屏
streamlit run cloud_server/god_dashboard.py --server.port 8501

# 在新终端启动 Redis
redis-server
```

---

## 💡 重要提示

```
✨ 脚本是幂等的，可以多次运行
✨ 脚本会自动检测已安装的组件
✨ 脚本会自动跳过已完成的步骤
✨ 脚本会自动处理大部分错误
✨ 如果失败，按照上面的故障排除步骤操作
```

---

## 🎉 总结

**你现在只需要做一件事：**

```powershell
.\complete_setup.ps1
```

**脚本会自动完成所有缺失的配置：**
1. ✅ 创建虚拟环境
2. ✅ 安装 65 个依赖包
3. ✅ 初始化 2 个数据库
4. ✅ 安装 Redis
5. ✅ 启动所有服务
6. ✅ 打开浏览器

**预计时间：5-10 分钟**

---

**现在就去运行脚本吧！** 🚀
