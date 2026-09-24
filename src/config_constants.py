"""
Configuration constants for LeagueStats Coach.
Centralized configuration for all hardcoded values across the application.
"""

from dataclasses import dataclass, field
from typing import Dict

# SPEC-04 B3: LCU `assignedPosition` values -> `lane` column values.
# The LCU calls the support role "utility"; LoLalytics (and the `lane`
# column) call it "support". An empty string means the queue doesn't
# assign roles (e.g. normal blind pick) and is intentionally absent here.
LCU_POSITION_TO_LANE: Dict[str, str] = {
    "top": "top",
    "jungle": "jungle",
    "middle": "middle",
    "bottom": "bottom",
    "utility": "support",
}


@dataclass
class ScrapingConfig:
    """Configuration for web scraping operations."""

    # Cookie acceptance - coordinates hardcoded (TO BE FIXED in Tâche #4)
    COOKIE_CLICK_X: int = 1661
    COOKIE_CLICK_Y: int = 853
    COOKIE_BUTTON_DELAY: float = 0.3

    # Page interaction delays
    PAGE_LOAD_DELAY: float = 2.0
    SCROLL_DELAY: float = 2.0

    # Cloudflare handling
    # How long to wait for the CF JS challenge to auto-resolve.
    # Set to 120s so the user has time to manually click "Verify" if CF shows
    # a Managed Challenge (CAPTCHA) instead of auto-resolving.
    CLOUDFLARE_WAIT_SECONDS: int = 120

    # Random delay ranges (replace fixed delays with ranges for anti-detection)
    PAGE_LOAD_DELAY_MIN: float = 1.5
    PAGE_LOAD_DELAY_MAX: float = 3.5
    SCROLL_DELAY_MIN: float = 1.5
    SCROLL_DELAY_MAX: float = 3.5

    # Scraping loop delays
    SCRAPING_DELAY_BETWEEN_CHAMPIONS: int = 1
    RETRY_ATTEMPTS: int = 3
    TIMEOUT: int = 30

    # Scroll position to trigger lazy-loading of the matchup/synergy section.
    # The section is at absolute Y ~2200. Scrolling to 1700 places it at
    # viewport Y ~500 (center of a 994px viewport), triggering IntersectionObserver.
    MATCHUP_SCROLL_Y: int = 1700

    # Scroll distance for horizontal matchup carousel
    MATCHUP_CAROUSEL_SCROLL_X: int = 460

    # Parallel scraping configuration
    DEFAULT_MAX_WORKERS: int = 5  # Optimal for i5-14600KF (20 threads, 50% usage)
    FIREFOX_STARTUP_DELAY: float = 1.0  # Minimal delay for Firefox initialization
    HEADLESS: bool = True  # Run Firefox in headless mode (no GUI, better performance)

    # ── Multi-lane scraping (Horizon 1) ──────────────────────────────────────
    # LoLalytics lane identifiers, as used in ?lane= URLs and stored in the
    # matchups/synergies `lane` column.
    LANES: tuple = ("top", "jungle", "middle", "bottom", "support")

    # Stored value for rows whose lane is unknown (discovery failure, legacy
    # scrape). SPEC-03 B8: NULL is never used in `lane` — SQLite treats
    # NULL != NULL, so a unique index on (champion, enemy, lane) would not
    # constrain untagged rows at all.
    DEFAULT_LANE: str = "default"

    # A lane is scraped for a champion when its share of the champion's games
    # exceeds this threshold. Originally 10.0 (ROADMAP_2026.md H1: « lanes à
    # pickrate >10% »); révisé à 5.0 par SPEC-09 E2 (2026-09-05) — mesuré sur
    # la base du 2026-09-05, 10% laissait invisibles 60 combos
    # (champion, lane) qui se jouent réellement (283 -> 343 combos, soit
    # +21%), typiquement les picks de niche où un coach a le plus de valeur
    # (ex: Malphite middle 8.7%, Pantheon middle 9.0%, Lissandra top 9.6%).
    # Coût accepté : scrape complet ~45 -> ~55 min (+21% de pages, 5 workers).
    LANE_PICKRATE_THRESHOLD: float = 5.0

    # Lane discovery is plain HTTP (the distribution is in the SSR HTML,
    # no JS rendering needed) — much cheaper than a Selenium page load.
    LANE_DISCOVERY_TIMEOUT: int = 20
    LANE_DISCOVERY_MAX_WORKERS: int = 8
    LANE_DISCOVERY_USER_AGENT: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0"
    )

    # Firefox profile path for Cloudflare bypass via cf_clearance cookie reuse.
    # Set to an existing Firefox profile that has already solved CF challenges on
    # lolalytics.com.  The scraper copies only cookies.sqlite from this directory
    # so parallel workers don't conflict with Firefox's profile lock.
    #
    # How to set up:
    #   1. Open Firefox → about:profiles → Create a New Profile named "lolalytics"
    #   2. Launch that profile, browse to lolalytics.com, solve any CF challenge
    #   3. Navigate a few champion pages to accumulate cf_clearance cookies
    #   4. Close Firefox (important: releases the profile lock)
    #   5. Open Firefox → about:profiles, click "Open Folder" for the profile
    #   6. Paste that path here (raw string, forward slashes or escaped backslashes)
    #
    # Example (Windows):
    #   FIREFOX_PROFILE_PATH: str = r"C:\Users\Paul\AppData\Roaming\Mozilla\Firefox\Profiles\xxxxxxxx.lolalytics"
    FIREFOX_PROFILE_PATH: str = ""


