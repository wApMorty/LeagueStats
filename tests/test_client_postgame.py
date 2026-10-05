"""Post-game du client (SPEC-21 tâche 75) : événement `game_captured`, `/postgame` et `/parties/{id}`
en mode revue (impact, constats, LP, axes jugés), variante Défaite, rapport console remplacé en mode client.
"""

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from src.client.app import create_app
from src.client.assets import Assets
from src.client.bus import EventBus
from src.client.draft_view import Champions
from src.client.review import game_page
from src.coaching import findings
from src.coaching.capture import GameCapture
from src.config_constants import coaching_config
from src.repositories.coaching import CoachingRepository
from src.winprob.model import WinModel
from tests.test_client_parties import GAME, NOW, capture, impact, roles
from tests.test_coaching_capture import GAME_ID, TIMELINE, _match
from tests.test_winprob_impact import _model

LOCAL = "http://127.0.0.1"
STATIC = Path(__file__).parent.parent / "src" / "client" / "static"


@pytest.fixture
def assets(tmp_path):
    return Assets(tmp_path / "cache", fetch=lambda url: None)


@pytest.fixture
def modele(tmp_path, monkeypatch):
    path = tmp_path / "winprob_model.json"
    path.write_text(_model().to_json(), encoding="utf-8")
    monkeypatch.setattr("src.client.review.model_path", lambda: path)
    monkeypatch.setattr("src.winprob.pending.model_path", lambda: path)
    return _model()


def client(temp_db, assets):
    return TestClient(
        create_app(temp_db, assets=assets), base_url=LOCAL, raise_server_exceptions=False
    )


def page_of(db, assets, model, game_id=GAME_ID, review=False):
    return game_page(CoachingRepository(db), game_id, Champions(assets), model, NOW, review=review)


# ---------- événement et rapport console ----------


def post_game_capture(db, bus=None, game_ids=(GAME_ID,)):
    lcu = Mock()
    lcu.get_recent_matches.return_value = [_match(game_id=g) for g in game_ids]
    lcu.get_game_detail.return_value = GAME
    lcu.get_game_timeline.return_value = TIMELINE
    lcu.get_end_of_game_block.return_value = None
    lcu.get_lp_change_notification.return_value = {}
    monitor = SimpleNamespace(
        lcu=lcu, assistant=SimpleNamespace(db=db), verbose=True, **({"bus": bus} if bus else {})
    )
    return GameCapture(monitor)


def test_la_partie_capturee_est_annoncee_sur_le_bus(db):
    bus = EventBus()
    with bus.subscribe(["game_captured"]) as events:
        with patch.object(findings, "onetricks_objective", return_value={}):
            post_game_capture(db, bus).on_post_game()
        assert events.get(0.1) == ("game_captured", {"game_id": GAME_ID})
        assert events.get(0.05) is None  # une seule annonce
    assert bus.latest("game_captured") == {"game_id": GAME_ID}


def test_un_passage_sans_nouvelle_partie_n_annonce_rien(db):
    bus = EventBus()
    with patch.object(findings, "onetricks_objective", return_value={}):
        capture_pass = post_game_capture(db, bus)
        capture_pass.on_post_game()
        with bus.subscribe(["game_captured"]) as events:
            capture_pass.on_post_game()
            assert events.get(0.05) is None


def test_plusieurs_parties_capturees_annoncent_la_plus_recente(db):
    bus = EventBus()
    with patch.object(findings, "onetricks_objective", return_value={}):
        post_game_capture(db, bus, game_ids=(GAME_ID - 5, GAME_ID)).on_post_game()
    assert bus.latest("game_captured") == {"game_id": GAME_ID}


def test_sans_bus_le_mode_console_ne_change_pas(db, capsys):
    with patch.object(findings, "onetricks_objective", return_value={}):
        post_game_capture(db).on_post_game()
    assert "[DATA] Fin de partie : " in capsys.readouterr().out


def test_en_mode_client_la_revue_remplace_le_rapport_console(db, modele, capsys):
    bus = EventBus()
    with patch.object(findings, "onetricks_objective", return_value={}):
        post_game_capture(db, bus).on_post_game()
    out = capsys.readouterr().out
    assert "Fin de partie" not in out and "Impact sur la win chance" not in out
    assert "partie(s) capturée(s)" in out  # le reste de la console est inchangé
    # l'impact, lui, est calculé et rangé pour la page de revue
    assert CoachingRepository(db).impact_rows(GAME_ID)


