# SPEC-07 — Dette technique, tests et documentation

**Items** : E1, E2, E3, E4, E6, E9, E10 · **Effort** : variable (E1/E4 ~1 h · E9/E10 plusieurs jours)
**Constats d'audit** : C1, C2, F7, §7.4, §7.5 (`docs/AUDIT_2026_08.md`)
**Prérequis** : aucun · **E1 devrait précéder E9/E10 et les gros chantiers (SPEC-03/04/05)**

---

## E1 — Mesurer la couverture sur tout `src/` ⚠️ *à faire tôt*

**Fichier** : `pyproject.toml`

```toml
[tool.coverage.run]
source = ["src/analysis"]     # ← 5 % du code
...
addopts = [..., "--cov=src/analysis", "--cov-fail-under=70"]
```

La CI valide donc **87 % sur 400 lignes** d'algorithmes en ignorant les 8 000 autres. Mesure honnête (`pytest --cov=src`) : **38,07 %**, avec `draft_monitor.py` à 26,2 %, `lcu_client.py` à 15,5 %, `lol_coach_legacy.py` à 14,0 %, `assistant.py` à 27,0 %.

Un PR peut aujourd'hui détruire `draft_monitor.py` sans faire bouger la métrique — et les quatre monolithes ont pris **+1 248 lignes** depuis juin pendant que le dépôt en perdait 12 800.

**Correction** :

```toml
[tool.coverage.run]
source = ["src"]
omit = ["src/ui/lol_coach_legacy.py"]   # dette isolée, traitée par E9

addopts = [..., "--cov=src", "--cov-fail-under=45"]
```

- Seuil à **45 %** : légèrement au-dessus du réel hors legacy, pour que la métrique morde sans bloquer immédiatement.
- Documenter en commentaire que le seuil doit **monter** avec chaque chantier, jamais descendre.
- Mettre `.github/workflows/ci.yml` en cohérence (le job `tests` répète les options en ligne de commande, l. ~95).

**Pourquoi tôt** : SPEC-03, 04 et 05 touchent massivement `scoring.py`, `db.py` et `draft_monitor.py`. Sans mesure honnête, impossible de savoir si ces chantiers améliorent ou dégradent la couverture du cœur du produit.

---

## E6 — Isoler les tests de la production

Deux fuites vérifiées, qui rendent les logs de production inexploitables pour le diagnostic :

**(a) Écriture dans `logs/update_all.log`.** Le fichier de production (1,3 Mo) contient les traces de la suite de tests : on y lit des `RuntimeError: geckodriver missing` levés depuis `unittest/mock.py`, et des « update_all completed successfully in 0.0 min » qui ne correspondent à aucun run réel. C'est ce qui a rendu l'historique du pipeline illisible pendant l'audit.

*Correction* : `_setup_logging()` dans `scripts/update_all.py` doit accepter un répertoire de log injectable ; les tests passent `tmp_path`. Ajouter dans `tests/conftest.py` une fixture **autouse** qui redirige le répertoire de logs vers `tmp_path` pour toute la suite — ceinture et bretelles.

**(b) Ouverture de `data/db.db`.** `PoolManager.__init__` → `_load_role_pools_from_db()` (l. ~105-150) ouvre `config.DATABASE_PATH`, donc la vraie base, à chaque instanciation — y compris sous pytest.

*Correction* : fixture autouse dans `conftest.py` qui `monkeypatch` `src.config.config.DATABASE_PATH` vers une base temporaire par défaut. Les tests qui veulent la vraie base (aucun ne le devrait) le déclarent explicitement.

**Test de garde** : un test qui échoue si `data/db.db` ou `logs/` sont touchés pendant la suite (vérification du `mtime` avant/après la session pytest).

---

## E2 — Réécrire le README

`README.md` est faux sur presque tout :

| Affirmation | Réalité |
|---|---|
| `python main.py` (« Legacy Mode ») | Le fichier n'existe pas |
| « 3 data modes » (SQLite / PostgreSQL / Hybrid) | Supprimés en juin-juillet 2026, SQLite uniquement |
| « PostgreSQL Direct Mode pour jouer en déplacement » | Neon décommissionné |
| « 12 min avec 10 workers, 87 % plus rapide » | 45 min avec 5 workers (multi-lane) |
| « Auto-updates daily via Task Scheduler, zero maintenance » | Suspendu par choix, mise à jour manuelle |
| « 36 000+ matchups » | 26 398 |
| « 89 % test coverage » | 38 % réels ; le 89 % ne concernait que `src/analysis` |
| Badges pointant vers `github.com/pj35/LeagueStats` | Le dépôt est `wApMorty/LeagueStats` |

**Contenu attendu** : ce que fait l'outil, comment le lancer, comment mettre à jour les données (menu 3 ou `scripts/update_all.py`), les prérequis réels (Python 3.13, Firefox, client LoL pour le draft coach), et un pointeur vers `docs/`. Court, exact, sans chiffre invérifiable.

Vérifier chaque affirmation avant de l'écrire : c'est un README, pas un argumentaire.

---

## E3 — `TODO.md`

