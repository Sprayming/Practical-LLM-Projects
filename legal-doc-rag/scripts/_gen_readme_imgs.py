# -*- coding: utf-8 -*-
"""_gen_readme_imgs.py —— 把三张测试概念图重绘为 PNG，并以 base64 内联进 README.md。

【作用与功能】
本脚本是一个"README 配图生成器"(文档图片资产构建脚本)，不参与线上业务逻辑:
1. 用 matplotlib 以纯代码方式绘制三张讲解"项目测试体系"的概念示意图
   (① 测试分层全景、② 集成测试范围、③ RAGAS 评测指标)；
2. 把每张图保存为高分辨率 PNG 到 docs/images/ 目录；
3. 再把 PNG 二进制读成 base64 data URI，直接替换 README.md 中原有的
   SVG 图片引用，使 README 图片"自包含"——在 GitHub / Gitee / 离线
   Markdown 阅读器中都能正常显示，不依赖外部图片文件是否被正确拉取。

【主要组成】
- `box`:在坐标系上绘制一个圆角卡片矩形，可选在左侧叠加一条竖色条
- `arrow`:在两点之间绘制箭头，用于表达调用链 / 数据流向
- `fig_landscape`:绘制图1「测试分层全景」——单元/集成/评测/E2E 四层纵向卡片
- `fig_integration`:绘制图2「集成测试范围」——真实接线链路 + 被 mock 的外部依赖
- `fig_ragas`:绘制图3「RAGAS 评测指标」——忠实度/相关性/精度/召回 四宫格
- `save_and_b64`:把 figure 落盘为 PNG，并返回可直接嵌入 Markdown 的 base64 data URI
- 模块级尾部流程:构造「旧图片引用 → 新 data URI」映射表，整体替换后写回 README.md

【适用场景】
- 场景1:README 配图需要重绘、改配色或改文案时，执行 `python scripts/_gen_readme_imgs.py`
- 场景2:希望 README 不再依赖 docs/images 外链，一次性把图片内联进 Markdown
- 注意:文件名以下划线开头表示这是内部一次性工具脚本；它会**直接改写 README.md**，
  建议在 git 工作区干净的情况下运行，便于用 `git diff` 复核结果

【依赖关系】
- 第三方库:matplotlib(强制使用 Agg 无界面后端，保证服务器 / CI 环境可运行)
- 标准库:base64
- 系统字体:需安装任一中文字体(Microsoft YaHei / SimHei / Noto Sans SC)，
  否则图中中文会渲染成方框(豆腐块)
- 文件路径:IMG_DIR、READ_ME 为硬编码的 Windows 绝对路径，换机器 / 换目录需同步修改
"""
import base64
import matplotlib
# 必须在 import pyplot 之前切换到 Agg 后端:Agg 只负责把图渲染到内存/文件，
# 不需要图形界面(GUI)，因此可在无显示器的服务器或 CI 容器中运行。
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

# 指定中文字体候选列表:matplotlib 会按顺序找第一个系统里存在的字体，
# 缺少中文字体时图中汉字会变成方框，所以同时列出 Windows / Linux 常见字体。
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Noto Sans SC", "sans-serif"]
# 换成中文字体后负号会显示异常，关闭 unicode 负号即可正常显示 "-"
plt.rcParams["axes.unicode_minus"] = False

IMG_DIR = r"D:\git\legal-doc-rag\docs\images"  # PNG 输出目录(硬编码绝对路径)
READ_ME = r"D:\git\legal-doc-rag\README.md"    # 待改写的 README 文件路径

# 统一配色表:键为色系名，值为四元组
# (边框色 edge, 填充色 face, 标题文字色 title, 副标题文字色 sub)
# 集中管理颜色，保证三张图风格一致、改色只需改一处。
C = {
    "green": ("#639922", "#EAF3DE", "#27500A", "#3B6D11"),
    "orange": ("#BA7517", "#FAEEDA", "#633806", "#854F0B"),
    "blue": ("#185FA5", "#E6F1FB", "#0C447C", "#185FA5"),
    "gray": ("#5F5E5A", "#F1EFE8", "#444441", "#444441"),
}


