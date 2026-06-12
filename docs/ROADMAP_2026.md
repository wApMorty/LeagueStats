# 🗺️ Roadmap 2026 — LeagueStats Coach

**Date** : 2026-06-11
**Base factuelle** : `docs/AUDIT_2026_06.md` (audit complet du même jour)
**Statut** : ✅ **Validée** — les 3 décisions stratégiques ont été tranchées par @pj35 le 2026-06-11 (voir §2). Exécution lancée (Horizon 0).

Cette roadmap **remplace la priorisation de TODO.md**, dont les scores et statuts ne reflètent plus la réalité (cf. audit §2). Elle repart d'un principe simple :

> **Tant que le pipeline de données n'est pas fiable, aucune feature n'a de valeur.** Le produit est un outil d'aide à la décision : des recommandations calculées sur des données amputées de 60% et vieilles de 3 mois (mode distant) sont pires qu'inutiles — elles sont trompeuses.

---

## 1. Remise en Question du Backlog Existant (TODO.md)

Revue tâche par tâche, avec verdict :

| # | Tâche (TODO.md) | Statut TODO | Verdict roadmap | Justification |
|---|---|---|---|---|
| 16 | Support Synergies | ❌ Not started | ✅ **Clore — c'est fait** | Implémenté depuis jan. 2026 (table, scraping, scoring, tests) |
| 17 | Optimisation Performance API Neon | ❌ À faire, ROI 2.60 | 🗑️ **Supprimer** | L'API FastAPI a été retirée du client en 1.2.0. On n'optimise pas un composant abandonné |
| 12 | Architecture Client-Serveur + Web App SaaS | ❌, ROI 0.62 | 🗑️ **Abandonner formellement la vision SaaS** | Projet mono-utilisateur ; la tentative (server/ + Render) a déjà échoué sur les free tiers ; le coût de maintenance (duplication code, déploiement, auth, multi-users) est sans rapport avec le bénéfice. Avec la Décision C, Neon disparaît aussi : SQLite local uniquement |
| 6 | Interface Graphique (GUI) | ❌, ROI 0.62 | ⏸️ **Reporter, re-scoper** | À reconsidérer en Horizon 3 sous forme légère (web UI locale type FastAPI+HTMX servie par l'app, ou overlay), pas en PyQt full rewrite |
| 8 | Internationalisation | ❌, ROI 0.60 | 🗑️ **Supprimer** | Un seul utilisateur, francophone. Aucune plus-value |
| 15 | Support des Lanes | ❌, ROI 1.00 | ✅ **Garder — promu priorité haute** | Devenu *plus* pertinent : la perte de données du 01/06 vient précisément de l'absence de modélisation des lanes. La migration de schéma (colonne `lane`) doit accompagner la reconstruction du pipeline (Horizon 1), le scoring lane-aware peut venir ensuite |
| 18 | Migration Playwright (jamais dans TODO.md) | Branche orpheline | 🗑️ **Archiver (tranché)** | Cloudflare a retiré son challenge (Décision A) : le chantier n'a plus d'objet. Tag `archive/playwright-migration` puis suppression de la branche (Horizon 0) |
| — | Backlog long terme (Discord bot, ML, mobile, cloud sync…) | Idées | ⏸️ Inchangé | Ne pas y toucher avant Horizon 3 |

**Méta-problème** : TODO.md fait 88 Ko, contient du code d'exemple périmé et des statuts contradictoires. → **Action** : le réécrire en backlog maigre (~100 lignes : tableau + 5 lignes par tâche max), et archiver l'actuel.

---

## 2. Les 3 Décisions Stratégiques à Trancher d'Abord

### Décision A — Source de données : comment sortir de la guerre contre Cloudflare ?

> **✅ TRANCHÉ (2026-06-11)** : **le chantier est annulé — Cloudflare a retiré son challenge sur LoLalytics.** Le scraping Selenium local fonctionne sans mitigation. Conséquences :
> - Pas de migration Playwright, pas de profil cookies CF, pas de source alternative à explorer. La branche `feature/playwright-migration` peut être archivée (tag) puis supprimée.
> - Toute la machinerie anti-CF (`cloudflare_detector.py`, attentes 120 s, délais aléatoires, `FIREFOX_PROFILE_PATH`) devient **candidate à simplification en Horizon 2** — on la garde fonctionnelle d'ici là (les tests de régression CF doivent continuer à passer tant que le code existe).
> - Le pipeline redevient un simple problème d'**automatisation locale** (Horizon 1), plus un problème d'anti-bot.

Analyse d'origine conservée pour mémoire :

| Option | Description | Pour | Contre | Effort |
|---|---|---|---|---|
| **A1. Scraping local consolidé** ⭐ recommandée | Abandonner le scraping en datacenter (GitHub Actions = IP bannies par CF). Tout faire depuis le PC résidentiel : Task Scheduler relancé, `fill_db.py` industrialisé (scores + bans + sync Neon + multi-lane), profil Firefox avec cookie `cf_clearance` (le support existe déjà : `FIREFOX_PROFILE_PATH`) | IP résidentielle ≈ pas de blocage CF (preuve : le run manuel du 01/06 a réussi 172/172 en headless) ; réutilise 90% de l'existant ; zéro coût | PC doit être allumé ; reste fragile aux changements DOM | 1-2 sem |
| A2. Reprendre Playwright + stealth | Recycler `feature/playwright-migration`, en local (pas en Actions) | Stack plus moderne, meilleurs outils anti-détection, auto-wait (moins de bugs « stale element ») | Re-tester tout le parsing ; le revert du 01/06 suggère des problèmes non documentés — faire un post-mortem d'abord | 2-3 sem |
| A3. Source de données alternative | Calculer les stats soi-même via l'API officielle Riot (match-v5) ou explorer les endpoints JSON non documentés de LoLalytics | Sortie définitive de la dépendance scraping ; données possédées | API Riot : volumétrie énorme pour des stats de matchups fiables (rate limits, des millions de matchs à agréger) — irréaliste en solo ; endpoints LoLalytics : fragiles juridiquement et techniquement | 4 sem+ / risqué |
| A4. Statu quo | Continuer à réparer au fil de l'eau | Aucun investissement initial | C'est la stratégie des 6 derniers mois ; elle a produit la situation actuelle | ∞ |

~~**Recommandation** : **A1 maintenant**, avec A2 en plan B documenté si LoLalytics re-casse le DOM.~~ → Caduc, voir encadré ci-dessus. `scraping.yml` est **supprimé** dans tous les cas (il échouait à 100%, coûtait ~60h de minutes/mois, et alimentait Neon qui est abandonné — voir Décision C).

### Décision B — Cible produit : outil personnel ou service ?

> **✅ TRANCHÉ (2026-06-11)** : **outil personnel.** L'API FastAPI/Render est archivée, la vision SaaS (Tâche #12) est officiellement enterrée, la duplication `server/src/analysis` disparaît avec `server/` (Horizon 2).

Tout TODO.md oscille entre « outil perso » et « SaaS multi-users » (Tâche #12). La réponse engage l'architecture, la sécurité (credentials dans le .exe) et la dette server/.

**Recommandation retenue** : **assumer l'outil personnel**. Conséquences :
- `server/src/api/` (FastAPI Render) → suppression ou archivage ; Neon ne sert plus que de « SQLite distant » synchronisé.
- La duplication `server/src/analysis` ↔ `src/analysis` disparaît avec elle (seul `server/scripts/` + modèles SQLAlchemy survivent si on garde la sync Neon).
- Le risque « connection string dans le .exe » reste acceptable (lecteur unique) — sinon il faudrait un vrai backend, qu'on vient d'écarter.

### Décision C — Couche données : combien de modes ?

> **✅ TRANCHÉ (2026-06-11)** : **SQLite uniquement** — @pj35 ne joue plus en déplacement, le mode nomade n'a plus de raison d'être. C'est la simplification maximale :
> - Suppression côté client : `PostgreSQLDataSource`, `HybridDataSource`, `APIDataSource` (zombie), `credentials.py` (la chaîne de connexion committée disparaît — le point sécurité de l'audit §6 se règle de lui-même), la logique de mode auto (`api_config.MODE`) et les dépendances `sqlalchemy/asyncpg` du client.
> - Décommissionnement : sync Neon (`sync_local_to_neon.py`), base Neon elle-même, `scraping.yml`, et à terme `server/` (avec Décision B).
> - `Assistant` ne connaît plus que `SQLiteDataSource` → des centaines de lignes et ~10 fichiers de tests en moins à maintenir.
> - `OFFLINE_FIRST_PLAN.md` : définitivement obsolète, archivé.
>
> *Réversibilité* : si le besoin nomade revient un jour, la solution simple est d'embarquer `data/db.db` dans le package .exe (c'était déjà le cas) — pas de réintroduire un backend.

Aujourd'hui : 4 implémentations `DataSource` (dont 1 zombie) × 3 modes. Pour un utilisateur, c'est trop — d'où la décision ci-dessus.

---

## 3. Plan d'Exécution par Horizons

### 🚨 Horizon 0 — « Arrêter l'hémorragie » (cette semaine, ~1-2 jours d'effort)

Objectif : plus rien ne brûle en arrière-plan, master redevient vert.

1. **Supprimer `scraping.yml`** — stoppe 2h/nuit de runner gaspillé (et son destinataire, Neon, est abandonné — Décision C).
2. **Réparer la CI** :
   - Corriger la régression réelle : `parallel_parser.py:262` doit laisser remonter `CloudflareException` (le test de régression a fait son travail — c'est le code qui est faux, pas le test).
   - Corriger `sync_local_to_neon` : exit 1 sans `DATABASE_URL` (fix minimal en attendant la suppression complète du chemin Neon en H2).
   - Corriger le score pylint du parser réécrit.
   - Corriger la condition du job build : `refs/heads/master` (il n'a **jamais** tourné).
3. **Recalculer `champion_scores` et `pool_ban_recommendations`** sur les données du 01/06 (les tier lists et bans actuels sont calculés sur l'ancienne BD).
4. **Hygiène express** : supprimer `NUL`, déplacer `fill_db.log`, archiver la branche `feature/playwright-migration` (tag `archive/playwright-migration` puis suppression — chantier annulé, CF retiré).

**Critère de sortie** : CI verte sur master ; aucun job planifié en échec ; scores cohérents avec les matchups en BD.

### 🔴 Horizon 1 — « Pipeline de données fiable » (2-4 semaines)

Objectif : des données complètes, fraîches, multi-lane, sans intervention manuelle. C'est l'implémentation de la Décision A (+ le schéma de la Tâche #15).

1. **Migration Alembic `lane`** sur `matchups`/`synergies` (+ index composites) — préalable à tout re-scrape multi-lane, et fondation de la Tâche #15.
2. **Industrialiser `fill_db.py` → `scripts/update_all.py`** : scrape multi-lane (lanes à pickrate >10%) → recalcul `champion_scores` → recalcul `pool_ban_recommendations` → notification (Windows + Discord webhook, le secret existe déjà) → patch version en config, plus de `PATCH = "14"` hardcodé. *(Plus de sync Neon — Décision C.)*
3. **Relancer l'automatisation locale** (Task Scheduler, nuit) avec **monitoring de fraîcheur** : au lancement, l'app affiche l'âge des données et alerte si >7 jours (le garde-fou qui a manqué : personne n'a vu que l'auto-update était mort depuis le 19/03, ni que la BD avait perdu 60% de ses lignes).
4. **Test de complétude post-scrape** : assertion volumétrique (ex. ≥200 matchups/champion toutes lanes confondues, 172/172 champions) qui échoue bruyamment — la perte silencieuse 40k→16k ne doit plus pouvoir se reproduire.
5. Documenter le **runbook** : que faire quand LoLalytics casse (diagnostic DOM, sélecteurs à vérifier, et marche à suivre si Cloudflare réapparaît un jour).

**Critère de sortie** : 2 semaines consécutives de mises à jour nocturnes réussies, volumétrie ≥ niveau de mars (≈40k matchups).

### 🟠 Horizon 2 — « Dette technique 2.0 » (3-4 semaines, parallélisable partiellement avec H1)

Objectif : réaliser les Décisions B et C, et re-payer la dette re-contractée depuis le Sprint 1.

1. **Décommissionner toute la couche données distante** (Décisions B + C, tranchées) : supprimer `APIDataSource`, `PostgreSQLDataSource`, `HybridDataSource`, `credentials.py` (chaîne de connexion committée — règle le point sécurité de l'audit §6), la logique de mode auto (`api_config.MODE` / `sys.frozen`), les dépendances `sqlalchemy`/`asyncpg` du client, `scripts/sync_local_to_neon.py` + ses tests. `Assistant` ne dépend plus que de `SQLiteDataSource`.
2. **Supprimer `server/`** intégralement (API FastAPI Render, duplication `server/src/analysis`, modèles SQLAlchemy, `server/requirements.txt` dans la CI) et fermer la base Neon.
3. **Démanteler `lol_coach_legacy.py`** (2 356 lignes, 0% testé, « temporaire » depuis 18 mois) : découpage par menu/feature dans `src/ui/`, avec tests de caractérisation d'abord.
4. **Re-dégraisser `assistant.py`** (1 843 lignes) : les méthodes draft/competitive/holistic ont leur place dans `analysis/` — c'était le plan du Sprint 1, à terminer cette fois.
5. **Couverture là où ça compte** : `draft_monitor.py` (22%) et le chemin LCU sont le cœur du produit. Élargir la mesure de coverage de `pyproject.toml` au-delà de `src/analysis` (quitte à baisser temporairement le seuil) pour que la métrique cesse de mentir.
6. **Docs** : réécrire TODO.md (backlog maigre), README, PROJECT_STRUCTURE ; créer `docs/archive/` pour AUDIT_REPORT 2025, API_PERFORMANCE_ISSUES, OFFLINE_FIRST_PLAN ; régénérer l'index `docs/README.md` ; **unifier la version** (recommandé : 1.3.0 à la sortie d'H1) entre `src/__init__.py`, README, CLAUDE.md, CHANGELOG.

**Critère de sortie** : plus aucun fichier >800 lignes (étape vers les 500), 0 duplication client/serveur, couverture globale mesurée honnêtement ≥50%, docs racine exactes.

### 🟢 Horizon 3 — « Valeur joueur » (ensuite, par appétit)

À ne lancer qu'avec un pipeline vert et une dette maîtrisée. Par ordre de ROI estimé :

1. **Tâche #15 partie 2 — scoring lane-aware** : exploiter la colonne `lane` (détection via LCU `get_assigned_position()`, pondération same-lane). Les données seront déjà là grâce à H1 — il ne reste que le scoring + UX. *(L'essentiel de la difficulté initialement estimée à 13 aura été absorbé par H1.)*
2. **UX de confiance** : affichage systématique de la fraîcheur des données + volumétrie dans l'app (déjà amorcé en H1) ; indicateurs de fiabilité par recommandation (nb de games du matchup).
3. **GUI légère** (ex-Tâche #6 re-scopée) : panneau web local (FastAPI + HTMX/React léger servi sur localhost) plutôt qu'un rewrite desktop — réutilise les algos en l'état.
4. **Intégration sites de draft** (recherche déjà faite : `DRAFT_SITES_INTEGRATION_RESEARCH.md`) : valeur forte pour les tournois, mais dépend du reverse-engineering WebSocket DraftLol — spike de 1-2 jours avant d'engager.
5. Backlog long terme inchangé (Discord bot, overlay, ML…) — à re-prioriser à ce moment-là.

---

## 4. Ce que cette Roadmap Refuse Explicitement

Pour mémoire (et pour éviter que ces sujets ne reviennent par la fenêtre) :

- ❌ **Vision SaaS multi-utilisateurs** (Tâche #12) — coût/bénéfice sans rapport avec un outil perso ; déjà tenté, déjà échoué sur free tiers.
- ❌ **Optimisation de l'API FastAPI** (Tâche #17) — composant abandonné.
- ❌ **i18n** (Tâche #8), **multi-plateforme** (déjà annulée).
- ❌ **Scraping en datacenter** (GitHub Actions) — IP bannies par le passé, et plus aucun destinataire (Neon abandonné). Le scraping reste local.
- ❌ **Maintenir le chemin Neon/PostgreSQL/Hybrid** (Décision C) — toute réintroduction d'un backend distant est hors-jeu ; si le besoin nomade revient, embarquer `data/db.db` dans le .exe.
- ❌ **Reprendre la migration Playwright** (Décision A) — chantier annulé, CF a retiré son challenge ; le tag `archive/playwright-migration` suffit comme mémoire.
- ❌ Nouvelle feature **avant** la sortie d'Horizon 1 — c'est la règle « Dette Technique First » du projet, appliquée pour de vrai cette fois.

---

## 5. Tableau de Bord de Suivi

Métriques à vérifier à chaque fin d'horizon (toutes mesurables en une commande) :

| Métrique | Aujourd'hui (11/06) | Cible H0 | Cible H1 | Cible H2 |
|---|---|---|---|---|
| CI master | 🔴 rouge depuis 24/05 | 🟢 verte | verte | verte |
| Tests | 608 ✅ / 2 ❌ | 610 ✅ / 0 ❌ | +tests volumétrie | +tests UI/draft |
| Matchups en BD | 16 179 (mono-lane) | — | ≥40 000 (multi-lane taggé) | — |
| Âge données (BD locale) | 11 j (01/06) | scores recalculés sur BD du 01/06 | ≤24 h auto | ≤24 h auto |
| Minutes Actions gaspillées | ~60 h/mois | 0 | 0 | 0 |
| Plus gros fichier | 2 356 lignes | — | — | ≤800 lignes |
| Couverture globale (mesurée honnêtement) | 34,9% | — | — | ≥50% |
| Docs racine exactes | non | — | — | oui (version unifiée) |

---

*Document généré dans le cadre de l'audit du 2026-06-11 — à faire évoluer comme source de vérité de la priorisation, en remplacement de la section « Vue d'Ensemble » de TODO.md.*
