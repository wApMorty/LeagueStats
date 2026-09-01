"""UI for real-time draft coach (League Client integration)."""

from typing import Optional
from ..draft_monitor import DraftMonitor
from ..utils.console import clear_console
from ..config_constants import draft_config
from ..user_prefs import UserPrefs, save_user_prefs


def _prompt_synergy_weight() -> float:
    """Ask the user for the matchup/synergy blend weight (0.0-1.0).

    Empty input keeps the historical balanced behavior (default 0.5).
    Re-prompts on invalid input (non-float or out of [0.0, 1.0]).
    """
    default = draft_config.DEFAULT_SYNERGY_WEIGHT
    while True:
        raw = input(
            f"Poids synergy vs matchup (0.0=matchup uniquement, 1.0=synergy uniquement) "
            f"[defaut {default}]: "
        ).strip()
        if not raw:
            return default
        try:
            value = float(raw)
        except ValueError:
            print("[ERROR] Valeur invalide, entrez un nombre flottant entre 0.0 et 1.0.")
            continue
        if not (0.0 <= value <= 1.0):
            print("[ERROR] La valeur doit etre comprise entre 0.0 et 1.0.")
            continue
        return value


def run_draft_coach(
    verbose: bool = False,
    auto_hover: bool = False,
    auto_accept_queue: bool = False,
    auto_ban_hover: bool = False,
    open_onetricks: Optional[bool] = None,
    synergy_weight: Optional[float] = None,
    pool_name: Optional[str] = None,
) -> None:
    """
    Run the real-time draft coach.

    Args:
        verbose: Enable verbose logging
        auto_hover: Auto-hover recommended champions
        auto_accept_queue: Auto-accept queue
        auto_ban_hover: Auto-hover ban recommendations
        open_onetricks: Open champion pages on draft completion
        synergy_weight: Poids synergy/matchup mémorisé (SPEC-06 D2) ; None = redemander
        pool_name: Pool mémorisée (SPEC-06 D2) ; None = sélection interactive
    """
    clear_console()  # Clear console at start
    print("[INFO] Starting Real-time Draft Coach...")
    print("Make sure League of Legends client is running and start a game!")
    if auto_hover:
        print("🎯 [AUTO-HOVER] Champion auto-hover is ENABLED")
    if auto_accept_queue:
        print("🔥 [AUTO-ACCEPT] Queue auto-accept is ENABLED")
    if auto_ban_hover:
        print("🚫 [AUTO-BAN-HOVER] Ban hover is ENABLED")
    if open_onetricks:
        print("🌐 [ONETRICKS] Open champion page on draft completion is ENABLED")
    print("Press Ctrl+C to stop monitoring.\n")

    if synergy_weight is None:
        synergy_weight = _prompt_synergy_weight()

    monitor = None
    try:
        monitor = DraftMonitor(
            verbose=verbose,
            auto_select_pool=False,
            auto_hover=auto_hover,
            auto_accept_queue=auto_accept_queue,
            auto_ban_hover=auto_ban_hover,
            open_onetricks=open_onetricks,
            synergy_weight=synergy_weight,
            preselected_pool_name=pool_name,
        )
        monitor.start_monitoring()
    except KeyboardInterrupt:
        print("\n[INFO] Draft Coach stopped by user")
    except Exception as e:
        print(f"[ERROR] Draft coach error: {e}")
        if verbose:
            import traceback

            traceback.print_exc()
    finally:
        # SPEC-06 D2: mémorise les choix réellement utilisés (y compris la
        # pool retombée en secours si le nom mémorisé n'existait plus).
        if monitor is not None:
            save_user_prefs(
                UserPrefs(
                    auto_hover=auto_hover,
                    auto_accept_queue=auto_accept_queue,
                    auto_ban_hover=auto_ban_hover,
                    open_onetricks=bool(monitor.open_onetricks),
                    synergy_weight=monitor.synergy_weight,
                    pool_name=monitor.pool_name,
                )
            )
