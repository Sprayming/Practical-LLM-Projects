# Ride-Hailing Analytics System
网约车平台的数据分析运营系统

基于自然语言查询的数据分析系统，面向网约车运营场景。
用户可以用日常语言问"哪个价位的卡券核销率最高？"，系统自动生成 SQL、查询数据库、分析数据并给出运营建议。

## 系统架构

`
用户问题
  ↓
Schema 理解（告诉 LLM 数据库结构）
  ↓
LLM 生成 SQL
  ↓
SQL 校验 → 执行查询
  ↓
LLM 解读数据 → 给出运营建议
  ↓
返回结果
`

## 数据模型

- drivers — 司机信息
- coupon_types — 卡券类型（面值、有效期等）
- coupons — 卡券发放记录
- orders — 订单记录
- redemptions — 核销记录

## 快速开始

1. 复制 .env.example 为 .env，填入 DeepSeek API Key
2. 创建数据库并导入 data/schema.sql
3. pip install -r requirements.txt
4. python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/query/ | 自然语言查询 |
| GET  | /api/dashboard/ | 仪表盘数据 |
