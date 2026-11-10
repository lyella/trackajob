from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.db import Base, get_engine
from app.routes import auth, health, jobs, resumes


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Idempotent schema creation. Fine at this scale; revisit if migrations
    # ever become real (see ADR-0007).
    import app.models  # noqa: F401  (registers tables on Base)

    Base.metadata.create_all(get_engine())
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)

    # API routes are registered first. With app.frontend() they always take
    # priority over frontend files regardless of registration order.
    application.include_router(health.router)
    application.include_router(auth.router)
    application.include_router(resumes.router)
    application.include_router(jobs.router)

    # Serve the built frontend (web/dist) from the same function, so the
    # app runs on one domain with no CORS setup. Vercel promotes these files
    # to its CDN at build time. The guard keeps the API runnable before the
    # frontend has ever been built locally.
    dist_dir = Path(__file__).resolve().parent.parent / "web" / "dist"
    if dist_dir.exists():
        if hasattr(application, "frontend"):
            application.frontend("/", directory=str(dist_dir), fallback="index.html")
        else:
            # Older FastAPI without frontend(): plain static mount.
            application.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="frontend")

    return application


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
