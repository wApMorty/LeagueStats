"""Mode démo du client LeagueStats, sans client League of Legends (SPEC-34 §4.3).

Un faux LCU, servi en HTTP sur 127.0.0.1, répond aux chemins du LCU et de la Live Client API à partir
du scénario de `scripts/demo/`. Le processus de démo ne patche que des points d'entrée : les
identifiants du LCU (`LCUClient.find_lcu_credentials`), l'URL de la Live Client API (`live.URL`), le
chemin de la base (une copie temporaire) et les journaux. Tout le reste est la vraie pile du client :
serveur, Live Coach, recommandations, modèle de win chance.

Garde-fous : `data/db.db`, `data/crawl.db` et `logs/` réels ne sont jamais écrits ; aucun appel
n'atteint le vrai client LoL, même ouvert ; le serveur du client prend un port libre.

USAGE:
    python scripts/demo_client.py                        # scénario en boucle, fenêtre du client
    python scripts/demo_client.py --scene draft-pick     # figé sur une scène
    python scripts/demo_client.py --sans-fenetre         # URL affichée, Ctrl+C pour arrêter
    python scripts/demo_client.py --liste                # scènes disponibles
"""

import argparse
import json
import re
import shutil
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Pattern, Tuple

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.client import server, window  # noqa: E402
from src.client.bus import EventBus  # noqa: E402
from src.client.ingame import LiveGame  # noqa: E402
from src.client.launch import LiveCoachThread, _phase_source  # noqa: E402
from src.coaching.capture import GameCapture  # noqa: E402
from src.config import config  # noqa: E402
from src.config_constants import demo_config  # noqa: E402
from src.draft import tick_timer  # noqa: E402
from src.draft_monitor import DraftMonitor  # noqa: E402
from src.lcu_client import LCUClient, LCUCredentials  # noqa: E402
from src.winprob import live  # noqa: E402
from src.winprob.crawl import Crawler  # noqa: E402

DEMO_DIR = project_root / "scripts" / "demo"
LCU_DIR = DEMO_DIR / "lcu"
SCENARIO_PATH = DEMO_DIR / "scenario.json"
LIVE_PATH = "/liveclientdata/allgamedata"

# Lectures servies telles quelles par un fichier de `scripts/demo/lcu/` : (motif complet, fichier).
ROUTES: Tuple[Tuple[Pattern[str], str], ...] = tuple(
    (re.compile(pattern), name)
    for pattern, name in (
        (r"/lol-summoner/v1/current-summoner", "current_summoner.json"),
        (r"/lol-ranked/v1/current-ranked-stats", "ranked_stats.json"),
        (r"/lol-regalia/v2/current-summoner/regalia", "regalia.json"),
        (r"/lol-challenges/v1/summary-player-data/local-player", "challenges_summary.json"),
        (
            r"/lol-match-history/v1/products/lol/current-summoner/matches\?begIndex=\d+&endIndex=\d+",
            "match_history.json",
        ),
        (r"/lol-match-history/v1/games/\d+", "game_detail.json"),
        (r"/lol-champions/v1/owned-champions-minimal", "owned_champions.json"),
        (r"/lol-champions/v1/inventories/\d+/champions/\d+/skins", "skins_annie.json"),
        (r"/lol-item-sets/v1/item-sets/\d+/sets", "item_sets.json"),
        (r"/lol-chat/v1/me", "chat_me.json"),
        (r"/lol-chat/v1/friends", "chat_friends.json"),
        (r"/lol-chat/v1/conversations", "chat_conversations.json"),
        (r"/lol-game-queues/v1/queues", "queues.json"),
        (r"/lol-lobby/v2/lobby", "lobby.json"),
        (r"/lol-lobby/v2/lobby/matchmaking/search-state", "search_state_idle.json"),
        (r"/lol-matchmaking/v1/search", "matchmaking_search.json"),
        (r"/lol-perks/v1/pages", "pages.json"),
        (r"/lol-perks/v1/currentpage", "current_page.json"),
        (r"/lol-perks/v1/inventory", "perks_inventory.json"),
        (r"/lol-perks/v1/styles", "styles.json"),
    )
)
GAME_DETAIL = re.compile(r"/lol-match-history/v1/games/(\d+)")


def load_scenario(path: Path = SCENARIO_PATH) -> Dict[str, Any]:
    """Le scénario de démo (`scripts/demo/scenario.json`)."""
    return json.loads(path.read_text(encoding="utf-8"))


