import json
import os
import sys
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, asdict, field
from .config import get_resource_path


def get_user_pools_path() -> str:
    """Get the path for user pools file, ensuring it's writable and persistent."""
    if getattr(sys, "frozen", False):
        # Mode exécutable PyInstaller
        # Sauve à côté de l'exécutable pour la persistance
        executable_dir = os.path.dirname(sys.executable)
        pools_path = os.path.join(executable_dir, "champion_pools.json")
    else:
        # Mode développement
        # Utilise le répertoire du projet
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        pools_path = os.path.join(project_root, "champion_pools.json")

    return pools_path


@dataclass
class ChampionPool:
    """Represents a champion pool with metadata."""

    name: str
    champions: List[str]
    description: str = ""
    role: str = "custom"
    created_by: str = "user"
    tags: List[str] = field(default_factory=list)

    def __post_init__(self):
        # Ensure no duplicates and maintain order
        seen = set()
        unique_champs = []
        for champ in self.champions:
            if champ not in seen:
                seen.add(champ)
                unique_champs.append(champ)
        self.champions = unique_champs

    def add_champion(self, champion: str) -> bool:
        """Add a champion to the pool if not already present."""
        if champion not in self.champions:
            self.champions.append(champion)
            return True
        return False

    def remove_champion(self, champion: str) -> bool:
        """Remove a champion from the pool."""
        if champion in self.champions:
            self.champions.remove(champion)
            return True
        return False

    def has_champion(self, champion: str) -> bool:
        """Check if champion is in the pool."""
        return champion in self.champions

    def size(self) -> int:
        """Get the number of champions in the pool."""
        return len(self.champions)


