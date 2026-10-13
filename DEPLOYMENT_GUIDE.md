# Production Deployment Guide
## Ethiopian Bank Exchange Rate Intelligence System

**Target**: Free hosting for production MVP  
**Role**: Senior Deployment Engineer  
**Date**: 2026-10-13

---

## Executive Summary

This system requires:
1. **Web application** (Flask API + UI)
2. **PostgreSQL database** (with constraints and indexes)
3. **Scheduled jobs** (3× daily collection runs)
4. **Persistent storage** (for rate_observation history)

**Recommended Stack**: Render.com (free tier covers all requirements)

---

## Part 1: Platform Comparison

### Option A: Render.com (RECOMMENDED ⭐)

**Pros**:
- ✅ Free PostgreSQL with 1GB storage (enough for 5+ years of data)
- ✅ Native cron jobs (scheduled collection runs)
- ✅ Zero-downtime deploys
- ✅ Automatic HTTPS
- ✅ GitHub auto-deploy on push
- ✅ Environment variables management
- ✅ View logs in real-time

**Cons**:
- ⚠️ Free tier spins down after 15 min inactivity (750 hrs/month)
- ⚠️ Cold start ~30 seconds

**Free Tier Limits**:
- Web service: 750 hours/month
- PostgreSQL: 1GB storage, 90-day retention
- Cron jobs: Unlimited

**Verdict**: Best for this project. Native support for all requirements.

---

### Option B: Railway.app

**Pros**:
- ✅ $5 free credit monthly
- ✅ PostgreSQL included
- ✅ Cron jobs via Railway Cron
- ✅ Excellent developer experience

**Cons**:
- ⚠️ Credits run out quickly (~200 hours/month)
- ⚠️ No true free tier anymore

**Verdict**: Good but limited free usage.

---

### Option C: Fly.io

**Pros**:
- ✅ 3 VMs with 256MB RAM free
- ✅ Persistent volumes (3GB free)
- ✅ PostgreSQL via Fly Postgres

**Cons**:
- ⚠️ More complex setup
- ⚠️ Need to configure cron manually

**Verdict**: More control but steeper learning curve.

---

### Option D: PythonAnywhere (Backup Option)

**Pros**:
- ✅ MySQL included (can adapt from PostgreSQL)
- ✅ Task scheduling built-in
- ✅ Easy to use

**Cons**:
- ❌ Free tier limited to 100 seconds/day CPU
- ❌ Would need MySQL migration
- ❌ Very restrictive for data collection

**Verdict**: Not suitable for this use case.

---

## Part 2: Render.com Deployment (Step-by-Step)

### Prerequisites

1. **GitHub account** with this repository pushed
2. **Render.com account** (free signup)
3. **Working local setup** (tests passing)

---

### Step 1: Prepare Repository

Create `render.yaml` (Blueprint file):

```yaml
services:
  # PostgreSQL Database
  - type: pserv
    name: exchange-rates-db
    plan: free
    databaseName: exchange_rates
    databaseUser: exchange_rates_user
    ipAllowList: []  # allow from anywhere

  # Web Service (Flask API + UI)
  - type: web
    name: exchange-rates-api
    env: python
    plan: free
    buildCommand: pip install -r requirements.txt
    startCommand: gunicorn -w 2 -b 0.0.0.0:$PORT api.app:app
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: exchange-rates-db
          property: connectionString
      - key: PYTHON_VERSION
        value: 3.11
    healthCheckPath: /health

  # Cron Job 1: Early Collection (08:00 EAT)
  - type: cron
    name: collect-early
    env: python
    schedule: "0 5 * * *"  # 05:00 UTC = 08:00 EAT
    buildCommand: pip install -r requirements.txt
    startCommand: python3 -m scheduler.run_job
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: exchange-rates-db
          property: connectionString

  # Cron Job 2: Mid-day Collection (12:00 EAT)
  - type: cron
    name: collect-midday
    env: python
    schedule: "0 9 * * *"  # 09:00 UTC = 12:00 EAT
    buildCommand: pip install -r requirements.txt
    startCommand: python3 -m scheduler.run_job
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: exchange-rates-db
          property: connectionString

  # Cron Job 3: Afternoon Collection (15:00 EAT)
  - type: cron
    name: collect-afternoon
    env: python
    schedule: "0 12 * * *"  # 12:00 UTC = 15:00 EAT
    buildCommand: pip install -r requirements.txt
    startCommand: python3 -m scheduler.run_job
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: exchange-rates-db
          property: connectionString
```

