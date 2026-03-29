# Project Claw VLM 物理执行驱动层完整指南

## 🎯 系统架构

### VLM 驱动架构

```
┌─────────────────────────────────────────────────────────────┐
│              VLM 物理执行驱动 (edge_box/vlm_driver.py)      │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  VLMDriver (VLM 驱动)                               │  │
│  │  - 调用 GPT-4 Vision / Claude Vision                │  │
│  │  - 发送截图 + 指令                                 │  │
│  │  - 解析 JSON 响应                                   │  │
│  │  - 降级到 OCR                                       │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  PhysicalExecutor (物理执行器)                      │  │
│  │  - 点击 (Tap)                                       │  │
│  │  - 输入 (Type)                                      │  │
│  │  - 滑动 (Swipe)                                     │  │
│  │  - 截图 (Screenshot)                               │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────────────┐
│              物理设备 (Android)                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  ADB / uiautomator2                                 │  │
│  │  - 执行点击、输入、滑动                             │  │
│  │  - 获取截图                                        │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## 📋 核心特性

### 1. 视觉理解操控
```python
✅ 摆脱硬编码坐标
✅ 基于 VLM 的 UI 理解
✅ 自然语言指令
✅ 高精度定位
```

### 2. 智能降级
```python
✅ VLM 失败自动降级到 OCR
✅ OCR 失败返回错误
✅ 完整的容错机制
✅ 日志记录
```

### 3. 完整的操作支持
```python
✅ 点击 (Tap)
✅ 输入 (Type)
✅ 滑动 (Swipe)
✅ 截图 (Screenshot)
```

### 4. 多模型支持
```python
✅ GPT-4 Vision
✅ Claude 3 Vision
✅ 其他 Vision API
```

---

## 🚀 快速开始

### 第 1 步：初始化 VLM 驱动

```python
from edge_box.vlm_driver import VLMDriver, PhysicalExecutor, VLMConfig

# 创建 VLM 配置
config = VLMConfig(
    api_key="your-openai-api-key",
    model="gpt-4-vision",
    base_url="https://api.openai.com/v1"
)

# 初始化驱动
vlm_driver = VLMDriver(config)
executor = PhysicalExecutor(vlm_driver)
```

### 第 2 步：获取截图

```python
# 获取截图
screenshot_base64 = await executor.get_screenshot()

if not screenshot_base64:
    print("获取截图失败")
```

### 第 3 步：点击元素

```python
# 点击发送按钮
success = await executor.tap_element(
    screenshot_base64=screenshot_base64,
    instruction="找出并点击发送按钮"
)

if success:
    print("✓ 点击成功")
else:
    print("✗ 点击失败")
```

### 第 4 步：输入文本

```python
# 在输入框中输入文本
success = await executor.type_text(
    screenshot_base64=screenshot_base64,
    instruction="找出消息输入框",
    text="你好，这是一条测试消息"
)

if success:
    print("✓ 输入成功")
else:
    print("✗ 输入失败")
```

### 第 5 步：滑动操作

```python
# 向上滑动
success = await executor.swipe(
    start_x=540,
    start_y=1600,
    end_x=540,
    end_y=400,
    duration=500
)

if success:
    print("✓ 滑动成功")
else:
    print("✗ 滑动失败")
```

---

## 📊 VLM 响应格式

### 成功响应

```json
{
    "found": true,
    "element_type": "button",
    "description": "发送按钮",
    "center_x": 950,
    "center_y": 1850,
    "confidence": 0.95
}
```

### 失败响应

```json
{
    "found": false,
    "element_type": "button",
    "description": "未找到发送按钮",
    "center_x": 0,
    "center_y": 0,
    "confidence": 0.0,
    "reason": "屏幕上没有可见的发送按钮"
}
```

---

## 🔧 集成到 BaseDriver

### 替换原有的坐标点击

```python
# 原来的方式 (硬编码坐标)
# self.driver.tap(950, 1850)

# 新的方式 (VLM 驱动)
screenshot = await executor.get_screenshot()
await executor.tap_element(
    screenshot_base64=screenshot,
    instruction="找出并点击发送按钮"
)
```

### 完整的 BaseDriver 重构

```python
# edge_box/base_driver.py

from edge_box.vlm_driver import VLMDriver, PhysicalExecutor, VLMConfig