def test_en_mode_console_l_impact_est_toujours_imprime(db, modele, capsys):
    with patch.object(findings, "onetricks_objective", return_value={}):
        post_game_capture(db).on_post_game()
    assert "Impact sur la win chance" in capsys.readouterr().out


def test_un_bus_en_panne_n_interrompt_pas_le_passage(db):
    bus = Mock()
    bus.publish.side_effect = RuntimeError("bus cassé")
    with patch.object(findings, "onetricks_objective", return_value={}):
        post_game_capture(db, bus).on_post_game()  # ne lève pas
    assert CoachingRepository(db).latest_game_id() == GAME_ID


# ---------- page ----------


def test_postgame_sans_partie(temp_db, assets):
    response = client(temp_db, assets).get("/postgame")
    assert response.status_code == 200
    assert "Aucune partie capturée pour l'instant" in response.text


def test_postgame_montre_la_derniere_partie_en_revue(db, temp_db, assets, modele):
    capture(db, game_id=1, pid=6, created="2026-10-01 10:00:00")
    capture(db, game_id=2, pid=1, created="2026-10-05 16:00:00")
    page = client(temp_db, assets).get("/postgame").text
    assert "Victoire" in page and "Revue de partie · il y a" in page
    assert 'class="nav-item" href="/postgame" style="--h: 345" aria-current="page"' in page


def test_une_partie_consultee_plus_tard_n_est_pas_une_revue(db, temp_db, assets, modele):
    capture(db, game_id=2, pid=1)
    page = client(temp_db, assets).get("/parties/2").text
    assert "Partie du 5 oct." in page and "Revue de partie" not in page


def test_la_page_complete_avec_impact_et_ecarts(db, temp_db, assets, modele):
    capture(db, pid=1)
    roles(db, GAME_ID)
    impact(db)
    page = client(temp_db, assets).get(f"/parties/{GAME_ID}").text
    for text in (
        "Impact par événement",
        "Ton impact attribué",
        "Les plus coûteux",
        "Les plus rentables",
        "Chance de victoire",
    ):
        assert text in page


# ---------- données ----------


def test_pile_d_impact_chronologique_et_bornee(db, assets, modele):
    capture(db, pid=1)
    impact(db)
    stack = page_of(db, assets, modele)["impact"]["stack"]
    assert 1 < len(stack) <= 10
    assert [e["ts"] for e in stack] == sorted(e["ts"] for e in stack)
    widths = [e["width"] for e in stack]
    assert max(widths) == 50.0 and all(
        0 <= w <= 50 for w in widths
    )  # la plus grande remplit la demi-barre
    assert all((e["left"] == 50.0) == (e["delta"] >= 0) for e in stack)
    assert all(e["delay"] >= 500 for e in stack)


def test_impact_attribue_et_residu(db, assets, modele):
    capture(db, pid=1)
    impact(db)
    impact_part = page_of(db, assets, modele)["impact"]
    rows = CoachingRepository(db).impact_rows(GAME_ID, 1)
    attributed = sum(r["delta_p"] for r in rows)
    expected = f"{attributed * 100:+.1f}".replace("-", "−").replace(".", ",")
    assert impact_part["attributed"] == expected
    assert impact_part["residual"] is not None


def test_le_residu_n_est_pas_affiche_avec_un_autre_modele(db, assets, modele):
    capture(db, pid=1)
    other = WinModel(modele.inputs, modele.mean, modele.scale, [w + 0.1 for w in modele.weights])
    assert other.version != modele.version
    impact(db)  # rangé avec la version du modèle d'origine
    part = page_of(db, assets, other)["impact"]
    assert part["available"] and part["residual"] is None  # recalculé, il ne correspondrait plus


def test_points_de_lp_de_la_partie(db, assets, modele):
    capture(db, pid=1)
    db.insert_rank_snapshot(
        queue="RANKED_SOLO_5x5",
        tier="EMERALD",
        division="II",
        lp=65,
        wins=62,
        losses=55,
        lp_delta=18,
        game_id=GAME_ID,
    )
    lp = page_of(db, assets, modele)["lp"]
    assert lp == {"delta": "+18", "gain": True, "value": 18, "rank": "Émeraude II · 65 LP"}


def test_sans_photo_de_rang_pas_de_lp(db, assets, modele):
    capture(db, pid=1)
    assert page_of(db, assets, modele)["lp"] is None


