# -*- coding: utf-8 -*-
"""run_ragas_eval.py —— 基于 RAGAS 的 RAG 问答质量评测脚本(自带黄金测试集)。

【作用与功能】
本脚本是项目"评测测试"层的独立可执行入口，回答的不是"代码对不对"，
而是"回答好不好"。完整流程:
1. 使用内置的 6 条劳动合同法黄金问答样本(问题 + 标准上下文 + 参考答案)；
2. 逐条把「上下文 + 问题」拼成 prompt 调用 DeepSeek 生成答案；
3. 把 (问题, 生成答案, 检索上下文, 参考答案) 组装成 RAGAS 评测数据集；
4. 用豆包(火山方舟 ARK)作为裁判 LLM + embedding，计算四个指标:
   Faithfulness(忠实度)、AnswerRelevancy(答案相关性)、
   ContextPrecision(上下文精度)、ContextRecall(上下文召回)；
5. 打印报告并把平均分写入项目根目录的 `evaluation_report.json`。

注意本脚本刻意使用了"双模型"设计:被测答案由 DeepSeek 生成，
评分裁判由豆包担任，避免"自己给自己打分"带来的偏袒。

【主要组成】
- `TEST_QUESTIONS`:内置黄金测试集，6 条《劳动合同法》问答样本
- `call_llm`:调用 DeepSeek Chat Completions 接口，返回纯文本答案
- `generate_answer`:把上下文与问题拼成法律专家 prompt，产出被测答案
- `run_eval`:主流程——生成答案、构造 RAGAS 数据集、计算指标、落盘报告
- `_DirectEmbed`(run_eval 内部类):直连 ARK embedding 接口的适配器，
  实现 RAGAS 所需的 embed_documents / embed_query / embed_text / embed_texts 四个方法

【适用场景】
- 场景1:常规质量回归 —— `python scripts/run_ragas_eval.py`
- 场景2:改动检索策略 / prompt 后，对比 evaluation_report.json 的指标涨跌
- 场景3:作为 CI 的质量门禁(可读取报告 JSON 判断是否低于阈值)
- 注意:会真实调用外部大模型接口，**产生 token 费用**，不适合高频执行

【依赖关系】
- 第三方库:requests、python-dotenv、ragas、langchain-openai、openai
  (ragas 一族依赖较重，已在 `run_eval` 内部惰性导入，保证本模块在缺少 ragas 时仍可被 import)
- 环境变量:LLM_API_KEY(被测模型 DeepSeek 的密钥，来自 .env)、
  LLM_BASE_URL(DeepSeek 接口地址)、ARK_API_KEY(裁判模型豆包的密钥)
- 外部服务:DeepSeek OpenAPI、火山方舟 ARK(LLM + embedding)、
  HuggingFace 镜像站(供 ragas 内部可能的模型下载走国内加速)
- 输出产物:`<项目根>/evaluation_report.json`
"""
import os
# 必须在 import 任何会触碰 HuggingFace 的库之前设置镜像端点，
# 否则 hf 客户端已按默认域名初始化，国内环境容易下载超时
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
import json, sys, requests
from pathlib import Path
from dotenv import load_dotenv
# 把项目根目录加入 sys.path，便于脚本直接运行时 import 项目内模块
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 加载项目根目录 .env(不存在则沿用系统环境变量与下面的默认值)
env_path = Path(__file__).resolve().parent.parent / '.env'
if env_path.exists(): load_dotenv(str(env_path))

# ---- 被测模型(生成答案):DeepSeek ----
API_KEY = os.getenv('LLM_API_KEY', '')                                    # DeepSeek 密钥，缺失则跳过评测
BASE_URL = os.getenv('LLM_BASE_URL', 'https://api.deepseek.com/v1')       # DeepSeek 接口根地址

# ---- 裁判模型(打分):火山方舟 ARK / 豆包 ----
ARK_API_KEY = os.getenv('ARK_API_KEY', '')                                # ARK 密钥
ARK_BASE_URL = 'https://ark.cn-beijing.volces.com/api/v3/'                # ARK OpenAI 兼容接口地址
ARK_LLM_MODEL = 'doubao-1-5-pro-32k-250115'                               # 裁判 LLM 模型名
ARK_EMBEDDING_ENDPOINT = 'ep-m-20251117205847-trwgz'                      # ARK embedding 推理接入点 ID

