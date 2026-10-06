"""Écran de draft du client (SPEC-21 tâche 73) : cadre, sceaux, balance, fragments synchronisables."""

import json
from pathlib import Path
from dataclasses import asdict
from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient

from src.client import draft_view
from src.client.app import create_app
from src.client.assets import Assets
from src.client.bus import EventBus
from src.client.draft_actions import Refusal
from src.client.draft_grimoire import grimoire_view, plain
from src.config_client import client_config
from src.draft.state import DraftState
from src.draft.snapshot import (
    DraftSnapshot,
    SnapshotBan,
    SnapshotBanAdvice,
    SnapshotChampion,
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


# ---------- phase de bans (tâche 87) ----------


def advice(champion, champion_id, gain, response="Aatrox", value=1.5):
    from src.draft.snapshot import SnapshotBanAdvice

    return SnapshotBanAdvice(champion, champion_id, gain, response, value, 12)


def test_bans_conseilles_cartes_gain_et_justification(client, bus):
    bus.publish(
        "draft",
        ban_snapshot(
            ban_advice=[
                asdict(advice("Darius", 122, 2.94)),
                asdict(advice("Yone", 777, 1.2, "Garen", -0.4)),
            ],
            pool_name="GRIND",
        ),
    )
    html = client.get("/draft/stage").text
    assert "Bans conseillés · menaces pour ton pool" in html and "Pool GRIND" in html
    assert html.count('class="d-card"') == 2
    assert "+2,9" in html and "pts si banni" in html and "+1,2" in html
    assert "Ta meilleure réponse : Aatrox (+1,5 pts)" in html and "Garen (−0,4 pts)" in html
    assert 'data-champ="122"' in html and 'src="/assets/champion/Darius.png"' in html
    assert '<button type="button" class="d-act d-act-ban" data-act="ban" disabled>' in html


def test_bans_conseilles_etat_du_script(client, bus):
    bus.publish("draft", ban_snapshot(ban_advice=[asdict(advice("Darius", 122, 2.9))]))
    state = state_of(client.get("/draft/stage").text)
    assert state["bans"] == [122] and state["names"]["122"] == "Darius"
    assert state["kind"] == "ban" and state["my_ban_id"] == 0


def test_ban_pose_remplace_le_bouton_par_le_constat(client, bus):
    bus.publish(
        "draft",
        ban_snapshot(
            my_ban=asdict(SnapshotBan(122, "Darius", "ally")),
            ban_advice=[asdict(advice("Darius", 122, 2.9))],
        ),
    )
    html = client.get("/draft/stage").text
    assert "Darius banni" in html and 'data-act="ban"' not in html
    assert state_of(html)["my_ban_id"] == 122


def test_sans_menace_identifiee_le_message_propose_le_grimoire(client, bus):
    bus.publish("draft", ban_snapshot(ban_advice=[]))
    html = client.get("/draft/stage").text
    assert "Aucune menace identifiée" in html and 'class="d-card"' not in html


def test_rangee_de_bans_absente_en_phase_de_picks(client, bus):
    bus.publish("draft", pick_snapshot())
    html = client.get("/draft/stage").text
    assert "Bans conseillés" not in html and 'data-act="ban"' not in html


def test_noms_de_ban_echappes(client, bus):
    bus.publish(
        "draft",
        ban_snapshot(ban_advice=[asdict(advice("<b>x</b>", 1, 1.0, "<i>y</i>"))]),
    )
    html = client.get("/draft/stage").text
    assert "<b>x</b>" not in html and "&lt;b&gt;x&lt;/b&gt;" in html and "<i>y</i>" not in html


def test_js_servi_sans_erreur_de_syntaxe():
    import shutil
    import subprocess
    from pathlib import Path

    node = shutil.which("node")
    if node is None:
        pytest.skip("node absent")
    path = Path(__file__).parent.parent / "src" / "client" / "static" / "draft.js"
    assert subprocess.run([node, "--check", str(path)], capture_output=True).returncode == 0


# ---------- phase de picks (tâche 88) ----------


def test_recommandations_cartes_win_ecart_et_suite(client, bus):
    bus.publish("draft", pick_snapshot(versus="Tryndamere"))
    html = client.get("/draft/stage").text
    assert "Recommandations · Top contre Tryndamere" in html
    assert html.count('class="d-card"') == 2
    assert "54,82 %" in html and "+3,1 pts" in html and "1,2k games" in html
    assert "53,07 %" in html and "860 games" in html
    assert "Suite attendue : Alistar (Support)" in html and "Suite attendue : —" in html
    assert 'data-champ="266"' in html and 'src="/assets/champion/Aatrox.png"' in html
    assert 'class="d-act d-act-lock" data-act="lock" disabled>' in html


def test_ecart_negatif_en_rose_avec_vrai_signe_moins(client, bus):
    snapshot = pick_snapshot()
    snapshot["recommendations"][1]["delta"] = -1.3
    bus.publish("draft", snapshot)
    html = client.get("/draft/stage").text
    assert "−1,3 pts" in html and '<div class="d-card-delta">−1,3 pts</div>' in html
    assert '<div class="d-card-delta up">+3,1 pts</div>' in html


def test_sous_titre_profondeur_et_champions_ecartes(client, bus):
    bus.publish("draft", pick_snapshot(pool_name="GRIND"))
    html = client.get("/draft/stage").text
    assert "Pool GRIND · profondeur atteinte : 2 pick(s) anticipé(s)" in html
    assert "sans données exploitables en Top : Ambessa (38 games)" in html


def test_sans_recommandation_le_message_remplace_les_cartes(client, bus):
    bus.publish("draft", pick_snapshot(recommendations=[], skipped=[]))
    html = client.get("/draft/stage").text
    assert "Aucune recommandation pour le moment" in html and 'class="d-card"' not in html


def test_pas_mon_tour_les_cartes_restent_mais_pas_de_survol_serveur(client, bus):
    bus.publish("draft", pick_snapshot(my_turn=False))
    html = client.get("/draft/stage").text
    assert 'class="d-card"' in html and "Phase de picks — en attente" in html
    assert state_of(html)["my_turn"] is False


def test_verrouille_la_rangee_devient_la_selection_de_skin(client, bus):
    snapshot = pick_snapshot()
    snapshot["allies"][0].update(champion_id=266, champion="Aatrox", hover_id=0, hover=None)
    bus.publish("draft", snapshot)
    html = client.get("/draft/stage").text
    assert (
        "Skins indisponibles" in html
        and 'data-act="lock"' not in html
        and 'class="d-card"' not in html
    )
    assert state_of(html)["locked_id"] == 266


def test_mon_portrait_est_toujours_la_pour_l_apercu_et_ne_rejoue_pas_son_apparition(client, bus):
    bus.publish("draft", ban_snapshot())
    fragment = client.get("/draft/stage").text
    assert "<img data-me" in fragment
    assert 'data-pop data-delay="1000"' not in fragment
    assert 'data-pop data-delay="1000"' in client.get("/draft").text


def test_le_sceau_du_verrouillage_a_sa_cible_de_secousse(client):
    assert "data-quake" in client.get("/draft").text


# ---------- grimoire des champions (tâche 89) ----------


import re  # noqa: E402


def table():
    return [
        asdict(row)
        for row in [
            SnapshotChampion(266, "Aatrox", ["top"], 0.5482, None),
            SnapshotChampion(122, "Darius", ["top"], 0.5307, 2.0),
            SnapshotChampion(64, "LeeSin", ["jungle"], 0.49, None),
            SnapshotChampion(103, "Ahri", ["middle"], 0.51, None),
            SnapshotChampion(222, "Jinx", ["bottom"], 0.52, None),
            SnapshotChampion(12, "Alistar", ["support"], 0.5, None),
            SnapshotChampion(23, "Tryndamere", ["top"], 0.47, None),
            SnapshotChampion(777, "Yone", ["top", "middle"], None, None),
        ]
    ]


def tiles(html):
    return re.findall(r'<div class="g-tile[^"]*" data-id="(\d+)"', html)


def test_recherche_sans_accents_ni_casse():
    assert plain("Kai'Sa") == "kai'sa" and plain("Renata Glasc") == "renata glasc"
    assert plain("Nunu & Willump") == "nunu & willump" and plain("Cho'Gath") == "cho'gath"
    assert plain("Éclat") == "eclat" and plain("MAÎTRE") == "maitre"


def test_grimoire_sans_snapshot(client):
    response = client.get("/draft/champions")
    assert response.status_code == 200 and "Pas de champ select" in response.text


def test_tri_recommandations_puis_pool_puis_alphabetique(client, bus):
    bus.publish("draft", pick_snapshot(champions=table(), pool=["Yone", "Jinx"]))
    html = client.get("/draft/champions").text
    # Aatrox, Darius : recommandés (0) ; Jinx, Yone : pool (1) ; Ahri, Alistar, Lee Sin, Tryndamere : le reste.
    # Darius (adverse banni), Alistar (allié), Jinx (allié) et Lee Sin / Tryndamere (adverses) restent listés.
    assert tiles(html) == ["266", "122", "222", "777", "103", "12", "64", "23"]


def test_indisponibles_avec_leur_raison(client, bus):
    bus.publish("draft", pick_snapshot(champions=table(), pool=[]))
    html = client.get("/draft/champions").text
    reasons = dict(
        re.findall(
            r'data-id="(\d+)" data-search="[^"]*" data-roles="[^"]*"\s+data-pool="\d" data-gone="([^"]*)"',
            html,
        )
    )
    assert reasons["122"] == "banni"  # ban adverse de Darius
    assert reasons["777"] == "banni"  # ban allié de Yone
    assert reasons["12"] == "allié" and reasons["222"] == "allié"
    assert reasons["23"] == "adverse" and reasons["64"] == "adverse"
    assert reasons["266"] == "" and reasons["103"] == ""
    assert html.count("is-gone") == 6 and html.count("g-strike") == 6


def test_meta_des_tuiles_en_pick(client, bus):
    bus.publish("draft", pick_snapshot(champions=table(), pool=["Ahri"]))
    html = client.get("/draft/champions").text
    assert '<span class="g-meta g-tone-win">54,8 %</span>' in html
    assert (
        'data-info="Victoire prédite 54,8 % · 1,2k games · suite attendue : Alistar (Support)"'
        in html
    )
    assert "Pool GRIND uniquement" in html


def test_info_pool_sans_donnees_et_hors_pool(client, bus):
    snap = pick_snapshot(champions=table(), pool=["Ahri"], recommendations=[], pool_name="GRIND")
    snap["enemies"] = snap["enemies"][2:]  # libère Lee Sin et Tryndamere
    snap["allies"] = snap["allies"][:1]
    snap["ally_bans"], snap["enemy_bans"] = [], []
    bus.publish("draft", snap)
    html = client.get("/draft/champions").text
    assert (
        "Pool GRIND · sans données exploitables en Top · victoire prédite 51,0 % (modèle seul)"
        in html
    )
    assert "Hors pool · victoire prédite 49,0 % (modèle seul, sans historique perso)" in html


def test_mode_ban_gains_et_intentions(client, bus):
    snap = ban_snapshot(
        champions=table(),
        ban_advice=[asdict(SnapshotBanAdvice("Darius", 122, 2.94, "Aatrox", 1.5, 12))],
        my_ban=asdict(SnapshotBan(777, "Yone", "ally")),
    )
    snap["allies"][1].update(hover_id=103, hover="Ahri")
    snap["allies"][0].update(hover_id=266, hover="Aatrox")
    bus.publish("draft", snap)
    html = client.get("/draft/champions").text
    assert 'class="g-overlay g-ban"' in html and "Double-clic pour bannir" in html
    assert tiles(html)[0] == "122"  # la menace conseillée en tête
    assert '<span class="g-meta g-tone-ban">+2,9 pts</span>' in html
    assert "Gain estimé si banni : +2,9 pts · Ta meilleure réponse : Aatrox (+1,5 pts)" in html
    assert "Hors des menaces identifiées pour ton pool" in html
    assert 'data-gone="intention alliée"' in html and 'data-gone="ton intention"' in html
    assert 'data-gone="banni"' in html  # mon ban


def test_puces_de_role_et_role_par_defaut(client, bus):
    bus.publish("draft", pick_snapshot(champions=table()))
    html = client.get("/draft/champions").text
    assert 'data-role="top"' in html
    for key in ("all", "top", "jungle", "middle", "bottom", "support"):
        assert f'data-role-chip="{key}"' in html
    assert re.search(r'data-roles="top middle"', html)  # Yone joue deux rôles


def test_noms_de_champions_echappes_dans_le_grimoire(client, bus):
    rows = table()
    rows[0]["champion"] = "<img src=x onerror=alert(1)>"
    bus.publish("draft", pick_snapshot(champions=rows))
    html = client.get("/draft/champions").text
    assert "<img src=x" not in html and "&lt;img src=x" in html


def test_vue_sans_snapshot():
    assert grimoire_view(None, None) == {"empty": True}


def test_boutons_d_ouverture_et_scripts(client, bus):
    bus.publish("draft", ban_snapshot())
    html = client.get("/draft/stage").text
    assert "data-open-grid" in html and "Tous les champions" in html
    bus.publish("draft", pick_snapshot())
    assert "data-open-grid" in client.get("/draft/stage").text
    assert 'src="/static/champions.js"' in client.get("/").text
    assert client.get("/static/champions.js").status_code == 200


def test_champions_js_sans_erreur_de_syntaxe():
    import shutil
    import subprocess
    from pathlib import Path

    node = shutil.which("node")
    if node is None:
        pytest.skip("node absent")
    path = Path(__file__).parent.parent / "src" / "client" / "static" / "champions.js"
    assert subprocess.run([node, "--check", str(path)], capture_output=True).returncode == 0


def test_instantane_du_grimoire_construit_par_le_live_coach():
    """`build_snapshot` annote tous les champions : rôles, victoire prédite, gain de ban."""
    from unittest.mock import Mock

    from src.draft.snapshot import Analysis, _champion_table

    monitor = Mock()
    monitor.champion_id_to_name = {1: "Annie", 2: "Zed"}
    monitor.lane_distributions = {
        1: {"middle": 80.0, "top": 3.0},
        2: {"middle": 60.0, "jungle": 20.0},
    }
    analysis = Analysis(candidates={1: 0.52})
    rows = _champion_table(monitor, analysis, {2: 1.4})
    assert [(r.champion, r.roles, r.win_probability, r.ban_gain) for r in rows] == [
        ("Annie", ["middle"], 0.52, None),  # 3 % de top : sous le seuil
        ("Zed", ["middle", "jungle"], None, 1.4),
    ]


# ---------- sélection de skin (tâche 90) ----------


def post(client, path, token=True, **params):
    headers = {client_config.TOKEN_HEADER: client.app.state.session_token} if token else {}
    return client.post(path, params=params, headers=headers)


SKINS_FIXTURE = Path(__file__).parent / "fixtures" / "lcu_forms" / "skins_annie.json"


class FauxLcuSkins:
    """LCU réduit aux skins : forme relevée sur le client réel (fixtures/lcu_forms/skins_annie.json)."""

    def __init__(self, skins=None):
        self.credentials = object()
        self.skins = (
            json.loads(SKINS_FIXTURE.read_text(encoding="utf-8")) if skins is None else skins
        )
        self.calls = []
        self.writes = []
        self.refuses = False

    def find_lcu_credentials(self):
        return self.credentials

    def _make_request(self, endpoint, method="GET", data=None):
        self.calls.append((method, endpoint))
        if method != "GET":
            self.writes.append((method, endpoint, data))
            return None if self.refuses else {}
        if endpoint == "/lol-summoner/v1/current-summoner":
            return {"summonerId": 7}
        if endpoint == "/lol-champions/v1/inventories/7/champions/1/skins":
            return self.skins
        return None


def annie_snapshot(skin_id=0, **overrides):
    snapshot = pick_snapshot(**overrides)
    snapshot["allies"][0].update(
        champion_id=1, champion="Annie", hover_id=0, hover=None, skin_id=skin_id
    )
    return snapshot


@pytest.fixture
def lcu_skins():
    return FauxLcuSkins()


@pytest.fixture
def skins_client(temp_db, bus, assets, lcu_skins, monkeypatch):
    monkeypatch.setattr(client_config, "SKINS_TTL_S", 0.0)
    assets._fetch = lambda url: (
        json.dumps(
            {
                "data": {
                    **CHAMPIONS["data"],
                    "Annie": {"key": "1", "id": "Annie", "name": "Annie", "tags": []},
                }
            }
        ).encode()
        if url.endswith("champion.json")
        else None
    )
    app = create_app(temp_db, bus=bus, lcu=lcu_skins, assets=assets)
    return TestClient(app, base_url=LOCAL, raise_server_exceptions=False)


def test_skins_possedes_et_verrouilles_lus_dans_le_lcu(skins_client, bus):
    bus.publish("draft", annie_snapshot())
    html = skins_client.get("/draft/stage").text
    assert html.count('data-skin="') == 3
    assert "Skin · Classique" in html and "Classique" in html
    assert "1 skin possédé sur 3" in html
    assert html.count("is-locked") == 2 and html.count("d-skin-lock") == 2
    assert (
        'src="/assets/loading/Annie_0.jpg"' in html and 'src="/assets/loading/Annie_1.jpg"' in html
    )
    assert 'data-skin="1000" data-owned="1"' in html and 'data-skin="1001" data-owned="0"' in html


def test_splash_du_skin_choisi(skins_client, bus):
    bus.publish("draft", annie_snapshot(skin_id=1000))
    html = skins_client.get("/draft/stage").text
    assert 'class="d-splash on"' in html and 'src="/assets/splash/Annie_0.jpg"' in html
    assert state_of(html)["skin_id"] == 1000


def test_skin_par_defaut_est_le_skin_de_base(skins_client, bus):
    bus.publish("draft", annie_snapshot(skin_id=0))
    assert state_of(skins_client.get("/draft/stage").text)["skin_id"] == 1000


def test_pas_de_skins_avant_le_verrouillage(skins_client, bus, lcu_skins):
    bus.publish("draft", pick_snapshot())
    html = skins_client.get("/draft/stage").text
    assert "d-skin" not in html and 'class="d-splash"' in html
    assert lcu_skins.calls == []  # aucune lecture inutile du LCU


def test_client_ferme_skins_indisponibles(skins_client, bus, lcu_skins):
    lcu_skins.skins = None
    bus.publish("draft", annie_snapshot())
    html = skins_client.get("/draft/stage").text
    assert "Skins indisponibles" in html and "d-skin " not in html


def test_ecrire_un_skin_possede(skins_client, bus, lcu_skins):
    bus.publish("draft", annie_snapshot())
    response = post(skins_client, "/draft/skin", skin_id=1000)
    assert response.status_code == 200
    assert lcu_skins.writes == [
        ("PATCH", "/lol-champ-select/v1/session/my-selection", {"selectedSkinId": 1000})
    ]


@pytest.mark.parametrize(
    "skin_id, message",
    [(1001, "possèdes pas"), (2000, "pas celui de ton champion"), (1999, "inconnu")],
)
def test_skin_refuse_sans_ecriture(skins_client, bus, lcu_skins, skin_id, message):
    bus.publish("draft", annie_snapshot())
    response = post(skins_client, "/draft/skin", skin_id=skin_id)
    assert response.status_code == 409 and message in response.json()["detail"]
    assert lcu_skins.writes == []


def test_skin_avant_le_verrouillage_refuse(skins_client, bus, lcu_skins):
    bus.publish("draft", pick_snapshot())
    response = post(skins_client, "/draft/skin", skin_id=1000)
    assert response.status_code == 409 and "Verrouille d'abord" in response.json()["detail"]
    assert lcu_skins.writes == []


def test_skin_sans_jeton_403(skins_client, bus, lcu_skins):
    bus.publish("draft", annie_snapshot())
    assert post(skins_client, "/draft/skin", token=False, skin_id=1000).status_code == 403
    assert lcu_skins.calls == []


def test_le_client_refuse_le_skin(skins_client, bus, lcu_skins):
    bus.publish("draft", annie_snapshot())
    lcu_skins.refuses = True
    response = post(skins_client, "/draft/skin", skin_id=1000)
    assert response.status_code == 409 and "refusé" in response.json()["detail"]


def test_liste_des_skins_gardee_entre_deux_rendus(skins_client, bus, lcu_skins, monkeypatch):
    monkeypatch.setattr(client_config, "SKINS_TTL_S", 60.0)
    bus.publish("draft", annie_snapshot())
    skins_client.get("/draft/stage")
    skins_client.get("/draft/stage")
    reads = [c for c in lcu_skins.calls if c[1].endswith("/skins")]
    assert len(reads) == 1


def test_skin_choisi_republie_le_snapshot(monkeypatch):
    from src.draft.recommendations import DraftRecommender
    from src.draft.state import Cell, DraftState

    a = DraftState(ally_cells=[Cell(cell_id=0, champion_id=1, skin_id=0)])
    b = DraftState(ally_cells=[Cell(cell_id=0, champion_id=1, skin_id=1002)])
    assert DraftRecommender._signature(a) != DraftRecommender._signature(b)


# ---------- colonne loadout (tâche 91) ----------

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def tree_from_lcu():
    """Arbres au format Data Dragon (`runesReforged.json`) reconstruits sur les ids du LCU relevé."""
    lcu_styles = json.loads(
        (FIXTURES_DIR / "lcu_forms" / "styles.json").read_text(encoding="utf-8")
    )
    return [
        {
            "id": style["id"],
            "key": style["idName"],
            "name": style["name"],
            "icon": f"perk-images/Styles/{style['id']}_{style['idName']}.png",
            "slots": [
                {
                    "runes": [
                        {
                            "id": rid,
                            "name": f"Rune {rid}",
                            "icon": f"perk-images/Styles/{style['idName']}/{rid}.png",
                        }
                        for rid in slot["perks"]
                    ]
                }
                for slot in style["slots"][:4]
            ],
        }
        for style in lcu_styles
    ]


JINX_PAGE = dict(
    primary=8000,
    sub=8300,
    perks=[8008, 8009, 8017, 8313, 8321, 9103],
    shards=[5005, 5008, 5011],
)


@pytest.fixture
def runes_assets(tmp_path, monkeypatch, assets):
    monkeypatch.setattr(Assets, "rune_styles", lambda self: tree_from_lcu())
    return assets


def test_normaliser_une_page_ordonnee_par_identifiant():
    from src.client.draft_loadout import normalize_page

    page = normalize_page(tree_from_lcu(), **JINX_PAGE)
    assert page == {
        "primary": 8000,
        "sub": 8300,
        "keystone": 8008,
        "rows": [8009, 9103, 8017],
        "subs": [8321, 8313],
        "shards": [5005, 5008, 5011],
    }


@pytest.mark.parametrize(
    "perks",
    [
        [8008, 8009, 8017, 8313, 8321],
        [8008, 8009, 9103, 8313, 8321, 8304],
        [9101, 8009, 9103, 8017, 8313, 8321],
    ],
)
def test_page_incomplete_ou_incoherente_refusee(perks):
    from src.client.draft_loadout import normalize_page

    assert normalize_page(tree_from_lcu(), 8000, 8300, perks, [5005, 5008, 5011]) is None


def good_page():
    from src.client.draft_loadout import normalize_page

    return normalize_page(tree_from_lcu(), **JINX_PAGE)


@pytest.mark.parametrize(
    "change, message",
    [
        ({"keystone": 9101}, "majeure"),
        ({"rows": [8009, 8009, 8017]}, "principal"),
        ({"subs": [8321, 8306]}, "rangées différentes"),
        ({"sub": 8000}, "incompatibles"),
        ({"primary": 1}, "incompatibles"),
        ({"shards": [5005, 5008, 9999]}, "Fragment"),
    ],
)
def test_validation_d_une_page(change, message):
    from src.client.draft_loadout import validate_page

    with pytest.raises(Refusal, match=message):
        validate_page(tree_from_lcu(), {**good_page(), **change})


def test_une_page_valide_passe():
    from src.client.draft_loadout import validate_page

    validate_page(tree_from_lcu(), good_page())


def test_charge_utile_des_runes(client, runes_assets):
    payload = client.get("/draft/runes").json()
    assert [s["id"] for s in payload["styles"]] == [8000, 8100, 8200, 8300, 8400]
    precision = payload["styles"][0]
    assert precision["color"].startswith("oklch") and len(precision["slots"]) == 4
    assert [r["title"] for r in payload["shards"]] == [
        "Offensif",
        "Flexible",
        "Défensif",
    ]
    assert (
        len(payload["spells"]) == 9
        and {"id": 4, "key": "SummonerFlash", "name": "Flash"} in payload["spells"]
    )


def jinx_snapshot(**overrides):
    snap = pick_snapshot(
        champions=[asdict(SnapshotChampion(222, "Jinx", ["bottom"], 0.52, None))],
        versus=None,
        local_role="bottom",
    )
    snap.update(overrides)
    return snap


@pytest.fixture
def onetricks(monkeypatch):
    from src.draft import loadout

    page = json.loads((FIXTURES_DIR / "onetricks_jinx_bot.json").read_text(encoding="utf-8"))
    calls = []

    def fake(champion, lane, opponent=None):
        calls.append((champion, lane, opponent))
        return page if opponent is None else None

    monkeypatch.setattr(loadout, "get_page", fake)
    return calls


def test_page_prevue_depuis_onetricks(client, bus, runes_assets, onetricks):
    bus.publish("draft", jinx_snapshot())
    plan = client.get("/draft/loadout", params={"champion_id": 222}).json()
    assert plan["available"] and plan["source"] == "onetricks" and plan["games"] > 0
    assert plan["page"]["primary"] == 8000 and plan["page"]["keystone"] == 8008
    assert len(plan["spells"]) == 2 and [b["title"] for b in plan["items"]] == [
        "Départ",
        "Core",
        "Bottes",
    ]
    assert onetricks == [("Jinx", "bottom", None)]


def test_duel_inconnu_retombe_sur_la_build_generale(client, bus, runes_assets, onetricks):
    bus.publish("draft", jinx_snapshot(versus="Draven"))
    plan = client.get("/draft/loadout", params={"champion_id": 222}).json()
    assert plan["available"] and plan["opponent"] is None
    assert ("Jinx", "bottom", "Draven") in onetricks


def test_page_deja_ecrite_dans_le_client_sans_reseau(client, bus, runes_assets, onetricks):
    applied = {
        "champion_id": 222,
        "label": "Jinx bottom",
        "primary_style": 8000,
        "sub_style": 8300,
        "perks": [8008, 8009, 8017, 8313, 8321, 9103],
        "shards": [5005, 5008, 5011],
        "spells": [4, 7],
        "item_blocks": [
            {"title": "Départ (40%)", "items": [1055]},
            {"title": "Core (50%)", "items": [3031]},
        ],
        "games": 321,
    }
    bus.publish("draft", jinx_snapshot(loadout=applied))
    plan = client.get("/draft/loadout", params={"champion_id": 222}).json()
    assert plan["source"] == "client" and plan["games"] == 321 and plan["spells"] == [4, 7]
    assert [b["title"] for b in plan["items"]] == ["Départ", "Core"]
    assert onetricks == []


def test_page_indisponible(client, bus, runes_assets, monkeypatch):
    from src.draft import loadout

    monkeypatch.setattr(loadout, "get_page", lambda *a, **k: None)
    bus.publish("draft", jinx_snapshot())
    plan = client.get("/draft/loadout", params={"champion_id": 222}).json()
    assert plan == {
        "available": False,
        "reason": "Page OneTricks indisponible pour ce champion",
    }
    assert (
        client.get("/draft/loadout", params={"champion_id": 1}).json()["reason"]
        == "Champion inconnu"
    )


def test_loadout_sans_champ_select(client):
    assert client.get("/draft/loadout", params={"champion_id": 222}).json()["available"] is False


class FauxLcuLoadout:
    """LCU des runes et des sorts : mémorise chaque appel."""

    def __init__(self):
        self.credentials = object()
        self.calls = []
        self.session = {
            "localPlayerCellId": 0,
            "myTeam": [{"cellId": 0, "spell1Id": 4, "spell2Id": 14}],
        }

    def find_lcu_credentials(self):
        return self.credentials

    def _make_request(self, endpoint, method="GET", data=None):
        self.calls.append((method, endpoint, data))
        if endpoint == "/lol-champ-select/v1/session":
            if method == "PATCH":
                return {}
            return self.session
        if method == "PATCH":
            return {}
        if endpoint == "/lol-perks/v1/pages" and method == "GET":
            return []
        if endpoint == "/lol-perks/v1/inventory":
            return {"ownedPageCount": 5}
        if endpoint == "/lol-perks/v1/styles":
            return json.loads(
                (FIXTURES_DIR / "lcu_forms" / "styles.json").read_text(encoding="utf-8")
            )
        return {"id": 1}


@pytest.fixture
def loadout_client(temp_db, bus, runes_assets):
    lcu = FauxLcuLoadout()
    lignes = []
    app = create_app(
        temp_db,
        bus=bus,
        lcu=lcu,
        assets=runes_assets,
        commands=lambda line: lignes.append(line) or True,
    )
    client = TestClient(app, base_url=LOCAL, raise_server_exceptions=False)
    return client, lcu, lignes


SEND = dict(
    primary=8000,
    sub=8300,
    perks="8008,8009,9103,8017,8321,8313",
    shards="5005,5008,5011",
    spell1=4,
    spell2=7,
)


def test_envoyer_la_page_et_les_sorts(loadout_client, bus):
    client, lcu, lignes = loadout_client
    bus.publish("draft", jinx_snapshot())
    response = post(client, "/draft/loadout/send", **SEND)
    assert response.status_code == 200
    writes = [(m, e) for m, e, _ in lcu.calls if m != "GET"]
    assert ("POST", "/lol-perks/v1/pages") in writes
    assert ("PATCH", "/lol-champ-select/v1/session/my-selection") in writes
    created = next(d for m, e, d in lcu.calls if (m, e) == ("POST", "/lol-perks/v1/pages"))
    assert created["selectedPerkIds"][:6] == [
        8008,
        8009,
        9103,
        8017,
        8321,
        8313,
    ] and created[
        "selectedPerkIds"
    ][6:] == [5005, 5008, 5011]
    assert created["primaryStyleId"] == 8000 and created["subStyleId"] == 8300
    assert lignes == ["loadout manual"]  # le Live Coach n'écrasera plus la page


@pytest.mark.parametrize(
    "change",
    [
        {"perks": "8008,8009,9103,8017,8321"},
        {"perks": "8008,8009,9103,8017,8321,8313,1"},
        {"shards": "5005,5008"},
        {"shards": "5005,5008,1"},
        {"perks": "a,b"},
        {"spell1": 4, "spell2": 4},
        {"spell1": 4, "spell2": 99},
        {"sub": 8000},
    ],
)
def test_envoi_invalide_refuse_sans_ecriture(loadout_client, bus, change):
    client, lcu, lignes = loadout_client
    bus.publish("draft", jinx_snapshot())
    response = post(client, "/draft/loadout/send", **{**SEND, **change})
    assert response.status_code == 409
    assert [c for c in lcu.calls if c[0] != "GET"] == [] and lignes == []


def test_envoi_sans_jeton_403(loadout_client, bus):
    client, lcu, lignes = loadout_client
    assert post(client, "/draft/loadout/send", token=False, **SEND).status_code == 403
    assert lcu.calls == [] and lignes == []


def test_marquer_la_page_a_la_main_puis_la_rendre(loadout_client):
    client, _, lignes = loadout_client
    assert post(client, "/draft/loadout/manual", on=1).status_code == 204
    assert post(client, "/draft/loadout/manual", on=0).status_code == 204
    assert lignes == ["loadout manual", "loadout auto"]


def test_manuel_sans_live_coach_503(client):
    assert post(client, "/draft/loadout/manual", on=1).status_code == 503


def test_les_ecritures_de_runes_sortent_par_la_liste_blanche():
    from src.client.lcu_proxy import ForbiddenEndpoint, LcuProxy

    lcu = FauxLcuLoadout()
    proxy = LcuProxy(lcu)
    proxy.send("POST", "/lol-perks/v1/pages", {})
    proxy.send("DELETE", "/lol-perks/v1/pages/12", None)
    with pytest.raises(ForbiddenEndpoint):
        proxy.send("PUT", "/lol-perks/v1/pages/12", {})
    with pytest.raises(ForbiddenEndpoint):
        proxy.send("DELETE", "/lol-perks/v1/pages", None)


# ---------- import automatique : la main prime ----------


def test_la_page_manuelle_arrete_l_import_du_lock_in(monkeypatch):
    from unittest.mock import Mock

    from src.config_constants import draft_config
    from src.draft.loadout_import import LoadoutImporter

    monkeypatch.setattr(draft_config, "AUTO_IMPORT_LOADOUT", True)
    importer = LoadoutImporter(Mock())
    importer._import = Mock()
    session = {
        "localPlayerCellId": 0,
        "actions": [[{"type": "pick", "actorCellId": 0, "completed": True}]],
        "myTeam": [{"cellId": 0, "championId": 222}],
    }
    state = DraftState(inferred_roles={222: "bottom"})
    importer.set_manual(True)
    importer.on_tick(session, state)
    importer._import.assert_not_called()
    importer.set_manual(False)  # « Rétablir OneTricks » : le tick suivant réimporte
    importer.on_tick(session, state)
    importer._import.assert_called_once()


def test_nouvelle_draft_rend_la_main_a_l_import():
    from unittest.mock import Mock

    from src.draft.loadout_import import LoadoutImporter

    importer = LoadoutImporter(Mock())
    importer.set_manual(True)
    importer.reset()
    assert importer.manual is False


def test_les_commandes_loadout_arrivent_jusqu_a_l_importeur():
    from unittest.mock import Mock

    from src.draft.commands import CommandListener
    from src.draft.state import DraftState as State

    monitor = Mock()
    monitor.console_input = False
    monitor._command_queue.get_nowait.side_effect = [
        "loadout manual",
        "loadout auto",
        __import__("queue").Empty(),
    ]
    CommandListener(monitor).apply_pending(State())
    assert [c.args[0] for c in monitor.loadout.set_manual.call_args_list] == [
        True,
        False,
    ]


def test_scripts_de_la_colonne_loadout(client):
    assert client.get("/static/runes.js").status_code == 200
    assert 'src="/static/runes.js"' in client.get("/").text


def test_runes_js_sans_erreur_de_syntaxe():
    import shutil
    import subprocess

    node = shutil.which("node")
    if node is None:
        pytest.skip("node absent")
    path = Path(__file__).parent.parent / "src" / "client" / "static" / "runes.js"
    assert subprocess.run([node, "--check", str(path)], capture_output=True).returncode == 0


def test_la_colonne_est_vide_cote_serveur_et_appartient_au_script(client, bus):
    bus.publish("draft", pick_snapshot())
    html = client.get("/draft/stage").text
    assert '<aside class="d-loadout"' in html and "Runes &amp; sorts" not in html


# ---------- éditeur de runes (tâche 92) ----------

import shutil  # noqa: E402
import subprocess  # noqa: E402

LOGIC = Path(__file__).parent.parent / "src" / "client" / "static" / "rune_logic.js"
NODE_SCRIPT = """
const L = require(process.argv[1]);
const { styles, page, ops } = JSON.parse(require('fs').readFileSync(0, 'utf8'));
let current = page;
const log = [];
for (const [name, ...args] of ops) {
  current = name === 'setPrimary' || name === 'setSub' || name === 'setKeystone' || name === 'setRow' || name === 'setSubRune'
    ? L[name](styles, current, ...args) : L[name](current, ...args);
  log.push(current);
}
console.log(JSON.stringify({ log, byRow: L.subsByRow(styles, current) }));
"""


def run_logic(ops, page=None):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node absent")
    from src.client.draft_loadout import runes_payload

    styles = runes_payload(tree_from_lcu())["styles"]  # la forme que le navigateur reçoit
    payload = {"styles": styles, "page": page or good_page(), "ops": ops}
    done = subprocess.run(
        [node, "-e", NODE_SCRIPT, str(LOGIC)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(done.stdout)


def test_changer_d_arbre_principal_reprend_les_premieres_runes():
    result = run_logic([["setPrimary", 8100]])
    page = result["log"][-1]
    domination = next(s for s in tree_from_lcu() if s["id"] == 8100)
    assert page["primary"] == 8100
    assert page["keystone"] == domination["slots"][0]["runes"][0]["id"]
    assert page["rows"] == [domination["slots"][i]["runes"][0]["id"] for i in (1, 2, 3)]
    assert page["sub"] == 8300 and page["subs"] == good_page()["subs"]  # le secondaire ne bouge pas


def test_arbre_principal_pris_au_secondaire_le_deplace_ailleurs():
    page = run_logic([["setPrimary", 8300]])["log"][-1]
    assert page["primary"] == 8300 and page["sub"] != 8300
    sub_tree = next(s for s in tree_from_lcu() if s["id"] == page["sub"])
    rows = [[r["id"] for r in slot["runes"]] for slot in sub_tree["slots"]]
    assert [next(i for i, row in enumerate(rows) if rune in row) for rune in page["subs"]] == [1, 2]


def test_choisir_le_meme_arbre_ne_change_rien():
    page = good_page()
    log = run_logic([["setPrimary", 8000], ["setSub", 8300], ["setSub", 8000]], page)["log"]
    assert (
        log[0] == page and log[1] == page and log[2] == page
    )  # le secondaire ne peut pas être le principal


def test_rune_majeure_et_rangees_restent_dans_leur_arbre():
    page = good_page()
    log = run_logic(
        [
            ["setKeystone", 8010],
            ["setKeystone", 9111],
            ["setRow", 0, 9101],
            ["setRow", 0, 8014],
        ],
        page,
    )["log"]
    assert log[0]["keystone"] == 8010
    assert log[1]["keystone"] == 8010  # 9111 n'est pas une rune majeure
    assert log[2]["rows"][0] == 9101
    assert log[3]["rows"][0] == 9101  # 8014 est de la rangée 3


def test_troisieme_rangee_secondaire_remplace_la_plus_ancienne():
    # subs = [8321 (rangée 1), 8313 (rangée 2)] ; la rangée 3 (8347) chasse la plus ancienne (8321).
    page = good_page()
    page["subs"] = [8321, 8313]
    result = run_logic([["setSubRune", 8347]], page)
    assert result["log"][-1]["subs"] == [8313, 8347]
    assert result["byRow"] == [8313, 8347]  # affichées dans l'ordre des rangées


def test_meme_rangee_secondaire_remplace_la_rune_de_cette_rangee():
    page = good_page()
    page["subs"] = [8321, 8313]  # rangées 1 et 2
    result = run_logic([["setSubRune", 8306]], page)  # autre rune de la rangée 1
    assert sorted(result["log"][-1]["subs"]) == sorted([8306, 8313])


def test_rune_secondaire_deja_choisie_ou_hors_arbre_ignoree():
    page = good_page()
    log = run_logic([["setSubRune", 8321], ["setSubRune", 8010]], page)["log"]
    assert log[0] == page and log[1] == page


def test_changer_d_arbre_secondaire_remet_les_deux_premieres_rangees():
    page = run_logic([["setSub", 8200]])["log"][-1]
    sorcery = next(s for s in tree_from_lcu() if s["id"] == 8200)
    assert page["sub"] == 8200
    assert page["subs"] == [
        sorcery["slots"][1]["runes"][0]["id"],
        sorcery["slots"][2]["runes"][0]["id"],
    ]


def test_fragment_par_rangee():
    page = run_logic([["setShard", 1, 5010]])["log"][-1]
    assert page["shards"] == [5005, 5010, 5011]


def test_chaque_page_produite_par_l_editeur_est_valide_pour_le_serveur():
    from src.client.draft_loadout import validate_page

    ops = [
        ["setPrimary", 8100],
        ["setSub", 8200],
        ["setSubRune", 8236],
        ["setShard", 0, 5007],
        ["setKeystone", 8128],
    ]
    for page in run_logic(ops)["log"]:
        validate_page(tree_from_lcu(), page)


def test_scripts_de_l_editeur_servis(client):
    assert client.get("/static/rune_logic.js").status_code == 200
    html = client.get("/").text
    assert html.index("rune_logic.js") < html.index("runes.js")


def test_rune_logic_js_sans_erreur_de_syntaxe():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node absent")
    assert subprocess.run([node, "--check", str(LOGIC)], capture_output=True).returncode == 0


# ---------- visée d'un ban sans présélection (SPEC-24 tâche 97) ----------

BAN_LOGIC = Path(__file__).parent.parent / "src" / "client" / "static" / "ban_logic.js"
BAN_SCRIPT = """
const L = require(process.argv[1]);
const { state, clicked, id } = JSON.parse(require('fs').readFileSync(0, 'utf8'));
console.log(JSON.stringify({
  target: L.target(state, clicked),
  suggestion: L.suggestion(state, clicked),
  send: L.shouldSendHover(state, clicked, id),
}));
"""


def ban_logic(state, clicked=None, id=None):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node absent")
    base = {"kind": "ban", "my_ban_id": 0, "ban_hover_id": 0, "bans": [122, 266]}
    done = subprocess.run(
        [node, "-e", BAN_SCRIPT, str(BAN_LOGIC)],
        input=json.dumps({"state": {**base, **state}, "clicked": clicked, "id": id}),
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(done.stdout)


def test_aucune_cible_a_l_ouverture_le_conseil_n_est_qu_une_suggestion():
    result = ban_logic({}, id=122)
    assert result["target"] is None  # le bouton « Bannir » reste inactif
    assert result["suggestion"] == 122


def test_un_clic_sur_la_premiere_carte_envoie_un_survol():
    assert ban_logic({}, id=122)["send"] is True


def test_cliquer_la_cible_deja_envoyee_n_envoie_rien():
    assert ban_logic({"ban_hover_id": 122}, id=122)["send"] is False
    assert ban_logic({}, clicked=122, id=122)["send"] is False


def test_un_autre_clic_change_la_cible_et_l_envoie():
    result = ban_logic({"ban_hover_id": 122}, clicked=266, id=266)
    assert result["target"] == 266 and result["send"] is False  # déjà la cible cliquée
    assert ban_logic({"ban_hover_id": 122}, id=266)["send"] is True


def test_ban_pose_ou_hors_phase_de_bans_rien_ne_part():
    assert ban_logic({"my_ban_id": 122}, id=266) == {
        "target": 122,
        "suggestion": None,
        "send": False,
    }
    assert ban_logic({"kind": "pick"}, id=122) == {
        "target": None,
        "suggestion": None,
        "send": False,
    }


def test_ban_logic_servi_avant_draft_js_et_sans_erreur_de_syntaxe(client):
    assert client.get("/static/ban_logic.js").status_code == 200
    html = client.get("/").text
    assert html.index("ban_logic.js") < html.index("draft.js")
    node = shutil.which("node")
    if node is None:
        pytest.skip("node absent")
    assert subprocess.run([node, "--check", str(BAN_LOGIC)], capture_output=True).returncode == 0
