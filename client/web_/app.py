"""
FastAPI 应用入口
"""
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
import os
import sys
import secrets

from routes.query import router as query_router
from database import WEB_QUERY_API_KEY, get_web_query_api_key

app = FastAPI(
    title="物料管理系统 - Web 查询",
    description="产线物料员领料记录查询服务",
    version="1.0.0",
)

# 挂载静态文件：兼容开发模式和 PyInstaller 打包模式
if getattr(sys, "frozen", False):
    if hasattr(sys, "_MEIPASS"):
        _WEB_DIR = sys._MEIPASS
        _web_subdir = os.path.join(_WEB_DIR, "web_")
        if os.path.isdir(_web_subdir):
            _WEB_DIR = _web_subdir
    else:
        _BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
        _WEB_DIR = os.path.join(_BASE_DIR, "_internal", "web_")
        if not os.path.isdir(_WEB_DIR):
            _WEB_DIR = os.path.join(_BASE_DIR, "web_")
else:
    _WEB_DIR = os.path.dirname(os.path.abspath(__file__))

_STATIC_DIR = os.path.join(_WEB_DIR, "static")
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

# 启动时提示 API Key 认证状态
if WEB_QUERY_API_KEY:
    print("[Auth] API Key 认证已启用，所有 /api/* 接口需要认证")
else:
    print("[Auth] 未配置 WEB_QUERY_API_KEY，/api/* 接口为开放访问（建议设置以增强安全性）")


@app.middleware("http")
async def api_key_auth_middleware(request: Request, call_next):
    """API Key 认证中间件

    安全设计：
    - / 页面：无需认证，访问后自动设置 HttpOnly Cookie 携带 API Key
    - /api/*：验证 Cookie 或 X-API-Key Header（不通过 URL Query 传参，避免日志泄露）
    - /health：不认证

    API Key 使用 get_web_query_api_key() 动态读取 config.ini 最新值，
    使配置页修改密钥后无需重启服务即可生效。
    """
    path = request.url.path
    api_key = get_web_query_api_key()

    # 访问首页时设置 HttpOnly Cookie（前端不再持有 API Key 明文）
    if path == "/" and api_key:
        response = await call_next(request)
        response.set_cookie(
            key="api_key",
            value=api_key,
            httponly=True,       # JS 无法读取，防止 XSS 窃取
            samesite="lax",   # 防止 CSRF
            max_age=86400,       # 1 天有效期
        )
        return response

    # /api/* 接口认证：仅允许 Cookie 或 Header（禁止 Query 传参）
    if path.startswith("/api/") and api_key:
        provided_key = (
            request.headers.get("X-API-Key")
            or request.cookies.get("api_key")
        )
        if not provided_key or not secrets.compare_digest(provided_key, api_key):
            return JSONResponse(
                status_code=401,
                content={"detail": "Unauthorized: 无效或缺失 API Key"},
            )

    response = await call_next(request)
    return response


# 注册路由（仅查询功能，配置统一在 PC 端管理）
app.include_router(query_router)


@app.get("/health")
async def health():
    """健康检查接口"""
    return {"status": "ok", "service": "mms-web-query"}


@app.exception_handler(RuntimeError)
async def runtime_error_handler(request: Request, exc: RuntimeError):
    """处理运行时错误（如数据库连接失败）"""
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
    )
