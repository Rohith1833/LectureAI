from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from loguru import logger

from app.api.routes.router import api_router
from app.core.config import settings
from app.core.logging import setup_logging
from app.schemas.responses import RootResponse


from app.db.session import engine
from app.models.document import Base


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Handle application startup and shutdown events."""
    setup_logging()
    logger.info("Starting {} v1.0.0", settings.PROJECT_NAME)
    logger.info("Debug mode: {}", settings.DEBUG)
    logger.info("API prefix: {}", settings.api_prefix)

    # Automatically create SQLite/PostgreSQL schemas on startup
    logger.info("Initializing database schemas...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database schemas created.")

    yield
    logger.info("Shutting down {}", settings.PROJECT_NAME)


def create_app() -> FastAPI:
    """Application factory — creates and configures the FastAPI instance."""
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version="1.0.0",
        debug=settings.DEBUG,
        lifespan=lifespan,
    )

    # --- CORS ---
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Request Logging Middleware ---
    @app.middleware("http")
    async def log_requests(request: Request, call_next):  # type: ignore[no-untyped-def]
        logger.info("{} {}", request.method, request.url.path)
        response = await call_next(request)
        logger.info("Response status: {}", response.status_code)
        return response

    # --- Global Exception Handlers ---
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error("Unhandled exception: {}", str(exc))
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": "Internal Server Error",
                "errors": [
                    {
                        "field": "server",
                        "message": str(exc) if settings.DEBUG else "An unexpected error occurred."
                    }
                ]
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        logger.warning("Validation error: {}", str(exc))
        errors = []
        for error in exc.errors():
            loc = error.get("loc", [])
            field = ".".join(str(x) for x in loc[1:]) if len(loc) > 1 else ".".join(str(x) for x in loc)
            if not field:
                field = "request"
            errors.append({
                "field": field,
                "message": error.get("msg", "Validation failed")
            })

        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "message": "Validation Error",
                "errors": errors
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        logger.warning("HTTP error: status={}, detail={}", exc.status_code, exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "message": str(exc.detail),
                "errors": [
                    {
                        "field": "request",
                        "message": f"HTTP status {exc.status_code}"
                    }
                ]
            },
        )

    # --- Root Route ---
    @app.get("/", response_model=RootResponse)
    async def root() -> RootResponse:
        return RootResponse(project=settings.PROJECT_NAME, version="1.0.0")

    # --- Versioned API Routes ---
    app.include_router(api_router, prefix=settings.api_prefix)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
