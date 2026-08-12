"""
app —— legal-doc-rag 应用包的初始化模块（包标识文件）

【作用与功能】
该文件作为 legal-doc-rag RAG 系统的顶层 Python 包标识文件，使 `app` 目录成为
一个可被 `import app...` 正常导入的包。它本身不包含运行逻辑，主要作用是声明
包的边界，并作为应用各子模块（api、core、security、retrieval 等）的统一
命名空间入口。

【主要组成】
- 本文件为包标记文件，无导出内容；实际业务逻辑分散在 app 下的各个子模块中。

【适用场景】
- 场景1：Python 解释器在导入 `app` 或 `app.core` 等子包时自动识别此文件作为包根。
- 场景2：作为应用代码统一导入路径（如 `from app.main import app`）的基础。

【依赖关系】
- 上游调用方：FastAPI 应用启动、各业务模块的相对导入。
- 下游依赖：app.core、app.api、app.security、app.retrieval 等子包。
"""
