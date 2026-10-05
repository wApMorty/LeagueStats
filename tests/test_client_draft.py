"""Écran de draft du client (SPEC-21 tâche 73) : cadre, sceaux, balance, fragments synchronisables."""

import json
from dataclasses import asdict
from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient

from src.client import draft_view
from src.client.app import create_app
from src.client.assets import Assets
from src.client.bus import EventBus
from src.config_client import client_config
from src.draft.snapshot import (
    DraftSnapshot,
    SnapshotBan,
    SnapshotPlayer,
    SnapshotRecommendation,
    SnapshotSkipped,
)

LOCAL = "http://127.0.0.1"
BASE = client_config.DDRAGON_BASE
CHAMPIONS = {
    "data": {
        name: {"key": str(key), "id": ident, "name": name, "tags": []}
        for key, ident, name in [
            (266, "Aatrox", "Aatrox"),
            (122, "Darius", "Darius"),
            (64, "LeeSin", "Lee Sin"),
            (103, "Ahri", "Ahri"),
            (222, "Jinx", "Jinx"),
            (12, "Alistar", "Alistar"),
            (23, "Tryndamere", "Tryndamere"),
            (777, "Yone", "Yone"),
        ]
    }
}


@pytest.fixture
def assets(tmp_path, monkeypatch):
    monkeypatch.setattr(client_config, "DDRAGON_VERSION", "16.2.1")
    files = {f"{BASE}/cdn/16.2.1/data/fr_FR/champion.json": json.dumps(CHAMPIONS).encode()}
    return Assets(tmp_path / "cache", fetch=files.get)


@pytest.fixture
def bus():
    return EventBus()


@pytest.fixture
def client(temp_db, bus, assets):
    app = create_app(temp_db, bus=bus, assets=assets)
    return TestClient(app, base_url=LOCAL, raise_server_exceptions=False)


def player(team, cell, champion_id=0, name=None, role=None, **extra):
    return SnapshotPlayer(
        team=team, cell_id=cell, champion_id=champion_id, champion=name, role=role, **extra
    )


def pick_snapshot(**overrides):
    """Moi (top, cellule 0, rien de verrouillé), Alistar et Jinx alliés, Tryndamere et Lee Sin adverses."""
    snapshot = DraftSnapshot(
        phase="BAN_PICK",
        kind="pick",
        my_turn=True,
        acting_cell=0,
        local_cell=0,
        local_role="top",
        time_left_ms=22000,
        time_total_ms=30000,
        allies=[
            player(
                "ally", 0, role="top", is_local=True, is_acting=True, hover_id=266, hover="Aatrox"
            ),
            player("ally", 1, 12, "Alistar", "support", role_source="lcu"),
            player("ally", 2, 222, "Jinx", "bottom", role_source="lcu"),
            player("ally", 3, role="jungle"),
            player("ally", 4, role="middle", hover_id=103, hover="Ahri"),
        ],
        enemies=[
            player(
                "enemy", 5, 23, "Tryndamere", "top", role_source="inferred", role_confidence=0.82
            ),
            player(
                "enemy", 6, 64, "Lee Sin", "jungle", role_source="inferred", role_confidence=0.97
            ),
            player("enemy", 7),
            player("enemy", 8),
            player("enemy", 9),
        ],
        ally_bans=[SnapshotBan(777, "Yone", "ally")],
        enemy_bans=[SnapshotBan(122, "Darius", "enemy")],
        recommendations=[
            SnapshotRecommendation(
                "Aatrox",
                266,
                "top",
                0.5482,
                3.1,
                2,
                1200,
                [{"champion": "Alistar", "lane": "support"}],
            ),
            SnapshotRecommendation("Darius", 122, "top", 0.5307, 1.4, 2, 860, []),
        ],
        skipped=[SnapshotSkipped("Ambessa", 38, champion_id=None)],
        depth=2,
        base_probability=0.517,
        projected_probability=0.5482,
        pool_name="GRIND",
    )
    for key, value in overrides.items():
        setattr(snapshot, key, value)
    return asdict(snapshot)


def ban_snapshot(**overrides):
    snapshot = DraftSnapshot(
        phase="BAN_PICK",
        kind="ban",
        my_turn=True,
        local_cell=0,
        local_role="top",
        allies=[
            player("ally", i, role=r, is_local=i == 0)
            for i, r in enumerate(["top", "jungle", "middle", "bottom", "support"])
        ],
        enemies=[player("enemy", 5 + i) for i in range(5)],
        ally_bans=[SnapshotBan(777, "Yone", "ally")],
        base_probability=0.5,
        projected_probability=0.5,
    )
    for key, value in overrides.items():
        setattr(snapshot, key, value)
    return asdict(snapshot)


