# 📐 Specs d'implémentation — lot 2026-09 (SPEC-08 à SPEC-11)

**Créées** : 2026-09-05 (SPEC-08 à SPEC-10), complétées le 2026-09-06 (SPEC-11)
**Base** : analyse d'état du 2026-09-05 (vérifiée sur le code et la base de production, non publiée comme audit séparé — les constats sont intégrés dans chaque spec)
**Validé par** : @pj35, le 2026-09-05, ordre et arbitrages inclus
**Destinataire** : agent d'implémentation autonome (Claude Sonnet 5, effort max) ou développeur humain — sauf SPEC-11, note de cadrage non actionable (voir son statut)

Le lot précédent (`SPEC-01` à `SPEC-07`) est **entièrement soldé** — voir `../archive/specs/`. Les Horizons 0 à 2 de `../ROADMAP_2026.md` le sont aussi : pipeline fiable, dette de code résorbée (plus aucun fichier > 500 lignes), 990 tests verts, 65,5 % de couverture.

Ce lot change donc de nature. La question n'est plus *« qu'est-ce qui est cassé »* mais **« comment l'outil devient un meilleur conseil »**.

---

## Le fil rouge du lot

> **Le produit ne sait pas s'il a raison, et ne dit pas quand il ne sait pas.**

Deux problèmes distincts, deux specs, dans cet ordre :

- **SPEC-08** — toutes les constantes de décision du modèle sont devinées, jamais mesurées. L'infrastructure de calibration existe intégralement… et n'a jamais reçu une seule donnée, parce que fermer la boucle demande de taper une commande manuelle après la partie. 12 prédictions en base, 0 résultat renseigné.
- **SPEC-09** — sur l'écran le plus utilisé du produit, un champion sans données disparaît **sans un mot**, et 60 combos (champion, lane) qui se jouent réellement ne sont jamais scrapés.
- **SPEC-10** — le filet de sécurité sur le chemin critique temps réel, aujourd'hui à 2,6 % et 18,6 % de couverture sur ses deux maillons les plus exposés.
- **SPEC-11** — pas un bug, une ambition produit (@pj35, 2026-09-06) : faire évoluer le modèle prédictif vers une pondération par lane restante puis, à terme, une recherche façon Stockfish sur l'arbre de draft. Note de cadrage, explicitement **bloquée** tant que SPEC-08 n'a pas produit une première calibration réelle — chercher profond sur une évaluation non calibrée amplifierait ses erreurs plutôt que de les corriger.

---

## Ordre et dépendances

```
SPEC-08  Boucle de mesure (auto-outcome LCU)  ───┐ priorité 1, indépendante
SPEC-09  Rendre l'ignorance visible           ───┘ priorité 2, indépendante (parallélisable avec 08)

SPEC-10  Couverture du chemin critique        ───  priorité 3, APRÈS 08 (qui ajoute du code dans lcu_client.py)

SPEC-11  Lane restante + recherche Stockfish  ───  🔵 recherche, APRÈS 08 + une calibration réelle
                                                    (scripts/calibrate_model.py, ~30 parties labellisées)
```

| Spec | Objet | Fichiers principaux touchés | Effort |
|---|---|---|---|
| [SPEC-08](SPEC-08-boucle-de-mesure.md) ⭐ | Résultat de partie automatique via LCU | `src/lcu_client.py`, `src/draft/outcome_tracker.py` (nouveau), `src/draft/lifecycle.py`, `src/repositories/predictions.py`, `alembic/versions/` | ~1 jour — ✅ mergée le 2026-09-06 |
| [SPEC-09](SPEC-09-ignorance-visible.md) | Champions écartés affichés, seuil de lane 10 % → 5 % | `src/draft/recommendations.py`, `src/draft/automation.py`, `src/config_constants.py`, `src/pipeline.py` | ~0,5-1 jour — ✅ mergée le 2026-09-06 |
| [SPEC-10](SPEC-10-couverture-chemin-critique.md) | Couverture LCU / pool_selection / champion_utils / phases | `tests/` | ~1 jour |
| [SPEC-11](SPEC-11-lane-restante-et-recherche.md) 🔵 | Pondération par lane restante, puis recherche minimax | `src/analysis/scoring.py` (à terme) | non estimé — non actionable |

**Pourquoi SPEC-08 en premier** : sans elle, toute discussion sur la qualité du modèle reste une conversation d'opinions, et chaque semaine écoulée est une semaine de parties perdues pour la calibration. Elle ne change aucun comportement visible — elle rend le reste *arbitrable sur pièces*, y compris l'ambition de SPEC-11.

