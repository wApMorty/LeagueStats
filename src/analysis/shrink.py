"""Combien faire confiance à un delta mesuré ? (SPEC-13)

``confidence(games) = games / (games + K)`` shrinke les petits échantillons vers
le neutre. La forme est celle du shrink bayésien optimal, mais K valait 500 par
convention — une valeur devinée, jamais mesurée. Ce module la calcule.

Modèle de mesure d'un delta observé::

    d_obs = d_vrai + bruit,   d_vrai ~ N(0, var_signal),   bruit ~ N(0, C/n)

``C/n`` est la variance binomiale d'un winrate sur n parties, exprimée en points
de winrate² : ``C = 10000 · p(1-p)``, soit ~2500 autour de p=0.5. C'est une
constante *physique*, pas un paramètre à régler — mesurée indépendamment sur les
cinq lanes, elle retombe entre 2284 et 2617.

Le poids bayésien optimal d'une mesure est alors::

    var_signal / (var_signal + C/n)  =  n / (n + C/var_signal)

C'est exactement ``confidence(n)`` avec ``K = C / var_signal``. Seul
``var_signal`` dépend de la méta, et il s'estime sur la table elle-même : d'où
un K recalculé à chaque scrape (``src/pipeline.py``) plutôt qu'une constante qui
vieillit en silence.

**Pourquoi un MLE et pas la méthode des moments.** ``var_signal = moyenne(d² −
C/n)`` est non biaisé et tient en une ligne, mais soustrait deux grands nombres
pour en obtenir un petit : à n=100 le terme de bruit vaut ~25 pp² quand le
signal en vaut ~1. Mesuré, cet estimateur donnait 0.91 à 3.17 selon la lane là
où le MLE — qui pondère chaque ligne par sa précision — donne 1.14 à 1.37 avec
des intervalles bootstrap qui se recouvrent. La variation apparente entre lanes
était du bruit d'estimateur, d'où un K par *type* (matchup/synergie) et non par
lane.
"""

import math
from typing import Dict, List, Optional, Sequence, Tuple

from ..config_constants import analysis_config
from .probability import confidence

# (delta2 en points de winrate, winrate en %, games)
Sample = Tuple[float, float, int]

# Seules tables dont les colonnes correspondent au modèle ci-dessus. Un nom de
# table ne peut pas être passé en paramètre SQL : la whitelist tient lieu de
# requête paramétrée (CLAUDE.md « Sécurité »).
_TABLES = {"matchups": "shrink_k_matchup", "synergies": "shrink_k_synergy"}


def meta_key(table: str) -> str:
    """Clé ``db_meta`` sous laquelle le K de cette table est stocké."""
    return _TABLES[table]


def noise_variance(winrate_pct: float, games: int) -> float:
    """Variance d'échantillonnage d'un winrate, en points de winrate²."""
    p = winrate_pct / 100.0
    return 10000.0 * p * (1.0 - p) / games


def fetch_samples(db, table: str) -> List[Sample]:
    """Lit (delta2, winrate, games) d'une table de paires.

    Même parti pris que ``calibration.fetch_labeled_predictions`` : la lecture
    vit à côté du calcul qu'elle alimente plutôt que dans un repository, parce
    qu'elle n'a qu'un seul appelant et qu'elle n'est pas du CRUD.
    """
    if table not in _TABLES:
        raise ValueError(f"table inattendue : {table!r} (attendu : {sorted(_TABLES)})")
    cursor = db.connection.cursor()
    # nosec: `table` vient de la whitelist _TABLES, jamais d'une entrée utilisateur.
    cursor.execute(
        f"SELECT delta2, winrate, games FROM {table} "  # noqa: S608
        "WHERE games > 0 AND delta2 IS NOT NULL AND winrate IS NOT NULL"
    )
    return cursor.fetchall()


def estimate_signal_variance(samples: Sequence[Sample], iterations: int = 60) -> float:
    """Variance du signal réel, hors bruit d'échantillonnage (MLE à 1 paramètre).

    Maximise la vraisemblance de ``d_i ~ N(0, v + c_i)`` en v, avec
    ``c_i = noise_variance(...)``. Le score::

        f(v) = Σ (d_i² − (v + c_i)) / (v + c_i)²

    est décroissant en v : une bissection suffit, sans dépendance externe
    (même parti pris que ``calibration.suggest_scale``).

    Returns:
        La variance estimée, en points de winrate². 0.0 quand la table ne
        contient pas plus de dispersion que son propre bruit — c'est le cas des
        synergies sur certaines lanes, et ça veut dire « aucun signal mesurable »,
        pas « erreur ».
    """
    terms = [
        (delta2 * delta2, noise_variance(winrate, games))
        for delta2, winrate, games in samples
        if games > 0 and 0.0 < winrate < 100.0
    ]
    if not terms:
        return 0.0

    def score(v: float) -> float:
        return sum((d2 - (v + c)) / (v + c) ** 2 for d2, c in terms)

    low, high = 0.0, float(analysis_config.SHRINK_MAX_SIGNAL_VARIANCE)
    if score(low) <= 0.0:
        return 0.0  # dispersion <= bruit : rien à extraire
    if score(high) >= 0.0:
        return high  # borne de sécurité, jamais atteinte sur des données saines

    for _ in range(iterations):
        mid = (low + high) / 2.0
        if score(mid) > 0.0:
            low = mid
        else:
            high = mid
    return (low + high) / 2.0