✅ **Déjà fait** (2026-08-29) : `TODO.md` a été réécrit à partir de `docs/BACKLOG_2026_08.md`. À maintenir à jour au fil des chantiers — cocher, retirer, ne pas laisser regonfler (l'ancien faisait 2 573 lignes).

---

## E4 — Unifier le numéro de version

Trois vérités coexistent :

| Emplacement | Valeur |
|---|---|
| `src/__init__.py` | `1.0.0` |
| `CLAUDE.md` | `1.1.0-dev` |
| `CHANGELOG.md` | `[Unreleased]` après `[1.2.0]` |

**Cible : `1.3.0`**, à poser une fois SPEC-01 livrée (fin du chantier pipeline). Mettre à jour `src/__init__.py`, `CLAUDE.md`, le titre du CHANGELOG, `README.md` et `LeagueStatsCoach.spec` s'il porte une version. Poser un tag git `v1.3.0`.

Corriger au passage l'ordre du CHANGELOG (`[Unreleased]` doit être **au-dessus** de `[1.2.0]`) et les mentions « PR #TBD ».

---

## E9 — Démanteler `lol_coach_legacy.py`

**2 576 lignes, 14 % de couverture, « temporaire » depuis décembre 2025.** A grossi de 220 lignes depuis juin.

**Prérequis impératif** : E1 (mesure honnête) et, idéalement, SPEC-01 A2 — qui retire déjà plusieurs centaines de lignes de ce fichier en faisant appeler le pipeline commun. **Faire SPEC-01 d'abord change la nature du travail restant.**

**Méthode** :

1. **Tests de caractérisation d'abord.** Avant de déplacer une ligne, écrire des tests qui capturent le comportement actuel des fonctions publiques (`check_dependencies`, `check_database`, `parse_match_statistics`, `run_champion_analysis`, `run_optimal_team_builder`, `manage_champion_pools`). Ils doivent passer avant **et** après le refactor, sans modification.
2. **Découper par menu**, un module par domaine dans `src/ui/` :
   - `src/ui/data_update_ui.py` — menu 3 (scraping)
   - `src/ui/analysis_ui.py` — menu 4 (analyse et tournoi)
   - `src/ui/team_builder_ui.py` — menu 5 (équipe optimale)
   - `src/ui/pools_ui.py` — menu 6 (gestion des pools)
   - `src/ui/checks.py` — `check_dependencies`, `check_database`
3. Chaque module **< 400 lignes**. Si un domaine dépasse, c'est qu'il contient de la logique métier qui doit descendre dans `src/analysis/`.
4. `lol_coach_legacy.py` disparaît ; `lol_coach.py` importe les nouveaux modules.

**Un commit par module extrait**, tests verts entre chaque.

---

## E10 — Dégraisser `assistant.py` et `draft_monitor.py`

| Fichier | Juin | Août | Couverture |
|---|---|---|---|
| `src/assistant.py` | 1 843 | **2 230** | 27,0 % |
| `src/draft_monitor.py` | 1 166 | **1 547** | 26,2 % |
| `src/db.py` | 1 149 | **1 409** | 48,5 % |

**`assistant.py`** — les blocs candidats à l'extraction, déjà identifiés :

| Bloc | Lignes | Destination |
|---|---|---|
| Trio holistique (`find_optimal_trios_holistic`, `_evaluate_trio_holistic`, scores de couverture/équilibre/cohérence/méta, poids adaptatifs, profils) | ~1468-2230 (≈ 760 l.) | `src/analysis/holistic.py` |
| Duos et trios classiques (`_find_optimal_counterpick_duo`, `optimal_trio_from_pool`, `optimal_duo_for_champion`, `_analyze_trio_*`) | ~546-1050 (≈ 500 l.) | `src/analysis/team_builder.py` |
| Bans (`get_ban_recommendations`, `precalculate_pool_bans`, `precalculate_all_custom_pool_bans`) | ~1051-1357 (≈ 300 l.) | `src/analysis/bans.py` |

`Assistant` redevient ce que le Sprint 1 avait produit : un coordinateur mince (cache, délégation, orchestration).

**`draft_monitor.py`** — extraire l'affichage (`_display_draft_state`, `_calculate_final_scores`, `_display_live_podium`, formatage des recommandations) vers `src/ui/draft_display.py`. Le monitor garde la boucle, l'état et le LCU.

**Ordre recommandé** : bans → duos/trios → holistique (du moins au plus intriqué). Un commit par bloc, tests verts entre chaque, aucune modification de comportement.

⚠️ **Ne pas engager E10 pendant SPEC-03/04/05** : ces specs modifient les mêmes fonctions, les conflits seraient pénibles. Soit avant, soit après.

---

## Critères d'acceptation

- [ ] **E1** : `pytest` mesure `src/` entier, seuil 45 %, CI en cohérence, seuil documenté comme devant monter.
- [ ] **E6** : une exécution complète de la suite ne modifie ni `data/db.db` ni `logs/` (vérifié par `mtime`).
- [ ] **E2** : chaque affirmation du README est vérifiable sur le dépôt à date.
- [ ] **E4** : une seule version dans tout le dépôt, tag git posé.
- [ ] **E9** : `lol_coach_legacy.py` supprimé, aucun module `src/ui/` > 400 lignes, tests de caractérisation verts sans modification.
- [ ] **E10** : `assistant.py` < 800 lignes, `draft_monitor.py` < 900 lignes, couverture du cœur produit en hausse.
- [ ] `pytest tests/ -v` : 0 échec à chaque étape.

---

## Pièges connus

- **Refactor ≠ amélioration.** E9 et E10 sont des déplacements de code à comportement **strictement identique**. Toute correction repérée en chemin fait l'objet d'un commit séparé, avec son test de régression.
- **Imports circulaires** : `src/utils/__init__.py` en signale déjà un (`src.assistant → src.pool_manager`, remonté par pylint). Extraire des modules d'`assistant.py` peut en créer d'autres — vérifier avec `pylint src/ | grep cyclic` après chaque extraction.
- **`lol_coach_legacy.py` est exclu de la couverture par E1** : ne pas oublier de retirer l'exclusion quand E9 le supprime.
- **Le seuil de couverture ne doit jamais baisser** pour faire passer un PR. S'il bloque, c'est qu'il manque des tests.
