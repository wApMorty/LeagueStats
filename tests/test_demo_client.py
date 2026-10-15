"""Mode démo du client (SPEC-34 §4.3) : faux LCU, isolation de la base et des journaux."""

import hashlib
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import psutil
import pytest

from scripts import demo_client as demo
from src.client.bus import EventBus
from src.client.ingame import TOPIC, LiveGame
from src.config import config
from src.config_constants import demo_config
from src.draft import tick_timer
from src.draft.phases import is_draft_complete
from src.draft.state_parser import DraftStateParser
from src.lcu_client import LCUClient
from src.winprob import live
from src.winprob.model import INPUTS, WinModel

SCENARIO = demo.load_scenario()
GAME = SCENARIO["game"]
TEMPLATE = json.loads(demo.ALLGAMEDATA_PATH.read_text(encoding="utf-8"))
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
    source.with_name("winprob_model.json").write_text("{}", encoding="utf-8")
    before = (_sha(source), source.stat().st_mtime_ns)
    workdir = tmp_path / "demo"
    patches = demo.isolate(source, workdir, monkeypatch.setattr)

    copy = Path(config.DATABASE_PATH)
    assert copy.parent == workdir and copy != source
    with sqlite3.connect(copy) as connection:
        connection.execute("CREATE TABLE demo_write (x INTEGER)")
    assert (_sha(source), source.stat().st_mtime_ns) == before
    assert workdir in Path(tick_timer._LOG_PATH).parents
    assert (workdir / "winprob_model.json").exists()  # la win chance se lit à côté de la copie
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


def _model():
    """Modèle jouet (même forme que `tests/test_winprob_scout.py::_model`) : les kills et tours pèsent."""
    d = 2 * len(INPUTS)
    weights = [0.0] * (d + 1)
    weights[INPUTS.index("kills")] = 0.5
    weights[INPUTS.index("towers")] = 0.5
    return WinModel(INPUTS, [0.0] * d, [1.0] * d, weights)


def test_la_partie_simulee_donne_une_courbe_qui_monte_et_une_win_chance_qui_bouge():
    bus = EventBus()
    live_game = LiveGame(bus, lambda: "InProgress", fetch=lambda: None, model=_model())
    step, duration = int(demo_config.INGAME_FRAME_STEP_S), int(GAME["duration_s"])
    levels = {i: [] for i in range(10)}
    for t in range(0, duration + 1, step):
        image = demo.frame(float(t), GAME, TEMPLATE)
        live_game._read(image)
        for i, player in enumerate(image["allPlayers"]):
            levels[i].append((player["level"], player["scores"]["creepScore"]))
    times = [point[0] for point in live_game.series]
    assert len(times) > 20 and all(a < b for a, b in zip(times, times[1:]))
    for values in levels.values():
        assert all(a <= b for a, b in zip(values, values[1:]))

    # win chance avant et après le premier kill (95 s) : elle doit bouger
    first_kill = min(e[0] for e in GAME["events"] if e[1] == "ChampionKill")
    live_game = LiveGame(bus, lambda: "InProgress", fetch=lambda: None, model=_model())
    live_game._read(demo.frame(first_kill - 1.0, GAME, TEMPLATE))
    p_before = bus.latest(TOPIC)["p"]
    live_game._read(demo.frame(float(first_kill), GAME, TEMPLATE))
    assert bus.latest(TOPIC)["p"] != p_before


def test_hors_partie_404_et_gametime_zero_en_chargement(fake):
    for scene in ("accueil", "fin", "draft-pick"):
        fake.set_scene(scene)
        assert fake.read(demo.LIVE_PATH) is None
    fake.set_scene("chargement")
    assert fake.read(demo.LIVE_PATH)["gameData"]["gameTime"] == 0.0


