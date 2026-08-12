"""
评测测试(Evaluation):用 RAGAS 量化「回答质量」。

与 unit/integration 不同，评测关注的是「答案好不好」，而非「代码对不对」。
对法律问答系统，最危险的是代码没报错但**编造法条**——RAGAS 的
Faithfulness(忠实度)指标就是专门拦截这一类问题的。

说明:
  - 本文件离线可跑(golden schema 校验 + harness 离线测试)，不依赖 ragas/网络。
  - 真正的 RAGAS 评分(test_ragas_real_eval)在检测到 ragas 与 API key 时才运行，
    否则自动跳过，便于在 CI 中安全执行。
  - run_ragas_eval.py 已改为惰性导入 ragas，因此无 ragas 时也能 import。
"""
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

# 项目根目录(tests/evaluation -> 上溯三级到 legal-doc-rag 根)
ROOT = Path(__file__).resolve().parent.parent.parent
# golden 回归测试集:离线校验其结构，并供 harness 离线评测使用
GOLDEN = ROOT / "tests" / "golden_test_set.json"


def _load_ragas_module():
    """按路径加载 scripts/run_ragas_eval.py(scripts 无 __init__.py，用 importlib 更稳)。"""
    path = ROOT / "scripts" / "run_ragas_eval.py"
    spec = importlib.util.spec_from_file_location("run_ragas_eval_module", str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.evaluation
def test_golden_test_set_schema():
    """golden 回归测试集结构校验(离线)。"""
    assert GOLDEN.exists(), "tests/golden_test_set.json 缺失"
    data = json.loads(GOLDEN.read_text(encoding="utf-8"))
    items = data.get("questions", []) if isinstance(data, dict) else data
    assert len(items) > 0, "golden 集为空"
    for i, it in enumerate(items):
        assert "question" in it, f"第 {i} 条缺少 question"
        assert "ground_truth" in it, f"第 {i} 条缺少 ground_truth"


@pytest.mark.evaluation
def test_ragas_harness_offline(monkeypatch):
    """离线验证评测 harness:mock LLM 调用后能正确组装评测数据集。"""
    m = _load_ragas_module()
    # 让 call_llm 认为已配置 key
    monkeypatch.setattr(m, "API_KEY", "test-key")

    canned = "应当订立书面劳动合同。"
    canned2 = "自用工之日起一个月内。"

    class _Resp:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": canned}}]}

    class _FakePost:
        def __call__(self, *a, **k):
            # run_ragas_eval 用 requests.post(...).json()["choices"][0]["message"]["content"]
            return _Resp()

    monkeypatch.setattr(m.requests, "post", _FakePost())

    q = m.TEST_QUESTIONS[0]
    ans = m.generate_answer(q["question"], q["contexts"])
    assert ans == canned, ans

    # 组装 RAGAS 所需的四个字段齐全(user_input / response / retrieved_contexts / reference)
    row = {
        "user_input": q["question"],
        "response": ans,
        "retrieved_contexts": q["contexts"],
        "reference": q["ground_truth"],
    }
    for k in ("user_input", "response", "retrieved_contexts", "reference"):
        assert k in row

    # TEST_QUESTIONS 自带 contexts(与 golden 集不同)，评测可直接用
    assert "contexts" in q, "TEST_QUESTIONS 应自带 contexts 才能离线评测"


@pytest.mark.evaluation
def test_ragas_real_eval():
    """真正跑 RAGAS 评测(需 ragas + LLM_API_KEY/ARK_API_KEY，否则跳过)。"""
    ragas = pytest.importorskip("ragas")
    api_key = os.getenv("LLM_API_KEY") or os.getenv("ARK_API_KEY")
    if not api_key:
        pytest.skip("未设置 LLM_API_KEY / ARK_API_KEY，跳过真实 RAGAS 评测")

    m = _load_ragas_module()
    m.run_eval()
    report = ROOT / "evaluation_report.json"
    assert report.exists(), "未生成 evaluation_report.json"
