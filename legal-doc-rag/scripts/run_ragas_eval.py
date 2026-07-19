# -*- coding: utf-8 -*-
import os, ssl
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
ssl._create_default_https_context = ssl._create_unverified_context
import json, sys, requests
from pathlib import Path
from dotenv import load_dotenv
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ragas import evaluate
from ragas.dataset_schema import EvaluationDataset
from ragas.metrics import Faithfulness, AnswerRelevancy, ContextPrecision, ContextRecall

env_path = Path(__file__).resolve().parent.parent / '.env'
if env_path.exists(): load_dotenv(str(env_path))
API_KEY = os.getenv('LLM_API_KEY', '')
BASE_URL = os.getenv('LLM_BASE_URL', 'https://api.deepseek.com/v1')
ARK_API_KEY = 'df9c9b2d-35d9-4df6-b49d-f489708e1eab'
ARK_BASE_URL = 'https://ark.cn-beijing.volces.com/api/v3/'
ARK_LLM_MODEL = 'doubao-1-5-pro-32k-250115'
ARK_EMBEDDING_ENDPOINT = 'ep-m-20251117205847-trwgz'
os.environ['OPENAI_API_KEY'] = ARK_API_KEY
os.environ['OPENAI_BASE_URL'] = ARK_BASE_URL

TEST_QUESTIONS = [
  {
    "question": "建立劳动关系需要签订什么形式的合同？",
    "contexts": [
      "《劳动合同法》第十条规定：建立劳动关系，应当订立书面劳动合同。"
    ],
    "ground_truth": "应当订立书面劳动合同。"
  },
  {
    "question": "已建立劳动关系但未同时订立书面合同的，应在多久内补签？",
    "contexts": [
      "《劳动合同法》第十条：应当自用工之日起一个月内订立书面劳动合同。"
    ],
    "ground_truth": "自用工之日起一个月内。"
  },
  {
    "question": "什么是无固定期限劳动合同？",
    "contexts": [
      "《劳动合同法》第十四条：无固定期限劳动合同，是指用人单位与劳动者约定无确定终止时间的劳动合同。"
    ],
    "ground_truth": "无确定终止时间的劳动合同。"
  },
  {
    "question": "劳动者在同一单位连续工作满多少年可以要求订立无固定期限合同？",
    "contexts": [
      "《劳动合同法》第十四条：劳动者在该用人单位连续工作满十年的，应当订立无固定期限劳动合同。"
    ],
    "ground_truth": "连续工作满十年。"
  },
  {
    "question": "连续订立两次固定期限劳动合同后续签有什么规定？",
    "contexts": [
      "《劳动合同法》第十四条：连续订立二次固定期限劳动合同，续订的应当订立无固定期限劳动合同。"
    ],
    "ground_truth": "应当订立无固定期限劳动合同。"
  },
  {
    "question": "经济补偿按什么标准计算？",
    "contexts": [
      "《劳动合同法》第四十七条：经济补偿按劳动者在本单位工作的年限，每满一年支付一个月工资。"
    ],
    "ground_truth": "每满一年支付一个月工资。"
  }
]

def call_llm(prompt, timeout=30):
  if not API_KEY: return ''
  try:
    r = requests.post(f'{BASE_URL}/chat/completions',
      headers={'Authorization': f'Bearer {API_KEY}', 'Content-Type': 'application/json'},
      json={'model': 'deepseek-chat', 'messages': [{'role': 'user', 'content': prompt}], 'temperature': 0.1},
      timeout=timeout, verify=False)
    if r.status_code == 200:
      d = r.json()
      if isinstance(d, dict) and d.get('choices') and d['choices'][0].get('message'):
        return d['choices'][0]['message']['content'] or ''
    return ''
  except: return ''

def generate_answer(q, ctxs):
  if not ctxs: return 'No context.'
  return call_llm('You are a legal expert. Answer based on:\n\n' + chr(10).join(ctxs[:3]) + '\n\nQuestion: ' + q)

def run_eval():
  if not API_KEY: print('WARNING: LLM_API_KEY not set'); return
  s = []
  print(f'Evaluating {len(TEST_QUESTIONS)} questions...')
  for i, item in enumerate(TEST_QUESTIONS, 1):
    q = item['question']; ctx = item.get('contexts', []); gt = item.get('ground_truth', '')
    print(f'  [{i}] {q[:40]}...')
    a = generate_answer(q, ctx)
    if a: print(f'    {a[:60]}...')
    s.append({'user_input': q, 'response': a, 'retrieved_contexts': ctx, 'reference': gt})
  print(chr(10) + 'Running RAGAS...')
  ds = EvaluationDataset.from_list(s)
  from langchain_openai import ChatOpenAI
  from ragas.llms import LangchainLLMWrapper
  from openai import OpenAI
  ragas_llm = LangchainLLMWrapper(ChatOpenAI(model=ARK_LLM_MODEL, openai_api_key=ARK_API_KEY, openai_api_base=ARK_BASE_URL, temperature=0.1))
  _oc = OpenAI(api_key=ARK_API_KEY, base_url=ARK_BASE_URL)
  class _DirectEmbed:
    def embed_documents(self, texts):
      resp = _oc.embeddings.create(input=texts, model=ARK_EMBEDDING_ENDPOINT)
      return [d.embedding for d in resp.data]
    def embed_query(self, text):
      resp = _oc.embeddings.create(input=text, model=ARK_EMBEDDING_ENDPOINT)
      return resp.data[0].embedding
    def embed_text(self, text):
      return self.embed_query(text)
    def embed_texts(self, texts):
      return self.embed_documents(texts)
  ragas_emb = _DirectEmbed()
  r = evaluate(ds, metrics=[Faithfulness(llm=ragas_llm), AnswerRelevancy(llm=ragas_llm, embeddings=ragas_emb), ContextPrecision(llm=ragas_llm), ContextRecall(llm=ragas_llm)], embeddings=ragas_emb)
  print("DEB: mro=" + str([c.__name__ for c in type(r).__mro__]))
  d = r.data if hasattr(r, 'data') else {}
  print("DEB: data=" + str(d))
  print(chr(10) + '=== Report ===')
  for k, l in {'faithfulness': 'Faithfulness', 'answer_relevancy': 'Relevancy', 'context_precision': 'Precision', 'context_recall': 'Recall'}.items():
    v = r[k] if isinstance(r, dict) else getattr(r, k, 0)
    print(f'  {l}: {float(v):.4f}' if isinstance(v, (int, float)) else f'  {l}: {v}')
  with open(Path(__file__).resolve().parent.parent / 'evaluation_report.json', 'w', encoding='utf-8') as fo:
    if hasattr(r, 'scores') and r.scores:
      avg = {}
      for key in ['faithfulness', 'answer_relevancy', 'context_precision', 'context_recall']:
        vals = [sc.get(key, 0) for sc in r.scores if isinstance(sc, dict)]
        avg[key] = sum(vals) / len(vals) if vals else 0.0
    else:
      avg = {k: 0.0 for k in ['faithfulness', 'answer_relevancy', 'context_precision', 'context_recall']}
    json.dump({'metrics': avg, 'total': len(s)}, fo, ensure_ascii=False, indent=2)
  print('Saved: evaluation_report.json')

if __name__ == '__main__': run_eval()
