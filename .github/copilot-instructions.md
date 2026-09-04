# LeagueStats Coach - AI Agent Instructions

## Project Overview

League of Legends draft coaching tool that analyzes 173 champions and ~25,000 matchups per role to generate tier lists and real-time draft recommendations. Uses a local-only SQLite database (`data/db.db`) with Alembic migrations, Selenium web scraping in parallel across the 5 roles, and PyInstaller for standalone distribution. Personal, single-user tool — no remote backend (Postgres/Neon/FastAPI were decommissioned, see `docs/ROADMAP_2026.md`).

**Architecture**: Modular Python 3.13+ application. `src/analysis/` (scoring, aggregation, tier lists, trio search), `src/draft/` (Live Coach logic, extracted from `draft_monitor.py`), `src/ui/` (one module per menu/domain), `src/utils/`. Centralized configuration in [src/config_constants.py](../src/config_constants.py). `src/pipeline.py` is the single orchestrator for the data pipeline (scrape → completeness check → recompute scores/bans → notify), used by both `scripts/update_all.py` and the app's menu 3.

## Critical Workflow Commands

### Development
```bash
python lol_coach.py                    # Main entry point (menu system) — main.py does NOT exist
python -m pytest tests/ -v             # Run all tests
python -m pytest tests/ --cov=src --cov-report=html  # Coverage report (45% threshold, ~62% measured)
```

### Data Pipeline
```bash
python scripts/update_all.py           # Reference pipeline: scrape (5 roles, ~45min) → completeness check → recompute scores/bans → notify
```
No scheduled automation — nightly auto-update was suspended by choice (@pj35), updates are manual. `scripts/auto_update_db.py` is the old, superseded orchestrator (kept on disk, not used).

### Build & Distribution
```bash
python build_app.py                    # Build standalone .exe with PyInstaller
python create_package.py               # Create ZIP distribution package
```

### Database Migrations (Alembic)
```bash
python -m alembic upgrade head                   # Apply all migrations
python -m alembic revision -m "description"       # New migration (write upgrade/downgrade by hand — see docs/alembic_guide.md)
python -m alembic current                          # Show current migration
```

## Code Conventions

### Configuration Management
**NEVER hardcode values**. Always use [src/config_constants.py](../src/config_constants.py):
```python
# ❌ WRONG
if games >= 2000:
    ...

# ✅ CORRECT
from .config_constants import analysis_config
if games >= analysis_config.MIN_GAMES_THRESHOLD:
    ...
```

Config classes: `ScrapingConfig`, `AnalysisConfig`, `DraftConfig`, `UIConfig`, `DataQualityConfig`, `RoleInferenceConfig`.

### Database Security
**ALWAYS use parameterized queries** to prevent SQL injection:
```python
# ❌ WRONG - SQL Injection vulnerable
cursor.execute(f"SELECT * FROM champions WHERE name = '{name}'")

# ✅ CORRECT - Parameterized query
cursor.execute("SELECT * FROM champions WHERE name = ?", (name,))
```

### Module Organization
- **File size limit**: 500 lines maximum. Not fully enforced today — `src/db.py` (1698), `src/parallel_parser.py` (974), `scripts/repair_data.py` (650), `src/constants.py` (593), `src/assistant.py` (527), `src/parser.py` (522) exceed it; see `TODO.md` for the refactor backlog.
- **Separation of concerns**: Analysis logic in `src/analysis/`, Live Coach logic in `src/draft/`, UI in `src/ui/`, utilities in `src/utils/`.
- **Lane awareness**: most matchup/synergy accessors (`db.py`, `analysis/*`) take an optional `lane` parameter (`None` = all lanes blended, a `scraping_config.LANES` value = filtered to that role). When adding a new call site that reads matchups/synergies for a specific role, pass `lane` through — several past bugs were exactly this parameter silently defaulting to `None` where it shouldn't have.
- **Type hints**: Required on all public functions.
- **Docstrings**: Required for classes and public methods.

### Import Order (PEP 8)
```python
# 1. Standard library
import os
from typing import List, Optional

# 2. Third-party
import sqlite3
from selenium import webdriver

# 3. Local imports
from .config import config
from .config_constants import analysis_config
```

## Architecture Patterns

