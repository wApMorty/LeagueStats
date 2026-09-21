"""End-of-draft team score analysis and display.

SPEC-12 : les scores viennent désormais de ``src/analysis/game_eval.py``, le
même évaluateur que la recherche du Live Coach. Deux conséquences visibles :

- la probabilité affichée est celle du modèle, pas le rapport
  ``allié / (allié + ennemi)`` qui servait auparavant de normalisation ;
- un matchup n'est plus compté deux fois (une fois par camp), l'antisymétrie
  du modèle s'en charge.

La prédiction enregistrée pour la calibration (SPEC-05 B7 §8) est donc celle
du modèle réellement utilisé pour recommander — sans quoi on calibrerait un
modèle qu'on n'utilise plus.

Back-reference to the monitor: touches assistant/evaluator/verbose, calls back
through _get_display_name, and writes _last_prediction_id (consumed by the
"outcome win/loss" command).
"""

from typing import Dict, List, Optional, Sequence, Tuple

from ..analysis.game_eval import Placed
from ..analysis.probability import sigmoid
from ..config_constants import analysis_config, draft_config
from ..utils.console import clear_console

# (nom, matchup, synergie, total) — matchup/total à None quand les données du
# champion sont trop minces pour être affichées.
ScoreRow = Tuple[str, Optional[float], float, float]


def _to_points(logit: float) -> float:
    """Log-odds -> points de winrate, saturants.

    Même échelle que l'ancien affichage par delta (``sigmoid(x) - 0.5`` vaut
    ``x/4`` près de 0), pour que les seuils de lecture du joueur — et les
    marqueurs [++]/[+]/[~] — gardent leur sens.
    """
    return (sigmoid(logit) - 0.5) * 100.0