---

### Step 2: Create Requirements File

Create `requirements.txt`:

```txt
# Web Framework
Flask==3.0.0
gunicorn==21.2.0

# Database
psycopg2-binary==2.9.9

# HTML Parsing
beautifulsoup4==4.12.2
lxml==4.9.3

# HTTP Requests
requests==2.31.0

# Testing (optional for production, but good to have)
pytest==7.4.3
```

---

### Step 3: Create Gunicorn Config (Optional)

Create `gunicorn.conf.py`:

```python
# Gunicorn configuration for Render.com

import multiprocessing
import os

# Bind to PORT provided by Render
bind = f"0.0.0.0:{os.environ.get('PORT', '5000')}"

# Worker configuration
workers = 2  # Free tier has limited resources
worker_class = "sync"
worker_connections = 100
timeout = 120  # 2 minutes (bank fetches can be slow)
keepalive = 5

# Logging
accesslog = "-"  # stdout
errorlog = "-"   # stderr
loglevel = "info"

# Process naming
proc_name = "exchange-rates-api"

# Server mechanics
daemon = False
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None
```

---

### Step 4: Create Deployment Scripts

Create `scripts/init_database.py`:

```python
#!/usr/bin/env python3
"""
Initialize database on first deploy.
Run this manually after first deployment.
"""
import os
import psycopg2

DSN = os.environ.get("DATABASE_URL")

if not DSN:
    print("ERROR: DATABASE_URL not set")
    exit(1)

print("Connecting to database...")
conn = psycopg2.connect(DSN)

print("Running migration 001_initial_schema.sql...")
with open("db/migrations/001_initial_schema.sql") as f:
    sql = f.read()
    
with conn.cursor() as cur:
    cur.execute(sql)
    
conn.commit()
print("✓ Schema created successfully")

print("\nSeeding sources from register...")
from seed_and_run import seed
seed(conn)
print("✓ Sources seeded")

conn.close()
print("\n✓ Database initialization complete")
```

Create `scripts/deploy_check.sh`:

```bash
#!/bin/bash
# Pre-deployment checklist

set -e

echo "=== Pre-Deployment Checks ==="

echo "1. Running tests..."
python3 -m pytest tests/ -q || { echo "❌ Tests failed"; exit 1; }
echo "✓ Tests passed"

echo "2. Checking required files..."
for file in requirements.txt render.yaml api/app.py scheduler/run_job.py; do
  if [ ! -f "$file" ]; then
    echo "❌ Missing $file"
    exit 1
  fi
done
echo "✓ All required files present"

echo "3. Checking Python syntax..."
python3 -m py_compile api/app.py scheduler/run_job.py
echo "✓ Python syntax valid"

echo "4. Checking .gitignore..."
if ! grep -q "\.env" .gitignore; then
  echo "⚠️  Warning: .env not in .gitignore"
fi
echo "✓ .gitignore configured"

echo ""
echo "✅ All checks passed - ready to deploy!"
```

---

### Step 5: Update Flask App for Production

Create `api/wsgi.py`:

```python
"""
WSGI entry point for production deployment.
Gunicorn will import this.
"""
import os
from api.app import app

# Set production defaults
if not os.environ.get("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL must be set in production")

# Health check endpoint is already in app.py
# Just export the app
application = app

if __name__ == "__main__":
    # For local testing
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
```

Update `api/app.py` to handle Render's DATABASE_URL format:

```python
# At the top of api/app.py, update DSN handling:

import os
import psycopg2

# Render provides DATABASE_URL in format:
# postgres://user:pass@host:port/dbname
# psycopg2 needs postgresql://...
DSN = os.environ.get("DATABASE_URL", "dbname=exchange_rates")
if DSN.startswith("postgres://"):
    DSN = DSN.replace("postgres://", "postgresql://", 1)
```

