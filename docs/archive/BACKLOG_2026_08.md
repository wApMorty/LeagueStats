# 📋 Backlog Candidat — Août 2026

**Source** : `docs/AUDIT_2026_08.md` (28/08/2026, corrigé le 29/08)
**Statut** : ⏳ **À trier par @pj35** — rien n'est engagé. Une fois le tri fait, ce document sert de base à la réécriture de `TODO.md`.
**Convention** : scores Fibonacci comme dans `TODO.md` (Plus-value 1→21, Difficulté 1→21, ROI = PV/D). Chaque item renvoie au constat d'audit correspondant.

## Arbitrages déjà rendus (29/08)

| Sujet | Décision |
|---|---|
| **Lanes** | ⭐ **À implémenter** — le Live Coach doit deviner la lane des **10 joueurs** (alliés et adversaires) pour affiner les calculs. C'est le chantier principal. |
| **P1 / C1 — page chargée deux fois** | ⭐ **Prioritaire** |
| **Automatisation nocturne** | Arrêtée **par choix** — pas un défaut. Les items associés sont reclassés en « si un jour ». |
| **M3 — pickrate** | La pondération par pickrate sert à **prédire le pick adverse** : elle est juste et se conserve. Le sujet devient : y **ajouter** une notion de confiance statistique. |
| **M5 — winrate d'équipe** | Modèle cherché, bases mathématiques à poser → proposition détaillée dans l'audit §4 (M5), item **B7** ci-dessous. À discuter avant d'implémenter. |

---

## Lot A — Remettre le dernier maillon en place 🔴

*Le scrape fonctionne (données du 25/08, multi-lane, complètes). Ce sont les étapes d'après qui décrochent.*

| Id | Item | PV | D | ROI | Constat |
|---|---|---|---|---|---|
| **A1** | **Recalculer `champion_scores` maintenant** | 13 | 1 | **13,0** | F2 |
| **A2** | **Faire converger le menu 3 et `update_all.py`** | 13 | 3 | **4,3** | F2, U4 |
| **A3** | **Rendre la fraîcheur mesurable (écrire `db_meta` au scrape)** | 13 | 2 | **6,5** | F3 |
| **A4** | **Contrôle de complétude gradué (bloquant / avertissement)** | 8 | 3 | **2,7** | F6 |
| **A5** | **Sauvegarde avant `DROP` (run non destructif)** | 13 | 5 | **2,6** | F1 |
| **A6** | **Réparer la CI (black 26 + test pool_manager)** | 8 | 2 | **4,0** | F9 |

**A1 — Recalculer les scores maintenant** *(quick win)*
`champion_scores` est vide : le menu 3 fait un `DROP` de la table avant le scrape, et le recalcul du 25/08 a planté (bug corrigé depuis par `08d2c9c`, jamais rejoué). Les tier lists sont donc HS alors que les données sont bonnes. Un `calculate_global_scores()` suffit — 5 minutes, sans re-scraper.
*Piste* : un flag `--recompute-only` sur `update_all.py`, réutilisable à chaque incident du même type.

**A2 — Faire converger les deux orchestrateurs**
Le menu 3 scrape correctement (multi-lane, même découverte de lane) mais saute quatre garde-fous : pas de contrôle de complétude, pas de `db_meta`, pas de recalcul des bans, pas de log fichier. `update_all.py` fait tout cela mais n'est plus lancé. Le plus simple : que le menu appelle `update_all.py` plutôt que de réimplémenter le pipeline. Bénéfice immédiat — A3, A4 et le journal deviennent effectifs sur le chemin réellement utilisé.

**A3 — Rendre la fraîcheur mesurable**
Deux gestes : écrire `db_meta.last_update_utc` **à la fin du scrape** (et non dans l'orchestrateur, sinon le menu ne l'écrit toujours pas), avec un statut distinguant « scrape OK » de « pipeline complet OK » ; et supprimer le repli sur le `mtime` du fichier dans `data_freshness.py`, qui mesure la dernière ouverture de la base et non sa dernière mise à jour. Sans métadonnée : « fraîcheur inconnue ».
*C'est ce qui m'a fait dater les données de six semaines au lieu de quatre jours — l'indicateur est activement trompeur, dans les deux sens.*

