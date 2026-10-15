"""Mode démo du client (SPEC-34 §4.3) : faux LCU, isolation de la base et des journaux."""

import hashlib
import sqlite3
from pathlib import Path

import psutil
import pytest

from scripts import demo_client as demo
from src.config import config
from src.draft import tick_timer
from src.draft.phases import is_draft_complete
from src.draft.state_parser import DraftStateParser
from src.lcu_client import LCUClient
from src.winprob import live

SCENARIO = demo.load_scenario()
# Ids factices : le test ne lit jamais la vraie base, seuls les noms du scénario comptent.
IDS = {
    name: index + 1
    for index, name in enumerate(sorted({name for _cell, _kind, name in SCENARIO["draft"]}))
}


@pytest.fixture
def fake():
    return demo.FakeLcu(SCENARIO, IDS)


def _parse_current(fake):
    """La session de la scène courante, lue par le vrai parseur du Live Coach."""
    session = fake.read("/lol-champ-select/v1/session")
    state, _ = DraftStateParser(LCUClient(), str).parse(session, {}, {})
    return state


def _parse(fake, scene):
    fake.set_scene(scene)
    return _parse_current(fake)


@pytest.fixture
def lcu_url(fake, monkeypatch):
    """Le faux LCU servi sur un port libre, tous les `LCUClient` pointés dessus."""
    httpd, url = demo.serve(fake)
    demo.point_to(url, monkeypatch.setattr)
    yield url
    httpd.shutdown()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_faux_lcu_sert_les_fixtures_et_rien_d_autre(fake):
    assert fake.read("/lol-summoner/v1/current-summoner")["gameName"] == "Démo"
    assert fake.read("/lol-gameflow/v1/gameflow-phase") == "None"
    assert fake.read("/lol-match-history/v1/games/123")["gameId"] == 123
    history = "/lol-match-history/v1/products/lol/current-summoner/matches?begIndex=0&endIndex=19"
    assert len(fake.read(history)["games"]["games"]) == 20
    assert fake.read("/lol-store/v1/catalog") is None
    assert fake.read("/lol-summoner/v1/current-summoner/extra") is None  # motif complet


def test_un_lcu_client_ne_parle_qu_au_faux_lcu(lcu_url, monkeypatch):
    def interdit(*_args, **_kwargs):
        raise AssertionError("le vrai client LoL a été cherché")

    monkeypatch.setattr(psutil, "process_iter", interdit)
    lcu = LCUClient()
    assert lcu.connect()
    assert lcu.credentials.base_url == lcu_url
    assert lcu._make_request("/lol-gameflow/v1/gameflow-phase") == "None"
    assert lcu._make_request("/lol-store/v1/catalog") is None
    assert lcu.last_status_code == 404
    assert lcu._make_request("/lol-lobby/v2/lobby", "POST", {"queueId": 420}) == {}
    assert live.URL == f"{lcu_url}{demo.LIVE_PATH}"
    assert live.fetch() is None  # aucune partie dans la scène d'accueil


def test_isolate_ne_touche_jamais_la_base_source(temp_db, tmp_path, monkeypatch):
    source = Path(temp_db)
    before = (_sha(source), source.stat().st_mtime_ns)
    workdir = tmp_path / "demo"
    patches = demo.isolate(source, workdir, monkeypatch.setattr)

    copy = Path(config.DATABASE_PATH)
    assert copy.parent == workdir and copy != source
    with sqlite3.connect(copy) as connection:
        connection.execute("CREATE TABLE demo_write (x INTEGER)")
    assert (_sha(source), source.stat().st_mtime_ns) == before
    assert workdir in Path(tick_timer._LOG_PATH).parents
    for _target, _name, value in patches:
        if isinstance(value, (str, Path)):
            assert workdir in Path(value).parents


def test_liste_des_scenes_du_client(fake):
    assert fake.names()[:3] == ["accueil", "profil", "historique"]
    fake.set_scene("profil")
    assert fake.phase() == "None"
    with pytest.raises(KeyError):
        fake.set_scene("inconnue")


def test_chaque_scene_de_draft_se_lit_comme_une_vraie_session(fake):
    local = SCENARIO["local_cell"]
    bans = _parse(fake, "draft-bans")
    assert bans.phase == "BAN_PICK" and local in bans.acting_cells
    assert not bans.ally_picks and not bans.ally_bans  # bans simultanés, aucun terminé

    pick = _parse(fake, "draft-pick")
    assert len(pick.ally_bans) == 5 and len(pick.enemy_bans) == 5
    assert [IDS["Vi"], IDS["Orianna"], IDS["Caitlyn"]] == pick.ally_picks
    assert len(pick.enemy_picks) == 4 and IDS["Darius"] in pick.enemy_picks
    assert pick.acting_cells == {3, 4} and pick.ally_positions[local] == "top"
    assert next(c for c in pick.ally_cells if c.cell_id == 4).hover_id == IDS["Nautilus"]

    lock = _parse(fake, "draft-lock")
    assert lock.phase == "FINALIZATION" and is_draft_complete(lock) and not lock.acting_cells
    for scene in fake.names():
        fake.set_scene(scene)
        if fake.phase() != "ChampSelect":
            assert fake.read("/lol-champ-select/v1/session") is None


def test_un_verrouillage_s_applique_puis_la_scene_repart_du_scenario(fake):
    fake.set_scene("draft-pick")
    my_action = 17  # 10 bans puis 7 picks : la 18e action est la mienne (cellule 3)
    path = f"/lol-champ-select/v1/session/actions/{my_action}"
    assert fake.write("PATCH", path, {"championId": IDS["DrMundo"], "completed": True}) == {}
    state = _parse_current(fake)
    assert IDS["DrMundo"] in state.ally_picks and 3 not in state.acting_cells
    assert fake.write("PATCH", "/lol-champ-select/v1/session/actions/999", {}) is None
    fake.set_scene("draft-pick")
    assert IDS["DrMundo"] not in _parse_current(fake).ally_picks


def test_en_partie_la_session_gameflow_porte_les_dix_joueurs(fake):
    fake.set_scene("chargement")
    data = fake.read("/lol-gameflow/v1/session")["gameData"]
    players = data["teamOne"] + data["teamTwo"]
    assert len(players) == 10 and all(p["puuid"] and p["championId"] for p in players)
    fake.set_scene("trouvee")
    assert fake.read("/lol-matchmaking/v1/ready-check")["state"] == "InProgress"