def box(ax, x, y, w, h, edge, face, bar=None):
    """在坐标系上绘制一个圆角卡片矩形，可选在左边缘叠加一条竖向色条。

    参数:
        ax (matplotlib.axes.Axes): 目标坐标轴对象(本脚本统一使用 0~1 归一化坐标)
        x (float): 卡片左下角横坐标(0~1)
        y (float): 卡片左下角纵坐标(0~1)
        w (float): 卡片宽度(0~1 相对比例)
        h (float): 卡片高度(0~1 相对比例)
        edge (str): 边框颜色，十六进制色值字符串
        face (str): 填充(背景)颜色，十六进制色值字符串
        bar (str | None): 左侧竖色条颜色；为 None 时不画色条
    返回:
        None: 直接把图形元素画到传入的 ax 上，无返回值
    适用场景:
        - 三张概念图中所有"卡片""方框"节点的统一绘制入口，避免重复写 patch 参数
    """
    # 主体圆角矩形:pad 控制外扩留白，rounding_size 控制圆角半径
    ax.add_patch(FancyBboxPatch((x, y), w, h,
                 boxstyle="round,pad=0.004,rounding_size=0.012",
                 linewidth=0.9, edgecolor=edge, facecolor=face))
    if bar is not None:
        # 左侧强调色条:宽度固定 0.018，与卡片等高，无边框，用于强化分类视觉标识
        ax.add_patch(FancyBboxPatch((x, y), 0.018, h,
                     boxstyle="round,pad=0.0,rounding_size=0.006",
                     linewidth=0, facecolor=bar))


def arrow(ax, x1, y1, x2, y2, color="#9AA0A6"):
    """在两点之间绘制一条带箭头的连线，用于表示调用关系或数据流向。

    参数:
        ax (matplotlib.axes.Axes): 目标坐标轴对象
        x1 (float): 起点横坐标
        y1 (float): 起点纵坐标
        x2 (float): 终点(箭头指向处)横坐标
        y2 (float): 终点(箭头指向处)纵坐标
        color (str): 箭头颜色，默认中性灰 #9AA0A6，避免抢走卡片视觉焦点
    返回:
        None: 直接把箭头画到传入的 ax 上，无返回值
    适用场景:
        - 图2 中表达 "TestClient → API 路由 → 鉴权 → 业务编排" 的横向链路
        - 图2 中表达业务编排向下扇出到检索 / 向量库 / LLM 三个组件
    """
    # 用空文本的 annotate 只画箭头:xy 为箭头尖端，xytext 为箭头尾部
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="-|>", color=color, lw=1.3))


# ---------- 图1:测试分层全景 ----------
def fig_landscape():
    """绘制图1「测试分层全景」:把四类测试自上而下排成四张卡片。

    参数:
        无
    返回:
        matplotlib.figure.Figure: 已绘制完成的 figure 对象，交由 `save_and_b64` 落盘
    适用场景:
        - README 中向读者解释项目测试体系的分层结构:
          单元测试 → 集成测试 → 评测测试 → 端到端 E2E，从"代码对不对"递进到"回答好不好"
    """
    fig, ax = plt.subplots(figsize=(8.2, 4.7))
    # 统一使用 0~1 归一化坐标系，并关闭坐标轴刻度/边框，得到纯净画布
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    ax.text(0.05, 0.965, "测试分层全景:从代码单元到问答质量",
            fontsize=13, fontweight="bold", color="#0C447C", va="top")
    cards = [
        ("green", "① 单元测试 · 已实现", "测单个函数是否正确:config 解析、检索打分、记忆存取"),
        ("orange", "② 集成测试 · 已实现", "多个真实组件接线跑通:API 路由 → 检索 → 向量库 → LLM"),
        ("blue", "③ 评测测试 · 已实现", "不问代码对错，问回答好坏:用 RAGAS 给忠实度/相关性打分 0~1"),
        ("gray", "④ 端到端 E2E · 可选", "从前端或脚本发真实请求跑完整流程，最慢最脆弱，少量关键路径才写"),
    ]
    # x/w/h 为卡片左边距、宽度、高度；gap 为卡片之间的纵向间隙
    x, w, h, gap = 0.05, 0.90, 0.155, 0.025
    y = 0.80  # 第一张卡片的起始纵坐标(从上往下排列)
    for key, title, sub in cards:
        edge, face, tc, sc = C[key]  # 从配色表取出该层对应的四种颜色
        box(ax, x, y, w, h, edge, face, bar=edge)
        # 标题居卡片偏上位置(0.66 高度处)，副标题居偏下位置(0.30 高度处)
        ax.text(x + 0.035, y + h * 0.66, title, fontsize=12, fontweight="bold", color=tc, va="center")
        ax.text(x + 0.035, y + h * 0.30, sub, fontsize=9.5, color=sc, va="center")
        y -= (h + gap)  # 纵坐标递减，实现自上而下依次堆叠
    fig.tight_layout()
    return fig