class FakeLcu:
    """Le faux client LoL : réponses de la scène courante, puis fichiers de `scripts/demo/lcu/`.

    Sans réseau : `read` et `write` se testent seuls, le serveur HTTP (`serve`) ne fait que les relayer.
    """

    def __init__(self, scenario: Dict[str, Any], lcu_dir: Path = LCU_DIR) -> None:
        self.scenario = scenario
        self.scenes: List[Dict[str, Any]] = scenario["scenes"]
        self._lcu_dir = lcu_dir
        self._files: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self.scene: Dict[str, Any] = self.scenes[0]

    def names(self) -> List[str]:
        """Les noms des scènes, dans l'ordre du scénario."""
        return [scene["name"] for scene in self.scenes]

    def set_scene(self, name: str) -> None:
        """Passe à la scène `name`.

        Raises:
            KeyError: scène inconnue.
        """
        scene = next((s for s in self.scenes if s["name"] == name), None)
        if scene is None:
            raise KeyError(name)
        with self._lock:
            self.scene = scene

    def phase(self) -> str:
        """Phase gameflow de la scène courante (`"None"` hors de toute file, comme le LCU)."""
        return self.scene.get("phase", "None")

    def _file(self, name: str) -> Any:
        if name not in self._files:
            self._files[name] = json.loads((self._lcu_dir / name).read_text(encoding="utf-8"))
        return json.loads(json.dumps(self._files[name]))  # copie : l'appelant peut la modifier

    def read(self, path: str) -> Optional[Any]:
        """Réponse à `GET path` ; None (404) pour un endpoint que la démo ne sert pas."""
        with self._lock:
            if path == "/lol-gameflow/v1/gameflow-phase":
                return self.phase()
            if path == "/lol-gameflow/v1/session":
                return {"phase": self.phase()}
            for pattern, name in ROUTES:
                if pattern.fullmatch(path):
                    data = self._file(name)
                    detail = GAME_DETAIL.fullmatch(path)
                    if detail:
                        data["gameId"] = int(detail.group(1))
                    return data
        return None

    def write(self, method: str, path: str, body: Optional[Any]) -> Optional[Any]:
        """Réponse à une écriture : acceptée sans effet (`{}`), comme un client qui l'aurait prise en compte."""
        return {}


class _Handler(BaseHTTPRequestHandler):
    """Relaie chaque requête au `FakeLcu` du serveur ; None devient 404."""

    def _reply(self, payload: Optional[Any]) -> None:
        if payload is None:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 (nom imposé par http.server)
        self._reply(self.server.fake.read(self.path))  # type: ignore[attr-defined]

    def _write(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw) if raw else None
        except ValueError:
            body = None
        fake = self.server.fake  # type: ignore[attr-defined]
        self._reply(fake.write(self.command, self.path, body))

    do_POST = do_PATCH = do_PUT = do_DELETE = _write

    def log_message(self, *args: Any) -> None:  # pylint: disable=unused-argument
        """Muet : la console de la démo reste celle du client."""


