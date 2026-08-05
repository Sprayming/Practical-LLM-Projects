# -*- coding: utf-8 -*-
"""把三张测试概念图重绘为 PNG，并以 base64 内联进 README.md。"""
import base64
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Noto Sans SC", "sans-serif"]
plt.rcParams["axes.unicode_minus"] = False

IMG_DIR = r"D:\git\legal-doc-rag\docs\images"
READ_ME = r"D:\git\legal-doc-rag\README.md"

C = {
    "green": ("#639922", "#EAF3DE", "#27500A", "#3B6D11"),
    "orange": ("#BA7517", "#FAEEDA", "#633806", "#854F0B"),
    "blue": ("#185FA5", "#E6F1FB", "#0C447C", "#185FA5"),
    "gray": ("#5F5E5A", "#F1EFE8", "#444441", "#444441"),
}


def box(ax, x, y, w, h, edge, face, bar=None):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
                 boxstyle="round,pad=0.004,rounding_size=0.012",
                 linewidth=0.9, edgecolor=edge, facecolor=face))
    if bar is not None:
        ax.add_patch(FancyBboxPatch((x, y), 0.018, h,
                     boxstyle="round,pad=0.0,rounding_size=0.006",
                     linewidth=0, facecolor=bar))


def arrow(ax, x1, y1, x2, y2, color="#9AA0A6"):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="-|>", color=color, lw=1.3))


# ---------- 图1：测试分层全景 ----------
def fig_landscape():
    fig, ax = plt.subplots(figsize=(8.2, 4.7))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    ax.text(0.05, 0.965, "测试分层全景：从代码单元到问答质量",
            fontsize=13, fontweight="bold", color="#0C447C", va="top")
    cards = [
        ("green", "① 单元测试 · 已实现", "测单个函数是否正确：config 解析、检索打分、记忆存取"),
        ("orange", "② 集成测试 · 已实现", "多个真实组件接线跑通：API 路由 → 检索 → 向量库 → LLM"),
        ("blue", "③ 评测测试 · 已实现", "不问代码对错，问回答好坏：用 RAGAS 给忠实度/相关性打分 0~1"),
        ("gray", "④ 端到端 E2E · 可选", "从前端或脚本发真实请求跑完整流程，最慢最脆弱，少量关键路径才写"),
    ]
    x, w, h, gap = 0.05, 0.90, 0.155, 0.025
    y = 0.80
    for key, title, sub in cards:
        edge, face, tc, sc = C[key]
        box(ax, x, y, w, h, edge, face, bar=edge)
        ax.text(x + 0.035, y + h * 0.66, title, fontsize=12, fontweight="bold", color=tc, va="center")
        ax.text(x + 0.035, y + h * 0.30, sub, fontsize=9.5, color=sc, va="center")
        y -= (h + gap)
    fig.tight_layout()
    return fig


# ---------- 图2：集成测试范围 ----------
def fig_integration():
    fig, ax = plt.subplots(figsize=(8.4, 5.0))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    ax.text(0.05, 0.965, "集成测试范围：真实接线，只 mock 外部 LLM",
            fontsize=13, fontweight="bold", color="#0C447C", va="top")
    # 顶部链路
    top = [("TestClient", "#5F5E5A", "#F1EFE8"),
           ("API 路由\n/api/chat", "#185FA5", "#E6F1FB"),
           ("JWT 鉴权", "#185FA5", "#E6F1FB"),
           ("业务编排\nchat.py", "#185FA5", "#E6F1FB")]
    tw, th, ty = 0.205, 0.13, 0.70
    xs = [0.04, 0.285, 0.53, 0.775]
    for i, (lab, e, f) in enumerate(top):
        box(ax, xs[i], ty, tw, th, e, f)
        ax.text(xs[i] + tw / 2, ty + th / 2, lab, fontsize=10, fontweight="bold",
                color=e, ha="center", va="center")
        if i < len(top) - 1:
            arrow(ax, xs[i] + tw, ty + th / 2, xs[i + 1], ty + th / 2)
    # 下方三个组件
    bot = [("混合检索\nBM25+Dense+RRF", "#BA7517", "#FAEEDA"),
           ("Chroma\n向量库", "#BA7517", "#FAEEDA"),
           ("LLM 生成\n(mock)", "#639922", "#EAF3DE")]
    bw, bh, by = 0.205, 0.13, 0.30
    bxs = [0.115, 0.40, 0.675]
    cx = xs[3] + tw / 2
    for i, (lab, e, f) in enumerate(bot):
        arrow(ax, cx, ty, bxs[i] + bw / 2, by + bh)
        box(ax, bxs[i], by, bw, bh, e, f)
        ax.text(bxs[i] + bw / 2, by + bh / 2, lab, fontsize=9.5, fontweight="bold",
                color=e, ha="center", va="center")
    ax.text(0.05, 0.14, "真实接线：路由→鉴权→检索→向量库均用真实组件；LLM / embedding / OCR 用 mock，不烧 token、不依赖外部服务",
            fontsize=9, color="#444441", va="center")
    fig.tight_layout()
    return fig


# ---------- 图3：RAGAS 评测指标 ----------
def fig_ragas():
    fig, ax = plt.subplots(figsize=(8.2, 4.7))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    ax.text(0.05, 0.965, "RAGAS 评测指标（0~1，越高越好）",
            fontsize=13, fontweight="bold", color="#0C447C", va="top")
    cards = [
        ("blue", "Faithfulness · 忠实度", "答案是否基于检索到的上下文，专拦“编造法条”"),
        ("green", "Answer Relevancy · 答案相关性", "回答是否切题、真正解决用户的问题"),
        ("orange", "Context Precision · 上下文精度", "检索到的内容是否确实相关（噪声少）"),
        ("gray", "Context Recall · 上下文召回", "是否找全了相关段落（漏检少）"),
    ]
    w, h = 0.43, 0.27
    pos = [(0.05, 0.57), (0.52, 0.57), (0.05, 0.27), (0.52, 0.27)]
    for (key, title, sub), (x, y) in zip(cards, pos):
        edge, face, tc, sc = C[key]
        box(ax, x, y, w, h, edge, face, bar=edge)
        ax.text(x + 0.035, y + h * 0.70, title, fontsize=11, fontweight="bold", color=tc, va="center")
        ax.text(x + 0.035, y + h * 0.34, sub, fontsize=9.5, color=sc, va="center")
        ax.text(x + w - 0.03, y + h * 0.85, "0~1 ↑", fontsize=9, color=edge, ha="right", va="center")
    fig.tight_layout()
    return fig


def save_and_b64(fig, name):
    png = f"{IMG_DIR}/{name}.png"
    fig.savefig(png, dpi=140, bbox_inches="tight")
    plt.close(fig)
    with open(png, "rb") as f:
        return f"data:image/png;base64,{base64.b64encode(f.read()).decode()}"


maps = {
    "![测试分层全景](docs/images/testing-landscape.svg)": save_and_b64(fig_landscape(), "testing-landscape"),
    "![集成测试范围](docs/images/integration-scope.svg)": save_and_b64(fig_integration(), "integration-scope"),
    "![RAGAS 评测指标](docs/images/ragas-metrics.svg)": save_and_b64(fig_ragas(), "ragas-metrics"),
}

readme = open(READ_ME, encoding="utf-8").read()
for old, new in maps.items():
    assert old in readme, f"未找到引用: {old}"
    readme = readme.replace(old, f"![{old.split('![')[1].split(']')[0]}]({new})")
open(READ_ME, "w", encoding="utf-8").write(readme)
print("README 已内联三张 PNG 图，替换行数:", len(maps))