class FinalDraftAnalyzer:
    """Compute and print individual champion scores at the end of a draft."""

    def __init__(self, monitor) -> None:
        self.m = monitor

    # ---------- calcul ----------

    def _has_enough_data(self, champion_name: str, lane: Optional[str]) -> bool:
        """SPEC-06 E7 : sous ce volume, le champion est affiché « données
        insuffisantes » plutôt que noté comme un matchup neutre."""
        matchups = self.m.assistant.get_matchups_for_draft(champion_name, lane=lane)
        total_games = sum(m.games for m in matchups) if matchups else 0
        if total_games < draft_config.MIN_CHAMPION_GAMES:
            if self.m.verbose:
                print(
                    f"[DEBUG] {champion_name}: Insufficient data (games={total_games}, "
                    f"need >={draft_config.MIN_CHAMPION_GAMES})"
                )
            return False
        return True

    def _score_team(self, team: Sequence[Placed], opposing: Sequence[Placed]) -> List[ScoreRow]:
        """Une ligne de tableau par champion.

        La colonne « Synergy » compte les paires du point de vue DE CE
        CHAMPION : la somme de la colonne compte donc chaque paire deux fois et
        ne vaut pas le total d'équipe, qui est calculé à part par
        ``team_logit()``. C'est voulu — la colonne répond à « qu'apporte ce
        champion », pas à « comment se décompose le total ».
        """
        rows: List[ScoreRow] = []
        for index, champion in enumerate(team):
            name, lane = champion
            try:
                if not self._has_enough_data(name, lane):
                    rows.append((name, None, 0.0, 0.0))
                    continue

                others = [mate for position, mate in enumerate(team) if position != index]
                matchup = sum(self.m.evaluator.matchup_logit(champion, enemy) for enemy in opposing)
                synergy = sum(self.m.evaluator.synergy_logit(champion, mate) for mate in others)
                rows.append(
                    (name, _to_points(matchup), _to_points(synergy), _to_points(matchup + synergy))
                )
            except Exception:
                rows.append((name, None, 0.0, 0.0))  # Mark error

        rows.sort(key=lambda row: row[3] if row[1] is not None else -999, reverse=True)
        return rows

    # ---------- affichage ----------

    @staticmethod
    def _marker(score: float) -> str:
        """ASCII strength marker for a score."""
        if score >= 2.0:
            return "[++]"
        elif score >= 1.0:
            return "[+]"
        elif score >= -1.0:
            return "[~]"
        elif score >= -2.0:
            return "[-]"
        else:
            return "[--]"

    def _print_table(self, title: str, rows: Sequence[ScoreRow]) -> None:
        print(f"\n{title}")
        print(f"  {'Champion':<15} | Matchup | Synergy | Total")
        print(f"  {'-'*15}-+---------+---------+-------")
        for champion_name, matchup_score, synergy_score, total_score in rows:
            if matchup_score is None:
                print(f"  {champion_name:<15} | Données insuffisantes")
            else:
                print(
                    f"  {champion_name:<15} | {self._marker(matchup_score)} {matchup_score:+5.1f} | "
                    f"{self._marker(synergy_score)} {synergy_score:+5.1f} | "
                    f"{self._marker(total_score)} {total_score:+5.1f}"
                )

    # ---------- entrée principale ----------

    def analyze(
        self,
        ally_picks: List[int],
        enemy_picks: List[int],
        ally_lanes: Optional[Dict[int, str]] = None,
    ) -> None:
        """Calculate individual scores for each champion at end of draft.

        Args:
            ally_lanes: championId -> inferred lane (state.inferred_roles),
                for both teams despite the name (SPEC-04 §4.3 merges ally and
                enemy assignments into a single dict). Used both to log the
                prediction row (SPEC-05 B7 §8) and, par champion, à pondérer
                ses paires selon la proximité de lane. None = aucune info de
                lane, pondération uniforme.
        """
        role_map = ally_lanes or {}
        # Clear console before final analysis for clean display
        clear_console()

        print("\n" + "=" * 80)
        print("ANALYSE FINALE DU DRAFT - Scores individuels des champions")
        print("=" * 80)

        if not ally_picks or not enemy_picks:
            print("[INFO] Draft incomplet - aucune analyse finale disponible")
            return

        allies: List[Placed] = [
            (self.m._get_display_name(champ_id), role_map.get(champ_id)) for champ_id in ally_picks
        ]
        enemies: List[Placed] = [
            (self.m._get_display_name(champ_id), role_map.get(champ_id)) for champ_id in enemy_picks
        ]

        print(f"\n[TEAMS] COMPOSITION FINALE :")
        print(f"  Équipe alliée :  {' | '.join(name for name, _ in allies)}")
        print(f"  Équipe ennemie : {' | '.join(name for name, _ in enemies)}")

        print(f"\nANALYSE DE PERFORMANCE D'ÉQUIPE :")
        print("-" * 60)

        self._print_table("VOTRE ÉQUIPE :", self._score_team(allies, enemies))
        self._print_table("ÉQUIPE ENNEMIE :", self._score_team(enemies, allies))

        # Team summary comparison
        print(f"\nCOMPARAISON DU DRAFT :")
        print("-" * 40)

        win_probability = self.m.evaluator.win_probability(allies, enemies)
        our_expected = win_probability * 100.0
        print(f"  Probabilité de victoire estimée : {our_expected:.2f}%")
        print(f"  Probabilité adverse : {100.0 - our_expected:.2f}%")

        # Même définition qu'avant SPEC-12 (écart entre les deux camps), pour
        # que les seuils d'évaluation ci-dessous gardent leur calibrage.
        draft_diff = (2.0 * win_probability - 1.0) * 100.0

        # SPEC-05 B7 §8: best-effort prediction logging for later calibration
        # (scripts/calibrate_model.py). Never blocks nor slows down the draft.
        try:
            self.m._last_prediction_id = self.m.assistant.db.insert_prediction(
                ally_champions=ally_picks,
                enemy_champions=enemy_picks,
                ally_lanes=ally_lanes,
                predicted_probability=win_probability,
                # SPEC-12 : le suffixe « +lane-restante » d'effective_model_version()
                # décrivait un régime du modèle par delta, que la recherche
                # n'emprunte plus. MODEL_VERSION seul, comme outcome_tracker.py
                # l'utilisait déjà de son côté.
                model_version=analysis_config.MODEL_VERSION,
            )
        except Exception as e:
            print(f"[WARNING] Échec de l'enregistrement de la prédiction: {e}")

        if draft_diff >= 5.0:
            print(f"  Évaluation : Avantage de draft majeur ({draft_diff:+.2f}% d'écart total)")
        elif draft_diff >= 2.5:
            print(f"  Évaluation : Bon avantage de draft ({draft_diff:+.2f}% d'écart total)")
        elif draft_diff >= -2.5:
            print(f"  Évaluation : Draft équilibré ({draft_diff:+.2f}% de différence)")
        elif draft_diff >= -5.0:
            print(f"  Évaluation : Désavantage de draft ({draft_diff:.2f}% de retard)")
        else:
            print(f"  Évaluation : Désavantage de draft majeur ({draft_diff:.2f}% de retard)")

        print("\n" + "=" * 80)
