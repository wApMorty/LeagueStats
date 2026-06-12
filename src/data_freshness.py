"""Data freshness monitoring shown at app startup (Horizon 1 — ROADMAP H1.3).

The guard-rail that was missing in spring 2026: the auto-update silently died
on 2026-03-19 and the database lost 60% of its rows on 2026-06-01, and nobody
noticed for days. The app now displays the data age at every launch and warns
when it exceeds ``data_quality_config.FRESHNESS_WARNING_DAYS``.

Reads ``db_meta.last_update_utc`` (written by scripts/update_all.py after a
fully successful run). Databases that predate migration b7e41c9a3f02 fall
back to the db file modification time.
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config_constants import data_quality_config


@dataclass
class FreshnessInfo:
    """Snapshot of the database freshness and volumetry."""

    last_update: Optional[datetime] = None
    source: str = "unknown"  # "db_meta" | "file_mtime" | "unknown"
    matchups_count: int = 0
    synergies_count: int = 0

    @property
    def age_days(self) -> Optional[float]:
        if self.last_update is None:
            return None
        return (datetime.now(timezone.utc) - self.last_update).total_seconds() / 86400

    @property
    def is_stale(self) -> bool:
        age = self.age_days
        if age is None:
            return True  # unknown age = assume stale (loud by default)
        return age > data_quality_config.FRESHNESS_WARNING_DAYS


def get_freshness_info(db_path: str) -> FreshnessInfo:
    """Read freshness metadata and volumetry from the database (read-only).

    Never raises: a missing/corrupt database returns an 'unknown' snapshot,
    which is reported as stale.
    """
    info = FreshnessInfo()
    path = Path(db_path)
    if not path.exists():
        return info

    try:
        connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            cursor = connection.cursor()

            try:
                cursor.execute("SELECT value FROM db_meta WHERE key = 'last_update_utc'")
                row = cursor.fetchone()
            except sqlite3.Error:
                row = None  # pre-migration database: no db_meta table

            if row:
                info.last_update = datetime.fromisoformat(row[0])
                if info.last_update.tzinfo is None:
                    info.last_update = info.last_update.replace(tzinfo=timezone.utc)
                info.source = "db_meta"
            else:
                info.last_update = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
                info.source = "file_mtime"

            for table, attr in (("matchups", "matchups_count"), ("synergies", "synergies_count")):
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")  # nosec B608 - literal
                    setattr(info, attr, cursor.fetchone()[0])
                except sqlite3.Error:
                    pass
        finally:
            connection.close()
    except (sqlite3.Error, ValueError, OSError):
        pass  # unknown snapshot, reported stale

    return info


def format_freshness_banner(info: FreshnessInfo) -> str:
    """Console banner shown under the app banner at startup.

    ASCII markers only ([OK]/[ALERTE]): emojis crash on cp1252 consoles
    (redirected output), and the rest of the console UI uses this style.
    """
    if info.last_update is None:
        return (
            "[ALERTE] DONNÉES INTROUVABLES — base absente ou illisible.\n"
            "         Lancez : python scripts/update_all.py"
        )

    age = info.age_days
    age_label = f"{age:.1f} j" if age >= 1 else f"{age * 24:.0f} h"
    via = " (estimé via date du fichier)" if info.source == "file_mtime" else ""

    matchups = f"{info.matchups_count:,}".replace(",", " ")
    synergies = f"{info.synergies_count:,}".replace(",", " ")
    line = (
        f"Données : {matchups} matchups, {synergies} synergies — "
        f"mises à jour il y a {age_label}{via}"
    )

    if info.is_stale:
        return (
            f"[ALERTE] DONNÉES OBSOLÈTES ({age_label} > "
            f"{data_quality_config.FRESHNESS_WARNING_DAYS} j) — {line}\n"
            f"         Vérifiez la tâche planifiée ou lancez : python scripts/update_all.py"
        )
    return f"[OK] {line}"
