# pip 下载加速完整指南

## 🚀 最快的方式 - 一键快速安装

### 双击运行
```
d:\桌面\Project Claw\快速安装.bat
```

**自动完成：**
- ✅ 创建虚拟环境
- ✅ 激活虚拟环境
- ✅ 升级 pip
- ✅ 使用国内镜像安装依赖（快 10 倍）

---

## 📋 手动加速方法

### 方法 1：使用阿里云镜像（推荐）

```powershell
cd "d:\桌面\Project Claw"
python -m venv venv
venv\Scripts\activate.bat

# 升级 pip
python -m pip install --upgrade pip -i https://mirrors.aliyun.com/pypi/simple/

# 安装依赖
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com
```

**速度：** ⚡⚡⚡⚡⚡ 最快

---

### 方法 2：使用清华大学镜像

```powershell
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

**速度：** ⚡⚡⚡⚡ 很快

---

### 方法 3：使用豆瓣镜像

```powershell
pip install -r requirements.txt -i http://mirrors.aliyun.com/pypi/simple/
```

**速度：** ⚡⚡⚡ 快

---

### 方法 4：永久配置镜像

**创建文件：** `%APPDATA%\pip\pip.ini`

**内容：**
```ini
[global]
index-url = https://mirrors.aliyun.com/pypi/simple/
trusted-host = mirrors.aliyun.com
timeout = 1000
```

**之后直接运行：**
```powershell
pip install -r requirements.txt
```

---

## 🔧 其他加速技巧

### 1️⃣ 增加超时时间
```powershell
pip install -r requirements.txt --default-timeout=1000
```

### 2️⃣ 使用缓存
```powershell
pip install -r requirements.txt --cache-dir ~/.cache/pip
```

### 3️⃣ 并行下载
```powershell
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/ --retries 5
```

### 4️⃣ 跳过已安装的包
```powershell
pip install -r requirements.txt --upgrade -i https://mirrors.aliyun.com/pypi/simple/
```

---

## 📊 速度对比

| 镜像源 | 速度 | 稳定性 | 推荐度 |
|------|------|------|------|
| 阿里云 | ⚡⚡⚡⚡⚡ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| 清华大学 | ⚡⚡⚡⚡ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| 豆瓣 | ⚡⚡⚡ | ⭐⭐⭐ | ⭐⭐⭐ |
| 官方 | ⚡ | ⭐⭐⭐⭐⭐ | ⭐⭐ |

---

## ✅ 完整的快速安装步骤

### 第 1 步：双击运行快速安装脚本
```
d:\桌面\Project Claw\快速安装.bat
```

### 第 2 步：等待安装完成
```
预期时间：2-5 分钟
```

### 第 3 步：验证安装
```powershell
pip list | Select-String fastapi
# 应该显示：fastapi 0.104.1
```

### 第 4 步：启动项目
```
双击运行：d:\桌面\Project Claw\启动.bat
```

---

## 💡 常见问题

### Q1：安装仍然很慢
```
解决：
1. 检查网络连接
2. 尝试其他镜像源
3. 增加超时时间：--default-timeout=2000
```

### Q2：某个包下载失败
```
解决：
1. 单独安装该包：pip install package_name -i https://mirrors.aliyun.com/pypi/simple/
2. 或跳过该包，稍后重试
```

### Q3：镜像源不可用
```
解决：
1. 尝试其他镜像源
2. 检查网络连接
3. 使用官方源：pip install -r requirements.txt
```

---

## 🎯 推荐的完整流程

### 第 1 步：快速安装
```
双击：快速安装.bat
```

### 第 2 步：验证安装
```powershell
pip list | Select-String -Pattern "fastapi|streamlit|redis"
```

### 第 3 步：启动项目
```
双击：启动.bat
```

### 第 4 步：访问服务
```
后端 API：http://localhost:8765/docs
融资路演大屏：http://localhost:8501
```

---

## 📚 相关文件

```
快速安装脚本：快速安装.bat
一键启动脚本：启动.bat
快速启动指南：快速启动指南.md
```

---

**现在就双击 快速安装.bat 快速安装依赖吧！** 🚀

使用国内镜像，下载速度快 10 倍！