# RAGAS 内部通过 OpenAI 兼容协议访问模型，这里把 OPENAI_* 指向 ARK，
# 让"打分"这一侧统一走豆包，与上面生成答案用的 DeepSeek 相互独立
os.environ['OPENAI_API_KEY'] = ARK_API_KEY
os.environ['OPENAI_BASE_URL'] = ARK_BASE_URL

# 黄金测试集(Golden Set):人工整理的《劳动合同法》问答样本。
# 每条包含三部分:
#   question     —— 用户提问
#   contexts     —— 标准检索上下文(此处直接给定法条原文，用于隔离检索环节、只评测生成质量)
#   ground_truth —— 参考标准答案，供 ContextRecall 等指标做比对
TEST_QUESTIONS = [
  {
    "question": "建立劳动关系需要签订什么形式的合同？",
    "contexts": [
      "《劳动合同法》第十条规定:建立劳动关系，应当订立书面劳动合同。"
    ],
    "ground_truth": "应当订立书面劳动合同。"
  },
  {
    "question": "已建立劳动关系但未同时订立书面合同的，应在多久内补签？",
    "contexts": [
      "《劳动合同法》第十条:应当自用工之日起一个月内订立书面劳动合同。"
    ],
    "ground_truth": "自用工之日起一个月内。"
  },
  {
    "question": "什么是无固定期限劳动合同？",
    "contexts": [
      "《劳动合同法》第十四条:无固定期限劳动合同，是指用人单位与劳动者约定无确定终止时间的劳动合同。"
    ],
    "ground_truth": "无确定终止时间的劳动合同。"
  },
  {
    "question": "劳动者在同一单位连续工作满多少年可以要求订立无固定期限合同？",
    "contexts": [
      "《劳动合同法》第十四条:劳动者在该用人单位连续工作满十年的，应当订立无固定期限劳动合同。"
    ],
    "ground_truth": "连续工作满十年。"
  },
  {
    "question": "连续订立两次固定期限劳动合同后续签有什么规定？",
    "contexts": [
      "《劳动合同法》第十四条:连续订立二次固定期限劳动合同，续订的应当订立无固定期限劳动合同。"
    ],
    "ground_truth": "应当订立无固定期限劳动合同。"
  },
  {
    "question": "经济补偿按什么标准计算？",
    "contexts": [
      "《劳动合同法》第四十七条:经济补偿按劳动者在本单位工作的年限，每满一年支付一个月工资。"
    ],
    "ground_truth": "每满一年支付一个月工资。"
  }
]

def call_llm(prompt, timeout=30):
  """调用 DeepSeek Chat Completions 接口，返回模型输出的纯文本。

  参数:
      prompt (str): 完整的用户提示词
      timeout (int): 单次 HTTP 请求超时秒数，默认 30
  返回:
      str: 模型回答文本；任何异常、非 200 状态码或响应结构不符合预期时统一返回空字符串
  适用场景:
      - 被 `generate_answer` 调用，为黄金测试集中的每个问题生成被测答案
  说明:
      - 采用"失败即返回空串"的容错策略:评测批量跑多条样本，
        单条网络抖动不应中断整轮评测，空答案会在后续指标中体现为低分
  """
  # 未配置密钥时直接返回空串，避免发出必然失败的请求
  if not API_KEY: return ''
  try:
    r = requests.post(f'{BASE_URL}/chat/completions',
      headers={'Authorization': f'Bearer {API_KEY}', 'Content-Type': 'application/json'},
      # temperature=0.1:评测场景需要尽可能稳定可复现的输出，故取接近确定性的低温度
      json={'model': 'deepseek-chat', 'messages': [{'role': 'user', 'content': prompt}], 'temperature': 0.1},
      timeout=timeout, verify=True)
    if r.status_code == 200:
      d = r.json()
      # 逐层防御式取值:确保是 dict、choices 非空、且首个 choice 带 message，
      # 避免接口返回错误结构时抛 KeyError / IndexError
      if isinstance(d, dict) and d.get('choices') and d['choices'][0].get('message'):
        return d['choices'][0]['message']['content'] or ''
    return ''
  except: return ''  # 网络异常、JSON 解析失败等一律降级为空答案

