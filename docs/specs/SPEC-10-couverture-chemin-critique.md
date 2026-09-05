# SPEC-10 — Couverture du chemin critique temps réel

**Chantier** : C (priorité 3) · **Effort** : ~1 jour · **Prérequis** : idéalement après SPEC-08 (qui ajoute du code dans `lcu_client.py`) · **Bloque** : rien

**Nature du chantier** : c'est de l'**assurance**, pas de la valeur utilisateur. À faire après A et B, mais à faire — les zones visées sont celles où une régression casse le produit en silence.

---

## 1. État mesuré (2026-09-05, 990 tests, 65,5 % global)

| Module | Couverture | Lignes non couvertes | Rôle |
|---|---|---|---|
| `src/ui/pool_selection_ui.py` | **2,6 %** | 111 / 114 | Sélection de pool et **résolution du rôle → lane** |
| `src/lcu_client.py` | **18,6 %** | 224 / 275 | Seule porte d'entrée vers le client League of Legends |
| `src/utils/champion_utils.py` | **33,3 %** | 70 / 105 | Normalisation des noms de champion (mapping LCU ↔ base) |
| `src/draft/phases.py` | **40,0 %** | 24 / 40 | Détection de la phase de ban |

Ces quatre modules forment **une chaîne continue** : le client LCU fournit l'état brut → `champion_utils` mappe les noms → `phases` décide quoi afficher → `pool_selection_ui` détermine la lane qui filtre toutes les données. Une rupture n'importe où produit un coach silencieusement faux, pas une exception.

Ce n'est pas théorique : `pool_selection_ui.py` est exactement le chemin des bugs lane de septembre 2026 (5 zones du produit, cf. `CHANGELOG.md [Unreleased]`), et sa couverture de 2,6 % explique qu'aucun test ne les ait vus venir.

## 2. Nuance sur `trio_*` / `ban_recommendations` (item P2 de `TODO.md`)

`TODO.md` les classe priorité 1. **La mesure contredit partiellement ce diagnostic** :

| Module | Couverture |
|---|---|
| `analysis/ban_recommendations.py` | 73,7 % |
| `analysis/matchup_cache.py` | 75,5 % |
| `analysis/trio_holistic.py` | 77,9 % |
| `analysis/trio_metrics.py` | 81,0 % |
| `analysis/trio_weights.py` | 86,3 % |
| `analysis/trio_counterpick.py` | 88,4 % |

Le problème n'est donc **pas la quantité** de couverture mais sa **nature** : ce sont des tests de caractérisation, qui figent le comportement observé plutôt que de spécifier le comportement attendu. Ils passent tout aussi bien quand le comportement est faux — ils n'auraient pas détecté le bug lane, et ils ne le détecteraient pas davantage aujourd'hui.

**Conséquence pour cette spec** : ajouter des tests de ligne sur ces modules n'apporterait rien. Ce qu'il faut, ce sont quelques tests **d'intention** sur les invariants métier (§3.5) — beaucoup moins nombreux, beaucoup plus utiles. `TODO.md` sera corrigé en ce sens.

---

## 3. Le travail

### 3.1 — `lcu_client.py` : cible ≥ 60 %

Tout est mockable via `requests` : `_make_request` est le point d'injection unique. Créer `tests/test_lcu_client.py` avec des payloads figés (ceux du spike de SPEC-08 si déjà fait) :

- `_make_request` : codes 200 / 204 / 404 / 500, corps vide, JSON invalide, `RequestException`, absence de credentials → chacun doit rendre la valeur documentée sans lever ;
- `find_lcu_credentials` : lockfile bien formé, lockfile absent, lockfile malformé (le repli par processus doit rester testé sur mock, jamais sur le vrai système) ;
- `get_assigned_positions` : payload complet, positions absentes (file sans rôle), lane inconnue ;
- `get_champion_id_by_name` / `_normalize_champion_name` : casse, apostrophes (`Kai'Sa`, `Cho'Gath`), espaces (`Lee Sin`), champion inconnu ;
- `hover_champion` / `lock_champion` : action introuvable, PATCH en échec → retour `False`, jamais d'exception remontée dans la boucle de draft.

