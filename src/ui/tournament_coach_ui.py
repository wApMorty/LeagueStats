"""Menu 4, option 2 -- tournament draft coach (manual pick/ban entry).

Extracted from src/ui/lol_coach_legacy.py (SPEC-07 E9).
"""

import sys

from src.utils.console import clear_console
from src.ui.pool_selection_ui import _select_pool_for_analysis
from src.ui.tournament_display_ui import (
    _show_tournament_help,
    _show_tournament_draft_state,
    _show_recommendations,
    _show_draft_history,
    _analyze_complete_draft,
)


def run_tournament_draft_coach():
    """Manual draft coaching for tournament scenarios."""
    clear_console()  # Clear console at start
    print("[INFO] Tournament Draft Coach")
    print("Perfect for external tournaments, scrimmages, or any draft outside the League client")
    print("\nThis tool provides the same coaching logic as the real-time coach,")
    print("but allows you to manually input pick/ban information.")

    try:
        from src.tournament_coach import TournamentCoach

        coach = TournamentCoach()
        coach.start_coaching_session()

    except ImportError:
        # If the module doesn't exist yet, create a basic implementation
        print("\n[INFO] Starting tournament coaching session...")
        _run_basic_tournament_coach()
    except Exception as e:
        print(f"[ERROR] Tournament coach error: {e}")


