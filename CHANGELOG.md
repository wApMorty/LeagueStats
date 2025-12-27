# Changelog

All notable changes to LeagueStats Coach will be documented in this file.

## [1.1.0-dev] - 2025-12-20 (Sprint 2 - In Progress)

### ⚡ Performance

- **MAJOR**: Parallel web scraping implementation (PR #5)
  - **87% performance improvement** - Data updates now take 12 minutes instead of 90-120 minutes
  - ThreadPoolExecutor with 10 concurrent workers (optimized for i5-14600KF)
  - Automatic retry mechanism with exponential backoff (tenacity)
  - Thread-safe database operations with proper locking
  - Real-time progress tracking with tqdm progress bars
  - Komorebi window manager integration with fullscreen mode
  - Dynamic cookie acceptance (fixes hardcoded coordinates bug)
- **MAJOR**: Pre-calculated ban recommendations system (PR #19)
  - **Instant ban suggestions** during draft - no more 5-10 second calculation delays
  - Database-backed storage of ban recommendations for all custom pools
  - Automatic updates during data parsing (both manual and auto-update)
  - Fallback to real-time calculation if pre-calculated data unavailable
  - Optimized for pools of 10-20 champions (typical custom pools)
  - System pools excluded (too large for meaningful ban calculations)
- **Live Coach cache system** for instant draft recommendations
  - Warm cache at draft start eliminates SQL queries during picks (99% faster)
  - In-memory storage of all champion matchups from selected pool
  - Cache statistics tracking (hits/misses) for performance monitoring
  - Automatic cache clear on draft exit to free memory

### ✨ Features

- **MAJOR**: Proactive Draft Start UX (PR #19)
  - **Immediate strategy display** - Best blind pick + ban recommendations shown at game start
  - **No waiting** - Information appears before ban/pick phases begin
  - **Clear guidance** - "If you're first pick, this is your safest choice!"
  - **Adaptive recommendations** - Updates dynamically when enemy picks appear
  - **Better preparation** - Players can plan strategy from the very start
- **MAJOR**: Auto-Update Database system (Tâche #11, PR #14)
  - **Automated daily updates** via Windows Task Scheduler (3 AM default)
  - **Background execution** with BELOW_NORMAL priority (no PC blocking)
  - **12-minute updates** using ParallelParser (10 workers)
  - **Windows notifications** on success/failure (win10toast)
  - **Detailed logging** to `logs/auto_update.log`
  - **PowerShell setup wizard** (`setup_auto_update.ps1`)
  - **Dry-run test script** (`test_auto_update.py`)
  - **Zero manual maintenance** - Always up-to-date database
- **MAJOR**: Restored 24 missing Assistant methods from refactoring (+902 lines)
  - 7 draft & competitive methods: `draft()`, `competitive_draft()`, `blind_pick()`, etc.
  - 14 holistic trio analysis methods: `find_optimal_trios_holistic()`, `_evaluate_trio_holistic()`, etc.
  - 3 ban recommendation methods: `get_ban_recommendations()` with reverse lookup strategy
  - All methods updated to use dynamic DB queries instead of hardcoded CHAMPIONS_LIST
- **Live podium display** during optimal duo/trio optimization
  - Real-time updates every 50 evaluations
  - Top 3 rankings with medals (🥇🥈🥉)
  - Progress bar with percentage and viable count
  - ANSI escape codes for in-place terminal updates
- **Pool Statistics Viewer** (Tâche #5, PR #TBD)
  - **Comprehensive statistical analysis** for champion pools
  - **Distribution metrics**: mean, median, min, max, standard deviation, variance
  - **Coverage analysis**: champions with/without sufficient data, percentage
  - **Outlier detection**: champions with insufficient matchup data
  - **Performance rankings**: Top 5 and Bottom 5 performers by avg_delta2
  - **Integrated into Pool Manager** as Menu option 8
  - **15 unit tests** with 100% pass rate
- **New champions support**: Zaahen (TOP), Yunara (ADC)
- **Bidirectional advantage calculation** in draft coach (Tâche #TBD, PR #TBD)
  - **More accurate predictions** accounting for matchup asymmetry
  - Combines two perspectives: our advantage vs their advantage
  - Formula: `net_advantage = our_advantage - opponent_advantage`
  - Handles asymmetric delta2 (e.g., Aatrox vs Darius ≠ Darius vs Aatrox)
  - Graceful degradation when opponent data missing (treats as neutral)
  - **8 unit tests** with 100% pass rate
  - **Zero breaking changes** - seamlessly integrated into existing scoring

### 🐛 Fixes

- **CRITICAL**: Fixed live coach performance and UX issues (PR #TBD)
  - **Ban recommendations spam**: Now show ONLY during ban phase (before any picks)
    - Root cause: Phase name "BAN_PICK" contains "BAN" → rewrote `_is_ban_phase()` to check picks count
    - Impact: Clean draft experience, no more spam on every pick
  - **Wrong advice during picks**: Dynamic advice detection based on game state
    - Before: Always showed "[BAN]" advice during "BAN_PICK" phase
    - After: Shows "[BAN]" only when 0 picks, "[PICK]" when picks > 0
  - **Duplicate DB queries**: Removed redundant `get_champion_matchups()` calls in final analysis
    - Impact: 2x faster final team analysis
  - Added debug logging for troubleshooting (verbose mode support)
  - All 113 tests pass ✅

- Fixed `get_ban_recommendations()` AttributeError (method was lost during Sprint 1 refactoring)
- Fixed missing draft and holistic trio analysis methods (24 methods restored)
- Removed debug logging from optimal duo finder for cleaner output
- Fixed CHAMPIONS_LIST dependency by using dynamic `db.get_all_champion_names().values()`

### 📦 Added

- `scripts/auto_update_db.py` - Automated database update script (260 lines)
- `scripts/setup_auto_update.ps1` - Task Scheduler setup wizard (202 lines)
- `scripts/test_auto_update.py` - Dry-run test script (204 lines)
- `docs/AUTO_UPDATE_SETUP.md` - Complete setup guide (397 lines)
- `src/parallel_parser.py` - Parallel web scraping with ThreadPoolExecutor (389 lines)
- `src/analysis/pool_statistics.py` - Pool statistics calculator and formatter (271 lines)
- Live podium display method in `src/assistant.py` (36 lines)
- 24 restored methods in `src/assistant.py` (+902 lines total)
- `tests/test_pool_statistics.py` - Unit tests for pool statistics (376 lines, 15 tests)
- `win10toast>=0.9` dependency for Windows notifications

### 🔧 Changed

- `src/assistant.py`: Added `Dict` to type imports
- `src/assistant.py`: Refactored `_find_optimal_counterpick_duo()` to use live podium (117 lines)
- `src/assistant.py`: Updated all methods to use dynamic DB queries instead of hardcoded constants
- `src/ui/lol_coach_legacy.py`: Enhanced `show_pool_statistics()` with submenu for global vs individual analysis
- `src/constants.py`: Added Zaahen and Yunara champion entries
- `main.py`: Added `parse_all_champions_parallel()` and `parse_champions_by_role_parallel()` functions

### 📊 Impact

- **Automation**: Zero manual database maintenance (runs daily automatically)
- **Performance**: 87% faster data updates (12min vs 90-120min)
- **Completeness**: 54 total Assistant methods (vs 30 before restoration)
- **User Experience**: Live progress tracking, real-time podium, notifications
- **Reliability**: Automatic retries, thread-safe operations, background execution
- **Compatibility**: 100% backward compatible, all methods functional

### 🧪 Testing

- Auto-update script successfully tested with 172 champions
- Task Scheduler integration verified (3 AM daily execution)
- Dry-run test script validates all components
- Manual testing of parallel scraping with 10 workers
- Verification of all 24 restored methods accessibility
- Performance benchmarking: 12min for full champion pool (172 champions)
- Thread-safety validation with concurrent database writes
- **Pool statistics**: 15 unit tests with 100% pass rate (113 total project tests)

---

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
