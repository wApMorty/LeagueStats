"""Database backup/restore around destructive pipeline runs (SPEC-01 A5).

``src/multilane.py`` DROPs the matchups/synergies tables before ~45 minutes
of scraping (see ``scrape_all_multilane``). Any interruption in that window
used to destroy the database outright — the exact mechanism behind the
2026-06-01 incident (40 753 -> 16 179 matchups). ``backup_database()``
snapshots the file first via ``sqlite3.Connection.backup()`` (safe even with
another connection already open on the same path, unlike ``shutil.copy``);
``restore_database()`` reverses it when a run fails.
"""

import logging
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger("update_all")

_BACKUP_NAME_RE = re.compile(r"^db\.backup-\d{8}T\d{6}Z\.db$")


def _sqlite_copy(source_path: Path, dest_path: Path) -> None:
    source = sqlite3.connect(str(source_path))
    try:
        dest = sqlite3.connect(str(dest_path))
        try:
            source.backup(dest)
        finally:
            dest.close()
    finally:
        source.close()


def backup_database(database_path: str) -> Path:
    """Snapshot ``database_path`` to a timestamped sibling ``db.backup-*.db``.

    Returns the backup's path.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = Path(database_path).resolve().parent / f"db.backup-{timestamp}.db"

    _sqlite_copy(Path(database_path), backup_path)

    logger.info("Database backed up to %s", backup_path)
    return backup_path


def restore_database(backup_path: Path, database_path: str) -> None:
    """Overwrite ``database_path`` with the contents of ``backup_path``."""
    _sqlite_copy(backup_path, Path(database_path))
    logger.warning("Database restored from %s", backup_path)


def purge_old_backups(database_path: str, retention: int) -> None:
    """Keep only the ``retention`` most recent backups, delete the rest."""
    backup_dir = Path(database_path).resolve().parent
    backups = sorted(
        (p for p in backup_dir.glob("db.backup-*.db") if _BACKUP_NAME_RE.match(p.name)),
        reverse=True,
    )
    for stale in backups[retention:]:
        try:
            stale.unlink()
            logger.info("Purged old backup %s", stale)
        except OSError as e:
            logger.warning("Failed to purge backup %s: %s", stale, e)


def _read_scrape_utc(path: Path) -> Tuple[bool, Optional[str]]:
    """Lecture seule de ``db_meta.last_scrape_utc`` : ``(lisible, valeur ou None)``.

    Illisible (absent, corrompu) : ``(False, None)``. Base sans table ``db_meta`` (pré-migration) :
    ``(True, None)``.
    """
    if not path.is_file():
        return False, None
    try:
        connection = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    except sqlite3.Error:
        return False, None
    try:
        try:
            row = connection.execute(
                "SELECT value FROM db_meta WHERE key = ?", ("last_scrape_utc",)
            ).fetchone()
        except sqlite3.OperationalError:
            return True, None
        return True, (row[0] if row else None)
    except sqlite3.Error:
        return False, None
    finally:
        connection.close()


def distinct_snapshots(database_path: str) -> List[Path]:
    """Scrapes distincts de ``database_path`` et de ses sauvegardes, du plus récent au plus ancien.

    Candidats : la base, puis les ``db.backup-*.db`` voisins triés par nom décroissant. Une seule
    par ``db_meta.last_scrape_utc`` (la première vue). Illisible : écarté. Sans valeur : la base
    reste en tête si elle est lisible, les sauvegardes sans valeur sont écartées.
    """
    base = Path(database_path)
    backups = sorted(
        (p for p in base.resolve().parent.glob("db.backup-*.db") if _BACKUP_NAME_RE.match(p.name)),
        reverse=True,
    )
    kept: List[Path] = []
    seen: set = set()
    for index, path in enumerate([base, *backups]):
        readable, value = _read_scrape_utc(path)
        if not readable:
            continue
        if value is None:
            if index == 0:
                kept.append(path)
            continue
        if value not in seen:
            seen.add(value)
            kept.append(path)
    return kept
