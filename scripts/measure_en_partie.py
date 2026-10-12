"""Mesure de l'écran « En partie » en Firefox headless (SPEC-30 tâche 140, §4.4).

Sert l'application du client sur une base et un cache d'images temporaires (jamais `data/db.db`, ni
`logs/`, ni réseau), publie sur le bus le cas le plus lourd de l'écran, puis mesure `.page` :

- à 1 920 x 986 (SPEC-30 §4.4 : 950 px utiles sous la barre de titre de 36 px) : ni défilement vertical
  ni horizontal, et au moins `MARGE_MIN_PX` de marge verticale, avec et sans modèle de win chance
  (on garde la pire des deux passes) ;
- à 1 400 x 900 : la grille `.ig-grid` n'a plus qu'une colonne.

Ce n'est pas un test : il lance Firefox (Selenium) mais n'ouvre aucune fenêtre visible et ne touche pas au
curseur. Code de sortie 1 si une exigence échoue.

USAGE:
    python scripts/measure_en_partie.py
"""

import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import json  # noqa: E402
import sqlite3  # noqa: E402

import uvicorn  # noqa: E402
from selenium import webdriver  # noqa: E402
from selenium.webdriver.firefox.options import Options  # noqa: E402
from selenium.webdriver.support.ui import WebDriverWait  # noqa: E402

from src.client.app import create_app  # noqa: E402
from src.client.assets import Assets  # noqa: E402
from src.client.bus import EventBus  # noqa: E402
from src.config_client import client_config  # noqa: E402
from src.config_constants import draft_config  # noqa: E402

# Marge verticale minimale sous le contenu à 1 920 x 986. Origine : SPEC-30 §4.4, Firefox rend un peu
# différemment de WebView2 (le client réel), donc on exige 30 px d'avance plutôt que 0.
MARGE_MIN_PX = 30
GRAND = (
    1920,
    986,
)  # fenêtre de référence : 950 px utiles sous la barre de titre de 36 px (SPEC-29 §4.3)
PETIT = (1400, 900)  # sous 1 500 px la grille doit passer à une colonne
RENDU_TIMEOUT_S = 15  # attente du rendu du fragment `/en-partie/stage`
STABILISATION_S = 2.5  # animations d'entrée, polices, relecture déclenchée par le bus
REFLUX_S = 0.5  # recomposition après un changement de taille de fenêtre

VERSION = "16.2.1"
BASE = client_config.DDRAGON_BASE

# Les deux équipes (nom Data Dragon, identifiant Data Dragon) ; des noms longs pour le cas le plus lourd.
ALLIES = [
    ("Garen", "Garen"),
    ("Nunu et Willump", "Nunu"),
    ("Aurelion Sol", "AurelionSol"),
    ("Jinx", "Jinx"),
    ("Renata Glasc", "Renata"),
]
ENEMIES = [
    ("Darius", "Darius"),
    ("Lee Sin", "LeeSin"),
    ("Syndra", "Syndra"),
    ("Miss Fortune", "MissFortune"),
    ("Tahm Kench", "TahmKench"),
]
DUELS = [3.4, -1.3, 0.2, -2.5, None]  # points de victoire, du point de vue allié


def fetch_factice(url: str) -> Optional[bytes]:
    """Data Dragon sans réseau : versions, champions et objets ; le reste (images) tombe sur PLACEHOLDER."""
    if url.endswith("/api/versions.json"):
        return json.dumps([VERSION]).encode()
    if url.endswith("/champion.json"):
        data = {
            ident: {"key": str(n), "id": ident, "name": name, "tags": []}
            for n, (name, ident) in enumerate(ALLIES + ENEMIES, start=1)
        }
        return json.dumps({"data": data}).encode()
    if url.endswith("/item.json"):
        return json.dumps({"data": ITEMS_DD}).encode()
    return None


def _blocs() -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """Les sept blocs du plan, pleins (dont « Autres cores », en dernier : index 2 et 5 inchangés)."""
    taille = {
        "Départ (62%)": 3,
        "Autres départs": 4,
        "Core (45%)": 3,
        "Bottes (70%)": 3,
        "Composants": 10,
        "Situationnels": draft_config.LOADOUT_SITUATIONAL_ITEMS,
        "Autres cores": draft_config.LOADOUT_ALT_CORE_ITEMS,
    }
    blocs, noms, suivant = [], {}, 3000
    for titre, nombre in taille.items():
        ids = list(range(suivant, suivant + nombre))
        suivant += nombre
        blocs.append({"title": titre, "items": ids})
        noms.update({str(i): f"Objet {i}" for i in ids})
    return blocs, noms


BLOCS, NOMS = _blocs()
CORE = BLOCS[2]["items"]
# item.json : le Core est assemblé de deux composants chacun (le prochain objet affiche coût et or manquant).
ITEMS_DD = {
    str(i): {
        "name": NOMS[str(i)],
        "gold": {"base": 800, "total": 3000 if i in CORE else 1100},
        **({"from": [str(i) for i in BLOCS[4]["items"][:2]]} if i in CORE else {}),
    }
    for block in BLOCS
    for i in block["items"]
}


