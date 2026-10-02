"""Réentraînement champion contre challenger (SPEC-20 tâche 42b, src/winprob/retrain.py). Hermétiques."""

import json
import sqlite3
from pathlib import Path

from src.config_winprob import winprob_config as cfg
from src.winprob import retrain
from src.winprob.crawl import SCHEMA, pack
from src.winprob.model import WinModel

FIXTURES = Path(__file__).parent / "fixtures" / "spike_gameplay"
GAME = json.loads((FIXTURES / "7998195590_game.json").read_text(encoding="utf-8"))
TIMELINE = json.loads((FIXTURES / "7998195590_timeline.json").read_text(encoding="utf-8"))
MIN = cfg.WINPROB_MIN_PATCH_GAMES


def test_no_model_trains_once_enough_games():
    assert retrain.should_retrain(None, {"16.19": MIN - 1}) is None
    assert retrain.should_retrain(None, {"16.19": MIN}) == "aucun modèle"


def test_new_patch_needs_enough_games():
    meta = {"games": 6000, "patch": "16.19"}
    assert retrain.should_retrain(meta, {"16.19": 6000, "16.20": MIN - 1}) is None
    assert "16.20" in retrain.should_retrain(meta, {"16.19": 6000, "16.20": MIN})


def test_growth_needs_both_ratio_and_minimum():
    meta = {"games": 60_000, "patch": "16.19"}
    # +10 000 parties mais seulement +16 % : pas assez
    assert retrain.should_retrain(meta, {"16.19": 70_000}) is None
    assert retrain.should_retrain(meta, {"16.19": 72_000}) is not None
    # +50 % mais seulement 1 000 parties : sous le minimum
    assert retrain.should_retrain({"games": 2000, "patch": "16.19"}, {"16.19": 3000}) is None


def test_adopt_requires_brier_not_worse_and_calibration_ok():
    champion = {"brier": 0.16, "max_gap": 0.03}
    assert retrain.adopt(champion, {"brier": 0.15, "max_gap": 0.04})  # dans le seuil de 5 points
    assert not retrain.adopt(champion, {"brier": 0.17, "max_gap": 0.01})
    assert not retrain.adopt(champion, {"brier": 0.15, "max_gap": 0.09})


def _crawl(tmp_path, games=10):
    db = sqlite3.connect(tmp_path / "crawl.db")
    db.executescript(SCHEMA)
    raw = pack(GAME, TIMELINE)
    for i in range(games):
        db.execute(
            "INSERT INTO crawl_games (game_id, queue_id, game_version, game_creation_utc, depth, raw)"
            " VALUES (?, 420, '16.19.823.722', ?, 1, ?)",
            (i, f"2026-10-{i + 1:02d} 00:00:00", raw),
        )
    db.commit()
    db.close()
    return tmp_path / "crawl.db"


def test_retrain_skips_without_trigger_and_forces_on_demand(tmp_path):
    path, out = _crawl(tmp_path), tmp_path / "winprob_model.json"
    assert "aucun déclencheur" in retrain.retrain(path=path, out=out)
    assert not out.exists()
    line = retrain.retrain(force=True, path=path, out=out)
    assert "manuel" in line
    assert out.with_suffix(".log").read_text(encoding="utf-8").strip().endswith(line)


def test_adopted_model_keeps_meta_for_the_next_trigger(tmp_path):
    path, out = _crawl(tmp_path), tmp_path / "winprob_model.json"
    # Fixture sans erreur de prédiction (que des victoires bleues) : adopté sans champion.
    assert "ADOPTÉ" in retrain.retrain(force=True, path=path, out=out)
    meta = WinModel.from_json(out.read_text(encoding="utf-8")).meta
    assert meta["games"] == 10 and meta["patch"] == "16.19"


def test_challenger_is_dropped_when_champion_is_better(tmp_path):
    path, out = _crawl(tmp_path), tmp_path / "winprob_model.json"
    retrain.retrain(force=True, path=path, out=out)
    before = out.read_text(encoding="utf-8")
    champion = WinModel.from_json(before)
    champion.weights = [w * 3 for w in champion.weights]  # champion plus tranché : Brier ~ 0
    out.write_text(champion.to_json(), encoding="utf-8")
    kept = out.read_text(encoding="utf-8")
    line = retrain.retrain(force=True, path=path, out=out)
    assert ("jeté" in line) == (out.read_text(encoding="utf-8") == kept)
