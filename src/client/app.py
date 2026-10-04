"""Fabrique de l'application FastAPI du client (SPEC-21 §4.2, §4.7)."""

import secrets
from pathlib import Path
from typing import Any, Optional, Union
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..config_client import client_config


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

    @app.get("/sante")
    def sante() -> dict:
        return {"ok": True}

    return app
