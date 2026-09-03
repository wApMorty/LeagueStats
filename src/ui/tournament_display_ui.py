"""Aides d'affichage/formatage pour le coach de draft de tournoi.

Extrait de src/ui/lol_coach_legacy.py (SPEC-07 E9). Utilisé par la boucle
de commandes interactive de src/ui/tournament_coach_ui.py.
"""


def _show_tournament_help():
    """Affiche l'aide du coach de tournoi."""
    print("\nCOMMANDES DU COACH DE TOURNOI")
    print("=" * 60)
    print("GESTION DU DRAFT :")
    print("  ally <champion>          - Ajoute un champion à votre équipe")
    print("  enemy <champion>         - Ajoute un champion à l'équipe adverse")
    print("  ban <champion>           - Ajoute un champion à la liste des bans")
    print("  remove ally/enemy/ban <champion> - Retire un champion")
    print()
    print("ANALYSE :")
    print("  status                   - Affiche l'état actuel du draft avec les scores")
    print("  recommend                - Obtient des recommandations de champions")
    print("  analyze                  - Analyse complète (quand les deux équipes sont complètes)")
    print("  history                  - Affiche l'historique des actions du draft")
    print()
    print("UTILITAIRES :")
    print("  undo                     - Annule la dernière action")
    print("  reset                    - Efface tout le draft")
    print("  auto on/off              - Active/désactive les recommandations automatiques")
    print("  export                   - Sauvegarde le draft dans un fichier JSON")
    print("  import <type>: <champs>  - Import rapide (voir exemples ci-dessous)")
    print()
    print("  help, h, ?               - Affiche cette aide")
    print("  quit, exit, q            - Quitte le coach")
    print()
    print("EXEMPLES D'IMPORT :")
    print("  import ally: Aatrox, Graves, Ahri")
    print("  import enemy: Gwen, Lee Sin, Syndra")
    print("  import bans: Yone, Yasuo, Zed")
    print("=" * 60)


def _show_tournament_draft_state(assistant, ally_team, enemy_team, banned_champions, champion_pool):
    """Affiche l'état enrichi du draft de tournoi avec les scores individuels des champions."""
    print(f"\n" + "=" * 70)
    print("ÉTAT ACTUEL DU DRAFT")
    print("=" * 70)

    # Affiche les équipes avec les scores individuels
    print(f"\nVOTRE ÉQUIPE ({len(ally_team)}/5) :")
    if ally_team:
        for champ in ally_team:
            matchups = assistant.db.get_champion_matchups_by_name(champ)
            if matchups and enemy_team:
                other_allies = [a for a in ally_team if a != champ]
                advantage = assistant.score_with_synergy(matchups, enemy_team, other_allies, champ)
                if advantage >= 2.0:
                    status = "Fort"
                elif advantage >= 0:
                    status = "Bon"
                else:
                    status = "Faible"
                print(f"  • {champ:<15} {status:>10}  ({advantage:+.2f}%)")
            else:
                print(f"  • {champ:<15}")
    else:
        print("  (Aucun pick pour le moment)")

    print(f"\nÉQUIPE ADVERSE ({len(enemy_team)}/5) :")
    if enemy_team:
        for champ in enemy_team:
            print(f"  • {champ}")
    else:
        print("  (Aucun pick pour le moment)")

    print(f"\nCHAMPIONS BANNIS ({len(banned_champions)}) :")
    if banned_champions:
        print(f"  {', '.join(banned_champions)}")
    else:
        print("  (Aucun)")

    # Affiche la progression
    remaining_ally = 5 - len(ally_team)
    remaining_enemy = 5 - len(enemy_team)
    print(f"\nPICKS RESTANTS :")
    print(f"  Vous : {remaining_ally}  |  Adversaire : {remaining_enemy}")

    # Affiche l'estimation du winrate si les deux équipes ont des picks
    if len(ally_team) >= 3 and len(enemy_team) >= 3:
        print(f"\nAVANTAGE DU DRAFT :")
        ally_advantages = []
        for champ in ally_team:
            matchups = assistant.db.get_champion_matchups_by_name(champ)
            if matchups:
                other_allies = [a for a in ally_team if a != champ]
                adv = assistant.score_with_synergy(matchups, enemy_team, other_allies, champ)
                ally_advantages.append(adv)

        if ally_advantages:
            avg_advantage = sum(ally_advantages) / len(ally_advantages)
            if avg_advantage >= 2.0:
                print(f"  Avantage fort ({avg_advantage:+.2f}% en moyenne)")
            elif avg_advantage >= 0:
                print(f"  Léger avantage ({avg_advantage:+.2f}% en moyenne)")
            else:
                print(f"  Désavantage ({avg_advantage:+.2f}% en moyenne)")

    print("=" * 70)


def _show_recommendations(
    assistant, enemy_team, ally_team, banned_champions, champion_pool, nb_results
):
    """Affiche les recommandations formatées."""
    if not enemy_team and not ally_team:
        print(
            "Aucun pick pour le moment. Ajoutez d'abord les picks adverses pour des "
            "recommandations pertinentes."
        )
        return

    print(f"\nTOP {nb_results} RECOMMANDATIONS :")
    print("-" * 50)
    assistant._calculate_and_display_recommendations(
        enemy_team, ally_team, nb_results, champion_pool, banned_champions
    )


