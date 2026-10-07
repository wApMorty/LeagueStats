# LeagueStats Coach

[![CI/CD Pipeline](https://github.com/wApMorty/LeagueStats/actions/workflows/ci.yml/badge.svg)](https://github.com/wApMorty/LeagueStats/actions/workflows/ci.yml)
[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

Outil personnel d'analyse et de coaching de draft pour League of Legends : recommandations de picks/bans en direct pendant la sélection des champions, et recherche de compositions d'équipe optimales à partir de statistiques de matchups scrapées sur LoLalytics.

## Démarrage

```bash
pip install -r requirements.txt
python lol_coach.py
```

Menu principal :

1. **Draft Coach en temps réel** — suit le champion select via le client League of Legends (LCU) et recommande picks/bans ; au lock-in, importe dans le client les runes, items et sorts les plus joués par les one-tricks (OneTricks.gg), affinés contre l'adversaire direct (désactivable : `draft_config.AUTO_IMPORT_LOADOUT`) ; après chaque partie SoloQ/Flex, le coach de gameplay compare tes stats à ta norme et aux one-tricks Master+, et suit tes axes de travail (commandes `bilan` et `axe <métrique>`)
2. **Mettre à jour les données** — récupère la liste des champions depuis l'API Riot
3. **Analyser des statistiques** — scrape les matchups (pool SoloQ ou tous les champions)
4. **Analyse & Tournoi** — analyse statistique, coaching manuel de tournoi et bilan du coach de gameplay
5. **Constructeur d'équipe** — recherche des meilleures combinaisons de champions (duos/trios)
6. **Gérer les pools** — création et gestion de pools de champions personnalisées
7. **Client LeagueStats** — fenêtre native (aussi `python lol_coach.py --client`) qui parle au client League of Legends : **draft interactive** (bans, picks avec leur numéro d'ordre, échanges d'ordre et de rôle, grimoire des champions, skins, runes et sorts, clic pour survoler et verrouiller), **partie trouvée**, **En partie** (win chance et courbe en direct, face-à-face de la draft, plan de build avec suivi des achats, lecture seule), section **Coaching** (accueil avec axes de travail, rang, progression, parties, calibration) et **revue de partie** à la fin de chaque partie classée ; une pastille de la barre de titre indique à tout moment la phase de jeu (hors partie, en file, champion select, en partie, fin de partie). Les écrans **Client** lisent le client LoL : **profil** (rangs, régalia, défis), **historique** des 20 dernières parties (détail et lien vers l'analyse du Live Coach), **collection** (champions, runes, sets d'objets), **lobby** (ouvrir une file, choisir ses postes, quitter), **file d'attente** (lancer, annuler depuis la barre de titre) et **social** en lecture seule ; `python build_app.py` embarque le tout dans l'exécutable.
8. Quitter

## Mise à jour des données

Les statistiques de matchups sont scrapées sur LoLalytics avec Selenium/Firefox, en parallèle sur les 5 rôles (top/jungle/mid/bottom/support). Un scrape complet prend environ **45 minutes** avec 5 workers.

```bash
python scripts/update_all.py
```

C'est l'implémentation de référence (contrôle de complétude, sauvegarde avant réécriture, log dans `logs/update_all.log`). Le menu 3 de `lol_coach.py` s'appuie sur le même pipeline.

Il n'y a pas de mise à jour automatique planifiée : l'automatisation nocturne a été désactivée par choix, la mise à jour reste manuelle.

## Distribution

Créer un exécutable Windows portable (aucun Python requis sur le PC cible) :

```bash
python build_app.py           # Génère l'exécutable
python create_package.py      # Génère le ZIP de distribution
```

## Structure du projet

```
LeagueStats/
├── lol_coach.py          # Point d'entrée de l'application
├── build_app.py           # Build de l'exécutable
├── create_package.py      # Empaquetage de la distribution
├── scripts/
│   └── update_all.py      # Pipeline de mise à jour des données (référence)
├── src/
│   ├── analysis/          # Algorithmes de scoring, agrégation, tier lists
│   ├── ui/                # Menus et affichage
│   ├── db.py, config.py, config_constants.py, ...
│   └── ...
├── data/db.db              # Base SQLite (champions, matchups, synergies)
├── tests/                  # Suite pytest
└── docs/                   # Documentation (specs, audits, guides)
```

## Prérequis

- Python 3.13+
- Firefox (scraping des matchups)
- Client League of Legends en cours d'exécution (pour le Draft Coach en temps réel, via l'API LCU locale)

Pour la version distribuée (exécutable) : Windows 10/11, League of Legends installé, Firefox pour les mises à jour de données. Aucun Python requis.

## Base de données

SQLite uniquement (`data/db.db`), en local. Contenu à titre indicatif — évolue à chaque scrape, voir `data/db.db` (table `db_meta`) pour l'état courant :

- ~173 champions
- ~25 000 matchups par rôle
- pools de champions personnalisées

Migrations de schéma : Alembic (voir `docs/alembic_guide.md`).

## Tests

```bash
pytest tests/ -v
```

La CI mesure la couverture sur tout `src/` avec un seuil minimum de 45 % (`pyproject.toml`), destiné à monter au fil des chantiers.

## Documentation

- `CLAUDE.md` — instructions de développement et conventions du projet
- `TODO.md` — backlog priorisé
- `docs/specs/` — spécifications d'implémentation par chantier
- `docs/DATABASE_STRUCTURE.md` — schéma de la base
- `docs/alembic_guide.md` — commandes de migration

## Historique des versions

Voir `CHANGELOG.md`.

---

**Version** : 4.3.1