def _run_basic_tournament_coach():
    """Enhanced tournament coaching implementation with full features."""
    from src.assistant import Assistant
    from src.pool_manager import PoolManager
    import time
    import json

    try:
        assistant = Assistant()

        # Select coaching pool
        print("\n" + "=" * 60)
        print("SELECT CHAMPION POOL FOR COACHING")
        print("=" * 60)

        selected_pool_info = _select_pool_for_analysis()
        if not selected_pool_info:
            print("[WARNING] No pool selected, using assistant's extended pool")
            champion_pool = assistant.select_extended_champion_pool()
            pool_name = "Extended Pool"
        else:
            pool_name, champion_pool = selected_pool_info

        print(f"\n✅ Using pool: {pool_name} ({len(champion_pool)} champions)")

        # Initialize draft state
        ally_team = []
        enemy_team = []
        banned_champions = []
        draft_history = []  # (timestamp, action, champion, side)
        auto_recommend = True  # Auto-show recommendations after picks

        print("\n" + "=" * 80)
        print("🎯 TOURNAMENT DRAFT COACHING SESSION")
        print("=" * 80)
        _show_tournament_help()

        while True:
            try:
                cmd = input("\n⚡ Coach > ").strip().lower()

                if cmd in ["quit", "exit", "q"]:
                    break

                elif cmd == "status":
                    _show_tournament_draft_state(
                        assistant, ally_team, enemy_team, banned_champions, champion_pool
                    )

                elif cmd == "reset":
                    ally_team.clear()
                    enemy_team.clear()
                    banned_champions.clear()
                    draft_history.clear()
                    print("✅ Draft state reset!")

                elif cmd == "recommend":
                    _show_recommendations(
                        assistant, enemy_team, ally_team, banned_champions, champion_pool, 5
                    )

                elif cmd == "analyze":
                    if len(ally_team) == 5 and len(enemy_team) == 5:
                        _analyze_complete_draft(assistant, ally_team, enemy_team)
                    else:
                        print(
                            f"⚠️ Draft incomplete: {len(ally_team)}/5 ally, {len(enemy_team)}/5 enemy"
                        )

                elif cmd.startswith("ally "):
                    champ_input = cmd[5:].strip()
                    champ = assistant.validate_champion_name(champ_input)
                    if champ:
                        if champ in ally_team:
                            print(f"⚠️ {champ} already in your team")
                        elif champ in enemy_team:
                            print(f"⚠️ {champ} already picked by enemy")
                        elif champ in banned_champions:
                            print(f"⚠️ {champ} is banned")
                        elif len(ally_team) >= 5:
                            print(f"⚠️ Your team is full (5/5)")
                        else:
                            ally_team.append(champ)
                            draft_history.append((time.time(), "ally", champ, "ally"))
                            print(f"✅ Added {champ} to your team ({len(ally_team)}/5)")
                            if auto_recommend and enemy_team:
                                print(f"\n📊 Top picks after adding {champ}:")
                                _show_recommendations(
                                    assistant,
                                    enemy_team,
                                    ally_team,
                                    banned_champions,
                                    champion_pool,
                                    3,
                                )

                elif cmd.startswith("enemy "):
                    champ_input = cmd[6:].strip()
                    champ = assistant.validate_champion_name(champ_input)
                    if champ:
                        if champ in enemy_team:
                            print(f"⚠️ {champ} already in enemy team")
                        elif champ in ally_team:
                            print(f"⚠️ {champ} already picked by you")
                        elif champ in banned_champions:
                            print(f"⚠️ {champ} is banned")
                        elif len(enemy_team) >= 5:
                            print(f"⚠️ Enemy team is full (5/5)")
                        else:
                            enemy_team.append(champ)
                            draft_history.append((time.time(), "enemy", champ, "enemy"))
                            print(f"✅ Enemy picked {champ} ({len(enemy_team)}/5)")
                            if auto_recommend:
                                print(f"\n📊 Best counters to {champ}:")
                                _show_recommendations(
                                    assistant,
                                    enemy_team,
                                    ally_team,
                                    banned_champions,
                                    champion_pool,
                                    3,
                                )

                elif cmd.startswith("ban "):
                    champ_input = cmd[4:].strip()
                    champ = assistant.validate_champion_name(champ_input)
                    if champ:
                        if champ in banned_champions:
                            print(f"⚠️ {champ} already banned")
                        elif champ in ally_team or champ in enemy_team:
                            print(f"⚠️ {champ} already picked")
                        else:
                            banned_champions.append(champ)
                            draft_history.append((time.time(), "ban", champ, "ban"))
                            print(f"✅ Banned {champ}")

                elif cmd.startswith("remove ally "):
                    champ_input = cmd[12:].strip()
                    champ = assistant.validate_champion_name(champ_input)
                    if champ and champ in ally_team:
                        ally_team.remove(champ)
                        draft_history.append((time.time(), "remove_ally", champ, "ally"))
                        print(f"✅ Removed {champ} from your team")
                    else:
                        print(f"⚠️ {champ_input} not in your team")

                elif cmd.startswith("remove enemy "):
                    champ_input = cmd[13:].strip()
                    champ = assistant.validate_champion_name(champ_input)
                    if champ and champ in enemy_team:
                        enemy_team.remove(champ)
                        draft_history.append((time.time(), "remove_enemy", champ, "enemy"))
                        print(f"✅ Removed {champ} from enemy team")
                    else:
                        print(f"⚠️ {champ_input} not in enemy team")

                elif cmd.startswith("remove ban "):
                    champ_input = cmd[11:].strip()
                    champ = assistant.validate_champion_name(champ_input)
                    if champ and champ in banned_champions:
                        banned_champions.remove(champ)
                        draft_history.append((time.time(), "unban", champ, "ban"))
                        print(f"✅ Unbanned {champ}")
                    else:
                        print(f"⚠️ {champ_input} not in ban list")

                elif cmd == "history":
                    _show_draft_history(draft_history)

                elif cmd == "undo":
                    if draft_history:
                        ts, action, champ, side = draft_history.pop()
                        if action == "ally":
                            ally_team.remove(champ)
                            print(f"↩️ Undone: {champ} removed from ally team")
                        elif action == "enemy":
                            enemy_team.remove(champ)
                            print(f"↩️ Undone: {champ} removed from enemy team")
                        elif action == "ban":
                            banned_champions.remove(champ)
                            print(f"↩️ Undone: {champ} unbanned")
                        elif action.startswith("remove"):
                            # Can't undo removes easily, skip
                            print(f"⚠️ Can't undo remove action")
                    else:
                        print("⚠️ No actions to undo")

                elif cmd.startswith("import "):
                    _handle_import_command(
                        cmd, assistant, ally_team, enemy_team, banned_champions, draft_history
                    )

                elif cmd == "export":
                    _export_draft(ally_team, enemy_team, banned_champions, pool_name)

                elif cmd == "auto on":
                    auto_recommend = True
                    print("✅ Auto-recommendations enabled")
                elif cmd == "auto off":
                    auto_recommend = False
                    print("✅ Auto-recommendations disabled")

                elif cmd in ["help", "h", "?"]:
                    _show_tournament_help()

                elif cmd == "":
                    continue

                else:
                    print(f"❌ Unknown command: '{cmd}'. Type 'help' for available commands.")

            except KeyboardInterrupt:
                print("\n\n👋 Exiting tournament coach...")
                break
            except Exception as e:
                print(f"❌ Error: {e}")
                if "--debug" in sys.argv:
                    import traceback

                    traceback.print_exc()

        assistant.close()
        print("\n✅ Tournament coaching session ended!")

    except Exception as e:
        print(f"❌ Tournament coaching error: {e}")
        import traceback

        traceback.print_exc()