### Assistant Class (src/assistant.py)
**Coordinator pattern**: Delegates to specialized modules while maintaining a stable public API. Core delegates (constructed in `_init_components`):
- `ChampionScorer` (`analysis/scoring.py`) — matchup/synergy scoring, log-odds model (SPEC-05 B7)
- `TierListGenerator` (`analysis/tier_list.py`) — S/A/B/C tier classification, lane-scoped
- `RecommendationEngine` (`analysis/recommendations.py`) — Tournament Coach recommendations
- `BanRecommender` (`analysis/ban_recommendations.py`) — ban threat scoring, pool precalculation
- `GlobalScoreCalculator` (`analysis/champion_scores.py`) — `champion_scores` table (per-champion, per-lane)
- `HolisticTrioFinder` / `CounterpickTrioFinder` / `TrioTacticsReporter` (`analysis/trio_*.py`) — Team Builder
- `MatchupCache` (`analysis/matchup_cache.py`) — in-memory cache for draft-time lookups
- `DraftScorer` (`draft/scoring.py`) — matchup+synergy blend shared by the Live Coach and Tournament Coach

**Cache system**: Call `assistant.warm_cache(champion_pool)` before draft analysis to load matchups into memory.

### Database Layer (src/db.py)
- **Connection lifecycle**: Always call `db.connect()` after initialization, `db.close()` when done.
- **Indexes**: Created automatically on first connection for performance (composite lane indexes, `COLLATE NOCASE` index on `champions.name`).
- **Schema changes**: Use Alembic migrations, NEVER modify tables directly in code. Derived/cache tables (`champion_scores`, `pool_ban_recommendations`) are dropped and fully recomputed rather than migrated in place — see e.g. `alembic/versions/3e87f22f2ec1_*.py`.
- **Backups**: `src/db_backup.py` — the pipeline backs up `data/db.db` before any destructive step and restores on failure.

### Parallel Web Scraping (src/parallel_parser.py)
- **Performance**: ~45 minutes for a full multi-lane scrape (5 roles), one page visit per (champion, lane) covering both matchups and synergies (SPEC-02).
- **Thread-local storage**: ONE Parser instance per thread (reused for multiple champions).
- **Retry mechanism**: Automatic exponential backoff with tenacity.
- **Thread-safe writes**: All DB operations use `self.db_lock` for atomicity.
- **Headless mode**: Auto-detects pythonw.exe (Task Scheduler) and disables tqdm to prevent crashes.

### Build System (PyInstaller)
- **Entry point**: [lol_coach.py](../lol_coach.py) (there is no `main.py`).
- **Critical data files**: `data/db.db` must be bundled with `--add-data`.
- **Output**: Single `.exe` in `dist/` → Release package in `LeagueStatsCoach_Release/`.

## Testing Strategy

### Fixtures (tests/conftest.py)
Key shared fixtures for all tests:
- `db` — Connected `Database` instance on a temp SQLite file (tests never touch `data/db.db`)
- `scorer` — `ChampionScorer` with test data
- `insert_matchup` / `insert_synergy` — Helpers to insert test rows, accept an optional `lane=` kwarg
- Autouse fixtures isolate `logs/` and any production DB path from the suite (SPEC-07 E6)

### Coverage Requirements
- **Threshold**: 45% on all of `src/` (`pyproject.toml`, `--cov-fail-under=45`), ~62% measured currently
- **Run**: `pytest tests/ --cov=src --cov-report=html`
- **View**: Open `htmlcov/index.html`

### Test Patterns
```python
def test_feature(db, insert_matchup):
    """Test docstring explaining what's being validated."""
    # Arrange - Setup test data
    insert_matchup("Aatrox", "Darius", 48.5, -150, -2.0, 8.5, 1500, lane="top")

    # Act - Execute functionality
    result = db.get_matchup_delta2("Aatrox", "Darius", lane="top")

    # Assert - Verify expectations
    assert result == -2.0
```

### Regression Tests (mandatory for bug fixes)
For every user-reported bug, add a regression test that reproduces it before the fix and passes after — see `tests/regression/` and `CLAUDE.md`.

## Git Workflow (Critical)

### Branch Strategy
**ALWAYS create feature branches from master**, never from another feature branch:
```bash
# ❌ WRONG - Inherits commits from old-task
git checkout feature/old-task
git checkout -b feature/new-task

# ✅ CORRECT - Clean branch from master
git checkout -b feature/new-task origin/master
```