@dataclass
class AnalysisConfig:
    """Configuration for champion analysis and tier list generation."""

    # Minimum thresholds for data quality
    # Valeurs scalées à ~40% des seuils Diamond+ d'origine (2000/10000/200) suite
    # au passage au tier Master+ (config.LOLALYTICS_TIER) : le volume de games
    # observé à Master+ tourne autour de 37-39% du volume Diamond+ pour un
    # champion donné (mesuré sur lolalytics, 2026-09).
    MIN_GAMES_THRESHOLD: int = 800  # Minimum total games for tier lists
    MIN_GAMES_COMPETITIVE: int = 4000  # Higher threshold for competitive
    MIN_PICKRATE: float = 0.5  # Minimum pickrate % for matchup inclusion
    MIN_MATCHUP_GAMES: int = 80  # Minimum games for matchup reliability

    # Sentinel `lane` value in champion_scores for the toutes-lanes aggregate
    # score (fallback for multi-lane/custom pools). Distinct from
    # ScrapingConfig.LANES (top/jungle/middle/bottom/support), which tag the
    # lane-scoped rows used for role-specific tier lists.
    ALL_LANES_KEY: str = "all"

    # Lissage de confiance : un matchup à CONFIDENCE_K parties reçoit la moitié
    # du poids d'un matchup infiniment observé. Les petits échantillons sont
    # ramenés vers le neutre plutôt que comptés au même titre que les gros.
    #
    # SPEC-13 : n'est plus la valeur utilisée par le Live Coach, seulement son
    # REPLI. Le K réel est mesuré sur les données à chaque scrape par
    # src/analysis/shrink.py et stocké dans db_meta, par type de table — il
    # dépend de la méta, une constante ne peut pas le suivre. Mesuré à ~1900
    # sur les matchups et ~4000-20000 sur les synergies : 500 sous-shrinkait
    # d'un facteur 4 à 40. (La justification d'origine — « la médiane de la base
    # est ~1 300 parties » — était fausse de surcroît : la médiane mesurée est
    # de 225 parties.)
    CONFIDENCE_K: int = 500

    # SPEC-13 : garde-fous sur le K estimé. Un scrape dégénéré (table tronquée,
    # winrates aberrants) produirait un var_signal absurde ; ces bornes
    # l'empêchent soit d'annuler le modèle (K énorme = tout shrinké à zéro),
    # soit de le rendre crédule (K proche de 0 = plus aucun lissage). Larges
    # exprès : elles attrapent l'accident, pas la dérive de méta.
    SHRINK_K_MIN: int = 100
    SHRINK_K_MAX: int = 50000

    # Borne haute de la bissection du MLE, en points de winrate². Le signal
    # mesuré vaut ~1.4 sur les matchups : 100 est deux ordres de grandeur
    # au-dessus, donc jamais atteint sur des données saines.
    SHRINK_MAX_SIGNAL_VARIANCE: float = 100.0

    # SPEC-05 B7 : pente du logit autour de p=0.5 (d(logit)/dp = 4 à p=0.5,
    # donc 1 point de winrate ~= 0.04 en log-odds). Remplace le delta2 * 1.0
    # identité de l'ancien delta2_to_win_advantage.
    LOGIT_PER_WINRATE_POINT: float = 0.04

    # Correction du double comptage résiduel entre matchups/synergies qui se
    # recouvrent partiellement (SPEC-05 §3.3). Valeurs de départ à calibrer
    # une fois la table `predictions` alimentée (scripts/calibrate_model.py).
    K_MATCHUP: float = 1.0
    K_SYNERGY: float = 0.5

    # Doit changer à chaque modification de LOGIT_PER_WINRATE_POINT/K_MATCHUP/
    # K_SYNERGY/CONFIDENCE_K, sinon scripts/calibrate_model.py mélange des
    # prédictions issues de modèles différents.
    #
    # SPEC-12 : le Live Coach prédit maintenant via src/analysis/game_eval.py
    # (somme sur les PAIRES, antisymétrique) et non plus via la somme des
    # score_against_team par champion. Modèle différent, donc version
    # différente — les 12 prédictions "b7-v1+lane-restante" déjà en base
    # restent lisibles à part, jamais mélangées à celles-ci.
    # SPEC-13 : le shrink des tables de paires n'est plus CONFIDENCE_K=500 mais
    # un K mesuré par type (cf. src/analysis/shrink.py). Les matchups pèsent ~2x
    # moins et les synergies ~10x moins qu'en spec12-v1 : même formule, poids
    # différents, donc prédictions non mélangeables avec les précédentes.
    MODEL_VERSION: str = "spec13-v1"

    # SPEC-05 §4 B7 step 5 : en dessous de ce nombre de prédictions
    # labellisées, une courbe de calibration ou un k_m/k_s suggéré est du
    # bruit, pas un signal. Déplacé depuis scripts/calibrate_model.py
    # (SPEC-08) car src/draft/outcome_tracker.py doit afficher la même
    # valeur dans son compteur de progression ("n / 30 requises").
    MIN_ROWS_FOR_CALIBRATION: int = 30

    # SPEC-12 : au-delà de MIN_ROWS_FOR_CALIBRATION, le diagnostic de
    # calibration se re-déclenche automatiquement (console du Draft Coach)
    # tous les AUTO_CALIBRATION_CHECK_INTERVAL prédictions labellisées
    # supplémentaires -- plutôt qu'à chaque partie une fois le seuil franchi,
    # ce qui répéterait un rappel quasi identique après chaque game.
    AUTO_CALIBRATION_CHECK_INTERVAL: int = 20

    # SPEC-11 (étage b, "1 ply glouton") : le terme de risque de
    # src/analysis/one_ply_lookahead.py moyenne les LOOKAHEAD_TOP_K pires
    # delta2 plausibles restants (parmi ceux qui passent filter_valid_
    # matchups) et l'ajoute -- jamais ne le substitue -- à la contribution
    # des slots ennemis encore inconnus. Petit par construction : plus il
    # est grand, plus le "pire cas" se rapproche d'une moyenne banale et
    # perd son sens.
    LOOKAHEAD_TOP_K: int = 3

    # Poids du terme de risque ci-dessus dans la moyenne pondérée globale
    # (mêmes unités que blind_picks/SAME_LANE_WEIGHT : un poids de 1.0 pèse
    # comme un ennemi connu de plus). Terme additif et strictement monotone
    # (min/moyenne d'un sous-ensemble <= moyenne de l'ensemble) : ne peut
    # jamais améliorer le score, seulement le dégrader ou le laisser
    # inchangé -- voir one_ply_lookahead.py pour pourquoi cette propriété
    # est ce qui distingue ce terme d'une resimulation naïve.
    LOOKAHEAD_WEIGHT: float = 1.0

    # Tier thresholds (0-100 scale)
    TIER_THRESHOLDS: Dict[str, float] = field(
        default_factory=lambda: {
            "S": 75.0,  # S-Tier: 75-100
            "A": 50.0,  # A-Tier: 50-75
            "B": 25.0,  # B-Tier: 25-50
            "C": 0.0,  # C-Tier: 0-25
        }
    )

    # Blind Pick scoring weights (must sum to 1.0)
    BLIND_AVG_WEIGHT: float = 0.5  # Average performance
    BLIND_STABILITY_WEIGHT: float = 0.3  # Low variance
    BLIND_COVERAGE_WEIGHT: float = 0.2  # Coverage of decent matchups

    # Matchup quality thresholds
    DECENT_MATCHUP_THRESHOLD: float = 0.0  # delta2 > 0
    GOOD_MATCHUP_THRESHOLD: float = 1.0  # Good matchup
    EXCELLENT_MATCHUP_THRESHOLD: float = 2.5  # Excellent matchup

    # Normalization ranges
    MIN_DELTA2: float = -3.0
    MAX_DELTA2: float = 3.0
    MAX_VARIANCE: float = 10.0
    MAX_PEAK_IMPACT: float = 2.0


