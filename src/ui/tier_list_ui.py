"""Menu 4 -- champion analysis & tournament coaching entry point, tier lists.

Extracted from src/ui/lol_coach_legacy.py (SPEC-07 E9).
"""

from typing import List

from src.utils.console import clear_console
from src.ui.pool_selection_ui import _select_pool_for_analysis
from src.ui.tournament_coach_ui import run_tournament_draft_coach


def run_champion_analysis():
    """Run champion analysis and tournament coaching."""
    clear_console()  # Clear console at start
    print("[INFO] Champion Analysis & Tournament Coaching")
    print("\nAvailable options:")
    print("1. Generate Tier List       - Create blind pick or counter pick tier lists")
    print("2. Tournament Draft Coach   - Manual coaching for external tournaments")
    print("3. Back to main menu")

    choice = input("\nChoose option (1-3): ").strip()

    if choice == "1":
        run_tier_list_generator()
    elif choice == "2":
        run_tournament_draft_coach()
    elif choice == "3":
        return
    else:
        print("[ERROR] Invalid option")


def run_tier_list_generator():
    """Generate tier lists for champion pools."""
    clear_console()  # Clear console at start
    print("[INFO] Tier List Generator")

    try:
        from src.assistant import Assistant

        # Step 1: Select champion pool
        print("\n" + "=" * 60)
        print("STEP 1: SELECT CHAMPION POOL")
        print("=" * 60)

        selected_pool_info = _select_pool_for_analysis()
        if not selected_pool_info:
            print("[ERROR] No pool selected")
            return

        pool_name, champion_pool = selected_pool_info
        print(f"\n✅ Selected pool: {pool_name} ({len(champion_pool)} champions)")

        # Step 2: Select analysis type
        print("\n" + "=" * 60)
        print("STEP 2: SELECT ANALYSIS TYPE")
        print("=" * 60)
        print("\nChoose tier list type:")
        print("  1. Blind Pick    - Champions with consistent performance across matchups")
        print("  2. Counter Pick  - Champions with high peaks in specific matchups")
        print("  3. Cancel")

        type_choice = input("\nChoice (1-3): ").strip()

        if type_choice == "1":
            analysis_type = "blind_pick"
            type_name = "BLIND PICK"
        elif type_choice == "2":
            analysis_type = "counter_pick"
            type_name = "COUNTER PICK"
        elif type_choice == "3":
            print("[INFO] Cancelled by user")
            return
        else:
            print("[ERROR] Invalid choice")
            return

        # Step 3: Generate tier list
        print("\n" + "=" * 60)
        print(f"GENERATING {type_name} TIER LIST...")
        print("=" * 60)

        assistant = Assistant()
        tier_list = assistant.generate_tier_list(champion_pool, analysis_type)
        assistant.close()

        if not tier_list:
            print("[WARNING] No champions with sufficient data found in pool")
            return

        # Step 4: Display results
        _display_tier_list(tier_list, pool_name, type_name, analysis_type)

    except Exception as e:
        print(f"[ERROR] Tier list generation error: {e}")
        import traceback

        traceback.print_exc()


