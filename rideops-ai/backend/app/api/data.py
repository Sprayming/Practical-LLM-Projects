from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import PlainTextResponse
from pathlib import Path
import uuid
from app.data import get_orders, get_datasets, get_dataset_info
from app.data.loader import load_any_file, SUPPORTED_FORMATS, generate_template
from app.config import settings

router = APIRouter(prefix="/api/data", tags=["Data"])

MAX_SIZE = 500 * 1024 * 1024  # 50MB

@router.get("/template", response_class=PlainTextResponse)
async def download_template():
    return generate_template()

@router.post("/upload")
async def upload_data(file: UploadFile = File(...)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in SUPPORTED_FORMATS:
        raise HTTPException(400, f"不支持 {ext}，仅支持 CSV / Excel")

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    save_path = upload_dir / f"{uuid.uuid4().hex}{ext}"

    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(400, f"文件超过50MB限制")
    save_path.write_bytes(content)

    try:
        result = load_any_file(str(save_path))

        if result["type"] == "orders":
            return {
                "success": True,
                "type": "orders",
                "filename": file.filename,
                "orders_loaded": result["orders_loaded"],
                "drivers_found": result["drivers"],
                "errors": result.get("warnings", [])[:5],
                "preview": result.get("preview", []),
                "message": f"成功加载 {result['orders_loaded']} 条订单，{result['drivers']} 位司机"
            }
        else:
            return {
                "success": True,
                "type": "dataset",
                "filename": file.filename,
                "rows": result["rows"],
                "columns": result["columns"],
                "errors": result.get("warnings", [])[:5],
                "preview": result.get("preview", []),
                "message": f"已加载 {result['rows']} 行数据，{len(result['columns'])} 列（{', '.join(result['columns'][:6])}...）"
            }
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"加载失败: {e}")

@router.get("/info")
async def get_data_info():
    """获取当前数据的基本信息"""
    ds = get_dataset()
    orders = get_orders()
    if orders:
        return {"type": "orders", "count": len(orders), "columns": list(orders[0].model_dump().keys())}
    elif ds["count"] > 0:
        return {"type": "dataset", "count": ds["count"], "columns": ds["columns"]}
    else:
        return {"type": "empty", "count": 0, "columns": []}

@router.get("/orders")
async def get_orders_list(skip: int = 0, limit: int = 100):
    orders = get_orders()
    return {"total": len(orders), "orders": [o.model_dump() for o in orders[skip:skip+limit]]}

@router.get("/summary")
async def get_summary():
    orders = get_orders()
    if orders:
        dates = [o.pickup_time for o in orders]
        return {"total_orders": len(orders), "total_drivers": len(set(o.driver_id for o in orders)), "date_range": f"{min(dates).strftime('%Y-%m-%d')} ~ {max(dates).strftime('%Y-%m-%d')}"}
    ds = get_dataset()
    if ds["count"] > 0:
        return {"total_rows": ds["count"], "total_columns": len(ds["columns"]), "columns": ds["columns"][:10]}
    return {"total_orders": 0}