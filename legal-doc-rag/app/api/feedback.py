import sys, json, os, time
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent.parent))
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from app.api.auth import get_user_from_token, require_user

router = APIRouter(prefix="/api/feedback", tags=["feedback"])

class FeedbackRequest(BaseModel):
    answer: str = ""
    rating: int = 0
    query: str = ""

@router.post("")
def submit_feedback(req: FeedbackRequest, user: dict = Depends(require_user)):
    tenant_id = user["tenant_id"]
    fb_dir = os.path.join("data", "feedback", tenant_id)
    os.makedirs(fb_dir, exist_ok=True)
    fb_file = os.path.join(fb_dir, f"{int(time.time())}.json")
    with open(fb_file, "w", encoding="utf-8") as f:
        json.dump({
            "query": req.query, "rating": req.rating,
            "answer": req.answer[:500], "timestamp": time.time(),
            "username": user.get("username", ""),
        }, f, ensure_ascii=False)
    return {"success": True, "message": "反馈已记录"}