def analyse() -> Dict[str, Any]:
    """Charge `FinalAnalysis.to_payload()` : cinq lignes complètes, loadout plein, quatre substitutions."""
    lignes = []
    for (ally, _), (enemy, _), duel in zip(ALLIES, ENEMIES, DUELS):
        lignes.append(
            {
                "ally": {"name": ally, "matchup": 1.2, "synergy": -0.4, "total": 0.8},
                "enemy": {"name": enemy, "matchup": -0.6, "synergy": 0.9, "total": 0.3},
                "duel": duel,
            }
        )
    return {
        "lines": lignes,
        "win_probability": 0.55,
        "draft_diff": 3.4,
        "evaluation": "Avantage de draft majeur",
        # Cas le plus lourd : deux postes corrigés, dont les deux noms les plus longs (ligne la plus longue).
        "reality": {
            "state": "corrected",
            "checked": 10,
            "mismatches": [
                {"champion": "Nunu et Willump", "predicted": "jungle", "real": "bas"},
                {"champion": "Miss Fortune", "predicted": "milieu", "real": "support"},
            ],
            "at": 1800.0,
        },
        "loadout": {
            "champion_id": 86,
            "label": "Garen top",
            "item_blocks": BLOCS,
            "substitutions": [
                {
                    "category": categorie,
                    "old": f"Objet {BLOCS[2]['items'][n % 3]}",
                    "new": f"Objet {BLOCS[5]['items'][n]}",
                    "reason": "40% vs 9% en général (80 parties)",
                }
                for n, categorie in enumerate(("Bottes", "Core", "Core", "Situationnels"))
            ],
            "skills": {
                "max_order": ["Q", "E", "W"],
                "levels": ["Q", "E", "W", "Q", "Q", "R"] * 3,
                "playrate": 0.42,
            },
            "item_names": NOMS,
        },
    }


def partie(avec_modele: bool) -> Dict[str, Any]:
    """Charge du sujet `ingame` : partie à 30 min, série à 5 s, objectifs, moi (objets, or, compétences).

    La série est gardée sans modèle aussi : c'est le cas le plus lourd (courbe et notice ensemble).
    """
    serie = [[5.0 * n, 0.5 + 0.2 * (n % 40) / 40] for n in range(361)]
    objectifs = [
        {"t": 300.0 + 150.0 * n, "kind": kind, "team": "ORDER" if n % 2 else "CHAOS"}
        for n, kind in enumerate(
            ["dragon", "turret", "herald", "dragon", "inhibitor", "baron", "turret", "dragon"]
        )
    ]
    return {
        "state": "live",
        "game_time": 1800.0,
        "p": 0.58 if avec_modele else None,
        "delta": 0.03 if avec_modele else None,
        "series": serie,
        "objectives": objectifs,
        "me": {
            "champion": "Garen",
            "team": "ORDER",
            "position": "TOP",
            "level": 14,
            "gold": 1450.0,
            "items": [
                {"id": CORE[0], "name": "x", "slot": 0, "count": 1, "price": 3000},
                {"id": BLOCS[0]["items"][0], "name": "x", "slot": 1, "count": 1, "price": 400},
            ],
            "abilities": {"Q": 5, "W": 3, "E": 5, "R": 1},
        },
    }


MESURE_JS = """
const page = document.querySelector(".page");
const grille = document.querySelector(".ig-grid");
// `scrollHeight` est plafonné par le bas à `clientHeight` : la marge se lit sur le bas du dernier enfant,
// plus le `padding-bottom` de `.page`.
const haut = page.getBoundingClientRect().top - page.scrollTop;
const bas = Math.max(...Array.from(page.children).map((e) => e.getBoundingClientRect().bottom));
const contenu = Math.ceil(bas - haut + parseFloat(getComputedStyle(page).paddingBottom));
return {
  contenu,
  grille: grille ? getComputedStyle(grille).gridTemplateColumns : null,
  scrollHeight: page.scrollHeight, clientHeight: page.clientHeight,
  scrollWidth: page.scrollWidth, clientWidth: page.clientWidth,
  innerWidth: window.innerWidth, innerHeight: window.innerHeight,
  ligne: document.querySelectorAll(".ig-reality").length,
  corrigees: document.querySelectorAll(".ig-table tr.is-corrected").length,
};
"""


def fenetre(driver: webdriver.Firefox, taille: Tuple[int, int]) -> None:
    """Fixe la taille intérieure de la fenêtre (la taille demandée est celle de la fenêtre externe)."""
    largeur, hauteur = taille
    driver.set_window_size(largeur, hauteur)
    interieur = driver.execute_script("return [window.innerWidth, window.innerHeight];")
    if interieur != [largeur, hauteur]:
        driver.set_window_size(2 * largeur - interieur[0], 2 * hauteur - interieur[1])
    time.sleep(REFLUX_S)


def mesure(driver: webdriver.Firefox) -> Dict[str, Any]:
    return driver.execute_script(MESURE_JS)


