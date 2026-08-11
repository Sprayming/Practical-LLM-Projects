"""
RAG 评估模块 - 基于 RAGAS 框架

评估指标:
- Faithfulness (忠实度): 评估生成答案与检索到的事实是否一致
- AnswerRelevancy (相关性): 评估答案是否准确回答了用户问题
- ContextPrecision (精确度): 评估检索到的上下文是否都相关
- ContextRecall (召回率): 评估是否检索到了所有相关的上下文

该模块通过预设的法律测试问题，对 RAG 系统进行端到端的性能评估。
"""

import types, sys, json, os
from pathlib import Path

# 临时处理依赖：模拟 langchain_community.chat_models.vertexai 模块
# 避免在评估环境中安装 VertexAI 相关依赖
fake = types.ModuleType("langchain_community.chat_models.vertexai")
class FakeDummy: pass
fake.ChatVertexAI = FakeDummy
sys.modules["langchain_community.chat_models.vertexai"] = fake

# 导入 RAGAS 评估相关组件
from ragas.dataset_schema import SingleTurnSample, EvaluationDataset
from ragas.metrics.collections import faithfulness, answer_relevancy, context_precision, context_recall
from ragas import evaluate

# 预设的法律领域测试问题集（包含问题和标准答案）
TEST_QUESTIONS = [
    {"question": "建立劳动关系需要签订什么形式的合同？", "ground_truth": "应当订立书面劳动合同"},
    {"question": "已建立劳动关系但未同时订立书面合同的，应在多久内补签？", "ground_truth": "自用工之日起一个月内"},
    {"question": "什么是无固定期限劳动合同？", "ground_truth": "用人单位与劳动者约定无确定终止时间的劳动合同"},
    {"question": "劳动者在同一单位连续工作满多少年可以要求订立无固定期限合同？", "ground_truth": "连续工作满十年"},
    {"question": "连续订立两次固定期限劳动合同后续签有什么规定？", "ground_truth": "应当订立无固定期限劳动合同"},
    {"question": "经济补偿按什么标准计算？", "ground_truth": "每满一年支付一个月工资"},
]


def build_retriever(data_path):
    """
    构建文档检索器。
    
    使用 HuggingFace 的 text2vec-base-chinese 模型创建向量库，
    并配置为返回 top 3 相关文档的检索器。
    
    Args:
        data_path (str): 待索引的文本文件路径。
        
    Returns:
        VectorStoreRetriever: 配置好的检索器实例。
    """
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_chroma import Chroma
    from langchain_huggingface import HuggingFaceEmbeddings
    
    # 1. 读取并分块处理文本
    with open(data_path, "r", encoding="utf-8") as f:
        text = f.read()
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500, 
        chunk_overlap=50, 
        separators=["\n\n", "\n", "。", "；", "，"]  # 中文文本分块分隔符
    )
    chunks = splitter.split_text(text)
    
    # 2. 创建嵌入模型和向量库
    embedder = HuggingFaceEmbeddings(
        model_name="shibing624/text2vec-base-chinese", 
        cache_folder="./model_cache"  # 本地缓存模型文件
    )
    store = Chroma.from_texts(
        texts=chunks, 
        embedding=embedder
    )
    
    # 3. 返回配置好的检索器（返回 top 3 相关文档）
    return store.as_retriever(search_kwargs={"k": 3})


def generate_answer(question, contexts):
    """
    调用大语言模型生成答案。
    
    使用 DeepSeek API 基于检索到的上下文生成回答。
    
    Args:
        question (str): 用户问题。
        contexts (List[str]): 检索到的相关上下文列表。
        
    Returns:
        str: 生成的答案，如果出错则返回错误信息。
    """
    import requests
    from dotenv import load_dotenv
    
    # 加载环境变量
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if env_path.exists():
        load_dotenv(str(env_path))
    api_key = os.getenv("LLM_API_KEY", "")
    base_url = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
    
    # 构建提示词
    ctx = "\n\n".join(contexts)
    prompt = "你是一个法律专家。只基于以下资料回答问题。资料不足时说明。\n\n资料:\n" + ctx + "\n\n问题: " + question
    
    try:
        # 调用大模型 API
        resp = requests.post(
            base_url + "/chat/completions",
            headers={
                "Authorization": "Bearer " + api_key, 
                "Content-Type": "application/json"
            },
            json={
                "model": "deepseek-chat", 
                "messages": [{"role": "user", "content": prompt}], 
                "temperature": 0.1  # 设置较低温度以获得更确定性的输出
            },
            timeout=30
        )
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"] or ""
        return "[API Error]"
    except Exception as e:
        return "[Error: " + str(e) + "]"


def run_evaluation(data_path=None):
    """
    执行完整的 RAG 评估流程。
    
    主要步骤：
    1. 构建检索器
    2. 对每个测试问题：
       - 检索相关上下文
       - 生成答案
       - 构建评估样本
    3. 使用 RAGAS 框架进行评估
    4. 输出评估结果并保存报告
    
    Args:
        data_path (str, optional): 待评估的文本文件路径。如果未提供，使用默认的法律文本。
        
    Returns:
        dict: RAGAS 评估结果字典，包含各项指标的分数。
    """
    # 1. 准备评估数据
    if data_path is None:
        data_path = str(Path(__file__).resolve().parent.parent.parent / "data" / "labor_law.txt")

    print("RAG 评估开始")
    print("数据:", data_path)
    print("问题数:", len(TEST_QUESTIONS))

    # 2. 构建检索器
    retriever = build_retriever(data_path)
    print("向量库就绪\n")

    # 3. 处理每个测试问题
    samples = []
    for i, item in enumerate(TEST_QUESTIONS, 1):
        q = item["question"]
        print(f"[{i}] {q[:40]}...")  # 只显示问题前40个字符
        
        # 检索相关文档
        docs = retriever.invoke(q)
        contexts = [d.page_content for d in docs]
        
        # 生成答案
        answer = generate_answer(q, contexts)
        print("  答:", answer[:100])  # 只显示答案前100个字符
        
        # 构建评估样本
        samples.append(SingleTurnSample(
            question=q,
            answer=answer,
            contexts=contexts,
            ground_truth=item["ground_truth"]
        ))

    # 4. 运行 RAGAS 评估
    print("\n运行 RAGAS 评估...")
    dataset = EvaluationDataset.from_list(samples)
    result = evaluate(
        dataset, 
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall]
    )

    # 5. 输出评估结果
    print("\n评估报告")
    for key, label in [
        ("faithfulness", "忠实度"), 
        ("answer_relevancy", "相关性"), 
        ("context_precision", "精确度"), 
        ("context_recall", "召回率")
    ]:
        val = result.get(key, 0)
        # 根据值的类型输出不同格式的结果
        print(f"  {label}: {float(val):.4f}" if isinstance(val, (int, float)) else f"  {label}: {val}")

    # 6. 保存评估报告
    report_path = Path(__file__).resolve().parent.parent.parent / "evaluation_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        # 将数值类型转换为 float 以便 JSON 序列化
        json.dump(
            {
                "metrics": {
                    k: float(result[k]) if isinstance(result.get(k), (int, float)) else str(result.get(k, 0)) 
                    for k in ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]
                }
            },
            f,
            ensure_ascii=False,
            indent=2
        )
    print(f"\n报告已保存: {report_path}")
    return result


# 主程序入口
if __name__ == "__main__":
    run_evaluation()