class PoolManager:
    """Manages champion pools with save/load functionality."""

    def __init__(self):
        self.pools: Dict[str, ChampionPool] = {}
        self.pools_file = get_user_pools_path()
        self._load_default_pools()
        self._load_custom_pools()

    def _load_default_pools(self):
        """Load default pools from constants."""
        from .constants import (
            TOP_SOLOQ_POOL,
            JUNGLE_SOLOQ_POOL,
            MID_SOLOQ_POOL,
            ADC_SOLOQ_POOL,
            SUPPORT_SOLOQ_POOL,
            CHAMPION_POOL,
            TOP_EXTENDED_POOL,
            SUPPORT_EXTENDED_POOL,
            JUNGLE_EXTENDED_POOL,
            MID_EXTENDED_POOL,
            ADC_EXTENDED_POOL,
        )

        # Create default pools - Complete champion lists by role
        default_pools = [
            # Complete role pools
            ChampionPool(
                "All Top Champions",
                TOP_SOLOQ_POOL,
                "Complete list of viable top lane champions",
                "top",
                "system",
                ["complete", "top"],
            ),
            ChampionPool(
                "All Jungle Champions",
                JUNGLE_SOLOQ_POOL,
                "Complete list of viable jungle champions",
                "jungle",
                "system",
                ["complete", "jungle"],
            ),
            ChampionPool(
                "All Mid Champions",
                MID_SOLOQ_POOL,
                "Complete list of viable mid lane champions",
                "mid",
                "system",
                ["complete", "mid"],
            ),
            ChampionPool(
                "All ADC Champions",
                ADC_SOLOQ_POOL,
                "Complete list of viable ADC champions",
                "adc",
                "system",
                ["complete", "adc"],
            ),
            ChampionPool(
                "All Support Champions",
                SUPPORT_SOLOQ_POOL,
                "Complete list of viable support champions",
                "support",
                "system",
                ["complete", "support"],
            ),
            # Meta/competitive pool
            ChampionPool(
                "Meta Picks",
                CHAMPION_POOL,
                "Balanced selection of meta champions across all roles",
                "custom",
                "system",
                ["meta", "competitive"],
            ),
        ]

        for pool in default_pools:
            self.pools[pool.name] = pool

    def _load_custom_pools(self):
        """Load custom pools from JSON file."""
        if os.path.exists(self.pools_file):
            try:
                with open(self.pools_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    loaded_count = 0
                    for pool_data in data.get("custom_pools", []):
                        pool = ChampionPool(**pool_data)
                        self.pools[pool.name] = pool
                        loaded_count += 1
                    print(f"[INFO] Loaded {loaded_count} custom pools from {self.pools_file}")
            except Exception as e:
                print(f"[WARNING] Failed to load custom pools from {self.pools_file}: {e}")
        else:
            print(f"[INFO] No custom pools file found at {self.pools_file}")

    def save_custom_pools(self, recalculate_bans: bool = True):
        """Save custom pools to JSON file and optionally recalculate ban recommendations.

        Args:
            recalculate_bans: If True, automatically recalculate ban recommendations for all custom pools

        Returns:
            bool: True if save successful, False otherwise
        """
        try:
            custom_pools = [
                asdict(pool) for pool in self.pools.values() if pool.created_by == "user"
            ]

            # Créer le répertoire parent si nécessaire
            os.makedirs(os.path.dirname(self.pools_file), exist_ok=True)

            with open(self.pools_file, "w", encoding="utf-8") as f:
                json.dump({"custom_pools": custom_pools}, f, indent=2, ensure_ascii=False)

            print(f"[INFO] Saved {len(custom_pools)} custom pools to {self.pools_file}")

            # Recalculate ban recommendations after successful save
            if recalculate_bans and len(custom_pools) > 0:
                print(
                    f"[INFO] Recalculating ban recommendations for {len(custom_pools)} custom pools..."
                )
                try:
                    from .assistant import Assistant
                    from .db import Database

                    # Use default database path
                    db = Database("data/db.db")
                    db.connect()
                    assistant = Assistant(verbose=False)

                    ban_results = assistant.precalculate_all_custom_pool_bans()
                    successful_pools = sum(1 for count in ban_results.values() if count > 0)
                    total_bans = sum(ban_results.values())

                    print(
                        f"[SUCCESS] Recalculated {total_bans} ban recommendations for {successful_pools}/{len(custom_pools)} pools"
                    )
                except Exception as e:
                    print(f"[WARNING] Failed to recalculate ban recommendations: {e}")
                    # Don't fail the save operation if ban recalculation fails

            return True
        except Exception as e:
            print(f"[ERROR] Failed to save custom pools to {self.pools_file}: {e}")
            return False

    def create_pool(
        self,
        name: str,
        champions: List[str],
        description: str = "",
        role: str = "custom",
        tags: List[str] = None,
    ) -> bool:
        """Create a new champion pool."""
        if name in self.pools:
            return False  # Pool already exists

        if tags is None:
            tags = []

        pool = ChampionPool(name, champions, description, role, "user", tags)
        self.pools[name] = pool
        return True

    def delete_pool(self, name: str) -> bool:
        """Delete a pool (only custom pools can be deleted)."""
        if name not in self.pools:
            return False

        pool = self.pools[name]
        if pool.created_by == "system":
            return False  # Cannot delete system pools

        del self.pools[name]
        return True

    def get_pool(self, name: str) -> Optional[ChampionPool]:
        """Get a pool by name."""
        return self.pools.get(name)

    def get_pool_names(self, role: str = None, tags: List[str] = None) -> List[str]:
        """Get list of pool names, optionally filtered by role or tags."""
        names = []
        for name, pool in self.pools.items():
            if role and pool.role != role and pool.role != "custom":
                continue
            if tags and not any(tag in pool.tags for tag in tags):
                continue
            names.append(name)
        return sorted(names)

    def get_all_pools(self) -> Dict[str, ChampionPool]:
        """Get all pools."""
        return self.pools.copy()

    def update_pool(self, name: str, **kwargs) -> bool:
        """Update pool properties."""
        if name not in self.pools:
            return False

        pool = self.pools[name]
        if pool.created_by == "system":
            return False  # Cannot modify system pools

        for key, value in kwargs.items():
            if hasattr(pool, key):
                setattr(pool, key, value)

        return True

    def duplicate_pool(self, source_name: str, new_name: str) -> bool:
        """Duplicate an existing pool with a new name."""
        if source_name not in self.pools or new_name in self.pools:
            return False

        source_pool = self.pools[source_name]
        new_pool = ChampionPool(
            name=new_name,
            champions=source_pool.champions.copy(),
            description=(
                f"Copy of {source_pool.description}"
                if source_pool.description
                else f"Copy of {source_name}"
            ),
            role=source_pool.role,
            created_by="user",
            tags=source_pool.tags.copy(),
        )
        self.pools[new_name] = new_pool
        return True

    def search_pools(self, query: str) -> List[str]:
        """Search for pools by name or description."""
        query_lower = query.lower()
        matches = []

        for name, pool in self.pools.items():
            if (
                query_lower in name.lower()
                or query_lower in pool.description.lower()
                or any(query_lower in tag.lower() for tag in pool.tags)
            ):
                matches.append(name)

        return sorted(matches)

    def get_pool_stats(self) -> Dict[str, int]:
        """Get statistics about pools."""
        stats = {
            "total_pools": len(self.pools),
            "custom_pools": sum(1 for p in self.pools.values() if p.created_by == "user"),
            "system_pools": sum(1 for p in self.pools.values() if p.created_by == "system"),
        }

        # Count by role
        for pool in self.pools.values():
            role_key = f"{pool.role}_pools"
            stats[role_key] = stats.get(role_key, 0) + 1

        return stats


def validate_champion_name(champion: str, available_champions: Set[str]) -> bool:
    """Validate that a champion name exists."""
    return champion in available_champions


def suggest_champions(partial: str, available_champions: Set[str], limit: int = 5) -> List[str]:
    """Suggest champion names based on partial input."""
    partial_lower = partial.lower()
    matches = []

    for champion in available_champions:
        if champion.lower().startswith(partial_lower):
            matches.append(champion)
        elif partial_lower in champion.lower():
            matches.append(champion)

    return sorted(matches)[:limit]