def _display_tier_list(tier_list: List[dict], pool_name: str, type_name: str, analysis_type: str):
    """Display formatted tier list results."""
    from src.config_constants import analysis_config
    from src.assistant import safe_print

    print("\n" + "=" * 80)
    if analysis_type == "blind_pick":
        safe_print(f"🎯 {type_name} TIER LIST - {pool_name} ({len(tier_list)} champions)")
        print("Focus: Consistency and stability across all matchups")
    else:
        safe_print(f"⚔️ {type_name} TIER LIST - {pool_name} ({len(tier_list)} champions)")
        print("Focus: Situational power and counter potential")
    print("=" * 80)

    # Group by tier
    tiers = {"S": [], "A": [], "B": [], "C": []}
    for entry in tier_list:
        tiers[entry["tier"]].append(entry)

    # Display each tier
    tier_icons = {"S": "🟢", "A": "🟡", "B": "🟠", "C": "🔴"}
    tier_ranges = {
        "S": f"{analysis_config.TIER_THRESHOLDS["S"]:.0f}-100",
        "A": f"{analysis_config.TIER_THRESHOLDS["A"]:.0f}-{analysis_config.TIER_THRESHOLDS["S"]:.0f}",
        "B": f"{analysis_config.TIER_THRESHOLDS["B"]:.0f}-{analysis_config.TIER_THRESHOLDS["A"]:.0f}",
        "C": f"0-{analysis_config.TIER_THRESHOLDS["B"]:.0f}",
    }

    for tier_letter in ["S", "A", "B", "C"]:
        champions_in_tier = tiers[tier_letter]
        if not champions_in_tier:
            continue

        tier_desc = {
            "S": "Elite" if analysis_type == "blind_pick" else "Premium counterpicks",
            "A": "Strong" if analysis_type == "blind_pick" else "Strong counterpicks",
            "B": "Situational" if analysis_type == "blind_pick" else "Niche counterpicks",
            "C": "Weak" if analysis_type == "blind_pick" else "Limited value",
        }

        safe_print(
            f"\n{tier_icons[tier_letter]} {tier_letter}-TIER ({tier_ranges[tier_letter]}) - {tier_desc[tier_letter]}"
        )

        for i, entry in enumerate(champions_in_tier, 1):
            champion = entry["champion"]
            score = entry["score"]
            metrics = entry["metrics"]

            print(f"  {i}. {champion:<15} | Score: {score:>5.1f} / 100")

            # Display metrics based on analysis type
            if analysis_type == "blind_pick":
                avg_delta2 = metrics["avg_delta2_raw"]
                variance = metrics["variance"]
                coverage = metrics["coverage_raw"]
                safe_print(f"     📊 Avg Delta2:   {avg_delta2:>+5.2f}  (Performance)")
                safe_print(
                    f"     📈 Stability:    {metrics['stability']:>5.2f}  (Variance: {variance:.2f})"
                )
                safe_print(f"     ✅ Coverage:     {coverage:>5.1%}  (Decent matchups)")

            elif analysis_type == "counter_pick":
                peak_impact = metrics["peak_impact_raw"]
                variance = metrics["variance"]
                target_ratio = metrics["target_ratio_raw"]
                safe_print(f"     💥 Peak Impact:  {peak_impact:>5.2f}  (Weighted good matchups)")
                safe_print(f"     📊 Volatility:   {variance:>5.2f}  (High = situational)")
                safe_print(f"     🎯 Targets:      {target_ratio:>5.1%}  (Viable counterpick %)")

            print()

    # Summary footer
    print("=" * 80)
    safe_print("💡 TIER LIST CONFIGURATION:")
    if analysis_type == "blind_pick":
        safe_print(
            f"   • Weights: Performance {analysis_config.BLIND_AVG_WEIGHT:.0%}, "
            f"Stability {analysis_config.BLIND_STABILITY_WEIGHT:.0%}, "
            f"Coverage {analysis_config.BLIND_COVERAGE_WEIGHT:.0%}"
        )
    else:
        safe_print(
            f"   • Weights: Peak Impact {analysis_config.COUNTER_PEAK_WEIGHT:.0%}, "
            f"Volatility {analysis_config.COUNTER_VOLATILITY_WEIGHT:.0%}, "
            f"Targets {analysis_config.COUNTER_TARGETS_WEIGHT:.0%}"
        )
    safe_print(
        f"   • Thresholds: S≥{analysis_config.TIER_THRESHOLDS["S"]:.0f}, "
        f"A≥{analysis_config.TIER_THRESHOLDS["A"]:.0f}, "
        f"B≥{analysis_config.TIER_THRESHOLDS["B"]:.0f}"
    )
    print("=" * 80)
