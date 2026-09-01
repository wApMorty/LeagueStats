# TODO — LeagueStats Coach

**Mis à jour** : 2026-09-01
**Source** : [docs/AUDIT_2026_08.md](docs/AUDIT_2026_08.md) · [docs/BACKLOG_2026_08.md](docs/BACKLOG_2026_08.md)
**Specs d'implémentation** : [docs/specs/](docs/specs/) — une spec autoportante par chantier.

> L'ancien TODO.md (2 573 lignes, tâches #1 à #18) est **entièrement soldé ou annulé** : ce qui devait être fait l'a été, le reste a été tranché par `docs/ROADMAP_2026.md` (SQLite only, outil personnel, pas de SaaS, pas de Playwright). Il reste consultable dans l'historique git : `git show ef7c193:TODO.md`.

---

## Priorités

| Rang | Chantier | Spec | Pourquoi maintenant |
|---|---|---|---|
| 1 | **Pipeline : remettre le dernier maillon** | [SPEC-01](docs/specs/SPEC-01-pipeline-fiabilite.md) | Les tier lists sont HS (`champion_scores` vide) sur des données pourtant bonnes |
| 2 | ⭐ **Scrape en une seule visite de page** | [SPEC-02](docs/specs/SPEC-02-scrape-page-unique.md) | −40 % de temps et moitié moins de requêtes vers LoLalytics |
| 3 | **Lecture lane-aware** | [SPEC-03](docs/specs/SPEC-03-lecture-lane.md) | Fondation du chantier lane ; corrige une incohérence de calcul |
| 4 | ⭐ **Inférence des rôles des 10 joueurs** | [SPEC-04](docs/specs/SPEC-04-inference-roles.md) | Le chantier principal : 18 à 24 pts de `delta2` aujourd'hui noyés |
| 5 | **Modèle de score en log-odds** | [SPEC-05](docs/specs/SPEC-05-modele-scoring.md) | Rend les scores interprétables **et vérifiables** |
| — | Quick wins (< 1 h chacun) | [SPEC-06](docs/specs/SPEC-06-quickwins.md) | À piocher entre deux chantiers |
| — | Dette, tests, docs | [SPEC-07](docs/specs/SPEC-07-dette-tests-docs.md) | E1 (couverture) avant tout gros refactor |

---

## Détail

### 1. Pipeline — remettre le dernier maillon 🔴 · [SPEC-01](docs/specs/SPEC-01-pipeline-fiabilite.md)

| Id | Item | PV | D | ROI |
|---|---|---|---|---|
| A1 | ✅ Recalculer `champion_scores` (table vide depuis le 25/08) | 13 | 1 | **13,0** |
| A2 | ✅ Faire converger le menu 3 et `scripts/update_all.py` | 13 | 3 | 4,3 |
| A3 | ✅ Rendre la fraîcheur mesurable (`db_meta` écrit au scrape) | 13 | 2 | 6,5 |
| A4 | ✅ Contrôle de complétude gradué (bloquant / avertissement) | 8 | 3 | 2,7 |
| A5 | ✅ Sauvegarde avant `DROP` (run non destructif) | 13 | 5 | 2,6 |
| A6 | ✅ Réparer la CI (black 26 + test `pool_manager`) | 8 | 2 | 4,0 |

### 2. Performance du scrape ⭐ · [SPEC-02](docs/specs/SPEC-02-scrape-page-unique.md) et [SPEC-06](docs/specs/SPEC-06-quickwins.md)

| Id | Item | PV | D | ROI |
|---|---|---|---|---|
| C1 | ✅ Matchups + synergies en une seule visite de page | 13 | 8 | 1,6 |
| C2 | ✅ Sortir `get_all_champion_names()` de la boucle des trios | 5 | 1 | 5,0 |
| C3 | ✅ Supprimer le double calcul d'affichage du top 3 | 3 | 1 | 3,0 |
| C4 | ✅ Index `COLLATE NOCASE` sur `champions.name` | 5 | 3 | 1,7 |

