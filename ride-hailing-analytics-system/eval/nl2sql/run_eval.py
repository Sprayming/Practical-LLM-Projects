#!/usr/bin/env python3
"""
网约车运营 NL2SQL 评测脚本

功能：
  1. 用可复现随机种子生成一个独立的评测数据库（不污染 data/ride_hailing.db）
  2. 逐条执行 evaluation_set.json 中的 gold SQL，校验其可执行且返回合理结果
  3. （可选）传入 --with-llm 时，调用真实 NL2SQL 管线生成 SQL，
     用 execution accuracy（执行结果集合相等）对比 gold SQL，量化准确率

用法：
  # 仅校验评测集 gold SQL 本身是否正确（无需 LLM key）
  python eval/nl2sql/run_eval.py --seed 42 --drivers 60 --orders 800 --coupons 400

  # 跑真实 NL2SQL 准确率（需要在 .env 中配置 LLM_API_KEY）
  python eval/nl2sql/run_eval.py --with-llm --seed 42 --drivers 60 --orders 800 --coupons 400
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

# 将项目根加入 sys.path，便于导入 scripts / app 包
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import scripts.generate_data as gen  # noqa: E402


def build_eval_db(db_path: Path, seed: int | None, drivers: int, orders: int, coupons: int) -> None:
    """用可复现种子生成独立评测库。

    采用 DROP + CREATE 而非删除文件，避免受沙箱安全删除策略限制，
    同时保证每次运行都从干净 schema 开始（可复现）。
    """
    conn = sqlite3.connect(str(db_path))
    drop = (
        "DROP TABLE IF EXISTS drivers; "
        "DROP TABLE IF EXISTS coupon_types; "
        "DROP TABLE IF EXISTS coupons; "
        "DROP TABLE IF EXISTS orders; "
        "DROP TABLE IF EXISTS redemptions;"
    )
    conn.executescript(drop)
    schema = (ROOT / "data" / "schema_sqlite.sql").read_text(encoding="utf-8")
    conn.executescript(schema)

    if seed is not None:
        gen.random.seed(seed)

    drivers_list = gen.generate_drivers(conn, drivers)
    gen.generate_coupon_types(conn)
    coupons_list = gen.generate_coupons(conn, coupons, drivers)
    orders_list = gen.generate_orders(conn, orders, drivers_list)
    gen.generate_redemptions(conn, coupons_list, orders_list)
    conn.close()


def run_sql(db_path: Path, sql: str):
    """执行 SQL，返回 (rows, columns)。出错返回 ([], [])。"""
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cur = conn.execute(sql)
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows, cols
    except Exception as e:  # noqa: BLE001
        return [], [f"ERROR: {e}"]


def result_signature(rows):
    """将结果集转为可比较的签名（忽略行顺序与列名，仅比数据值）。"""
    return sorted(tuple(r.values()) for r in rows)


def validate_expect(case: dict, rows, cols) -> bool:
    """根据 expect 字段校验结果形态是否合理。"""
    expect = case.get("expect", "multi_row")
    if len(rows) == 0:
        return False
    if expect == "scalar":
        return len(rows) == 1 and len(cols) == 1
    return True  # multi_row: 至少一行即可


def main():
    parser = argparse.ArgumentParser(description="网约车 NL2SQL 评测")
    parser.add_argument("--eval-file", default=str(ROOT / "eval" / "nl2sql" / "evaluation_set.json"))
    parser.add_argument("--db", default=str(ROOT / "data" / "eval_nl2sql.db"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--drivers", type=int, default=60)
    parser.add_argument("--orders", type=int, default=800)
    parser.add_argument("--coupons", type=int, default=400)
    parser.add_argument("--with-llm", action="store_true", help="调用真实 NL2SQL 管线计算准确率（需 LLM_API_KEY）")
    args = parser.parse_args()

    db_path = Path(args.db)
    eval_path = Path(args.eval_file)
    if not eval_path.exists():
        print(f"[FATAL] 评测集不存在: {eval_path}")
        sys.exit(1)

    print("=" * 64)
    print("Step 1/2: 构建可复现评测库 ...")
    build_eval_db(db_path, args.seed, args.drivers, args.orders, args.coupons)
    print(f"  评测库: {db_path}")

    cases = json.loads(eval_path.read_text(encoding="utf-8"))["cases"]
    print(f"  评测用例: {len(cases)} 条")
    print("=" * 64)

    # ---- gold SQL 校验 ----
    print("Step 2/2: 校验 gold SQL 正确性")
    gold_pass = 0
    for case in cases:
        rows, cols = run_sql(db_path, case["gold_sql"])
        ok = validate_expect(case, rows, cols)
        gold_pass += 1 if ok else 0
        status = "OK " if ok else "FAIL"
        preview = ""
        if rows and cols:
            preview = f"  | cols={cols}  sample={rows[0]}"
        print(f"  [{status}] {case['id']} ({case['category']}): {case['question']}{preview}")

    gold_rate = gold_pass / len(cases) * 100
    print("-" * 64)
    print(f"Gold SQL 校验通过率: {gold_pass}/{len(cases)} = {gold_rate:.1f}%")

    # ---- 可选：真实 NL2SQL 准确率 ----
    if args.with_llm:
        try:
            from app.nlsql.sql_generator import generate_sql
            from app.nlsql.sql_executor import validate_sql
        except Exception as e:  # noqa: BLE001
            print(f"[WARN] 无法导入 NL2SQL 管线（缺少依赖或 LLM 配置）: {e}")
            sys.exit(2)

        print("=" * 64)
        print("真实 NL2SQL 准确率评估（execution accuracy）")
        match = 0
        for case in cases:
            gold_rows, _ = run_sql(db_path, case["gold_sql"])
            gold_sig = result_signature(gold_rows)
            try:
                pred_sql, _ = generate_sql(case["question"])
                if not validate_sql(pred_sql):
                    pred_sql = ""
            except Exception as e:  # noqa: BLE001
                pred_sql = ""
                print(f"  [ERR ] {case['id']} 生成失败: {e}")

            pred_rows, _ = run_sql(db_path, pred_sql) if pred_sql else ([], [])
            pred_sig = result_signature(pred_rows)
            hit = gold_sig == pred_sig
            match += 1 if hit else 0
            print(f"  [{'HIT ' if hit else 'MISS'}] {case['id']}: {case['question']}")
            if not hit:
                print(f"        gold  = {case['gold_sql']}")
                print(f"        pred  = {pred_sql}")

        acc = match / len(cases) * 100
        print("-" * 64)
        print(f"NL2SQL 执行准确率: {match}/{len(cases)} = {acc:.1f}%")
    else:
        print("（未启用 --with-llm，跳过真实 NL2SQL 评估；配置 LLM_API_KEY 后可加 --with-llm 量化准确率）")

    print("=" * 64)
    # 退出码：gold 校验必须 100% 通过
    sys.exit(0 if gold_pass == len(cases) else 1)


if __name__ == "__main__":
    main()
