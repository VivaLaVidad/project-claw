---
name: Project Claw 完整前端系统建设
overview: 构建完整的 C 端小程序和 B 端管理后台，支持多租户、实时交互、成本追踪等功能
todos:
  - id: miniprogram-structure
    content: 创建小程序项目结构和基础配置
    status: pending
  - id: miniprogram-auth
    content: 实现小程序认证和登录功能
    status: pending
  - id: miniprogram-voice
    content: 实现语音对讲模块
    status: pending
  - id: miniprogram-messages
    content: 实现消息和订单模块
    status: pending
  - id: admin-structure
    content: 创建 B 端后台项目结构
    status: pending
  - id: admin-dashboard
    content: 实现仪表板和监控功能
    status: pending
  - id: admin-cost
    content: 实现成本分析和报表
    status: pending
  - id: admin-approval
    content: 实现人工干预审批系统
    status: pending
  - id: api-integration
    content: 集成后端 API 接口
    status: pending
  - id: deployment
    content: 部署和上线
    status: pending
isProject: false
---

# Project Claw 完整前端系统建设计划

## 📋 项目范围

### C 端小程序 (WeChat Mini Program)

- 用户认证和登录
- 实时语音对讲
- 消息历史查看
- 订单管理
- 用户个人中心

### B 端管理后台 (Admin Dashboard)

- 多智能体监控
- 成本追踪和分析
- 人工干预审批
- 模型管理
- 数据统计和报表

## 🎯 技术栈

### C 端小程序

- 框架: 原生微信小程序 / Taro
- UI: 自定义组件库
- 状态管理: Redux / Pinia
- 网络: WebSocket + HTTP

### B 端后台

- 框架: React 18 + TypeScript
- UI: Ant Design Pro / Material-UI
- 状态管理: Redux Toolkit
- 图表: ECharts / Recharts
- 实时: WebSocket

## 📊 核心功能模块

### C 端小程序

1. 认证模块 (登录、注册、授权)
2. 语音对讲模块 (WebAudio API)
3. 消息模块 (历史、实时)
4. 订单模块 (列表、详情)
5. 个人中心 (设置、反馈)

### B 端后台

1. 仪表板 (概览、KPI)
2. 智能体管理 (监控、控制)
3. 成本分析 (按租户、按模型、按日期)
4. 人工干预 (待审批、历史)
5. 系统设置 (模型、规则、用户)

## 🚀 实现步骤

1. 创建小程序项目结构
2. 实现 C 端核心功能
3. 创建 B 端项目结构
4. 实现 B 端核心功能
5. 集成 API 接口
6. 测试和优化
7. 部署上线

