"""UI for real-time draft coach (League Client integration)."""

from typing import Optional
from ..draft_monitor import DraftMonitor
from ..utils.console import clear_console
from ..user_prefs import UserPrefs, save_user_prefs


def run_draft_coach(
    verbose: bool = False,
    auto_hover: bool = False,
    auto_accept_queue: bool = False,
    auto_ban_hover: bool = False,
    open_onetricks: Optional[bool] = None,
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
        pool_name: Pool mémorisée (SPEC-06 D2) ; None = sélection interactive
    """
    clear_console()  # Clear console at start
    print("[INFO] Démarrage du Draft Coach en temps réel...")
    print("Assurez-vous que le client League of Legends est lancé et démarrez une partie !")
    if auto_hover:
        print("[AUTO-HOVER] Survol automatique des champions ACTIVÉ")
    if auto_accept_queue:
        print("[AUTO-ACCEPT] Acceptation automatique de la queue ACTIVÉE")
    if auto_ban_hover:
        print("[AUTO-BAN-HOVER] Survol automatique des bans ACTIVÉ")
    if open_onetricks:
        print("[ONETRICKS] Ouverture de la page du champion en fin de draft ACTIVÉE")
    print("Appuyez sur Ctrl+C pour arrêter le suivi.\n")

    monitor = None
    try:
        monitor = DraftMonitor(
            verbose=verbose,
            auto_select_pool=False,
            auto_hover=auto_hover,
            auto_accept_queue=auto_accept_queue,
            auto_ban_hover=auto_ban_hover,
            open_onetricks=open_onetricks,
            preselected_pool_name=pool_name,
        )
        # SPEC-08 §2.6b's startup outcome backfill runs inside
        # start_monitoring(), right after self.lcu.connect() succeeds and
        # before the poll loop starts -- not here, since the LCU isn't
        # connected yet at this point and connecting here too would just
        # duplicate that call (see DraftMonitor.start_monitoring).
        monitor.start_monitoring()
    except KeyboardInterrupt:
        print("\n[INFO] Draft Coach arrêté par l'utilisateur")
    except Exception as e:
        print(f"[ERREUR] Erreur du draft coach : {e}")
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
                    pool_name=monitor.pool_name,
                )
            )