def estimate_shrink_k(samples: Sequence[Sample]) -> Optional[float]:
    """``K = C / var_signal`` pour ``confidence(games, k)``, ou None si indécidable.

    Borné par ``SHRINK_K_MIN``/``SHRINK_K_MAX`` : un scrape dégénéré (table
    tronquée, winrates aberrants) ne doit pas pouvoir annuler le modèle entier
    en renvoyant un K astronomique, ni le rendre crédule avec un K proche de 0.

    Returns:
        Le K estimé, ou None quand l'échantillon est vide ou sans signal
        mesurable — l'appelant garde alors sa valeur précédente plutôt que
        d'écrire une valeur inventée.
    """
    usable = [s for s in samples if s[2] > 0 and 0.0 < s[1] < 100.0]
    if not usable:
        return None

    variance = estimate_signal_variance(usable)
    if variance <= 0.0:
        return None

    mean_c = sum(noise_variance(winrate, 1) for _, winrate, _ in usable) / len(usable)
    return min(
        max(mean_c / variance, float(analysis_config.SHRINK_K_MIN)),
        float(analysis_config.SHRINK_K_MAX),
    )


def refresh_shrink_k(db) -> dict:
    """Recalcule et stocke le K de chaque table de paires dans ``db_meta``.

    Appelé par le pipeline après chaque recompute. Une table sans signal
    mesurable laisse sa clé inchangée (cf. ``estimate_shrink_k``).

    Returns:
        {nom de table: K écrit}, les tables ignorées étant absentes du dict.
    """
    written = {}
    for table in _TABLES:
        try:
            k = estimate_shrink_k(fetch_samples(db, table))
        except Exception as e:  # une table absente ne doit jamais casser le pipeline
            print(f"[WARN] Estimation du shrink impossible sur {table}: {e}")
            continue
        if k is None:
            continue
        db.set_meta(meta_key(table), f"{k:.1f}")
        written[table] = k
    return written


def _stored_k(db, table: str) -> Optional[float]:
    """K lu dans ``db_meta``, ou None si absent ou inexploitable."""
    try:
        raw = db.get_meta(meta_key(table))
        if raw is None:
            return None
        value = float(raw)
        return value if math.isfinite(value) and value > 0.0 else None
    except (TypeError, ValueError, KeyError):
        return None


def read_shrink_k(db, table: str) -> float:
    """K stocké pour ``table``, ou ``CONFIDENCE_K`` si absent/illisible.

    Le repli sur la constante garde le modèle fonctionnel sur une base qui n'a
    pas encore vu passer un pipeline depuis SPEC-13 — mais il fait alors tourner
    un modèle qu'on sait mal pondéré. ``shrink_is_measured()`` existe pour que
    l'appelant puisse le dire à l'utilisateur au lieu de le taire.
    """
    stored = _stored_k(db, table)
    return stored if stored is not None else float(analysis_config.CONFIDENCE_K)


def shrink_is_measured(db) -> bool:
    """True quand les deux K viennent d'une mesure, pas du repli.

    SPEC-09 (« ignorance visible ») : un repli silencieux vers CONFIDENCE_K
    laisse le Live Coach afficher des probabilités calculées avec des poids
    qu'on sait faux, sans que rien ne le signale. C'est arrivé en vrai — une
    partie jouée le 2026-09-21 a tourné sur l'ancien shrink parce que le
    pipeline n'avait pas été relancé, et aucune ligne ne le disait.
    """
    return all(_stored_k(db, table) is not None for table in _TABLES)


def shrunk_lane_winrates(db, lane: Optional[str]) -> Dict[str, float]:
    """Winrate de chaque champion sur ``lane``, rétréci vers la moyenne de la lane (SPEC-18).

    C'est la force d'un champion en blind pick. ``avg_delta2`` ne l'est pas : le
    delta2 de LoLalytics est un écart à la moyenne du champion, sa moyenne sur
    les adversaires est nulle par construction, et sa dispersion entre
    champions est du bruit pur (variance de signal nulle sur les 5 lanes).

    Même modèle que les paires, au niveau du champion : l'écart à la moyenne
    de la lane, et non à 50 %. Les winrates LoLalytics sont en moyenne à ~52,4 %
    sur chaque lane, et centrer sur 50 gonflerait la variance mesurée. K est
    estimé à chaque appel : quelques dizaines de champions, c'est instantané,
    et ça évite une clé ``db_meta`` de plus à tenir à jour.

    Returns:
        {nom du champion: winrate rétréci en %} ; vide sans données.
    """
    raw = db.get_lane_winrates(lane)
    total_games = sum(games for _, games in raw.values())
    if not total_games:
        return {}
    mean = sum(winrate * games for winrate, games in raw.values()) / total_games
    k = estimate_shrink_k([(wr - mean, wr, games) for wr, games in raw.values()])
    if k is None:
        k = float(analysis_config.CONFIDENCE_K)
    return {
        name: mean + (winrate - mean) * confidence(games, k)
        for name, (winrate, games) in raw.items()
    }
