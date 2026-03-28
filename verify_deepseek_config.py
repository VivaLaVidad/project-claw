# 验证 DeepSeek API 配置脚本

import os
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

print("=" * 60)
print("🔍 Project Claw DeepSeek API 配置验证")
print("=" * 60)
print()

# 1. 检查 .env 文件
print("[1/4] 检查 .env 文件...")
env_file = Path(".env")
if env_file.exists():
    print("✓ .env 文件存在")
else:
    print("✗ .env 文件不存在")
    sys.exit(1)
print()

# 2. 加载环境变量
print("[2/4] 加载环境变量...")
from dotenv import load_dotenv
load_dotenv()

deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")
deepseek_api_url = os.getenv("DEEPSEEK_API_URL")
deepseek_model = os.getenv("DEEPSEEK_MODEL")

if deepseek_api_key:
    # 隐藏 API Key 的大部分内容
    masked_key = deepseek_api_key[:10] + "..." + deepseek_api_key[-10:]
    print(f"✓ DEEPSEEK_API_KEY: {masked_key}")
else:
    print("✗ DEEPSEEK_API_KEY 未设置")
    sys.exit(1)

if deepseek_api_url:
    print(f"✓ DEEPSEEK_API_URL: {deepseek_api_url}")
else:
    print("✗ DEEPSEEK_API_URL 未设置")
    sys.exit(1)

if deepseek_model:
    print(f"✓ DEEPSEEK_MODEL: {deepseek_model}")
else:
    print("✗ DEEPSEEK_MODEL 未设置")
    sys.exit(1)

print()

# 3. 测试 API 连接
print("[3/4] 测试 DeepSeek API 连接...")
try:
    import httpx
    
    client = httpx.Client(timeout=10.0)
    
    response = client.post(
        deepseek_api_url,
        json={
            "model": deepseek_model,
            "messages": [
                {
                    "role": "user",
                    "content": "你好，请简短回复"
                }
            ],
            "max_tokens": 50,
            "temperature": 0.7
        },
        headers={
            "Authorization": f"Bearer {deepseek_api_key}",
            "Content-Type": "application/json"
        }
    )
    
    if response.status_code == 200:
        result = response.json()
        message = result["choices"][0]["message"]["content"]
        print(f"✓ API 连接成功")
        print(f"✓ 响应: {message[:50]}...")
    else:
        print(f"✗ API 返回错误: {response.status_code}")
        print(f"✗ 错误信息: {response.text}")
        sys.exit(1)
    
    client.close()

except Exception as e:
    print(f"✗ API 连接失败: {e}")
    sys.exit(1)

print()

# 4. 验证项目依赖
print("[4/4] 验证项目依赖...")
try:
    import fastapi
    import streamlit
    import httpx
    print("✓ 所有核心依赖已安装")
except ImportError as e:
    print(f"✗ 缺少依赖: {e}")
    sys.exit(1)

print()
print("=" * 60)
print("✅ 所有配置验证通过！")
print("=" * 60)
print()
print("📍 你现在可以：")
print("  1. 运行后端服务")
print("  2. 启动融资路演大屏")
print("  3. 开始开发项目")
print()
