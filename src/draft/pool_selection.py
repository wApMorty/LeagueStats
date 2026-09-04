"""Champion pool selection (remembered pool or interactive prompt).

Extracted from src/draft_monitor.py (SPEC-07 E10, lot 9) : déplacement
verbatim, aucun changement de comportement.

Back-reference to the monitor: both methods write ``pool_name`` as a side
effect (consumed by the pre-calculated ban lookups), and the "not found"
fallback of ``select_by_name`` must call back through the monitor's own
``_select_champion_pool_interactive`` facade — not this component directly
— so that tests patching that facade still intercept it.
"""

from typing import List

from ..constants import CHAMPIONS_BY_ROLE
from ..utils.display import safe_print


class PoolSelector:
    """Resolve the champion pool used for the draft session."""

    def __init__(self, monitor) -> None:
        self.m = monitor

    def select_by_name(self, pool_name: str) -> List[str]:
        """Charge une pool mémorisée par son nom, sans re-poser la question.

        Retombe sur la sélection interactive si la pool a été supprimée ou
        renommée depuis la dernière session (SPEC-06 D2).
        """
        try:
            from ..pool_manager import PoolManager, pool_role_to_lane

            pool_manager = PoolManager()
            pool = pool_manager.get_pool(pool_name)
            if pool is None:
                print(f"[INFO] Pool '{pool_name}' introuvable, sélection manuelle.")
                return self.m._select_champion_pool_interactive()

            safe_print(f"[OK] Pool mémorisée utilisée : {pool_name} ({', '.join(pool.champions)})")
            self.m.pool_name = pool_name
            self.m.pool_lane = pool_role_to_lane(pool.role)
            return pool.champions
        except Exception as e:
            print(f"[WARNING] Erreur lors du chargement de la pool mémorisée: {e}")
            return self.m._select_champion_pool_interactive()

    def select_interactive(self) -> List[str]:
        """Interactive pool selection with custom pools support."""
        try:
            from ..pool_manager import PoolManager, pool_role_to_lane

            pool_manager = PoolManager()

            print("\n" + "=" * 50)
            print("SÉLECTION DE LA POOL DE CHAMPIONS")
            print("=" * 50)

            # Show available pools
            pools = pool_manager.get_all_pools()
            pool_list = []

            print("\nPools disponibles :")
            idx = 1
            for name, pool in sorted(pools.items()):
                pool_list.append((name, pool))
                status = "[SYS]" if pool.created_by == "system" else "[USR]"
                print(
                    f"  {idx}. {status} {name:<20} | {pool.role:<8} | {pool.size():>2} champs | {pool.description}"
                )
                idx += 1

            # Add legacy options
            print(f"\n  {idx}. Utiliser le sélecteur de pool étendu de l'assistant (legacy)")

            try:
                choice = int(input(f"\nChoisissez une pool (1-{idx}) : ").strip())

                if 1 <= choice <= len(pool_list):
                    selected_name, selected_pool = pool_list[choice - 1]
                    safe_print(
                        f"[OK] Pool utilisée : {selected_name} ({', '.join(selected_pool.champions)})"
                    )
                    # Store pool name for pre-calculated ban lookups
                    self.m.pool_name = selected_name
                    self.m.pool_lane = pool_role_to_lane(selected_pool.role)
                    return selected_pool.champions
                elif choice == idx:
                    # Fallback to assistant's method (no pool_name)
                    self.m.pool_name = None
                    self.m.pool_lane = None
                    return self.m.assistant.select_champion_pool()
                else:
                    print("[WARNING] Choix invalide, utilisation de la pool TOP par défaut")
                    self.m.pool_name = "All Top Champions"  # System pool name
                    self.m.pool_lane = "top"
                    return CHAMPIONS_BY_ROLE["top"]

            except (ValueError, IndexError):
                print("[WARNING] Saisie invalide, utilisation de la pool TOP par défaut")
                self.m.pool_name = "All Top Champions"
                self.m.pool_lane = "top"
                return CHAMPIONS_BY_ROLE["top"]

        except Exception as e:
            print(f"[WARNING] Erreur de sélection de pool: {e}")
            print("Retour au sélecteur de pool legacy...")
            self.m.pool_name = None
            self.m.pool_lane = None
            return self.m.assistant.select_champion_pool()
