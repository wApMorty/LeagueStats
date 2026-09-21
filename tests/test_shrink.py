"""SPEC-13 : estimation du shrink des tables de paires (src/analysis/shrink.py).

Le test central est ``test_mle_recovers_known_variance`` : on fabrique des
deltas dont on CONNAÎT la variance de signal, et on vérifie que l'estimateur la
retrouve. C'est la seule façon de valider un estimateur — sur les données
réelles, la vraie valeur est justement ce qu'on cherche.
"""

import math
import random

import pytest

from src.analysis.probability import confidence
from src.analysis.shrink import (
    estimate_shrink_k,
    estimate_signal_variance,
    fetch_samples,
    noise_variance,
    read_shrink_k,
    shrink_is_measured,
)
from src.config_constants import analysis_config


class _FakeDb:
    """db_meta minimal : juste ce que read_shrink_k consomme."""

    def __init__(self, meta=None):
        self._meta = meta or {}

    def get_meta(self, key):
        return self._meta.get(key)


def _synthetic(signal_variance, count=6000, seed=0):
    """Deltas tirés du modèle de shrink.py, avec un signal de variance connue.

    Les effectifs couvrent la plage réelle de la base (quelques dizaines à
    quelques milliers de parties) : c'est cette hétérogénéité qui met en défaut
    la méthode des moments et que le MLE doit encaisser.
    """
    rng = random.Random(seed)
    samples = []
    for _ in range(count):
        games = rng.choice([30, 80, 150, 400, 1200, 5000])
        winrate = 50.0 + rng.gauss(0, 2)
        true_delta = rng.gauss(0, math.sqrt(signal_variance))
        noise = rng.gauss(0, math.sqrt(noise_variance(winrate, games)))
        samples.append((true_delta + noise, winrate, games))
    return samples


@pytest.mark.parametrize("true_variance", [0.5, 1.4, 4.0])
def test_mle_recovers_known_variance(true_variance):
    """L'estimateur retrouve la variance de signal qui a généré les données."""
    estimated = estimate_signal_variance(_synthetic(true_variance))
    assert estimated == pytest.approx(true_variance, rel=0.20)


def test_pure_noise_yields_no_signal():
    """Des deltas qui ne sont QUE du bruit ne doivent pas produire de signal.

    C'est le cas mesuré sur les synergies de top/jungle : l'estimateur doit
    répondre « rien », pas inventer une petite variance positive.
    """
    assert estimate_signal_variance(_synthetic(0.0)) == 0.0
    assert estimate_shrink_k(_synthetic(0.0)) is None


def test_less_signal_means_more_shrink():
    """Moins de signal réel => K plus grand => les petits échantillons pèsent moins.

    C'est toute la thèse de SPEC-13, et ce qui sépare les synergies (peu de
    signal, fort shrink) des matchups.
    """
    k_strong = estimate_shrink_k(_synthetic(4.0))
    k_weak = estimate_shrink_k(_synthetic(0.5))
    assert k_weak > k_strong
    assert confidence(500, k_weak) < confidence(500, k_strong)


def test_estimated_k_stays_within_bounds():
    """Un signal quasi nul ne doit pas produire un K capable d'annuler le modèle."""
    k = estimate_shrink_k(_synthetic(0.01, count=2000))
    assert k is None or k <= analysis_config.SHRINK_K_MAX


def test_empty_samples_are_undecidable():
    assert estimate_shrink_k([]) is None
    assert estimate_signal_variance([]) == 0.0


def test_degenerate_rows_are_ignored():
    """games <= 0 ou winrate hors ]0, 100[ : variance de bruit indéfinie."""
    assert estimate_shrink_k([(3.0, 50.0, 0), (2.0, 0.0, 100), (1.0, 100.0, 100)]) is None


def test_confidence_default_is_unchanged():
    """Les 14 appelants d'avant SPEC-13 gardent exactement leur comportement."""
    for games in (0, 10, 500, 5000):
        assert confidence(games) == confidence(games, analysis_config.CONFIDENCE_K)
        assert confidence(games) == games / (games + analysis_config.CONFIDENCE_K)


def test_confidence_half_weight_at_k():
    assert confidence(1900, 1900) == pytest.approx(0.5)


def test_read_shrink_k_falls_back_to_constant():
    """Base jamais passée par un pipeline SPEC-13 : le modèle reste fonctionnel."""
    assert read_shrink_k(_FakeDb(), "matchups") == float(analysis_config.CONFIDENCE_K)


@pytest.mark.parametrize("stored", ["0", "-5", "pas un nombre", "nan", "inf"])
def test_read_shrink_k_rejects_unusable_values(stored):
    """Une valeur corrompue en base ne doit pas propager un NaN dans les logits."""
    db = _FakeDb({"shrink_k_matchup": stored})
    value = read_shrink_k(db, "matchups")
    assert math.isfinite(value) and value > 0


def test_read_shrink_k_uses_stored_value():
    db = _FakeDb({"shrink_k_synergy": "4200.0"})
    assert read_shrink_k(db, "synergies") == 4200.0


def test_shrink_is_measured_detects_the_silent_fallback():
    """Régression : une base sans K mesuré faisait tourner le Live Coach sur
    CONFIDENCE_K sans rien signaler (partie du 2026-09-21, pipeline non relancé
    après le bump SPEC-13). Le repli reste, mais il doit être détectable."""
    assert shrink_is_measured(_FakeDb()) is False
    assert shrink_is_measured(_FakeDb({"shrink_k_matchup": "1897"})) is False
    assert (
        shrink_is_measured(_FakeDb({"shrink_k_matchup": "1897", "shrink_k_synergy": "6460"}))
        is True
    )


def test_shrink_is_measured_rejects_a_corrupt_value():
    """Une clé présente mais inexploitable est une absence de mesure, pas une mesure."""
    assert (
        shrink_is_measured(_FakeDb({"shrink_k_matchup": "1897", "shrink_k_synergy": "0"})) is False
    )


def test_fetch_samples_rejects_unknown_table():
    """Le nom de table ne peut pas être paramétré en SQL : la whitelist en tient
    lieu (CLAUDE.md « Sécurité »). Une table hors liste doit lever, pas requêter."""
    with pytest.raises(ValueError):
        fetch_samples(_FakeDb(), "predictions; DROP TABLE champions")
