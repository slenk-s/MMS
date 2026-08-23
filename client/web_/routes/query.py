"""
领料记录查询路由
提供网页渲染、JSON API 和统计接口
"""
from datetime import datetime
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.templating import Jinja2Templates
import sys as _sys

from database import db, get_web_query_api_key
from schemas import RecordQueryParams, PaginatedResponse

router = APIRouter()

# 模板路径：兼容开发模式和 PyInstaller 打包模式
import os as _os
if getattr(_sys, "frozen", False):
    if hasattr(_sys, "_MEIPASS"):
        _WEB_DIR = _sys._MEIPASS
        _web_subdir = _os.path.join(_WEB_DIR, "web_")
        if _os.path.isdir(_web_subdir):
            _WEB_DIR = _web_subdir
    else:
        _BASE_DIR = _os.path.dirname(_os.path.abspath(_sys.executable))
        _WEB_DIR = _os.path.join(_BASE_DIR, "_internal", "web_")
        if not _os.path.isdir(_WEB_DIR):
            _WEB_DIR = _os.path.join(_BASE_DIR, "web_")
else:
    _WEB_DIR = _os.path.dirname(_os.path.dirname(__file__))

_TEMPLATES_DIR = _os.path.join(_WEB_DIR, "templates")
_templates = Jinja2Templates(directory=_TEMPLATES_DIR)


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """渲染查询页面

    API Key 不再注入模板，由中间件通过 HttpOnly Cookie 自动传递。
    前端 fetch 会自动携带 Cookie，无需在 JS 中持有 API Key。
    """
    # ?? API Key ??????????? X-API-Key Header ??
    return _templates.TemplateResponse(
        request, "index.html",
        {
            "now": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "api_key": get_web_query_api_key() or "",
        },
    )


@router.get("/api/stats")
async def get_stats(
    card_no: str = Query(default=""),
    user_name: str = Query(default=""),
    material_code: str = Query(default=""),
    material_name: str = Query(default=""),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
    unreturned_only: bool = Query(default=False),
):
    """获取领料记录统计数据（支持查询条件过滤）"""
    return db.get_filtered_stats(
        card_no=card_no,
        user_name=user_name,
        material_code=material_code,
        material_name=material_name,
        date_from=date_from,
        date_to=date_to,
        unreturned_only=unreturned_only,
    )


@router.get("/api/records", response_model=PaginatedResponse)
async def query_records(
    card_no: str = Query(default=""),
    user_name: str = Query(default=""),
    material_code: str = Query(default=""),
    material_name: str = Query(default=""),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
    unreturned_only: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
):
    """查询领料记录 JSON API"""
    records, total = db.search_borrow_records(
        card_no=card_no,
        user_name=user_name,
        material_code=material_code,
        material_name=material_name,
        date_from=date_from,
        date_to=date_to,
        unreturned_only=unreturned_only,
        page=page,
        page_size=page_size,
    )
    total_pages = max(1, (total + page_size - 1) // page_size)

    return PaginatedResponse(
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        records=records,
    )