**A4 — Contrôle de complétude gradué**
Aujourd'hui, un champion sous le seuil fait échouer tout le pipeline (c'est ce qui s'est passé le 16/07 : 566/566 pages OK, 13 champions sans synergies, tout annulé). Distinguer **bloquant** (volumétrie effondrée, > 5 % de champions vides) de **avertissement** (quelques trous → on continue, on recalcule, on notifie, on lance un `repair_data.py` ciblé). Traiter au passage **Aphelios, 0 matchup** — seul champion qui bloquerait un contrôle aujourd'hui.

**A5 — Sauvegarde avant `DROP`**
Les deux orchestrateurs font `DROP TABLE matchups/synergies` puis re-remplissent pendant ~45 min : toute interruption détruit la base (mécanisme exact du sinistre du 01/06). Version minimale et suffisante : copier `data/db.db` avant le `DROP`, restaurer si le run échoue. Version propre : tables de staging + bascule transactionnelle. **La version minimale couvre l'essentiel du risque pour une fraction de l'effort** — et devient franchement peu coûteuse si A2 est fait d'abord (un seul endroit à modifier).

**A6 — Réparer la CI**
(1) `black 26.3.1` pinné par Dependabot sans reformatage du code : lancer black 26 et committer, puis l'installer en local pour éviter la récidive (le black 24 local dit « All done » — d'où l'invisibilité). (2) `test_save_custom_pools_recalc_bans_in_dev_mode` attend 1 appel à `Database` alors que `PoolManager` en fait 2 depuis les pools système dynamiques.

---

## Lot B — Le chantier lanes et le modèle de score ⭐🔴

*Les données lane sont en base depuis juillet. Personne ne les lit. C'est là que se trouve la valeur.*

