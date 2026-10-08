"""Régression : changer de pool dans l'écran Pool ne changeait pas le pool de la draft suivante.

Symptôme (@pj35, 2026-10-09) : pool actif changé sur /pool, draft lancée dans la foulée, le Live Coach
recommande toujours sur l'ancien pool.

Cause racine : le Live Coach du client lit le pool une seule fois, au démarrage de son fil
(`LiveCoachThread._run`) ; l'écran Pool n'écrivait que `user_prefs.json` et `champion_pools.json`.

Correctif : l'écran dépose une commande `pool <nom>` chez le Live Coach quand le pool actif change ou
est édité ; le Live Coach la draine comme les autres commandes, recharge le pool et chauffe son cache.

Prévention : ce test suit la chaîne des deux côtés, écran (commande déposée) et Live Coach (pool,
lane et cache rechargés), et vérifie qu'un pool disparu laisse le pool courant intact.
"""

import queue
import sqlite3
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from src import pool_manager, user_prefs
from src.client.app import create_app
from src.draft.commands import CommandListener
from src.draft.state import DraftState
from tests.support_lcu_nav import make_assets
from tests.test_client_pool import LOCAL, post


@pytest.fixture
def web(temp_db, tmp_path, monkeypatch):
    """Écran Pool dont les commandes au Live Coach sont relevées dans `web.lines`."""
    monkeypatch.setattr(pool_manager, "get_user_data_path", lambda f: str(tmp_path / f))
    monkeypatch.setattr(user_prefs, "get_user_data_path", lambda f: str(tmp_path / f))
    with sqlite3.connect(temp_db) as db:
        db.executemany("INSERT INTO champions (name) VALUES (?)", [("Ahri",), ("Garen",)])
    lines = []
    app = create_app(
        temp_db, assets=make_assets(tmp_path), commands=lambda line: lines.append(line) or True
    )
    client = TestClient(app, base_url=LOCAL, raise_server_exceptions=False)
    client.lines = lines
    return client


def test_choisir_le_pool_actif_previent_le_live_coach(web):
    reply = post(web, "/pool/actif?name=Meta Picks")
    assert web.lines == ["pool Meta Picks"]
    assert "prochaine draft" in reply.text


def test_editer_le_pool_actif_previent_le_live_coach_mais_pas_un_autre_pool(web):
    post(web, "/pool/creer", data={"arg": "Main"})
    post(web, "/pool/creer", data={"arg": "Autre"})
    post(web, "/pool/actif?name=Main")
    web.lines.clear()
    post(web, "/pool/ajouter?name=Autre&arg=Ahri")
    assert web.lines == []
    post(web, "/pool/ajouter?name=Main&arg=Ahri")
    assert web.lines == ["pool Main"]


def drain(monitor, *lines):
    monitor._command_queue.get_nowait.side_effect = [*lines, queue.Empty()]
    return CommandListener(monitor).apply_pending(DraftState())


def test_la_commande_pool_recharge_le_pool_et_son_cache(monkeypatch):
    manager = Mock()
    manager.get_pool.return_value = pool_manager.ChampionPool("Main", ["Ahri", "Garen"], role="mid")
    monkeypatch.setattr(pool_manager, "PoolManager", lambda: manager)
    monitor = Mock()
    assert drain(monitor, "pool Main") is True
    assert monitor.current_pool == ["Ahri", "Garen"]
    assert (monitor.pool_name, monitor.pool_lane) == ("Main", "middle")
    monitor.assistant.warm_cache.assert_called_once_with(["Ahri", "Garen"])


def test_un_pool_disparu_ne_change_rien_et_ne_leve_pas(monkeypatch):
    manager = Mock()
    manager.get_pool.return_value = None
    monkeypatch.setattr(pool_manager, "PoolManager", lambda: manager)
    monitor = Mock(current_pool=["Zed"], pool_name="Ancien")
    assert drain(monitor, "pool Fantome") is False
    assert (monitor.current_pool, monitor.pool_name) == (["Zed"], "Ancien")
    monitor.assistant.warm_cache.assert_not_called()