**Ce qui est délibérément écarté du lot** : les features candidates de `../../TODO.md` (GUI légère, intégration DraftLol, templates de composition). Elles ajoutent de la surface à un moteur dont on ne sait pas encore mesurer la qualité. À rouvrir une fois SPEC-08 alimentée en données.

---

## Lot suivant — notes de features (@pj35, à partir du 2026-09-23)

Specs issues de notes de features au fil de l'eau, chacune indépendante sauf mention contraire.

| Spec | Objet | Fichiers principaux touchés | Effort |
|---|---|---|---|
| [SPEC-14](SPEC-14-draft-finale-head-to-head.md) ✅ | Draft finale en tableau face-à-face ordonné par lane, avec flèche et valeur du duel direct | `src/draft/final_analysis.py`, `src/analysis/game_eval.py`, `src/config_constants.py` | ~0,5 jour |
| [SPEC-15](SPEC-15-import-runes-items.md) | Runes, items et sorts poussés dans le client au lock-in, build OneTricks générale puis affinée au duel ([ADR-003](../adr/ADR-003-onetricks-temps-reel.md)) | `src/draft/loadout.py` (nouveau), `src/draft/lifecycle.py`, `src/config_constants.py` | ~1,5 j |
| [SPEC-16](SPEC-16-moteur-optimisation-builds.md) ⏸️ | Moteur d'optimisation des builds : shrinkage mesuré (A), puis correction par les patchs (A+) ([ADR-002](../adr/ADR-002-moteur-optimisation-builds.md)) | `src/analysis/build_engine.py`, `src/analysis/patch_diff.py` (nouveaux) | Reportée : A avec le spike Coachless, A+ abandonnée (ADR-003) |
| [SPEC-17](SPEC-17-recherche-plus-profonde.md) ✅ | Recherche minimax : candidats par popularité, lane des alliés, cache des paires ; multi-processus en phase 2 conditionnelle | `src/draft/search.py`, `src/analysis/game_eval.py`, `src/draft/state_parser.py`, `src/repositories/matchups.py` | Phase 1 implémentée le 2026-09-24 (B1 5, B2 7/7) ; phase 2 non ouverte |
| [SPEC-18](SPEC-18-force-intrinseque.md) 🟢 | Tier list et blind pick classés au winrate de lane rétréci (`avg_delta2` est du bruit) ; terme de force intrinsèque du modèle décidé sur mesure | `src/analysis/shrink.py`, `src/analysis/tier_list.py`, `src/draft/automation.py`, `scripts/compare_intrinsic_strength.py` | Phase A implémentée le 2026-09-24 ; phase B reportée (IC d'AUC contient 0) |
| [SPEC-19](SPEC-19-coach-de-gameplay.md) 🟢 | Coach de gameplay : capture LCU des parties SoloQ/Flex, grille de lecture par rôle, écarts à la norme et à l'objectif en fin de partie, schémas récurrents, suivi des LP et axes de travail | `src/coaching/` (nouveau), `src/lcu_match_history.py`, `alembic/versions/` | ~6,5 j sur 4 phases ; validée le 2026-09-26, spike à lancer |
| [SPEC-20](SPEC-20-win-chance-et-impact.md) 🟡 | Win chance en partie (logistique entraînée sur des parties tierces collectées via le LCU), impact de chaque événement attribué aux joueurs, overlay en jeu | `src/winprob/` (nouveau), `src/lcu_match_history.py`, `data/crawl.db` | ~8 j sur 5 phases ; ordre validé le 2026-10-01, arbitrages §2 à valider |
| [SPEC-21](SPEC-21-tableau-de-bord-local.md) 🟡 | **Client LeagueStats** : fenêtre `pywebview` sur FastAPI, interface enhanced du client LoL par le LCU (profil, historique, collection, lobby/file, social en lecture seule), section Coaching complète, draft interactive et post-game avec le Live Coach, motion design poussé | `src/client/` (nouveau), `src/config_client.py`, `src/draft/snapshot.py`, `src/winprob/report.py`, `src/analysis/calibration.py`, `lol_coach.py`, `LeagueStatsCoach.spec` | ~33 j, 37 tâches (48 à 56, 68 à 95, 163 pts) en six lots ; réécrite le 2026-10-04 (forme, périmètre, fenêtre sans bordure validés), plan revu le 2026-10-05 après le handoff de design « Alchimie » (fiche par écran, §4.10) ; ordre des lots, fenêtre, thème clair reporté et écrans sans maquette validés le 2026-10-05, écritures du coaching validées le 2026-10-05 ; tâches 48, 49, 68 et 70 faites le 2026-10-04 (socle, coque, temps réel), 69, 84 (banc de mesure), 55 (lancement), tout le lot 2 (draft : 72 à 74, 85 à 92) et le lot 3 (file trouvée, transition : 93 et 94) et le lot 4 (coaching et post-game : 50 à 54, 71, 75, 95, 56) le 2026-10-05, puis le lot 5 (profil et historique : 76 à 78) et le lot 6 (collection, lobby, file, social, clôture : 79 à 83) le 2026-10-05, soit 163 pts sur 163 ; reste la recette de @pj35 |
| [SPEC-22](SPEC-22-attribution-complete-impact.md) 🟡 | Attribution complète de l'impact : objectifs perdus débités aux absents, niveaux face à l'adversaire de lane, récupération après respawn ; le résidu « non attribué » (−20 pts mesurés) ne garde que la valeur du temps | `src/winprob/impact.py`, `src/winprob/state.py`, `src/winprob/model.py`, `src/winprob/report.py`, `src/repositories/coaching.py` | ~2 j, tâches 57 à 61 (16 pts) ; périmètre validé le 2026-10-04, trois conventions à valider |
| [SPEC-23](SPEC-23-debit-collecte-concurrent.md) 🟡 | Débit de la collecte SPEC-20 : pool de threads (requêtes seules, écritures dans la boucle), spike par paliers sur copie de `crawl.db`, débit réduit en partie, croisière à la cible ; les 30 000 req/10 min ne bornent pas le LCU, plafond de référence 50 req/s | `src/winprob/crawl.py`, `src/lcu_client.py`, `src/config_winprob.py`, `src/draft/lifecycle.py`, `scripts/bench_crawl_rate.py` (nouveau) | ~2 j, tâches 62 à 67 (16 pts) ; architecture et critère d'arrêt validés le 2026-10-04, cible et croisière à valider |
| [SPEC-24](SPEC-24-retours-gui-bans-ordre-en-partie.md) 🟡 | Retours sur le client : bans qui n'arrivent pas dans le client LoL (relevé réel puis correctif), `current_actor` faux à la cellule 0, ordre de pick affiché, swaps d'ordre et de rôle (boutons et conseil chiffré), écran « En partie » (analyse de la draft, build et suivi des achats, courbe de win chance) ; rouvre SPEC-21 §7 | `src/client/draft_actions.py`, `src/client/draft_swaps.py` (nouveau), `src/client/ingame.py` (nouveau), `src/draft/state_parser.py`, `src/draft/snapshot.py`, `src/draft/swap_advice.py` (nouveau), `src/draft/final_analysis.py`, `src/lcu_client.py` | ~8 j, tâches 96 à 111 (61 pts) en trois lots ; rédigée le 2026-10-06, arbitrages §2 à valider ; ✅ livrée le 2026-10-07 (103 sans conseil d'ordre), recettes @pj35 à faire |

---

## Règles communes à toutes les specs

Les règles de développement (workflow, tests, SQL, constantes, gitmoji) vivent dans `CLAUDE.md` et
`.claude/rules/`, pas ici. Une spec se rédige avec `/spec` (gabarit : `.claude/skills/spec/template.md`)
et s'implémente avec `/implement SPEC-NN tâches a-b`.

Conventions propres aux specs :

- Chaque spec se termine par des **critères d'acceptation** numérotés, chacun vérifiable par une commande
  ou une lecture : c'est ce que `/implement` et l'agent `spec-verifier` contrôlent.
- Le découpage en tâches (numéro global, points Fibonacci, dépendances) vit dans la spec **et** dans `TODO.md`.
- Un arbitrage non tranché est marqué « à valider » ; `/implement` s'arrête devant lui.

### Contexte produit à ne pas perdre de vue

- **Outil mono-utilisateur**, local, SQLite uniquement. Pas de backend, pas de multi-utilisateurs, pas d'i18n (décisions tranchées, `../ROADMAP_2026.md` §2 et §4).
- La mise à jour des données est **manuelle** (menu 3, ou `python scripts/update_all.py`) — l'automatisation nocturne est suspendue par choix.
- Source de données : LoLalytics, scrapé en Selenium/Firefox. Le DOM change sans préavis — voir `../runbook_scraping.md`.
- Le tier de référence est **Master+** (`config.LOLALYTICS_TIER`) : les volumétries valent ~40 % de l'ancien Diamond+, ce qui explique les seuils de games actuels.