def test_les_axes_juges_sur_la_partie(db, assets, modele):
    capture(db, pid=1)
    repo = CoachingRepository(db)
    repo.insert_goal("deaths_before_14", "top", 1.0, "proposed")
    repo.insert_goal("xp_diff_15", "top", 0.0, "player")
    repo.insert_verdict(1, GAME_ID, 2.0, False)
    repo.insert_verdict(2, GAME_ID, 140.0, True)
    axes = page_of(db, assets, modele)["axes"]
    assert [a["held"] for a in axes] == [False, True]
    assert axes[0]["text"] == "Axe « Morts avant 14 min » : non tenu (2, cible ≤ 1)"
    assert axes[1]["text"] == "Axe « Écart d'XP @15 » : tenu (+140, cible ≥ +0)"


def test_ecarts_a_la_norme_et_a_l_objectif(db, assets, modele):
    capture(db, pid=1)
    repo = CoachingRepository(db)
    n = coaching_config.MIN_NORM_SAMPLE
    repo.insert_metrics(
        [
            (GAME_ID, 1, "cs_10", 1, "top", 2, 74.0, 71.0, 6.0, n, 0.5)
            + (78.0, 5.0, "OneTricks", 0.3, coaching_config.GRID_VERSION),
            (GAME_ID, 1, "gold_diff_15", 1, "top", 2, 240.0, 0.0, 300.0, n, 0.8)
            + (None, None, None, None, coaching_config.GRID_VERSION),
            (GAME_ID, 1, "solo_deaths", 1, "top", 2, 3.0, 1.6, 0.8, n - 1, -1.75)
            + (None, None, None, None, coaching_config.GRID_VERSION),
        ]
    )
    repo.insert_findings(
        [
            (GAME_ID, "cs_10", "positive", 0.5, "norm", 1),
            (GAME_ID, "gold_diff_15", "positive", 0.8, "norm", 2),
            (GAME_ID, "solo_deaths", "negative", -1.75, "objective", 1),
        ]
    )
    rows = page_of(db, assets, modele)["findings"]
    assert [(r["label"], r["value"], r["reference"], r["good"]) for r in rows] == [
        ("Morts en solo", "3", "—", False),  # norme en construction : pas affichée
        ("CS @10", "74", "norme 71 · obj. 78", True),
        ("Écart d'or @15", "+240", "norme 0", True),
    ]


def test_variante_defaite(db, temp_db, assets, modele):
    capture(db, pid=6)
    db.insert_rank_snapshot(
        queue="RANKED_SOLO_5x5",
        tier="EMERALD",
        division="II",
        lp=47,
        wins=62,
        losses=56,
        lp_delta=-17,
        game_id=GAME_ID,
    )
    page = page_of(db, assets, modele)
    assert page["title"] == "Défaite" and page["win"] is False
    assert (
        page["lp"]["gain"] is False and page["lp"]["delta"] == "−17" and page["lp"]["value"] == 17
    )
    html = client(temp_db, assets).get(f"/parties/{GAME_ID}").text
    assert 'class="game-title loss"' in html and 'class="lp-gain loss"' in html


def test_sans_impact_la_page_le_dit_et_garde_la_courbe(db, temp_db, assets, modele):
    capture(db, pid=1)
    html = client(temp_db, assets).get("/postgame").text
    assert "Impact non calculé pour cette partie." in html and 'class="ch-line"' in html
    assert "Impact par événement" not in html


def test_une_partie_sans_analyse_s_affiche(db, temp_db, assets, modele):
    """Sans poste ni constat (partie non analysée), la page répond quand même."""
    capture(db, pid=1)
    response = client(temp_db, assets).get("/postgame")
    assert response.status_code == 200
    assert (
        "Champion 2" in response.text
    )  # Data Dragon hors ligne : le nom retombe sur l'identifiant


def test_la_consultation_n_ecrit_pas_dans_la_base(db, temp_db, assets, modele):
    capture(db, pid=1)
    impact(db)
    before = (temp_db.stat().st_mtime_ns, temp_db.read_bytes())
    assert client(temp_db, assets).get("/postgame").status_code == 200
    assert (temp_db.stat().st_mtime_ns, temp_db.read_bytes()) == before


# ---------- front ----------


@pytest.mark.skipif(shutil.which("node") is None, reason="node absent")
def test_coaching_js_est_valide():
    assert subprocess.run(["node", "--check", str(STATIC / "coaching.js")]).returncode == 0


def test_le_client_ecoute_game_captured_sans_quitter_une_draft():
    script = (STATIC / "coaching.js").read_text(encoding="utf-8")
    assert 'Sse?.open("game_captured"' in script
    assert 'getElementById("draft")' in script  # jamais en pleine draft
    assert "/postgame" in script
