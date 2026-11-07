"""add rank_snapshots.puuid and attribute existing photos

Revision ID: b52d1e7c9a40
Revises: a3f6c1d8b7e2
Create Date: 2026-11-07

SPEC-52 tâche 258 — chaque photo de rang porte le compte qui l'a prise. L'historique est rattaché :
photo liée à une partie → compte du joueur dans la partie ; photo de démarrage → compte dont le total
victoires + défaites est proche ; photo restante prise à la même seconde qu'une photo de démarrage
attribuée d'une autre file → même compte. Le reste garde NULL.
"""

import json
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b52d1e7c9a40"
down_revision: Union[str, Sequence[str], None] = "a3f6c1d8b7e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Figées avec la migration (elle ne lit pas config_constants.py, qui peut changer après coup).
MAX_GAMES_GAP = 10  # parties jouées entre deux démarrages sans photo liée
PAIR_SECONDS = 2  # snapshot_current écrit solo et flexible dans la même seconde


def _game_accounts(conn) -> Dict[int, str]:
    """game_id -> puuid du joueur, lu dans le brut de chaque partie capturée."""
    accounts = {}
    rows = conn.exec_driver_sql(
        "SELECT game_id, player_participant_id, raw_game FROM game_records"
    ).fetchall()
    for game_id, participant_id, raw in rows:
        try:
            identities = json.loads(raw).get("participantIdentities") or []
        except (TypeError, ValueError, AttributeError):
            continue
        for identity in identities:
            puuid = (identity.get("player") or {}).get("puuid")
            if identity.get("participantId") == participant_id and puuid:
                accounts[game_id] = puuid
    return accounts


def attribute(photos: List[tuple], game_accounts: Dict[int, str]) -> Dict[int, str]:
    """id de photo -> puuid. `photos` : (id, captured_utc, queue, wins, losses, game_id)."""
    found: Dict[int, str] = {}
    for pid, _, _, _, _, game_id in photos:
        if game_id is not None and game_id in game_accounts:
            found[pid] = game_accounts[game_id]
    linked = [p for p in photos if p[0] in found]
    for pid, _, queue, wins, losses, game_id in photos:
        if pid in found or game_id is not None or wins is None or losses is None:
            continue
        near = {
            found[other[0]]
            for other in linked
            if other[2] == queue
            and other[3] is not None
            and other[4] is not None
            and abs(other[3] + other[4] - wins - losses) <= MAX_GAMES_GAP
        }
        if len(near) == 1:
            found[pid] = near.pop()
    startup = [p for p in photos if p[5] is None and p[0] in found]
    for pid, captured, queue, _, _, game_id in photos:
        if pid in found or game_id is not None:
            continue
        mate = _pair(captured, queue, startup)
        if mate is not None:
            found[pid] = found[mate]
    return found


def _pair(captured: str, queue: str, startup: List[tuple]) -> Optional[int]:
    """La photo de démarrage attribuée d'une autre file prise à moins de PAIR_SECONDS."""
    when = datetime.fromisoformat(captured)
    for other in startup:
        gap = abs((datetime.fromisoformat(other[1]) - when).total_seconds())
        if other[2] != queue and gap <= PAIR_SECONDS:
            return other[0]
    return None


def upgrade() -> None:
    """Add rank_snapshots.puuid, index it, attribute existing photos."""
    op.execute("ALTER TABLE rank_snapshots ADD COLUMN puuid TEXT")
    op.execute("CREATE INDEX idx_rank_snapshots_puuid ON rank_snapshots(puuid, id)")
    conn = op.get_bind()
    photos = conn.exec_driver_sql(
        "SELECT id, captured_utc, queue, wins, losses, game_id FROM rank_snapshots ORDER BY id"
    ).fetchall()
    found = attribute([tuple(p) for p in photos], _game_accounts(conn))
    if found:
        conn.exec_driver_sql(
            "UPDATE rank_snapshots SET puuid = ? WHERE id = ?",
            [(puuid, pid) for pid, puuid in found.items()],
        )
    print(
        f"[DATA] rank_snapshots : {len(found)} photos rattachées, "
        f"{len(photos) - len(found)} sans compte"
    )


def downgrade() -> None:
    """Drop rank_snapshots.puuid and its index."""
    op.execute("DROP INDEX idx_rank_snapshots_puuid")
    op.execute("ALTER TABLE rank_snapshots DROP COLUMN puuid")
