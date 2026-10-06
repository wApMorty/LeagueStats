"""SPEC-24 tâche 110 : build de l'écran « En partie » : plan d'objets, suivi des achats, compétences.

Hermétique : objets de la partie réelle du spike (`allgamedata_items.json`), table d'objets de Data
Dragon factice, page OneTricks enregistrée pour l'ordre des compétences. Aucun client LoL.
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.client import en_partie
from src.client.app import create_app
from src.client.assets import Assets
from src.client.ingame import me_of
from src.config_client import client_config
from src.draft.loadout_import import _skills
from tests.test_client_draft import BASE, CHAMPIONS, LOCAL, bus  # noqa: F401  (fixture)

FIXTURES = Path(__file__).parent / "fixtures"

# Objets de Data Dragon (forme d'`Assets.items()`) : l'essentiel de la partie du spike.
ITEMS = {
    3071: {"name": "Fendoir noir", "total": 3000, "base": 850, "parts": [3133, 1037]},
    3133: {"name": "Marteau de guerre de Caulfield", "total": 1100, "base": 1100, "parts": []},
    1037: {"name": "Pioche", "total": 875, "base": 875, "parts": []},
    3053: {"name": "Lame de Sterak", "total": 3200, "base": 600, "parts": [3067]},
    3067: {"name": "Gemme ardente", "total": 800, "base": 800, "parts": []},
    3008: {"name": "Jambières gloutonnes", "total": 1100, "base": 700, "parts": []},
    3047: {"name": "Sandales de blindage", "total": 1100, "base": 1100, "parts": []},
}
SKILLS = json.loads((FIXTURES / "onetricks_skills_yorick_top.json").read_text(encoding="utf-8"))


def loadout(**extra):
    """Le loadout de FinalAnalysis : départ, core (Fendoir noir puis Lame de Sterak), bottes."""
    return {
        "champion_id": 83,
        "label": "Yorick top",
        "item_blocks": [
            {"title": "Départ (60%)", "items": [1120, 1036]},
            {"title": "Core (45%)", "items": [3071, 3053]},
            {"title": "Bottes (70%)", "items": [3008, 3047]},
            {"title": "Situationnels", "items": [3067]},
        ],
        "substitutions": [
            {
                "category": "Bottes",
                "old": "Jambières gloutonnes",
                "new": "Sandales de blindage",
                "reason": "40% vs 9% en général (80 parties)",
            }
        ],
        "skills": None,
        "item_names": {"1120": "Doran's Helm", "1036": "Long Sword", "3071": "Black Cleaver"},
        **extra,
    }


def me(items, gold=858.0):
    return {
        "team": "ORDER",
        "gold": gold,
        "items": items,
        "abilities": {"Q": 5, "W": 1, "E": 5, "R": 2},
    }


def owned(*ids):
    return [{"id": i, "name": str(i), "slot": n, "count": 1, "price": 0} for n, i in enumerate(ids)]


def view(items, gold=858.0, analysis_loadout=None, table=ITEMS):
    analysis = {"loadout": analysis_loadout if analysis_loadout is not None else loadout()}
    return en_partie.build_view(analysis, {"me": me(items, gold)}, table)


def test_les_objets_possedes_sont_coches_dans_le_plan():
    build = view(owned(1120, 1036, 3071, 3008))
    flags = {i["id"]: i["owned"] for block in build["blocks"] for i in block["items"]}
    assert flags[1120] and flags[1036] and flags[3071] and flags[3008]
    assert not flags[3053] and not flags[3047]


def test_prochain_objet_et_manque_d_or():
    build = view(owned(1120, 3071, 3008), gold=858.0)
    nxt = build["next"]
    assert nxt["name"] == "Lame de Sterak"  # le Fendoir noir est acheté
    assert nxt["cost"] == 600 + 800  # assemblage + Gemme ardente, pas encore possédée
    assert (nxt["gold"], nxt["missing"]) == (858, 542)


def test_un_composant_possede_baisse_le_cout():
    nxt = view(owned(3071, 3008, 3067), gold=858.0)["next"]
    assert nxt["cost"] == 600 and nxt["missing"] == 0


def test_les_bottes_se_visent_quand_le_core_est_achete_et_les_alternatives_ne_comptent_pas():
    nxt = view(owned(3071, 3053))["next"]
    assert nxt["id"] == 3008  # la première paire de bottes seulement
    done = view(owned(3071, 3053, 3047))  # des bottes alternatives suffisent
    assert done["next"] is None and done["complete"]


def test_le_cout_de_la_partie_reelle():
    real = me_of(
        json.loads((FIXTURES / "spike_live" / "allgamedata_items.json").read_text("utf-8"))
    )
    build = en_partie.build_view({"loadout": loadout()}, {"me": real}, ITEMS)
    assert build["next"]["id"] == 3053 and build["next"]["gold"] == 857  # or de la partie réelle
    assert build["next"]["missing"] == 1400 - 857


def test_sans_items_dans_l_api_les_achats_sont_indisponibles():
    build = en_partie.build_view({"loadout": loadout()}, {"me": {**me(None)}}, ITEMS)
    assert build["tracking"] is False and build["next"] is None and not build["complete"]
    api = {
        "gameData": {},
        "activePlayer": {"summonerName": "x"},
        "allPlayers": [{"summonerName": "x", "team": "ORDER"}],
    }
    assert me_of(api)["items"] is None  # la clé absente de l'API, pas une liste vide
    assert me_of({**api, "allPlayers": [{**api["allPlayers"][0], "items": []}]})["items"] == []


def test_aucun_achat_au_debut_de_la_partie_est_un_suivi_valide():
    build = view([])
    assert build["tracking"] is True and build["next"]["id"] == 3071


def test_cout_indisponible_sans_data_dragon():
    nxt = view(owned(1120), table={})["next"]
    assert nxt["cost"] is None and nxt["missing"] is None
    assert nxt["name"] == "Black Cleaver"  # le nom de la page OneTricks en repli


def test_substitutions_du_duel():
    assert view(owned())["substitutions"][0]["new"] == "Sandales de blindage"


def test_pas_de_plan_sans_loadout():
    assert en_partie.build_view({"loadout": None}, {"me": me(owned())}, ITEMS) == {
        "available": False
    }
    assert en_partie.build_view(None, {}, ITEMS) == {"available": False}


# ---------- ordre des compétences : seulement si la page le publie ----------


def page_with_skills():
    return {
        "firstItemStats": {"all": {"all": {k: SKILLS[k] for k in ("skillPaths", "maxSkillOrders")}}}
    }


def test_l_ordre_des_competences_quand_la_page_le_publie():
    skills = _skills(page_with_skills())
    assert skills["max_order"] == ["Q", "E", "W"] and skills["levels"][:3] == ["Q", "E", "W"]
    build = view(owned(), analysis_loadout=loadout(skills=skills))
    assert build["skills"]["max_order"] == "Q > E > W"
    assert build["skills"]["levels"].startswith("Q E W Q Q R")
    assert build["skills"]["playrate"] == round(skills["playrate"] * 100)
    assert build["skills"]["current"] == "Q 5 W 1 E 5 R 2"


def test_pas_d_ordre_des_competences_si_la_page_ne_le_publie_pas():
    page = json.loads((FIXTURES / "onetricks_jinx_bot.json").read_text(encoding="utf-8"))
    assert _skills({"firstItemStats": page["firstItemStats"]}) is None
    assert view(owned())["skills"] is None
    assert _skills({}) is None


# ---------- sur la page ----------


@pytest.fixture
def client(temp_db, bus, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setattr(client_config, "DDRAGON_VERSION", "16.2.1")
    catalog = {
        "data": {
            str(i): {
                "name": d["name"],
                "gold": {"base": d["base"], "total": d["total"]},
                "from": [str(p) for p in d["parts"]],
            }
            for i, d in ITEMS.items()
        }
    }
    files = {
        f"{BASE}/cdn/16.2.1/data/fr_FR/champion.json": json.dumps(CHAMPIONS).encode(),
        f"{BASE}/cdn/16.2.1/data/fr_FR/item.json": json.dumps(catalog).encode(),
    }
    app = create_app(temp_db, bus=bus, assets=Assets(tmp_path / "cache", fetch=files.get))
    return TestClient(app, base_url=LOCAL, raise_server_exceptions=False)


LIVE = {"state": "live", "game_time": 600.0, "p": 0.5, "delta": 0.0, "series": []}


def test_page_plan_suivi_et_competences(client, bus):  # noqa: F811
    bus.publish("ingame", {**LIVE, "me": me(owned(1120, 3071, 3008))})
    bus.publish(
        "game",
        {
            "lines": [],
            "win_probability": 0.5,
            "draft_diff": 0.0,
            "evaluation": "Draft équilibré",
            "loadout": loadout(skills=_skills(page_with_skills())),
        },
    )
    html = client.get("/en-partie/stage").text
    assert "Prochain objet" in html and "Lame de Sterak" in html and "il manque 542" in html
    assert html.count("is-owned") == 3 and "/assets/item/3071.png" in html
    assert "Q &gt; E &gt; W" in html and "Adaptations au duel" in html


def test_page_sans_items_dit_achats_indisponibles(client, bus):  # noqa: F811
    bus.publish("ingame", {**LIVE, "me": me(None)})
    bus.publish(
        "game",
        {
            "lines": [],
            "win_probability": 0.5,
            "draft_diff": 0.0,
            "evaluation": "Draft équilibré",
            "loadout": loadout(),
        },
    )
    html = client.get("/en-partie/stage").text
    assert "Achats indisponibles" in html and "Prochain objet" not in html
    assert "Compétences" not in html  # la page ne le publie pas


def test_page_sans_loadout(client, bus):  # noqa: F811
    bus.publish("ingame", {**LIVE, "me": me(owned())})
    assert "Plan de build indisponible" in client.get("/en-partie/stage").text
