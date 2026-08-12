#!/usr/bin/env python3
"""
run.py —— 本地开发服务启动入口

【作用与功能】
使用 uvicorn 以热重载（reload）模式启动 FastAPI 应用（app.main:app），
作为本地开发与调试阶段统一的后端服务启动脚本。

【主要组成】
- 顶层逻辑：调用 `uvicorn.run` 拉起 ASGI 应用，监听 0.0.0.0:8000 并开启 reload。

【适用场景】
- 场景1：本地运行 `python run.py` 启动后端 API 服务
- 场景2：开发阶段配合 reload 实时生效代码改动，便于调试

【依赖关系】
- 依赖 uvicorn 第三方库与项目 `app.main` 模块（需提供 FastAPI 应用实例 app）
- 服务监听端口 8000，需保证该端口未被占用
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
