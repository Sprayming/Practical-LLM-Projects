"""
build_golden_from_docs.py —— 从租户已上传文档自动生成问答质量评测集(golden set)

【作用与功能】
轻量自进化闭环需要一份"标准问答对"(golden set)作为回归闸门。手动编写费时且难覆盖
真实业务。本脚本扫描 legal-doc-rag 知识库里的真实文档(默认 uploads/<tenant>/ 下),
抽取文本后调用 LLM 批量生成贴近业务的 {query, expect_keywords, min_citations} 问答对,
直接写出 tests/eval/golden_set.json,供 run_eval.py 使用。

这是把"被动沉淀(trace_store)"与"主动评测(run_eval)"打通的桥梁:
今后租户文档更新 -> 跑本脚本刷新 golden set -> 改 prompt/检索参数前跑 run_eval 看是否退化。

【用法】
    # 默认扫描 uploads/ 全部租户文档,每文档生成 3 题,写出 tests/eval/golden_set.json
    python tests/eval/build_golden_from_docs.py

    # 只针对某个租户,且每文档生成 5 题
    python tests/eval/build_golden_from_docs.py --tenant 7e990ab9 --per-doc 5

    # 指定文档目录与输出路径
    python tests/eval/build_golden_from_docs.py --docs-dir ./my_docs --out ./my_golden.json

【依赖】
- 标准库 + pypdf(抽取 PDF 文本,requirements 已含)。
- 需要可用的 LLM_API_KEY(主供应商),与线上一致(复用 app.llm.client 故障转移)。
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def _load_env(path):
    """把项目根 .env 注入环境变量,确保 import app.config 时能读到 LLM_* 配置。"""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


# 必须在 import app 模块之前注入 .env(配置在 import 时即读取 os.getenv)
_load_env(BASE_DIR / ".env")

sys.path.insert(0, str(BASE_DIR))
from app.llm.client import complete_chat  # noqa: E402

SUPPORTED_EXT = {".txt", ".md", ".pdf", ".docx"}
MAX_CHARS = 6000

PROMPT_TMPL = """你是一名法律文档评测集构建助手。下面是一段法律文档的文本内容。
请基于该文档生成 {n} 个"普通用户最可能向智能问答系统提出的真实问题",用于评测 RAG 系统的回答质量。

要求:
1. 问题必须是文档内容能够回答的真实业务问题(不要问文档里没有的信息)。
2. 对每个问题,给出答案中"必须出现"的 2-4 个关键词(expect_keywords,用于判断回答是否切题)。
3. min_citations 设为 1(答案应至少引用一条来源)。
4. 只输出 JSON 数组,不要任何解释,格式:
[{{"query":"...","expect_keywords":["..."],"min_citations":1}}, ...]

文档内容:
\"\"\"
{text}
\"\"\"
"""


def extract_text(path: Path) -> str:
    """抽取文档纯文本,支持 txt/md/pdf/docx;失败返回空字符串。"""
    ext = path.suffix.lower()
    try:
        if ext in (".txt", ".md"):
            return path.read_text(encoding="utf-8", errors="ignore")
        if ext == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(str(path))
            return "\n".join((p.extract_text() or "") for p in reader.pages)
        if ext == ".docx":
            import docx
            d = docx.Document(str(path))
            return "\n".join(par.text for par in d.paragraphs)
    except Exception as e:
        print(f"  [warn] 文本抽取失败 {path.name}: {e}")
    return ""


def parse_llm_json(text: str):
    """容错解析 LLM 可能带 ```json 围栏或前后缀的输出。"""
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```", 2)
        if len(parts) >= 2:
            text = parts[1]
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        return json.loads(text)
    except Exception:
        s, e = text.find("["), text.rfind("]")
        if s != -1 and e != -1:
            try:
                return json.loads(text[s:e + 1])
            except Exception:
                return None
    return None


async def gen_for_doc(text: str, n: int):
    """对单篇文档调用 LLM 生成问答对,返回清洗后的 case 列表。"""
    prompt = PROMPT_TMPL.format(n=n, text=text[:MAX_CHARS])
    try:
        out = await complete_chat(
            [{"role": "user", "content": prompt}],
            temperature=0.3, max_tokens=1024,
        )
    except Exception as e:
        print(f"  [warn] LLM 调用失败: {e}")
        return []
    data = parse_llm_json(out)
    if not isinstance(data, list):
        return []
    cases = []
    for item in data:
        q = item.get("query")
        kw = item.get("expect_keywords") or []
        if q and kw:
            cases.append({
                "query": q,
                "expect_keywords": kw,
                "min_citations": item.get("min_citations", 1) or 1,
            })
    return cases


async def main_async(args):
    docs_dir = Path(args.docs_dir)
    if args.tenant:
        docs_dir = docs_dir / args.tenant
    if not docs_dir.exists():
        print(f"[error] 文档目录不存在: {docs_dir}")
        return 1
    files = [p for p in docs_dir.rglob("*") if p.suffix.lower() in SUPPORTED_EXT]
    if not files:
        print(f"[error] 在 {docs_dir} 下未找到支持的文档({', '.join(SUPPORTED_EXT)})")
        return 1
    print(f"[build] 找到 {len(files)} 个文档,每文档生成 {args.per_doc} 题 ...")
    all_cases = []
    for f in files:
        print(f"  - 处理 {f.name}")
        text = extract_text(f)
        if not text.strip():
            print("    (空文本,跳过)")
            continue
        cases = await gen_for_doc(text, args.per_doc)
        print(f"    => {len(cases)} 题")
        all_cases.extend(cases)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(all_cases, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[build] 完成,共 {len(all_cases)} 题,已写出 {out}")
    if not all_cases:
        print("[warn] 未生成任何题目,请检查 LLM_API_KEY 是否配置或文档是否非空。")
    return 0


def main():
    ap = argparse.ArgumentParser(description="从租户文档自动生成 golden set")
    ap.add_argument("--docs-dir", default=str(BASE_DIR / "uploads"), help="文档根目录(默认 uploads/)")
    ap.add_argument("--tenant", default=None, help="只处理指定租户子目录(如 7e990ab9)")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent / "golden_set.json"), help="输出路径")
    ap.add_argument("--per-doc", type=int, default=3, help="每文档生成题数")
    args = ap.parse_args()
    raise SystemExit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