def charger(driver: webdriver.Firefox, url: str) -> None:
    driver.get(f"{url}/en-partie")
    WebDriverWait(driver, RENDU_TIMEOUT_S).until(
        lambda d: d.execute_script(
            'return !!document.querySelector("#en-partie-body section, #en-partie-body .empty")'
        )
    )
    time.sleep(STABILISATION_S)


def demarrer(
    db_path: Path, bus: EventBus, cache: Path
) -> Tuple[uvicorn.Server, threading.Thread, str]:
    """Serveur uvicorn en fil sur un port libre de 127.0.0.1 (le garde d'hôte du client l'accepte)."""
    app = create_app(db_path, bus=bus, assets=Assets(cache, fetch=fetch_factice))
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=0,
        log_level="warning",
        log_config=None,
        timeout_graceful_shutdown=client_config.SERVER_GRACEFUL_SHUTDOWN_S,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    fin = time.monotonic() + client_config.SERVER_START_TIMEOUT_S
    while not server.started and thread.is_alive() and time.monotonic() < fin:
        time.sleep(0.01)
    if not server.started:
        server.should_exit = True
        raise RuntimeError("le serveur n'a pas démarré")
    return server, thread, f"http://127.0.0.1:{server.servers[0].sockets[0].getsockname()[1]}"


def main() -> int:
    ok = True
    driver: Optional[webdriver.Firefox] = None
    server: Optional[uvicorn.Server] = None
    thread: Optional[threading.Thread] = None
    with tempfile.TemporaryDirectory(prefix="measure_en_partie_") as tmp:
        try:
            db_path = Path(tmp) / "mesure.db"
            sqlite3.connect(db_path).close()  # base vide : l'écran « En partie » ne lit que le bus
            bus = EventBus()
            server, thread, url = demarrer(db_path, bus, Path(tmp) / "assets")
            print(f"[INFO] Serveur du client sur {url} (base et cache temporaires)")

            options = Options()
            options.add_argument("-headless")
            options.add_argument(f"--width={GRAND[0]}")
            options.add_argument(f"--height={GRAND[1]}")
            driver = webdriver.Firefox(options=options)
            fenetre(driver, GRAND)

            pire: Optional[Dict[str, Any]] = None
            for avec_modele in (False, True):
                bus.publish("game", analyse())
                bus.publish("ingame", partie(avec_modele))
                charger(driver, url)
                m = mesure(driver)
                marge = m["clientHeight"] - m["contenu"]
                nom = "avec modèle" if avec_modele else "sans modèle"
                print(
                    f"[DATA] {nom} à {m['innerWidth']}x{m['innerHeight']} : "
                    f"scrollHeight={m['scrollHeight']} contenu={m['contenu']} clientHeight={m['clientHeight']} "
                    f"scrollWidth={m['scrollWidth']} clientWidth={m['clientWidth']} marge={marge} px"
                )
                if m["ligne"] != 1 or m["corrigees"] != 2:
                    print(
                        f"[ERREUR] {nom} : .ig-reality x{m['ligne']} (attendu 1), "
                        f"lignes corrigées x{m['corrigees']} (attendu 2)"
                    )
                    ok = False
                if pire is None or marge < pire["marge"]:
                    pire = {**m, "marge": marge, "nom": nom}

            assert pire is not None
            print(f"[INFO] Pire passe : {pire['nom']}, marge {pire['marge']} px")
            if pire["scrollHeight"] > pire["clientHeight"]:
                print(
                    f"[ERREUR] {GRAND[0]}x{GRAND[1]} : .page défile verticalement "
                    f"({pire['scrollHeight']} > {pire['clientHeight']})"
                )
                ok = False
            if pire["scrollWidth"] > pire["clientWidth"]:
                print(
                    f"[ERREUR] {GRAND[0]}x{GRAND[1]} : .page défile horizontalement "
                    f"({pire['scrollWidth']} > {pire['clientWidth']})"
                )
                ok = False
            if pire["marge"] < MARGE_MIN_PX:
                print(
                    f"[ERREUR] Marge de {pire['marge']} px, il en faut au moins {MARGE_MIN_PX} px"
                )
                ok = False
            elif ok:
                print(f"[OK] {GRAND[0]}x{GRAND[1]} : aucun défilement, marge de {pire['marge']} px")

            fenetre(driver, PETIT)
            colonnes = mesure(driver)["grille"]
            if colonnes is None:
                print(
                    "[ERREUR] .ig-grid est absent du gabarit : impossible de constater la colonne unique"
                )
                ok = False
            elif len(colonnes.split()) == 1:
                print(
                    f"[OK] {PETIT[0]}x{PETIT[1]} : une colonne (grid-template-columns : {colonnes})"
                )
            else:
                print(
                    f"[ERREUR] {PETIT[0]}x{PETIT[1]} : plusieurs colonnes "
                    f"(grid-template-columns : {colonnes})"
                )
                ok = False
        except Exception as exc:  # pylint: disable=broad-exception-caught
            print(f"[ERREUR] Mesure impossible : {type(exc).__name__}: {exc}")
            ok = False
        finally:
            if driver is not None:
                driver.quit()
            if server is not None:
                server.should_exit = True
                if thread is not None:
                    thread.join(client_config.SERVER_STOP_TIMEOUT_S)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