def _show_draft_history(draft_history):
    """Affiche l'historique des actions du draft."""
    if not draft_history:
        print("Aucune action pour le moment")
        return

    print(f"\nHISTORIQUE DU DRAFT ({len(draft_history)} actions) :")
    print("-" * 60)
    for i, (ts, action, champ, side) in enumerate(draft_history, 1):
        print(f"  {i:2}. {action.upper():<12} {champ}")


def _analyze_complete_draft(assistant, ally_team, enemy_team):
    """Analyse le draft complet avec la même logique que le draft monitor."""
    print("\n" + "=" * 80)
    print("ANALYSE COMPLÈTE DU DRAFT")
    print("=" * 80)

    # Calcule les scores individuels
    ally_scores = []
    for champ in ally_team:
        matchups = assistant.db.get_champion_matchups_by_name(champ)
        if matchups:
            other_allies = [a for a in ally_team if a != champ]
            advantage = assistant.score_with_synergy(matchups, enemy_team, other_allies, champ)
            ally_scores.append((champ, advantage))
        else:
            ally_scores.append((champ, None))

    enemy_scores = []
    for champ in enemy_team:
        matchups = assistant.db.get_champion_matchups_by_name(champ)
        if matchups:
            other_enemies = [e for e in enemy_team if e != champ]
            advantage = assistant.score_with_synergy(matchups, ally_team, other_enemies, champ)
            enemy_scores.append((champ, advantage))
        else:
            enemy_scores.append((champ, None))

    # Trie par avantage
    ally_scores.sort(key=lambda x: x[1] if x[1] is not None else -999, reverse=True)
    enemy_scores.sort(key=lambda x: x[1] if x[1] is not None else -999, reverse=True)

    # Affiche l'équipe alliée
    print(f"\nPERFORMANCE DE VOTRE ÉQUIPE :")
    print("-" * 60)
    for champ, advantage in ally_scores:
        if advantage is None:
            print(f"  {champ:<15} | Données insuffisantes")
        elif advantage >= 2.0:
            print(f"  {champ:<15} | {advantage:+.2f}% (Excellent)")
        elif advantage >= 1.0:
            print(f"  {champ:<15} | {advantage:+.2f}% (Bon)")
        elif advantage >= -1.0:
            print(f"  {champ:<15} | {advantage:+.2f}% (Neutre)")
        elif advantage >= -2.0:
            print(f"  {champ:<15} | {advantage:.2f}% (Mauvais)")
        else:
            print(f"  {champ:<15} | {advantage:.2f}% (Très mauvais)")

    # Affiche l'équipe adverse
    print(f"\nPERFORMANCE DE L'ÉQUIPE ADVERSE :")
    print("-" * 60)
    for champ, advantage in enemy_scores:
        if advantage is None:
            print(f"  {champ:<15} | Données insuffisantes")
        elif advantage >= 2.0:
            print(f"  {champ:<15} | {advantage:+.2f}% (Fort contre nous)")
        elif advantage >= 1.0:
            print(f"  {champ:<15} | {advantage:+.2f}% (Bon contre nous)")
        elif advantage >= -1.0:
            print(f"  {champ:<15} | {advantage:+.2f}% (Neutre)")
        elif advantage >= -2.0:
            print(f"  {champ:<15} | {advantage:.2f}% (Faible contre nous)")
        else:
            print(f"  {champ:<15} | {advantage:.2f}% (Très faible contre nous)")

    # Calcul du winrate d'équipe par moyenne géométrique
    ally_valid = [adv for _, adv in ally_scores if adv is not None]
    enemy_valid = [adv for _, adv in enemy_scores if adv is not None]

    if ally_valid and enemy_valid:
        print(f"\nPRÉDICTION DU MATCHUP D'ÉQUIPE :")
        print("-" * 60)

        # Convertit en winrates et utilise la moyenne géométrique
        ally_winrates = [50.0 + adv for adv in ally_valid]
        enemy_winrates = [50.0 + adv for adv in enemy_valid]

        ally_team_stats = assistant._calculate_team_winrate(ally_winrates)
        enemy_team_stats = assistant._calculate_team_winrate(enemy_winrates)

        # Normalise à 100 %
        total = ally_team_stats["team_winrate"] + enemy_team_stats["team_winrate"]
        ally_normalized = (ally_team_stats["team_winrate"] / total) * 100
        enemy_normalized = (enemy_team_stats["team_winrate"] / total) * 100

        print(f"  Votre équipe :   {ally_normalized:.1f}%")
        print(f"  Équipe adverse : {enemy_normalized:.1f}%")

        diff = ally_normalized - enemy_normalized
        if diff >= 5.0:
            print(f"\n  Avantage majeur ({diff:+.1f}%)")
        elif diff >= 2.5:
            print(f"\n  Bon avantage ({diff:+.1f}%)")
        elif diff >= -2.5:
            print(f"\n  Matchup équilibré ({diff:+.1f}%)")
        elif diff >= -5.0:
            print(f"\n  Désavantage ({diff:.1f}%)")
        else:
            print(f"\n  Désavantage majeur ({diff:.1f}%)")

    print("\n" + "=" * 80)
