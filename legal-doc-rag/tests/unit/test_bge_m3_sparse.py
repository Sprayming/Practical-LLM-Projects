"""
BGE-M3 稀疏向量（SPLADE）自计算逻辑的单元测试。

不依赖真实 2.3GB 权重 / 网络：用轻量 mock 模拟 BGEM3FlagModel 的真实属性结构
（model.model=编码器, model.model.sparse_linear=投影, model.tokenizer=分词器），
验证 encode_sparse_direct 的「非空 / 确定性 / 形状正确 / 特殊 token 过滤」等关键性质。

这些性质正是修复前 FlagEmbedding 1.4.0 scatter_reduce 路径偶发丢值的回归护栏。
"""
import torch
import torch.nn as nn
import pytest

from app.retrieval.bge_m3_embedder import encode_sparse_direct, _unused_token_ids


VOCAB = 32


class FakeTokenizer:
    special_tokens_map = {
        "cls_token": "[CLS]", "eos_token": "</s>",
        "pad_token": "<pad>", "unk_token": "<unk>",
    }
    _ids = {"[CLS]": 0, "</s>": 1, "<pad>": 2, "<unk>": 3}

    def convert_tokens_to_ids(self, t):
        return self._ids.get(t, 0)

    def __call__(self, texts, padding=False, truncation=False, max_length=512, return_tensors=None):
        ids, masks = [], []
        for t in texts:
            seq = [ord(c) % (VOCAB - 4) + 4 for c in t]  # 映射到 4..VOCAB-1，避开 0-3 特殊符
            ids.append(seq)
            masks.append([1] * len(seq))
        L = max(len(x) for x in ids)
        for i in range(len(texts)):
            ids[i] += [2] * (L - len(ids[i]))
            masks[i] += [0] * (L - len(masks[i]))
        return {"input_ids": torch.tensor(ids), "attention_mask": torch.tensor(masks)}


HIDDEN = 8  # 模拟编码器隐藏维度（真实 BGE-M3 为 1024）


class FakeTransformer(nn.Module):
    def __init__(self):
        super().__init__()
        self.config = type("C", (), {"vocab_size": VOCAB})()

    def forward(self, input_ids=None, attention_mask=None, **kw):
        B, S = input_ids.shape
        # 每个位置都给一个正值的隐藏向量 -> 经稀疏头（Linear(H,1)）后门控权重为正，
        # 等价于真实 BGE-M3 逐位置标量门控。权重与 token 无关，便于断言非空/确定性。
        h = torch.full((B, S, HIDDEN), 1.5)
        return type("O", (), {"last_hidden_state": h})()


class FakeInner(nn.Module):
    def __init__(self):
        super().__init__()
        self.model = FakeTransformer()
        # BGE-M3 真实稀疏头：Linear(HIDDEN -> 1) 逐位置标量门控（不是投影到词表维度）
        self.sparse_linear = nn.Linear(HIDDEN, 1, bias=False)
        with torch.no_grad():
            nn.init.ones_(self.sparse_linear.weight)  # 门控恒为正
        self.training = False

    def eval(self):
        super().eval()
        self.model.eval()
        return self


class FakeBGEM3FlagModel:
    def __init__(self):
        self.model = FakeInner()
        self.tokenizer = FakeTokenizer()


@pytest.fixture
def fake_model():
    return FakeBGEM3FlagModel()


def test_non_empty_output(fake_model):
    """修复前 scatter_reduce 偶发整条稀疏为空——这里必须稳定非空。"""
    texts = ["劳动合同解除", "违约金 定金"]
    res = encode_sparse_direct(fake_model, texts)
    assert len(res) == 2
    for i, d in enumerate(res):
        assert d, f"第 {i} 条稀疏结果为空（原 bug 表现）"
    # 每个真实 token 都应进入词典且权重为正
    for d in res:
        assert all(w > 0 for w in d.values())


def test_deterministic(fake_model):
    """同输入两次编码结果必须完全一致（确定性 gather，无偶发丢值）。"""
    texts = ["劳动合同解除", "违约金 定金"]
    assert encode_sparse_direct(fake_model, texts) == encode_sparse_direct(fake_model, texts)


def test_single_text_stable(fake_model):
    """单条编码也能稳定产出非空结果（原 retry 逻辑要解决的场景）。"""
    res = encode_sparse_direct(fake_model, ["单独一条查询文本"])
    assert res and res[0]


def test_special_tokens_filtered(fake_model):
    """特殊 token（cls/eos/pad/unk）不应进入稀疏词典。"""
    unused = _unused_token_ids(fake_model.tokenizer)
    res = encode_sparse_direct(fake_model, ["劳动合同解除"])
    for tid in res[0]:
        assert int(tid) not in unused, f"特殊 token {tid} 不应进入稀疏词典"


def test_empty_input_safe(fake_model):
    """空输入安全返回空列表。"""
    assert encode_sparse_direct(fake_model, []) == []


def test_batch_consistency(fake_model):
    """批量编码与逐条编码结果一致（验证 batch 路径无形状/对齐问题）。"""
    texts = ["股权转让", "知识产权侵权赔偿", "公司章程 股东会决议"]
    batched = encode_sparse_direct(fake_model, texts)
    for i, t in enumerate(texts):
        single = encode_sparse_direct(fake_model, [t])[0]
        assert single == batched[i], f"批量与单条第 {i} 条结果不一致"
