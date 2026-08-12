"""
evaluation 测试包 —— 量化「回答质量」而非「代码对错」的评测用例集合。

【测试覆盖范围】
- golden 回归测试集结构校验（离线）。
- RAGAS 评测 harness 离线验证：mock LLM 后能否正确组装评测数据集。
- 真实 RAGAS 评测（需 ragas + API key，否则自动跳过）。

【适用场景】
- 用 `pytest -m evaluation` 运行，覆盖评测（evaluation）模块的功能与可跳过的边界。

【依赖】
- 本包内 test_ragas_eval.py、被测模块 scripts/run_ragas_eval.py、Fixture GOLDEN。
"""