# RideOps AI — 网约车运营数据分析助手

## 项目简介
基于 FastAPI + DeepSeek 的网约车运营数据分析平台。
上传运营数据，AI 自动分析订单趋势、司机绩效、收入变化，生成运营建议报告。

## 技术栈
- **后端**: FastAPI + Pandas + NumPy
- **AI**: DeepSeek API（OpenAI 兼容接口）
- **前端**: HTML + Chart.js（纯静态）

## 项目结构
```
rideops-ai/
├── backend/
│   ├── app/
│   │   ├── main.py          — 应用入口
│   │   ├── config.py        — 配置中心
│   │   ├── models/          — 数据模型
│   │   │   └── __init__.py  — Order, Driver, DailyStats, AnalysisReport
│   │   ├── data/
│   │   │   ├── loader.py    — 数据加载（CSV/Excel）
│   │   │   └── preprocessor.py — 数据清洗
│   │   ├── analysis/
│   │   │   ├── statistics.py — KPI 统计
│   │   │   ├── trends.py    — 趋势分析
│   │   │   └── anomalies.py — 异常检测
│   │   ├── ai/
│   │   │   ├── prompts.py   — 提示词模板
│   │   │   └── analyst.py   — AI 分析师
│   │   ├── api/
│   │   │   ├── data.py      — 数据管理接口
│   │   │   ├── analysis.py  — 分析接口
│   │   │   └── reports.py   — 报告接口
│   │   └── reports/
│   │       └── generator.py — 报告生成
│   ├── requirements.txt
│   └── .env.example
├── frontend/                 — 前端页面
├── data/sample/              — 示例数据
├── data/uploads/             — 上传数据
└── README.md
```

## 快速开始

```bash
# 1. 安装依赖
cd backend
pip install -r requirements.txt

# 2. 配置 API Key
cp .env.example .env
# 编辑 .env 填入你的 LLM_API_KEY

# 3. 启动服务
python -m app.main
# 或
uvicorn app.main:app --reload

# 4. 访问
# API: http://127.0.0.1:8000/docs
# 前端: 直接打开 frontend/index.html
```

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/health | 健康检查 |
| POST | /api/data/upload | 上传数据文件 |
| GET | /api/data/orders | 查询订单 |
| GET | /api/data/summary | 数据概览 |
| POST | /api/analysis/run | 执行分析 |
| GET | /api/analysis/trends | 趋势数据 |
| GET | /api/analysis/anomalies | 异常检测 |
| POST | /api/reports/generate | 生成报告 |
| GET | /api/reports/list | 报告列表 |

## 数据格式
### 订单 CSV 示例
```csv
order_id,driver_id,passenger_id,pickup_time,pickup_location,dropoff_location,distance_km,duration_min,fare,status,rating
ORD001,DRV001,PAS001,2024-01-15 08:30:00,朝阳区国贸,海淀区中关村,12.5,35,45.00,completed,4.8
```

## TODO
- [ ] 数据分析模块（统计、趋势、异常检测）
- [ ] AI 分析集成
- [ ] 前端仪表盘
- [ ] 报告导出 PDF
- [ ] 示例数据集
