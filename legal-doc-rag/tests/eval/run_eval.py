"""
tests/eval/run_eval.py —— 问答质量评测回归脚本（轻量自进化闭环的"闸门式验证"工具）

【作用与功能】
对 legal-doc-rag 跑一批"标准问答对"(golden set)，统计通过率、平均引用数、平均延迟，
用于模型升级 / prompt 修改 / 检索参数调整后判断是否"退化"。这是自进化闭环里的人工
把关闸门：任何改动上线前先跑一遍本脚本，通过率不降才允许发布（法律场景不自动改 prompt）。

【用法】
    python tests/eval/run_eval.py \
        --base-url http://127.0.0.1:8000 \
        --user admin --password Admin123456 \
        --golden tests/eval/golden_set.json

【判定规则】
每条 case: {query, expect_keywords:[...], min_citations:N}
    - 答案包含全部 expect_keywords 且 引用数 >= min_citations => 通过
    - 否则 => 失败,列出缺失关键词 / 引用不足原因

【依赖】仅标准库 urllib/json/time/argparse,无需额外安装包。
"""

import argparse
import json
import time
import urllib.request
import urllib.error


def login(base_url, user, password):
    """登录拿 JWT token。"""
    url = f"{base_url}/api/auth/login"
    data = json.dumps({"username": user, "password": password}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    if "token" not in body:
        raise RuntimeError(f"登录失败,响应无 token: {body}")
    return body["token"]


def ask(base_url, token, query, history=None):
    """调 /api/chat 非流式,返回 (answer, citations, duration_ms, error)。"""
    url = f"{base_url}/api/chat"
    payload = {"message": query, "stream": False, "history": history or []}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        dur = (time.time() - start) * 1000
        return body.get("answer", ""), body.get("citations", []), dur, None
    except urllib.error.HTTPError as e:
        dur = (time.time() - start) * 1000
        return "", [], dur, f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:200]}"
    except Exception as e:
        dur = (time.time() - start) * 1000
        return "", [], dur, str(e)


def evaluate_case(query, expect_keywords, min_citations, answer, citations, dur, err):
    """单条判定,返回 (passed, reasons)。"""
    reasons = []
    if err:
        return False, [f"请求错误: {err}"]
    if not answer:
        return False, ["答案为空"]
    missing = [k for k in expect_keywords if k not in answer]
    if missing:
        reasons.append(f"缺失关键词: {missing}")
    n_cit = len(citations) if isinstance(citations, list) else 0
    if n_cit < min_citations:
        reasons.append(f"引用不足: {n_cit} < {min_citations}")
    passed = (len(missing) == 0) and (n_cit >= min_citations)
    return passed, reasons


def main():
    parser = argparse.ArgumentParser(description="legal-doc-rag 问答质量评测回归")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--user", default="admin")
    parser.add_argument("--password", default="Admin123456")
    parser.add_argument("--golden", default="tests/eval/golden_set.json")
    parser.add_argument("--report", default="tests/eval/eval_report.json")
    args = parser.parse_args()

    with open(args.golden, "r", encoding="utf-8") as f:
        cases = json.load(f)

    print(f"[eval] 登录 {args.base_url} ...")
    token = login(args.base_url, args.user, args.password)
    print(f"[eval] 拿到 token, 共 {len(cases)} 条 case")

    results = []
    total_dur = 0.0
    pass_count = 0
    for i, case in enumerate(cases, 1):
        query = case["query"]
        expect = case.get("expect_keywords", [])
        min_cit = case.get("min_citations", 1)
        answer, citations, dur, err = ask(args.base_url, token, query)
        total_dur += dur
        passed, reasons = evaluate_case(query, expect, min_cit, answer, citations, dur, err)
        if passed:
            pass_count += 1
        results.append({
            "no": i, "query": query, "passed": passed,
            "duration_ms": round(dur, 1),
            "citations": len(citations) if isinstance(citations, list) else 0,
            "reasons": reasons,
        })
        flag = "OK " if passed else "FAIL"
        print(f"[{flag}] #{i} {dur:7.1f}ms cit={results[-1]['citations']} {query[:30]}")

    rate = pass_count / len(cases) * 100 if cases else 0
    avg_dur = total_dur / len(cases) if cases else 0
    summary = {
        "total": len(cases),
        "passed": pass_count,
        "pass_rate": round(rate, 1),
        "avg_duration_ms": round(avg_dur, 1),
        "results": results,
    }
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print("\n==== 评测汇总 ====")
    print(f"通过率 : {pass_count}/{len(cases)} ({rate:.1f}%)")
    print(f"平均延迟: {avg_dur:.1f} ms")
    print(f"报告已存: {args.report}")
    # 退出码:有失败则非 0,便于 CI / 人工闸门判定
    raise SystemExit(0 if pass_count == len(cases) else 1)


if __name__ == "__main__":
    main()
