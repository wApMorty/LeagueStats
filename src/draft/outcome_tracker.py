"""Rapprochement prédictions <-> parties réellement jouées (SPEC-08).

Toute la logique d'appariement vit ici (pas dans lifecycle.py ni commands.py,
voir SPEC-08 §2.4) : c'est un concern substantiel avec sa propre suite de
tests (tests/test_outcome_tracker.py), pendant que lcu_client.py/
lcu_match_history.py ne font que lire et normaliser les payloads LCU.

Règle d'appariement, en deux passes :
  1. Filtre temporel (`_temporal_candidates`) sur `get_recent_matches` seul :
     la partie doit démarrer après la fin de la draft, dans une fenêtre de
     `OUTCOME_MATCH_WINDOW_HOURS`.
  2. Confirmation par composition (`_composition_confirms`), qui coûte un
     appel `get_match_participants` par partie candidate : au moins
     `OUTCOME_MIN_ALLY_OVERLAP` champions communs des deux côtés (alliés ET
     ennemis).

Les candidats retenus par la passe 1 sont ensuite traités du plus proche au
plus lointain dans le temps : ce tri unique règle les deux sens d'ambiguïté
de la spec en une seule passe -- une prédiction avec plusieurs parties
candidates prend la plus proche, et une partie candidate pour plusieurs
prédictions revient à la prédiction la plus proche, l'autre restant en
attente (une donnée fausse est pire qu'une donnée absente).
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from ..config_constants import analysis_config, draft_config


class OutcomeTracker:
    """Rapproche les prédictions en attente des parties réellement jouées."""

    def __init__(self, monitor) -> None:
        self.m = monitor

    def resolve_pending(self, limit: Optional[int] = None) -> int:
        """Labellise les prédictions sans outcome depuis l'historique LCU.

        Args:
            limit: nombre max de prédictions en attente examinées. None
                retombe sur draft_config.OUTCOME_BACKFILL_LIMIT.

        Returns:
            Le nombre de prédictions résolues lors de cet appel.

        Best-effort : ne lève jamais. Un LCU indisponible, une réponse
        inattendue ou une erreur base ne doivent jamais interrompre la
        boucle de monitoring ni bloquer le démarrage du Draft Coach.
        """
        try:
            return self._resolve_pending(limit)
        except Exception as e:  # pragma: no cover - filet de sécurité ultime
            if getattr(self.m, "verbose", False):
                print(f"[WARNING] Échec de la résolution des résultats de partie: {e}")
            return 0

    def _resolve_pending(self, limit: Optional[int]) -> int:
        effective_limit = limit if limit is not None else draft_config.OUTCOME_BACKFILL_LIMIT
        pending = self.m.assistant.db.get_pending_predictions(effective_limit)
        if not pending:
            return 0

        matches = self.m.lcu.get_recent_matches(draft_config.OUTCOME_HISTORY_DEPTH)
        if not matches:
            return 0

        pairs = self._temporal_candidates(pending, matches)
        if not pairs:
            return 0

        # Le plus proche dans le temps d'abord : règle les deux sens
        # d'ambiguïté de la spec (§2.4) avec un seul tri.
        pairs.sort(key=lambda pair: pair[2])

        participants_cache: Dict[int, Dict[int, List[int]]] = {}
        used_prediction_ids: Set[int] = set()
        used_game_ids: Set[int] = set()
        resolved_count = 0

        for prediction, match, _diff_seconds in pairs:
            if prediction["id"] in used_prediction_ids or match["game_id"] in used_game_ids:
                continue

            game_id = match["game_id"]
            if game_id not in participants_cache:
                # Économie d'appels (§2.4) : uniquement pour les candidates
                # retenues par la passe temporelle, une fois par partie.
                participants_cache[game_id] = self.m.lcu.get_match_participants(game_id)
            participants = participants_cache[game_id]

            if not self._composition_confirms(prediction, match, participants):
                continue

            outcome = 1 if match["win"] else 0
            updated = self.m.assistant.db.update_prediction_outcome(
                prediction["id"], outcome, game_id=game_id
            )
            if not updated:
                # Conflit d'unicité sur game_id (filet de sécurité DB) ou
                # échec d'écriture : abstention, pas de nouvelle tentative.
                continue

            used_prediction_ids.add(prediction["id"])
            used_game_ids.add(game_id)
            resolved_count += 1
            self._print_resolution(prediction, match, outcome)

        if resolved_count:
            self._print_summary(resolved_count)
        return resolved_count

    def _temporal_candidates(
        self, pending: List[Dict[str, Any]], matches: List[Dict[str, Any]]
    ) -> List[Tuple[Dict[str, Any], Dict[str, Any], float]]:
        """Passe 1 (SPEC-08 §2.4) : (prediction, match, écart en secondes)
        pour chaque paire où la partie démarre après la prédiction, dans la
        fenêtre OUTCOME_MATCH_WINDOW_HOURS."""
        window_seconds = draft_config.OUTCOME_MATCH_WINDOW_HOURS * 3600
        pairs: List[Tuple[Dict[str, Any], Dict[str, Any], float]] = []
        for prediction in pending:
            created_at = self._parse_created_utc(prediction.get("created_utc"))
            if created_at is None:
                continue
            for match in matches:
                game_creation_ms = match.get("game_creation_ms")
                if game_creation_ms is None:
                    continue
                game_at = datetime.fromtimestamp(game_creation_ms / 1000, tz=timezone.utc)
                delta_seconds = (game_at - created_at).total_seconds()
                if 0 < delta_seconds < window_seconds:
                    pairs.append((prediction, match, delta_seconds))
        return pairs

    @staticmethod
    def _parse_created_utc(created_utc: Optional[str]) -> Optional[datetime]:
        """`created_utc` est écrit par `datetime('now')` de SQLite : naïf,
        UTC, format 'YYYY-MM-DD HH:MM:SS'. Ne jamais comparer un naïf à un
        aware -- cette méthode attache explicitement UTC."""
        if not created_utc:
            return None
        try:
            return datetime.strptime(created_utc, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _composition_confirms(
        prediction: Dict[str, Any],
        match: Dict[str, Any],
        participants: Dict[int, List[int]],
    ) -> bool:
        """Passe 2 (SPEC-08 §2.4) : au moins OUTCOME_MIN_ALLY_OVERLAP
        champions communs des deux côtés (alliés ET ennemis). Abstention
        (False) si le détail de la partie est indisponible."""
        if not participants:
            return False

        player_team_id = match.get("team_id")
        if player_team_id not in participants:
            return False
        enemy_team_id = next(
            (team_id for team_id in participants if team_id != player_team_id), None
        )
        if enemy_team_id is None:
            return False

        ally_roster = set(participants.get(player_team_id, []))
        enemy_roster = set(participants.get(enemy_team_id, []))
        threshold = draft_config.OUTCOME_MIN_ALLY_OVERLAP

        ally_overlap = len(set(prediction["ally_champions"]) & ally_roster)
        enemy_overlap = len(set(prediction["enemy_champions"]) & enemy_roster)
        return ally_overlap >= threshold and enemy_overlap >= threshold

    @staticmethod
    def _print_resolution(prediction: Dict[str, Any], match: Dict[str, Any], outcome: int) -> None:
        result = "victoire" if outcome == 1 else "défaite"
        probability_pct = f"{prediction['predicted_probability'] * 100:.1f}".replace(".", ",")
        print(
            f"[OUTCOME] Partie {match['game_id']} -> {result} "
            f"— prédiction #{prediction['id']} (prévue {probability_pct} %) labellisée"
        )

    def _print_summary(self, resolved_count: int) -> None:
        total_labelled = self.m.assistant.db.count_labelled_predictions()
        print(
            f"[OUTCOME] {resolved_count} prédiction(s) en attente rattrapée(s) "
            f"· {total_labelled} labellisées au total "
            f"({analysis_config.MIN_ROWS_FOR_CALIBRATION} requises pour calibrer)"
        )
