"""Écrans Parties et page d'une partie du client (SPEC-21 tâche 53), sur la partie réelle
7998195590 relevée par le spike du 2026-10-02 (équipe bleue victorieuse, 26 images)."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.client.app import create_app
from src.client.assets import Assets
from src.client.review import clock, game_page, games_view, load_model
from src.client.draft_view import Champions
from src.config_client import client_config
from src.repositories.coaching import CoachingRepository
from src.winprob.impact import impacts
from tests.test_winprob_impact import _model

LOCAL = "http://127.0.0.1"
FIXTURES = Path(__file__).parent / "fixtures" / "spike_gameplay"
GAME = json.loads((FIXTURES / "7998195590_game.json").read_text(encoding="utf-8"))
TIMELINE = json.loads((FIXTURES / "7998195590_timeline.json").read_text(encoding="utf-8"))
NOW = datetime(2026, 10, 5, 18, 0, tzinfo=timezone.utc)
CHAMPIONS = {
    "data": {
        "Olaf": {"key": "2", "id": "Olaf", "name": "Olaf", "tags": []},
        "Kled": {"key": "240", "id": "Kled", "name": "Kled", "tags": []},
        "Maokai": {"key": "57", "id": "Maokai", "name": "<script>alert(1)</script>", "tags": []},
    }
}
TOP = {1: "top", 6: "top"}


@pytest.fixture
def assets(tmp_path):
    base = client_config.DDRAGON_BASE
    files = {
        f"{base}/api/versions.json": json.dumps(["16.2.1"]).encode(),
        f"{base}/cdn/16.2.1/data/fr_FR/champion.json": json.dumps(CHAMPIONS).encode(),
    }
    return Assets(tmp_path / "cache", fetch=files.get)


@pytest.fixture
def modele(tmp_path, monkeypatch):
    path = tmp_path / "winprob_model.json"
    path.write_text(_model().to_json(), encoding="utf-8")
    monkeypatch.setattr("src.client.review.model_path", lambda: path)
    return _model()


def client(temp_db, assets):
    return TestClient(
        create_app(temp_db, assets=assets), base_url=LOCAL, raise_server_exceptions=False
    )


def capture(db, game_id=7998195590, pid=1, created="2026-10-05 16:00:00", timeline=True, raw=None):
    db.insert_game_record(
        game_id=game_id,
        queue_id=420,
        game_creation_utc=created,
        duration_s=GAME["gameDuration"],
        player_participant_id=pid,
        raw_game=raw or json.dumps(GAME),
        raw_timeline=json.dumps(TIMELINE) if timeline else None,
        raw_eog=None,
    )


def roles(db, game_id, by_participant=TOP):
    rows = [
        (game_id, participant, "cs_10", int(participant == 1), role, 0, 70.0) + (None,) * 9
        for participant, role in by_participant.items()
    ]
    CoachingRepository(db).insert_metrics(rows)


def impact(db, game_id=7998195590):
    result = impacts(_model(), GAME, TIMELINE)
    CoachingRepository(db).save_impact(game_id, _model().version, result["rows"])


# ---------- liste ----------


def test_liste_sur_base_vide(temp_db, assets):
    response = client(temp_db, assets).get("/parties")
    assert response.status_code == 200 and "Aucune partie capturée" in response.text


def test_la_liste_donne_resultat_kda_duree_et_adversaire(db, assets):
    capture(db, pid=1)
    roles(db, 7998195590)
    view = games_view(CoachingRepository(db), Champions(assets), NOW)
    row = view["rows"][0]
    stats = GAME["participants"][0]["stats"]
    assert row["win"] is True
    assert row["kda"] == f"{stats['kills']} / {stats['deaths']} / {stats['assists']}"
    assert row["duration"] == "24:48" and row["queue"] == "Classée solo/duo"
    assert (row["champion"], row["role"], row["opponent"]) == ("Olaf", "Top", "Kled")
    assert row["href"] == "/parties/7998195590"
    assert view["summary"] == "1 partie capturée · 1 V · 0 D"


def test_un_joueur_de_l_equipe_rouge_perd(db, assets):
    capture(db, pid=6)
    row = games_view(CoachingRepository(db), Champions(assets), NOW)["rows"][0]
    assert (
        row["win"] is False and row["opponent"] is None
    )  # poste inconnu : pas d'adversaire déduit


def test_la_liste_est_du_plus_recent_au_plus_ancien_avec_lp_et_impact(db, assets, modele):
    capture(db, game_id=1, created="2026-10-01 10:00:00")
    capture(db, game_id=7998195590, created="2026-10-05 16:00:00")
    impact(db)
    db.insert_rank_snapshot(
        queue="RANKED_SOLO_5x5",
        tier="EMERALD",
        division="II",
        lp=65,
        wins=62,
        losses=55,
        lp_delta=18,
        game_id=7998195590,
    )
    view = games_view(CoachingRepository(db), Champions(assets), NOW)
    assert [r["game_id"] for r in view["rows"]] == [7998195590, 1]
    first, second = view["rows"]
    assert first["lp"] == "+18 LP" and second["lp"] is None
    assert first["impact"].endswith(" pts") and second["impact"] is None
    assert first["ago"] == "il y a 1 h" and first["date"] == "5 oct."  # 16:00 + 24 min de partie


def test_une_partie_au_brut_illisible_ne_masque_pas_les_autres(db, assets):
    capture(db, game_id=1, raw="{}")
    capture(db, game_id=2, raw="pas du json")
    capture(db, game_id=3)
    view = games_view(CoachingRepository(db), Champions(assets), NOW)
    assert [r["game_id"] for r in view["rows"]] == [3]


def test_la_liste_est_bornee(db, assets, monkeypatch):
    monkeypatch.setattr(client_config, "PARTIES_LIMIT", 2)
    for i in range(1, 5):
        capture(db, game_id=i, created=f"2026-10-0{i} 10:00:00")
    view = games_view(CoachingRepository(db), Champions(assets), NOW)
    assert [r["game_id"] for r in view["rows"]] == [4, 3]


def test_route_liste_et_noms_echappes(db, temp_db, assets):
    capture(db, pid=2)  # Maokai : le nom de Data Dragon est hostile
    page = client(temp_db, assets).get("/parties").text
    assert "<script>alert(1)</script>" not in page and "&lt;script&gt;" in page
    assert 'href="/parties/7998195590"' in page


# ---------- page d'une partie ----------


def test_page_d_une_partie_inconnue(temp_db, assets):
    response = client(temp_db, assets).get("/parties/42")
    assert response.status_code == 404 and "Partie introuvable" in response.text


def test_page_avec_courbe_et_marqueurs(db, assets, modele):
    capture(db, pid=1)
    roles(db, 7998195590)
    impact(db)
    page = game_page(CoachingRepository(db), 7998195590, Champions(assets), modele, NOW)
    assert page["title"] == "Victoire" and page["opponent"] == "Kled"
    svg = str(page["curve"])
    assert svg.count('class="ch-line"') == 1
    assert 1 <= svg.count('class="ch-mark"') <= client_config.GAME_MARKS
    assert "0 %" in svg and "50 %" in svg and "100 %" in svg and "20 min" in svg
    assert page["impact"]["available"] is True


def test_la_courbe_de_l_equipe_rouge_est_inversee(db, assets, modele):
    capture(db, pid=1)
    capture(db, game_id=2, pid=6)
    repo, champions = CoachingRepository(db), Champions(assets)
    blue = game_page(repo, 7998195590, champions, modele, NOW)
    red = game_page(repo, 2, champions, modele, NOW)
    assert blue["win"] and not red["win"] and red["title"] == "Défaite"
    assert str(blue["curve"]) != str(red["curve"])


def test_les_plus_couteux_et_les_plus_rentables_du_joueur(db, assets, modele):
    capture(db, pid=5)  # tué à 1:34 (assisté par 7), puis à 16:07
    impact(db)
    page = game_page(CoachingRepository(db), 7998195590, Champions(assets), modele, NOW)
    costly = page["impact"]["costly"]
    assert 1 <= len(costly) <= client_config.GAME_TOP
    assert costly == sorted(costly, key=lambda e: e["mine_delta"])
    assert all(e["mine_delta"] < 0 for e in costly)
    assert any(
        e["time"] == "01:34" and e["label"] == "Mort" for e in costly
    )  # avec assistance : pas « solo »
    assert all(e["mine_delta"] > 0 for e in page["impact"]["profitable"])


def test_une_mort_en_solo_est_nommee(db, assets, modele):
    capture(db, pid=10)  # le participant 10 meurt seul
    impact(db)
    events = game_page(CoachingRepository(db), 7998195590, Champions(assets), modele, NOW)[
        "impact"
    ]["events"]
    assert any(e["label"] == "Mort solo" and e["mine"] and e["delta"] < 0 for e in events)


def test_un_evenement_de_l_adversaire_est_vu_de_mon_equipe(db, assets, modele):
    capture(db, pid=1)
    impact(db)
    events = game_page(CoachingRepository(db), 7998195590, Champions(assets), modele, NOW)[
        "impact"
    ]["events"]
    assert [e["ts"] for e in events] == sorted(e["ts"] for e in events)
    assert any(e["kind"] == "kill" and e["delta"] > 0 for e in events)  # un kill de mon équipe
    assert any(e["kind"] == "kill" and e["delta"] < 0 for e in events)  # une mort dans mon équipe
    assert all(e["color"] == "var(--rose)" for e in events if e["delta"] < 0)
    assert all(e["delta_text"][0] in "+−0" for e in events)


def test_sans_impact_la_courbe_s_affiche_et_le_dit(db, assets, modele):
    capture(db, pid=1)
    page = game_page(CoachingRepository(db), 7998195590, Champions(assets), modele, NOW)
    assert page["curve"] and page["impact"]["available"] is False
    assert page["impact_note"] == "Impact non calculé pour cette partie."


def test_sans_timeline_ni_courbe_ni_impact(db, assets, modele):
    capture(db, pid=1, timeline=False)
    page = game_page(CoachingRepository(db), 7998195590, Champions(assets), modele, NOW)
    assert page["curve"] is None and "Pas de timeline" in page["curve_note"]
    assert page["impact"]["available"] is False


def test_sans_modele_la_courbe_dit_comment_l_entrainer(db, assets):
    capture(db, pid=1)
    page = game_page(CoachingRepository(db), 7998195590, Champions(assets), None, NOW)
    assert page["curve"] is None and "retrain" in page["curve_note"]


def test_prediction_de_draft_rattachee_a_la_partie(db, assets, modele):
    capture(db, pid=1)
    prediction_id = db.insert_prediction([2], [240], None, 0.548, "b7-v1")
    db.update_prediction_outcome(prediction_id, 1, game_id=7998195590)
    page = game_page(CoachingRepository(db), 7998195590, Champions(assets), modele, NOW)
    assert page["predicted"] == "54,8 % · modèle b7-v1"


def test_route_page_d_une_partie(db, temp_db, assets, modele):
    capture(db, pid=1)
    impact(db)
    response = client(temp_db, assets).get("/parties/7998195590")
    assert response.status_code == 200
    assert "Victoire" in response.text and "Les plus coûteux" in response.text
    assert response.text.count('class="ch-line"') == 1


def test_la_consultation_n_ecrit_pas_dans_la_base(db, temp_db, assets, modele):
    capture(db, pid=1)
    impact(db)
    before = (temp_db.stat().st_mtime_ns, temp_db.read_bytes())
    web = client(temp_db, assets)
    assert web.get("/parties").status_code == 200
    assert web.get("/parties/7998195590").status_code == 200
    assert (temp_db.stat().st_mtime_ns, temp_db.read_bytes()) == before


def test_modele_illisible_ou_absent(tmp_path, monkeypatch):
    monkeypatch.setattr("src.client.review.model_path", lambda: tmp_path / "absent.json")
    assert load_model() is None
    broken = tmp_path / "casse.json"
    broken.write_text("{pas du json", encoding="utf-8")
    monkeypatch.setattr("src.client.review.model_path", lambda: broken)
    assert load_model() is None


def test_horloge():
    assert clock(0) == "00:00" and clock(1488) == "24:48" and clock(3725.9) == "62:05"


def test_points_de_win_chance_sans_zero_signe():
    from src.client.review import _pts

    assert _pts(-0.00004) == "0,0" and _pts(0.054) == "+5,4" and _pts(-0.0412) == "−4,1"