@dataclass
class DraftConfig:
    """Configuration for real-time draft monitoring."""

    # Polling and interaction
    POLL_INTERVAL: float = 1.0  # Check draft state every N seconds
    AUTO_HOVER_DELAY: float = 0.5  # Delay before auto-hovering champion

    # Feature toggles
    AUTO_BAN_ENABLED: bool = True
    AUTO_ACCEPT_QUEUE_ENABLED: bool = False
    OPEN_ONETRICKS_ON_DRAFT_END: bool = True

    # SPEC-06 E7: below this total games (all matchups for a candidate
    # champion combined), the sample is too thin to score during live draft.
    # Scalé à ~40% (500->200) suite au passage au tier Master+, voir
    # AnalysisConfig.MIN_GAMES_THRESHOLD.
    MIN_CHAMPION_GAMES: int = 200

    # SPEC-14 : paliers (en points de winrate) des chevrons de la colonne DUEL
    # de l'analyse finale — 1 chevron à partir de 1.0, 2 à 2.0, 3 à 3.0. Les deux
    # premiers reprennent les paliers des anciens marqueurs [+]/[++].
    DUEL_ARROW_THRESHOLDS: tuple = (1.0, 2.0, 3.0)

    # SPEC-15 / ADR-003 : build OneTricks importée au lock-in. Le User-Agent de
    # navigateur fait passer le checkpoint anti-bot Vercel, acceptable tant que
    # le volume reste celui d'une consultation manuelle (2 pages par draft).
    # La page répond en 0,1-2,3 s : le timeout borne le pire cas dans la boucle.
    LOADOUT_TIMEOUT_SECONDS: float = 5.0
    LOADOUT_USER_AGENT: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
    )
    # Risque du test binomial qui décide si le duel change un composant de la
    # build générale (SPEC-15 §3.2.1). Plus haut = plus de substitutions, et
    # plus de bruit : sur 40 parties de duel, 0.05 ne laisse passer que des
    # écarts francs (Fatigue contre Draven : 12 % contre < 4 %).
    LOADOUT_MATCHUP_ALPHA: float = 0.05
    # Import automatique de la build au lock-in (SPEC-15). False = aucun appel
    # à OneTricks ni écriture dans le client.
    AUTO_IMPORT_LOADOUT: bool = True
    # Préfixe de la page de runes et du set d'items écrits par le coach : seuls
    # les éléments portant ce préfixe sont jamais supprimés ou remplacés.
    LOADOUT_PREFIX: str = "LS "

    # Draft phase detection
    READY_CHECK_COOLDOWN: float = 2.0  # Seconds after accepting queue

    # Matchup vs synergy blend for the final recommendation score
    DEFAULT_SYNERGY_WEIGHT: float = 0.5  # 0.0 = matchup only, 1.0 = synergy only
    # Formula (DraftScorer.final_score):
    #   final_score = matchup_score * min(1, 2 * (1 - synergy_weight))
    #               + synergy_score * min(1, 2 * synergy_weight)
    # At the default 0.5, both coefficients clamp to 1, so this is exactly
    # matchup_score + synergy_score (unchanged historical behavior).
    #
    # N'est PLUS demandé à l'utilisateur : le curseur interactif ne pilotait
    # que DraftMonitor, dont le DraftScorer n'avait plus d'appelant depuis
    # SPEC-12 (le Live Coach passe par game_eval + la recherche, qui utilisent
    # analysis_config.K_SYNERGY). Reste un réglage développeur sur le seul
    # chemin qui mélange encore les deux scores : Assistant.draft_scorer, servi
    # au Team Builder et à RecommendationEngine. La valeur 0.5 y est la seule
    # jamais utilisée, ce qui y réduit final_score à une addition.

    # ── SPEC-12 : recherche minimax sur les picks restants (src/draft/search.py) ──

    # Budget temps d'une recherche, en secondes. L'approfondissement itératif
    # rend le meilleur coup de la dernière profondeur TERMINÉE, donc ce budget
    # borne la latence sans jamais borner la qualité par le haut. 2 s laisse le
    # coach réactif pendant que la draft bouge (le chrono de pick fait ~30 s).
    SEARCH_BUDGET_SECONDS: float = 2.0

    # Profondeur maximale, en nombre de picks déroulés. 10 = draft entière ;
    # la borne sert de garde-fou, le budget temps coupe bien avant en pratique.
    SEARCH_MAX_DEPTH: int = 10

    # Coups candidats retenus par lane libre pour les picks qui ne sont pas les
    # nôtres : les N champions les plus joués de la lane (SPEC-17 §4.1). Au-delà,
    # le facteur de branchement coûte de la profondeur ; en deçà, on rate des
    # contre-picks réels. Calibré au bench (scripts/bench_search.py, 2 s,
    # 2026-09-24) : 8 est le plus grand N qui atteint la fin de draft en B2
    # (N=10 : B2 6/7 ; N=12 : B2 6/7, B1 4). Les 8 plus joués couvrent 27 %
    # des games en top, 37 % en jungle, 34 % en mid, 56 % en bot, 42 % en
    # support.
    SEARCH_TOP_N: int = 8

    # ── SPEC-08 : boucle de mesure (résultat de partie automatique via LCU) ──

    # Fenêtre max entre la fin d'une draft et le début de la partie
    # correspondante dans l'historique LCU. 6 h couvre une partie lancée après
    # une longue file ou une pause, sans risquer d'apparier la session du soir
    # avec celle du lendemain matin.
    OUTCOME_MATCH_WINDOW_HOURS: float = 6.0

    # Nombre de prédictions en attente examinées au démarrage (rattrapage).
    OUTCOME_BACKFILL_LIMIT: int = 20

    # Parties lues dans l'historique LCU à chaque tentative de résolution.
    # Attention : le paramètre `endIndex` de l'endpoint est INCLUSIF (vérifié
    # 2026-09-05), donc la requête utilise endIndex = OUTCOME_HISTORY_DEPTH - 1.
    OUTCOME_HISTORY_DEPTH: int = 10

    # Champions communs exigés (sur 5) entre une prédiction et une partie, des
    # deux côtés — alliés ET ennemis. 4 tolère un pick modifié après le log de
    # fin de draft.
    OUTCOME_MIN_ALLY_OVERLAP: int = 4

    # Phases gameflow déclenchant une tentative de résolution.
    OUTCOME_TRIGGER_PHASES: tuple = ("WaitingForStats", "PreEndOfGame", "EndOfGame")


