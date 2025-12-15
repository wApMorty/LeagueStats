# League Stats Coach

Advanced draft coaching and champion analysis tool for League of Legends.

## Quick Start

### Run the Application
```bash
python lol_coach.py
```

### Legacy Mode
```bash
python main.py
```

## Features

- **Real-time Draft Coach** - Live recommendations during champion select
- **Team Builder** - Find optimal champion trios with extended pools  
- **Multi-Role Pools** - Support for top, support, jungle, mid, adc roles
- **Automatic Parsing** - Update champion statistics from web sources
- **Standalone Distribution** - Portable executable for any Windows PC

## Distribution

Create a portable version for Gaming House or other PCs:

```bash
python build_app.py           # Build executable
python create_package.py      # Create ZIP package
```

Result: `LeagueStatsCoach_Portable.zip` ready for distribution.

## Project Structure

```
LeagueStats/
├── lol_coach.py          # Main application entry point
├── main.py               # Legacy entry point  
├── build_app.py          # Build executable
├── create_package.py     # Create distribution ZIP
├── src/                  # Source code modules
├── data/                 # Database and data files  
├── docs/                 # Documentation
└── README.md             # This file
```

## Requirements

**Development:**
- Python 3.13+
- Dependencies: `pip install -r requirements.txt`
- Firefox browser (for web scraping)

**Distribution:**
- No Python required on target PC
- Windows 10/11
- League of Legends installed
- Firefox browser (for parsing updates)

## Documentation

- **User Guide:** `docs/CLAUDE.md`
- **Architecture:** `docs/PROJECT_STRUCTURE.md` 
- **Build Tools:** `build_app.py` and `create_package.py` scripts

## Database

The application includes a complete database with:
- **171 champions** with current statistics
- **36,000+ matchup records** with win rates and performance metrics
- **Role-specific pools** for targeted analysis

Database location: `data/db.db`

## Recent Updates

### Version 1.0.1 - Security & Performance Update (2025-11-27)

**Security Fixes:**
- ✅ Fixed SQL injection vulnerabilities (6 locations in `src/db.py`)
- ✅ All database queries now use parameterized queries

**Performance Improvements:**
- ✅ Added 6 database indexes for faster queries (50-80% improvement)
- ✅ Automatic index creation on database connection

**Development:**
- ✅ Added `requirements.txt` with pinned dependency versions
- ✅ Added `requirements-dev.txt` for development tools
- ✅ Created test suite (`test_db_fixes.py`)

See `SECURITY_FIXES.md` for detailed information.

---

**Version:** 1.0.1 Security & Performance Update
**Ready for Gaming House deployment** 🎮