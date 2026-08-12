"""
tests 包 —— legal-doc-rag 项目全部 pytest 测试用例的包初始化文件。

【测试覆盖范围】
- 本包作为 pytest 发现测试用例的包根目录，本身不含测试逻辑。
- 其子模块（tests/conftest.py、tests/unit/*）承载具体的单元与接口测试。

【适用场景】
- 由 pytest 自动识别为测试包根目录，统一组织项目测试代码。

【依赖】
- 运行时依赖 pytest 及各测试模块所引用的 app.* 业务代码。
"""
