"""Menu 5 -- optimal team builder (duos/trios, holistic evaluation).

Extracted from src/ui/lol_coach_legacy.py (SPEC-07 E9).
"""

from typing import List

from src.assistant import Assistant
from src.utils.console import clear_console
from src.ui.pool_selection_ui import _select_pool_for_analysis


def run_optimal_team_builder():
    """Run optimal team building tools."""
    clear_console()  # Clear console at start
    print("[INFO] Optimal Team Builder")
    print("\nAvailable options:")
    print("1. Find optimal trio from pool (traditional - blind pick + counterpicks)")
    print("2. Find optimal duo for specific champion")
    print("3. Find optimal trio combinations (holistic evaluation)")

    choice = input("Choose option (1-3): ").strip()

    try:
        from src.pool_manager import PoolManager

        ast = Assistant()

        # Enhanced pool selection using PoolManager
        selected_pool_info = _select_pool_for_analysis()
        if not selected_pool_info:
            print("[WARNING] No pool selected, using default Top SoloQ pool")
            selected_pool = ast.select_extended_champion_pool()
        else:
            pool_name, pool_champions = selected_pool_info
            selected_pool = pool_champions
            print(f"\n✅ Using pool: {pool_name} ({len(pool_champions)} champions)")

        if choice == "1":
            print(f"\n" + "=" * 60)
            print(f"OPTIMAL TRIO ANALYSIS")
            print("=" * 60)
            result = ast.optimal_trio_from_pool(selected_pool)
            blind, counter1, counter2, score = result
            print(f"\nFINAL RESULT:")
            print(f"Blind Pick: {blind}")
            print(f"Counterpicks: {counter1}, {counter2}")
            print(f"Total Score: {score:.2f}")

            # Proposer de sauvegarder le trio comme nouveau pool
            _offer_save_optimization_result(
                [blind, counter1, counter2], f"Optimal Trio (Score: {score:.2f})"
            )

        elif choice == "2":
            champion = input("Enter champion name: ").strip()
            if champion:
                print(f"\n" + "=" * 60)
                print(f"OPTIMAL DUO FOR {champion.upper()}")
                print("=" * 60)
                duo_result = ast.optimal_duo_for_champion(champion, selected_pool)

                # Si la méthode retourne un résultat, proposer de le sauvegarder
                if duo_result and isinstance(duo_result, tuple) and len(duo_result) == 4:
                    # Extract the 3 champions (exclude the score)
                    fixed_champ, companion1, companion2, score = duo_result
                    duo_champions = [fixed_champ, companion1, companion2]
                    _offer_save_optimization_result(
                        duo_champions, f"Optimal Duo for {champion} (Score: {score:.2f})"
                    )
            else:
                print("[ERROR] No champion name provided")

        elif choice == "3":
            print(f"\n" + "=" * 60)
            print(f"HOLISTIC TRIO COMBINATIONS ANALYSIS")
            print("=" * 60)
            print(f"Analyzing all possible trio combinations from your pool...")
            print(f"This evaluates trios as complete units rather than blind pick + counterpicks")

            # Ask user for scoring profile
            scoring_profile = _select_scoring_profile()

            # Run the holistic trio analysis
            trio_results = ast.find_optimal_trios_holistic(
                selected_pool, num_results=5, profile=scoring_profile
            )

            # Display results
            _display_holistic_trio_results(trio_results, scoring_profile)

            # Offer to save the best trio
            if trio_results:
                best_trio = trio_results[0]["trio"]
                best_score = trio_results[0]["total_score"]
                _offer_save_optimization_result(
                    list(best_trio), f"Holistic Trio (Score: {best_score:.2f})"
                )

        else:
            print("[ERROR] Invalid option")

        ast.close()

    except Exception as e:
        print(f"[ERROR] Team builder error: {e}")


def _offer_save_optimization_result(champions: List[str], suggested_name: str):
    """Offer to save optimization results as a new champion pool."""
    if not champions:
        return

    # Show ban recommendations for this optimized pool
    _show_ban_recommendations(champions)

    save_choice = input(f"\nSave this result as a new pool? (y/N): ").strip().lower()
    if save_choice != "y":
        return

    try:
        from src.pool_manager import PoolManager

        pool_manager = PoolManager()

        print(f"\nSaving pool with champions: {', '.join(champions)}")

        # Suggest a name but allow customization
        default_name = suggested_name
        pool_name = input(f"Pool name (or press Enter for '{default_name}'): ").strip()
        if not pool_name:
            pool_name = default_name

        # Check if name already exists
        if pool_manager.get_pool(pool_name):
            print(f"[WARNING] Pool '{pool_name}' already exists.")
            overwrite = input("Overwrite existing pool? (y/N): ").strip().lower()
            if overwrite != "y":
                return
            pool_manager.delete_pool(pool_name)  # Remove existing

        description = input("Description (optional): ").strip()
        if not description:
            description = f"Generated from optimization analysis"

        # Determine role based on champions (simple heuristic)
        role = "custom"

        # Tags
        tags = ["optimization", "generated"]

        if pool_manager.create_pool(pool_name, champions, description, role, tags):
            print(f"[SUCCESS] Created pool '{pool_name}' with {len(champions)} champions!")

            # Save immediately
            if pool_manager.save_custom_pools():
                print(f"[SUCCESS] Pool saved successfully!")
            else:
                print(
                    f"[WARNING] Pool created but save failed. Use 'Manage Champion Pools' menu to save manually."
                )
        else:
            print(f"[ERROR] Failed to create pool '{pool_name}'")

    except Exception as e:
        print(f"[ERROR] Error saving optimization result: {e}")


