# GitHub Actions Automated Scraping

**Setup Guide for Daily Automated Scraping to PostgreSQL Neon**

Version: 1.0.0
Last Updated: 2026-02-01

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Setup Instructions](#setup-instructions)
4. [Monitoring](#monitoring)
5. [Troubleshooting](#troubleshooting)
6. [Cost Optimization](#cost-optimization)

---

## Overview

This system automatically scrapes League of Legends champion matchup data daily and updates the PostgreSQL database hosted on Neon.

**Key Features**:
- **Daily Schedule**: Runs at 3:00 AM UTC every day
- **Parallel Scraping**: 5 workers optimized for GitHub Actions 2-core runners
- **PostgreSQL Integration**: Direct writes to Neon serverless PostgreSQL
- **Discord Notifications**: Alerts on failure (optional)
- **Headless Mode**: Firefox headless for CI/CD compatibility

**Performance**:
- **Duration**: ~12 minutes per run
- **Data**: 171 champions, 36,000+ matchups, synergies
- **GitHub Actions Cost**: ~360 minutes/month (18% of free tier quota)

---

## Architecture

### Two-Phase Process

**Phase 1: Scraping to Temporary SQLite**
```
ParallelParser (5 workers)
    ↓
In-Memory SQLite (:memory:)
    ↓
171 champions + matchups + synergies
```

**Phase 2: Transfer to PostgreSQL**
```
Read from SQLite
    ↓
Transform to PostgreSQL schema
    ↓
Bulk insert via SQLAlchemy async
    ↓
Atomic commit (all or nothing)
```

### Files

| File | Purpose |
|------|---------|
| `.github/workflows/scraping.yml` | GitHub Actions workflow definition |
| `server/scripts/scrape_and_update.py` | Main scraping script |
| `src/parallel_parser.py` | Parallel scraping engine |
| `server/src/db.py` | PostgreSQL ORM models |

---

## Setup Instructions

### 1. Configure GitHub Secrets

Navigate to your GitHub repository settings and add the following secrets:

**Settings → Secrets and variables → Actions → New repository secret**

#### Required Secrets

**`DATABASE_URL`** (Required)
- **Description**: PostgreSQL connection string from Neon
- **Format**: `postgresql://user:password@host/database?sslmode=require`
- **Example**: `postgresql://username:password@ep-cool-name-123456.us-east-2.aws.neon.tech/leaguestats?sslmode=require`
- **Where to find**:
  1. Go to [Neon Console](https://console.neon.tech/)
  2. Select your project
  3. Go to "Connection Details"
  4. Copy "Connection string" (select "Pooled connection" for better performance)

#### Optional Secrets

**`DISCORD_WEBHOOK_URL`** (Optional but recommended)
- **Description**: Discord webhook URL for failure notifications
- **Format**: `https://discord.com/api/webhooks/WEBHOOK_ID/WEBHOOK_TOKEN`
- **How to create**:
  1. Open Discord → Server Settings → Integrations → Webhooks
  2. Click "New Webhook"
  3. Name it "GitHub Actions Scraping"
  4. Select channel (e.g., #logs or #monitoring)
  5. Copy webhook URL
  6. Paste into GitHub secret

### 2. Enable GitHub Actions

Ensure GitHub Actions are enabled for your repository:

**Settings → Actions → General → Allow all actions and reusable workflows**

### 3. Verify Workflow

The workflow is automatically triggered by:
- **Schedule**: Daily at 3:00 AM UTC (cron: `0 3 * * *`)
- **Manual**: Via "Run workflow" button in Actions tab

**To test manually**:
1. Go to **Actions** tab
2. Select **Daily Automated Scraping** workflow
3. Click **Run workflow** → **Run workflow**
4. Monitor logs in real-time

---

## Monitoring

### GitHub Actions Dashboard

**View Runs**:
1. Go to **Actions** tab
2. Select **Daily Automated Scraping**
3. View run history with statuses (success ✅ / failure ❌)

**Check Logs**:
1. Click on a specific run
2. Expand "Scrape Data and Update PostgreSQL" job
3. Review detailed logs:
   - Scraping progress
   - Champions scraped
   - PostgreSQL transfer statistics
   - Total duration

### Discord Notifications

If `DISCORD_WEBHOOK_URL` is configured, you'll receive notifications on:
- **Failures only**: Critical errors with full stack trace
- **No spam**: No notifications on successful runs

**Notification Format**:
```
🚨 GitHub Actions Scraping Failed

<error message>
<stack trace>

Timestamp: 2026-02-01 03:12:45 UTC
```

### Expected Log Output (Success)

```
🚀 Starting GitHub Actions Automated Scraping
Timestamp: 2026-02-01 03:00:00 UTC

=== Phase 1: Scraping to Temporary Database ===
Initializing temporary database tables...
Starting parallel scraping (5 workers, headless mode)...
Scraping 171 champions...
Scraping completed in 480.23s
  Champions: 171
  Matchups: 36,234
  Synergies: 24,567

=== Phase 2: Transferring to PostgreSQL ===
Clearing existing data...
Existing data cleared
Transferring champions...
  Transferred 171 champions
Transferring matchups...
  Transferred 36,234 matchups
Transferring synergies...
  Transferred 24,567 synergies
Transfer committed successfully

============================================================
✅ Scraping and Update Completed Successfully
Total Duration: 542.67s
Champions: 171
Matchups: 36,234
Synergies: 24,567
============================================================
```

---

## Troubleshooting

### Common Issues

#### 1. `DATABASE_URL environment variable not set`

**Cause**: GitHub secret not configured or incorrectly named

**Solution**:
1. Verify secret name is exactly `DATABASE_URL` (case-sensitive)
2. Ensure secret contains valid PostgreSQL connection string
3. Re-run workflow

#### 2. `Connection refused` or `SSL required`

**Cause**: Neon requires SSL connections

**Solution**:
- Ensure `DATABASE_URL` includes `?sslmode=require` parameter
- Example: `postgresql://user:pass@host/db?sslmode=require`

#### 3. `Too few champions scraped`

**Cause**: Scraping failed for many champions (rate limiting, site changes)

**Solution**:
1. Check if LoLalytics site structure changed
2. Review scraping logs for specific errors
3. May need to update XPath selectors in `src/parser.py`

#### 4. `Timeout` after 30 minutes

**Cause**: Scraping taking too long (network issues, site slowness)

**Solution**:
- Normal duration: ~12 minutes
- If consistently timing out:
  1. Check GitHub Actions status page
  2. Verify LoLalytics site availability
  3. Consider increasing `timeout-minutes` in workflow (max 360)

#### 5. Firefox/Geckodriver Issues

**Cause**: Firefox or geckodriver installation failed

**Solution**:
- Workflow installs Firefox ESR and geckodriver automatically
- Check "Install Firefox and geckodriver" step logs
- Versions:
  - Firefox: ESR (Extended Support Release)
  - Geckodriver: v0.34.0

---

## Cost Optimization

### GitHub Actions Free Tier

**Quota**: 2,000 minutes/month for free accounts

**Current Usage**:
- **Per run**: ~12 minutes
- **Daily runs**: 30 runs/month
- **Total**: ~360 minutes/month (18% of quota)
- **Remaining**: 1,640 minutes/month for other workflows

**Optimization Tips**:
1. **Manual runs only**: Disable cron schedule, trigger manually when needed
   ```yaml
   # Comment out or remove:
   # schedule:
   #   - cron: '0 3 * * *'
   ```

2. **Weekly instead of daily**: Change to run once per week
   ```yaml
   schedule:
     - cron: '0 3 * * 0'  # Sunday at 3:00 AM UTC
   ```

3. **Reduce workers**: Lower `max_workers` from 5 to 3 (slower but saves time)
   ```python
   parser = ParallelParser(max_workers=3, headless=True)
   ```

### Neon PostgreSQL Free Tier

**Quota**:
- **Compute**: Always-available compute (no auto-suspend)
- **Storage**: 10 GB (current usage: <100 MB)
- **Data Transfer**: Unlimited

**No optimization needed** - current usage well within limits

---

## Manual Execution (Local Testing)

**For testing without GitHub Actions**:

1. **Set environment variables**:
   ```bash
   # Windows (PowerShell)
   $env:DATABASE_URL="postgresql://user:pass@host/db?sslmode=require"
   $env:DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."

   # Linux/Mac
   export DATABASE_URL="postgresql://user:pass@host/db?sslmode=require"
   export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
   ```

2. **Run script**:
   ```bash
   python server/scripts/scrape_and_update.py
   ```

3. **Expected output**: Same as GitHub Actions logs above

---

## Maintenance

### Updating Scraping Logic

If LoLalytics changes their site structure:

1. **Update XPath selectors** in `src/parser.py`
2. **Test locally** with manual execution
3. **Commit changes** and push
4. **Monitor next GitHub Actions run**

### Monitoring Database Size

Neon free tier: 10 GB limit

**Current data**:
- Champions: 171 rows (~10 KB)
- Matchups: 36,000+ rows (~2 MB)
- Synergies: 24,000+ rows (~1.5 MB)
- **Total**: <5 MB per update

**Capacity**: Can store 2,000+ updates before hitting 10 GB limit (years of data)

---

## Support

**Questions or Issues?**

1. Check logs in GitHub Actions tab
2. Review Discord notifications (if configured)
3. Consult this documentation
4. Open an issue on GitHub repository

**Related Documentation**:
- [Neon PostgreSQL Docs](https://neon.tech/docs/)
- [GitHub Actions Docs](https://docs.github.com/en/actions)
- [Selenium WebDriver Docs](https://www.selenium.dev/documentation/)

---

**Last Updated**: 2026-02-01
**Version**: 1.0.0
**Maintainer**: @pj35
