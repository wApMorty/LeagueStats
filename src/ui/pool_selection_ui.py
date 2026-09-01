"""Fonctions d'aide interactives pour la sélection de pool, partagées entre les modules de menu.

Extrait de src/ui/lol_coach_legacy.py (SPEC-07 E9) : ces trois fonctions
étaient définies dans le fichier legacy mais déjà utilisées par plusieurs
domaines de menu différents (mise à jour des données, tier list, coach de
tournoi, constructeur d'équipe, gestion des pools), elles vivent donc ici
plutôt que dans un seul module de menu.
"""


def _select_pool_for_analysis():
    """Sélectionne une pool pour l'analyse de composition d'équipe, avec interface améliorée."""
    try:
        from src.pool_manager import PoolManager

        pool_manager = PoolManager()

        pools = pool_manager.get_all_pools()
        if not pools:
            print("[ERROR] Aucune pool trouvée.")
            return None

        print(f"\n" + "=" * 50)
        print("SÉLECTIONNER UNE POOL POUR L'ANALYSE")
        print("=" * 50)
        print("Pools disponibles pour l'analyse :")

        # Créer une liste numérotée
        pool_list = []
        idx = 1
        for name, pool in sorted(pools.items()):
            pool_list.append((name, pool))
            status = "[SYS]" if pool.created_by == "system" else "[PER]"
            suitable = (
                "[REC]" if pool.size() >= 5 else "[PTT]"
            )  # Indicateur de pertinence pour l'analyse
            print(
                f"  {idx:>2}. {status}{suitable} {name:<18} | {pool.role:<8} | {pool.size():>2} champs | {pool.description}"
            )
            idx += 1

        print(f"\n  {idx}. Utiliser le sélecteur de pool étendu de l'Assistant (legacy)")
        print("\n[REC] = Recommandé pour l'analyse (5+ champions)")
        print("[PTT] = Pool réduite (analyse potentiellement limitée)")

        try:
            choice = input(f"\nChoisissez une pool (1-{idx} ou 'cancel') : ").strip()

            if choice.lower() == "cancel":
                return None

            choice_num = int(choice)
            if 1 <= choice_num <= len(pool_list):
                selected_name, selected_pool = pool_list[choice_num - 1]
                return (selected_name, selected_pool.champions)
            elif choice_num == idx:
                # Repli legacy
                return None
            else:
                print(f"[ERROR] Choix invalide. Veuillez choisir 1-{idx}.")
                return None

        except ValueError:
            print("[ERROR] Entrée invalide. Veuillez entrer un nombre.")
            return None

    except Exception as e:
        print(f"[WARNING] Erreur de sélection de pool : {e}")
        return None


def _select_pool_for_parsing():
    """Sélectionne une pool pour l'analyse de statistiques, avec interface améliorée."""
    try:
        from src.pool_manager import PoolManager

        pool_manager = PoolManager()

        pools = pool_manager.get_all_pools()
        if not pools:
            print("[ERROR] Aucune pool trouvée.")
            return None

        print(f"\n" + "=" * 50)
        print("SÉLECTIONNER UNE POOL POUR L'ANALYSE DE STATISTIQUES")
        print("=" * 50)
        print("Pools disponibles pour l'analyse de statistiques :")

        # Créer une liste numérotée
        pool_list = []
        idx = 1
        for name, pool in sorted(pools.items()):
            pool_list.append((name, pool))
            status = "[SYS]" if pool.created_by == "system" else "[PER]"
            time_est = f"~{pool.size()*0.5:.2f}-{pool.size()*1:.2f}min"
            print(
                f"  {idx:>2}. {status} {name:<18} | {pool.role:<8} | {pool.size():>2} champs | {time_est:>8} | {pool.description}"
            )
            idx += 1

        print(f"\n  {idx}. Analyser TOUS les champions (analyse étendue - ~60-90 min)")
        print(f"  {idx+1}. Utiliser la pool Top SoloQ (par défaut - ~2-3 min)")

        try:
            choice = input(f"\nChoisissez une pool (1-{idx+1} ou 'cancel') : ").strip()

            if choice.lower() == "cancel":
                return None

            choice_num = int(choice)
            if 1 <= choice_num <= len(pool_list):
                selected_name, selected_pool = pool_list[choice_num - 1]
                return (selected_name, selected_pool.champions)
            elif choice_num == idx:
                # Option tous les champions
                from src.constants import CHAMPIONS_LIST

                return ("ALL CHAMPIONS", list(CHAMPIONS_LIST))
            elif choice_num == idx + 1:
                # Top SoloQ par défaut
                return None
            else:
                print(f"[ERROR] Choix invalide. Veuillez choisir 1-{idx+1}.")
                return None

        except ValueError:
            print("[ERROR] Entrée invalide. Veuillez entrer un nombre.")
            return None

    except Exception as e:
        print(f"[WARNING] Erreur de sélection de pool : {e}")
        return None


def _select_pool_interactive(pool_manager, action_name="Sélectionner une pool"):
    """Sélection de pool interactive avec choix numérotés."""
    from src.utils.display import safe_print

    pools = pool_manager.get_all_pools()
    if not pools:
        print("[ERROR] Aucune pool trouvée.")
        return None

    print(f"\n" + "=" * 50)
    print(f"{action_name.upper()}")
    print("=" * 50)
    print("Pools disponibles :")

    # Créer une liste numérotée
    pool_list = []
    idx = 1
    for name, pool in sorted(pools.items()):
        pool_list.append((name, pool))
        status = "[SYS]" if pool.created_by == "system" else "[PER]"
        safe_print(
            f"  {idx:>2}. {status} {name:<20} | {pool.role:<8} | {pool.size():>2} champs | {pool.description}"
        )
        idx += 1

    try:
        choice = input(f"\nChoisissez une pool (1-{len(pool_list)} ou 'cancel') : ").strip()

        if choice.lower() == "cancel":
            return None

        choice_num = int(choice)
        if 1 <= choice_num <= len(pool_list):
            selected_name, selected_pool = pool_list[choice_num - 1]
            return selected_pool
        else:
            print(f"[ERROR] Choix invalide. Veuillez choisir 1-{len(pool_list)}.")
            return None

    except ValueError:
        print("[ERROR] Entrée invalide. Veuillez entrer un nombre.")
        return None