# ---------- 图2:集成测试范围 ----------
def fig_integration():
    """绘制图2「集成测试范围」:上方一条横向真实调用链，下方三个被接入的组件。

    参数:
        无
    返回:
        matplotlib.figure.Figure: 已绘制完成的 figure 对象，交由 `save_and_b64` 落盘
    适用场景:
        - README 中说明集成测试的"边界"在哪里:
          路由 / 鉴权 / 检索 / 向量库全部使用真实组件，只有 LLM、embedding、OCR 走 mock，
          既验证了真实接线，又不消耗 token、不依赖外部服务可用性
    """
    fig, ax = plt.subplots(figsize=(8.4, 5.0))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    ax.text(0.05, 0.965, "集成测试范围:真实接线，只 mock 外部 LLM",
            fontsize=13, fontweight="bold", color="#0C447C", va="top")
    # 顶部链路:请求从测试客户端进入，依次经过路由、鉴权、业务编排(均为真实代码)
    # 每个元素为 (显示文案, 边框/文字色, 填充色)
    top = [("TestClient", "#5F5E5A", "#F1EFE8"),
           ("API 路由\n/api/chat", "#185FA5", "#E6F1FB"),
           ("JWT 鉴权", "#185FA5", "#E6F1FB"),
           ("业务编排\nchat.py", "#185FA5", "#E6F1FB")]
    tw, th, ty = 0.205, 0.13, 0.70  # 顶部卡片的宽、高、统一纵坐标
    xs = [0.04, 0.285, 0.53, 0.775]  # 四个顶部卡片的横坐标，等距排布
    for i, (lab, e, f) in enumerate(top):
        box(ax, xs[i], ty, tw, th, e, f)
        # 文案在卡片正中央(水平、垂直双向居中)
        ax.text(xs[i] + tw / 2, ty + th / 2, lab, fontsize=10, fontweight="bold",
                color=e, ha="center", va="center")
        if i < len(top) - 1:
            # 除最后一个卡片外，都从右边缘向下一个卡片左边缘画箭头，形成链路
            arrow(ax, xs[i] + tw, ty + th / 2, xs[i + 1], ty + th / 2)
    # 下方三个组件:由业务编排层扇出调用，前两个为真实组件，LLM 为 mock(故用绿色区分)
    bot = [("混合检索\nBM25+Dense+RRF", "#BA7517", "#FAEEDA"),
           ("Chroma\n向量库", "#BA7517", "#FAEEDA"),
           ("LLM 生成\n(mock)", "#639922", "#EAF3DE")]
    bw, bh, by = 0.205, 0.13, 0.30  # 下方卡片的宽、高、统一纵坐标
    bxs = [0.115, 0.40, 0.675]      # 三个下方卡片的横坐标
    cx = xs[3] + tw / 2             # 扇出起点:顶部最后一个卡片(业务编排)的水平中心
    for i, (lab, e, f) in enumerate(bot):
        # 先画箭头再画卡片，保证箭头线段被卡片遮住尾部，视觉上更干净
        arrow(ax, cx, ty, bxs[i] + bw / 2, by + bh)
        box(ax, bxs[i], by, bw, bh, e, f)
        ax.text(bxs[i] + bw / 2, by + bh / 2, lab, fontsize=9.5, fontweight="bold",
                color=e, ha="center", va="center")
    # 底部一行说明文字:点明"哪些真实、哪些 mock"这一集成测试的核心取舍
    ax.text(0.05, 0.14, "真实接线:路由→鉴权→检索→向量库均用真实组件；LLM / embedding / OCR 用 mock，不烧 token、不依赖外部服务",
            fontsize=9, color="#444441", va="center")
    fig.tight_layout()
    return fig