def _handle_import_command(cmd, assistant, ally_team, enemy_team, banned_champions, draft_history):
    """Handle import commands for quick draft entry."""
    import time

    try:
        # Format: import ally: Aatrox, Jax, Ahri
        if ":" not in cmd:
            print("⚠️ Import format: import <type>: <champion1>, <champion2>, ...")
            print("   Example: import ally: Aatrox, Graves, Ahri")
            return

        parts = cmd.split(":", 1)
        cmd_part = parts[0].strip().lower()
        champs_part = parts[1].strip()

        target_type = cmd_part.replace("import ", "").strip()

        if target_type not in ["ally", "enemy", "bans", "ban"]:
            print(f"⚠️ Unknown import type: {target_type}. Use: ally, enemy, or bans")
            return

        # Parse champion names
        champ_names = [c.strip() for c in champs_part.split(",")]

        imported = 0
        for champ_input in champ_names:
            champ = assistant.validate_champion_name(champ_input)
            if not champ:
                continue

            if target_type == "ally":
                if champ not in ally_team and len(ally_team) < 5:
                    ally_team.append(champ)
                    draft_history.append((time.time(), "ally", champ, "ally"))
                    imported += 1
            elif target_type == "enemy":
                if champ not in enemy_team and len(enemy_team) < 5:
                    enemy_team.append(champ)
                    draft_history.append((time.time(), "enemy", champ, "enemy"))
                    imported += 1
            elif target_type in ["bans", "ban"]:
                if champ not in banned_champions:
                    banned_champions.append(champ)
                    draft_history.append((time.time(), "ban", champ, "ban"))
                    imported += 1

        print(f"✅ Imported {imported}/{len(champ_names)} champions to {target_type}")

    except Exception as e:
        print(f"❌ Import error: {e}")


def _export_draft(ally_team, enemy_team, banned_champions, pool_name):
    """Export draft to JSON file."""
    import json
    import time
    from datetime import datetime

    timestamp = int(time.time())
    filename = f"draft_{timestamp}.json"

    draft_data = {
        "timestamp": timestamp,
        "datetime": datetime.fromtimestamp(timestamp).isoformat(),
        "pool": pool_name,
        "ally_team": ally_team,
        "enemy_team": enemy_team,
        "banned_champions": banned_champions,
        "version": "1.0",
    }

    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(draft_data, f, indent=2, ensure_ascii=False)
        print(f"✅ Draft exported to: {filename}")
    except Exception as e:
        print(f"❌ Export failed: {e}")