def generate_answer(q, ctxs):
  """把检索上下文与问题拼成"法律专家"提示词，调用 LLM 生成被测答案。

  参数:
      q (str): 用户问题
      ctxs (list[str]): 检索到的上下文片段列表(法条原文)
  返回:
      str: 生成的答案文本；上下文为空时返回固定串 'No context.'
  适用场景:
      - 在 `run_eval` 中逐条为黄金测试集生成待评分的答案
  说明:
      - 只取前 3 条上下文(ctxs[:3])，控制 prompt 长度与 token 成本；
      - chr(10) 即换行符 "\\n"，此处用 chr(10) 是为规避字符串内嵌转义带来的书写歧义
  """
  # 无上下文时不必浪费一次 LLM 调用，直接给出可识别的占位答案
  if not ctxs: return 'No context.'
  # 提示词结构:角色设定 + 上下文(最多 3 条，换行拼接) + 问题
  return call_llm('You are a legal expert. Answer based on:\n\n' + chr(10).join(ctxs[:3]) + '\n\nQuestion: ' + q)

def run_eval():
  """评测主流程:生成答案 → 构造 RAGAS 数据集 → 计算四项指标 → 打印并落盘报告。

  参数:
      无(数据来自模块级 TEST_QUESTIONS，配置来自模块级环境变量)
  返回:
      None: 结果通过控制台输出和 `evaluation_report.json` 文件呈现；
            未配置 LLM_API_KEY 时打印警告后提前 return
  适用场景:
      - 脚本直接运行时的唯一入口:`python scripts/run_ragas_eval.py`
      - 也可在 Python 交互环境中 `from scripts.run_ragas_eval import run_eval` 手动触发
  副作用:
      - 会真实调用 DeepSeek 与 ARK 接口，产生 token 费用
      - 会覆盖写入项目根目录的 `evaluation_report.json`
  """
  # ragas 相关依赖较重且在无 GPU/网络环境下非必需，改为函数内惰性导入，
  # 这样本模块在无 ragas 时也能被 import(供离线测试 / CI 使用)。
  from ragas import evaluate
  from ragas.dataset_schema import EvaluationDataset
  from ragas.metrics import Faithfulness, AnswerRelevancy, ContextPrecision, ContextRecall

  # 没有被测模型密钥就无法生成答案，评测无意义，直接告警退出
  if not API_KEY: print('WARNING: LLM_API_KEY not set'); return
  s = []  # 评测样本列表，字段名需严格匹配 RAGAS 的 EvaluationDataset 约定
  print(f'Evaluating {len(TEST_QUESTIONS)} questions...')
  # ---- 第一阶段:逐条生成被测答案 ----
  for i, item in enumerate(TEST_QUESTIONS, 1):
    q = item['question']; ctx = item.get('contexts', []); gt = item.get('ground_truth', '')
    print(f'  [{i}] {q[:40]}...')  # 只截前 40 字做进度提示，避免刷屏
    a = generate_answer(q, ctx)
    if a: print(f'    {a[:60]}...')
    # RAGAS 字段语义:user_input=问题，response=被测答案，
    # retrieved_contexts=检索上下文，reference=标准答案
    s.append({'user_input': q, 'response': a, 'retrieved_contexts': ctx, 'reference': gt})
  print(chr(10) + 'Running RAGAS...')
  # ---- 第二阶段:构造 RAGAS 数据集与裁判模型 ----
  ds = EvaluationDataset.from_list(s)
  from langchain_openai import ChatOpenAI
  from ragas.llms import LangchainLLMWrapper
  from openai import OpenAI
  # 裁判 LLM:豆包，经 LangchainLLMWrapper 适配成 RAGAS 可用的 LLM 接口；
  # 同样用低温度 0.1 保证打分尽量稳定可复现
  ragas_llm = LangchainLLMWrapper(ChatOpenAI(model=ARK_LLM_MODEL, openai_api_key=ARK_API_KEY, openai_api_base=ARK_BASE_URL, temperature=0.1))
  # 原生 OpenAI 客户端，指向 ARK，专门用于调用 embedding 接口
  _oc = OpenAI(api_key=ARK_API_KEY, base_url=ARK_BASE_URL)
  class _DirectEmbed:
    """直连 ARK embedding 接口的极简适配器(RAGAS embedding 协议实现)。

    之所以自己写而不用 langchain 的 OpenAIEmbeddings:
    ARK 的 embedding 需要传"推理接入点 ID"而非常规模型名，
    且不同版本的 RAGAS / langchain 会调用四种不同的方法名，
    这里一次性把四个方法都实现，屏蔽版本差异。

    适用场景:
        - 作为 `evaluate(..., embeddings=...)` 的实参，供 AnswerRelevancy 等
          需要向量相似度的指标使用
    """
    def embed_documents(self, texts):
      """批量把文本编码为向量(langchain 风格接口)。

      参数:
          texts (list[str]): 待编码的文本列表
      返回:
          list[list[float]]: 与输入顺序一致的向量列表
      """
      resp = _oc.embeddings.create(input=texts, model=ARK_EMBEDDING_ENDPOINT)
      return [d.embedding for d in resp.data]
    def embed_query(self, text):
      """把单条查询文本编码为向量。

      参数:
          text (str): 待编码文本
      返回:
          list[float]: 该文本对应的向量
      """
      resp = _oc.embeddings.create(input=text, model=ARK_EMBEDDING_ENDPOINT)
      return resp.data[0].embedding
    def embed_text(self, text):
      """`embed_query` 的别名，兼容部分 RAGAS 版本使用的方法名。

      参数:
          text (str): 待编码文本
      返回:
          list[float]: 该文本对应的向量
      """
      return self.embed_query(text)
    def embed_texts(self, texts):
      """`embed_documents` 的别名，兼容部分 RAGAS 版本使用的方法名。

      参数:
          texts (list[str]): 待编码的文本列表
      返回:
          list[list[float]]: 与输入顺序一致的向量列表
      """
      return self.embed_documents(texts)
  ragas_emb = _DirectEmbed()
  # ---- 第三阶段:执行评测 ----
  # 四个指标含义:
  #   Faithfulness     忠实度   —— 答案是否严格基于上下文，专门拦"编造法条"
  #   AnswerRelevancy  相关性   —— 答案是否切题(需要 embedding 算语义相似度)
  #   ContextPrecision 上下文精度 —— 检索内容中相关比例高不高(噪声少)
  #   ContextRecall    上下文召回 —— 相关内容是否找全(漏检少)
  r = evaluate(ds, metrics=[Faithfulness(llm=ragas_llm), AnswerRelevancy(llm=ragas_llm, embeddings=ragas_emb), ContextPrecision(llm=ragas_llm), ContextRecall(llm=ragas_llm)], embeddings=ragas_emb)
  # 以下两行 DEB 为调试输出:不同 RAGAS 版本返回对象结构差异较大，
  # 打印类继承链(mro)与 data 属性便于定位取值方式
  print("DEB: mro=" + str([c.__name__ for c in type(r).__mro__]))
  d = r.data if hasattr(r, 'data') else {}
  print("DEB: data=" + str(d))
  # ---- 第四阶段:打印可读报告 ----
  print(chr(10) + '=== Report ===')
  # 键为 RAGAS 内部指标名，值为报告中展示的简短标签
  for k, l in {'faithfulness': 'Faithfulness', 'answer_relevancy': 'Relevancy', 'context_precision': 'Precision', 'context_recall': 'Recall'}.items():
    # 兼容两种返回形态:dict(按键取)与结果对象(按属性取，缺失则为 0)
    v = r[k] if isinstance(r, dict) else getattr(r, k, 0)
    # 数值统一格式化为 4 位小数；非数值(如 nan、字符串)则原样打印
    print(f'  {l}: {float(v):.4f}' if isinstance(v, (int, float)) else f'  {l}: {v}')
  # ---- 第五阶段:把平均分落盘为 JSON 报告，便于 CI 比对或趋势跟踪 ----
  with open(Path(__file__).resolve().parent.parent / 'evaluation_report.json', 'w', encoding='utf-8') as fo:
    if hasattr(r, 'scores') and r.scores:
      # r.scores 是"每条样本一个 dict"的逐条明细，这里手工按指标求算术平均
      avg = {}
      for key in ['faithfulness', 'answer_relevancy', 'context_precision', 'context_recall']:
        vals = [sc.get(key, 0) for sc in r.scores if isinstance(sc, dict)]
        avg[key] = sum(vals) / len(vals) if vals else 0.0  # 无有效样本时记 0，避免除零
    else:
      # 拿不到逐条明细(版本不兼容或评测异常)时，写入全 0 占位，保证报告结构稳定
      avg = {k: 0.0 for k in ['faithfulness', 'answer_relevancy', 'context_precision', 'context_recall']}
    # total 记录本轮评测的样本总数，便于判断报告的统计可信度
    json.dump({'metrics': avg, 'total': len(s)}, fo, ensure_ascii=False, indent=2)
  print('Saved: evaluation_report.json')

# 仅在作为脚本直接执行时运行评测；被 import 时不触发(避免误产生 token 费用)
if __name__ == '__main__': run_eval()
