"""Backtest du modèle de draft (SPEC-43 §4.2, tâche 210) : régression, AUC, plis, termes, sélection."""

import random
import sqlite3

import pytest

from scripts import backtest_draft_model as backtest
from src.analysis.calibration import auc as calibration_auc
from src.analysis.game_eval import GameEvaluator
from src.analysis.mastery import fit_logistic
from src.analysis.probability import sigmoid
from src.config_constants import analysis_config as cfg
from src.winprob.crawl import pack


class FakeDB:
    """Tables de paires et winrates de lane figées, quelle que soit la lane demandée."""

    def __init__(self, matchups=None, synergies=None, winrates=None):
        self.matchups = matchups or {}
        self.synergies = synergies or {}
        self.winrates = winrates or {}

    def get_lane_winrates(self, lane):
        return self.winrates

    def get_all_matchups_bulk(self, lane=None, with_games=False):
        return self.matchups

    def get_all_synergies_bulk(self, lane=None, with_games=False):
        return self.synergies

    def get_meta(self, key):
        return None  # pas de K mesuré : repli sur CONFIDENCE_K


def _game(duration=1500, blue="Win", red="Fail"):
    """Partie à dix participants, bleus 100 et rouges 200, champions 1 à 10."""
    return {
        "gameDuration": duration,
        "teams": [{"teamId": 100, "win": blue}, {"teamId": 200, "win": red}],
        "participants": [
            {"participantId": pid, "teamId": 100 if pid <= 5 else 200, "championId": pid}
            for pid in range(1, 11)
        ],
    }


def _roles(lanes):
    """Postes par participantId (1 à 10), ``None`` pour un poste inconnu."""
    return dict(zip(range(1, 11), lanes))


ROLES_OK = ("top", "jungle", "middle", "bottom", "support") * 2


def test_regression_recovers_known_coefficients_and_wald_contains_them():
    rng = random.Random(cfg.BACKTEST_SEED)
    true = [-0.2, 1.0, 0.5, 0.8]
    xs, ys = [], []
    for _ in range(4000):
        x = [1.0] + [rng.gauss(0, 1) for _ in range(3)]
        xs.append(x)
        ys.append(int(rng.random() < sigmoid(sum(c * v for c, v in zip(true, x)))))
    coef = fit_logistic(xs, ys)
    intervals = backtest.wald_interval(xs, ys, coef, cfg.BACKTEST_Z90)
    for estimate, expected, (low, high) in zip(coef, true, intervals):
        assert abs(estimate - expected) <= 0.15
        assert low <= expected <= high


def test_rank_auc_matches_calibration_auc_with_ties():
    scores = [0.2, 0.5, 0.5, 0.9, 0.1, 0.5, 0.7, 0.7]
    outcomes = [0, 1, 0, 1, 0, 1, 0, 1]
    assert backtest.rank_auc(scores, outcomes) == pytest.approx(
        calibration_auc(list(zip(scores, outcomes)))
    )
    assert backtest.rank_auc(scores, [0] * 8) == 0.5


def test_cross_validate_never_predicts_a_row_its_model_saw(monkeypatch):
    events = []

    def spy_fit(train_xs, train_ys):
        events.append(("fit", {round(x[1]) for x in train_xs}))
        return [0.0, 0.0]

    def spy_predict(coef, x):
        events.append(("predict", round(x[1])))
        return 0.5

    monkeypatch.setattr(backtest, "fit_logistic", spy_fit)
    monkeypatch.setattr(backtest, "predict_logistic", spy_predict)
    xs = [[1.0, float(i)] for i in range(200)]
    predictions = backtest.cross_validate(xs, [i % 2 for i in range(200)], folds=5, seed=43)

    assert len(predictions) == 200
    trained = set()
    predicted = []
    for kind, value in events:
        if kind == "fit":
            trained = value
        else:
            assert value not in trained
            predicted.append(value)
    assert sorted(predicted) == list(range(200))


