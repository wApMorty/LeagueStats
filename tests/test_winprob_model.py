"""Modèle de win chance (SPEC-20 tâche 42, src/winprob/model.py et train.py). Hermétiques."""

import json
import random
import sqlite3
from pathlib import Path

from src.winprob import train
from src.winprob.crawl import SCHEMA, pack
from src.winprob.model import INPUTS, WinModel, _sigmoid, _solve, evaluate, expand, fit
from src.winprob.state import FEATURES

FIXTURES = Path(__file__).parent / "fixtures" / "spike_gameplay"
GAME = json.loads((FIXTURES / "7998195590_game.json").read_text(encoding="utf-8"))
TIMELINE = json.loads((FIXTURES / "7998195590_timeline.json").read_text(encoding="utf-8"))


def _synthetic(n, seed=1):
    """États aléatoires dont l'issue suit une logistique connue (kills et tours)."""
    rng = random.Random(seed)
    states, wins = [], []
    for _ in range(n):
        s = dict.fromkeys(FEATURES, 0.0)
        s.update(
            time_min=rng.uniform(0, 40),
            kills=rng.randint(-8, 8),
            towers=rng.randint(-4, 4),
            gold=0.0,
        )
        p = _sigmoid(0.25 * s["kills"] + 0.5 * s["towers"])
        states.append(s)
        wins.append(int(rng.random() < p))
    return states, wins


def test_solve_linear_system():
    assert [round(v, 9) for v in _solve([[2.0, 1.0], [1.0, 3.0]], [3.0, 5.0])] == [0.8, 1.4]


def test_fit_recovers_signal_and_is_calibrated():
    train_x, train_y = _synthetic(6000)
    val_x, val_y = _synthetic(3000, seed=2)
    model = fit(train_x, train_y)
    ahead = dict.fromkeys(FEATURES, 0.0) | {"time_min": 20.0, "kills": 5.0, "towers": 2.0}
    behind = dict(ahead, kills=-5.0, towers=-2.0)
    assert model.predict(ahead) > 0.85 > 0.15 > model.predict(behind)
    assert evaluate(model, val_x, val_y)["max_gap"] < 0.05


def test_json_roundtrip_keeps_predictions_and_version():
    states, wins = _synthetic(500)
    model = fit(states, wins)
    again = WinModel.from_json(model.to_json())
    assert again.version == model.version and model.version.startswith("wp-")
    assert again.predict(states[0]) == model.predict(states[0])
    assert len(expand(states[0])) == 2 * len(INPUTS)


def test_evaluate_ignores_early_images():
    states, wins = _synthetic(400)
    early = sum(1 for s in states if s["time_min"] < 10)
    assert evaluate(fit(states, wins), states, wins)["images"] == 400 - early


def test_load_splits_by_game_with_newest_in_validation(tmp_path):
    db = sqlite3.connect(tmp_path / "crawl.db")
    db.executescript(SCHEMA)
    raw = pack(GAME, TIMELINE)
    for i in range(10):
        db.execute(
            "INSERT INTO crawl_games (game_id, queue_id, game_creation_utc, depth, raw) VALUES (?, 420, ?, 1, ?)",
            (i, f"2026-10-0{i % 9 + 1} 00:00:00", raw),
        )
    db.execute(
        "INSERT INTO crawl_games (game_id, queue_id, game_creation_utc, depth, raw) VALUES (99, 420, '2026-09-01', 1, x'')"
    )
    db.commit()
    db.close()
    (train_x, train_y), (val_x, val_y) = train.load(tmp_path / "crawl.db")
    frames = len(TIMELINE["frames"])
    assert len(train_x) == 8 * frames and len(val_x) == 2 * frames  # 20 % de 10 parties
    assert set(train_y) == set(val_y) == {1}  # la fixture est une victoire bleue


def test_cross_validate_pools_every_game_once(tmp_path):
    db = sqlite3.connect(tmp_path / "crawl.db")
    db.executescript(SCHEMA)
    raw = pack(GAME, TIMELINE)
    for i in range(10):
        db.execute(
            "INSERT INTO crawl_games (game_id, queue_id, game_creation_utc, depth, raw) VALUES (?, 420, ?, 1, ?)",
            (i, f"2026-10-{i + 1:02d}", raw),
        )
    db.commit()
    db.close()
    result = train.cross_validate(tmp_path / "crawl.db", folds=5)
    after_10_min = sum(1 for f in TIMELINE["frames"] if f["timestamp"] >= 600_000)
    assert result["images"] == 10 * after_10_min