def serve(fake: FakeLcu) -> Tuple[ThreadingHTTPServer, str]:
    """Sert `fake` sur un port libre de 127.0.0.1, en fil daemon ; renvoie le serveur et son URL."""
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    httpd.daemon_threads = True
    httpd.fake = fake  # type: ignore[attr-defined]
    threading.Thread(target=httpd.serve_forever, name="demo-lcu", daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def _quiet(*_args: Any, **_kwargs: Any) -> None:
    """Remplace un travail que la démo n'a pas à faire (capture, collecte, journal mémoire)."""


Setter = Callable[[Any, str, Any], None]


def isolate(db_src: Path, workdir: Path, setattr_: Setter = setattr) -> List[Tuple[Any, str, Any]]:
    """Copie `db_src` dans `workdir` et y redirige base, `crawl.db` et journaux.

    Coupe aussi la capture de fin de partie (elle rangerait des parties inventées dans la copie, que la
    revue montrerait à la place de la vraie) et la collecte. `setattr_` : `monkeypatch.setattr` en test.
    Renvoie les remplacements faits, `(cible, attribut, valeur)`.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    db = workdir / "db.db"
    shutil.copyfile(db_src, db)
    (workdir / "logs").mkdir(exist_ok=True)
    patches: List[Tuple[Any, str, Any]] = [
        (config, "DATABASE_PATH", str(db)),  # crawl.db en dérive (src/winprob/crawl.py:185)
        (tick_timer, "_LOG_PATH", workdir / "logs" / "draft_monitor_ticks.log"),
        (DraftMonitor, "_log_memory_usage", _quiet),
        (GameCapture, "on_startup", _quiet),
        (GameCapture, "on_post_game", _quiet),
        (Crawler, "seed", _quiet),
        (Crawler, "start", _quiet),
    ]
    for target, name, value in patches:
        setattr_(target, name, value)
    return patches


def point_to(url: str, setattr_: Setter = setattr) -> None:
    """Fait parler au faux LCU de `url` tous les `LCUClient` et tous les lecteurs de la Live Client API."""
    port = int(url.rsplit(":", 1)[1])
    credentials = LCUCredentials(port=port, password="demo", base_url=url)
    setattr_(LCUClient, "find_lcu_credentials", lambda _self: credentials)
    setattr_(live, "URL", f"{url}{LIVE_PATH}")


class DemoHandle:
    """La démo en cours : son URL, son bus, son faux LCU ; `goto`, `play` et `stop`."""

    def __init__(
        self,
        url: str,
        bus: EventBus,
        fake: FakeLcu,
        workdir: Path,
        stoppers: List[Callable[[], None]],
    ) -> None:
        self.url = url
        self.bus = bus
        self.fake = fake
        self._workdir = workdir
        self._stoppers = stoppers
        self._playing = threading.Event()
        self._halt = threading.Event()

    def goto(self, scene: str) -> None:
        """Saute à la scène et l'y fige (arrête la lecture continue)."""
        self._playing.clear()
        self.fake.set_scene(scene)

    def play(self) -> None:
        """Lit le scénario en boucle, `SCENE_DELAY_S` par scène, dans un fil daemon."""
        if self._playing.is_set():
            return
        self._playing.set()

        def run() -> None:
            while self._playing.is_set() and not self._halt.is_set():
                for name in self.fake.names():
                    if not self._playing.is_set() or self._halt.is_set():
                        return
                    self.fake.set_scene(name)
                    self._halt.wait(demo_config.SCENE_DELAY_S)

        threading.Thread(target=run, name="demo-play", daemon=True).start()

    def stop(self) -> None:
        """Arrête la lecture, le client et le faux LCU ; supprime la copie temporaire."""
        self._playing.clear()
        self._halt.set()
        for stop in self._stoppers:
            try:
                stop()
            except Exception:  # pylint: disable=broad-exception-caught
                pass
        shutil.rmtree(self._workdir, ignore_errors=True)


def start_demo(
    scene: Optional[str] = None, window: bool = True, db_src: Optional[Path] = None
) -> Optional[DemoHandle]:
    """Lance la démo comme `run_client` (serveur, Live Coach, `LiveGame`), sur le faux LCU.

    `window` vrai : ouvre la fenêtre du client et ne rend la main qu'à sa fermeture (démo arrêtée) ;
    faux : rend tout de suite la démo en cours (captures). Sans `scene`, le scénario tourne en boucle.
    Ne lève pas : un échec s'annonce en `[ERREUR]` et renvoie None.
    """
    workdir = Path(tempfile.mkdtemp(prefix="leaguestats-demo-"))
    stoppers: List[Callable[[], None]] = []
    try:
        isolate(Path(db_src or config.DATABASE_PATH), workdir)
        fake = FakeLcu(load_scenario())
        httpd, lcu_url = serve(fake)
        stoppers.append(httpd.shutdown)
        point_to(lcu_url)
        bus = EventBus()
        coach = LiveCoachThread(bus)
        url = server.start(config.DATABASE_PATH, bus, LCUClient(), coach.send)
        if url is None:
            raise RuntimeError("le serveur du client n'a pas démarré")
        stoppers.insert(0, server.stop)
        game = LiveGame(bus, _phase_source(bus, LCUClient()))
        game.start()
        stoppers.insert(0, game.stop)
        coach.start()
        stoppers.insert(0, coach.stop)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"[ERREUR] Démo impossible : {exc}")
        for stop in stoppers:
            stop()
        shutil.rmtree(workdir, ignore_errors=True)
        return None
    handle = DemoHandle(url, bus, fake, workdir, stoppers)
    if scene:
        handle.goto(scene)
    else:
        handle.play()
    print(f"[OK] Démo sur {url} (scène : {scene or 'lecture en boucle'})")
    if window:
        try:
            if not window_run(url):
                print("[INFO] Ctrl+C pour arrêter la démo")
                _wait_for_interrupt()
        finally:
            handle.stop()
    return handle


def window_run(url: str) -> bool:
    """La fenêtre du client (`src/client/window.py`) ; False si elle ne s'ouvre pas."""
    return window.run(url)


def _wait_for_interrupt() -> None:
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Client LeagueStats en mode démo (SPEC-34)")
    parser.add_argument("--scene", help="scène sur laquelle se figer (voir --liste)")
    parser.add_argument("--sans-fenetre", action="store_true", help="pas de fenêtre, URL affichée")
    parser.add_argument("--liste", action="store_true", help="liste les scènes et quitte")
    args = parser.parse_args()
    names = [scene["name"] for scene in load_scenario()["scenes"]]
    if args.liste:
        for name in names:
            print(name)
        return 0
    if args.scene and args.scene not in names:
        print(f"[ERREUR] Scène inconnue : {args.scene} (voir --liste)")
        return 1
    handle = start_demo(args.scene, window=not args.sans_fenetre)
    if handle is None:
        return 1
    if args.sans_fenetre:
        print("[INFO] Ctrl+C pour arrêter la démo")
        try:
            _wait_for_interrupt()
        finally:
            handle.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
