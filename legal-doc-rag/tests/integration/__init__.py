"""
integration 测试包 —— 验证「多个真实组件被接线起来跑得通」的端到端集成用例集合。

【测试覆盖范围】
- 认证链路:注册/登录/JWT 签发与校验、受保护接口鉴权。
- 聊天接口:完整检索编排链路 + 缺文档/非法请求体等边界。
- 文档上传:API 契约、落盘、列表可见、多租户隔离。
- 请求限流:slowapi 限流是否真正生效(超过阈值返回 429)。

【适用场景】
- 用 `pytest -m integration` 运行；外部依赖(LLM/embedding/OCR/向量库)以 mock 替代。

【依赖】
- 本包内 conftest.py 提供的 fixture:test_env / client / auth_headers。
"""