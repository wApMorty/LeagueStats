---
paths:
  - "src/db.py"
  - "alembic/**"
---

# Base de données (SQLite + Alembic)

- Requêtes toujours paramétrées : `cursor.execute("... WHERE name = ?", (name,))`, jamais de f-string dans le SQL.
- Une migration = `python -m alembic revision -m "..."`, avec `upgrade()` et `downgrade()` écrits à la main (voir `docs/alembic_guide.md`).
- Tester la migration sur une copie de `data/db.db`, jamais sur la vraie base.
- Un changement de schéma exige une action utilisateur (`alembic upgrade head`) : le mentionner en tête de l'entrée CHANGELOG (version majeure).
