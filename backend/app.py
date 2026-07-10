# FastAPI启动入口
# 启动员工助手服务，监听8001端口，前端直接调用此服务
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from config.settings import settings
from api.routers import chat, webhook, auth, admin


@asynccontextmanager
async def lifespan(app: FastAPI):
    from services.quota import seed_quota_config
    seed_quota_config()
    yield


app = FastAPI(title="Employee Assistant Agent", version="1.0.0", lifespan=lifespan)

# 注册路由
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(webhook.router, prefix="/api", tags=["webhook"])
app.include_router(auth.router, prefix="/api", tags=["auth"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])

# 静态文件 (Dashboard) — 挂到 /dashboard，避免与 /admin API 冲突
_static_dir = str(Path(__file__).parent / "static")
app.mount("/dashboard", StaticFiles(directory=_static_dir, html=True), name="dashboard")


@app.get("/health")
def health_check():
    # 健康检查接口，用于服务监控
    return {"status": "ok", "service": "agent-service"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.host, port=settings.port)
