"""Display/formatting helpers for the tournament draft coach.

Extracted from src/ui/lol_coach_legacy.py (SPEC-07 E9). Used by
src/ui/tournament_coach_ui.py's interactive command loop.
"""


def _show_tournament_help():
    """Display tournament coach help."""
    print("\n📖 TOURNAMENT COACH COMMANDS")
    print("=" * 60)
    print("DRAFT MANAGEMENT:")
    print("  ally <champion>          - Add champion to your team")
    print("  enemy <champion>         - Add champion to enemy team")
    print("  ban <champion>           - Add champion to ban list")
    print("  remove ally/enemy/ban <champion> - Remove champion")
    print()
    print("ANALYSIS:")
    print("  status                   - Show current draft state with scores")
    print("  recommend                - Get champion recommendations")
    print("  analyze                  - Full analysis (when both teams complete)")
    print("  history                  - Show draft action history")
    print()
    print("UTILITIES:")
    print("  undo                     - Undo last action")
    print("  reset                    - Clear entire draft")
    print("  auto on/off              - Toggle auto-recommendations")
    print("  export                   - Save draft to JSON file")
    print("  import <type>: <champs>  - Quick import (see examples below)")
    print()
    print("  help, h, ?               - Show this help")
    print("  quit, exit, q            - Exit coach")
    print()
    print("IMPORT EXAMPLES:")
    print("  import ally: Aatrox, Graves, Ahri")
    print("  import enemy: Gwen, Lee Sin, Syndra")
    print("  import bans: Yone, Yasuo, Zed")
    print("=" * 60)


def _show_tournament_draft_state(assistant, ally_team, enemy_team, banned_champions, champion_pool):
    """Show enhanced tournament draft state with individual champion scores."""
    print(f"\n" + "=" * 70)
    print("📋 CURRENT DRAFT STATE")
    print("=" * 70)

    # Show teams with individual scores
    print(f"\n🟦 YOUR TEAM ({len(ally_team)}/5):")
    if ally_team:
        for champ in ally_team:
            matchups = assistant.db.get_champion_matchups_by_name(champ)
            if matchups and enemy_team:
                advantage = assistant.score_against_team(matchups, enemy_team, champ)
                if advantage >= 2.0:
                    status = "✅ Strong"
                elif advantage >= 0:
                    status = "🟡 Good"
                else:
                    status = "🔴 Weak"
                print(f"  • {champ:<15} {status:>10}  ({advantage:+.2f}%)")
            else:
                print(f"  • {champ:<15}")
    else:
        print("  (No picks yet)")

    print(f"\n🟥 ENEMY TEAM ({len(enemy_team)}/5):")
    if enemy_team:
        for champ in enemy_team:
            print(f"  • {champ}")
    else:
        print("  (No picks yet)")

    print(f"\n🚫 BANNED CHAMPIONS ({len(banned_champions)}):")
    if banned_champions:
        print(f"  {', '.join(banned_champions)}")
    else:
        print("  (None)")

    # Show progress
    remaining_ally = 5 - len(ally_team)
    remaining_enemy = 5 - len(enemy_team)
    print(f"\n📊 REMAINING PICKS:")
    print(f"  You: {remaining_ally}  |  Enemy: {remaining_enemy}")

    # Show team winrate estimate if both teams have picks
    if len(ally_team) >= 3 and len(enemy_team) >= 3:
        print(f"\n💯 DRAFT ADVANTAGE:")
        ally_advantages = []
        for champ in ally_team:
            matchups = assistant.db.get_champion_matchups_by_name(champ)
            if matchups:
                adv = assistant.score_against_team(matchups, enemy_team, champ)
                ally_advantages.append(adv)

        if ally_advantages:
            avg_advantage = sum(ally_advantages) / len(ally_advantages)
            if avg_advantage >= 2.0:
                print(f"  ✅ Strong advantage ({avg_advantage:+.2f}% avg)")
            elif avg_advantage >= 0:
                print(f"  🟡 Slight advantage ({avg_advantage:+.2f}% avg)")
            else:
                print(f"  🔴 Disadvantage ({avg_advantage:+.2f}% avg)")

    print("=" * 70)


def _show_recommendations(
    assistant, enemy_team, ally_team, banned_champions, champion_pool, nb_results
):
    """Show formatted recommendations."""
    if not enemy_team and not ally_team:
        print("⚠️ No picks yet. Add enemy picks first for meaningful recommendations.")
        return

    print(f"\n🎯 TOP {nb_results} RECOMMENDATIONS:")
    print("-" * 50)
    assistant._calculate_and_display_recommendations(
        enemy_team, ally_team, nb_results, champion_pool, banned_champions
    )


