# LeagueStats Coach - API Server

**Version**: 2.0.0-alpha (Phase 1 - Backend API)
**Framework**: FastAPI 0.110
**Database**: PostgreSQL 15+ (Neon)
**Python**: 3.13+

---

## 📋 Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Setup & Installation](#setup--installation)
3. [Database Setup (Neon PostgreSQL)](#database-setup-neon-postgresql)
4. [Running the Server](#running-the-server)
5. [API Endpoints](#api-endpoints)
6. [Testing](#testing)
7. [Deployment (Render)](#deployment-render)
8. [Project Structure](#project-structure)

---

## 🏗️ Architecture Overview

This server provides a REST API for LeagueStats Coach, exposing champion data analysis algorithms via HTTP endpoints.

**Key Components**:
- **FastAPI**: Modern async web framework
- **PostgreSQL**: Centralized champion data (172 champions, 36k+ matchups)
- **SQLAlchemy 2.0**: Async ORM
- **Alembic**: Database migrations
- **Pydantic**: Request/response validation

**Data Flow**:
```
Client → FastAPI API → PostgreSQL → Analysis Algorithms → JSON Response
```

---

## 🚀 Setup & Installation

### Prerequisites

- Python 3.13+
- PostgreSQL 15+ (Neon account - see below)
- pip (Python package manager)

### Installation Steps

1. **Clone the repository** (if not already done):
   ```bash
   git clone https://github.com/wApMorty/LeagueStats.git
   cd LeagueStats/server
   ```

2. **Create virtual environment**:
   ```bash
   python -m venv venv

   # Windows
   venv\Scripts\activate

   # Linux/Mac
   source venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**:
   ```bash
   # Copy example env file
   cp .env.example .env

   # Edit .env and fill in DATABASE_URL (see next section)
   ```

---

## 🗄️ Database Setup (Neon PostgreSQL)

### Step 1: Create Neon Account & Database

1. Go to https://neon.tech and create a free account
2. Create a new project:
   - **Project name**: `leaguestats-db`
   - **Region**: Choose closest to you (e.g., `us-east-2` or `eu-central-1`)
   - **PostgreSQL version**: 15 or higher
3. Copy the connection string from the dashboard:
   ```
   postgresql://user:password@ep-xxx-xxx.region.aws.neon.tech/leaguestats?sslmode=require
   ```
4. Paste it into `server/.env`:
   ```bash
   DATABASE_URL=postgresql://user:password@ep-xxx-xxx.region.aws.neon.tech/leaguestats?sslmode=require
   ```

### Step 2: Run Database Migrations

```bash
# Navigate to server directory
cd server

# Run Alembic migrations (creates tables)
python -m alembic upgrade head
```

This will create the following tables:
- `champions` (172 champions)
- `matchups` (36,000+ matchups with winrate/delta2/games)
- `synergies` (champion duo synergies)
- `champion_scores` (tier list cache)
- `pool_ban_recommendations` (ban recommendations cache)

### Step 3: Import Data (SQLite → PostgreSQL)

**IMPORTANT**: This step requires existing SQLite database (`data/db.db` from client).

```bash
# From project root
cd server

# Export SQLite data to CSV (automated script)
python scripts/export_sqlite_to_csv.py

# Import CSV data to PostgreSQL (automated script)
python scripts/import_csv_to_postgres.py

# Verify data integrity
python scripts/verify_database_integrity.py
```

Expected output:
```
✅ Champions: 172
✅ Matchups: 36,288
✅ Synergies: 29,584
✅ Data integrity validated
```

---

## 🚀 Running the Server

### Development Server (Auto-reload)

```bash
# Navigate to server directory
cd server

# Run with uvicorn (auto-reload enabled)
python -m uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```

Server will start on: http://localhost:8000

### Production Server (Gunicorn)

```bash
# Multiple workers (recommended for production)
gunicorn src.api.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000
```

### Verify Server is Running

```bash
# Health check
curl http://localhost:8000/health

# Expected response:
# {
#   "status": "ok",
#   "version": "2.0.0",
#   "database": "connected",
#   "timestamp": "2026-01-19T..."
# }
```

### Access API Documentation

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

---

## 📡 API Endpoints

### Base URL
```
Development: http://localhost:8000
Production: https://leaguestats-adf4.onrender.com
```

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/api/champions` | List all champions |
| GET | `/api/champions/{id}/matchups` | Matchups for champion |
| GET | `/api/champions/{id}/synergies` | Synergies for champion |
| GET | `/api/matchups/bulk` | All matchups (bulk, for cache) |
| GET | `/api/synergies/bulk` | All synergies (bulk, for cache) |
| GET | `/api/tier-list?pool={pool}&type={blind\|counter}` | Tier list |
| POST | `/api/analyze-team` | Holistic team analysis |
| GET | `/api/ban-recommendations?pool={pool}` | Ban recommendations |

### Example Requests

**Get all champions**:
```bash
curl http://localhost:8000/api/champions
```

**Get matchups for Aatrox (id=1)**:
```bash
curl http://localhost:8000/api/champions/1/matchups
```

**Get tier list for TOP pool (blind pick)**:
```bash
curl "http://localhost:8000/api/tier-list?pool=TOP&type=blind"
```

**Analyze team composition**:
```bash
curl -X POST http://localhost:8000/api/analyze-team \
  -H "Content-Type: application/json" \
  -d '{"champion_ids": [1, 10, 25]}'
```

See **Swagger docs** (http://localhost:8000/docs) for interactive API exploration.

---

## 🧪 Testing

### Run All Tests

```bash
# Navigate to server directory
cd server

# Run all tests with coverage
pytest tests/ -v --cov=src --cov-report=html

# Expected output:
# ✅ All tests passed
# ✅ Coverage: ≥80%
```

### Run Specific Test Files

```bash
# Test health endpoint
pytest tests/test_health.py -v

# Test champions endpoints
pytest tests/test_champions.py -v

# Test tier list endpoint
pytest tests/test_tier_list.py -v
```

### Coverage Report

After running tests with `--cov-report=html`, open:
```bash
# Windows
start htmlcov/index.html

# Linux/Mac
open htmlcov/index.html
```

---

## 🚢 Deployment (Render)

### Prerequisites

- GitHub repository connected to Render
- Neon PostgreSQL database created (see above)
- `render.yaml` configured (already done)

### Deployment Steps

1. **Push to GitHub**:
   ```bash
   git add server/
   git commit -m "✨ Feature: FastAPI backend (Phase 1)"
   git push origin feature/api-backend-phase1
   ```

2. **Create Render Web Service**:
   - Go to https://dashboard.render.com
   - Click "New +" → "Web Service"
   - Connect GitHub repo: `wApMorty/LeagueStats`
   - **Root directory**: `server`
   - **Build command**: `pip install -r requirements.txt`
   - **Start command**: `gunicorn src.api.main:app --workers 2 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT`
   - **Environment variables**:
     - `DATABASE_URL`: (paste Neon connection string)
     - `PYTHON_VERSION`: `3.13.0`

3. **Deploy**:
   - Click "Create Web Service"
   - Render will automatically build and deploy
   - Wait for deploy to complete (~5 minutes)

4. **Verify Deployment**:
   ```bash
   # Health check (replace with your Render URL)
   curl https://leaguestats-adf4.onrender.com/health
   ```

5. **Access Swagger Docs**:
   - https://leaguestats-adf4.onrender.com/docs

### Auto-Deploy on Push

Render will automatically redeploy when you push to `main` branch (if configured).

---

## 📂 Project Structure

```
server/
├── src/
│   ├── api/
│   │   ├── main.py              # FastAPI app (entry point)
│   │   ├── models.py            # Pydantic request/response models
│   │   ├── dependencies.py      # DB connection, dependencies
│   │   └── routes/
│   │       ├── health.py        # Health endpoint
│   │       ├── champions.py     # Champions endpoints
│   │       ├── matchups.py      # Matchups endpoints
│   │       ├── tier_list.py     # Tier list endpoint
│   │       ├── analysis.py      # Team analysis endpoint
│   │       └── bans.py          # Ban recommendations endpoint
│   ├── analysis/                # Analysis algorithms (copied from client)
│   │   ├── scoring.py           # Champion scoring (17 algorithms)
│   │   ├── tier_list.py         # Tier list generation
│   │   ├── team_analysis.py     # Trio/duo optimization
│   │   └── recommendations.py   # Ban recommendations
│   ├── db.py                    # PostgreSQL adapter (SQLAlchemy async)
│   ├── config.py                # Configuration (DATABASE_URL, etc.)
│   └── config_constants.py      # Constants (copied from client)
├── alembic/
│   ├── env.py                   # Alembic config (PostgreSQL)
│   └── versions/                # Database migrations
├── tests/
│   ├── conftest.py              # Pytest fixtures (test DB, async client)
│   ├── test_health.py           # Health endpoint tests
│   ├── test_champions.py        # Champions endpoints tests
│   ├── test_tier_list.py        # Tier list endpoint tests
│   └── test_analysis.py         # Team analysis tests
├── data/                        # CSV exports (temporary)
│   ├── champions.csv
│   ├── matchups.csv
│   └── synergies.csv
├── scripts/                     # Utility scripts
│   ├── export_sqlite_to_csv.py
│   ├── import_csv_to_postgres.py
│   └── verify_database_integrity.py
├── .env.example                 # Environment variables template
├── .gitignore
├── requirements.txt             # Python dependencies
├── render.yaml                  # Render deployment config
├── alembic.ini                  # Alembic configuration
└── README.md                    # This file
```

---

## 🔧 Troubleshooting

### Database Connection Errors

```
sqlalchemy.exc.OperationalError: could not connect to server
```

**Solutions**:
1. Verify `DATABASE_URL` in `.env` is correct
2. Check Neon dashboard - database might be paused (free tier sleeps after inactivity)
3. Test connection with `psql`:
   ```bash
   psql "postgresql://user:password@host/db?sslmode=require"
   ```

### Port Already in Use

```
ERROR: [Errno 48] Address already in use
```

**Solution**: Kill process using port 8000:
```bash
# Windows
netstat -ano | findstr :8000
taskkill /PID <PID> /F

# Linux/Mac
lsof -ti:8000 | xargs kill -9
```

### Tests Failing

```
FAILED tests/test_api.py::test_get_champions
```

**Solutions**:
1. Ensure database migrations are up to date:
   ```bash
   python -m alembic upgrade head
   ```
2. Verify test database connection in `conftest.py`
3. Check test fixtures are properly initialized

---

## 📝 Next Steps (Phase 2+)

- [ ] **Phase 2**: Setup Celery Worker for automated scraping
- [ ] **Phase 3**: Client modifications (api_client.py, consume API)
- [ ] **Phase 4**: CI/CD pipeline (GitHub Actions)
- [ ] **Phase 5**: Monitoring & analytics (Sentry, Prometheus)

---

## 📄 License

MIT License - See LICENSE file in root directory

---

## 🤝 Contributing

See CONTRIBUTING.md in root directory

---

**Last Updated**: 2026-01-19
**Maintainer**: @pj35