def test_game_terms_antisymmetric_and_current_is_team_logit(monkeypatch):
    monkeypatch.setattr(cfg, "K_INTRINSIC", 0.5)
    db = FakeDB(
        matchups={
            ("aatrox", "garen"): (2.0, 5000),
            ("garen", "aatrox"): (-1.0, 5000),
            ("lulu", "janna"): (1.0, 3000),
            ("aatrox", "janna"): (0.5, 800),
            ("garen", "lulu"): (-2.0, 4000),
        },
        synergies={
            ("aatrox", "lulu"): (1.5, 2000),
            ("lulu", "aatrox"): (0.5, 2000),
            ("garen", "janna"): (2.0, 4000),
        },
        winrates={
            "aatrox": (52.0, 900),
            "garen": (50.5, 2000),
            "lulu": (53.0, 1500),
            "janna": (48.0, 1200),
        },
    )
    evaluator = GameEvaluator(db)
    blue = [("Aatrox", "top"), ("Lulu", "support")]
    red = [("Garen", "top"), ("Janna", "support")]

    terms = backtest.game_terms(evaluator, blue, red)
    swapped = backtest.game_terms(evaluator, red, blue)

    assert swapped.lane == pytest.approx(-terms.lane)
    assert swapped.other == pytest.approx(-terms.other)
    assert swapped.synergy == pytest.approx(-terms.synergy)
    assert swapped.strength == pytest.approx(-terms.strength)
    assert swapped.current == pytest.approx(-terms.current)
    assert terms.current == pytest.approx(evaluator.team_logit(blue, red))
    assert terms.current == pytest.approx(
        terms.matchup * cfg.K_MATCHUP
        + terms.synergy * cfg.K_SYNERGY
        + terms.strength * cfg.K_INTRINSIC
    )


def test_select_drops_game_with_unknown_position(monkeypatch):
    names = {pid: f"Champ{pid}" for pid in range(1, 11)}
    game = _game()

    monkeypatch.setattr(backtest, "participant_roles", lambda g: _roles([*ROLES_OK[:9], None]))
    assert backtest.select(game, names) == ("postes", None)

    monkeypatch.setattr(backtest, "participant_roles", lambda g: _roles(ROLES_OK))
    motif, picked = backtest.select(game, names)
    assert motif == "retenues"
    assert len(picked.blue) == 5 and len(picked.red) == 5
    assert picked.win is True

    assert backtest.select(_game(duration=600), names) == ("courtes", None)


def test_read_games_counts_unreadable_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(backtest, "participant_roles", lambda g: _roles(ROLES_OK))
    names = {pid: f"Champ{pid}" for pid in range(1, 11)}
    crawl = sqlite3.connect(tmp_path / "crawl.db")
    crawl.execute(
        "CREATE TABLE crawl_games (game_id INTEGER PRIMARY KEY, queue_id INTEGER, "
        "game_creation_utc TEXT, read_utc TEXT, raw BLOB)"
    )
    rows = [
        (1, 420, "2026-01-01", "x", pack(_game(), None)),
        (2, 420, "2026-01-02", "x", b"pas du zlib"),
        (3, 400, "2026-01-03", "x", pack(_game(), None)),  # file hors cible
        (4, 440, "2026-01-04", "x", pack(_game(duration=600), None)),
    ]
    crawl.executemany("INSERT INTO crawl_games VALUES (?, ?, ?, ?, ?)", rows)
    counts = {key: 0 for key in backtest.COUNT_KEYS}

    games = backtest.read_games(crawl, None, names, counts)

    crawl.close()
    assert len(games) == 1
    assert counts["lues"] == 3
    assert counts["illisibles"] == 1
    assert counts["courtes"] == 1
    assert counts["retenues"] == 1


def test_effective_lane_weight_is_the_configured_weight_when_coefficients_match():
    """Les variables portent déjà SAME_LANE_WEIGHT : des coefficients égaux confirment le poids en
    vigueur (le diagnostic comparait à tort le rapport brut à 2)."""
    from src.config_constants import role_inference_config as roles

    expected = roles.SAME_LANE_WEIGHT / roles.OTHER_LANE_WEIGHT
    assert backtest.effective_lane_weight(0.7, 0.7) == pytest.approx(expected)
    assert backtest.effective_lane_weight(1.4, 0.7) == pytest.approx(2 * expected)
    assert backtest.effective_lane_weight(0.7, 0.0) is None