class Tree(HTMLParser):
    """Enfants directs des conteneurs `data-sync`, pour vérifier le contrat de synchronisation."""

    def __init__(self):
        super().__init__()
        self.stack = []
        self.orphans = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if self.stack and self.stack[-1][1] and not ("data-key" in attrs and "data-sig" in attrs):
            self.orphans.append((tag, attrs.get("class")))
        if tag not in ("img", "br", "input", "meta", "link", "circle", "path"):
            self.stack.append((tag, "data-sync" in attrs))

    def handle_startendtag(self, tag, attrs):
        attrs = dict(attrs)
        if self.stack and self.stack[-1][1] and not ("data-key" in attrs and "data-sig" in attrs):
            self.orphans.append((tag, attrs.get("class")))

    def handle_endtag(self, tag):
        if self.stack and self.stack[-1][0] == tag:
            self.stack.pop()


def state_of(html):
    import re

    return json.loads(re.search(r"data-state='([^']*)'", html).group(1))


# ---------- page et fragment ----------


def test_page_sans_snapshot_etat_vide_sans_navigation(client):
    response = client.get("/draft")
    html = response.text
    assert response.status_code == 200
    assert "Pas de champ select en cours" in html
    assert 'id="draft"' in html and 'class="nav"' not in html and "page-draft" in html


def test_navigation_garde_l_entree_draft_active(client):
    assert 'href="/draft"' in client.get("/").text
    assert client.get("/draft").status_code == 200


def test_fragment_sans_snapshot_etat_vide(client):
    html = client.get("/draft/stage").text
    assert "Pas de champ select" in html and "<html" not in html


def test_page_et_fragment_rendent_le_meme_ecran(client, bus):
    bus.publish("draft", pick_snapshot())
    page, fragment = client.get("/draft").text, client.get("/draft/stage").text
    assert state_of(page) == state_of(fragment)
    for name in ("Alistar", "Tryndamere", "Jinx"):
        assert name in page and name in fragment


def test_tous_les_enfants_d_un_conteneur_synchronise_ont_cle_et_empreinte(client, bus):
    for snapshot in (None, pick_snapshot(), ban_snapshot()):
        if snapshot:
            bus.publish("draft", snapshot)
        tree = Tree()
        tree.feed(client.get("/draft/stage").text)
        assert tree.orphans == []


def test_empreinte_stable_et_sensible_au_contenu():
    assert draft_view.signature({"a": 1, "b": [2]}) == draft_view.signature({"b": [2], "a": 1})
    assert draft_view.signature({"a": 1}) != draft_view.signature({"a": 2})


def test_fragment_identique_donne_des_empreintes_identiques(client, bus):
    bus.publish("draft", pick_snapshot())
    import re

    sigs = lambda html: re.findall(r'data-sig="([^"]+)"', html)
    assert sigs(client.get("/draft/stage").text) == sigs(client.get("/draft/stage").text)


# ---------- sceaux ----------


def test_sceaux_moi_alliés_et_adversaires(client, bus):
    bus.publish("draft", pick_snapshot())
    html = client.get("/draft/stage").text
    assert html.count("d-member-ally") == 4 and html.count("d-member-enemy") == 5
    assert "Toi · Top" in html and "Aatrox" in html  # mon survol
    assert "déduit 82 %" in html and "déduit 97 %" in html
    assert "verrouillé" in html and "survol" in html
    assert (
        'src="/assets/champion/Alistar.png"' in html and 'src="/assets/champion/Jinx.png"' in html
    )


def test_alliés_sur_les_branches_4_3_2_1_dans_l_ordre_des_rôles(client, bus):
    bus.publish("draft", pick_snapshot())
    seal = client.get("/draft/stage").text.split("d-seal-ally")[1].split("d-seal-foe")[0]
    import re

    positions = re.findall(r'--l: ([\d.]+)px; --t: ([\d.]+)px[^>]*data-champion="(\d*)"', seal)
    # jungle (inconnu), mid (Ahri survolé), bot (Jinx), support (Alistar) : branches 4, 3, 2, 1
    expected = [draft_view._branch_point(b) for b in (4, 3, 2, 1)]
    assert [(float(l), float(t)) for l, t, _ in positions] == expected
    assert [c for _, _, c in positions][2:] == ["222", "12"]


def test_adversaire_place_selon_son_role_les_inconnus_sur_les_branches_libres(client, bus):
    bus.publish("draft", pick_snapshot())
    foe = client.get("/draft/stage").text.split("d-seal-foe")[1]
    import re

    positions = re.findall(r'--l: ([\d.]+)px; --t: ([\d.]+)px[^>]*data-champion="(\d*)"', foe)
    by_champion = {c: (float(l), float(t)) for l, t, c in positions if c}
    assert by_champion["23"] == draft_view._branch_point(0)  # Tryndamere top
    assert by_champion["64"] == draft_view._branch_point(1)  # Lee Sin jungle
    assert len(positions) == 5
    assert foe.count("d-pending") == 3  # trois adversaires pas encore choisis


