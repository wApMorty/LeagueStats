"""OneTricks.gg browser window recycling (Brave app window per draft).

Extracted from src/draft_monitor.py (SPEC-07 E10, lot 9) : déplacement
verbatim, aucun changement de comportement.

Back-reference to the monitor (rather than composition) because
``_onetricks_proc`` is read AND reassigned by tests directly on the
DraftMonitor instance (tests/regression/test_regression_onetricks_window_recycling.py),
and must stay the single live attribute rather than a copy on this component.
"""

import os
import subprocess
import tempfile

from ..config import config
from ..constants import normalize_champion_name_for_onetricks


class OneTricksWindow:
    """Recycle a single OneTricks.gg Brave app window across drafts."""

    def __init__(self, monitor) -> None:
        self.m = monitor

    def profile_dir(self) -> str:
        """Return the dedicated, reused Brave profile dir for the OneTricks window.

        Using a dedicated ``--user-data-dir`` makes the launched Brave a standalone
        process we fully control (and can terminate). Without it, Brave merges the
        request into the user's main instance, our handle exits immediately, and we
        lose the ability to close the previous tab — which is what caused tabs to
        pile up across games. The directory is fixed (not per-call) so it is reused.
        """
        return os.path.join(tempfile.gettempdir(), "leaguestats_onetricks_profile")

    def close_window(self) -> None:
        """Terminate the previously opened OneTricks window, if any.

        Guarantees at most one OneTricks window is alive at a time, preventing the
        per-game tab/process accumulation that drove system memory growth.
        """
        proc = self.m._onetricks_proc
        if proc is None:
            return
        try:
            if proc.poll() is None:  # still running
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
        except Exception as e:
            if self.m.verbose:
                print(f"[ONETRICKS] Failed to close previous window: {e}")
        finally:
            self.m._onetricks_proc = None

    def open_champion_page(self) -> None:
        """Open the player's champion page on OneTriks.gg, recycling a single window.

        Each completed draft replaces the previous OneTricks window instead of
        opening a new tab, so Brave does not accumulate one tab per game over a
        long Draft Monitor session.
        """
        try:
            if not self.m.player_champion:
                if self.m.verbose:
                    print("[ONETRICKS] No player champion detected, skipping browser open")
                return

            # Normalize champion name for OneTricks.gg URL
            normalized_name = normalize_champion_name_for_onetricks(self.m.player_champion)
            onetricks_url = f"https://www.onetricks.gg/champions/builds/{normalized_name}"

            # Try to get Brave browser path
            try:
                brave_path = config.get_brave_path()
            except FileNotFoundError:
                if self.m.verbose:
                    print("[ONETRICKS] Brave browser not found, trying default browser")
                # Fallback to default browser. Note: we cannot recycle the default
                # browser's tabs, so accumulation is only fully prevented with Brave.
                import webbrowser

                webbrowser.open(onetricks_url)
                return

            # Close the previous OneTricks window before opening a new one.
            self.close_window()

            # Launch a dedicated, killable Brave app window (see profile_dir).
            self.m._onetricks_proc = subprocess.Popen(
                [
                    brave_path,
                    f"--app={onetricks_url}",
                    f"--user-data-dir={self.profile_dir()}",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        except Exception as e:
            if self.m.verbose:
                print(f"[WARNING] Échec d'ouverture de la page OneTricks.gg: {e}")
            else:
                print(f"[WARNING] Échec d'ouverture de la page du champion dans le navigateur")
