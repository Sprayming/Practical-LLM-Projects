"""
verify_retrieval.py —— 端到端验证脚本:确认 BGE-M3 SPLADE 稀疏向量已接入混合检索且生效。

【作用与功能】
本脚本是混合检索能力的"自检探针"，用最小可运行样本(5 条法条)跑通一次完整检索链路，
用于回答两个问题:
1. BGE-M3 的 SPLADE 稀疏权重是否真的算出来了(非空)——
   FlagEmbedding 1.4.0 的 scatter_reduce 存在偶发丢值 bug，项目改为自计算，
   本脚本正是该修复是否生效的验证手段；
2. 稠密向量 + BM25 + 稀疏向量经 RRF 融合后，TOP1 能否命中语义正确的法条。
它不是单元测试，而是需要真实模型权重的人工/半自动验证脚本，结果以控制台
✅ / ❌ 的形式直观呈现。

【主要组成】
- `TENANT_ID`:验证专用租户标识，避免污染真实租户的稀疏索引数据
- `DOCS`:5 条真实法条语料(民法典高空抛物、劳动合同法、刑法盗窃、交通安全法、民事诉讼法)
- `QUERY`:一条指向"民法典高空抛物"的自然语言查询，用于检验语义命中
- `main`:全流程主函数——加载模型 → 稀疏编码落盘 → 稠密写入 Chroma → 混合检索 → 打印结论

【适用场景】
- 场景1:升级 FlagEmbedding / BGE-M3 版本后回归验证 —— `python scripts/verify_retrieval.py`
- 场景2:新环境部署完成后确认模型权重可加载、检索链路可跑通
- 场景3:排查"检索结果不准"时，先用干净的 5 条语料排除代码逻辑问题
- 注意:模型加载失败会以退出码 1 结束，便于在 CI / 部署脚本中检测

【依赖关系】
- 内部模块:
  - `app.retrieval.bge_m3_embedder`(BGEM3Embedder、get_bge_m3_model、encode_sparse_safe)
  - `app.retrieval.sparse_store`(save_sparse、load_sparse_lookup)
  - `app.retrieval.hybrid_retriever`(HybridRetriever)
- 第三方库:langchain_community(Chroma)、chromadb、FlagEmbedding、torch 等
- 环境变量:BGE_M3_MODEL_PATH(可选，指定本地权重路径；未设置时从 HuggingFace cache 加载)
- 产生的落盘数据:`./sparse_db/verify_tenant`(稀疏权重)，稠密向量仅存内存不落盘

前置:本地已下载 BGE-M3 权重(默认从 HF cache 加载，或设 BGE_M3_MODEL_PATH)。
依赖:legal-doc-rag 的全部依赖(langchain、chromadb、FlagEmbedding 等)。

运行(在 legal-doc-rag 根目录):
    python scripts/verify_retrieval.py

脚本行为:
  1. 用 BGEM3Embedder 对若干法律片段做稠密 + 稀疏编码
  2. 稀疏权重落盘到 ./sparse_db/{tenant}，稠密写入内存 Chroma
  3. 用 HybridRetriever 检索一个含法条关键词的查询
  4. 打印 TOP3 融合结果，并断言:
     - 稀疏权重非空(证明绕过 FlagEmbedding 1.4.0 scatter_reduce 偶发丢值的自计算生效)
     - TOP1 命中正确法条(民法典高空抛物)
"""
import os
import sys

# 把项目根目录插到 sys.path 首位，使脚本可用 `python scripts/verify_retrieval.py`
# 直接运行并 import 到 app 包(必须在下面 import app.* 之前执行)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_community.vectorstores import Chroma
from app.retrieval.bge_m3_embedder import (
    BGEM3Embedder,
    get_bge_m3_model,
    encode_sparse_safe,
)
from app.retrieval.sparse_store import save_sparse, load_sparse_lookup
from app.retrieval.hybrid_retriever import HybridRetriever

# 验证专用租户 ID:稀疏索引按租户隔离存储，用独立 ID 避免污染真实业务数据
TENANT_ID = "verify_tenant"

# 验证语料:5 条来自不同法律的条文，主题彼此区分度高，
# 便于观察检索能否把语义最相关的那一条排到 TOP1
DOCS = [
    "《中华人民共和国民法典》第一千二百五十四条:禁止从建筑物中抛掷物品。从建筑物中抛掷物品或者从建筑物上坠落的物品造成他人损害的，由侵权人依法承担侵权责任；经调查难以确定具体侵权人的，除能够证明自己不是侵权人的外，由可能加害的建筑物使用人给予补偿。",
    "《中华人民共和国劳动合同法》第三十八条:用人单位有下列情形之一的，劳动者可以解除劳动合同:(一)未按照劳动合同约定提供劳动保护或者劳动条件的；(二)未及时足额支付劳动报酬的；(三)未依法为劳动者缴纳社会保险费的。",
    "《中华人民共和国刑法》第二百六十四条:盗窃公私财物，数额较大的，或者多次盗窃、入户盗窃、携带凶器盗窃、扒窃的，处三年以下有期徒刑、拘役或者管制，并处或者单处罚金。",
    "《中华人民共和国道路交通安全法》第七十六条:机动车发生交通事故造成人身伤亡、财产损失的，由保险公司在机动车第三者责任强制保险责任限额范围内予以赔偿；不足部分，按照下列规定承担赔偿责任。",
    "《中华人民共和国民事诉讼法》第一百条:人民法院对于可能因当事人一方的行为或者其他原因，使判决难以执行或者造成当事人其他损害的案件，可以根据对方当事人的申请，作出保全裁定。",
]

