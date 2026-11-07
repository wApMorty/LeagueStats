"""Régression — un clic sur l'écran Données faisait disparaître son panneau.

Symptôme (2026-11-07) : un clic sur un ELO du scrape (et de même sur « Actualiser », ou au
sondage pendant un run) vidait l'écran Données ; le choix était pourtant enregistré.

Cause racine : `#view` (`base.html`) porte `hx-select="#view"`, que htmx fait hériter à tout
descendant. Les requêtes du panneau gardaient donc ce filtre sur le fragment `#donnees-etat`
renvoyé, qui ne contient pas `#view` : htmx remplaçait le panneau par une sélection vide.

Correctif : le panneau pose son propre `hx-target`, `hx-select` et `hx-swap`, comme les
autres fragments du client (`pool_body.html`, `accueil_axes.html`).

Prévention : le fragment rendu doit porter `hx-select="#donnees-etat"` sur sa racine.
"""

import re

from fastapi.testclient import TestClient

from src.client.app import create_app
from src.client.assets import Assets
from src.client.donnees import UpdateJob
from src.pipeline import PipelineResult


def test_regression_panneau_donnees_garde_son_hx_select(temp_db, tmp_path):
    job = UpdateJob(run=lambda progress, stop: PipelineResult(status="ok"))
    app = create_app(
        temp_db, assets=Assets(tmp_path / "cache", fetch=lambda url: None), update_job=job
    )
    web = TestClient(app, base_url="http://127.0.0.1")
    fragment = web.get("/donnees/etat").text
    root = re.match(r"\s*<section[^>]*>", fragment).group(0)
    assert 'id="donnees-etat"' in root
    assert 'hx-select="#donnees-etat"' in root