**Invariant à vérifier explicitement** : aucune méthode publique de `LCUClient` ne lève quand le client est absent ou répond n'importe quoi. C'est le contrat sur lequel repose toute la boucle de monitoring.

### 3.2 — `ui/pool_selection_ui.py` : cible ≥ 60 %

Le point sensible est la résolution `ChampionPool.role` → lane, via `pool_manager.pool_role_to_lane()`. Tester :

- chaque rôle de pool connu → la bonne lane ;
- pool multi-rôle ou custom → `None` (repli toutes-lanes assumé), et **non** une lane arbitraire ;
- pool sans rôle → `None` ;
- la lane résolue est bien celle transmise au monitor (`pool_lane`).

Les fonctions d'affichage/saisie se testent en mockant `input()` et en capturant `capsys`, comme dans `tests/test_ui_menu_dispatch.py`.

### 3.3 — `utils/champion_utils.py` : cible ≥ 70 %

Module purement fonctionnel, donc peu coûteux à couvrir. Insister sur les cas qui cassent en vrai : noms à apostrophe, `Nunu & Willump`, `Renata Glasc`, `Wukong`/`MonkeyKing` (l'id Riot diffère du nom affiché), casse mixte, chaîne vide, `None`.

### 3.4 — `draft/phases.py` : cible ≥ 80 %

40 lignes, aucune dépendance externe : décide si l'on est en phase de ban, ce qui conditionne l'affichage des recommandations de ban. Couvrir chaque combinaison de `actions`/`type`/`isInProgress` rencontrée, y compris un payload d'actions vide et une phase inconnue.

### 3.5 — Tests d'intention sur `trio_*` / `ban_recommendations`

**Quelques tests, pas beaucoup.** Objectif : verrouiller des invariants métier que la caractérisation ne protège pas. Par exemple :

- un trio évalué avec `lane` fixée n'utilise **que** les matchups de cette lane (le bug de septembre, verrouillé au niveau du module et non plus seulement via `Assistant`) ;
- `BanRecommender` ne recommande jamais un champion déjà banni ou déjà pické ;
- la menace d'un ennemi est monotone : à données égales, un ennemi avec un meilleur `delta2` contre la pool ne peut pas être classé moins menaçant ;
- un champion sans donnée sur la lane demandée n'est jamais scoré à 0 comme s'il était neutre — il est écarté ou marqué (cohérent avec SPEC-09 E1).

Ces tests doivent **échouer** si l'on réintroduit volontairement le bug lane. Le vérifier pendant l'écriture, c'est le seul critère qui prouve leur valeur.

---

## 4. Critères d'acceptation

1. Couvertures cibles atteintes sur les 4 modules du §1.
2. Couverture globale ≥ 70 % (contre 65,5 %).
3. Relever le seuil `--cov-fail-under` de `pyproject.toml:67` de 45 à **60** — un seuil très en dessous du réel ne protège de rien. Ne pas le fixer au niveau exact atteint : garder de la marge pour ne pas casser la CI au premier refactor.
4. Aucun test n'accède à `data/db.db` ni n'écrit dans `logs/` réels (règle d'hermétisme ; voir le fix du 2026-09-05, commit `db872ff`, où un test de régression touchait le vrai `logs/repair_matchups.log`).
5. `pytest tests/ -v` vert, `black --check`, `pylint src/ --fail-under=8.0`.

## 5. Hors périmètre

- ❌ Couvrir les UI d'affichage pur (`tournament_display_ui`, `pools_crud_ui`, `champion_data_ui`) : beaucoup de lignes, peu de risque. La couverture n'est pas un objectif en soi.
- ❌ Tests d'intégration contre un vrai client League of Legends : non reproductibles en CI.
- ❌ Refactorer les modules testés « pour les rendre testables » : s'ils résistent au test, le signaler dans la PR plutôt que de mélanger refactor et couverture.
