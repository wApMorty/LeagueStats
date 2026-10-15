"""Captures de la vitrine depuis le mode démo, en Firefox headless (SPEC-34 §4.4).

Lance la démo sans fenêtre (`scripts/demo_client.py`), parcourt ses scènes dans l'ordre du scénario et
capture chaque écran à la taille intérieure `CAPTURE_SIZE`. Écrit :

- `docs/images/captures/NN-<nom>.png` en pleine résolution (source de la vidéo) ;
- `docs/images/captures/manifest.json` : captures, série de win chance de la partie, chiffres clés de la base ;
- `docs/images/readme/<nom>.png` : copies réduites pour le README, sous `README_IMAGE_MAX_KB`.

Comme la démo, ne touche ni `data/db.db`, ni `data/crawl.db`, ni `logs/`, ni le vrai client LoL.

USAGE:
    python scripts/capture_screens.py
"""

import json
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from PIL import Image  # noqa: E402
from selenium.webdriver.support.ui import WebDriverWait  # noqa: E402

from scripts import demo_client as demo  # noqa: E402
from scripts._firefox import fenetre, headless_firefox  # noqa: E402
from src.client.bus import EventBus  # noqa: E402
from src.config import config  # noqa: E402
from src.config_constants import demo_config  # noqa: E402

CAPTURES_DIR = project_root / "docs" / "images" / "captures"
README_DIR = project_root / "docs" / "images" / "readme"
VIEW = ".view"  # conteneur de chaque écran (`base.html`)
LANES_SQL = "SELECT lane, COUNT(*) FROM matchups GROUP BY lane ORDER BY lane"
COUNT_SQL = "SELECT COUNT(*) FROM champions"
META_SQL = "SELECT value FROM db_meta WHERE key = ?"

Ready = Callable[[EventBus], Any]
LONG = demo_config.CAPTURE_LONG_SETTLE_S  # écrans à intro longue


@dataclass
class Shot:
    """Une capture : la scène de la démo, la route ouverte, ce qu'il faut attendre avant de capturer."""

    name: str
    scene: str
    route: str
    selector: str = VIEW
    ready: Ready = lambda _bus: True  # condition sur le bus du client, avant de charger la page
    settle_s: float = field(default_factory=lambda: demo_config.CAPTURE_SETTLE_S)


def _draft(kind: str) -> Ready:
    """La draft publiée par le Live Coach est à la phase `kind` (« ban » ou « pick »)."""

    def ready(bus: EventBus) -> bool:
        snapshot = bus.latest("draft") or {}
        return snapshot.get("kind") == kind and (kind == "ban" or bool(snapshot["recommendations"]))

    return ready


def _game_over(bus: EventBus) -> bool:
    """La partie simulée est arrivée au bout : la courbe de win chance est complète."""
    duration = demo.load_scenario()["game"]["duration_s"]
    return ((bus.latest("ingame") or {}).get("game_time") or 0) >= duration


# Dans l'ordre du scénario : la démo rejoue la draft puis la partie, comme en vrai.
SHOTS: List[Shot] = [
    Shot("accueil", "accueil", "/"),
    Shot("profil", "profil", "/profil"),
    Shot("historique", "historique", "/historique"),
    Shot("collection", "historique", "/collection"),
    Shot("trouvee", "trouvee", "/", ".f-overlay", settle_s=demo_config.CAPTURE_INTRO_SETTLE_S),
    Shot("draft-bans", "draft-bans", "/draft", "#draft-stage", _draft("ban"), LONG),
    Shot("draft-pick", "draft-pick", "/draft", "#draft-stage", _draft("pick"), LONG),
    Shot(
        "draft-lock", "draft-lock", "/draft", "#draft-stage", lambda bus: bus.latest("game"), LONG
    ),
    Shot(
        "chargement",
        "chargement",
        "/en-partie",
        "#en-partie-body section",
        lambda bus: bus.latest("players"),
    ),
    Shot("en-partie", "en-partie", "/en-partie", "#en-partie-body section", _game_over),
    Shot(
        "revue", "revue", "/postgame", ready=lambda bus: bus.latest("game_captured"), settle_s=LONG
    ),
    Shot("progression", "coaching", "/progression", "#prog"),
    Shot("parties", "coaching", "/parties"),
]


