"""Accès SQLite du client (SPEC-21 §4.2).

Une connexion en lecture seule **par requête** : `Database.connect()` imprime, crée des index
(écriture) et sa connexion n'est pas partageable entre fils, rien de tout cela ne convient à un
serveur. Les repositories ne lisent que `db.connection`, d'où le `DbHandle`.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Union

from ..config_client import client_config


class DbHandle:
    """Ce que lisent les repositories : un objet qui porte `.connection`."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection


@contextmanager
def read_only(db_path: Union[str, Path]) -> Iterator[DbHandle]:
    """Ouvre `db_path` en `mode=ro` (jamais créé, jamais écrit) et le referme à la sortie.

    Raises:
        sqlite3.OperationalError: base absente, ou verrouillée au-delà du délai d'attente.
    """
    uri = f"{Path(db_path).resolve().as_uri()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=client_config.DB_READ_TIMEOUT_S)
    try:
        yield DbHandle(connection)
    finally:
        connection.close()
