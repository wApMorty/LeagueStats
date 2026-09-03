"""End-of-draft team score analysis and display.

Extracted from src/draft_monitor.py (SPEC-07 E10, lot 11) : déplacement
verbatim, aucun changement de comportement.

Back-reference to the monitor: touches assistant/verbose, calls back through
_get_display_name/_calculate_synergy_score/_final_score, and writes
_last_prediction_id (consumed by the "outcome win/loss" command).
"""

from typing import Dict, List, Optional

from ..config_constants import analysis_config, draft_config
from ..utils.console import clear_console


class FinalDraftAnalyzer:
    """Compute and print individual champion scores at the end of a draft."""

    def __init__(self, monitor) -> None:
        self.m = monitor

    def analyze(
        self,
        ally_picks: List[int],
        enemy_picks: List[int],
        ally_lanes: Optional[Dict[int, str]] = None,
    ) -> None:
        """Calculate individual scores for each champion at end of draft.

        Args:
            ally_lanes: championId -> inferred lane (state.inferred_roles),
                used only to log the prediction row (SPEC-05 B7 §8). None =
                no lane info stored with the prediction.
        """
        # Clear console before final analysis for clean display
        clear_console()

        print("\n" + "=" * 80)
        print("ANALYSE FINALE DU DRAFT - Scores individuels des champions")
        print("=" * 80)

        if not ally_picks or not enemy_picks:
            print("[INFO] Draft incomplet - aucune analyse finale disponible")
            return

        ally_names = [self.m._get_display_name(champ_id) for champ_id in ally_picks]
        enemy_names = [self.m._get_display_name(champ_id) for champ_id in enemy_picks]

        print(f"\n[TEAMS] COMPOSITION FINALE :")
        print(f"  Équipe alliée :  {' | '.join(ally_names)}")
        print(f"  Équipe ennemie : {' | '.join(enemy_names)}")

        print(f"\nANALYSE DE PERFORMANCE D'ÉQUIPE :")
        print("-" * 60)

        ally_scores = []
        enemy_scores = []

        # Calculate scores for ALLY team (without displaying yet)
        for i, champion_id in enumerate(ally_picks):
            champion_name = self.m._get_display_name(champion_id)

            try:
                # Get champion matchups (cached for performance) - uses 6-column format
                champion_matchups = self.m.assistant.get_matchups_for_draft(champion_name)

                if (
                    not champion_matchups
                    or sum(m.games for m in champion_matchups) < draft_config.MIN_CHAMPION_GAMES
                ):  # m.games = games in 6-column format
                    if self.m.verbose:
                        total_games = (
                            sum(m.games for m in champion_matchups) if champion_matchups else 0
                        )
                        print(
                            f"[DEBUG] {champion_name}: Insufficient data (games={total_games}, "
                            f"need >={draft_config.MIN_CHAMPION_GAMES})"
                        )
                    ally_scores.append(
                        (champion_name, None, 0, 0.0)
                    )  # (name, matchup_score, synergy_score, total)
                    continue

                # Use the new normalized scoring system
                enemy_names = [self.m._get_display_name(enemy_id) for enemy_id in enemy_picks]

                # Calculate matchup score against enemies
                matchup_score = self.m.assistant.score_against_team(
                    champion_matchups, enemy_names, champion_name
                )

                # Calculate synergy score with other allies (excluding self)
                other_allies = [aid for aid in ally_picks if aid != champion_id]
                synergy_score = self.m._calculate_synergy_score(champion_name, other_allies)

                # Total score = configurable blend of matchup and synergy (see _final_score)
                total_score = self.m._final_score(matchup_score, synergy_score)

                ally_scores.append((champion_name, matchup_score, synergy_score, total_score))

            except Exception as e:
                ally_scores.append((champion_name, None, 0.0, 0.0))  # Mark error

        # Calculate scores for ENEMY team (without displaying yet)
        for i, champion_id in enumerate(enemy_picks):
            champion_name = self.m._get_display_name(champion_id)

            try:
                # Get champion matchups (cached for performance) - uses 6-column format
                champion_matchups = self.m.assistant.get_matchups_for_draft(champion_name)

                if (
                    not champion_matchups
                    or sum(m.games for m in champion_matchups) < draft_config.MIN_CHAMPION_GAMES
                ):  # m.games = games in 6-column format
                    if self.m.verbose:
                        total_games = (
                            sum(m.games for m in champion_matchups) if champion_matchups else 0
                        )
                        print(
                            f"[DEBUG] {champion_name}: Insufficient data (games={total_games}, "
                            f"need >={draft_config.MIN_CHAMPION_GAMES})"
                        )
                    enemy_scores.append((champion_name, None, 0.0, 0.0))  # Mark insufficient data
                    continue

                # Use the new normalized scoring system
                ally_names = [self.m._get_display_name(ally_id) for ally_id in ally_picks]

                # Calculate matchup score against our team
                matchup_score = self.m.assistant.score_against_team(
                    champion_matchups, ally_names, champion_name
                )

                # Calculate synergy score with other enemies (excluding self)
                other_enemies = [eid for eid in enemy_picks if eid != champion_id]
                synergy_score = self.m._calculate_synergy_score(champion_name, other_enemies)

                # Total score = configurable blend of matchup and synergy (see _final_score)
                total_score = self.m._final_score(matchup_score, synergy_score)

                enemy_scores.append((champion_name, matchup_score, synergy_score, total_score))

            except Exception as e:
                enemy_scores.append((champion_name, None, 0.0, 0.0))  # Mark error

        # Sort both teams by total score (descending - best scores first)
        ally_scores.sort(
            key=lambda x: x[3] if x[1] is not None else -999, reverse=True
        )  # Sort by total_score
        enemy_scores.sort(key=lambda x: x[3] if x[1] is not None else -999, reverse=True)

        # Helper function to get an ASCII strength marker for a score
        def get_emoji(score):
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

        # Display ALLY team performance (sorted)
        print(f"\nVOTRE ÉQUIPE :")
        print(f"  {'Champion':<15} | Matchup | Synergy | Total")
        print(f"  {'-'*15}-+---------+---------+-------")
        for champion_name, matchup_score, synergy_score, total_score in ally_scores:
            if matchup_score is None:
                print(f"  {champion_name:<15} | Données insuffisantes")
            else:
                matchup_emoji = get_emoji(matchup_score)
                synergy_emoji = get_emoji(synergy_score)
                total_emoji = get_emoji(total_score)
                print(
                    f"  {champion_name:<15} | {matchup_emoji} {matchup_score:+5.1f} | "
                    f"{synergy_emoji} {synergy_score:+5.1f} | {total_emoji} {total_score:+5.1f}"
                )

        # Display ENEMY team performance (sorted)
        print(f"\nÉQUIPE ENNEMIE :")
        print(f"  {'Champion':<15} | Matchup | Synergy | Total")
        print(f"  {'-'*15}-+---------+---------+-------")
        for champion_name, matchup_score, synergy_score, total_score in enemy_scores:
            if matchup_score is None:
                print(f"  {champion_name:<15} | Données insuffisantes")
            else:
                matchup_emoji = get_emoji(matchup_score)
                synergy_emoji = get_emoji(synergy_score)
                total_emoji = get_emoji(total_score)
                print(
                    f"  {champion_name:<15} | {matchup_emoji} {matchup_score:+5.1f} | "
                    f"{synergy_emoji} {synergy_score:+5.1f} | {total_emoji} {total_score:+5.1f}"
                )

        # Team summary comparison
        print(f"\nCOMPARAISON DU DRAFT :")
        print("-" * 40)

        # Calculate team winrates using total scores (matchup + synergy)
        ally_valid_scores = [
            score[3] for score in ally_scores if score[1] is not None
        ]  # index 3 = total_score
        enemy_valid_scores = [score[3] for score in enemy_scores if score[1] is not None]

        if ally_valid_scores:
            # Convert total advantages to individual winrates
            ally_winrates = [50.0 + advantage for advantage in ally_valid_scores]
            # Use geometric mean for team strength calculation
            ally_team_stats = self.m.assistant._calculate_team_winrate(ally_winrates)
            ally_team_winrate = ally_team_stats["team_winrate"]
            ally_total = sum(ally_valid_scores)  # For display purposes
            print(
                f"  Votre équipe : {ally_total:+.2f}% d'avantage total → {ally_team_winrate:.2f}% de winrate d'équipe"
            )
        else:
            ally_team_winrate = 50.0
            ally_total = 0
            print(f"  Votre équipe : Aucune donnée valide")

        if enemy_valid_scores:
            # Convert advantages to individual winrates
            enemy_winrates = [50.0 + advantage for advantage in enemy_valid_scores]
            # Use geometric mean for team strength calculation
            enemy_team_stats = self.m.assistant._calculate_team_winrate(enemy_winrates)
            enemy_team_winrate = enemy_team_stats["team_winrate"]
            enemy_total = sum(enemy_valid_scores)  # For display purposes
            print(
                f"  Équipe ennemie : {enemy_total:+.2f}% d'avantage total → {enemy_team_winrate:.2f}% de winrate d'équipe"
            )
        else:
            enemy_team_winrate = 50.0
            enemy_total = 0
            print(f"  Équipe ennemie : Aucune donnée valide")

        # Normalize team winrates to ensure they sum to 100%
        if ally_team_winrate != 50.0 or enemy_team_winrate != 50.0:
            total_winrate = ally_team_winrate + enemy_team_winrate
            our_expected = (ally_team_winrate / total_winrate) * 100.0
            their_expected = (enemy_team_winrate / total_winrate) * 100.0

            print(f"\n  Matchup attendu (normalisé) : {our_expected:.2f}% vs {their_expected:.2f}%")

            # Overall assessment based on normalized winrates
            draft_diff = our_expected - their_expected
        else:
            # No valid data - neutral matchup
            our_expected = 50.0
            their_expected = 50.0
            draft_diff = 0.0

        # SPEC-05 B7 §8: best-effort prediction logging for later calibration
        # (scripts/calibrate_model.py). Never blocks nor slows down the draft.
        try:
            self.m._last_prediction_id = self.m.assistant.db.insert_prediction(
                ally_champions=ally_picks,
                enemy_champions=enemy_picks,
                ally_lanes=ally_lanes,
                predicted_probability=our_expected / 100.0,
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
