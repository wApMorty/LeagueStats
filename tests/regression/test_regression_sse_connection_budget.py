"""Régression SPEC-25 : depuis la 4.3.0 le client n'entrait plus dans l'écran de draft.

Symptôme : au champ select, la page Draft reste sur « Pas de champ select en cours », l'auto-ouverture
ne se fait pas et « Retour au coaching » ne ramène nulle part (aucun `fetch` ni navigation htmx ne part).

Cause racine : chaque `Sse.open` ouvrait son propre flux, et un flux SSE tient une connexion HTTP/1.1.
Chromium n'en accorde que 6 par hôte. Avec les 3 flux `lcu`, `ingame`, `game_captured` et, depuis la
pastille de phase (SPEC-25), `phase`, la page en tenait déjà 6 avant même la draft : plus aucune
connexion pour les requêtes (6 `ESTABLISHED` relevées sur le port du client, 6 abonnés au bus). Un
premier correctif à 5 flux globaux + celui de la draft retombait à 6.

Correctif : `sse.js` ouvre une seule connexion pour toute la page et distribue les événements aux
écouteurs par sujet.

Prévention : ce test exige qu'aucun script n'ouvre de connexion de son côté (une seule `fetch` vers
`/events`, dans `sse.js`) et que les écouteurs passent tous par `Sse.open`.
"""

import re
from pathlib import Path

STATIC = Path("src/client/static")


def _scripts():
    return [p for p in STATIC.glob("*.js") if not p.name.endswith(".min.js")]


def test_une_seule_connexion_sse_pour_toute_la_page():
    opens = {p.name: p.read_text(encoding="utf-8").count('fetch("/events') for p in _scripts()}
    assert opens["sse.js"] == 1 and sum(opens.values()) == 1, opens
    assert not any("new EventSource" in p.read_text(encoding="utf-8") for p in _scripts())


def test_les_ecouteurs_ne_filtrent_pas_par_la_requete():
    source = (STATIC / "sse.js").read_text(encoding="utf-8")
    assert "topic=" not in source  # un filtre par requête rouvrirait un flux par sujet
    assert re.search(r"topics\.has\(name\)", source)