@dataclass
class RoleInferenceConfig:
    """Configuration for team role inference (SPEC-04 B4, src/role_inference.py)."""

    # Floor applied to a champion's lane share before taking log() — a lane
    # never played (share=0) must become an improbable assignment, not an
    # impossible one (log(0)), since the only valid assignment sometimes
    # requires it (exotic comp). In percent, same unit as champion_lanes.share.
    EPSILON: float = 0.5

    # Weighting of enemy matchups by lane proximity when scoring a candidate
    # (SPEC-04 §4.3): the enemy sharing our lane is the direct counter and
    # counts more than the rest of the enemy team. Provisional values, to be
    # calibrated with SPEC-05.
    SAME_LANE_WEIGHT: float = 2.0
    OTHER_LANE_WEIGHT: float = 1.0

    # Below this confidence, the Live Coach display flags an inferred role
    # with "?" so the player knows to double check it (SPEC-04 B5).
    ROLE_CONFIDENCE_WARN: float = 0.6


@dataclass
class UIConfig:
    """Configuration for user interface and display."""

    # Results display
    DEFAULT_RESULTS_COUNT: int = 10
    # SPEC-06 E7: arbitré à 3 pour matcher le comportement existant du draft
    # coach (top 3 affiché en direct), au lieu de la valeur 5 jamais câblée.
    MAX_RECOMMENDATIONS: int = 3

    # Table formatting
    TABLE_WIDTH: int = 80
    COLUMN_SEPARATOR: str = " | "

    # Console output
    VERBOSE_MODE: bool = False


