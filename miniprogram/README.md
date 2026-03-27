# Project Claw 微信小程序

## 目录结构

```
miniprogram/
├── app.js              # 全局入口，初始化 clientId / 画像
├── app.json            # 页面路由 / TabBar 配置
├── app.wxss            # 全局样式（气泡、按钮、卡片等）
├── sitemap.json
├── api/
│   └── request.js      # HTTP 封装 + WS 监听器 + DialogueAPI / IntentAPI
├── utils/
│   └── profile.js      # C/B 端画像管理 + 满意度计算
└── pages/
    ├── index/          # C端发现页（发起智能谈判 / 广播意图）
    ├── dialogue/       # B/C Agent 多轮对话页（实时 WS 气泡）
    ├── orders/         # 订单历史页
    └── merchant/       # B端商家控制台（画像配置 + 实时统计）
```

## 对接后端地址

修改 `app.js` 中：

```js
globalData: {
  serverBase: 'http://你的公网IP:8765',
  wsBase:     'ws://你的公网IP:8765',
  token: '',   // 如果设置了 INTERNAL_API_TOKEN 填这里
}
```

## 核心功能

| 功能 | 路径 |
|------|------|
| 发起 A2A 智能谈判 | `POST /a2a/dialogue/start` |
| C端发轮 | `POST /a2a/dialogue/client_turn` |
| 实时收 B端回复 | `WS /ws/a2a/dialogue/client/{client_id}` |
| 查看会话历史 | `GET /a2a/dialogue/{session_id}` |
| 快速广播意图 | `POST /intent` |
| 订单列表 | `GET /orders` |
| B端画像配置 | `POST /a2a/dialogue/profile/merchant` |
| C端画像配置 | `POST /a2a/dialogue/profile/client` |

## 开发工具使用

1. 微信开发者工具 -> 导入项目 -> 选择 `miniprogram/` 目录
2. AppID 填你的小程序 AppID（或使用测试号）
3. 后端服务需部署到有公网的服务器，或开发时使用内网穿透
4. 在「详情 -> 本地设置」勾选「不校验合法域名」（开发调试用）
