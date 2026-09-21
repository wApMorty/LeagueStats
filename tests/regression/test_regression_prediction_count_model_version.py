"""Régression : le compteur de prédictions labellisées ignorait model_version.

Remonté par @pj35 le 2026-09-21. Juste après le bump MODEL_VERSION de SPEC-13,
le Live Coach affichait :

    [OUTCOME] 1 prédiction(s) en attente rattrapée(s) · 54 labellisées au total
              (30 requises pour calibrer)

alors qu'une seule prédiction relevait du modèle courant. Les 54 additionnaient
quatre générations (b7-v1: 31, b7-v1+lane-restante: 16, spec12-v1: 5,
spec13-v1: 2).

Deux conséquences, la seconde bien plus grave que l'affichage :

1. Le message contredisait ``scripts/calibrate_model.py``, qui filtre, lui, et
   aurait refusé de calibrer faute de données.
2. ``lane_restante.is_enabled()`` s'appuie sur le même compteur pour décider
   d'activer la pondération SPEC-11. Le garde-fou s'ouvrait donc sur des
   parties jouées sous un AUTRE modèle : une éval était déclarée éprouvée par
   l'expérience acquise avec une autre.
"""

import pytest

from src.analysis.lane_restante import is_enabled
from src.config_constants import analysis_config

CURRENT = analysis_config.MODEL_VERSION
OTHER = "un-vieux-modele-v1"


def _labelled(db, model_version, count, outcome=1):
    """Insère `count` prédictions labellisées sous `model_version`."""
    for _ in range(count):
        prediction_id = db.insert_prediction(
            ally_champions=[1, 2],
            enemy_champions=[3, 4],
            ally_lanes=None,
            predicted_probability=0.55,
            model_version=model_version,
        )
        assert prediction_id is not None
        assert db.update_prediction_outcome(prediction_id, outcome)


def test_counter_only_sees_the_current_model_version(db):
    _labelled(db, OTHER, 31)
    _labelled(db, CURRENT, 2)

    assert db.count_labelled_predictions(CURRENT) == 2
    assert db.count_labelled_predictions(OTHER) == 31


def test_counting_every_version_requires_asking_for_it(db):
    """Le total reste accessible, mais seulement en le demandant explicitement."""
    _labelled(db, OTHER, 31)
    _labelled(db, CURRENT, 2)

    assert db.count_labelled_predictions(None) == 33


def test_spec11_gate_ignores_experience_from_another_model(db):
    """Le cœur du bug : 31 parties sous un autre modèle ne prouvent rien sur
    celui-ci, et ne doivent pas ouvrir le garde-fou SPEC-11."""
    _labelled(db, OTHER, analysis_config.MIN_ROWS_FOR_CALIBRATION + 1)

    assert is_enabled(db) is False


def test_spec11_gate_opens_on_the_current_model(db):
    """Et il s'ouvre bien une fois le seuil atteint SOUS le modèle courant."""
    _labelled(db, CURRENT, analysis_config.MIN_ROWS_FOR_CALIBRATION)

    assert is_enabled(db) is True


def test_counter_requires_an_explicit_model_version(db):
    """L'argument n'a pas de défaut : c'est son absence qui a causé le bug.

    Un futur appelant ne doit pas pouvoir retomber par inadvertance dans le
    comptage toutes-versions — il doit écrire None pour l'obtenir.
    """
    with pytest.raises(TypeError):
        db.count_labelled_predictions()