@dataclass
class XPathConfig:
    """XPath selectors for web scraping (LoLalytics)."""

    # Matchup data paths
    WINRATE_XPATH: str = "/html/body/main/div[5]/div[1]/div[2]/div[3]/div/div/div[1]/div[1]/text()"
    GAMES_XPATH: str = "/html/body/main/div[5]/div[1]/div[2]/div[3]/div/div/div[2]/div[1]/text()"

    # Matchup row base path
    MATCHUP_ROW_BASE: str = "/html/body/main/div[6]/div[1]/div[{index}]/div[2]/div"

    # Synergies button (LoLalytics: Click to switch from Counters to Synergies)
    # Note: LoLalytics uses a <div> containing <span>Common Teammates</span> (as of 2026-01-17)
    # The span itself has pointer-events-none, so we click the parent div
    SYNERGIES_BUTTON_XPATH: str = "//span[text()='Common Teammates']/.."


@dataclass
class PoolStatisticsConfig:
    """Configuration for pool statistics analysis."""

    # Minimum thresholds for data quality in pool statistics
    # Scalé à ~40% (100->40) suite au passage au tier Master+, voir
    # AnalysisConfig.MIN_GAMES_THRESHOLD.
    MIN_GAMES_THRESHOLD: int = 40  # Minimum total games for sufficient data
    MIN_PICKRATE: float = 0.5  # Minimum pickrate % for matchup inclusion