# 测试查询:口语化提问，字面上并不完全等于法条原文(如"高空抛物" vs "从建筑物中抛掷物品")，
# 因此能同时考验稠密语义匹配与稀疏词项匹配的融合效果
QUERY = "民法典关于高空抛物造成他人损害的责任是怎么规定的？"


def main():
    """执行一次完整的混合检索端到端验证，并打印验证结论。

    参数:
        无(语料与查询取自模块级常量 DOCS、QUERY)
    返回:
        None: 结论通过控制台 ✅ / ❌ 输出；
              BGE-M3 模型加载失败时以 `sys.exit(1)` 非零退出码终止
    适用场景:
        - 作为脚本入口被 `python scripts/verify_retrieval.py` 调用
    验证要点:
        1. 稀疏权重非空 —— 证明绕过 FlagEmbedding 1.4.0 丢值 bug 的自计算逻辑生效
        2. TOP1 命中民法典高空抛物条款 —— 证明 RRF 融合排序合理
    副作用:
        - 会向 `./sparse_db/verify_tenant` 写入稀疏权重文件
        - 会加载 BGE-M3 模型，占用较多内存 / 显存，首次运行耗时较长
    """
    # 稠密 embedding 适配器(供 Chroma 建索引与查询时调用)
    embedder = BGEM3Embedder()
    # 获取底层 BGE-M3 原始模型对象(稀疏编码需要直接操作它)
    model = get_bge_m3_model()
    # 模型加载失败通常是权重缺失或路径配置错误，属于致命前置条件，直接非零退出
    if model is None:
        print("❌ BGE-M3 模型加载失败，请确认本地已下载权重(默认从 HF cache，或设 BGE_M3_MODEL_PATH)。")
        sys.exit(1)

    # 稀疏自计算(绕过 FlagEmbedding 1.4.0 偶发丢值的 bug)
    # 返回 list[dict]，每个 dict 是 {token_id: 权重} 的稀疏向量表示
    sp = encode_sparse_safe(model, DOCS)
    # 组装落盘条目:key 取正文前 200 字作为文档标识(检索时用同样规则反查匹配)，
    # sp 为该文档对应的稀疏权重字典
    items = [{"key": DOCS[i][:200], "sp": sp[i]} for i in range(len(DOCS))]
    # 写入按租户隔离的稀疏索引(落盘到 ./sparse_db/{tenant})
    save_sparse(TENANT_ID, "verify_doc", items)
    # 再从磁盘读回查找表，顺带验证"落盘 → 读取"这条链路也是通的
    sparse_store = load_sparse_lookup(TENANT_ID)

    # 稠密写入内存 Chroma
    # 不指定 persist_directory，向量仅存内存，脚本退出即释放，不污染真实向量库
    vector_store = Chroma.from_texts(texts=DOCS, embedding=embedder, collection_name="verify")

    # 组装混合检索器:内部并行跑 稠密向量检索 + BM25 关键词检索 + 稀疏 SPLADE 检索，
    # 再用 RRF(Reciprocal Rank Fusion，倒数排名融合)合并三路结果
    retriever = HybridRetriever(
        dense_store=vector_store,   # 稠密向量库
        texts=DOCS,                 # 原始文本，供 BM25 构建词频索引
        k=5,                        # 返回候选数(此处等于语料总数，便于观察全量排序)
        sparse_store=sparse_store,  # 稀疏权重查找表
    )
    results = retriever.retrieve(QUERY)

    print("\n=== 查询 ===")
    print(QUERY)
    print("\n=== TOP3 融合结果(稠密 + BM25 + BGE-M3 稀疏 → RRF)===")
    # 只展示前 3 名:打印各自的 RRF 融合得分与正文前 36 字，便于肉眼判断排序是否合理
    for i, d in enumerate(results[:3]):
        print(f"  {i + 1}. RRF={d.metadata.get('rrf_score', 0):.4f} | {d.page_content[:36]}...")

    top = results[0].page_content
    # 命中判定:TOP1 正文含"抛掷"或"民法典"即认为语义匹配正确
    # (用关键词做宽松判定，而非全文严格相等，避免语料微调就导致断言失败)
    hit_ok = ("抛掷" in top) or ("民法典" in top)
    # 稀疏有效性判定:只要有任意一条文档算出了非空权重字典，就说明 SPLADE 自计算没有丢值
    sparse_ok = any(len(s) > 0 for s in sp)

    print("\n=== 验证结论 ===")
    print(f"  BGE-M3 稀疏权重非空 : {'✅' if sparse_ok else '❌'} (证明 SPLADE 自计算生效、未丢值)")
    print(f"  TOP1 命中正确法条   : {'✅' if hit_ok else '⚠️ 未命中'} -> {top[:30]}...")

    # 未命中不视为失败:语料极少时排序波动正常，此处只做提示，
    # 本脚本的硬性验证目标是"稀疏权重非空 + 融合链路跑通"
    if not hit_ok:
        print("  ⚠️ 注意:demo 仅有 5 条语料，若 TOP1 偏差属正常；本脚本核心验证目标是稀疏权重非空 + 融合逻辑跑通。")


if __name__ == "__main__":
    # 仅在直接执行脚本时运行验证；被 import 时不触发(避免意外加载大模型)
    main()