### Commit Standards
- **Atomic commits**: One logical change per commit
- **Gitmoji convention**: `<emoji> Type: Description` (Fix 🐛, Feature ✨, Refactor ♻️, Test ✅, Docs 📝, Chore 🔧, Database 🗃️, Security 🔒, Perf ⚡) — see `CLAUDE.md` for the full list

### Pre-PR Checklist (MANDATORY)
1. **Tests**: Write tests for ALL new functionality; a regression test for every bug fix
2. **Run tests**: `pytest tests/ -v` (all must pass)
3. **Format**: `python -m black src/ tests/ scripts/`
4. **Update docs**: `CHANGELOG.md`, `README.md` if user-facing changes
5. **Push**: `git push -u origin feature/task-name`

### Code Review Process
- **WAIT for user validation** before merging (never auto-merge)
- Provide a summary of changes, files modified, test results

## Backlog Methodology

The project no longer follows a "Sprint 0/1/2/3" numbering. Work is organized as: an audit document (`docs/AUDIT_YYYY_MM.md`) → a triaged backlog (`docs/BACKLOG_YYYY_MM.md`) → per-chantier specs (`docs/specs/SPEC-NN-*.md`) → tracked to completion in `TODO.md`. Once a backlog is fully executed, its audit/backlog/specs move to `docs/archive/` and `TODO.md` is rewritten from the next audit cycle. Check `TODO.md` first for the current priorities.

## Key Files & Integration Points

### Entry Points
- [lol_coach.py](../lol_coach.py) — Main menu system (build target). No `main.py`.

### Core Modules
- [src/assistant.py](../src/assistant.py) — Coordinator, delegates to `src/analysis/*` and `src/draft/scoring.py`
- [src/db.py](../src/db.py) — Database layer with parameterized queries
- [src/pipeline.py](../src/pipeline.py) — Single data-pipeline orchestrator (scrape → checks → recompute → notify)
- [src/parallel_parser.py](../src/parallel_parser.py) — Parallel multi-lane scraping
- [src/draft_monitor.py](../src/draft_monitor.py) — Live Coach facade (LCU API integration), delegates to `src/draft/`

### Configuration
- [src/config_constants.py](../src/config_constants.py) — ALL hardcoded values (`ScrapingConfig`, `AnalysisConfig`, `DraftConfig`, etc.)
- [src/config.py](../src/config.py) — Runtime config (patch version, database path)
- [src/constants.py](../src/constants.py) — Champion pools (`TOP_CHAMPIONS`, `JUNGLE_CHAMPIONS`, etc.)

### External Dependencies
- **LCU (League Client Update) API**: REST API on `127.0.0.1:2999` for live draft data
- **LoLalytics**: Web scraping source for matchup/synergy statistics
- **Firefox/Selenium**: Webdriver for scraping (geckodriver auto-managed)

## Common Pitfalls

1. **SQL Injection**: Always use `?` placeholders, never f-strings in queries
2. **Lane blending**: Passing no `lane` to a matchup/synergy accessor silently aggregates every role a champion has ever played — check whether the caller actually knows a specific lane (pool role, inferred player role) before defaulting to `None`
3. **Cache warming**: Must call `warm_cache()` before draft analysis or performance suffers
4. **Thread safety**: Use `db_lock` when writing to DB from multiple threads
5. **PyInstaller data files**: Use `--add-data` for db.db or exe won't work
6. **Branch inheritance**: Create branches from master to avoid polluted history
7. **Test coverage**: Write tests BEFORE creating PR, not after; a regression test is mandatory for bug fixes
8. **File size**: Keep modules under 500 lines (split into submodules if needed) — several existing files are already over, don't make it worse
9. **Config usage**: Check `config_constants.py` before hardcoding ANY value
10. **Derived tables**: `champion_scores` and `pool_ban_recommendations` are caches, fully recomputed by the pipeline — never assume they're in sync with `matchups`/`synergies` without checking `db_meta`

## Debugging & Logging

- **Logs location**: `logs/update_all.log` for pipeline runs (the actively used log; `logs/auto_update.log` is from the superseded orchestrator)
- **Verbose mode**: `python lol_coach.py --verbose` for detailed output
- **Test failures**: Run `pytest tests/ -vv` for detailed failure info
- **Database inspection**: Use a SQLite browser on `data/db.db` (173 champions, ~25k matchups per role); check the `db_meta` table for last-scrape freshness
