# 问答质量评测回归（轻量自进化闭环 · 闸门式验证）

本目录是 legal-doc-rag "轻量自进化闭环"的第二环：**闸门式验证**。闭环第一环（`app/core/trace_store.py`）
负责把每次问答沉淀到 SQLite 做经验捕获；本目录负责在**模型升级 / prompt 修改 / 检索参数调整**后，
跑一批标准问答对判断有没有"退化"。法律场景答错有合规风险，所以**不做自动改 prompt，只做人工把关闸门**。

## 文件
- `run_eval.py`：评测脚本（仅依赖标准库，无需额外装包）。
- `golden_set.example.json`：示例 golden set（标准问答对）。**请基于你实际上传的租户文档复制一份 `golden_set.json` 并定制**。
- `eval_report.json`：运行后生成的报告（通过率 / 平均延迟 / 逐条结果）。

## 用法

```bash
# 1. 复制示例并定制（关键词要贴合你租户知识库里真实存在的法条/术语）
cp tests/eval/golden_set.example.json tests/eval/golden_set.json
# 编辑 golden_set.json:把 query 换成你文档里的真实问题,expect_keywords 换成答案必含的关键词

# 2. 先确保服务已启动
#    uvicorn app.main:app --port 8000  (或 docker-compose up)

# 3. 跑评测
python tests/eval/run_eval.py \
    --base-url http://127.0.0.1:8000 \
    --user admin --password Admin123456 \
    --golden tests/eval/golden_set.json
```

## 判定规则
每条 case：`{query, expect_keywords:[...], min_citations:N}`
- 答案**包含全部** `expect_keywords` 且 引用数 `>= min_citations` => 通过
- 否则 => 失败（报告里列出缺失关键词 / 引用不足原因）

## 怎么当"闸门"
- **改 prompt / 检索参数前**：跑一次，记下来通过率（基线）。
- **改完后**：再跑一次，通过率不降（且延迟不恶化）才允许发布。
- 脚本退出码：全部通过=0，有失败=1，可直接接 CI 或人工 review。

## 与 trace_store 的关系
`run_eval.py` 是主动评测；`app/core/trace_store.py` 是被动沉淀（线上真实问答 + 用户👍/👎）。
两者互补：trace_store 的 `get_low_rated()` 能挖出"线上答得差"的样本，可作为 golden set 的补充来源。

## 从租户文档自动生成 golden set
手动编写标准问答对费时且难覆盖真实业务。提供 `build_golden_from_docs.py`，扫描你**真实上传的文档**自动生成贴合业务的评测集：

```bash
# 默认扫描 uploads/ 全部租户文档,每文档生成 3 题,写出 tests/eval/golden_set.json
python tests/eval/build_golden_from_docs.py

# 只针对某个租户,且每文档生成 5 题
python tests/eval/build_golden_from_docs.py --tenant 7e990ab9 --per-doc 5

# 指定文档目录与输出路径(支持 .txt/.md/.pdf/.docx)
python tests/eval/build_golden_from_docs.py --docs-dir ./my_docs --out ./my_golden.json
```

要点：
- 复用项目已有的 `app.llm.client.complete_chat`（含多供应商故障转移），所以 `.env` 里的 `LLM_API_KEY` 要可用。
- 每篇文档抽取文本后由 LLM 产出 `{query, expect_keywords, min_citations}` 问答对，自动合并写出。
- 生成后直接 `python tests/eval/run_eval.py` 即可评测，形成"文档更新 → 刷新 golden set → 回归闸门"的闭环。

> 提示：`golden_set.json` 是各租户定制的工作文件，建议加入 `.gitignore` 不入库；仓库只跟踪 `golden_set.example.json` 示例。
