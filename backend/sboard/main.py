from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from sboard import __version__
from sboard.config import get_settings
from sboard.database import init_db
from sboard.routers import agents, groups, imports, node_api, nodes, overview, subscriptions


@asynccontextmanager
async def lifespan(_app: FastAPI):  # type: ignore[no-untyped-def]
    get_settings().validate()
    init_db()
    yield


app = FastAPI(
    title="SBoard API",
    version=__version__,
    description="Lightweight personal proxy node management control plane",
    lifespan=lifespan,
)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "detail": {
                "code": "validation_error",
                "message": "Request validation failed",
                "details": exc.errors(),
            }
        },
    )


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


api_prefix = "/api/v1"
app.include_router(overview.router, prefix=api_prefix)
app.include_router(agents.router, prefix=api_prefix)
app.include_router(nodes.router, prefix=api_prefix)
app.include_router(imports.router, prefix=api_prefix)
app.include_router(groups.router, prefix=api_prefix)
app.include_router(subscriptions.router, prefix=api_prefix)
app.include_router(node_api.router, prefix="/api")
app.include_router(subscriptions.public_router)
