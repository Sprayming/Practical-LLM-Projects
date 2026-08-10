"""
NL2SQL 评测集集成测试

目标：保证 evaluation_set.json 中的 gold SQL 在可复现种子库上
「本身是正确的」——可执行、返回非空、结果形态符合 expect 约定。
（真实 NL2SQL 准确率评估由 eval/nl2sql/run_eval.py --with-llm 负责，
 不在此处调用，以免依赖 LLM_API_KEY 与网络。）

运行：
  pytest tests/test_nl2sql_eval.py -v
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import scripts.generate_data as gen  # noqa: E402

EVAL_FILE = ROOT / "eval" / "nl2sql" / "evaluation_set.json"
SEED = 42
DRIVERS = 60
ORDERS = 800
COUPONS = 400


def _build_db(path: Path) -> None:
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(str(path))
    schema = (ROOT / "data" / "schema_sqlite.sql").read_text(encoding="utf-8")
    conn.executescript(schema)
    gen.random.seed(SEED)
    drivers = gen.generate_drivers(conn, DRIVERS)
    gen.generate_coupon_types(conn)
    coupons = gen.generate_coupons(conn, COUPONS, DRIVERS)
    orders = gen.generate_orders(conn, ORDERS, drivers)
    gen.generate_redemptions(conn, coupons, orders)
    conn.close()


@pytest.fixture(scope="session")
def db_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    p = tmp_path_factory.mktemp("nl2sql_eval") / "eval.db"
    _build_db(p)
    return p


def _run_sql(db_path: Path, sql: str):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.execute(sql)
    cols = [d[0] for d in cur.description] if cur.description else []
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows, cols


_eval = json.loads(EVAL_FILE.read_text(encoding="utf-8"))
CASES = _eval["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_gold_sql(db_path: Path, case: dict) -> None:
    rows, cols = _run_sql(db_path, case["gold_sql"])

    # gold SQL 必须是只读 SELECT（允许 WITH 开头的 CTE 查询）
    sql_upper = case["gold_sql"].strip().upper()
    assert sql_upper.startswith("SELECT") or sql_upper.startswith("WITH"), \
        f"{case['id']} 必须是 SELECT 或 WITH(CTE) 只读查询"

    # 必须返回结果
    assert len(rows) >= 1, f"{case['id']} ({case['question']}) 返回空结果"

    # 结果形态需符合 expect 约定
    if case["expect"] == "scalar":
        assert len(rows) == 1, f"{case['id']} 期望单行，实际 {len(rows)} 行"
        assert len(cols) == 1, f"{case['id']} 期望单列，实际 {len(cols)} 列"
    elif case["expect"] == "multi_row":
        assert len(rows) >= 1, f"{case['id']} 期望多行，实际 {len(rows)} 行"
    else:
        raise AssertionError(f"未知 expect 类型: {case['expect']}")
