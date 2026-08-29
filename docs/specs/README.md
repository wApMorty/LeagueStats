# 📐 Specs d'implémentation — LeagueStats Coach

**Créées** : 2026-08-29
**Base** : `docs/AUDIT_2026_08.md` (constats) · `docs/BACKLOG_2026_08.md` (priorisation)
**Destinataire** : agent d'implémentation autonome (Claude Sonnet 5, effort high) ou développeur humain.

Chaque spec est **autoportante** : elle contient l'état vérifié du code (fichiers, lignes, signatures), le travail à faire, les critères d'acceptation et les tests exigés. Aucune ne suppose la lecture des autres, sauf dépendance explicitement notée.

---

## Ordre recommandé et dépendances

```
SPEC-01  Pipeline / fiabilité          ─┐  indépendante, à faire en premier
SPEC-02  Scrape en une visite ⭐        ─┘  indépendante (touche parser/parallel_parser)

SPEC-03  Lecture lane-aware            ───┐  fondation
SPEC-04  Inférence des rôles ⭐         ───┘  DÉPEND de SPEC-03

SPEC-05  Modèle de score (log-odds)    ───   indépendante, mais à faire APRÈS 03
                                             (sinon double refonte du scoring)

SPEC-06  Quick wins                    ───   indépendante, à piocher n'importe quand
SPEC-07  Dette / tests / docs          ───   E1 (couverture) idéalement AVANT 03/04/05
```

| Spec | Items backlog | Fichiers principaux touchés | Effort |
|---|---|---|---|
| [SPEC-01](SPEC-01-pipeline-fiabilite.md) | A1–A6 | `scripts/update_all.py`, `src/data_quality.py`, `src/data_freshness.py`, `src/ui/lol_coach_legacy.py` | ~1 jour |
| [SPEC-02](SPEC-02-scrape-page-unique.md) ⭐ | C1 | `src/parser.py`, `src/parallel_parser.py`, `src/multilane.py` | ~1-2 jours |
| [SPEC-03](SPEC-03-lecture-lane.md) | B1, B2, B8 | `src/db.py`, `src/analysis/scoring.py`, `alembic/versions/` | ~2 jours |
| [SPEC-04](SPEC-04-inference-roles.md) ⭐ | B3, B4, B5 | `src/lcu_client.py`, `src/role_inference.py` (nouveau), `src/draft_monitor.py` | ~3 jours |
| [SPEC-05](SPEC-05-modele-scoring.md) | B6, B7 | `src/analysis/scoring.py`, `src/config_constants.py` | ~2 jours |
| [SPEC-06](SPEC-06-quickwins.md) | C2–C4, D1–D4, E5, E7, E8 | divers, petits | ~1 jour cumulé |
| [SPEC-07](SPEC-07-dette-tests-docs.md) | E1–E4, E6, E9, E10 | `pyproject.toml`, `README.md`, monolithes | variable |

---

## Règles communes à toutes les specs

Ces règles viennent de `CLAUDE.md` et de l'état réel du projet. Elles s'appliquent à **toute** implémentation issue de ces specs.

### Avant de commencer

```bash
git checkout -b feature/<nom> origin/master   # toujours depuis master
```

### Pendant

1. **Commits atomiques** avec Gitmoji : `✨ Feature:`, `🐛 Fix:`, `♻️ Refactor:`, `✅ Test:`, `⚡ Perf:`, `🗃️ Database:`, `📝 Docs:`
2. **Aucune valeur métier hardcodée** — tout seuil, poids ou constante va dans `src/config_constants.py`, avec un commentaire expliquant sa calibration.
3. **Requêtes SQL paramétrées** exclusivement (`cursor.execute(sql, (param,))`).
4. **Type hints** sur toute fonction publique, docstring sur toute classe et méthode publique.
5. **Pas de fichier > 500 lignes** créé. Les fichiers déjà au-dessus (`assistant.py`, `draft_monitor.py`, `db.py`, `lol_coach_legacy.py`) ne doivent **pas grossir** : si une spec demande d'y ajouter plus de ~50 lignes, créer un module dédié et déléguer.
6. **Pas d'emoji dans les sorties console** — la console Windows en cp1252 lève `UnicodeEncodeError` sur sortie redirigée. Utiliser `[OK]`, `[ALERTE]`, `[INFO]`, `[ERREUR]` (convention de `src/data_freshness.py`).

### Avant de proposer le travail

```bash
pytest tests/ -v                      # tout doit passer
python -m black src/ tests/ scripts/  # formatage obligatoire (black 26.3.1, cf. requirements-dev.txt)
python -m pylint src/ --fail-under=8.0
```

Puis mettre à jour `CHANGELOG.md` (section `[Unreleased]`) et **attendre la validation de @pj35 avant tout merge**.

### Tests

- **Tout comportement nouveau** est couvert par un test unitaire dans `tests/`.
- **Tout bug corrigé** reçoit un test de régression dans `tests/regression/`, nommé `test_regression_<sujet>.py`, avec en docstring : symptôme, cause racine, correctif, prévention (voir `tests/regression/test_regression_calculate_global_scores_delegation.py` comme modèle).
- Les tests doivent être **hermétiques** : jamais d'accès à `data/db.db` ni d'écriture dans `logs/` réels. Utiliser la fixture `temp_db` de `tests/conftest.py`, `tmp_path`, ou `monkeypatch.setattr("src.config.config.DATABASE_PATH", ...)`.

### Contexte produit à ne pas perdre de vue

- **Outil mono-utilisateur**, local, SQLite uniquement. Pas de backend, pas de multi-utilisateurs, pas d'i18n.
- La mise à jour des données est **manuelle** (menu 3 de l'application) — l'automatisation nocturne est suspendue par choix.
- La base de production contient ~26 400 matchups et ~21 300 synergies sur 173 champions, taggés sur 5 lanes (`top`, `jungle`, `middle`, `bottom`, `support`).
- Source de données : LoLalytics, scrapé en Selenium/Firefox. Le DOM change sans préavis — voir `docs/runbook_scraping.md`.