@dataclass
class SynergyConfig:
    """Configuration for champion synergy analysis and scoring."""

    # Minimum thresholds for synergy data quality
    MIN_SYNERGY_PICKRATE: float = 0.5  # Minimum pickrate % for synergy inclusion
    MIN_SYNERGY_GAMES: int = 200  # Minimum games for synergy reliability

    # Synergy scoring weight: SPEC-05 B7 replaced SYNERGY_BONUS_MULTIPLIER with
    # analysis_config.K_SYNERGY (same role, interpretable scale — see
    # ChampionScorer.calculate_final_score_with_synergies). Don't reintroduce
    # a second multiplier here; the two must never coexist (SPEC-05 §7).

    # Synergy aggregation method
    USE_WEIGHTED_AVERAGE: bool = True  # Weight synergies by ally pickrate
    # If True: synergy_bonus = sum(delta2 * pickrate) / sum(pickrate)
    # If False: synergy_bonus = average(delta2) for all allies

    # Feature toggle
    SYNERGIES_ENABLED: bool = True  # Global toggle for synergy feature
    # If False, synergy bonus = 0 (backward compatible behavior)

    # Display configuration
    SHOW_SYNERGY_DETAILS: bool = True  # Show detailed synergy breakdown in UI
    MAX_SYNERGIES_DISPLAYED: int = 5  # Maximum number of top synergies to display


