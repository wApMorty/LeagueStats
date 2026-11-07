"""Régression SPEC-52 : l'écran Rang mêlait les photos de deux comptes.

Symptôme : après une partie classée sur le smurf (Or I, 35 puis 65 LP le 2026-11-07), la courbe du
compte principal (Diamant IV 87 LP) descendait jusqu'à l'Or : l'axe, les graduations et le creux
affichés appartenaient au smurf.

Cause racine : `CoachingRepository.rank_history()` et `rank_snapshots()` lisaient toutes les photos de
`rank_snapshots`, sans filtre de compte, alors que la migration b52d1e7c9a40 rattache désormais chaque
photo à son `puuid`.

Correctif : lecture par compte. `rank_account()` donne le puuid de la dernière photo rattachée,
`rank_history(puuid)` et `rank_snapshots(puuid)` ne lisent que ce compte, et l'écran Rang prend le
compte connecté (`current_puuid`) ou, client fermé, le dernier compte vu.

Prévention : ce test insère la séquence du 2026-11-07 par compte et vérifie que l'écran Rang, client
fermé, ne montre que le compte principal (aucune graduation en Or, « Diamant IV » présent).
"""

import re

from fastapi.testclient import TestClient

from src.client.app import create_app

LOCAL = "http://127.0.0.1"
SOLO = "RANKED_SOLO_5x5"


def _insert(db, captured, puuid, tier, division, lp, wins, losses):
    db.connection.execute(
        "INSERT INTO rank_snapshots (captured_utc, queue, tier, division, lp, wins, losses, puuid) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (captured, SOLO, tier, division, lp, wins, losses, puuid),
    )
    db.connection.commit()


def test_rang_ne_montre_que_le_dernier_compte_vu(db, temp_db):
    _insert(db, "2026-11-03 12:00:00", "main", "DIAMOND", "IV", 87, 451, 462)
    _insert(db, "2026-11-07 09:00:00", "smurf", "GOLD", "I", 35, 17, 16)
    _insert(db, "2026-11-07 09:30:00", "smurf", "GOLD", "I", 65, 19, 16)
    _insert(db, "2026-11-07 19:27:00", "main", "DIAMOND", "IV", 87, 452, 462)

    page = TestClient(create_app(temp_db), base_url=LOCAL).get("/rang").text

    assert "Diamant IV" in page
    assert not re.search(r"\bOr\b", page)  # aucune graduation ni carte du smurf en Or
