# 🎯 Project Claw DeepSeek API 配置完整指南

## ✅ 你的 DeepSeek API Key 已配置

```
API Key: sk-4aab42a0cace4e9a8c9bb31faa8c8f01
状态: ✅ 已配置在 .env 文件中
```

---

## 📋 当前配置

### .env 文件中的 DeepSeek 配置
```
DEEPSEEK_API_KEY=sk-4aab42a0cace4e9a8c9bb31faa8c8f01
DEEPSEEK_API_URL=https://api.deepseek.com/chat/completions
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_TIMEOUT=15
DEEPSEEK_MAX_TOKENS=200
DEEPSEEK_TEMPERATURE=0.7
DEEPSEEK_MAX_RETRIES=3
```

---

## 🚀 验证配置

### 步骤 1：激活虚拟环境
```powershell
cd "d:\桌面\Project Claw"
venv\Scripts\activate.bat
```

### 步骤 2：运行验证脚本
```powershell
python verify_deepseek_config.py
```

**脚本会验证：**
- ✅ .env 文件存在
- ✅ DeepSeek API Key 已设置
- ✅ API 连接正常
- ✅ 项目依赖已安装

---

## 🔧 配置说明

### DEEPSEEK_API_KEY
```
你的 API Key：sk-4aab42a0cace4e9a8c9bb31faa8c8f01
用途：调用 DeepSeek API 进行 LLM 推理
```

### DEEPSEEK_API_URL
```
API 端点：https://api.deepseek.com/chat/completions
用途：发送聊天请求到 DeepSeek 服务器
```

### DEEPSEEK_MODEL
```
模型名称：deepseek-chat
用途：指定使用的 DeepSeek 模型
```

### DEEPSEEK_TIMEOUT
```
超时时间：15 秒
用途：API 请求的最大等待时间
```

### DEEPSEEK_MAX_TOKENS
```
最大令牌数：200
用途：限制 API 响应的长度
```

### DEEPSEEK_TEMPERATURE
```
温度参数：0.7
用途：控制响应的随机性（0-1，越低越确定）
```

### DEEPSEEK_MAX_RETRIES
```
最大重试次数：3
用途：API 请求失败时的重试次数
```

---

## 💡 使用场景

### 1. 谈判引擎
```python
# 使用 DeepSeek 进行动态谈判
response = await llm_client.chat(
    model="deepseek-chat",
    messages=[
        {"role": "user", "content": "帮我砍价..."}
    ]
)
```

### 2. 价格分析
```python
# 使用 DeepSeek 分析价格合理性
response = await llm_client.chat(
    model="deepseek-chat",
    messages=[
        {"role": "user", "content": "这个价格合理吗？"}
    ]
)
```

### 3. 对话生成
```python
# 使用 DeepSeek 生成自然对话
response = await llm_client.chat(
    model="deepseek-chat",
    messages=[
        {"role": "user", "content": "生成一个砍价对话..."}
    ]
)
```

---

## 🔐 安全建议

### ✅ 已做的事
- ✅ API Key 存储在 .env 文件中
- ✅ .env 文件已添加到 .gitignore
- ✅ API Key 不会被提交到 Git

### ⚠️ 需要注意
- ⚠️ 不要在代码中硬编码 API Key
- ⚠️ 不要将 .env 文件提交到 Git
- ⚠️ 定期检查 API 使用情况
- ⚠️ 如果 API Key 泄露，立即更换

---

## 📊 API 使用限制

### DeepSeek API 配额
```
根据你的账户类型而定
建议定期检查使用情况
```

### 项目中的限制
```
DEEPSEEK_MAX_TOKENS=200      # 每次请求最多 200 个令牌
DEEPSEEK_TIMEOUT=15          # 每次请求最多等待 15 秒
DEEPSEEK_MAX_RETRIES=3       # 失败最多重试 3 次
```

---

## 🧪 测试 API

### 方式 1：运行验证脚本
```powershell
python verify_deepseek_config.py
```

### 方式 2：手动测试
```python
import httpx
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("DEEPSEEK_API_KEY")
api_url = os.getenv("DEEPSEEK_API_URL")

client = httpx.Client()
response = client.post(
    api_url,
    json={
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": "你好"}],
        "max_tokens": 50
    },
    headers={"Authorization": f"Bearer {api_key}"}
)

print(response.json())
```

---

## 🚀 现在可以做什么

### 1. 验证配置
```powershell
python verify_deepseek_config.py
```

### 2. 启动后端服务
```powershell
python -m uvicorn cloud_server.api_server_pro:app --host 0.0.0.0 --port 8765 --reload
```

### 3. 启动融资路演大屏
```powershell
streamlit run cloud_server/god_dashboard.py --server.port 8501
```

### 4. 开始开发
```
现在你可以使用 DeepSeek API 进行：
- 谈判引擎开发
- 价格分析
- 对话生成
- 其他 LLM 相关功能
```

---

## 📚 相关文档

```
验证脚本：verify_deepseek_config.py
快速启动：QUICK_START_GUIDE.md
Redis 配置：REDIS_MANUAL_SETUP.md
```

---

## ✅ 配置检查清单

- [x] DeepSeek API Key 已获取
- [x] API Key 已添加到 .env 文件
- [x] API 端点已配置
- [x] 模型已配置
- [x] 超时和重试已配置
- [ ] 运行验证脚本
- [ ] 启动后端服务
- [ ] 启动融资路演大屏
- [ ] 开始开发

---

## 🎉 你已准备好！

**你现在拥有：**
- ✅ 完整的 Project Claw 项目
- ✅ 配置好的 DeepSeek API
- ✅ 虚拟环境和依赖
- ✅ 初始化的数据库
- ✅ 启动脚本和指南

**下一步：**
1. 运行验证脚本
2. 启动所有服务
3. 开始开发

---

**祝你使用愉快！** 🚀