def _select_scoring_profile() -> str:
    """Ask user to select a scoring profile for trio analysis."""
    print(f"\n" + "=" * 50)
    print("SELECT SCORING PROFILE")
    print("=" * 50)
    print("Choose your preferred analysis style:")
    print()
    print("  1. SAFE       - Prioritizes consistency and balance over raw performance")
    print("                  Best for: Risk-averse players, ranked climbing")
    print()
    print("  2. META       - Focuses on performance against popular champions")
    print("                  Best for: Current patch adaptation, high elo play")
    print()
    print("  3. AGGRESSIVE - Maximizes coverage and diverse champion profiles")
    print("                  Best for: Proactive players, team flexibility")
    print()
    print("  4. BALANCED   - Mathematical weights with no bias")
    print("                  Best for: Default choice, general use")
    print()

    profile_map = {"1": "safe", "2": "meta", "3": "aggressive", "4": "balanced"}

    while True:
        choice = input("Choose scoring profile (1-4): ").strip()

        if choice in profile_map:
            selected_profile = profile_map[choice]
            profile_names = {
                "safe": "SAFE",
                "meta": "META",
                "aggressive": "AGGRESSIVE",
                "balanced": "BALANCED",
            }
            print(f"\nSelected profile: {profile_names[selected_profile]}")
            return selected_profile
        else:
            print("[ERROR] Invalid choice. Please select 1-4.")


def _display_holistic_trio_results(trio_results: List[dict], profile: str = "balanced"):
    """Display the results of holistic trio analysis in a clear format."""
    try:
        if not trio_results:
            print("No viable trios found")
            return

        # Display profile info
        profile_names = {
            "safe": "SAFE (Consistency Focus)",
            "meta": "META (Popular Champions Focus)",
            "aggressive": "AGGRESSIVE (Coverage Focus)",
            "balanced": "BALANCED (Mathematical Weights)",
        }

        print(f"\nTOP TRIO COMBINATIONS FOUND:")
        print(f"Analysis Profile: {profile_names.get(profile, profile.upper())}")
        print("=" * 80)

        for i, result in enumerate(trio_results, 1):
            trio = result["trio"]
            total = result["total_score"]
            coverage = result["coverage_score"]
            balance = result["balance_score"]
            consistency = result["consistency_score"]
            meta = result["meta_score"]

            # Rank symbol
            rank_symbol = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."

            print(f"\n{rank_symbol} {trio[0]} + {trio[1]} + {trio[2]}")
            print(f"   🎯 Total Score: {total:>5.2f}/100")
            print(f"   📊 Coverage:    {coverage:>5.2f}/100  (Enemy matchup coverage)")
            print(f"   ⚖️  Balance:     {balance:>5.2f}/100  (Diverse profiles)")
            print(f"   📈 Consistency: {consistency:>5.2f}/100  (Reliable performance)")
            print(f"   🌟 Meta:        {meta:>5.2f}/100  (vs popular picks)")

            # Show some enemy coverage examples for top trio
            if i == 1 and "enemy_coverage" in result:
                coverage_data = result["enemy_coverage"]
                if coverage_data:
                    print(f"   Best matchups: ", end="")
                    top_matchups = sorted(
                        coverage_data.items(), key=lambda x: x[1][0], reverse=True
                    )[:3]
                    matchup_strs = [
                        f"{enemy}(+{delta2:.2f})"
                        for enemy, (delta2, _) in top_matchups
                        if delta2 > 0
                    ]
                    print(", ".join(matchup_strs[:3]) if matchup_strs else "None significant")

        print("\n" + "=" * 80)
        print("💡 INTERPRETATION:")
        print("   • Higher scores = better overall trio performance")
        print("   • Coverage = How well the trio handles all enemies")
        print("   • Balance = Diversity to avoid shared weaknesses")
        print("   • Consistency = Reliable performance across matchups")
        print("   • Meta = Performance vs currently popular champions")

    except Exception as e:
        print(f"[ERROR] Error displaying trio results: {e}")


def _show_ban_recommendations(champions: List[str]):
    """Show ban recommendations for a champion pool."""
    try:
        print(f"\n" + "=" * 60)
        print("🛡️ STRATEGIC BAN RECOMMENDATIONS")
        print("=" * 60)
        print(f"For your optimized pool: {', '.join(champions)}")

        from src.assistant import Assistant

        assistant = Assistant()

        ban_recommendations = assistant.get_ban_recommendations(champions, num_bans=5)

        if ban_recommendations:
            print(f"\nTop threats to ban:")
            # Tuple format: (enemy, threat_score, best_delta2, best_champ, matchup_count)
            for i, (enemy, threat_score, _best_delta2, _best_champ, matchup_count) in enumerate(
                ban_recommendations, 1
            ):
                print(
                    f"  {i}. {enemy:<15} | Threat: {threat_score:>5.2f} | Counters {matchup_count}/{len(champions)} champions"
                )

            print(f"\n💡 These champions are statistically strong against your pool.")
            print(f"💡 Banning them will improve your overall matchup spread.")
        else:
            print(f"⚠️ No ban recommendations found (insufficient data)")

        assistant.close()

    except Exception as e:
        print(f"[WARNING] Error generating ban recommendations: {e}")
