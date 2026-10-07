"""Régression SPEC-25 : depuis la 4.3.0 le client n'entrait plus dans l'écran de draft.

Symptôme : au champ select, la page de draft reste vide ou ne s'ouvre pas (`/draft`, `/draft/stage` et
les images attendent indéfiniment).

Cause racine : chaque `Sse.open` garde une connexion HTTP/1.1 ouverte, et Chromium n'en autorise que 6
par hôte. La pastille de phase (SPEC-25) a ajouté un flux `phase` aux 4 flux globaux + celui de la
draft : 6 connexions tenues, plus aucune pour les requêtes ordinaires (6 `ESTABLISHED` relevées sur le
port du client le 2026-10-07).

Correctif : les sujets `ingame` et `phase` partagent une seule connexion (`Sse.open` accepte une liste).

Prévention : ce test compte les flux ouverts par les scripts de la coque (tous chargés sur la page de
draft) et en exige un de moins que la limite du navigateur.
"""

import re
from pathlib import Path

CLIENT = Path("src/client")
CHROMIUM_CONNECTIONS_PER_HOST = 6


def test_les_flux_sse_laissent_une_connexion_libre_aux_requetes():
    base = (CLIENT / "templates" / "base.html").read_text(encoding="utf-8")
    scripts = re.findall(r'src="/static/([\w.]+\.js)"', base)
    streams = sum(
        (CLIENT / "static" / name).read_text(encoding="utf-8").count("Sse.open(")
        for name in scripts
        if name != "sse.js"
    )
    assert streams < CHROMIUM_CONNECTIONS_PER_HOST, (
        f"{streams} flux SSE tenus ouverts sur la page de draft : "
        "plus de connexion pour fetch ni htmx"
    )