| Id | Item | PV | D | ROI | Constat |
|---|---|---|---|---|---|
| **B1** | **Unifier l'agrégation multi-lane** | 13 | 3 | **4,3** | M2 |
| **B2** | **Lecture filtrée par lane (accesseurs + scoring)** | 21 | 8 | **2,6** | M1 |
| **B3** | **Exposer `assignedPosition` du LCU** | 13 | 3 | **4,3** | M1 |
| **B4** | **Inférer le rôle des 10 joueurs (affectation 5×5)** | 21 | 13 | **1,6** | M1 |
| **B5** | **Afficher lane + nombre de parties dans les recommandations** | 13 | 3 | **4,3** | M3, U5 |
| **B6** | **Composer pickrate × confiance statistique** | 13 | 5 | **2,6** | M3 |
| **B7** | **Modèle de score en log-odds (à discuter d'abord)** | 13 | 8 | **1,6** | M4, M5 |
| **B8** | **Contrainte d'unicité `(champion, enemy, lane)` + dédoublonnage** | 8 | 3 | **2,7** | F5 |

### L'enchaînement du chantier lane

`B1 → B2 → B3 → B4 → B5` se fait dans cet ordre, et **chaque étape a déjà de la valeur seule** :

**B1 — Unifier l'agrégation** *(prérequis technique)*
`get_matchup_delta2()` fait une moyenne pondérée par parties ; `get_all_matchups_bulk()` **écrase** les doublons de lane (26 398 lignes → 15 699 entrées, 10 699 valeurs jetées, la survivante dépendant de l'ordre SQL). Le même matchup peut donc être noté différemment selon le chemin de code. Une seule fonction d'agrégation, utilisée partout — sinon B2 construit sur du sable.

**B2 — Lecture filtrée par lane**
Ajouter un paramètre `lane` optionnel aux accesseurs (`get_champion_matchups_by_name`, `get_matchup_delta2`, les bulk) et le propager dans `ChampionScorer` / `DraftMonitor`, avec repli sur l'agrégation toutes lanes quand la lane est inconnue. Les index composites nécessaires existent déjà (créés en H1). **Testable immédiatement avec une lane saisie à la main**, avant même B3/B4 — c'est le bon moment pour vérifier que les recommandations changent dans le bon sens.

**B3 — Position assignée par le client**
`assignedPosition` est dans la session de champion select pour l'équipe alliée en file classée ; `lcu_client.py` ne l'expose pas. Donne gratuitement les 5 rôles alliés quand l'info est là (absente en Draft Normal, ARAM, etc.).

**B4 — Inférer le rôle des 10 joueurs**
Le vrai morceau, et l'objectif que tu as fixé. Le principe :

1. Pour chaque champion pické, la base donne déjà sa **distribution de lanes** (part de parties par lane — c'est ce qui alimente les pools système dynamiques).
2. Une équipe a **exactement un joueur par rôle** : ce n'est donc pas cinq devinettes indépendantes, mais une **affectation** de 5 champions à 5 rôles distincts.
3. Il n'y a que `5! = 120` affectations possibles : les énumérer toutes (`itertools.permutations`) et garder celle de vraisemblance maximale donne l'optimum **exact**, en moins d'une milliseconde et en une dizaine de lignes — inutile d'introduire `scipy` pour un algorithme hongrois.

C'est nettement plus juste que « chaque champion prend sa lane la plus fréquente », qui produit des équipes à deux junglers et zéro support. À recalculer **à chaque pick** (l'information s'affine à mesure du draft) et à rendre **révisable** : les rôles inférés s'affichent, tu peux les corriger d'une touche.
*Signal complémentaire faible : l'ordre de pick (les premiers picks penchent top/jungle/mid) — à n'utiliser qu'en départage.*

**B5 — Afficher lane et volume**
Aujourd'hui : `[1st] Pantheon +2,34% (Matchup: +1,80%, Synergy: +0,54%)`. Après : `[1st] Pantheon (top vs Darius top) +2,34% · 4 800 parties`. Les données sont déjà là ; c'est ce qui permet de savoir quand ne **pas** suivre le conseil.

### Les deux items de modélisation

**B6 — Composer fréquence de pick et confiance**
Ta remarque est intégrée : le `pickrate` sert à prédire le pick adverse, c'est correct et ça reste. Le manque est ailleurs : au-delà du seuil `games >= 200`, un matchup à 210 parties pèse autant qu'un à 26 354. Composer les deux : `poids = pickrate × games/(games+k)`, avec `k ≈ 500` à calibrer. Un matchup peu joué est alors ramené vers le neutre plutôt que compté plein pot — sans rien retirer à la logique de prédiction du pick.

**B7 — Modèle en log-odds** *(discussion d'abord)*
Remplace à la fois `calculate_team_winrate` (moyenne géométrique bornée à [25, 75], sans fondement) et `delta2_to_win_advantage` (l'identité, affichée avec un signe `%`). Principe : les avantages ne s'additionnent pas en probabilités mais en **log-odds**, et une sigmoïde finale ramène le tout dans ]0 ; 1[ — plus de bornes arbitraires, saturation naturelle des avantages cumulés. **Le développement complet, la formule et le chemin d'implémentation en 5 étapes sont dans l'audit §4 (M5).**
Point qui mérite l'effort à lui seul : le modèle est **calibrable**. Le draft coach connaît l'issue réelle des parties via le LCU ; en journalisant `(probabilité prédite, résultat)`, on peut vérifier que les drafts annoncés à 60 % se gagnent bien ~60 % du temps, et ajuster les coefficients. C'est le seul endroit du projet où l'on peut mesurer si le coach a **raison**.

**B8 — Unicité en base**
1 263 triplets `(champion, enemy, lane)` en double, dont des valeurs contradictoires (Annie vs Lux support : −9,25 **et** +4,61). Migration Alembic `UNIQUE` + `ON CONFLICT DO UPDATE`, précédée d'un dédoublonnage. Devient indispensable si A5 fait disparaître le `DROP TABLE`.

---

## Lot C — Performance ⚡

| Id | Item | PV | D | ROI | Constat |
|---|---|---|---|---|---|
| **C1** | ⭐ **Scraper matchups + synergies en une seule visite de page** | 13 | 8 | **1,6** | P1 |
| **C2** | **Sortir `get_all_champion_names()` de la boucle des trios** | 5 | 1 | **5,0** | P2 |
| **C3** | **Supprimer le double calcul d'affichage du top 3** | 3 | 1 | **3,0** | P3 |
| **C4** | **Retirer `COLLATE NOCASE` des jointures (normaliser en amont)** | 5 | 3 | **1,7** | P4 |

**C1 — Une seule visite par page** ⭐ *priorisé*
Le pipeline fait deux passes complètes sur les mêmes 283 pages — matchups, puis synergies — alors que les deux jeux de données sont sur la **même page** : le scraper clique simplement « Common Teammates » pour basculer l'affichage. Mesure du run du 16/07 : 24,7 min de matchups + 18,1 min de synergies = 45 min.

Gain attendu : **−30 à 40 %** (→ ~28 min), et surtout **moitié moins de requêtes** vers LoLalytics — donc moitié moins d'exposition à un blocage, ce qui compte autant que le temps gagné vu l'historique Cloudflare du projet.

*Attention à un point de conception* : aujourd'hui les deux phases sont indépendantes, donc un échec de synergie n'invalide pas le matchup déjà écrit. En fusionnant, il faut décider quoi faire quand la page se charge mais que le clic « Common Teammates » échoue — écrire les matchups seuls et signaler le trou (recommandé), plutôt que de perdre les deux. C'est ce qui rend l'item plus proche de 8 que de 5 en difficulté.

**C2 / C3 / C4** — Trois nettoyages de quelques lignes : une requête SQL sortie d'une boucle de 455 itérations, un recalcul redondant à l'affichage, et une jointure qui n'utilise pas son index (6,3 ms par appel, ~50× le coût attendu).

---

## Lot D — Confort d'usage 🎮

| Id | Item | PV | D | ROI | Constat |
|---|---|---|---|---|---|
| **D1** | **Corriger le chemin de `champion_pools.json`** | 8 | 1 | **8,0** | F8 |
| **D2** | **Mémoriser les préférences du draft coach** | 8 | 2 | **4,0** | U1 |
| **D3** | **Unifier la langue de l'interface (français)** | 5 | 3 | **1,7** | U2 |
| **D4** | **Purger les emojis des sorties console** | 3 | 2 | **1,5** | U3 |

**D1 — Corriger le chemin des pools** *(quick win)*
`get_user_pools_path()` fait trois `dirname` au lieu de deux : tes 5 pools personnels sont écrits dans `Code Workspace/champion_pools.json`, **hors du dépôt**, hors sauvegarde. Une ligne à corriger + migrer le fichier existant.

**D2 — Mémoriser les préférences**
Six questions avant chaque draft (auto-hover, auto-accept, auto-ban, onetricks, poids synergie, pool), toujours les mêmes réponses. Sauvegarder les derniers choix et proposer « Entrée = comme la dernière fois ». 30 secondes gagnées avant chaque partie, au moment où on est le plus pressé.

---

## Lot E — Dette et hygiène 🧹

| Id | Item | PV | D | ROI | Constat |
|---|---|---|---|---|---|
| **E1** | **Mesurer la couverture sur tout `src/`** | 8 | 2 | **4,0** | C2 |
| **E2** | **Réécrire le README** | 8 | 2 | **4,0** | §7.5 |
| **E3** | **Réécrire `TODO.md` depuis ce backlog** | 8 | 2 | **4,0** | §7.5 |
| **E4** | **Unifier le numéro de version (→ 1.3.0)** | 5 | 1 | **5,0** | §7.5 |
| **E5** | **Hygiène du dépôt** | 5 | 1 | **5,0** | §7.4 |
| **E6** | **Isoler les tests (log et BD de production)** | 8 | 3 | **2,7** | F7 |
| **E7** | **Sortir les seuils métier restants vers `config_constants`** | 5 | 2 | **2,5** | M8 |
| **E8** | **Corriger la casse dans `calculate_synergy_bonus`** | 5 | 1 | **5,0** | M7 |
| **E9** | **Démanteler `lol_coach_legacy.py` (2 576 l., 14 % couvert)** | 8 | 13 | **0,6** | C1 |
| **E10** | **Dégraisser `assistant.py` (2 230 l.) et `draft_monitor.py` (1 547 l.)** | 8 | 13 | **0,6** | C1 |

**E1 — Mesurer la couverture honnêtement**
`pyproject.toml` mesure `src/analysis` seul avec un seuil à 70 % : la CI valide 87 % sur 5 % du code pendant que `draft_monitor.py` est à 26 %. Élargir à `src/` et poser le seuil au niveau réel (38 %), quitte à le remonter ensuite. Sans ça, rien ne freine la reprise de poids des monolithes (+1 248 lignes depuis juin) — et le lot B va beaucoup toucher à `draft_monitor.py`.

**E5 — Hygiène** *(quick win)*
Supprimer les fichiers parasites **trackés dans git** (`2.0.0`, `90%`, `Dict[str`), le dossier `server/` orphelin sur disque, `node_modules/` + `package*.json` (résidus Ruflo), `config/.env.neon`, `outputs/t13_neon_readonly_user.yaml`, `logs/auto_update.log` (12,7 Mo, mort depuis mars). Restreindre le `*.json` global du `.gitignore`.

**E6 — Isoler les tests**
La suite écrit dans `logs/update_all.log` (fichier de production — on y lit des `RuntimeError: geckodriver missing` levés depuis `unittest/mock.py`) et `PoolManager()` ouvre la vraie `data/db.db` à chaque instanciation. Diagnostic faussé pour qui lit les logs — c'est une des raisons pour lesquelles l'historique du pipeline est illisible.

**E9 / E10 — Les monolithes**
Faible ROI, effort réel, aucune urgence fonctionnelle — mais c'est ce qui ralentit tout le reste. À n'engager qu'après E1 (sinon on démantèle sans filet). `lol_coach_legacy.py` est « temporaire » depuis décembre 2025.

---

## Si un jour l'automatisation nocturne reprend ⏸️

*Hors périmètre tant que la mise à jour manuelle convient — noté pour ne pas avoir à le redécouvrir.*

- La tâche « LeagueStats Auto-Update » est désactivée et pointe sur `scripts/auto_update_db.py`, l'ancien orchestrateur — à basculer sur `scripts/update_all.py`.
- `auto_update_db.py` (491 l.) et `update_all.py` (253 l.) font double emploi : le premier peut être supprimé, que l'automatisation reprenne ou non.
- `docs/AUTO_UPDATE_SETUP.md` décrit encore l'ancien script.
- A3 (fraîcheur) et A4 (complétude graduée) sont les prérequis pour qu'un run nocturne échoue **bruyamment** au lieu de silencieusement.

---

## Ce que ce backlog ne propose pas

Par cohérence avec les décisions tranchées le 11/06/2026 (`ROADMAP_2026.md` §2), confirmées en août :

- ❌ Retour d'un backend distant (Neon, API, SaaS) — décommissionné, et ce décommissionnement a réglé le seul point de sécurité notable.
- ❌ Migration Playwright — Cloudflare n'oppose plus de challenge, le scraping Selenium local fonctionne (566/566 pages le 16/07, run complet le 25/08).
- ❌ Scraping en datacenter / GitHub Actions.
- ❌ i18n, multi-plateforme, GUI lourde.

---

*À trier, puis à reporter dans `TODO.md`. Les constats détaillés, leurs preuves et le développement du modèle log-odds sont dans `docs/AUDIT_2026_08.md`.*