---

### Step 6: Create Procfile (Backup for other platforms)

Create `Procfile`:

```
web: gunicorn -c gunicorn.conf.py api.app:app
scheduler: python3 -m scheduler.run_job
```

---

### Step 7: Deploy to Render

#### 7.1 Push to GitHub

```bash
git add render.yaml requirements.txt gunicorn.conf.py scripts/ api/wsgi.py
git commit -m "feat(deploy): add Render.com deployment configuration"
git push origin main
```

#### 7.2 Connect Render to GitHub

1. Go to https://render.com
2. Sign up / Log in
3. Click **"New +"** → **"Blueprint"**
4. Connect your GitHub account
5. Select your repository
6. Render will detect `render.yaml` and create all services

#### 7.3 Initialize Database (One-Time)

After deployment completes:

1. Go to Render Dashboard → **exchange-rates-api** → **Shell**
2. Run:
```bash
python3 scripts/init_database.py
```

#### 7.4 Verify Deployment

1. Visit your app URL: `https://exchange-rates-api-xxxx.onrender.com`
2. Check `/health` endpoint
3. Check `/rates` endpoint
4. View cron job logs to see collection runs

---

## Part 3: Post-Deployment Configuration

### 3.1 Environment Variables

Render automatically sets:
- `DATABASE_URL` (from database connection)
- `PORT` (for web service)

Add these in Render Dashboard → Service → Environment:

```
FLASK_ENV=production
PYTHON_VERSION=3.11
TZ=Africa/Addis_Ababa
```

### 3.2 Database Backups

Render free tier: 90-day retention, no manual backups.

**Workaround**: Create a backup cron job:

Add to `render.yaml`:

```yaml
  # Weekly Backup (Sunday 00:00 UTC)
  - type: cron
    name: backup-db
    env: python
    schedule: "0 0 * * 0"
    buildCommand: pip install -r requirements.txt
    startCommand: python3 scripts/backup_db.py
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: exchange-rates-db
          property: connectionString
```

Create `scripts/backup_db.py`:

```python
#!/usr/bin/env python3
"""
Weekly database backup to logs.
Can be extended to upload to S3/B2 later.
"""
import os
import subprocess
from datetime import datetime

DSN = os.environ.get("DATABASE_URL")
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

print(f"=== Database Backup {timestamp} ===")

# pg_dump to stdout (Render captures logs)
cmd = [
    "pg_dump",
    "--no-owner",
    "--no-acl",
    "--clean",
    "--if-exists",
    DSN
]

try:
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    print(result.stdout)
    print(f"\n✓ Backup completed: {len(result.stdout)} bytes")
except subprocess.CalledProcessError as e:
    print(f"❌ Backup failed: {e.stderr}")
    exit(1)
```

### 3.3 Monitoring & Alerts

Create `scripts/health_check.py`:

```python
#!/usr/bin/env python3
"""
Health check script for monitoring.
Run this from external service (e.g., UptimeRobot, Better Uptime)
"""
import os
import sys
import psycopg2
import requests

API_URL = os.environ.get("API_URL", "https://exchange-rates-api.onrender.com")
DSN = os.environ.get("DATABASE_URL")

def check_api():
    """Check API health endpoint"""
    try:
        resp = requests.get(f"{API_URL}/health", timeout=10)
        if resp.status_code == 200 and resp.json().get("status") == "ok":
            print("✓ API healthy")
            return True
        else:
            print(f"❌ API unhealthy: {resp.status_code}")
            return False
    except Exception as e:
        print(f"❌ API unreachable: {e}")
        return False

def check_database():
    """Check database connectivity"""
    try:
        conn = psycopg2.connect(DSN)
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM rate_observation WHERE is_current = TRUE")
            count = cur.fetchone()[0]
        conn.close()
        print(f"✓ Database healthy ({count} current rates)")
        return True
    except Exception as e:
        print(f"❌ Database unhealthy: {e}")
        return False

def check_freshness():
    """Check data freshness"""
    try:
        conn = psycopg2.connect(DSN)
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM rate_source 
                WHERE is_enabled = TRUE 
                  AND last_success_at > now() - interval '24 hours'
            """)
            fresh = cur.fetchone()[0]
        conn.close()
        
        if fresh >= 5:
            print(f"✓ Data fresh ({fresh} sources updated in 24h)")
            return True
        else:
            print(f"⚠️  Data stale ({fresh} sources updated in 24h)")
            return False
    except Exception as e:
        print(f"❌ Freshness check failed: {e}")
        return False

if __name__ == "__main__":
    checks = [
        check_api(),
        check_database(),
        check_freshness()
    ]
    
    if all(checks):
        print("\n✅ All checks passed")
        sys.exit(0)
    else:
        print("\n❌ Some checks failed")
        sys.exit(1)
```

