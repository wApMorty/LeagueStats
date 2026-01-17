# Guide Alembic - Database Migrations

Ce guide décrit l'utilisation d'Alembic pour gérer les migrations de base de données dans LeagueStats Coach.

---

## Commandes Essentielles

### Check current migration version
```bash
python -m alembic current
```

### View migration history
```bash
python -m alembic history
```

### Upgrade to latest version (head)
```bash
python -m alembic upgrade head
```

### Downgrade to previous version
```bash
python -m alembic downgrade -1
```

### Downgrade to specific version
```bash
python -m alembic downgrade <revision_id>
```

### Downgrade to base (empty database)
```bash
python -m alembic downgrade base
```

### Create new migration (manual)
```bash
python -m alembic revision -m "Description of changes"
```

### Create new migration with autogenerate (requires SQLAlchemy models)
```bash
python -m alembic revision --autogenerate -m "Description"
```

### Show SQL without executing (dry-run)
```bash
python -m alembic upgrade head --sql
```

---

## Important Notes

- ✅ **Always backup database** before running migrations in production
- ✅ **Test migrations locally** before deploying
- ✅ Database path configured in `alembic.ini`: `sqlite:///data/db.db`
- ✅ Schema defined in `alembic/env.py` for migration tracking
- ✅ Migration files stored in `alembic/versions/`
- ⚠️ **Downgrading may result in data loss** - use with caution

---

## Migration Workflow

### 1. Create Migration
```bash
alembic revision -m "Add new column"
```

### 2. Edit Migration File
Edit the generated file in `alembic/versions/` and implement the `upgrade()` and `downgrade()` functions.

**Example**:
```python
def upgrade() -> None:
    op.add_column('matchups', sa.Column('lane', sa.String(10), nullable=True))

def downgrade() -> None:
    op.drop_column('matchups', 'lane')
```

### 3. Test Locally
```bash
# Test upgrade
alembic upgrade head

# Test downgrade
alembic downgrade -1

# If OK, upgrade again
alembic upgrade head
```

### 4. Commit Migration File
```bash
git add alembic/versions/xxxx_add_new_column.py
git commit -m "🗃️ Database: Add migration for new column"
```

### 5. Deploy to Production
```bash
# Backup first!
cp data/db.db data/db.db.backup

# Run migration
python -m alembic upgrade head
```

---

## Testing Migrations

Before deploying migrations, always test them:

### Test Upgrade Path
```bash
# Start from base
alembic downgrade base

# Upgrade step by step
alembic upgrade +1  # Upgrade one version
alembic current     # Verify current version
```

### Test Downgrade Path
```bash
# Downgrade one version
alembic downgrade -1

# Verify database still works
python -c "from src.db import Database; db = Database('data/db.db'); db.connect(); print('OK')"
```

### Test Idempotency
```bash
# Run same migration twice (should be safe)
alembic upgrade head
alembic upgrade head  # Should do nothing
```

---

## Common Issues

### Issue: Migration conflicts
**Solution**: Resolve conflicts manually, then:
```bash
alembic stamp head  # Mark as current version
```

### Issue: Migration fails mid-way
**Solution**:
1. Restore backup: `cp data/db.db.backup data/db.db`
2. Fix migration script
3. Retry: `alembic upgrade head`

### Issue: Need to skip a migration
**Solution**:
```bash
# Mark as done without running
alembic stamp <revision_id>
```

---

## Best Practices

1. ✅ **Always write reversible migrations** (implement `downgrade()`)
2. ✅ **Test both upgrade and downgrade** before committing
3. ✅ **Use descriptive migration names** (`add_lane_column`, not `update_db`)
4. ✅ **Backup production database** before running migrations
5. ✅ **Run migrations in transaction** when possible (SQLite default)
6. ✅ **Document breaking changes** in migration docstring
7. ❌ **Never modify existing migrations** after they're deployed
8. ❌ **Never delete migration files** from `alembic/versions/`

---

## Migration Patterns

### Adding a Column
```python
def upgrade() -> None:
    op.add_column('table_name',
                  sa.Column('column_name', sa.String(50), nullable=True))

def downgrade() -> None:
    op.drop_column('table_name', 'column_name')
```

### Creating a Table
```python
def upgrade() -> None:
    op.create_table(
        'synergies',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('champion', sa.String(50), nullable=False),
        sa.Column('ally', sa.String(50), nullable=False),
        sa.Column('winrate', sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

def downgrade() -> None:
    op.drop_table('synergies')
```

### Adding an Index
```python
def upgrade() -> None:
    op.create_index('idx_champion_enemy', 'matchups',
                    ['champion', 'enemy'])

def downgrade() -> None:
    op.drop_index('idx_champion_enemy', 'matchups')
```

### Migrating Data
```python
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column

def upgrade() -> None:
    # Add column
    op.add_column('matchups', sa.Column('tier', sa.String(10)))

    # Migrate data
    matchups_table = table('matchups',
        column('tier', sa.String),
        column('winrate', sa.Float)
    )

    op.execute(
        matchups_table.update()
        .where(matchups_table.c.winrate >= 52.0)
        .values(tier='S')
    )
```

---

## Configuration

### alembic.ini
```ini
[alembic]
script_location = alembic
sqlalchemy.url = sqlite:///data/db.db
```

### alembic/env.py
Contains the environment configuration and schema detection logic.

**Key functions**:
- `run_migrations_offline()` - Dry-run mode (SQL output)
- `run_migrations_online()` - Live database mode

---

## Resources

- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [SQLAlchemy Types](https://docs.sqlalchemy.org/en/14/core/type_basics.html)
- [Migration Cookbook](https://alembic.sqlalchemy.org/en/latest/cookbook.html)

---

**Dernière mise à jour**: 2026-01-15
**Maintenu par**: @pj35
