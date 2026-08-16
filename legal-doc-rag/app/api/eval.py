"""
eval.py —— 自进化闭环「回答质量看板」后端接口

【作用与功能】
把 app.core.trace_store 沉淀的问答 trace 以聚合统计 + 样本列表的形式暴露给前端
eval_dashboard.html,形成「经验捕获 → 可视化归因」的闭环视图。管理员可在看板上一眼看到:
整体通过率/延迟、哪些问题被用户点踩(低分样本)、最近问答明细,从而定位需要改进的方向。

【主要组成】
- `GET /api/eval/stats`    :看板顶部统计卡片(总量/低分/成功率/平均延迟/反馈覆盖/供应商分布)。
- `GET /api/eval/low-rated`:「答得差」的样本(点踩或生成失败),用于失败归因。
- `GET /api/eval/recent`   :最近问答明细,支持快速回看。

【安全】
看板含跨租户运营数据,仅 super_admin / admin 可访问;普通用户返回 403。

【依赖关系】
- 上游:前端 eval_dashboard.html。
- 下游:app.core.trace_store(get_stats / get_low_rated / get_recent_traces)。
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from app.api.auth import require_user
from app.core.trace_store import get_stats, get_low_rated, get_recent_traces

# 统一前缀 /api/eval,便于前端聚合调用与 nginx 路由
router = APIRouter(prefix="/api/eval", tags=["eval"])


def _require_admin(user: dict):
    """看板为运营敏感数据,仅管理员可访问全量;否则 403。"""
    if user.get("role") not in ("super_admin", "admin"):
        raise HTTPException(status_code=403, detail="仅管理员可访问回答质量看板")
    return user


@router.get("/stats")
def eval_stats(user: dict = Depends(require_user)):
    """
    看板统计指标。

    返回:
        dict: get_stats() 的聚合结果(见 trace_store.get_stats 字段说明)。
    """
    _require_admin(user)
    return get_stats()


@router.get("/low-rated")
def eval_low_rated(
    limit: int = Query(50, ge=1, le=500),
    user: dict = Depends(require_user),
):
    """
    取出「答得差」的样本列表。

    参数:
        limit (int): 最多返回条数(1-500)。

    返回:
        list[dict]: 低分/失败样本(字段同 trace_store._row_to_dict)。
    """
    _require_admin(user)
    return get_low_rated(limit=limit)


@router.get("/recent")
def eval_recent(
    n: int = Query(50, ge=1, le=500),
    user: dict = Depends(require_user),
):
    """
    最近问答明细。

    参数:
        n (int): 最多返回条数(1-500)。

    返回:
        list[dict]: 最近 n 条问答 trace。
    """
    _require_admin(user)
    return get_recent_traces(n=n)
