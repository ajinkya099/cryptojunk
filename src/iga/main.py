"""IGA AI Framework — FastAPI application entry point."""

from contextlib import asynccontextmanager
from typing import Any

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from iga.api import access, agents, certifications, identities, roles
from iga.config import settings
from iga.database import create_tables

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown logic."""
    logger.info(
        "iga_starting",
        environment=settings.environment,
        model=settings.agent_model,
        agent_dry_run=settings.agent_dry_run,
    )
    # Auto-create tables in dev/test (use Alembic in production)
    if not settings.is_production:
        await create_tables()
        logger.info("database_tables_created")

    yield  # Application runs here

    logger.info("iga_shutting_down")


app = FastAPI(
    title="IGA AI Framework",
    description=(
        "Identity Governance & Administration powered by AISm — "
        "AI Self-Management autonomous agents"
    ),
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if not settings.is_production else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ──────────────────────────────────────────────────────
app.include_router(identities.router, prefix="/api/v1/identities", tags=["Identities"])
app.include_router(roles.router, prefix="/api/v1/roles", tags=["Roles"])
app.include_router(access.router, prefix="/api/v1/access", tags=["Access"])
app.include_router(certifications.router, prefix="/api/v1/certifications", tags=["Certifications"])
app.include_router(agents.router, prefix="/api/v1/agents", tags=["AISm Agents"])


# ── Health ───────────────────────────────────────────────────────
@app.get("/health", tags=["Health"])
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "environment": settings.environment,
        "agent_model": settings.agent_model,
        "agent_dry_run": settings.agent_dry_run,
    }


@app.get("/", tags=["Root"])
async def root() -> dict[str, str]:
    return {
        "service": "IGA AI Framework",
        "version": "0.1.0",
        "docs": "/docs",
    }


def run() -> None:
    uvicorn.run(
        "iga.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.environment == "development",
    )


if __name__ == "__main__":
    run()
