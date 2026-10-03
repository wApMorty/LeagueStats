# LeagueStats Coach

Outil perso d'analyse et de coaching de draft pour League of Legends (173 champions, ~25 000 matchups par rôle). Python 3.13, SQLite + Alembic, Selenium, PyInstaller. Mainteneur : @pj35.
<!-- Version : src/__init__.py. Règles scopées : .claude/rules/. Procédures : .claude/skills/. -->

## Commandes

```bash
python lol_coach.py                              # point d'entrée (menus)
python -m pytest tests/ -v                       # suite complète
python -m black src/ tests/ scripts/             # formatage (aussi appliqué par un hook après chaque édition .py)
python -m alembic upgrade head                   # migrations
python scripts/update_all.py                     # pipeline de données (scrape ~45 min)
python build_app.py                              # exe PyInstaller
```

## Décisions tranchées (ne pas rouvrir)

- SQLite seul, outil mono-utilisateur : pas de backend distant (Neon, FastAPI décommissionnés).
- Cloudflare ne bloque plus : pas de Playwright. Détails dans `docs/ROADMAP_2026.md`.
- Pas de mise à jour automatique nocturne : les mises à jour sont manuelles.

## Code

- Toute valeur de réglage vit dans `src/config_constants.py` (seuils, délais, tailles), pas dans le code.
- SQL toujours paramétré (`?`), jamais de f-string.
- Type hints et docstring sur les fonctions publiques ; Black (ligne 100) fait foi pour le style.
- Sorties console sans emoji : `[OK]`, `[ALERTE]`, `[INFO]`, `[ERREUR]`, `[DATA]` (la console Windows cp1252 lève `UnicodeEncodeError` sur sortie redirigée).
- Boucle de draft du Live Coach : tout ajout est best-effort, aucune exception ne doit interrompre le monitoring en pleine partie.
- Tests hermétiques : jamais `data/db.db`, ni `logs/` réels, ni vrai client League of Legends (fixtures de `tests/conftest.py`).
- Un bug corrigé = un test de régression dans `tests/regression/`, vérifié rouge avant le fix, vert après, commités ensemble.
- Une « 1 error » en fin de suite pytest = Live Coach ouvert qui a touché `data/db.db` ou `logs/` (voir `.claude/rules/tests.md`), pas un bug du test.

## Workflow

- Travail direct sur `master` à jour. Une branche reste possible pour un chantier long.
- Commits atomiques, format `<gitmoji> Type: description` (✨ Feature, 🐛 Fix, ♻️ Refactor, ✅ Test, 📝 Docs, 🔧 Chore, ⚡ Perf, 🔒 Security, 🎨 Style, 🚀 Deploy, 🗃️ Database). Pas de ligne `Co-Authored-By`.
- IMPORTANT : ne jamais pousser sans validation explicite de @pj35. Avant un push, lancer `/ship`.
- Décision d'architecture non triviale : proposer 2-3 approches avec leurs compromis et attendre le choix de @pj35.
- Specs : `/spec <sujet>` rédige la spec et met à jour le `TODO.md` ; `/implement SPEC-NN tâches a-b` l'exécute (un commit par tâche, jamais de push).
- Release : la proposer sans attendre à la fin d'une spec ou d'un sprint du `TODO.md`, ou dès 8 entrées sous `[Unreleased]` ; la procédure est `/release`.

## Comportement attendu

- Continue jusqu'à ce que tout ce qui est demandé soit fait ; ne t'arrête que si tu es bloqué ou avant une action risquée.
- Quand le travail demandé est fait et vérifié, arrête-toi et rapporte. N'ajoute ni fonctionnalité, ni test, ni doc, ni refactor non demandés ; propose-les à la fin.
- Avant de dire « terminé » sur du code exécutable, lance un vrai check qui exerce le changement (pytest ciblé puis suite complète). Un `py_compile` seul ne compte pas.
- Pas de revue par sous-agents sauf demande ; seuls `/implement` (agent `spec-verifier`) et `/ship` (agent `test-runner`) en lancent d'office. `/code-review` à la demande de @pj35.
- Fin de tâche : 3 à 6 lignes (fait, chiffre clé, question). Le détail va dans le CHANGELOG ou le commit.

## Où chercher

- `TODO.md` backlog et sprints ; `docs/specs/` specs ; `docs/adr/` décisions ; `docs/alembic_guide.md` migrations.
- `CHANGELOG.md` : une entrée sous `[Unreleased]` par changement visible.
- `docs/PROJECT_STRUCTURE.md` pour l'arborescence (`src/analysis`, `src/draft`, `src/ui`, `src/pipeline.py`).