def _wait_bus(bus: EventBus, ready: Ready) -> bool:
    deadline = time.monotonic() + demo_config.READY_TIMEOUT_S
    while not ready(bus) and time.monotonic() < deadline:
        time.sleep(demo_config.READY_POLL_S)
    return bool(ready(bus))


def key_figures(db_path: Path) -> Dict[str, Any]:
    """Chiffres clés de la base (lecture seule) : champions, matchups par rôle, dernière mise à jour."""
    connection = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        lanes = dict(connection.execute(LANES_SQL).fetchall())
        updated = connection.execute(META_SQL, ("last_full_success_utc",)).fetchone()
        return {
            "champions": connection.execute(COUNT_SQL).fetchone()[0],
            "matchups_par_role": lanes,
            "matchups": sum(lanes.values()),
            "mise_a_jour_utc": updated[0] if updated else None,
        }
    finally:
        connection.close()


def readme_copy(source: Path, target: Path) -> int:
    """Copie réduite à `README_IMAGE_WIDTH` de large, PNG optimisé, en palette si besoin ; taille en Ko."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as image:
        width = demo_config.README_IMAGE_WIDTH
        small = image.convert("RGB").resize(
            (width, round(image.height * width / image.width)), Image.Resampling.LANCZOS
        )
    small.save(target, optimize=True)
    if target.stat().st_size > demo_config.README_IMAGE_MAX_KB * 1024:
        small.quantize(colors=256, method=Image.Quantize.MEDIANCUT).save(target, optimize=True)
    return round(target.stat().st_size / 1024)


def capture(driver: Any, handle: "demo.DemoHandle", shot: Shot, path: Path) -> bool:
    """Met la démo sur la scène de `shot`, charge sa route, attend son rendu et la capture."""
    if handle.fake.scene["name"] != shot.scene:
        handle.goto(shot.scene)
    if not _wait_bus(handle.bus, shot.ready):
        print(f"[ALERTE] {shot.name} : état attendu non publié, capture quand même")
    driver.get(f"{handle.url}{shot.route}")
    try:
        WebDriverWait(driver, demo_config.CAPTURE_RENDER_TIMEOUT_S).until(
            lambda d: d.execute_script(
                "return !!document.querySelector(arguments[0]);", shot.selector
            )
        )
    except Exception:  # pylint: disable=broad-exception-caught
        print(f"[ERREUR] {shot.name} : {shot.selector} absent de {shot.route}")
        return False
    time.sleep(shot.settle_s)
    return bool(driver.save_screenshot(str(path)))


def main() -> int:
    CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
    db_src = Path(config.DATABASE_PATH)
    figures = key_figures(db_src)
    handle: Optional[demo.DemoHandle] = None
    driver = None
    ok = True
    files: List[Dict[str, str]] = []
    series: List[List[float]] = []
    try:
        handle = demo.start_demo(SHOTS[0].scene, window=False, db_src=db_src)
        if handle is None:
            return 1
        driver = headless_firefox(demo_config.CAPTURE_SIZE)
        fenetre(driver, demo_config.CAPTURE_SIZE, demo_config.CAPTURE_SETTLE_S)
        for index, shot in enumerate(SHOTS, start=1):
            path = CAPTURES_DIR / f"{index:02d}-{shot.name}.png"
            if not capture(driver, handle, shot, path):
                ok = False
                continue
            if shot.name == "en-partie":
                series = (handle.bus.latest("ingame") or {}).get("series") or []
            kb = readme_copy(path, README_DIR / f"{shot.name}.png")
            if kb > demo_config.README_IMAGE_MAX_KB:
                print(
                    f"[ALERTE] {shot.name} : {kb} Ko pour le README (max {demo_config.README_IMAGE_MAX_KB})"
                )
            files.append({"file": path.name, "scene": shot.scene, "route": shot.route})
            print(f"[OK] {path.name} ({kb} Ko pour le README)")
    finally:
        if driver is not None:
            driver.quit()
        if handle is not None:
            handle.stop()
    manifest = {
        "capture_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "taille": list(demo_config.CAPTURE_SIZE),
        "captures": files,
        "win_chance": series,
        "chiffres": figures,
    }
    (CAPTURES_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"[DATA] {len(files)}/{len(SHOTS)} captures, courbe de {len(series)} points")
    return 0 if ok and len(series) >= 20 else 1


if __name__ == "__main__":
    sys.exit(main())
