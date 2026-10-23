"""FastAPI application factory.

Wires all routers, exception handlers, and metadata together.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from format_validator import InvalidRequest
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.routers import compatibility, format_info, validation
from config import Settings
from service.shared_paths import PathNotAbsolute, PathNotShared, SharedFileMissing


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events (startup / shutdown)."""
    # Any async initialisation (e.g. warming caches) can go here.
    yield
    # Teardown code can go here.


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        settings: Optional ``Settings`` instance. When ``None`` the default
                  settings are loaded.

    Returns:
        Configured ``FastAPI`` instance.
    """
    if settings is None:
        settings = Settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )

    # --- routers -------------------------------------------------------------
    app.include_router(validation.router, prefix="/api/v1")
    app.include_router(compatibility.router, prefix="/api/v1")
    app.include_router(format_info.router, prefix="/api/v1")

    # --- exception handlers --------------------------------------------------
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request, exc: StarletteHTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(InvalidRequest)
    async def invalid_request_handler(request, exc: InvalidRequest):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(PathNotAbsolute)
    async def path_not_absolute_handler(request, exc: PathNotAbsolute):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(PathNotShared)
    async def path_not_shared_handler(request, exc: PathNotShared):
        return JSONResponse(status_code=403, content={"detail": str(exc)})

    @app.exception_handler(SharedFileMissing)
    async def shared_file_missing_handler(request, exc: SharedFileMissing):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={"detail": jsonable_encoder(exc.errors())},
        )

    @app.get("/health", tags=["health"])
    async def health_check() -> dict[str, str]:
        """Simple health probe."""
        return {"status": "ok"}

    return app