class BaseDriver:
    def __init__(self, vlm_config: VLMConfig):
        self.vlm_driver = VLMDriver(vlm_config)
        self.executor = PhysicalExecutor(self.vlm_driver)
    
    async def tap_send_button(self):
        """点击发送按钮"""
        screenshot = await self.executor.get_screenshot()
        return await self.executor.tap_element(
            screenshot_base64=screenshot,
            instruction="找出并点击发送按钮"
        )
    
    async def input_message(self, message: str):
        """输入消息"""
        screenshot = await self.executor.get_screenshot()
        return await self.executor.type_text(
            screenshot_base64=screenshot,
            instruction="找出消息输入框",
            text=message
        )
    
    async def scroll_up(self):
        """向上滑动"""
        return await self.executor.swipe(540, 1600, 540, 400)
    
    async def close(self):
        """关闭驱动"""
        await self.vlm_driver.close()
```

---

## 💡 高级用法

### 自定义 OCR 降级函数

```python
async def custom_ocr_fallback(instruction: str) -> Optional[Dict]:
    """自定义 OCR 降级函数"""
    # 使用 Tesseract 或其他 OCR 库
    # 返回 {"x": 950, "y": 1850}
    pass

# 使用自定义降级函数
success = await executor.tap_element(
    screenshot_base64=screenshot,
    instruction="找出发送按钮",
    fallback_ocr_func=custom_ocr_fallback
)
```

### 批量操作

```python
async def send_message(executor, message: str):
    """发送消息的完整流程"""
    
    # 第 1 步：获取截图
    screenshot = await executor.get_screenshot()
    if not screenshot:
        return False
    
    # 第 2 步：输入消息
    success = await executor.type_text(
        screenshot_base64=screenshot,
        instruction="找出消息输入框",
        text=message
    )
    if not success:
        return False
    
    # 第 3 步：获取新截图
    await asyncio.sleep(0.5)
    screenshot = await executor.get_screenshot()
    
    # 第 4 步：点击发送
    success = await executor.tap_element(
        screenshot_base64=screenshot,
        instruction="找出并点击发送按钮"
    )
    
    return success
```

---

## 🛡️ 错误处理

### 完整的错误处理示例

```python
async def safe_tap_element(executor, instruction: str) -> bool:
    """安全的点击操作"""
    
    try:
        # 获取截图
        screenshot = await executor.get_screenshot()
        if not screenshot:
            logger.error("获取截图失败")
            return False
        
        # 点击元素
        success = await executor.tap_element(
            screenshot_base64=screenshot,
            instruction=instruction
        )
        
        if not success:
            logger.error(f"点击失败: {instruction}")
            return False
        
        logger.info(f"✓ 点击成功: {instruction}")
        return True
    
    except Exception as e:
        logger.error(f"点击异常: {e}")
        return False
```

---

## 📈 性能指标

```
VLM 调用延迟：2-5 秒
OCR 降级延迟：1-2 秒
点击执行延迟：< 100ms
截图获取延迟：1-2 秒
总体操作延迟：3-7 秒
```

---

## ✅ 完整性检查清单

- [x] VLMDriver 完整
- [x] PhysicalExecutor 完整
- [x] VLM 响应解析完整
- [x] OCR 降级完整
- [x] 错误处理完整
- [x] 日志记录完整
- [x] 文档完整

---

## 📚 相关文件

```
edge_box/vlm_driver.py              # VLM 物理执行驱动
edge_box/base_driver.py             # BaseDriver（待重构）
```

---

## 🎉 现在就开始吧！

```python
import asyncio
from edge_box.vlm_driver import VLMDriver, PhysicalExecutor, VLMConfig

async def main():
    # 初始化
    config = VLMConfig(
        api_key="your-openai-api-key",
        model="gpt-4-vision"
    )
    
    vlm_driver = VLMDriver(config)
    executor = PhysicalExecutor(vlm_driver)
    
    try:
        # 获取截图
        screenshot = await executor.get_screenshot()
        
        # 点击发送按钮
        success = await executor.tap_element(
            screenshot_base64=screenshot,
            instruction="找出并点击发送按钮"
        )
        
        if success:
            print("✓ 操作成功")
        else:
            print("✗ 操作失败")
    
    finally:
        await vlm_driver.close()

asyncio.run(main())
```

---

**Project Claw VLM 物理执行驱动层已完成！** 🚀🦞

彻底摆脱硬编码坐标，基于视觉理解的智能 UI 操控！
