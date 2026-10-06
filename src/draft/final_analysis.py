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

from dataclasses import asdict, dataclass, field
from itertools import zip_longest
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..analysis.game_eval import Placed
from ..analysis.probability import sigmoid
from ..coaching.goals import draft_reminder
from ..config_constants import analysis_config, draft_config, scraping_config
from ..utils.console import clear_console

TOPIC = "game"  # sujet du bus : l'analyse de la draft qui vient de finir (SPEC-24 tâche 106)

# Une ligne du tableau face-à-face : (allié, ennemi) sous forme d'indices dans
# leur équipe, None pour un côté vide, et True si les deux se font face dans
# la même lane (sinon aucun duel n'est affiché).
FaceOff = Tuple[Optional[int], Optional[int], bool]

NAME_WIDTH = 14
STATS_WIDTH = 17  # trois colonnes « +5.1f » séparées par un espace
DUEL_WIDTH = 12
# « Données insuffisantes » (SPEC-06 E7) ne tient pas dans STATS_WIDTH.
INSUFFICIENT = "peu de données"


@dataclass
class ScoreLine:
    """Un champion du tableau ; ``matchup`` à None quand ses données sont trop minces."""

    name: str
    matchup: Optional[float]
    synergy: float
    total: float


@dataclass
class FaceOffLine:
    """Une ligne du face-à-face : un côté peut être vide, ``duel`` est None s'il n'est pas mesuré."""

    ally: Optional[ScoreLine]
    enemy: Optional[ScoreLine]
    duel: Optional[float]


@dataclass
class FinalAnalysis:
    """L'analyse de fin de draft, en données : la console l'imprime, l'écran « En partie » la relit."""

    lines: List[FaceOffLine]
    win_probability: float
    draft_diff: float  # écart entre les deux camps, en points
    evaluation: str
    loadout: Optional[Dict[str, Any]] = field(default=None)

    def to_payload(self) -> Dict[str, Any]:
        """Charge utile du bus (types simples, sérialisable en JSON)."""
        return asdict(self)


def _to_points(logit: float) -> float:
    """Log-odds -> points de winrate, saturants.

    Même échelle que l'ancien affichage par delta (``sigmoid(x) - 0.5`` vaut
    ``x/4`` près de 0), pour que les seuils de lecture du joueur — et les
    paliers des chevrons de DUEL — gardent leur sens.
    """
    return (sigmoid(logit) - 0.5) * 100.0


def duel_cell(points: Optional[float]) -> str:
    """Flèche vers le gagnant du duel direct, suivie de sa valeur (SPEC-14 §2.2).

    ``<`` = avantage allié, ``>`` = avantage ennemi, un chevron par palier
    franchi ; ``=`` sous le premier palier ; ``?`` sans valeur quand rien n'est
    mesuré.
    """
    if points is None:
        return "?"
    level = sum(abs(points) >= step for step in draft_config.DUEL_ARROW_THRESHOLDS)
    arrow = ("<" if points > 0 else ">") * level if level else "="
    return f"{arrow:<3} {points:+5.1f}"


def face_offs(allies: Sequence[Placed], enemies: Sequence[Placed]) -> List[FaceOff]:
    """Apparie les deux équipes lane par lane, dans l'ordre de ``LANES``.

    Un champion sans lane, ou qui partage sa lane avec un coéquipier, n'est
    apparié à personne : il va en fin de tableau (SPEC-14 §2.1). Mieux vaut un
    appariement absent qu'un appariement faux.
    """

    def by_lane(team: Sequence[Placed]) -> Dict[str, int]:
        lanes = [lane for _, lane in team]
        return {
            lane: index
            for index, lane in enumerate(lanes)
            if lane in scraping_config.LANES and lanes.count(lane) == 1
        }

    ally_lanes, enemy_lanes = by_lane(allies), by_lane(enemies)
    rows: List[FaceOff] = []
    for lane in scraping_config.LANES:
        ally, enemy = ally_lanes.get(lane), enemy_lanes.get(lane)
        if ally is not None or enemy is not None:
            rows.append((ally, enemy, ally is not None and enemy is not None))

    lone_allies = [i for i in range(len(allies)) if i not in ally_lanes.values()]
    lone_enemies = [i for i in range(len(enemies)) if i not in enemy_lanes.values()]
    rows.extend((ally, enemy, False) for ally, enemy in zip_longest(lone_allies, lone_enemies))
    return rows


