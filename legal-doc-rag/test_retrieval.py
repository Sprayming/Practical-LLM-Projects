import sys
sys.path.insert(0, "D:/git/legal-doc-rag")

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

# 加载数据
with open("D:/git/legal-doc-rag/data/labor_law.txt", "r", encoding="utf-8") as f:
    text = f.read()

# 分块
splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50, separators=["\n\n", "\n", "\u3002", "\uff1b", "\uff0c"])
chunks = splitter.split_text(text)

# 稠密索引
embedder = HuggingFaceEmbeddings(model_name="shibing624/text2vec-base-chinese", cache_folder="./model_cache")
store = Chroma.from_texts(texts=chunks, embedding=embedder)

# 混合检索
from app.retrieval.hybrid_retriever import HybridRetriever
retriever = HybridRetriever(store, chunks, k=5)

# 查询
results = retriever.retrieve("订立书面劳动合同")
print(f"混合检索结果: {len(results)} 条")
for r in results:
    score = r.metadata.get("rrf_score", 0)
    text_preview = r.page_content[:80]
    print(f"  RRF={score:.4f} | {text_preview}...")
