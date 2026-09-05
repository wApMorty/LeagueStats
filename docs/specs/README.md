# 📐 Specs d'implémentation — lot 2026-09 (SPEC-08 à SPEC-10)

**Créées** : 2026-09-05
**Base** : analyse d'état du 2026-09-05 (vérifiée sur le code et la base de production, non publiée comme audit séparé — les constats sont intégrés dans chaque spec)
**Validé par** : @pj35, le 2026-09-05, ordre et arbitrages inclus
**Destinataire** : agent d'implémentation autonome (Claude Sonnet 5, effort max) ou développeur humain

Le lot précédent (`SPEC-01` à `SPEC-07`) est **entièrement soldé** — voir `../archive/specs/`. Les Horizons 0 à 2 de `../ROADMAP_2026.md` le sont aussi : pipeline fiable, dette de code résorbée (plus aucun fichier > 500 lignes), 990 tests verts, 65,5 % de couverture.

Ce lot change donc de nature. La question n'est plus *« qu'est-ce qui est cassé »* mais **« comment l'outil devient un meilleur conseil »**.

---

## Le fil rouge du lot

> **Le produit ne sait pas s'il a raison, et ne dit pas quand il ne sait pas.**

Deux problèmes distincts, deux specs, dans cet ordre :

- **SPEC-08** — toutes les constantes de décision du modèle sont devinées, jamais mesurées. L'infrastructure de calibration existe intégralement… et n'a jamais reçu une seule donnée, parce que fermer la boucle demande de taper une commande manuelle après la partie. 12 prédictions en base, 0 résultat renseigné.
- **SPEC-09** — sur l'écran le plus utilisé du produit, un champion sans données disparaît **sans un mot**, et 60 combos (champion, lane) qui se jouent réellement ne sont jamais scrapés.
- **SPEC-10** — le filet de sécurité sur le chemin critique temps réel, aujourd'hui à 2,6 % et 18,6 % de couverture sur ses deux maillons les plus exposés.

---

## Ordre et dépendances

```
SPEC-08  Boucle de mesure (auto-outcome LCU)  ───┐ priorité 1, indépendante
SPEC-09  Rendre l'ignorance visible           ───┘ priorité 2, indépendante (parallélisable avec 08)

SPEC-10  Couverture du chemin critique        ───  priorité 3, APRÈS 08 (qui ajoute du code dans lcu_client.py)
```

| Spec | Objet | Fichiers principaux touchés | Effort |
|---|---|---|---|
| [SPEC-08](SPEC-08-boucle-de-mesure.md) ⭐ | Résultat de partie automatique via LCU | `src/lcu_client.py`, `src/draft/outcome_tracker.py` (nouveau), `src/draft/lifecycle.py`, `src/repositories/predictions.py`, `alembic/versions/` | ~1 jour |
| [SPEC-09](SPEC-09-ignorance-visible.md) | Champions écartés affichés, seuil de lane 10 % → 5 % | `src/draft/recommendations.py`, `src/draft/automation.py`, `src/config_constants.py`, `src/pipeline.py` | ~0,5-1 jour |
| [SPEC-10](SPEC-10-couverture-chemin-critique.md) | Couverture LCU / pool_selection / champion_utils / phases | `tests/` | ~1 jour |

**Pourquoi SPEC-08 en premier** : sans elle, toute discussion sur la qualité du modèle reste une conversation d'opinions, et chaque semaine écoulée est une semaine de parties perdues pour la calibration. Elle ne change aucun comportement visible — elle rend le reste *arbitrable sur pièces*.

**Ce qui est délibérément écarté du lot** : les features candidates de `../../TODO.md` (GUI légère, intégration DraftLol, templates de composition). Elles ajoutent de la surface à un moteur dont on ne sait pas encore mesurer la qualité. À rouvrir une fois SPEC-08 alimentée en données.

---

## Règles communes à toutes les specs

Reprises de `CLAUDE.md` et de l'état réel du projet. Elles s'appliquent à **toute** implémentation issue de ces specs.

### Avant de commencer

```bash
git checkout -b feature/<nom> origin/master   # toujours depuis master, jamais depuis une autre feature
```

### Pendant

1. **Commits atomiques** avec Gitmoji : `✨ Feature:`, `🐛 Fix:`, `♻️ Refactor:`, `✅ Test:`, `⚡ Perf:`, `🗃️ Database:`, `📝 Docs:`
2. **Aucune valeur métier en dur** — tout seuil, poids ou constante va dans `src/config_constants.py`, avec un commentaire expliquant d'où vient sa valeur.
3. **Requêtes SQL paramétrées** exclusivement (`cursor.execute(sql, (param,))`).
4. **Type hints** sur toute fonction publique, docstring sur toute classe et méthode publique.
5. **Aucun fichier > 500 lignes** — le projet vient de solder cette dette, ne pas la recontracter. `src/lcu_client.py` est à 493 lignes : toute logique substantielle va dans un module dédié.
6. **Pas d'emoji dans les sorties console** — la console Windows en cp1252 lève `UnicodeEncodeError` sur sortie redirigée. Utiliser `[OK]`, `[ALERTE]`, `[INFO]`, `[ERREUR]`, `[DATA]` (convention de `src/data_freshness.py`).
7. **Best-effort dans la boucle de draft** — aucun ajout ne doit pouvoir lever une exception qui interrompt le monitoring en pleine partie.

### Avant de proposer le travail

```bash
pytest tests/ -v                      # 990 tests doivent passer, plus les nouveaux
python -m black src/ tests/ scripts/  # formatage obligatoire (black 26.3.1, cf. requirements-dev.txt)
python -m pylint src/ --fail-under=8.0
```

Puis mettre à jour `CHANGELOG.md` (section `[Unreleased]`) et **attendre la validation de @pj35 avant tout merge**.

### Tests

- **Tout comportement nouveau** est couvert par un test unitaire dans `tests/`.
- **Tout bug corrigé** reçoit un test de régression dans `tests/regression/`, nommé `test_regression_<sujet>.py`, avec en docstring : symptôme, cause racine, correctif, prévention (modèle : `tests/regression/test_regression_live_coach_lane_filter.py`).
- Les tests sont **hermétiques** : jamais d'accès à `data/db.db`, jamais d'écriture dans `logs/` réels, jamais d'appel à un vrai client League of Legends. Utiliser la fixture `temp_db` de `tests/conftest.py`, `tmp_path`, ou `monkeypatch.setattr("src.config.config.DATABASE_PATH", ...)`.

### Contexte produit à ne pas perdre de vue

- **Outil mono-utilisateur**, local, SQLite uniquement. Pas de backend, pas de multi-utilisateurs, pas d'i18n (décisions tranchées, `../ROADMAP_2026.md` §2 et §4).
- La mise à jour des données est **manuelle** (menu 3, ou `python scripts/update_all.py`) — l'automatisation nocturne est suspendue par choix.
- Base de production au 2026-09-05 : 173 champions, 25 105 matchups et 20 401 synergies sur 5 lanes, 283 combos (champion, lane).
- Source de données : LoLalytics, scrapé en Selenium/Firefox. Le DOM change sans préavis — voir `../runbook_scraping.md`.
- Le tier de référence est **Master+** (`config.LOLALYTICS_TIER`) : les volumétries valent ~40 % de l'ancien Diamond+, ce qui explique les seuils de games actuels.