def test_horloge_de_la_partie_avance_puis_se_fige(fake, monkeypatch):
    clock = {"now": 100.0}
    monkeypatch.setattr(demo, "time", SimpleNamespace(monotonic=lambda: clock["now"]))
    fake.set_scene("en-partie")
    assert fake.read(demo.LIVE_PATH)["gameData"]["gameTime"] == 0.0
    clock["now"] += demo_config.INGAME_FRAME_PERIOD_S
    assert fake.read(demo.LIVE_PATH)["gameData"]["gameTime"] == demo_config.INGAME_FRAME_STEP_S
    clock["now"] += 10_000
    assert fake.read(demo.LIVE_PATH)["gameData"]["gameTime"] == GAME["duration_s"]


def test_historique_stable_par_puuid_et_different_d_un_autre(fake):
    path = "/lol-match-history/v1/products/lol/{}/matches?begIndex=0&endIndex=19"
    first = fake.read(path.format("demo-puuid-0"))
    assert first == fake.read(path.format("demo-puuid-0"))
    assert first != fake.read(path.format("demo-puuid-1"))
    assert len(first["games"]["games"]) == 20


def test_la_revue_annonce_la_derniere_partie_de_la_copie(temp_db, tmp_path, monkeypatch, fake):
    with sqlite3.connect(temp_db) as connection:
        for game_id in (111, 222):
            connection.execute(
                "INSERT INTO game_records (game_id, queue_id, game_creation_utc, captured_utc, "
                "raw_game) VALUES (?, ?, ?, ?, ?)",
                (game_id, 420, "2026-10-01T00:00:00", "2026-10-01T00:30:00", "{}"),
            )
    monkeypatch.setattr(config, "DATABASE_PATH", str(temp_db))
    bus = EventBus()
    handle = demo.DemoHandle("http://127.0.0.1:1", bus, fake, tmp_path / "demo", [])
    handle.goto("revue")
    assert bus.latest("game_captured") == {"game_id": 222}


def test_la_revue_sans_base_ne_publie_rien_et_ne_leve_pas(fake, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATABASE_PATH", str(tmp_path / "absente.db"))
    bus = EventBus()
    handle = demo.DemoHandle("http://127.0.0.1:1", bus, fake, tmp_path / "demo", [])
    handle.goto("revue")
    assert fake.scene["name"] == "revue" and bus.latest("game_captured") is None


class _Idle:
    """Live Coach et `LiveGame` inertes : le test ne vérifie que le câblage de `start_demo`."""

    def __init__(self, *_args, **_kwargs):
        self.send = lambda line: False

    def start(self):
        pass

    def stop(self):
        pass


def test_start_demo_isole_la_base_puis_defait_tout_a_l_arret(temp_db, monkeypatch):
    monkeypatch.setattr(demo, "LiveCoachThread", _Idle)
    monkeypatch.setattr(demo, "LiveGame", _Idle)
    monkeypatch.setattr(demo.server, "start", lambda *args, **kwargs: "http://127.0.0.1:1")
    monkeypatch.setattr(demo.server, "stop", lambda: None)
    source = Path(temp_db)
    before = (_sha(source), source.stat().st_mtime_ns)
    original = (config.DATABASE_PATH, live.URL, LCUClient.find_lcu_credentials)

    assert demo.start_demo("inconnue", window=False, db_src=source) is None
    handle = demo.start_demo("accueil", window=False, db_src=source)
    assert handle is not None
    copy = Path(config.DATABASE_PATH)
    assert copy != source and copy.exists()
    connection = sqlite3.connect(copy)
    connection.execute("CREATE TABLE demo_write (x INTEGER)")
    connection.close()  # sous Windows, un fichier ouvert empêcherait la suppression du dossier
    assert LCUClient().find_lcu_credentials().password == "demo"
    handle.stop()

    assert (_sha(source), source.stat().st_mtime_ns) == before
    assert (config.DATABASE_PATH, live.URL, LCUClient.find_lcu_credentials) == original
    assert not copy.parent.exists()
    second = demo.start_demo("accueil", window=False, db_src=source)  # même processus
    assert second is not None
    second.stop()
