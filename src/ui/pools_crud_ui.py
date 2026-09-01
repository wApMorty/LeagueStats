"""Menu 6 -- CRUD des pools de champions (créer/modifier/supprimer/dupliquer).

Extrait de src/ui/lol_coach_legacy.py (SPEC-07 E9). Le menu de premier niveau
des pools ainsi que le listing/les statistiques se trouvent dans
src/ui/pools_menu_ui.py.
"""

from src.ui.pool_selection_ui import _select_pool_interactive


def create_new_pool(pool_manager, available_champions):
    """Crée une nouvelle pool de champions."""
    from src.pool_manager import validate_champion_name, suggest_champions

    print("\n" + "=" * 50)
    print("CRÉER UNE NOUVELLE POOL")
    print("=" * 50)

    name = input("Nom de la pool : ").strip()
    if not name:
        print("[ERROR] Le nom de la pool ne peut pas être vide.")
        return

    if pool_manager.get_pool(name):
        print(f"[ERROR] La pool '{name}' existe déjà.")
        return

    description = input("Description (optionnel) : ").strip()
    role = input("Rôle (top/jungle/mid/adc/support/custom) : ").strip().lower()
    if role not in ["top", "jungle", "mid", "adc", "support", "custom"]:
        role = "custom"

    # Tags
    tags_input = input("Tags (séparés par des virgules, optionnel) : ").strip()
    tags = [tag.strip() for tag in tags_input.split(",") if tag.strip()] if tags_input else []

    print("\nAjoutez des champions à la pool :")
    print("  - Entrez les noms de champions un par un")
    print("  - Tapez 'done' pour terminer")
    print("  - Tapez 'list' pour voir des suggestions")

    champions = []
    while True:
        champ_input = input(f"Champion {len(champions)+1} (ou 'done'/'list') : ").strip()

        if champ_input.lower() == "done":
            break
        elif champ_input.lower() == "list":
            print(
                "Champions disponibles :",
                ", ".join(sorted(list(available_champions)[:20])) + "...",
            )
            continue

        # Suggestion automatique en cas de correspondance partielle
        if champ_input and not validate_champion_name(champ_input, available_champions):
            suggestions = suggest_champions(champ_input, available_champions)
            if suggestions:
                print(f"Vouliez-vous dire : {', '.join(suggestions)}")
                continue
            else:
                print(f"[WARNING] Champion '{champ_input}' introuvable.")
                continue

        if champ_input and champ_input not in champions:
            champions.append(champ_input)
            print(f"  Ajouté : {champ_input}")
        elif champ_input in champions:
            print(f"  Déjà dans la pool : {champ_input}")

    if not champions:
        print("[ERROR] Impossible de créer une pool vide.")
        return

    if pool_manager.create_pool(name, champions, description, role, tags):
        print(f"[SUCCESS] Pool '{name}' créée avec {len(champions)} champions !")
    else:
        print(f"[ERROR] Échec de la création de la pool '{name}'.")


def edit_pool(pool_manager, available_champions):
    """Modifie une pool existante."""
    from src.pool_manager import validate_champion_name, suggest_champions

    # Sélectionne la pool de manière interactive
    pool = _select_pool_interactive(pool_manager, "Modifier une pool")
    if not pool:
        return

    if pool.created_by == "system":
        print(f"[ERROR] Impossible de modifier la pool système '{pool.name}'.")
        return

    while True:
        # Affiche l'état actuel de la pool
        print(f"\n" + "=" * 60)
        print(f"MODIFICATION DE LA POOL : {pool.name}")
        print("=" * 60)
        print(f"Rôle : {pool.role} | Description : {pool.description}")
        print(f"Tags : {', '.join(pool.tags) if pool.tags else 'Aucun'}")
        print(f"Champions actuels ({pool.size()}) :")

        # Affiche les champions en format compact
        champions = pool.champions
        if champions:
            cols = 4
            for i in range(0, len(champions), cols):
                row = champions[i : i + cols]
                print(f"  {' | '.join(f'{champ:<12}' for champ in row)}")
        else:
            print("  [Aucun champion dans la pool]")

        menu = """
Options de modification :
  1. Ajouter un champion
  2. Retirer un champion
  3. Modifier la description
  4. Modifier le rôle
  5. Modifier les tags
  6. Retour au menu des pools

Choisissez une option (1-6) : """

        choice = input(menu).strip()

        if choice == "1":
            print(f"\nAjout d'un champion à '{pool.name}'")
            champ = input("Champion à ajouter : ").strip()
            if champ:
                if validate_champion_name(champ, available_champions):
                    if pool.add_champion(champ):
                        print(f"[SUCCESS] {champ} ajouté à {pool.name}")
                    else:
                        print(f"[INFO] {champ} est déjà dans la pool")
                else:
                    suggestions = suggest_champions(champ, available_champions)
                    if suggestions:
                        print(
                            f"[ERROR] Champion introuvable. Suggestions : {', '.join(suggestions)}"
                        )
                    else:
                        print(f"[ERROR] Champion '{champ}' introuvable.")

        elif choice == "2":
            if not pool.champions:
                print("[INFO] La pool est vide, aucun champion à retirer.")
                continue

            print(f"\nRetrait d'un champion de '{pool.name}'")
            print("Champions actuels :")
            for i, champ in enumerate(pool.champions, 1):
                print(f"  {i}. {champ}")

            try:
                remove_choice = input("\nRetirer par numéro ou par nom : ").strip()

                # Essaie d'abord comme un numéro
                if remove_choice.isdigit():
                    idx = int(remove_choice) - 1
                    if 0 <= idx < len(pool.champions):
                        champ_to_remove = pool.champions[idx]
                        pool.remove_champion(champ_to_remove)
                        print(f"[SUCCESS] {champ_to_remove} retiré de {pool.name}")
                    else:
                        print("[ERROR] Numéro invalide.")
                else:
                    # Essaie comme un nom
                    if pool.remove_champion(remove_choice):
                        print(f"[SUCCESS] {remove_choice} retiré de {pool.name}")
                    else:
                        print(f"[ERROR] {remove_choice} introuvable dans la pool")
            except ValueError:
                print("[ERROR] Entrée invalide.")

        elif choice == "3":
            print(f"\nModification de la description de '{pool.name}'")
            print(f"Actuelle : {pool.description}")
            new_desc = input(
                "Nouvelle description (ou Entrée pour conserver l'actuelle) : "
            ).strip()
            if new_desc:
                pool.description = new_desc
                print("[SUCCESS] Description mise à jour")

        elif choice == "4":
            print(f"\nModification du rôle de '{pool.name}'")
            print(f"Actuel : {pool.role}")
            print("Rôles disponibles : top, jungle, mid, adc, support, custom")
            new_role = input("Nouveau rôle : ").strip().lower()
            if new_role in ["top", "jungle", "mid", "adc", "support", "custom"]:
                pool.role = new_role
                print("[SUCCESS] Rôle mis à jour")
            elif new_role:
                print("[ERROR] Rôle invalide")

        elif choice == "5":
            print(f"\nModification des tags de '{pool.name}'")
            print(f"Actuels : {', '.join(pool.tags) if pool.tags else 'Aucun'}")
            tags_input = input(
                "Nouveaux tags (séparés par des virgules, ou Entrée pour effacer) : "
            ).strip()
            pool.tags = (
                [tag.strip() for tag in tags_input.split(",") if tag.strip()] if tags_input else []
            )
            print("[SUCCESS] Tags mis à jour")

        elif choice == "6":
            break

        else:
            print("[ERROR] Option invalide. Choisissez 1-6.")


