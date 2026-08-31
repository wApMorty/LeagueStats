"""Politique unique d'agrégation multi-lane (SPEC-03, item B1).

LoLalytics fournit une ligne par lane : un même couple (champion, adversaire)
peut exister en top, jungle, middle, bottom et support. Avant ce module, trois
traitements divergents cohabitaient dans ``src/db.py`` — moyenne pondérée,
écrasement silencieux, ou aucun regroupement — et le même matchup pouvait donc
être noté différemment selon le chemin de code emprunté.

Politique unique, appliquée par tous les accesseurs de lecture :

- ``delta2`` (et ``winrate``, ``delta1``) : moyenne pondérée par ``games``,
  ``sum(valeur * games) / sum(games)``. La valeur la mieux estimée est celle qui
  repose sur le plus grand nombre de parties.
- ``games`` : somme. C'est le volume total observé, utile pour la confiance
  (cf. SPEC-05). La somme sur l'ensemble des adversaires reste donc inchangée.
- ``pickrate`` : somme. C'est la fréquence totale de rencontre de cet
  adversaire, toutes lanes confondues, ce qui préserve son rôle de prédiction du
  pick adverse (cf. audit M3).
"""

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

# Les dataclasses de src/models.py valident pickrate et winrate dans [0, 100].
# La somme des pickrates par lane reste très en dessous (max mesuré : 46,7 sur
# la base réelle), mais on borne par sécurité plutôt que de lever une exception
# de lecture sur une donnée aberrante.
MAX_PERCENT = 100.0


@dataclass(frozen=True)
class AggregatedRow:
    """Une paire de champions, toutes lanes agrégées.

    ``winrate`` et ``delta1`` restent à ``None`` quand la requête d'origine ne
    les a pas sélectionnés (requêtes « draft », 4 colonnes).
    """

    peer_name: str
    delta2: float
    pickrate: float
    games: int
    winrate: Optional[float] = None
    delta1: Optional[float] = None


def weighted_delta2(rows: Iterable[Sequence]) -> Optional[float]:
    """Moyenne pondérée par ``games`` de lignes ``(delta2, games)``.

    Renvoie ``None`` si aucune ligne n'est fournie, et la moyenne simple si
    toutes les lignes ont ``games = 0`` (pondération impossible).
    """
    group = list(rows)
    if not group:
        return None
    return _weighted(group, 0, sum(int(row[1]) for row in group))


def aggregate_rows(rows: Iterable[Sequence]) -> Dict[str, AggregatedRow]:
    """Agrège des lignes ``(peer_name, delta2, pickrate, games)``.

    Retour : ``{peer_name.lower(): AggregatedRow}``, dans l'ordre de première
    apparition des adversaires.
    """
    return _aggregate(rows, full=False)


def aggregate_full_rows(rows: Iterable[Sequence]) -> Dict[str, AggregatedRow]:
    """Agrège des lignes ``(peer_name, winrate, delta1, delta2, pickrate, games)``."""
    return _aggregate(rows, full=True)


def aggregate_pairs(rows: Iterable[Sequence]) -> Dict[Tuple[str, str], float]:
    """Agrège des lignes ``(name_a, name_b, delta2, games)`` pour les caches bulk.

    Retour : ``{(name_a.lower(), name_b.lower()): delta2 pondéré}``. La forme du
    dictionnaire est identique à celle d'avant B1 — seule la valeur change.
    """
    grouped: Dict[Tuple[str, str], List[Sequence]] = {}
    for name_a, name_b, delta2, games in rows:
        grouped.setdefault((name_a.lower(), name_b.lower()), []).append((delta2, games))
    return {key: weighted_delta2(group) for key, group in grouped.items()}


def _aggregate(rows: Iterable[Sequence], full: bool) -> Dict[str, AggregatedRow]:
    grouped: Dict[str, List[Sequence]] = {}
    display_names: Dict[str, str] = {}
    for row in rows:
        key = row[0].lower()
        display_names.setdefault(key, row[0])
        grouped.setdefault(key, []).append(row)

    aggregated: Dict[str, AggregatedRow] = {}
    for key, group in grouped.items():
        games = sum(int(row[-1]) for row in group)
        aggregated[key] = AggregatedRow(
            peer_name=display_names[key],
            delta2=_weighted(group, 3 if full else 1, games),
            pickrate=min(MAX_PERCENT, sum(float(row[-2]) for row in group)),
            games=games,
            winrate=_weighted(group, 1, games) if full else None,
            delta1=_weighted(group, 2, games) if full else None,
        )
    return aggregated


def _weighted(group: List[Sequence], index: int, total_games: int) -> float:
    """Moyenne de ``group[index]`` pondérée par ``games`` (dernière colonne)."""
    if total_games > 0:
        return sum(float(row[index]) * int(row[-1]) for row in group) / total_games
    # Aucune partie enregistrée : la pondération est impossible, on retombe sur
    # la moyenne simple plutôt que de perdre l'information.
    return sum(float(row[index]) for row in group) / len(group)