@dataclass
class DataQualityConfig:
    """Volumetric completeness thresholds for the scraping pipeline (Horizon 1).

    Goal: a silent data loss like 2026-06-01 (40k -> 16k matchups, nobody
    noticed for 10 days) must make the pipeline fail LOUDLY instead.

    Calibration notes (2026-06-12):
    - A single LoLalytics lane page yields ~94 matchups above the 0.5%
      pickrate cutoff, so a champion playing 1 lane lands around ~90.
      FAUX (2026-09-24) : ces ~90 étaient 5 rangées × ~18 cellules, le
      carrousel virtualisé n'étant jamais défilé (bug corrigé dans
      parser.py). Une page lue en entier donne ~170 adversaires distincts
      (Sion top : 172). Les deux seuils ci-dessous restent des planchers
      valides ; à relever après le premier scrape complet corrigé.
    - Mono-lane DB (the failure mode): 16 179 matchups / 12 943 synergies.
    - Multi-lane at the original >10% lane threshold measured ~25k matchups
      (283 (champion, lane) combos, base 2026-09-05).
      MIN_TOTAL_MATCHUPS sits between the two.

    SPEC-09 E2 (2026-09-05): ScrapingConfig.LANE_PICKRATE_THRESHOLD lowered
    10% -> 5%, raising the combo count to ~343 (+21%) and the expected total
    matchups to ~30k. MIN_TOTAL_MATCHUPS is left at 20000 — still a valid
    floor under the higher volume, comfortably clear of the mono-lane
    failure mode — but recalibrate upward once real nightly runs at the new
    threshold confirm the actual total (see docs/runbook_scraping.md).
    """

    # Every champion in the champions table must have at least this many
    # matchup rows, all lanes combined. Catches per-champion scrape failures.
    MIN_MATCHUPS_PER_CHAMPION: int = 75
    MIN_SYNERGIES_PER_CHAMPION: int = 50

    # Global volumetry. Catches the mono-lane regression (16k rows) without
    # tripping on legitimate multi-lane runs (~25k+ rows).
    MIN_TOTAL_MATCHUPS: int = 20000
    MIN_TOTAL_SYNERGIES: int = 15000

    # SPEC-01 A4: share of champions allowed to be empty/below-threshold
    # before the run is BLOCKED rather than merely flagged as a warning.
    # Calibrated against the 2026-07-16 incident: 13/566 champions without
    # synergies (~2.3%) should have been a warning, not a full pipeline abort.
    MAX_INCOMPLETE_CHAMPIONS_RATIO: float = 0.05

    # Data freshness: warn at app startup when the last successful update
    # is older than this (the guard-rail that was missing when auto-update
    # silently died on 2026-03-19).
    FRESHNESS_WARNING_DAYS: int = 7

    # SPEC-01 A5: number of pre-scrape db.backup-*.db snapshots kept in
    # data/ after a successful ("ok" or "partial") run. Older ones are
    # purged so backups don't accumulate indefinitely.
    BACKUP_RETENTION: int = 3


# Global configuration instances
scraping_config = ScrapingConfig()
analysis_config = AnalysisConfig()
draft_config = DraftConfig()
role_inference_config = RoleInferenceConfig()
ui_config = UIConfig()
xpath_config = XPathConfig()
pool_stats_config = PoolStatisticsConfig()
synergy_config = SynergyConfig()
data_quality_config = DataQualityConfig()
