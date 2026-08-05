# 长期项目笔记

## 用户工作领域
主要做大模型应用开发，专注于RAG（检索增强生成）和多Agent协作系统。关注AI应用的实际落地和效率提升。

## Legal-DOC-RAG 项目
- 路径：D:\git\legal-doc-rag
- 类型：法律文书智能问答系统
- 技术栈：FastAPI + RAG（检索增强生成）
- 状态：P0+P1+P2改进已完成，功能完整度较高
- 关键模块：混合检索、三层记忆系统、多租户、异步任务处理
- 部署：Docker + 本地启动脚本
- 文档：README 详细，包含完整更新日志
- 测试：19个单元测试已添加

## ride-hailing-analytics-system 项目
- 路径：D:\git\ride-hailing-analytics-system
- 类型：网约车数据分析运营系统
- 技术栈：FastAPI + LLM（DeepSeek）+ SQLite/MySQL
- 状态：P0+P1改进已完成，44个测试全部通过
- 关键模块：NLSQL自然语言转SQL、Agent编排、数据分析、用户认证
- 安全：SQL注入防护、JWT认证、速率限制、输入验证
- 前端：响应式Web界面 + Chart.js数据可视化
- 部署：Docker + docker-compose（App + MySQL + Nginx）
- 文档：README 完整，包含API文档、部署指南、开发指南