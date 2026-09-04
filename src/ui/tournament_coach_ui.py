"""Menu 4, option 2 -- coach de draft de tournoi (saisie manuelle pick/ban).

Extrait de src/ui/lol_coach_legacy.py (SPEC-07 E9).
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
    """Coaching manuel de draft pour les scénarios de tournoi."""
    clear_console()  # Efface la console au démarrage
    print("[INFO] Coach de draft de tournoi")
    print(
        "Parfait pour les tournois externes, les scrims, ou tout draft en dehors du client League"
    )
    print("\nCet outil fournit la même logique de coaching que le coach en temps réel,")
    print("mais permet de saisir manuellement les informations de pick/ban.")

    try:
        from src.tournament_coach import TournamentCoach

        coach = TournamentCoach()
        coach.start_coaching_session()

    except ImportError:
        # Si le module n'existe pas encore, crée une implémentation basique
        print("\n[INFO] Démarrage de la session de coaching de tournoi...")
        _run_basic_tournament_coach()
    except Exception as e:
        print(f"[ERROR] Erreur du coach de tournoi : {e}")


def _run_basic_tournament_coach():
    """Implémentation enrichie du coaching de tournoi avec toutes les fonctionnalités."""
    from src.assistant import Assistant
    from src.pool_manager import PoolManager
    import time
    import json

    try:
        assistant = Assistant()

        # Sélectionne la pool de coaching
        print("\n" + "=" * 60)
        print("SÉLECTIONNER LA POOL DE CHAMPIONS POUR LE COACHING")
        print("=" * 60)

        selected_pool_info = _select_pool_for_analysis()
        if not selected_pool_info:
            print(
                "[WARNING] Aucune pool sélectionnée, utilisation de la pool étendue de l'assistant"
            )
            champion_pool = assistant.select_extended_champion_pool()
            pool_name = "Pool étendue"
        else:
            pool_name, champion_pool, _pool_lane = selected_pool_info

        print(f"\nUtilisation de la pool : {pool_name} ({len(champion_pool)} champions)")

        # Initialise l'état du draft
        ally_team = []
        enemy_team = []
        banned_champions = []
        draft_history = []  # (timestamp, action, champion, side)
        auto_recommend = True  # Affiche automatiquement les recommandations après chaque pick

        print("\n" + "=" * 80)
        print("SESSION DE COACHING DE DRAFT DE TOURNOI")
        print("=" * 80)
        _show_tournament_help()

        while True:
            try:
                cmd = input("\nCoach > ").strip().lower()

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
                    print("État du draft réinitialisé !")

                elif cmd == "recommend":
                    _show_recommendations(
                        assistant, enemy_team, ally_team, banned_champions, champion_pool, 5
                    )

                elif cmd == "analyze":
                    if len(ally_team) == 5 and len(enemy_team) == 5:
                        _analyze_complete_draft(assistant, ally_team, enemy_team)
                    else:
                        print(
                            f"Draft incomplet : {len(ally_team)}/5 alliés, {len(enemy_team)}/5 adverses"
                        )

                elif cmd.startswith("ally "):
                    champ_input = cmd[5:].strip()
                    champ = assistant.validate_champion_name(champ_input)
                    if champ:
                        if champ in ally_team:
                            print(f"{champ} est déjà dans votre équipe")
                        elif champ in enemy_team:
                            print(f"{champ} est déjà pris par l'adversaire")
                        elif champ in banned_champions:
                            print(f"{champ} est banni")
                        elif len(ally_team) >= 5:
                            print(f"Votre équipe est complète (5/5)")
                        else:
                            ally_team.append(champ)
                            draft_history.append((time.time(), "ally", champ, "ally"))
                            print(f"{champ} ajouté à votre équipe ({len(ally_team)}/5)")
                            if auto_recommend and enemy_team:
                                print(f"\nMeilleurs picks après l'ajout de {champ} :")
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
                            print(f"{champ} est déjà dans l'équipe adverse")
                        elif champ in ally_team:
                            print(f"{champ} est déjà pris par vous")
                        elif champ in banned_champions:
                            print(f"{champ} est banni")
                        elif len(enemy_team) >= 5:
                            print(f"L'équipe adverse est complète (5/5)")
                        else:
                            enemy_team.append(champ)
                            draft_history.append((time.time(), "enemy", champ, "enemy"))
                            print(f"L'adversaire a pick {champ} ({len(enemy_team)}/5)")
                            if auto_recommend:
                                print(f"\nMeilleurs counters à {champ} :")
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
                            print(f"{champ} déjà banni")
                        elif champ in ally_team or champ in enemy_team:
                            print(f"{champ} déjà pick")
                        else:
                            banned_champions.append(champ)
                            draft_history.append((time.time(), "ban", champ, "ban"))
                            print(f"{champ} banni")

                elif cmd.startswith("remove ally "):
                    champ_input = cmd[12:].strip()
                    champ = assistant.validate_champion_name(champ_input)
                    if champ and champ in ally_team:
                        ally_team.remove(champ)
                        draft_history.append((time.time(), "remove_ally", champ, "ally"))
                        print(f"{champ} retiré de votre équipe")
                    else:
                        print(f"{champ_input} n'est pas dans votre équipe")

                elif cmd.startswith("remove enemy "):
                    champ_input = cmd[13:].strip()
                    champ = assistant.validate_champion_name(champ_input)
                    if champ and champ in enemy_team:
                        enemy_team.remove(champ)
                        draft_history.append((time.time(), "remove_enemy", champ, "enemy"))
                        print(f"{champ} retiré de l'équipe adverse")
                    else:
                        print(f"{champ_input} n'est pas dans l'équipe adverse")

                elif cmd.startswith("remove ban "):
                    champ_input = cmd[11:].strip()
                    champ = assistant.validate_champion_name(champ_input)
                    if champ and champ in banned_champions:
                        banned_champions.remove(champ)
                        draft_history.append((time.time(), "unban", champ, "ban"))
                        print(f"{champ} débanni")
                    else:
                        print(f"{champ_input} n'est pas dans la liste des bans")

                elif cmd == "history":
                    _show_draft_history(draft_history)

                elif cmd == "undo":
                    if draft_history:
                        ts, action, champ, side = draft_history.pop()
                        if action == "ally":
                            ally_team.remove(champ)
                            print(f"Annulé : {champ} retiré de l'équipe alliée")
                        elif action == "enemy":
                            enemy_team.remove(champ)
                            print(f"Annulé : {champ} retiré de l'équipe adverse")
                        elif action == "ban":
                            banned_champions.remove(champ)
                            print(f"Annulé : {champ} débanni")
                        elif action.startswith("remove"):
                            # Impossible d'annuler facilement les retraits, on passe
                            print(f"Impossible d'annuler une action de retrait")
                    else:
                        print("Aucune action à annuler")

                elif cmd.startswith("import "):
                    _handle_import_command(
                        cmd, assistant, ally_team, enemy_team, banned_champions, draft_history
                    )

                elif cmd == "export":
                    _export_draft(ally_team, enemy_team, banned_champions, pool_name)

                elif cmd == "auto on":
                    auto_recommend = True
                    print("Recommandations automatiques activées")
                elif cmd == "auto off":
                    auto_recommend = False
                    print("Recommandations automatiques désactivées")

                elif cmd in ["help", "h", "?"]:
                    _show_tournament_help()

                elif cmd == "":
                    continue

                else:
                    print(
                        f"Commande inconnue : '{cmd}'. Tapez 'help' pour voir les commandes disponibles."
                    )

            except KeyboardInterrupt:
                print("\n\nSortie du coach de tournoi...")
                break
            except Exception as e:
                print(f"Erreur : {e}")
                if "--debug" in sys.argv:
                    import traceback

                    traceback.print_exc()

        assistant.close()
        print("\nSession de coaching de tournoi terminée !")

    except Exception as e:
        print(f"Erreur du coach de tournoi : {e}")
        import traceback

        traceback.print_exc()


def _handle_import_command(cmd, assistant, ally_team, enemy_team, banned_champions, draft_history):
    """Gère les commandes d'import pour une saisie rapide du draft."""
    import time

    try:
        # Format : import ally: Aatrox, Jax, Ahri
        if ":" not in cmd:
            print("Format d'import : import <type>: <champion1>, <champion2>, ...")
            print("   Exemple : import ally: Aatrox, Graves, Ahri")
            return

        parts = cmd.split(":", 1)
        cmd_part = parts[0].strip().lower()
        champs_part = parts[1].strip()

        target_type = cmd_part.replace("import ", "").strip()

        if target_type not in ["ally", "enemy", "bans", "ban"]:
            print(f"Type d'import inconnu : {target_type}. Utilisez : ally, enemy ou bans")
            return

        # Parse les noms de champions
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

        print(f"{imported}/{len(champ_names)} champions importés dans {target_type}")

    except Exception as e:
        print(f"Erreur d'import : {e}")


def _export_draft(ally_team, enemy_team, banned_champions, pool_name):
    """Exporte le draft dans un fichier JSON."""
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
        print(f"Draft exporté vers : {filename}")
    except Exception as e:
        print(f"Échec de l'export : {e}")