### 3. Chantier lane ⭐🔴 · [SPEC-03](docs/specs/SPEC-03-lecture-lane.md) et [SPEC-04](docs/specs/SPEC-04-inference-roles.md)

| Id | Item | PV | D | ROI |
|---|---|---|---|---|
| B1 | ✅ Unifier l'agrégation multi-lane (bulk ≠ unitaire) | 13 | 3 | 4,3 |
| B2 | ✅ Lecture filtrée par lane (accesseurs + scoring) | 21 | 8 | 2,6 |
| B8 | ✅ Contrainte d'unicité `(champion, enemy, lane)` + dédoublonnage | 8 | 3 | 2,7 |
| B3 | ✅ Exposer `assignedPosition` du LCU | 13 | 3 | 4,3 |
| B4 | ✅ Inférer le rôle des 10 joueurs (affectation 5×5) | 21 | 13 | 1,6 |
| B5 | ✅ Afficher lane + nombre de parties dans les recommandations | 13 | 3 | 4,3 |

### 4. Modèle de score · [SPEC-05](docs/specs/SPEC-05-modele-scoring.md)

| Id | Item | PV | D | ROI |
|---|---|---|---|---|
| B6 | ✅ Composer `pickrate × confiance(games)` | 13 | 5 | 2,6 |
| B7 | ✅ Passage en log-odds (remplace winrate d'équipe + `delta2 → %`) | 13 | 8 | 1,6 |

### 5. Confort d'usage · [SPEC-06](docs/specs/SPEC-06-quickwins.md)

| Id | Item | PV | D | ROI |
|---|---|---|---|---|
| D1 | ✅ Corriger le chemin de `champion_pools.json` (écrit hors du dépôt) | 8 | 1 | **8,0** |
| D2 | ✅ Mémoriser les préférences du draft coach | 8 | 2 | 4,0 |
| D3 | 🟡 Unifier la langue de l'interface (français) — fait sauf `lol_coach_legacy.py`, différé à E9 | 5 | 3 | 1,7 |
| D4 | Purger les emojis des sorties console | 3 | 2 | 1,5 |

### 6. Dette, tests, docs · [SPEC-07](docs/specs/SPEC-07-dette-tests-docs.md)

| Id | Item | PV | D | ROI |
|---|---|---|---|---|
| E1 | Mesurer la couverture sur tout `src/` | 8 | 2 | 4,0 |
| E2 | Réécrire le README | 8 | 2 | 4,0 |
| E4 | Unifier le numéro de version (→ 1.3.0) | 5 | 1 | 5,0 |
| E5 | Hygiène du dépôt (fichiers parasites trackés, résidus) | 5 | 1 | 5,0 |
| E6 | Isoler les tests (log et BD de production touchés) | 8 | 3 | 2,7 |
| E7 | Sortir les seuils métier restants vers `config_constants` | 5 | 2 | 2,5 |
| E8 | ✅ Corriger la casse dans `calculate_synergy_bonus` | 5 | 1 | 5,0 |
| E9 | Démanteler `lol_coach_legacy.py` (2 045 l., 14 % couvert) — inclut la traduction D3 restante | 8 | 13 | 0,6 |
| E10 | Dégraisser `assistant.py` (2 230 l.) et `draft_monitor.py` (1 547 l.) | 8 | 13 | 0,6 |

---

## Hors périmètre (tranché)

- ❌ Backend distant (Neon, API FastAPI, SaaS multi-utilisateurs)
- ❌ Migration Playwright — Cloudflare n'oppose plus de challenge
- ❌ Scraping en datacenter / GitHub Actions
- ❌ i18n, multi-plateforme, GUI lourde
- ⏸️ Automatisation nocturne — **suspendue par choix**, mise à jour manuelle assumée

---

**Légende** : PV = plus-value (1→21) · D = difficulté (1→21) · ROI = PV/D · ⭐ = priorisé par @pj35
