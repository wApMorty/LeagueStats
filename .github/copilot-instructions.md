# LeagueStats Coach - AI Agent Instructions

## Project Overview

League of Legends draft coaching tool that analyzes 172 champions and 36,000+ matchups to generate tier lists and real-time draft recommendations. Uses SQLite database with Alembic migrations, Selenium web scraping with parallel execution (10 workers), and PyInstaller for standalone distribution.

**Architecture**: Modular Python 3.13+ application with `src/` containing core modules (analysis, UI, utils), centralized configuration in [src/config_constants.py](../src/config_constants.py), and specialized components for draft monitoring, web scraping, and champion analysis.

## Critical Workflow Commands

### Development
```bash
python lol_coach.py                    # Main entry point (menu system)
python main.py                         # Legacy entry point
python -m pytest tests/ -v             # Run all tests
python -m pytest tests/ --cov=src --cov-report=html  # Coverage report (89% target)
```

### Build & Distribution
```bash
python build_app.py                    # Build standalone .exe with PyInstaller
python create_package.py               # Create ZIP distribution package
```

### Database Migrations (Alembic)
```bash
alembic upgrade head                   # Apply all migrations
alembic revision --autogenerate -m "description"  # Generate migration
alembic current                        # Show current migration
```

### Auto-Update Setup (Production)
```powershell
.\scripts\setup_auto_update.ps1        # Setup Task Scheduler for daily updates
python scripts\test_auto_update.py     # Test auto-update dry-run
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

Config classes: `ScrapingConfig`, `AnalysisConfig`, `DraftConfig`, `UIConfig`

### Database Security
**ALWAYS use parameterized queries** to prevent SQL injection:
```python
# ❌ WRONG - SQL Injection vulnerable
cursor.execute(f"SELECT * FROM champions WHERE name = '{name}'")

# ✅ CORRECT - Parameterized query
cursor.execute("SELECT * FROM champions WHERE name = ?", (name,))
```

### Module Organization
- **File size limit**: 500 lines maximum (enforced since Sprint 1 refactoring)
- **Separation of concerns**: Analysis logic in `src/analysis/`, UI in `src/ui/`, utilities in `src/utils/`
- **Type hints**: Required on all public functions
- **Docstrings**: Required for classes and public methods

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
**Coordinator pattern**: Delegates to specialized modules while maintaining backward compatibility. Core components:
- `ChampionScorer` - Tier list calculations (blind/counterpick)
- `TierListGenerator` - S/A/B/C tier classification
- `RecommendationEngine` - Draft recommendations
- `TeamAnalyzer` - Optimal duo/trio analysis with holistic evaluation

**Cache system**: Call `assistant.warm_cache(champion_pool)` before draft analysis to load matchups into memory (99% faster, eliminates SQL queries).

### Database Layer (src/db.py)
- **Connection lifecycle**: Always call `db.connect()` after initialization, `db.close()` when done
- **Indexes**: Created automatically on first connection for performance (6 indexes on matchups/champions tables)
- **Schema changes**: Use Alembic migrations, NEVER modify tables directly in code

### Parallel Web Scraping (src/parallel_parser.py)
- **Performance**: 10 concurrent workers = 12 minutes for 172 champions (87% faster than sequential)
- **Thread-local storage**: ONE Parser instance per thread (reused for multiple champions)
- **Retry mechanism**: Automatic exponential backoff with tenacity (3 attempts)
- **Thread-safe writes**: All DB operations use `self.db_lock` for atomicity
- **Headless mode**: Auto-detects pythonw.exe (Task Scheduler) and disables tqdm to prevent crashes

### Build System (PyInstaller)
- **Entry point**: [lol_coach.py](../lol_coach.py) (NOT main.py)
- **Critical data files**: `data/db.db` must be bundled with `--add-data`
- **Output**: Single `.exe` in `dist/` → Release package in `LeagueStatsCoach_Release/`

## Testing Strategy

### Fixtures (tests/conftest.py)
Key shared fixtures for all tests:
- `temp_db` - Temporary SQLite database
- `db` - Connected Database instance
- `scorer` - ChampionScorer with test data
- `insert_matchup` - Helper to insert test matchups
- `sample_champions/matchups` - Pre-populated test data

### Coverage Requirements
- **Target**: 89% achieved for `src/analysis/` module (far exceeds 70% goal)
- **Run**: `pytest tests/ --cov=src --cov-report=html`
- **View**: Open `htmlcov/index.html`

### Test Patterns
```python
def test_feature(db, scorer, insert_matchup):
    """Test docstring explaining what's being validated."""
    # Arrange - Setup test data
    insert_matchup("Aatrox", "Darius", 48.5, -150, -200, 8.5, 1500)
    
    # Act - Execute functionality
    result = scorer.calculate_blind_pick_score("Aatrox")
    
    # Assert - Verify expectations
    assert result > 0.0