def delete_pool(pool_manager):
    """Supprime une pool."""
    # Ne montre que les pools personnalisées pour la suppression
    custom_pools = {
        name: pool
        for name, pool in pool_manager.get_all_pools().items()
        if pool.created_by == "user"
    }

    if not custom_pools:
        print("[INFO] Aucune pool personnalisée disponible à la suppression.")
        return

    print(f"\n" + "=" * 50)
    print("SUPPRIMER UNE POOL")
    print("=" * 50)
    print("Pools personnalisées disponibles pour suppression :")

    pool_list = []
    idx = 1
    for name, pool in sorted(custom_pools.items()):
        pool_list.append((name, pool))
        print(
            f"  {idx:>2}. {name:<20} | {pool.role:<8} | {pool.size():>2} champs | {pool.description}"
        )
        idx += 1

    try:
        choice = input(
            f"\nChoisissez la pool à supprimer (1-{len(pool_list)} ou 'cancel') : "
        ).strip()

        if choice.lower() == "cancel":
            return

        choice_num = int(choice)
        if 1 <= choice_num <= len(pool_list):
            selected_name, selected_pool = pool_list[choice_num - 1]

            # Affiche les détails de la pool avant confirmation
            print(f"\nSur le point de supprimer :")
            print(f"  Pool : {selected_name}")
            print(f"  Champions : {', '.join(selected_pool.champions)}")

            confirm = (
                input(f"\nÊtes-vous sûr de vouloir supprimer '{selected_name}' ? (y/N) : ")
                .strip()
                .lower()
            )
            if confirm == "y":
                if pool_manager.delete_pool(selected_name):
                    print(f"[SUCCESS] Pool '{selected_name}' supprimée")
                else:
                    print(f"[ERROR] Échec de la suppression de la pool '{selected_name}'")
        else:
            print(f"[ERROR] Choix invalide. Choisissez entre 1 et {len(pool_list)}.")

    except ValueError:
        print("[ERROR] Entrée invalide. Veuillez entrer un numéro.")


def duplicate_pool(pool_manager):
    """Duplique une pool existante."""
    source_pool = _select_pool_interactive(pool_manager, "Dupliquer une pool")
    if not source_pool:
        return

    print(f"\nDuplication de la pool '{source_pool.name}'")
    new_name = input("Entrez le nom de la nouvelle pool : ").strip()

    if not new_name:
        print("[ERROR] Le nom de la nouvelle pool ne peut pas être vide.")
        return

    if pool_manager.duplicate_pool(source_pool.name, new_name):
        print(f"[SUCCESS] '{source_pool.name}' dupliquée sous le nom '{new_name}'")

        # Affiche les infos de la nouvelle pool
        new_pool = pool_manager.get_pool(new_name)
        if new_pool:
            print(
                f"Nouvelle pool créée avec {new_pool.size()} champions : {', '.join(new_pool.champions)}"
            )
    else:
        print("[ERROR] Échec de la duplication de la pool (le nom existe peut-être déjà)")
