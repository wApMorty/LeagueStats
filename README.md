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

- **Real-time Draft Coach** - Live recommendations during champion select with ban analysis
- **Team Builder** - Find optimal champion trios/duos with holistic evaluation (17 advanced algorithms)
- **Multi-Role Pools** - Support for top, support, jungle, mid, adc roles
- **Auto-Update Database** - 🔄 **Automated daily updates** via Task Scheduler (zero manual maintenance)
- **Parallel Web Scraping** - ⚡ **87% faster** data updates (12min vs 90-120min) with 10 concurrent workers
- **Live Progress Tracking** - Real-time podium display during trio optimization
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
- **Auto-Update Setup:** `docs/AUTO_UPDATE_SETUP.md` - Daily database automation
- **Build Tools:** `build_app.py` and `create_package.py` scripts

## Database

The application includes a complete database with:
- **172 champions** (including Zaahen, Yunara) with current statistics
- **36,000+ matchup records** with win rates and performance metrics
- **Role-specific pools** for targeted analysis
- **Auto-updates daily** via Task Scheduler (3 AM default, zero maintenance)
- **Parallel scraping** updates all data in **12 minutes** (87% faster than before)

Database location: `data/db.db`

**Setup auto-update**: See [docs/AUTO_UPDATE_SETUP.md](docs/AUTO_UPDATE_SETUP.md) for 3-step setup guide

## Recent Updates

### Version 1.1.0-dev - Auto-Update & Performance (2025-12-22)

**🔄 Automation Breakthrough:**
- 🤖 **Auto-Update Database** - Daily automated updates via Task Scheduler
- 🔕 **Background execution** - Low priority, no PC blocking
- 🔔 **Windows notifications** - Success/failure alerts (win10toast)
- 📊 **Detailed logging** - Full operation history in `logs/auto_update.log`
- ⚙️ **3-step setup** - PowerShell wizard for Task Scheduler

**🚀 Performance Breakthrough:**
- ⚡ **Parallel web scraping** - 87% faster data updates (12min vs 90-120min)
- 🔧 10 concurrent workers optimized for multi-core CPUs
- 🔄 Automatic retry with exponential backoff for reliability
- 📊 Real-time progress tracking with live podium display

**✨ Advanced Features:**
- 🎯 **54 Assistant methods** including holistic trio analysis (17 algorithms)
- 🏆 Live podium display during champion optimization
- 🚫 Intelligent ban recommendations with reverse lookup strategy
- 📈 Competitive draft simulation (blue/red side)
- 🎮 172 champions supported (including new champions Zaahen, Yunara)

**🧪 Quality & Maintainability:**
- ✅ 89% test coverage on analysis module
- ✅ Modular architecture (<500 lines/file)
- ✅ Database migrations with Alembic
- ✅ Zero SQL injection vulnerabilities

See `CHANGELOG.md` for detailed version history.

---

### Version 1.0.1 - Security & Performance Update (2025-11-27)

**Security Fixes:**
- ✅ Fixed SQL injection vulnerabilities (6 locations in `src/db.db`)
- ✅ All database queries now use parameterized queries

**Performance Improvements:**
- ✅ Added 6 database indexes for faster queries (50-80% improvement)
- ✅ Automatic index creation on database connection

---

**Version:** 1.1.0-dev (Sprint 2 in progress)
**Ready for Gaming House deployment** 🎮