"""Fabrique de l'application FastAPI du client (SPEC-21 §4.2, §4.7)."""

import json
import secrets
import sqlite3
from pathlib import Path
from typing import Any, NamedTuple, Optional, Tuple, Union
from urllib.parse import urlsplit

import anyio
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sse_starlette.sse import EventSourceResponse

from ..config import get_resource_path
from ..config_client import client_config
from ..user_prefs import load_motion, save_motion
from .lcu_status import LcuProbe


class NavItem(NamedTuple):
    """Entrée de la navigation ; sans `href`, l'écran n'existe pas encore (entrée grisée)."""

    key: str
    label: str
    rune: str  # décorative : toujours accompagnée du libellé
    hue: int
    href: Optional[str] = None


class NavGroup(NamedTuple):
    label: str
    hue: int
    items: Tuple[NavItem, ...]


# Chaque écran reçoit son `href` à sa tâche (SPEC-21 §4.10).
NAV = (
    NavGroup(
        "Coaching",
        165,
        (
            NavItem("accueil", "Accueil", "ᚨ", 165, "/"),
            NavItem("rang", "Rang", "ᚱ", 245),
            NavItem("progression", "Progression", "ᛏ", 290),
            NavItem("parties", "Parties", "ᛗ", 85),
            NavItem("calibration", "Calibration", "ᛉ", 345),
        ),
    ),
    NavGroup(
        "Partie",
        55,
        (NavItem("draft", "Draft", "ᛟ", 55), NavItem("postgame", "Post-game", "ᛞ", 345)),
    ),
    NavGroup(
        "Client",
        245,
        (
            NavItem("profil", "Profil", "ᛒ", 245),
            NavItem("collection", "Collection", "ᚲ", 85),
            NavItem("lobby", "Lobby", "ᚹ", 290),
            NavItem("social", "Social", "ᛜ", 165),
        ),
    ),
)
MOTION_LABELS = {"systeme": "Système", "complet": "Complet", "reduit": "Réduit"}

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
                item.key
                for group in NAV
                for item in group.items
                if item.href
                and (path == item.href or (item.href != "/" and path.startswith(item.href)))
            ),
            None,
        )
        context.update(
            nav=NAV,
            active=active,
            motion=load_motion(),
            motion_modes=[(m, MOTION_LABELS[m]) for m in client_config.MOTION_MODES],
            lcu_open=probe.is_open(),
            token=app.state.session_token,
            token_header=client_config.TOKEN_HEADER,
            poll_s=client_config.LCU_STATE_POLL_S,
        )
        return templates.TemplateResponse(request, name, context, status_code=status_code)

    async def in_thread(function, *args, **kwargs):
        """`render` sonde le LCU (requête synchrone) : hors de la boucle d'événements."""
        return await anyio.to_thread.run_sync(lambda: function(*args, **kwargs))

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
            if not secrets.compare_digest(sent.encode(), app.state.session_token.encode()):
                return _refuse("jeton de session absent ou invalide")
        return await call_next(request)

    @app.exception_handler(sqlite3.OperationalError)
    async def db_error(request: Request, exc: sqlite3.OperationalError):
        if "locked" not in str(exc):
            return await server_error(request, exc)
        return await in_thread(
            render,
            request,
            "erreur.html",
            503,
            title="Base occupée",
            detail="Une autre partie de l'application écrit dans la base. Réessaie dans un instant.",
        )

    @app.exception_handler(Exception)
    async def server_error(request: Request, exc: Exception):
        return await in_thread(
            render,
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

    @app.post("/prefs/motion")
    def prefs_motion(mode: str):
        if mode not in client_config.MOTION_MODES:
            return JSONResponse({"detail": "mode inconnu"}, status_code=400)
        if not save_motion(mode):
            return JSONResponse({"detail": "préférences non enregistrées"}, status_code=500)
        return Response(status_code=204)

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
