"""NewsFlow 应用入口。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.v1.router import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理：启动和关闭时的资源初始化/清理。"""
    from app.core.database import init_db
    await init_db()
    yield


OPENAPI_TAGS = [
    {"name": "认证", "description": "用户注册、登录、JWT 令牌管理及 LLM API Key 配置"},
    {"name": "事件案卷", "description": "Event Case CRUD、状态迁移（candidate→active→archived）"},
    {"name": "报道任务包", "description": "Story Packet CRUD、状态迁移、送审预检、提交送审流程"},
    {"name": "签发中心", "description": "Approval Task 队列查询、签发决策（approve/return/escalate/hold/reject）、Decision Log"},
    {"name": "线索来源", "description": "Source Item 采集（上传、RSS、手动提交）、素材列表查询"},
    {"name": "今日概览", "description": "Dashboard 统计卡片、高优先级事件、SLA 告警、Agent 活动、侧边栏计数"},
    {"name": "工作流", "description": "Canonical Workflow 模板、工作流实例运行管理、统一审计事件流"},
    {"name": "证据包", "description": "Evidence Pack CRUD、快照创建"},
    {"name": "渠道包", "description": "Channel Package CRUD、状态迁移"},
    {"name": "勘误单", "description": "Correction Ticket CRUD、关闭操作"},
    {"name": "送审快照包", "description": "Review Bundle 只读查询（系统管理，不可人工修改）"},
    {"name": "风险报告", "description": "Risk/Redaction Report CRUD、版本管理"},
    {"name": "事实卡", "description": "Claim Card CRUD、核验状态更新（支持 manually_accepted 需填理由）"},
]

if settings.DEBUG:
    OPENAPI_TAGS.append({"name": "开发工具", "description": "开发环境专用接口（种子数据生成），生产环境不可用"})

app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "NewsFlow 新闻生产全流程管理平台 API。\n\n"
        "## 核心概念\n"
        "- **Event Case（事件案卷）**：新闻事件的顶层容器，管理事件生命周期\n"
        "- **Story Packet（报道任务包）**：挂载在事件下的具体报道任务，包含 Claim Cards、Evidence、Draft 等\n"
        "- **Approval Task（签发任务）**：由送审流程自动创建，支持多级审批\n"
        "- **Review Bundle（送审快照包）**：冻结版本的稿件快照，关联 Approval Task\n\n"
        "## 认证方式\n"
        "所有受保护接口需在 Header 中携带 `Authorization: Bearer <token>`，"
        "token 通过 `/api/v1/auth/login` 获取。\n\n"
        "## 风险等级\n"
        "L0（低）/ L1（中低）/ L2（中高）/ L3（高），L2/L3 签发时必须填写决策理由。"
    ),
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=OPENAPI_TAGS,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=settings.CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)


def _normalize_http_error_payload(status_code: int, detail) -> dict:
    if isinstance(detail, dict):
        code = detail.get("code") or "HTTP_ERROR"
        message = detail.get("message") or "请求失败"
        raw_details = detail.get("details")
        if isinstance(raw_details, dict):
            details = raw_details
        else:
            details = {
                k: v for k, v in detail.items()
                if k not in {"code", "message", "status", "details"}
            }
        return {
            "code": code,
            "message": message,
            "status": status_code,
            "details": details,
        }

    message = str(detail) if detail else "请求失败"
    return {
        "code": "HTTP_ERROR",
        "message": message,
        "status": status_code,
        "details": {},
    }


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content=_normalize_http_error_payload(exc.status_code, exc.detail),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "code": "VALIDATION_ERROR",
            "message": "请求参数校验失败",
            "status": 422,
            "details": {"errors": exc.errors()},
        },
    )


@app.get("/health")
async def health_check():
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION}


@app.post("/admin/init-db")
async def admin_init_db():
    """手动触发数据库表创建（Serverless 环境使用）。"""
    from app.core.database import init_db
    await init_db()
    return {"status": "ok", "message": "Database tables initialized."}
