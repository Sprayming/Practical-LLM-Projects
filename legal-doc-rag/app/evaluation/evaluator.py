# =+= NEW MODULE - Added 2026-07-14 by Codex =+=

"""
RAG 评估模块 - 基于 RAGAS 框架
评估指标: Faithfulness, AnswerRelevancy, ContextPrecision, ContextRecall
"""
import types, sys, json, os
from pathlib import Path

fake = types.ModuleType("langchain_community.chat_models.vertexai")
class FakeDummy: pass
fake.ChatVertexAI = FakeDummy
sys.modules["langchain_community.chat_models.vertexai"] = fake

from ragas.dataset_schema import SingleTurnSample, EvaluationDataset
from ragas.metrics.collections import faithfulness, answer_relevancy, context_precision, context_recall
from ragas import evaluate

TEST_QUESTIONS = [
    {"question": "建立劳动关系需要签订什么形式的合同？", "ground_truth": "应当订立书面劳动合同"},
    {"question": "已建立劳动关系但未同时订立书面合同的，应在多久内补签？", "ground_truth": "自用工之日起一个月内"},
    {"question": "什么是无固定期限劳动合同？", "ground_truth": "用人单位与劳动者约定无确定终止时间的劳动合同"},
    {"question": "劳动者在同一单位连续工作满多少年可以要求订立无固定期限合同？", "ground_truth": "连续工作满十年"},
    {"question": "连续订立两次固定期限劳动合同后续签有什么规定？", "ground_truth": "应当订立无固定期限劳动合同"},
    {"question": "经济补偿按什么标准计算？", "ground_truth": "每满一年支付一个月工资"},
]


def build_retriever(data_path):
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_chroma import Chroma
    from langchain_huggingface import HuggingFaceEmbeddings
    with open(data_path, "r", encoding="utf-8") as f:
        text = f.read()
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50, separators=["\n\n", "\n", "。", "；", "，"])
    chunks = splitter.split_text(text)
    embedder = HuggingFaceEmbeddings(model_name="shibing624/text2vec-base-chinese", cache_folder="./model_cache")
    store = Chroma.from_texts(texts=chunks, embedding=embedder)
    return store.as_retriever(search_kwargs={"k": 3})


def generate_answer(question, contexts):
    import requests
    from dotenv import load_dotenv
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if env_path.exists():
        load_dotenv(str(env_path))
    api_key = os.getenv("LLM_API_KEY", "")
    base_url = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
    ctx = "\n\n".join(contexts)
    prompt = "你是一个法律专家。只基于以下资料回答问题。资料不足时说明。\n\n资料:\n" + ctx + "\n\n问题: " + question
    try:
        resp = requests.post(base_url + "/chat/completions",
            headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
            json={"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}], "temperature": 0.1},
            timeout=30)
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"] or ""
        return "[API Error]"
    except Exception as e:
        return "[Error: " + str(e) + "]"


def run_evaluation(data_path=None):
    if data_path is None:
        data_path = str(Path(__file__).resolve().parent.parent.parent / "data" / "labor_law.txt")

    print("RAG 评估开始")
    print("数据:", data_path)
    print("问题数:", len(TEST_QUESTIONS))

    retriever = build_retriever(data_path)
    print("向量库就绪\n")

    samples = []
    for i, item in enumerate(TEST_QUESTIONS, 1):
        q = item["question"]
        print(f"[{i}] {q[:40]}...")
        docs = retriever.invoke(q)
        contexts = [d.page_content for d in docs]
        answer = generate_answer(q, contexts)
        print("  答:", answer[:100])
        samples.append(SingleTurnSample(question=q, answer=answer, contexts=contexts, ground_truth=item["ground_truth"]))

    print("\n运行 RAGAS 评估...")
    dataset = EvaluationDataset.from_list(samples)
    result = evaluate(dataset, metrics=[faithfulness, answer_relevancy, context_precision, context_recall])

    print("\n评估报告")
    for key, label in [("faithfulness", "忠实度"), ("answer_relevancy", "相关性"), ("context_precision", "精确度"), ("context_recall", "召回率")]:
        val = result.get(key, 0)
        print(f"  {label}: {float(val):.4f}" if isinstance(val, (int, float)) else f"  {label}: {val}")

    report_path = Path(__file__).resolve().parent.parent.parent / "evaluation_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({"metrics": {k: float(result[k]) if isinstance(result.get(k), (int, float)) else str(result.get(k, 0)) for k in ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]}}, f, ensure_ascii=False, indent=2)
    print(f"\n报告已保存: {report_path}")
    return result


if __name__ == "__main__":
    run_evaluation()