# ---------- 图3:RAGAS 评测指标 ----------
def fig_ragas():
    """绘制图3「RAGAS 评测指标」:把四个核心指标排成 2×2 四宫格卡片。

    参数:
        无
    返回:
        matplotlib.figure.Figure: 已绘制完成的 figure 对象，交由 `save_and_b64` 落盘
    适用场景:
        - README 中用一张图讲清 RAGAS 的四个打分维度及其业务含义:
          忠实度(防编造法条)、答案相关性(是否切题)、
          上下文精度(检索噪声少)、上下文召回(漏检少)，取值均为 0~1，越高越好
    """
    fig, ax = plt.subplots(figsize=(8.2, 4.7))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    ax.text(0.05, 0.965, "RAGAS 评测指标(0~1，越高越好)",
            fontsize=13, fontweight="bold", color="#0C447C", va="top")
    cards = [
        ("blue", "Faithfulness · 忠实度", "答案是否基于检索到的上下文，专拦“编造法条”"),
        ("green", "Answer Relevancy · 答案相关性", "回答是否切题、真正解决用户的问题"),
        ("orange", "Context Precision · 上下文精度", "检索到的内容是否确实相关(噪声少)"),
        ("gray", "Context Recall · 上下文召回", "是否找全了相关段落(漏检少)"),
    ]
    w, h = 0.43, 0.27  # 单张卡片的宽、高(两列布局，每列约占一半宽度)
    # 四个卡片左下角坐标:左上、右上、左下、右下，与 cards 列表顺序一一对应
    pos = [(0.05, 0.57), (0.52, 0.57), (0.05, 0.27), (0.52, 0.27)]
    for (key, title, sub), (x, y) in zip(cards, pos):
        edge, face, tc, sc = C[key]
        box(ax, x, y, w, h, edge, face, bar=edge)
        ax.text(x + 0.035, y + h * 0.70, title, fontsize=11, fontweight="bold", color=tc, va="center")
        ax.text(x + 0.035, y + h * 0.34, sub, fontsize=9.5, color=sc, va="center")
        # 右上角统一标注取值范围与"越高越好"的方向提示
        ax.text(x + w - 0.03, y + h * 0.85, "0~1 ↑", fontsize=9, color=edge, ha="right", va="center")
    fig.tight_layout()
    return fig


def save_and_b64(fig, name):
    """把 figure 保存为 PNG 文件，并返回可直接内联到 Markdown 的 base64 data URI。

    参数:
        fig (matplotlib.figure.Figure): 待保存的图对象
        name (str): 文件名(不含扩展名)，最终落盘为 `{IMG_DIR}/{name}.png`
    返回:
        str: 形如 `data:image/png;base64,iVBORw0...` 的 data URI 字符串，
             可直接写进 Markdown 的 `![alt](...)` 括号内
    适用场景:
        - 在构造 `maps` 映射表时调用，一次完成"落盘 + 编码"两件事
    """
    png = f"{IMG_DIR}/{name}.png"
    # dpi=140 兼顾清晰度与体积；bbox_inches="tight" 自动裁掉四周多余白边
    fig.savefig(png, dpi=140, bbox_inches="tight")
    plt.close(fig)  # 及时关闭 figure 释放内存，避免多图累积告警
    # 以二进制读回 PNG 并做 base64 编码，拼成 data URI
    with open(png, "rb") as f:
        return f"data:image/png;base64,{base64.b64encode(f.read()).decode()}"


# ---------- 主流程:绘图 → 落盘 → 内联替换 README ----------
# maps 的键 = README 中现存的旧图片引用(原为 SVG 外链)
# maps 的值 = 新生成 PNG 的 base64 data URI
# 注意:字典构造过程中即完成了三张图的绘制与落盘(save_and_b64 立即执行)
maps = {
    "![测试分层全景](docs/images/testing-landscape.svg)": save_and_b64(fig_landscape(), "testing-landscape"),
    "![集成测试范围](docs/images/integration-scope.svg)": save_and_b64(fig_integration(), "integration-scope"),
    "![RAGAS 评测指标](docs/images/ragas-metrics.svg)": save_and_b64(fig_ragas(), "ragas-metrics"),
}

readme = open(READ_ME, encoding="utf-8").read()
for old, new in maps.items():
    # 断言旧引用必须存在:若 README 已被改过导致找不到锚点，立即失败而不是静默跳过
    assert old in readme, f"未找到引用: {old}"
    # 从旧引用中截取原 alt 文案("![" 与 "]" 之间的内容)，保持替换后 alt 不变，
    # 仅把括号内的路径换成 base64 data URI
    readme = readme.replace(old, f"![{old.split('![')[1].split(']')[0]}]({new})")
# 全部替换成功后再一次性写回文件，避免中途失败留下半成品 README
open(READ_ME, "w", encoding="utf-8").write(readme)
print("README 已内联三张 PNG 图，替换行数:", len(maps))
