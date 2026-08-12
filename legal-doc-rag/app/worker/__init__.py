"""
worker/__init__.py —— Legal-DOC-RAG 后台 Worker 子包入口

【作用与功能】
本文件为 app/worker 后台 Worker 子包的包初始化文件。该子包提供两类
后台执行能力：其一是「影子 Worker」（shadow_worker.py）——基于优先级
队列的无阻塞后台任务执行器，用于执行可延迟、可重试的轻量任务；其二是
「Webhook 通知系统」（webhook.py）——将系统事件异步推送到外部订阅地址。
本文件作为子包统一导入入口，供应用层装配后台任务与事件通知。

【主要组成】
- 子模块 `shadow_worker`：优先级任务队列、多 Worker 线程、自动重试、
  通过 get_worker() 获取全局单例
- 子模块 `webhook`：Webhook 配置管理、事件触发、签名校验与失败重试，
  通过 get_webhook_manager() 获取全局单例

【适用场景】
- 场景1：应用启动时创建并启动后台 Worker / Webhook 管理器
- 场景2：业务代码提交可延迟任务（如索引、通知）而不阻塞请求线程

【依赖关系】
- 上游调用方：应用启动流程、文档处理与事件触发逻辑
- 下游依赖：app.worker.shadow_worker、app.worker.webhook
"""