---

## Part 4: Free Monitoring Services

### Option 1: UptimeRobot (Recommended)

**Setup**:
1. Sign up at https://uptimerobot.com (50 monitors free)
2. Add HTTP(s) monitor: `https://your-app.onrender.com/health`
3. Set check interval: 5 minutes
4. Add email alert

### Option 2: Better Uptime

**Setup**:
1. Sign up at https://betteruptime.com (10 monitors free)
2. Add monitor with `/health` endpoint
3. Configure Slack/email alerts

### Option 3: Render Native Monitoring

Render Dashboard shows:
- Service health
- CPU/Memory usage
- Request logs
- Cron job logs

---

## Part 5: Deployment Checklist

### Pre-Deployment

- [ ] All tests passing: `pytest tests/ -q`
- [ ] .gitignore configured (no secrets)
- [ ] requirements.txt up to date
- [ ] render.yaml validated
- [ ] Database migration tested locally
- [ ] Seed script tested

### First Deployment

- [ ] Repository pushed to GitHub
- [ ] Render Blueprint deployed
- [ ] Database initialized: `python3 scripts/init_database.py`
- [ ] Web service healthy: visit `/health`
- [ ] First collection run: check cron logs
- [ ] Trusted rates visible: visit `/rates`

### Post-Deployment

- [ ] Uptime monitoring configured
- [ ] Email alerts set up
- [ ] Team has access to Render dashboard
- [ ] Backup strategy documented
- [ ] Rollback plan tested

---

## Part 6: Troubleshooting

### Issue 1: "Application failed to start"

**Symptoms**: Render logs show startup errors

**Solutions**:
1. Check `requirements.txt` has all dependencies
2. Verify `DATABASE_URL` is set (automatic from render.yaml)
3. Check Python version: `python3 --version` in Shell
4. Review build logs in Render Dashboard

### Issue 2: Cron jobs not running

**Symptoms**: No collection runs in logs