def _show_draft_history(draft_history):
    """Display draft action history."""
    if not draft_history:
        print("📜 No actions yet")
        return

    print(f"\n📜 DRAFT HISTORY ({len(draft_history)} actions):")
    print("-" * 60)
    for i, (ts, action, champ, side) in enumerate(draft_history, 1):
        action_icons = {
            "ally": "🟦",
            "enemy": "🟥",
            "ban": "🚫",
            "remove_ally": "↩️🟦",
            "remove_enemy": "↩️🟥",
            "unban": "↩️🚫",
        }
        icon = action_icons.get(action, "•")
        print(f"  {i:2}. {icon} {action.upper():<12} {champ}")


def _analyze_complete_draft(assistant, ally_team, enemy_team):
    """Analyze complete draft using same logic as draft monitor."""
    print("\n" + "=" * 80)
    print("🎯 COMPLETE DRAFT ANALYSIS")
    print("=" * 80)

    # Calculate individual scores
    ally_scores = []
    for champ in ally_team:
        matchups = assistant.db.get_champion_matchups_by_name(champ)
        if matchups:
            advantage = assistant.score_against_team(matchups, enemy_team, champ)
            ally_scores.append((champ, advantage))
        else:
            ally_scores.append((champ, None))

    enemy_scores = []
    for champ in enemy_team:
        matchups = assistant.db.get_champion_matchups_by_name(champ)
        if matchups:
            advantage = assistant.score_against_team(matchups, ally_team, champ)
            enemy_scores.append((champ, advantage))
        else:
            enemy_scores.append((champ, None))

    # Sort by advantage
    ally_scores.sort(key=lambda x: x[1] if x[1] is not None else -999, reverse=True)
    enemy_scores.sort(key=lambda x: x[1] if x[1] is not None else -999, reverse=True)

    # Display ally team
    print(f"\n🟦 YOUR TEAM PERFORMANCE:")
    print("-" * 60)
    for champ, advantage in ally_scores:
        if advantage is None:
            print(f"  {champ:<15} | ❌ Insufficient data")
        elif advantage >= 2.0:
            print(f"  {champ:<15} | ✅ {advantage:+.2f}% (Excellent)")
        elif advantage >= 1.0:
            print(f"  {champ:<15} | 🟢 {advantage:+.2f}% (Good)")
        elif advantage >= -1.0:
            print(f"  {champ:<15} | 🟡 {advantage:+.2f}% (Neutral)")
        elif advantage >= -2.0:
            print(f"  {champ:<15} | 🟠 {advantage:.2f}% (Bad)")
        else:
            print(f"  {champ:<15} | 🔴 {advantage:.2f}% (Very Bad)")

    # Display enemy team
    print(f"\n🟥 ENEMY TEAM PERFORMANCE:")
    print("-" * 60)
    for champ, advantage in enemy_scores:
        if advantage is None:
            print(f"  {champ:<15} | ❌ Insufficient data")
        elif advantage >= 2.0:
            print(f"  {champ:<15} | ⚠️ {advantage:+.2f}% (Strong vs us)")
        elif advantage >= 1.0:
            print(f"  {champ:<15} | 🟡 {advantage:+.2f}% (Good vs us)")
        elif advantage >= -1.0:
            print(f"  {champ:<15} | ➖ {advantage:+.2f}% (Neutral)")
        elif advantage >= -2.0:
            print(f"  {champ:<15} | 🟢 {advantage:.2f}% (Weak vs us)")
        else:
            print(f"  {champ:<15} | ✅ {advantage:.2f}% (Very weak vs us)")

    # Team winrate calculation using geometric mean
    ally_valid = [adv for _, adv in ally_scores if adv is not None]
    enemy_valid = [adv for _, adv in enemy_scores if adv is not None]

    if ally_valid and enemy_valid:
        print(f"\n📊 TEAM MATCHUP PREDICTION:")
        print("-" * 60)

        # Convert to winrates and use geometric mean
        ally_winrates = [50.0 + adv for adv in ally_valid]
        enemy_winrates = [50.0 + adv for adv in enemy_valid]

        ally_team_stats = assistant._calculate_team_winrate(ally_winrates)
        enemy_team_stats = assistant._calculate_team_winrate(enemy_winrates)

        # Normalize to 100%
        total = ally_team_stats["team_winrate"] + enemy_team_stats["team_winrate"]
        ally_normalized = (ally_team_stats["team_winrate"] / total) * 100
        enemy_normalized = (enemy_team_stats["team_winrate"] / total) * 100

        print(f"  Your team:   {ally_normalized:.1f}%")
        print(f"  Enemy team:  {enemy_normalized:.1f}%")

        diff = ally_normalized - enemy_normalized
        if diff >= 5.0:
            print(f"\n  ✅ Major advantage ({diff:+.1f}%)")
        elif diff >= 2.5:
            print(f"\n  🟢 Good advantage ({diff:+.1f}%)")
        elif diff >= -2.5:
            print(f"\n  🟡 Even matchup ({diff:+.1f}%)")
        elif diff >= -5.0:
            print(f"\n  🟠 Disadvantage ({diff:.1f}%)")
        else:
            print(f"\n  🔴 Major disadvantage ({diff:.1f}%)")

    print("\n" + "=" * 80)
