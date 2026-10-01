"""Calibration appliquée par « o/n » : fichier d'override, garde-fou, bump de
MODEL_VERSION, et régression de suggest_scale (sous-convergence)."""

import json
import math
import random
from types import SimpleNamespace

import pytest

from src import calibration_overrides as overrides
from src.analysis.calibration import scale_interval, suggest_scale
from src.config_constants import AnalysisConfig, analysis_config
from src.draft import calibration_notice
from src.draft.commands import CommandListener


def _rows(n, slope, seed=1):
    """Prédictions dont le vrai pouvoir est `slope` fois celui annoncé."""
    rng = random.Random(seed)
    rows = []
    for _ in range(n):
        p = rng.uniform(0.3, 0.7)
        true_p = 1 / (1 + math.exp(-slope * math.log(p / (1 - p))))
        rows.append((p, int(rng.random() < true_p)))
    return rows


def _fill(db, rows, version="v1"):
    for p, outcome in rows:
        prediction_id = db.insert_prediction([1], [2], None, p, version)
        db.update_prediction_outcome(prediction_id, outcome)


class TestSuggestScaleConverges:
    def test_no_signal_gives_a_scale_near_zero_not_a_timid_shrink(self):
        """Régression (2026-10-01) : l'ancienne montée de gradient rendait 0,586
        sur 53 parties dont l'optimum était -0,10, car elle s'arrêtait à ~40 %
        du chemin quand les logits sont petits."""
        coin_flip = [(0.55, 1), (0.55, 0), (0.45, 1), (0.45, 0)] * 25
        assert suggest_scale(coin_flip) == pytest.approx(0.0, abs=0.05)

    def test_matches_a_known_slope(self):
        assert suggest_scale(_rows(4000, 0.5)) == pytest.approx(0.5, abs=0.15)


class TestOverrides:
    def test_roundtrip_applies_to_a_config(self, tmp_path):
        path = str(tmp_path / "calibration.json")
        assert overrides.save_overrides(0.7, 0.3, "spec13-v1+cal1", path)
        cfg = AnalysisConfig()

        overrides.apply_overrides(cfg, path)

        assert (cfg.K_MATCHUP, cfg.K_SYNERGY, cfg.MODEL_VERSION) == (0.7, 0.3, "spec13-v1+cal1")

    @pytest.mark.parametrize(
        "content",
        [
            "not json",
            json.dumps({"K_MATCHUP": 0.7, "K_SYNERGY": 0.3}),  # version seule manquante
            json.dumps({"K_MATCHUP": -1, "K_SYNERGY": 0.3, "MODEL_VERSION": "v"}),
            json.dumps({"K_MATCHUP": "x", "K_SYNERGY": 0.3, "MODEL_VERSION": "v"}),
            json.dumps({"K_MATCHUP": 0.7, "K_SYNERGY": 0.3, "MODEL_VERSION": " "}),
        ],
    )
    def test_invalid_file_changes_nothing(self, tmp_path, content):
        path = tmp_path / "calibration.json"
        path.write_text(content, encoding="utf-8")
        cfg = AnalysisConfig()

        assert overrides.apply_overrides(cfg, str(path)) == {}
        assert (cfg.K_MATCHUP, cfg.MODEL_VERSION) == (
            AnalysisConfig().K_MATCHUP,
            AnalysisConfig().MODEL_VERSION,
        )

    def test_missing_file_changes_nothing(self, tmp_path):
        assert overrides.load_overrides(str(tmp_path / "absent.json")) == {}

    def test_version_bump_increments_the_suffix(self):
        assert overrides.next_version("spec13-v1") == "spec13-v1+cal1"
        assert overrides.next_version("spec13-v1+cal1") == "spec13-v1+cal2"
        assert overrides.next_version("spec13-v1+cal9") == "spec13-v1+cal10"


class TestGuard:
    def test_too_few_games_gives_no_proposal(self, db):
        _fill(db, _rows(analysis_config.CALIBRATION_APPLY_MIN_ROWS - 1, 0.3))
        assert calibration_notice.build_proposal(db, "v1") is None

    def test_no_signal_gives_no_proposal(self, db):
        """Le cas réel du 2026-10-01 : l'IC du facteur touche 0."""
        _fill(db, [(0.55, 1), (0.55, 0), (0.45, 1), (0.45, 0)] * 40)
        assert calibration_notice.build_proposal(db, "v1") is None

    def test_well_calibrated_gives_no_proposal(self, db):
        _fill(db, _rows(400, 1.0))
        assert calibration_notice.build_proposal(db, "v1") is None

    def test_clearly_overconfident_model_gets_a_proposal_with_a_bumped_version(self, db):
        _fill(db, _rows(1500, 0.4))

        proposal = calibration_notice.build_proposal(db, "v1")

        assert proposal is not None
        assert proposal.model_version == "v1+cal1"
        assert 0 < proposal.scale < 1
        assert proposal.k_matchup == pytest.approx(analysis_config.K_MATCHUP * proposal.scale)

    def test_interval_brackets_the_estimate(self):
        rows = _rows(300, 0.5)
        low, high = scale_interval(rows, 0.9, 100)
        assert low < suggest_scale(rows) < high


class TestAnswer:
    @pytest.fixture
    def restore_config(self):
        saved = (
            analysis_config.K_MATCHUP,
            analysis_config.K_SYNERGY,
            analysis_config.MODEL_VERSION,
        )
        yield
        analysis_config.K_MATCHUP, analysis_config.K_SYNERGY, analysis_config.MODEL_VERSION = saved

    def _monitor(self):
        proposal = calibration_notice.Proposal(0.5, 0.3, 0.7, 0.5, 0.25, "spec13-v1+cal1")
        return SimpleNamespace(_pending_calibration=proposal, _command_queue=None), proposal

    def test_yes_writes_the_file_and_bumps_the_live_version(
        self, tmp_path, monkeypatch, restore_config
    ):
        path = str(tmp_path / "calibration.json")
        monkeypatch.setattr(overrides, "get_calibration_path", lambda: path)
        monitor, proposal = self._monitor()

        CommandListener(monitor).handle_calibration_answer(True)

        assert monitor._pending_calibration is None
        assert overrides.load_overrides(path)["MODEL_VERSION"] == "spec13-v1+cal1"
        assert analysis_config.MODEL_VERSION == "spec13-v1+cal1"
        assert analysis_config.K_MATCHUP == 0.5

    def test_no_changes_nothing(self, tmp_path, monkeypatch, restore_config):
        path = str(tmp_path / "calibration.json")
        monkeypatch.setattr(overrides, "get_calibration_path", lambda: path)
        monitor, _ = self._monitor()
        before = analysis_config.MODEL_VERSION

        CommandListener(monitor).handle_calibration_answer(False)

        assert monitor._pending_calibration is None
        assert analysis_config.MODEL_VERSION == before
        assert overrides.load_overrides(path) == {}


class TestTrackerAsksTheQuestion:
    def test_a_justified_proposal_is_printed_and_kept_pending(self, db, capsys):
        from src.draft.outcome_tracker import OutcomeTracker
        from tests.test_outcome_tracker import _fake_monitor

        _fill(db, _rows(1500, 0.4))
        monitor = _fake_monitor(db)

        OutcomeTracker(monitor)._maybe_notify_calibration(before_count=0, model_version="v1")

        assert monitor._pending_calibration.model_version == "v1+cal1"
        assert "Appliquer ? (o/n)" in capsys.readouterr().out