**Solutions**:
1. Check cron job logs in Render Dashboard
2. Verify schedule syntax (use https://crontab.guru)
3. Test manually: Run `python3 -m scheduler.run_job` in Shell
4. Check DATABASE_URL is set for cron service

### Issue 3: Database connection errors

**Symptoms**: psycopg2.OperationalError

**Solutions**:
1. Verify DATABASE_URL format (postgresql:// not postgres://)
2. Check database service is running
3. Verify IP allowlist (should be empty for Render services)
4. Test connection: `psql $DATABASE_URL` in Shell

### Issue 4: Cold start slowness

**Symptoms**: First request after inactivity takes 30+ seconds

**Solutions**:
1. This is expected on free tier (spin-down after 15 min)
2. Use external monitoring to keep alive (5-min ping)
3. Upgrade to paid tier for 24/7 uptime ($7/month)

### Issue 5: Out of database storage

**Symptoms**: "disk full" errors (unlikely but possible)

**Solutions**:
1. Check current usage: `SELECT pg_size_pretty(pg_database_size('exchange_rates'));`
2. Delete old `raw_capture` entries (90-day retention)
3. Upgrade to paid tier (10GB for $7/month)

---

## Part 7: Scaling Plan

### When to Upgrade (Paid Tier)

**Indicators**:
- Cold starts affecting user experience
- Need more than 750 hours/month uptime
- Database approaching 1GB limit
- Need faster response times

**Render Pricing** (as of 2024):
- **Web Service**: $7/month (512MB RAM, always on)
- **PostgreSQL**: $7/month (10GB storage)
- **Cron Jobs**: Free (no limits)

**Total**: ~$14/month for production-grade hosting

### Alternative: Self-Hosted VPS

If costs grow, consider:
- **DigitalOcean Droplet**: $6/month (1GB RAM)
- **Hetzner Cloud**: €4/month (2GB RAM)
- **Linode**: $5/month (1GB RAM)

Self-hosting gives full control but requires more DevOps work.

---

## Part 8: Security Hardening

### 8.1 Database Security

```sql
-- Create read-only user for API (recommended)
CREATE USER exchange_rates_readonly WITH PASSWORD 'strong_password_here';
GRANT CONNECT ON DATABASE exchange_rates TO exchange_rates_readonly;
GRANT USAGE ON SCHEMA public TO exchange_rates_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO exchange_rates_readonly;

-- API uses read-only user
-- Cron jobs use full-access user
```

### 8.2 API Rate Limiting

Add to `api/app.py`:

```python
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

@app.route("/rates")
@limiter.limit("30 per minute")
def rates():
    # ... existing code
```

Update `requirements.txt`:
```
Flask-Limiter==3.5.0
```

### 8.3 CORS Configuration

If adding frontend separately:

```python
from flask_cors import CORS

CORS(app, resources={
    r"/rates/*": {"origins": ["https://your-frontend-domain.com"]},
    r"/health": {"origins": "*"}
})
```

---

## Part 9: CI/CD Pipeline (Optional)

### GitHub Actions

Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy to Render

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_DB: exchange_rates_test
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
    
    - name: Run tests
      env:
        DATABASE_URL: postgresql://test:test@localhost:5432/exchange_rates_test
      run: |
        pytest tests/ -v
    
    - name: Deploy to Render
      if: github.ref == 'refs/heads/main'
      run: |
        echo "Render auto-deploys on push to main"
        # Or trigger manual deploy via Render API
```

---

## Part 10: Production Runbook

### Daily Operations

**Morning Check** (09:00 EAT):
1. Visit https://your-app.onrender.com/health
2. Check cron logs in Render Dashboard
3. Verify trusted rate count: `/rates` endpoint

**Evening Check** (17:00 EAT):
1. Review collection success rate (logs)
2. Check for any alerts from UptimeRobot
3. Verify all 3 cron jobs ran successfully

### Weekly Operations

**Sunday**:
1. Review backup logs
2. Check database size: `SELECT pg_size_pretty(pg_database_size('exchange_rates'));`
3. Review failed source adapters (Group B status)
4. Plan fixes for upcoming week

### Monthly Operations

**First Monday**:
1. Review uptime metrics (should be >99% excl. cold starts)
2. Review data coverage (how many banks collecting successfully)
3. Update STATUS.md with month's progress
4. Review and close any open issues

### Incident Response

**If API is down**:
1. Check Render status: https://status.render.com
2. Check service logs in Render Dashboard
3. Restart service: Render Dashboard → Manual Deploy
4. If DB issue: Check connection in Shell

**If data is stale**:
1. Check cron job logs (did they run?)
2. Manually trigger: `python3 -m scheduler.run_job` in Shell
3. Check individual source failures
4. Review adapter error logs

**If database is full**:
1. Delete old raw_capture: `DELETE FROM raw_capture WHERE retention_until < now();`
2. Vacuum: `VACUUM FULL;`
3. Consider upgrading storage tier

---

## Summary

**Deployment Time**: 1-2 hours for first deployment

**Monthly Cost**: $0 (free tier) or $14 (production tier)

**Maintenance**: ~1 hour/week

**Next Steps**:
1. Create Render account
2. Push code with deployment files
3. Deploy via Blueprint
4. Initialize database
5. Set up monitoring
6. Verify first collection run

**You're ready for production!** 🚀

