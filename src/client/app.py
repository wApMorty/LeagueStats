"""Fabrique de l'application FastAPI du client (SPEC-21 §4.2, §4.7)."""

import json
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, NamedTuple, Optional, Tuple, Union
from urllib.parse import urlsplit

import anyio
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sse_starlette.sse import EventSourceResponse

from ..config import get_resource_path
from ..config_client import client_config
from ..pool_manager import get_user_data_path
from ..coaching.goals import set_goal
from ..coaching.grid import GRID
from ..repositories.coaching import CoachingRepository
from ..user_prefs import load_motion, save_motion
from .assets import PLACEHOLDER, Assets
from .data import (
    ROLE_ORDER,
    calibration_empty,
    calibration_view,
    default_role,
    progression_view,
    rank_view,
)
from .db import read_only, writable
from .home import ORIGINS, axes_view, empty_home, home_view
from .draft_grimoire import grimoire_view
from .draft_loadout import normalize_page, plan as loadout_plan, runes_payload, send as send_loadout
from . import found
from .draft_actions import Refusal, role_command, run as run_draft_action
from .draft_skins import SkinBook, select_skin
from .draft_view import Champions, signature, stage_view
from .lcu_proxy import LcuProxy
from .lcu_status import LcuProbe
from .review import game_page, games_view, load_model


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
            NavItem("rang", "Rang", "ᚱ", 245, "/rang"),
            NavItem("progression", "Progression", "ᛏ", 290, "/progression"),
            NavItem("parties", "Parties", "ᛗ", 85, "/parties"),
            NavItem("calibration", "Calibration", "ᛉ", 345, "/calibration"),
        ),
    ),
    NavGroup(
        "Partie",
        55,
        (NavItem("draft", "Draft", "ᛟ", 55, "/draft"), NavItem("postgame", "Post-game", "ᛞ", 345)),
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


def create_app(
    db_path: Union[str, Path],
    bus: Any = None,
    lcu: Any = None,
    assets: Optional[Assets] = None,
    commands: Optional[Callable[[str], bool]] = None,
) -> FastAPI:
    """Construit l'application ; `bus` et `lcu` sont ceux que les écrans liront.

    `commands` dépose une ligne de commande chez le Live Coach (`r <champion> <lane>`) et dit si
    elle a été prise ; None en mode console.

    Tout passe par un garde : `Host` et `Origin` sur la boucle locale (sinon 403), et le jeton de
    session (`app.state.session_token`) sur les méthodes qui écrivent et sur le SSE, avant tout
    appel au LCU.
    """
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.db_path = Path(db_path)
    app.state.bus = bus
    app.state.lcu = lcu
    app.state.assets = assets or Assets(Path(get_user_data_path(client_config.ASSETS_DIR)))
    app.state.session_token = secrets.token_urlsafe(client_config.SESSION_TOKEN_BYTES)
    probe = LcuProbe(lcu)
    proxy = LcuProxy(lcu)
    skin_book = SkinBook(proxy)
    templates = Jinja2Templates(directory=get_resource_path(f"{CLIENT_DIR}/templates"))
    app.mount(
        "/static", StaticFiles(directory=get_resource_path(f"{CLIENT_DIR}/static")), name="static"
    )

    templates.env.filters["sig"] = signature

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
            transition=client_config.transition(),
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

    def coaching(reader: Callable[[CoachingRepository], Any], empty: Callable[[], Any]) -> Any:
        """Lit la base en lecture seule ; tables absentes (base non migrée) : l'état vide, pas une 500."""
        try:
            with read_only(app.state.db_path) as db:
                return reader(CoachingRepository(db))
        except sqlite3.OperationalError as error:
            if "no such table" not in str(error):
                raise
            return empty()

    @app.get("/sante")
    def sante() -> dict:
        return {"ok": True}

    @app.get("/", response_class=HTMLResponse)
    def accueil(request: Request):
        champions, now = Champions(app.state.assets), datetime.now(timezone.utc)
        view = coaching(lambda repo: home_view(repo, champions, now), empty_home)
        return render(request, "accueil.html", v=view)

    def axes_fragment(request: Request, notice: Optional[str] = None) -> HTMLResponse:
        """Les places d'axe, rechargées après chaque écriture ; le message de celle-ci au-dessus."""
        view = coaching(lambda repo: axes_view(repo, notice), lambda: None)
        return templates.TemplateResponse(request, "partials/accueil_axes.html", {"a": view})

    @app.get("/accueil/axes", response_class=HTMLResponse)
    def accueil_axes(request: Request):
        return axes_fragment(request)

    @app.post("/accueil/axe", response_class=HTMLResponse)
    def axe_fixer(request: Request, metric: str, role: str, origin: str = "player"):
        """Fixe un axe de travail (SPEC-21 §2 : l'une des deux écritures du coaching dans la base)."""
        if role not in GRID or metric not in GRID[role] or origin not in ORIGINS:
            return JSONResponse({"detail": "axe invalide"}, status_code=400)
        with writable(app.state.db_path) as db:
            message = set_goal(CoachingRepository(db), metric, role, origin)
        return axes_fragment(request, message.removeprefix("[AXE] "))

    @app.post("/accueil/axe/{goal_id}/clore", response_class=HTMLResponse)
    def axe_clore(request: Request, goal_id: int):
        """Clôt un axe actif (statut `dropped`, comme quand le Live Coach en déplace un)."""
        with writable(app.state.db_path) as db:
            repo = CoachingRepository(db)
            if not any(goal["id"] == goal_id for goal in repo.goals()):
                return JSONResponse({"detail": "axe inconnu ou déjà clos"}, status_code=404)
            repo.set_goal_status(goal_id, "dropped")
        return axes_fragment(request, "Axe clos")

    @app.get("/rang", response_class=HTMLResponse)
    def rang(request: Request):
        view = coaching(lambda repo: rank_view(repo.rank_history()), lambda: rank_view([]))
        return render(request, "rang.html", v=view)

    @app.get("/progression", response_class=HTMLResponse)
    def progression(request: Request, role: Optional[str] = None):
        def read(repo: CoachingRepository) -> dict:
            roles = repo.player_roles()
            shown = role if role in ROLE_ORDER else default_role(roles)
            return progression_view(roles, repo.player_history(shown), shown)

        return render(
            request, "progression.html", v=coaching(read, lambda: progression_view({}, [], role))
        )

    @app.get("/calibration", response_class=HTMLResponse)
    def calibration(request: Request, version: Optional[str] = None):
        view = coaching(lambda repo: calibration_view(repo, version), calibration_empty)
        return render(request, "calibration.html", v=view)

    @app.get("/parties", response_class=HTMLResponse)
    def parties(request: Request):
        champions, now = Champions(app.state.assets), datetime.now(timezone.utc)
        view = coaching(
            lambda repo: games_view(repo, champions, now),
            lambda: {"empty": True, "rows": [], "summary": ""},
        )
        return render(request, "parties.html", v=view)

    @app.get("/parties/{game_id}", response_class=HTMLResponse)
    def partie(request: Request, game_id: int):
        champions, now = Champions(app.state.assets), datetime.now(timezone.utc)
        page = coaching(
            lambda repo: game_page(repo, game_id, champions, load_model(), now), lambda: None
        )
        if page is None:
            return render(
                request,
                "erreur.html",
                404,
                title="Partie introuvable",
                detail=f"La partie {game_id} n'est pas dans les parties capturées.",
            )
        return render(request, "partie.html", g=page)

    def draft_snapshot() -> Optional[dict]:
        return bus.latest("draft") if bus is not None else None

    def locked_skins(snapshot: Optional[dict]):
        """Les skins du champion que j'ai verrouillé (lus dans le LCU), None sinon ou client fermé."""
        me = next((p for p in (snapshot or {}).get("allies", []) if p["is_local"]), None)
        return skin_book.skins(me["champion_id"]) if me and me["champion_id"] else None

    @app.get("/draft", response_class=HTMLResponse)
    def draft_page(request: Request):
        snapshot = draft_snapshot()
        view = stage_view(snapshot, app.state.assets, intro=True, skins=locked_skins(snapshot))
        return render(request, "draft.html", v=view, stage_size=client_config.DRAFT_STAGE_SIZE)

    @app.get("/draft/stage", response_class=HTMLResponse)
    def draft_stage(request: Request):
        """Le contenu synchronisé de l'écran, rechargé par le script à chaque snapshot du bus."""
        snapshot = draft_snapshot()
        view = stage_view(snapshot, app.state.assets, skins=locked_skins(snapshot))
        return templates.TemplateResponse(request, "partials/draft_stage.html", {"v": view})

    @app.post("/draft/skin")
    def draft_skin(skin_id: int):
        """Écrit le skin choisi dans le champ select ; refusé (409) s'il n'est pas possédé."""
        me = next((p for p in (draft_snapshot() or {}).get("allies", []) if p["is_local"]), None)
        try:
            if not me or not me["champion_id"]:
                raise Refusal("Verrouille d'abord ton champion")
            return select_skin(proxy, skin_book, me["champion_id"], skin_id)
        except Refusal as refusal:
            return JSONResponse({"detail": str(refusal)}, status_code=409)

    @app.get("/draft/champions", response_class=HTMLResponse)
    def draft_champions(request: Request):
        """Le grimoire des champions, ouvert par le script au clic."""
        view = grimoire_view(draft_snapshot(), app.state.assets)
        return templates.TemplateResponse(request, "partials/draft_grimoire.html", {"g": view})

    @app.get("/found/state")
    def found_state() -> dict:
        """Phase du client LoL et compte à rebours de la partie trouvée."""
        return found.state(proxy)

    @app.post("/found/{name}")
    def found_answer(name: str):
        """Accepte ou refuse la partie trouvée ; refusé (409) hors de la file trouvée."""
        try:
            return found.answer(proxy, name)
        except Refusal as refusal:
            return JSONResponse({"detail": str(refusal)}, status_code=409)

    @app.get("/draft/runes")
    def draft_runes() -> dict:
        """Arbres de runes, fragments et sorts, pour la page de runes et son éditeur."""
        return runes_payload(app.state.assets.rune_styles())

    @app.get("/draft/loadout")
    def draft_loadout(champion_id: int) -> dict:
        """La page de runes, les sorts et les objets prévus pour ce champion (OneTricks, ou déjà dans le client)."""
        snapshot = draft_snapshot()
        if not snapshot:
            return {"available": False, "reason": "Pas de champ select en cours"}
        return loadout_plan(snapshot, champion_id, app.state.assets.rune_styles())

    def tell_live_coach(line: str) -> bool:
        return commands is not None and commands(line)

    @app.post("/draft/loadout/manual")
    def draft_loadout_manual(on: int):
        """La page est modifiée à la main (l'import du lock-in s'efface) ou rétablie (il reprend)."""
        if not tell_live_coach("loadout manual" if on else "loadout auto"):
            return JSONResponse({"detail": "Live Coach inactif"}, status_code=503)
        return Response(status_code=204)

    @app.post("/draft/loadout/send")
    def draft_loadout_send(
        primary: int, sub: int, perks: str, shards: str, spell1: int, spell2: int
    ):
        """Écrit la page et les sorts choisis dans le client ; ils priment alors sur l'import du lock-in."""
        styles = app.state.assets.rune_styles()
        try:
            ids = [int(x) for x in perks.split(",")]
            fragments = [int(x) for x in shards.split(",")]
            page = (
                normalize_page(styles, primary, sub, ids, fragments)
                if len(ids) == 6 and len(set(ids)) == 6
                else None
            )
            if page is None:
                raise Refusal("Page de runes incomplète")
            snapshot = draft_snapshot() or {}
            me = next((p for p in snapshot.get("allies", []) if p["is_local"]), None)
            shown = next(
                (
                    c
                    for c in snapshot.get("champions", [])
                    if me and c["champion_id"] == (me["champion_id"] or me["hover_id"])
                ),
                None,
            )
            label = (
                f"{shown['champion']} {snapshot.get('local_role') or ''}".strip()
                if shown
                else "Page"
            )
            outcome = send_loadout(proxy, styles, page, [spell1, spell2], label)
        except ValueError:
            return JSONResponse({"detail": "Identifiants de runes illisibles"}, status_code=409)
        except Refusal as refusal:
            return JSONResponse({"detail": str(refusal)}, status_code=409)
        tell_live_coach("loadout manual")
        return outcome

    @app.post("/draft/action/{name}")
    def draft_action(name: str, champion_id: int):
        """Survoler, verrouiller ou bannir ; refusé (409) hors phase et hors tour, sans écriture."""
        try:
            return run_draft_action(proxy, name, champion_id)
        except Refusal as refusal:
            return JSONResponse({"detail": str(refusal)}, status_code=409)

    @app.post("/draft/role")
    def draft_role(champion: str, lane: str):
        """Corrige le rôle d'un champion : la commande `r` du Live Coach, appliquée à son prochain tour."""
        try:
            line = role_command(champion, lane)
        except Refusal as refusal:
            return JSONResponse({"detail": str(refusal)}, status_code=409)
        if commands is None or not commands(line):
            return JSONResponse({"detail": "Live Coach inactif"}, status_code=503)
        return Response(status_code=204)

    @app.get("/assets/{kind}/{name:path}")
    def asset(kind: str, name: str):
        """Image de Data Dragon depuis le cache ; absente, un emplacement neutre (jamais d'erreur)."""
        store: Assets = app.state.assets
        if not store.accepts(kind, name):
            return JSONResponse({"detail": "ressource inconnue"}, status_code=404)
        data = store.image(kind, name)
        if data is None:
            return Response(
                PLACEHOLDER, media_type="image/gif", headers={"Cache-Control": "no-store"}
            )
        media_type = "image/jpeg" if name.endswith(".jpg") else "image/png"
        cache = f"max-age={client_config.ASSETS_BROWSER_CACHE_S}"
        return Response(data, media_type=media_type, headers={"Cache-Control": cache})

    @app.get("/_motion", response_class=HTMLResponse)
    def banc_motion(request: Request):
        return render(
            request,
            "motion_bench.html",
            budget_ms=client_config.MOTION_BUDGET_MS,
            scene_s=client_config.MOTION_BENCH_SCENE_S,
        )

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
