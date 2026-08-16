"""
FastAPI Backend per Gestor de Substitucions.

The real application lives in this uniquely named module so frozen desktop builds
cannot confuse the generic module name ``main`` with a PyInstaller bootstrap
module. ``main.py`` remains a compatibility wrapper for ``uvicorn main:app``.
"""
from dotenv import load_dotenv
load_dotenv()

import logging
import os
import sys
import time
from datetime import datetime


def _configure_console_streams() -> None:
    """Make legacy startup prints safe on Windows consoles.

    The upstream project contains a few emoji/non-ASCII status prints. Windows
    runners and some local shells default to cp1252, which can raise
    UnicodeEncodeError during module import. Reconfigure existing text streams to
    UTF-8; windowed PyInstaller builds have no streams and are handled separately
    by ``desktop_launcher``.
    """
    for stream in (getattr(sys, "stdout", None), getattr(sys, "stderr", None)):
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, ValueError, OSError):
                pass


_configure_console_streams()

from fastapi import FastAPI, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from database import create_auth_tables
from auth_utils import ensure_default_users, get_current_user, require_admin
from config.auth import IS_DEVELOPMENT
from rate_limit import limiter
from schemas import ConfigResponse
from helpers import get_horari, MissingXmlError
from auth_utils import decode_access_token

access_logger = logging.getLogger("uvicorn.error")
access_logger.setLevel(logging.INFO)

create_auth_tables()
ensure_default_users()


def _inicialitzar_prioritats():
    from database import get_data_db_session
    from config.settings import config
    from routes.prioritats import _recarregar_prioritats_desde_bd

    try:
        institucio = os.getenv("APP_INSTITUCIO") or config.global_data.get("institucio") or "exemple"
        with get_data_db_session(institucio) as db:
            _recarregar_prioritats_desde_bd(db)
    except Exception as e:
        print(f"⚠️  No s'han pogut carregar prioritats des de BD: {e}")
        print("   Es faran servir les constants del JSON per defecte")


def _inicialitzar_invigilation():
    """初始化中国监考模块默认岗位与基础规则。"""
    from database import get_data_db_session
    from config.settings import config
    from invigilation_defaults import seed_defaults

    try:
        institucio = os.getenv("APP_INSTITUCIO") or config.global_data.get("institucio") or "exemple"
        with get_data_db_session(institucio) as db:
            seed_defaults(db)
    except Exception as e:
        print(f"⚠️  监考模块默认配置初始化失败: {e}")


_inicialitzar_prioritats()
_inicialitzar_invigilation()

app = FastAPI(
    title="Gestor Substitucions API",
    description="API REST per gestionar substitucions i vigilàncies",
    version="1.0.0",
    docs_url="/docs" if IS_DEVELOPMENT else None,
    redoc_url="/redoc" if IS_DEVELOPMENT else None,
    openapi_url="/openapi.json" if IS_DEVELOPMENT else None,
)


@app.exception_handler(MissingXmlError)
async def missing_xml_exception_handler(request: Request, exc: MissingXmlError):
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc), "xml_missing": True, "institucio": exc.institucio},
    )


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = int((time.perf_counter() - start) * 1000)
        _log_request(request, duration_ms, 500)
        raise
    duration_ms = int((time.perf_counter() - start) * 1000)
    _log_request(request, duration_ms, response.status_code)
    return response


def _log_request(request: Request, duration_ms: int, status_code: int) -> None:
    username = "-"
    role = "-"
    instit = "-"
    token = request.cookies.get("gestor_token")
    if token:
        try:
            payload = decode_access_token(token)
            username = payload.get("sub") or "-"
            role = payload.get("role") or "-"
            instit = payload.get("institucio") or "-"
        except Exception:
            pass

    path = request.url.path
    query = request.url.query
    full_path = f"{path}?{query}" if query else path
    ip = request.client.host if request.client else "-"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    access_logger.info(
        f"{timestamp} | {username} ({role}@{instit}) | {ip} | {request.method} {full_path} | {status_code} | {duration_ms}ms"
    )


app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from routes import (
    auth,
    config_examens,
    grups,
    grups_amagats,
    pdf,
    vigilancies,
    substitucions,
    settings,
    estadistiques,
    prioritats,
    horari,
    files,
    users,
    disponibles,
    scheduler,
    informes,
    cursos,
    dades,
    invigilation_config,
    invigilation_exams,
    invigilation_import,
    invigilation_solver,
    invigilation_export,
)

app.include_router(auth.router)
app.include_router(config_examens.router, dependencies=[Depends(require_admin)])
app.include_router(grups.router, dependencies=[Depends(get_current_user)])
app.include_router(grups_amagats.router, dependencies=[Depends(require_admin)])
app.include_router(pdf.router, dependencies=[Depends(get_current_user)])
app.include_router(vigilancies.router, dependencies=[Depends(get_current_user)])
app.include_router(substitucions.router, dependencies=[Depends(get_current_user)])
app.include_router(settings.router, dependencies=[Depends(require_admin)])
app.include_router(estadistiques.router, dependencies=[Depends(require_admin)])
app.include_router(prioritats.router, dependencies=[Depends(require_admin)])
app.include_router(horari.router, dependencies=[Depends(get_current_user)])
app.include_router(files.router, dependencies=[Depends(require_admin)])
app.include_router(users.router, dependencies=[Depends(get_current_user)])
app.include_router(disponibles.router, dependencies=[Depends(get_current_user)])
app.include_router(scheduler.router, dependencies=[Depends(require_admin)])
app.include_router(informes.router, dependencies=[Depends(require_admin)])
app.include_router(cursos.router, dependencies=[Depends(get_current_user)])
app.include_router(dades.router, dependencies=[Depends(require_admin)])
app.include_router(invigilation_config.router, dependencies=[Depends(get_current_user)])
app.include_router(invigilation_exams.router, dependencies=[Depends(get_current_user)])
app.include_router(invigilation_import.router, dependencies=[Depends(get_current_user)])
app.include_router(invigilation_solver.router, dependencies=[Depends(get_current_user)])
app.include_router(invigilation_export.router, dependencies=[Depends(get_current_user)])


@app.get("/")
async def root():
    return {"status": "ok", "message": "Gestor Substitucions API", "docs": "/docs"}


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/config", response_model=ConfigResponse, dependencies=[Depends(get_current_user)])
async def get_config():
    try:
        horari = get_horari()
    except MissingXmlError:
        return ConfigResponse(
            data_actual=datetime.now().strftime("%Y-%m-%d"),
            horari_carregat=False,
            num_professors=0,
            num_hores=0,
            xml_missing=True,
        )

    return ConfigResponse(
        data_actual=datetime.now().strftime("%Y-%m-%d"),
        horari_carregat=True,
        num_professors=len(horari.professors),
        num_hores=len(horari.hores),
    )


@app.get("/api/professors", dependencies=[Depends(get_current_user)])
async def get_professors():
    try:
        horari = get_horari()
    except MissingXmlError:
        return {"professors": [], "xml_missing": True}
    return {"professors": sorted(horari.professors)}


@app.get("/api/hores", dependencies=[Depends(get_current_user)])
async def get_hores():
    try:
        horari = get_horari()
    except MissingXmlError:
        return {"hores": [], "xml_missing": True}
    return {"hores": horari.hores}


@app.get("/api/config/no-substituir", dependencies=[Depends(get_current_user)])
async def get_no_substituir():
    from config.constants import NO_SUBST
    return {"no_substituir": list(NO_SUBST)}