def _stats(row: Optional[ScoreLine], mirrored: bool) -> str:
    """Mat Syn Tot (Tot Syn Mat côté ennemi, en miroir) sur STATS_WIDTH."""
    if row is None:
        return ""
    if row.matchup is None:
        return INSUFFICIENT
    values = (
        (row.total, row.synergy, row.matchup) if mirrored else (row.matchup, row.synergy, row.total)
    )
    return " ".join(f"{value:+5.1f}" for value in values)


def evaluation_of(draft_diff: float) -> Tuple[str, str]:
    """Libellé de l'évaluation et sa ligne console, d'après l'écart de draft en points."""
    if draft_diff >= 5.0:
        label, detail = "Avantage de draft majeur", f"{draft_diff:+.2f}% d'écart total"
    elif draft_diff >= 2.5:
        label, detail = "Bon avantage de draft", f"{draft_diff:+.2f}% d'écart total"
    elif draft_diff >= -2.5:
        label, detail = "Draft équilibré", f"{draft_diff:+.2f}% de différence"
    elif draft_diff >= -5.0:
        label, detail = "Désavantage de draft", f"{draft_diff:.2f}% de retard"
    else:
        label, detail = "Désavantage de draft majeur", f"{draft_diff:.2f}% de retard"
    return label, f"{label} ({detail})"


def _line(ally_stats: str, ally: str, duel: str, enemy: str, enemy_stats: str) -> str:
    """Une ligne du tableau miroir, 80 colonnes au plus (SPEC-14 §2)."""
    return (
        f"{ally_stats:>{STATS_WIDTH}}  {ally[:NAME_WIDTH]:<{NAME_WIDTH}} "
        f"{duel:^{DUEL_WIDTH}} {enemy[:NAME_WIDTH]:<{NAME_WIDTH}}  "
        f"{enemy_stats:<{STATS_WIDTH}}"
    ).rstrip()


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

    def _score_team(self, team: Sequence[Placed], opposing: Sequence[Placed]) -> List[ScoreLine]:
        """Une ligne de tableau par champion, dans l'ordre de ``team``.

        La colonne « Synergy » compte les paires du point de vue DE CE
        CHAMPION : la somme de la colonne compte donc chaque paire deux fois et
        ne vaut pas le total d'équipe, qui est calculé à part par
        ``team_logit()``. C'est voulu — la colonne répond à « qu'apporte ce
        champion », pas à « comment se décompose le total ».
        """
        rows: List[ScoreLine] = []
        for index, champion in enumerate(team):
            name, lane = champion
            try:
                if not self._has_enough_data(name, lane):
                    rows.append(ScoreLine(name, None, 0.0, 0.0))
                    continue

                others = [mate for position, mate in enumerate(team) if position != index]
                matchup = sum(self.m.evaluator.matchup_logit(champion, enemy) for enemy in opposing)
                synergy = sum(self.m.evaluator.synergy_logit(champion, mate) for mate in others)
                rows.append(
                    ScoreLine(
                        name,
                        _to_points(matchup),
                        _to_points(synergy),
                        _to_points(matchup + synergy),
                    )
                )
            except Exception:
                rows.append(ScoreLine(name, None, 0.0, 0.0))  # Mark error

        return rows

    # ---------- affichage ----------

    def _duel(self, ally: Placed, enemy: Placed) -> Optional[float]:
        """Matchup direct en points, None s'il n'est pas mesuré."""
        try:
            if not self.m.evaluator.has_matchup_data(ally, enemy):
                return None
            return _to_points(self.m.evaluator.matchup_logit(ally, enemy))
        except Exception:
            return None

    def _face_off_lines(
        self, allies: Sequence[Placed], enemies: Sequence[Placed]
    ) -> List[FaceOffLine]:
        """Les lignes du tableau miroir, une par lane, dans l'ordre de ``face_offs`` (SPEC-14)."""
        ally_rows = self._score_team(allies, enemies)
        enemy_rows = self._score_team(enemies, allies)
        return [
            FaceOffLine(
                ally_rows[ally] if ally is not None else None,
                enemy_rows[enemy] if enemy is not None else None,
                self._duel(allies[ally], enemies[enemy]) if paired else None,
            )
            for ally, enemy, paired in face_offs(allies, enemies)
        ]

    @staticmethod
    def _print_face_off(lines: Sequence[FaceOffLine]) -> None:
        """Tableau miroir, une ligne par lane (SPEC-14)."""
        print("\nFACE-À-FACE PAR LANE :\n")
        print(_line("  Mat   Syn   Tot", "Allié", "DUEL", "Ennemi", "  Tot   Syn   Mat"))
        dashes = " ".join(["-" * 5] * 3)
        print(_line(dashes, "-" * NAME_WIDTH, "-" * DUEL_WIDTH, "-" * NAME_WIDTH, dashes))
        for line in lines:
            print(
                _line(
                    _stats(line.ally, mirrored=False),
                    line.ally.name if line.ally else "",
                    duel_cell(line.duel),
                    line.enemy.name if line.enemy else "",
                    _stats(line.enemy, mirrored=True),
                )
            )
        print("\n  DUEL : matchup direct en points de winrate, + = avantage pour vous")
        print("  ?    : pas de donnée sur ce duel, ou lane incertaine")

    # ---------- entrée principale ----------

    def _publish(self, analysis: FinalAnalysis) -> None:
        """Sur le bus du client (sujet ``game``), jusqu'à la draft suivante ; best-effort."""
        try:
            bus = getattr(self.m, "bus", None)
            if bus is not None:
                bus.publish(TOPIC, analysis.to_payload())
        except Exception:  # pylint: disable=broad-exception-caught
            pass

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

        analysis = build_final_analysis(self.m, ally_picks, enemy_picks, role_map)
        self._print_face_off(analysis.lines)
        self._publish(analysis)

        # Team summary comparison
        print("\nCOMPARAISON DU DRAFT :")
        print("-" * 40)

        win_probability = analysis.win_probability
        our_expected = win_probability * 100.0
        print(f"  Probabilité de victoire estimée : {our_expected:.2f}%")
        print(f"  Probabilité adverse : {100.0 - our_expected:.2f}%")

        # SPEC-05 B7 §8: best-effort prediction logging for later calibration
        # (scripts/calibrate_model.py). Never blocks nor slows down the draft.
        try:
            self.m._last_prediction_id = self.m.assistant.db.insert_prediction(
                ally_champions=ally_picks,
                enemy_champions=enemy_picks,
                ally_lanes=ally_lanes,
                predicted_probability=win_probability,
                # SPEC-12 : le suffixe « +lane-restante » (SPEC-11, supprimé depuis)
                # décrivait un régime du modèle par delta, que la recherche
                # n'emprunte plus. MODEL_VERSION seul, comme outcome_tracker.py
                # l'utilisait déjà de son côté.
                model_version=analysis_config.MODEL_VERSION,
            )
        except Exception as e:
            print(f"[WARNING] Échec de l'enregistrement de la prédiction: {e}")

        print(f"  Évaluation : {evaluation_of(analysis.draft_diff)[1]}")

        # SPEC-19 §7.3 : rappel des axes de travail du coach de gameplay.
        try:
            reminders = draft_reminder(self.m.assistant.db)
        except Exception as e:
            reminders = []
            if self.m.verbose:
                print(f"[WARNING] Axes de travail illisibles : {e}")
        if reminders:
            print()
            for line in reminders:
                print(line)

        print("\n" + "=" * 80)