```

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
- **Descriptive messages**: "Refactor: Extract scoring logic to analysis/scoring.py"
- **Convention**: `Type: Description` (Type = Refactor|Feature|Fix|Test|Docs)

### Pre-PR Checklist (MANDATORY)
1. **Tests**: Write tests for ALL new functionality
2. **Run tests**: `pytest tests/ -v` (all must pass)
3. **Update docs**: CHANGELOG.md, README.md if user-facing changes
4. **Rebase**: `git fetch origin && git rebase origin/master`
5. **Push**: `git push -u origin feature/task-name`

### Code Review Process
- **WAIT for user validation** before merging (never auto-merge)
- Provide summary of changes, files modified, test results
- After approval: `git merge --no-ff feature/task-name`

## Technical Debt First Philosophy

**Principle**: Resolve technical debt BEFORE adding features. This ensures clean foundation for velocity.

**Sprint Order**:
1. ✅ Sprint 0: Configuration setup
2. ✅ Sprint 1: Refactoring + Tests + Migrations (COMPLETED)
3. 🔴 Sprint 2: Performance & Features (IN PROGRESS - Parallel scraping ✅, Auto-update ✅)
4. 🟡 Sprint 3+: Advanced features

**Current State**: Sprint 2 with parallel scraping (12min updates) and auto-update system (Task Scheduler, zero maintenance) completed.

## Key Files & Integration Points

### Entry Points
- [lol_coach.py](../lol_coach.py) - Main menu system (build target)
- [main.py](../main.py) - Legacy entry (kept for compatibility)

### Core Modules
- [src/assistant.py](../src/assistant.py) - Coordinator with 54 methods (24 restored in Sprint 2)
- [src/db.py](../src/db.py) - Database layer with parameterized queries
- [src/parallel_parser.py](../src/parallel_parser.py) - High-performance scraping
- [src/draft_monitor.py](../src/draft_monitor.py) - Real-time LCU API integration

### Configuration
- [src/config_constants.py](../src/config_constants.py) - ALL hardcoded values (ScrapingConfig, AnalysisConfig, etc.)
- [src/config.py](../src/config.py) - Runtime config (patch version, database path)
- [src/constants.py](../src/constants.py) - Champion pools (TOP_POOL, JUNGLE_POOL, etc.)

### External Dependencies
- **LCU (League Client Update) API**: REST API on `127.0.0.1:2999` for live draft data
- **LoLalytics**: Web scraping source for matchup statistics (dynamic cookie acceptance required)
- **Firefox/Selenium**: Webdriver for scraping (geckodriver auto-managed)

## Common Pitfalls

1. **SQL Injection**: Always use `?` placeholders, never f-strings in queries
2. **Cache warming**: Must call `warm_cache()` before draft analysis or performance suffers
3. **Thread safety**: Use `db_lock` when writing to DB from multiple threads
4. **PyInstaller data files**: Use `--add-data` for db.db or exe won't work
5. **Branch inheritance**: Create branches from master to avoid polluted history
6. **Test coverage**: Write tests BEFORE creating PR, not after
7. **File size**: Keep modules under 500 lines (split into submodules if needed)
8. **Config usage**: Check config_constants.py before hardcoding ANY value
9. **tqdm in headless mode**: parallel_parser.py auto-detects pythonw.exe and disables progress bars

## Debugging & Logging

- **Logs location**: `logs/auto_update.log` for scheduled updates
- **Verbose mode**: `python lol_coach.py --verbose` for detailed output
- **Test failures**: Run `pytest tests/ -vv` for detailed failure info
- **Database inspection**: Use SQLite browser on `data/db.db` (172 champions, 36k+ matchups)
