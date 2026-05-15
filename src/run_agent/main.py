"""FastAPI app factory."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from run_agent.config.logging import configure_logging, get_logger
from run_agent.config.settings import settings
from run_agent.middlewares.error_handler import register_exception_handlers
from run_agent.routes import auth, chat, conversations, files, health

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging()
    logger.info("startup", app=settings.app_name, debug=settings.debug)
    yield
    logger.info("shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        lifespan=lifespan,
        docs_url=f"{settings.api_prefix}/docs" if settings.debug else None,
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    app.include_router(health.router, prefix=settings.api_prefix, tags=["health"])
    app.include_router(auth.router, prefix=f"{settings.api_prefix}/auth", tags=["auth"])
    app.include_router(chat.router, prefix=f"{settings.api_prefix}/chat", tags=["chat"])
    app.include_router(
        conversations.router,
        prefix=f"{settings.api_prefix}/conversations",
        tags=["conversations"],
    )
    app.include_router(files.router, prefix=f"{settings.api_prefix}/files", tags=["files"])

    return app


app = create_app()