def build_final_analysis(
    monitor, ally_picks: List[int], enemy_picks: List[int], ally_lanes: Dict[int, str]
) -> FinalAnalysis:
    """Calcule l'analyse de fin de draft, sans rien imprimer ni publier (SPEC-24 tâche 106).

    ``ally_lanes`` : championId -> lane inférée, pour les deux camps (``state.inferred_roles``).
    """
    allies: List[Placed] = [
        (monitor._get_display_name(champ_id), ally_lanes.get(champ_id)) for champ_id in ally_picks
    ]
    enemies: List[Placed] = [
        (monitor._get_display_name(champ_id), ally_lanes.get(champ_id)) for champ_id in enemy_picks
    ]
    win_probability = monitor.evaluator.win_probability(allies, enemies)
    # Même définition qu'avant SPEC-12 (écart entre les deux camps), pour que les seuils
    # d'évaluation gardent leur calibrage.
    draft_diff = (2.0 * win_probability - 1.0) * 100.0
    return FinalAnalysis(
        lines=FinalDraftAnalyzer(monitor)._face_off_lines(allies, enemies),
        win_probability=win_probability,
        draft_diff=draft_diff,
        evaluation=evaluation_of(draft_diff)[0],
        loadout=_loadout_of(monitor),
    )


def _loadout_of(monitor) -> Optional[Dict[str, Any]]:
    """La build écrite dans le client à cet instant (None avant le lock-in ou si illisible)."""
    try:
        loadout = monitor.loadout.state(with_duel=True)
    except Exception:  # pylint: disable=broad-exception-caught
        return None
    return loadout if isinstance(loadout, dict) else None
