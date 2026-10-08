"""Constantes du client LeagueStats (SPEC-21).

Réexportées par config_constants.py comme config_coaching.py
(`from .config_constants import client_config` reste valable).
"""

from dataclasses import dataclass, field
from typing import Dict, Tuple


@dataclass
class ClientConfig:
    """Serveur local, base et sécurité du client (SPEC-21 §4.1, §4.7)."""

    # Le serveur n'écoute que sur la boucle locale ; port 0 = port libre choisi par l'OS
    # (la fenêtre locale n'a pas besoin d'un port connu, @pj35, 2026-10-04).
    HOST: str = "127.0.0.1"
    PORT: int = 0
    SERVER_START_TIMEOUT_S: float = 10.0
    SERVER_STOP_TIMEOUT_S: float = 5.0

    # Fenêtre sans bordure (SPEC-21 §2 et §8). Le fond évite l'éclair blanc avant la première image.
    WINDOW_TITLE: str = "LeagueStats"
    WINDOW_SIZE: Tuple[int, int] = (1280, 800)
    WINDOW_MIN_SIZE: Tuple[int, int] = (960, 600)
    WINDOW_BACKGROUND: str = "#030e0a"  # équivalent hexadécimal de `--bg` (style.css)

    # Réglage Motion (SPEC-21 §4.3) : « systeme » suit `prefers-reduced-motion`, « reduit » coupe
    # tout, « complet » anime quel que soit le système (Windows annonce `reduce` chez @pj35).
    MOTION_MODES: Tuple[str, ...] = ("systeme", "complet", "reduit")
    MOTION_DEFAULT: str = "complet"

    # Data Dragon (SPEC-21 tâche 86) : images et données de la draft, mises en cache sur disque.
    # Version vide = la plus récente de `versions.json` (renouvelée une fois par jour).
    DDRAGON_BASE: str = "https://ddragon.leagueoflegends.com"
    DDRAGON_VERSION: str = ""
    DDRAGON_LOCALE: str = "fr_FR"
    ASSETS_DIR: str = "data/client_assets"
    ASSETS_TIMEOUT_S: float = 10.0
    ASSETS_VERSIONS_TTL_S: int = 86400
    ASSETS_RETRY_S: float = 300.0  # délai avant de retenter un téléchargement échoué
    ASSETS_BROWSER_CACHE_S: int = 86400

    # Écran de draft (SPEC-21 tâches 73 à 92) : recommandations de pick affichées, mise à l'échelle
    # sous la taille de référence du handoff.
    DRAFT_REC_COUNT: int = 4
    DRAFT_STAGE_SIZE: Tuple[int, int] = (1920, 950)

    # Skins du champion verrouillé : durée de garde de la liste lue dans le LCU.
    SKINS_TTL_S: float = 60.0

    # Transition de page (SPEC-21 tâche 94, README du handoff) : le contenu s'assombrit en `DARKEN`, le
    # remplacement attend `SWAP` (le cercle implose), la page s'ouvre en `OPEN` ; la navigation glisse en
    # `SLIDE` à la sortie de la draft.
    TRANSITION_DARKEN_MS: int = 560
    TRANSITION_SWAP_MS: int = 860
    TRANSITION_OPEN_MS: int = 820
    TRANSITION_SLIDE_MS: int = 520
    TRANSITION_RUNES: int = 44
    NAV_WIDTH_PX: int = 220  # `--nav-w` de style.css

    # Partie trouvée (SPEC-21 tâche 93) : secondes laissées pour répondre ; le compte à rebours part de
    # là, moins le `timer` du LCU (forme non relevée : à confirmer en partie réelle).
    FOUND_SECONDS: float = 10.0
    # SPEC-26 : une fois acceptée, la partie trouvée reste à l'écran au plus `HOLD_MAX_S` (trois fois la
    # fenêtre de réponse) si la phase n'avance pas ; à l'entrée en draft, la page /draft se charge sous
    # l'overlay pendant au plus `ENTER_WAIT_S` avant l'effondrement (durée de chargement non mesurée).
    FOUND_HOLD_MAX_S: float = 30.0
    FOUND_ENTER_WAIT_S: float = 1.5

    # Écran Rang (SPEC-21 tâche 51) : files suivies, seuil de photos sous lequel une file n'a pas de
    # courbe (README du handoff), fenêtre du delta de LP, parties de l'histogramme, taille de la courbe.
    RANK_QUEUE_NAMES: Dict[str, str] = field(
        default_factory=lambda: {
            "RANKED_SOLO_5x5": "Classée solo/duo",
            "RANKED_FLEX_SR": "Classée flexible",
        }
    )
    RANK_MIN_PHOTOS: int = 2
    RANK_DELTA_DAYS: int = 30
    RANK_BARS: int = 20
    RANK_CHART_SIZE: Tuple[int, int] = (1124, 560)
    RANK_BARS_SIZE: Tuple[int, int] = (1076, 120)
    RANK_X_TICKS: int = 5
    RANK_SPARK_SIZE: Tuple[int, int] = (392, 70)
    # Teinte (H d'OKLCH) de la bande et du libellé de chaque palier.
    TIER_HUES: Dict[str, int] = field(
        default_factory=lambda: {
            "IRON": 40,
            "BRONZE": 55,
            "SILVER": 230,
            "GOLD": 85,
            "PLATINUM": 215,
            "EMERALD": 155,
            "DIAMOND": 250,
            "MASTER": 310,
            "GRANDMASTER": 20,
            "CHALLENGER": 195,
        }
    )
    TIER_NAMES: Dict[str, str] = field(
        default_factory=lambda: {
            "IRON": "Fer",
            "BRONZE": "Bronze",
            "SILVER": "Argent",
            "GOLD": "Or",
            "PLATINUM": "Platine",
            "EMERALD": "Émeraude",
            "DIAMOND": "Diamant",
            "MASTER": "Maître",
            "GRANDMASTER": "Grand Maître",
            "CHALLENGER": "Challenger",
        }
    )

    # Écran Progression (SPEC-21 tâche 52) : tendance d'une métrique = moyenne glissante de son z sur
    # `WINDOW` parties, les `POINTS` dernières ; échelle verticale de ±`Z_RANGE` écarts-types.
    PROGRESSION_SPARK_WINDOW: int = 10
    PROGRESSION_SPARK_POINTS: int = 16
    PROGRESSION_SPARK_SIZE: Tuple[int, int] = (190, 40)
    PROGRESSION_Z_RANGE: float = 2.0

    # Écrans Parties et page d'une partie (SPEC-21 tâche 53) : parties listées, courbe de win chance
    # (taille du handoff), événements marqués sur la courbe, lignes des « plus coûteux / rentables ».
    PARTIES_LIMIT: int = 50
    GAME_QUEUE_NAMES: Dict[int, str] = field(
        default_factory=lambda: {
            400: "Normale (draft)",
            420: "Classée solo/duo",
            430: "Normale (à l'aveugle)",
            440: "Classée flexible",
            450: "ARAM",
            480: "Partie rapide",
            700: "Clash",
            1700: "Arena",
        }
    )
    GAME_CURVE_SIZE: Tuple[int, int] = (1124, 430)
    GAME_CURVE_MARGIN: Tuple[int, int, int, int] = (70, 50, 34, 60)
    GAME_CURVE_X_STEP_MIN: int = 5
    GAME_MARKS: int = 10
    GAME_TOP: int = 3

    # Écran Calibration (SPEC-21 tâche 54) : taille du diagramme de fiabilité.
    CALIBRATION_CHART_SIZE: Tuple[int, int] = (620, 520)

    # Accueil du coaching (SPEC-21 tâche 71) : parties en portraits, forces et faiblesses du bilan, et
    # écart (en σ) qui remplit une demi-barre divergente des constats (22 % de la demi-largeur par σ).
    HOME_LAST_GAMES: int = 10
    HOME_STRENGTHS: int = 2
    HOME_FINDING_Z_FULL: float = 2.27

    # Profil (SPEC-21 tâche 77) : files affichées (le LCU renvoie aussi celles de TFT), catégories de défis.
    PROFILE_QUEUES: Tuple[str, ...] = ("RANKED_SOLO_5x5", "RANKED_FLEX_SR")
    CHALLENGE_CATEGORIES: Dict[str, str] = field(
        default_factory=lambda: {
            "COLLECTION": "Collection",
            "TEAMWORK": "Esprit d'équipe",
            "EXPERTISE": "Expertise",
            "VETERANCY": "Ancienneté",
            "IMAGINATION": "Imagination",
        }
    )

    # Historique (SPEC-21 tâche 78) : parties demandées au LCU (il en sert 20 au plus, SPEC-19).
    HISTORY_COUNT: int = 20

    # Lobby (SPEC-21 tâche 80) : groupes de modes (`gameSelectModeGroup` du LCU) dont on propose les files
    # (Faille et ARAM ; TFT et modes alternatifs hors périmètre), phases du client où l'on peut ouvrir un
    # lobby, postes qu'on peut demander.
    LOBBY_QUEUE_GROUPS: Tuple[str, ...] = ("kSummonersRift", "kARAM")
    LOBBY_CREATE_PHASES: Tuple[str, ...] = ("None", "Lobby")
    LOBBY_POSITIONS: Tuple[str, ...] = ("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY", "FILL")

    # Social (SPEC-21 tâche 82) : longueur du dernier message affiché d'une conversation.
    SOCIAL_MESSAGE_CHARS: int = 80

    # Live Coach lancé en fil par le client : attente du client LoL (secondes) entre deux essais
    # et délai d'arrêt à la fermeture de la fenêtre.
    LIVE_COACH_RETRY_S: float = 15.0
    LIVE_COACH_STOP_TIMEOUT_S: float = 5.0

    # Banc `/_motion` (critère 11) : budget par image (60 Hz) et durée d'une scène.
    MOTION_BUDGET_MS: float = 16.7
    MOTION_BENCH_SCENE_S: int = 3

    # État du client LoL (sonde légère, mise en cache) et rafraîchissement de la pastille.
    LCU_PROBE_ENDPOINT: str = "/lol-gameflow/v1/gameflow-phase"
    LCU_PROBE_TTL_S: float = 3.0
    LCU_STATE_POLL_S: int = 5

    # Bus interne : file par abonné (le plus ancien message est abandonné quand elle déborde),
    # sondage de la file par le flux SSE (sert aussi à constater la déconnexion), battement SSE.
    BUS_QUEUE_SIZE: int = 256
    SSE_POLL_S: float = 1.0
    SSE_PING_S: int = 15
    # Un flux SSE ouvert retiendrait l'arrêt du serveur : délai avant de le couper.
    SERVER_GRACEFUL_SHUTDOWN_S: int = 2

    # WebSocket LCU (SPEC-21 §4.2) : événements suivis (préfixes d'URI), abonnement, et reconnexion
    # exponentielle bornée.
    LCU_EVENT_PREFIXES: Tuple[str, ...] = (
        "/lol-gameflow",
        "/lol-lobby",
        "/lol-matchmaking",
        "/lol-champ-select",
        "/lol-chat",
        "/lol-end-of-game",
        "/lol-ranked",
    )
    LCU_WS_SUBSCRIBE_EVENT: str = "OnJsonApiEvent"
    LCU_WS_BACKOFF_MIN_S: float = 1.0
    LCU_WS_BACKOFF_MAX_S: float = 30.0
    LCU_WS_STOP_TIMEOUT_S: float = 5.0

    # Pastille de phase de la barre de titre (SPEC-25 §4.4) : libellé de chaque famille de phase
    # publiée par `PhaseTracker` (sujet `phase`).
    PHASE_LABELS: Dict[str, str] = field(
        default_factory=lambda: {
            "idle": "Hors partie",
            "queue": "En file",
            "draft": "Champion select",
            "game": "En partie",
            "post": "Fin de partie",
            "closed": "Client LoL fermé",
            "error": "Erreur de partie",
            "unknown": "Phase inconnue",
        }
    )

    # Lecture pendant que le Live Coach écrit : attente d'un verrou avant d'abandonner.
    DB_READ_TIMEOUT_S: float = 5.0

    # Écran « En partie » (SPEC-24 tâche 107) : lecture de la Live Client API pendant la partie
    # (`INGAME_POLL_S` et `INGAME_GRACE_POLLS` reprennent `OVERLAY_*` de SPEC-20), repos hors partie, pas
    # de la série de win chance (celui du spike de SPEC-20), points gardés (une heure), lectures
    # vides d'affilée avant de conclure que la partie est finie.
    INGAME_POLL_S: float = 1.0
    INGAME_IDLE_POLL_S: float = 5.0
    INGAME_SAMPLE_S: float = 5.0
    INGAME_MAX_POINTS: int = 720
    INGAME_GRACE_POLLS: int = 10
    # Premier point de la série au-delà duquel l'écran dit que le début de la partie n'est pas tracé.
    INGAME_LATE_START_S: float = 60.0

    # Jeton de session (octets aléatoires) et en-tête qui le porte.
    SESSION_TOKEN_BYTES: int = 32
    TOKEN_HEADER: str = "X-Session-Token"

    # Hôtes acceptés dans `Host` et `Origin` (anti-DNS rebinding, anti-CSRF).
    ALLOWED_HOSTS: Tuple[str, ...] = ("127.0.0.1", "localhost")

    # Méthodes qui modifient quelque chose, et lectures qui exigent aussi le jeton (SSE).
    TOKEN_METHODS: Tuple[str, ...] = ("POST", "PUT", "PATCH", "DELETE")
    TOKEN_PATHS: Tuple[str, ...] = ("/events",)

    def transition(self) -> dict:
        """Les durées de la transition de page, telles que `transition.js` les lit."""
        return {
            "darken": self.TRANSITION_DARKEN_MS,
            "swap": self.TRANSITION_SWAP_MS,
            "open": self.TRANSITION_OPEN_MS,
            "slide": self.TRANSITION_SLIDE_MS,
            "runes": self.TRANSITION_RUNES,
            "nav_width": self.NAV_WIDTH_PX,
        }


client_config = ClientConfig()