def test_survol_d_un_allie_est_decrit_sans_etre_un_pick(client, bus):
    bus.publish("draft", pick_snapshot())
    html = client.get("/draft/stage").text
    assert html.count("d-hover") >= 1 and "Ahri" in html and "survol" in html


def test_phase_de_bans_adversaires_inconnus_et_bans_caches(client, bus):
    bus.publish("draft", ban_snapshot())
    html = client.get("/draft/stage").text
    assert "Phase de bans — choisis ton ban" in html
    assert html.count("Inconnu") == 5 and html.count("d-ban-hidden") >= 5
    assert "Bans adverses · cachés" in html and "Bans alliés · ton ban" in html


def test_mon_ban_pose_survole_ou_ouvert(client, bus):
    for extra, state in (
        ({}, "open"),
        ({"my_ban_hover": asdict(SnapshotBan(266, "Aatrox", "ally"))}, "aim"),
        ({"my_ban": asdict(SnapshotBan(266, "Aatrox", "ally"))}, "done"),
    ):
        bus.publish("draft", ban_snapshot(**extra))
        html = client.get("/draft/stage").text
        assert f'class="d-ban d-ban-ally d-ban-{state} d-ban-me"' in html


def test_bans_revelés_apres_la_phase_de_bans(client, bus):
    bus.publish("draft", pick_snapshot())
    html = client.get("/draft/stage").text
    assert "Bans adverses<" in html and 'title="Darius"' in html and 'title="Yone"' in html


# ---------- état pour le script ----------


def test_état_chrono_balance_et_probabilités(client, bus):
    bus.publish("draft", pick_snapshot())
    state = state_of(client.get("/draft/stage").text)
    assert state["phase"] == "pick_turn" and state["time_left_ms"] == 22000
    assert state["win"] == {"266": 0.5482, "122": 0.5307}
    assert state["shown"] == pytest.approx(0.5482) and state["base"] == pytest.approx(0.517)
    assert state["hover_id"] == 266 and state["locked_id"] == 0
    assert state["names"]["266"] == "Aatrox"


def test_phases(client, bus):
    cases = [
        (ban_snapshot(), "ban"),
        (pick_snapshot(my_turn=False), "pick_wait"),
        (pick_snapshot(), "pick_turn"),
    ]
    locked = pick_snapshot()
    locked["allies"][0].update(champion_id=266, champion="Aatrox", hover_id=0, hover=None)
    cases.append((locked, "locked"))
    final = json.loads(json.dumps(locked))
    final["phase"] = "FINALIZATION"
    cases.append((final, "final"))
    for snapshot, expected in cases:
        bus.publish("draft", snapshot)
        assert state_of(client.get("/draft/stage").text)["phase"] == expected


def test_verrouillé_montre_le_sceau_et_cache_le_cercle_pointillé(client, bus):
    snapshot = pick_snapshot()
    snapshot["allies"][0].update(champion_id=266, champion="Aatrox", hover_id=0, hover=None)
    bus.publish("draft", snapshot)
    html = client.get("/draft/stage").text
    assert "d-lock" in html and "d-dashring-me" not in html


def test_sans_probabilité_la_balance_reste_vide(client, bus):
    bus.publish("draft", ban_snapshot(base_probability=None, projected_probability=None))
    assert state_of(client.get("/draft/stage").text)["shown"] is None


def test_noms_echappés(client, bus):
    snapshot = pick_snapshot()
    snapshot["allies"][1]["champion"] = "<script>alert(1)</script>"
    bus.publish("draft", snapshot)
    html = client.get("/draft/stage").text
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html


def test_portraits_absents_sans_data_dragon(temp_db, bus, tmp_path):
    hors_ligne = Assets(tmp_path / "vide", fetch=lambda url: None)
    client = TestClient(create_app(temp_db, bus=bus, assets=hors_ligne), base_url=LOCAL)
    bus.publish("draft", pick_snapshot())
    response = client.get("/draft/stage")
    assert response.status_code == 200 and "/assets/champion/" not in response.text


def test_bus_latest_renvoie_le_dernier_snapshot(bus):
    assert bus.latest("draft") is None
    bus.publish("draft", {"n": 1})
    bus.publish("draft", {"n": 2})
    bus.publish("lcu", {"n": 3})
    assert bus.latest("draft") == {"n": 2}


def test_aides_de_format():
    assert draft_view.fr(54.8212, 2) == "54,82"
    assert draft_view.games_short(1240) == "1,2k" and draft_view.games_short(860) == "860"
    assert draft_view.games_short(None) == "—"


def test_script_servi_et_chargé_par_la_coque(client):
    assert client.get("/static/draft.js").status_code == 200
    assert 'src="/static/draft.js"' in client.get("/").text
