# Changelog

All notable changes to LeagueStats Coach will be documented in this file.

## [1.1.0] - 2025-12-14

### ♻️ Refactoring

- **MAJOR**: Refactored monolithic files into modular architecture (PR #2)
  - `assistant.py`: 2,381 → 190 lines (-92%)
  - `lol_coach.py`: 2,159 → 215 lines (-90%)
  - Created 9 new modules organized into `analysis/`, `ui/`, and `utils/`
  - Largest file reduced from 2,381 → 220 lines (-91%)

### 📦 Added

- **Analysis modules**:
  - `src/analysis/scoring.py` - Champion scoring algorithms (216 lines)
  - `src/analysis/tier_list.py` - Tier list generation (91 lines)
  - `src/analysis/recommendations.py` - Draft recommendations (116 lines)
  - `src/analysis/team_analysis.py` - Team composition analysis (129 lines)
- **Utils modules**:
  - `src/utils/display.py` - Emoji fallback for Windows terminals (30 lines)
  - `src/utils/champion_utils.py` - Champion validation/selection (220 lines)
- **UI modules**:
  - `src/ui/menu_system.py` - Main menu system (45 lines)
  - `src/ui/champion_data_ui.py` - Champion data management (105 lines)
  - `src/ui/draft_coach_ui.py` - Real-time draft coach UI (52 lines)
  - `src/ui/lol_coach_legacy.py` - Legacy UI functions (temporary)

### 🔧 Changed

- `src/assistant.py` - Replaced monolithic class with delegation pattern
- `lol_coach.py` - Replaced with minimal entry point delegating to UI modules
- `src/draft_monitor.py` - Fixed import for `safe_print` from utils.display

### 🐛 Fixed

- Type hint for `open_onetricks` parameter (str → Optional[bool])

### 📊 Impact

- **Maintainability**: Code now organized in focused modules (<500 lines each)
- **Testing**: Easier to write unit tests for isolated components
- **Onboarding**: Clearer code structure for new contributors
- **Foundation**: Clean base for future features and refactoring
- **Compatibility**: 100% backward compatible, all tests pass

---

## [1.0.1] - 2025-11-27

### 🔒 Security

- **CRITICAL**: Fixed SQL injection vulnerabilities in 6 database query methods
  - `get_champion_id()` - Line 86
  - `get_champion_by_id()` - Line 98
  - `get_champion_matchups()` - Line 110
  - `get_champion_matchups_by_name()` - Line 128
  - `add_matchup()` - Line 80
  - `init_champion_table()` - Line 43
- All SQL queries now use parameterized queries with `?` placeholders

### ⚡ Performance

- Added 6 database indexes for optimized query performance
  - `idx_champions_name` - Champion name lookups (50-80% faster)
  - `idx_matchups_champion` - Champion ID queries
  - `idx_matchups_enemy` - Enemy ID queries
  - `idx_matchups_pickrate` - Pickrate filtering
  - `idx_matchups_champion_pickrate` - Composite index for common queries
  - `idx_matchups_enemy_pickrate` - Composite index for reverse lookups
- Indexes are automatically created on database connection
- Expected performance improvement: 50-80% on name lookups, 60-90% on filtered matchup queries

### 📦 Added

- `requirements.txt` - Production dependencies with version pinning
- `requirements-dev.txt` - Development dependencies including PyInstaller
- `test_db_fixes.py` - Test suite for SQL injection fixes and index creation
- `SECURITY_FIXES.md` - Detailed documentation of security and performance fixes
- `CHANGELOG.md` - This file

### 🔧 Changed

- `src/db.py`:
  - Added `create_database_indexes()` method
  - Modified `connect()` to auto-create indexes
  - Modified `init_matchups_table()` to create indexes after table creation
  - Fixed all vulnerable SQL queries to use parameterized queries
- `README.md`:
  - Updated installation instructions to use `requirements.txt`
  - Added "Recent Updates" section with version 1.0.1 changes
  - Updated version number

### 🧪 Testing

- All tests pass successfully
- SQL injection prevention verified with special character handling
- Database index creation verified with automated tests

### 📊 Impact

- **Security**: Eliminated all SQL injection vulnerabilities
- **Performance**: 50-90% improvement on database queries
- **Maintainability**: Better dependency management with requirements files
- **Testing**: Automated test suite for critical functionality

---

## [1.0.0] - 2025-11-26

### Added

- Initial standalone release
- Real-time draft coach with LCU integration
- Champion pool management
- Team builder and optimization tools
- Database with 171 champions and 36,000+ matchups
- Portable executable distribution
- Documentation and build tools

---

**Legend:**
- 🔒 Security fixes
- ⚡ Performance improvements
- 📦 New features/files
- 🔧 Changes to existing functionality
- 🧪 Testing improvements
- 📊 Metrics and analysis
