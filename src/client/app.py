"""Fabrique de l'application FastAPI du client (SPEC-21 §4.2, §4.7)."""

import json
import secrets
import sqlite3
from pathlib import Path
from typing import Any, Optional, Union
from urllib.parse import urlsplit

import anyio
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sse_starlette.sse import EventSourceResponse

from ..config import get_resource_path
from ..config_client import client_config
from .lcu_status import LcuProbe

# Sections de la navigation : (clé, libellé, chemin). Chaque écran s'y ajoute à sa tâche.
SECTIONS = (("coaching", "Coaching", "/"),)

CLIENT_DIR = "src/client"


def _refuse(reason: str) -> JSONResponse:
    return JSONResponse({"detail": reason}, status_code=403)


def _host_allowed(value: str, scheme: Optional[str] = None) -> bool:
    """`value` désigne la boucle locale : un `Host` (port éventuel) ou, avec `scheme`, une `Origin`."""
    parts = urlsplit(f"//{value}" if scheme is None else value)
    if scheme is not None and parts.scheme != scheme:
        return False
    try:
        return parts.hostname in client_config.ALLOWED_HOSTS
    except ValueError:  # port illisible
        return False


def create_app(db_path: Union[str, Path], bus: Any = None, lcu: Any = None) -> FastAPI:
    """Construit l'application ; `bus` et `lcu` sont ceux que les écrans liront.

    Tout passe par un garde : `Host` et `Origin` sur la boucle locale (sinon 403), et le jeton de
    session (`app.state.session_token`) sur les méthodes qui écrivent et sur le SSE, avant tout
    appel au LCU.
    """
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.db_path = Path(db_path)
    app.state.bus = bus
    app.state.lcu = lcu
    app.state.session_token = secrets.token_urlsafe(client_config.SESSION_TOKEN_BYTES)
    probe = LcuProbe(lcu)
    templates = Jinja2Templates(directory=get_resource_path(f"{CLIENT_DIR}/templates"))
    app.mount(
        "/static", StaticFiles(directory=get_resource_path(f"{CLIENT_DIR}/static")), name="static"
    )

    def render(request: Request, name: str, status_code: int = 200, **context: Any) -> HTMLResponse:
        path = request.url.path
        active = next(
            (
                k
                for k, _, href in SECTIONS
                if path == href or (href != "/" and path.startswith(href))
            ),
            None,
        )
        context.update(
            sections=SECTIONS,
            active=active,
            lcu_open=probe.is_open(),
            token=app.state.session_token,
            token_header=client_config.TOKEN_HEADER,
            poll_s=client_config.LCU_STATE_POLL_S,
        )
        return templates.TemplateResponse(request, name, context, status_code=status_code)

    @app.middleware("http")
    async def guard(request: Request, call_next):
        if not _host_allowed(request.headers.get("host", "")):
            return _refuse("hôte refusé")
        origin = request.headers.get("origin")
        if origin is not None and not _host_allowed(origin, scheme="http"):
            return _refuse("origine refusée")
        needs_token = (
            request.method in client_config.TOKEN_METHODS
            or request.url.path in client_config.TOKEN_PATHS
        )
        if needs_token:
            sent = request.headers.get(client_config.TOKEN_HEADER, "")
            if not secrets.compare_digest(sent, app.state.session_token):
                return _refuse("jeton de session absent ou invalide")
        return await call_next(request)

    @app.exception_handler(sqlite3.OperationalError)
    async def db_error(request: Request, exc: sqlite3.OperationalError):
        if "locked" not in str(exc):
            return await server_error(request, exc)
        return render(
            request,
            "erreur.html",
            503,
            title="Base occupée",
            detail="Une autre partie de l'application écrit dans la base. Réessaie dans un instant.",
        )

    @app.exception_handler(Exception)
    async def server_error(request: Request, exc: Exception):
        return render(
            request,
            "erreur.html",
            500,
            title="Erreur",
            detail=f"{type(exc).__name__} : {exc}",
        )

    @app.get("/sante")
    def sante() -> dict:
        return {"ok": True}

    @app.get("/", response_class=HTMLResponse)
    def accueil(request: Request):
        return render(request, "accueil.html")

    @app.get("/etat/client", response_class=HTMLResponse)
    def etat_client(request: Request):
        return render(request, "partials/client_state.html")

    @app.get("/events")
    async def events(request: Request):
        """Flux SSE du bus : un événement par message, nommé d'après son sujet (`?topic=` répété)."""
        if bus is None:
            return JSONResponse({"detail": "bus absent (mode console)"}, status_code=404)
        topics = request.query_params.getlist("topic") or None

        async def stream():
            with bus.subscribe(topics) as subscription:
                while True:
                    item = await anyio.to_thread.run_sync(
                        subscription.get, client_config.SSE_POLL_S, abandon_on_cancel=True
                    )
                    if item is not None:
                        yield {"event": item[0], "data": json.dumps(item[1], default=str)}

        return EventSourceResponse(stream(), ping=client_config.SSE_PING_S)

    return app
