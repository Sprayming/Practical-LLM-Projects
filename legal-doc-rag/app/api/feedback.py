"""
feedback.py —— 用户反馈收集 API 模块

【作用与功能】
本模块提供用户对 AI 回答的评价反馈接口。它将评分与原始问答以 JSON 文件形式按租户隔离
存储于 data/feedback 目录，文件名使用 Unix 时间戳保证唯一，便于后续离线分析与模型评估。

【主要组成】
- `submit_feedback`：提交反馈，记录 query、rating、answer（截取前 500 字符）及用户名。

【适用场景】
- 前端在用户对某条回答点赞/点踩或打分后调用，沉淀回答质量信号。
- 运营或算法团队离线分析反馈文件，评估与改进回答质量。

【依赖关系】
- 上游调用方：前端对话页反馈组件。
- 下游依赖：app.api.auth（require_user 鉴权）、本地文件系统 data/feedback。
"""

import sys, json, os, time

# 将项目根目录添加到系统路径中，以便正确导入项目内的其他模块
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent.parent))

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from app.api.auth import get_user_from_token, require_user

# 创建 API 路由器实例，统一添加 /api/feedback 前缀，并打上 "feedback" 标签用于文档分类
router = APIRouter(prefix="/api/feedback", tags=["feedback"])


class FeedbackRequest(BaseModel):
    """
    用户反馈请求的数据模型。
    
    属性：
        answer (str): AI 生成的回答内容，默认为空字符串。
        rating (int): 用户对回答的评分（如 1-5 分），默认为 0。
        query (str): 用户原始提问内容，默认为空字符串。
    """
    answer: str = ""
    rating: int = 0
    query: str = ""


@router.post("")
def submit_feedback(req: FeedbackRequest, user: dict = Depends(require_user)):
    """
    提交用户反馈接口。
    
    接收用户对 AI 回答的评分和评价，将其以 JSON 文件形式按租户分类存储在 data/feedback 目录下。
    文件名使用 Unix 时间戳确保唯一性，便于后续分析。
    
    参数：
        req (FeedbackRequest): 包含回答内容、评分和原始提问的请求体。
        user (dict): 依赖注入获取的当前登录用户信息，用于提取 tenant_id 和 username。
        
    返回：
        dict: 包含成功标志和确认消息。
    """
    tenant_id = user["tenant_id"]
    # 按租户创建专属反馈目录，实现数据隔离
    fb_dir = os.path.join("data", "feedback", tenant_id)
    os.makedirs(fb_dir, exist_ok=True)
    
    # 使用当前时间戳作为文件名，确保唯一性和时序性
    fb_file = os.path.join(fb_dir, f"{int(time.time())}.json")
    # 将反馈信息写入 JSON 文件，限制回答长度以控制文件体积
    with open(fb_file, "w", encoding="utf-8") as f:
        json.dump({
            "query": req.query,       # 用户原始提问
            "rating": req.rating,     # 用户评分（1-5分）
            "answer": req.answer[:500], # AI 回答（截取前500字符）
            "timestamp": time.time(), # 反馈提交时间戳
            "username": user.get("username", ""), # 提交反馈的用户名
        }, f, ensure_ascii=False)  # 确保中文正常写入
    return {"success": True, "message": "反馈已记录"}
