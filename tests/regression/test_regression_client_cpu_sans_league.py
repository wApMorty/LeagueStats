"""Régression client : League fermé, le client consomme presque un cœur et ses pages mettent 7 à 11 s.

Symptôme (@pj35, 2026-11-06) : « écran noir » en ouvrant l'écran Suggestions, League fermé. Le client
lancé depuis 15 min consommait 93 % d'un cœur ; l'accueil répondait en 7 s et l'écran Pool en 11 s, la
fenêtre restant sombre pendant l'attente.

Cause racine : sans `lockfile`, `LCUClient.find_lcu_credentials` parcourt tous les processus de Windows
(`psutil.process_iter`, 284 processus, 1 s de CPU mesurée). La sonde de l'écran, le suivi de partie, le
Live Coach et le WebSocket le relancent chacun toutes les 3 à 30 s, avec leur propre `LCUClient`.

Correctif : un parcours qui ne trouve rien est mémorisé pour tout le processus pendant
`LCU_PROCESS_SCAN_ABSENT_TTL_S` ; le `lockfile`, qui ne coûte rien, reste lu à chaque appel.

Prévention : ces tests comptent les parcours des processus entre deux `LCUClient` distincts.
"""

from unittest.mock import patch

import pytest

from src import lcu_client as lcu_module
from src.config_constants import draft_config
from src.lcu_client import LCUClient, LCUCredentials


@pytest.fixture
def scans(monkeypatch):
    """Lockfile absent ; compte les parcours des processus (aucun client LoL trouvé)."""
    monkeypatch.setattr(LCUClient, "_find_credentials_lockfile", lambda self: None)
    calls = []
    monkeypatch.setattr("psutil.process_iter", lambda *a, **k: calls.append(1) or iter([]))
    return calls


@pytest.fixture
def clock(monkeypatch):
    """Horloge monotone pilotée par le test."""
    now = [1000.0]
    monkeypatch.setattr(lcu_module.time, "monotonic", lambda: now[0])
    return now


def test_un_parcours_vide_n_est_pas_refait_par_un_autre_client(scans, clock):
    assert LCUClient().find_lcu_credentials() is None
    assert LCUClient().find_lcu_credentials() is None

    assert len(scans) == 1


def test_le_parcours_reprend_apres_le_delai(scans, clock):
    LCUClient().find_lcu_credentials()
    clock[0] += draft_config.LCU_PROCESS_SCAN_ABSENT_TTL_S + 0.1
    LCUClient().find_lcu_credentials()

    assert len(scans) == 2


def test_le_lockfile_est_lu_meme_pendant_le_delai(scans, clock):
    LCUClient().find_lcu_credentials()
    found = LCUCredentials(port=1234, password="x", base_url="https://127.0.0.1:1234")

    with patch.object(LCUClient, "_find_credentials_lockfile", lambda self: found):
        assert LCUClient().find_lcu_credentials() == found
