# 🚀 Render Deployment Guide - Ethiopian Exchange Rate System

This guide will walk you through deploying your application to Render.com step by step.

---

## 📋 Prerequisites

Before you start, make sure you have:
- [x] GitHub account with your code pushed (✅ Done - `github.com:bisratjenbere/Exchange_Rate_System.git`)
- [ ] Render.com account (free tier is fine)
- [ ] Your latest code pushed to `main` branch (✅ Done)

---

## 🎯 Deployment Steps

### Step 1: Sign Up / Log In to Render

1. Go to **https://render.com**
2. Click **"Get Started"** or **"Sign In"**
3. Sign up/in with your **GitHub account** (recommended)
4. Authorize Render to access your GitHub repositories

---

### Step 2: Create a New Blueprint

Render will use your `render.yaml` file to automatically create all services.

1. Once logged in, click **"New +"** button (top right)
2. Select **"Blueprint"**
3. Connect your GitHub repository:
   - Repository: `bisratjenbere/Exchange_Rate_System`
   - Branch: `main`
4. Render will detect your `render.yaml` file
5. Click **"Apply"**

Render will now create:
- ✅ PostgreSQL database (`exchange-rates-db`)
- ✅ Web service (`exchange-rates-api`)
- ✅ 3 cron jobs for data collection

---

### Step 3: Monitor Deployment

After clicking "Apply", Render will:

1. **Create the database** (takes ~30 seconds)
   - Wait for status: **"Available"**
   
2. **Build the web service** (takes ~3-5 minutes)
   - Installing Python dependencies
   - Installing Playwright + Chromium
   - Status will show: **"Building"** → **"Live"**
   
3. **Set up cron jobs** (takes ~1 minute each)
   - They won't run until their scheduled time

**IMPORTANT**: The first build will take 3-5 minutes. Be patient!

---

### Step 4: Initialize the Database

Once the web service is **"Live"**, you need to create the database schema:

#### Option A: Using Render Shell (Recommended)

1. Go to your web service (`exchange-rates-api`)
2. Click the **"Shell"** tab
3. Run these commands:

```bash
# Create the schema
python3 << 'EOF'
import os
import psycopg2

dsn = os.environ['DATABASE_URL'].replace('postgres://', 'postgresql://', 1)
conn = psycopg2.connect(dsn)
with open('db/migrations/001_initial_schema.sql', 'r') as f:
    sql = f.read()
with conn.cursor() as cur:
    cur.execute(sql)
conn.commit()
conn.close()
print("✅ Database schema created successfully!")
EOF

# Seed initial data
python3 seed_and_run.py
```

#### Option B: Using psql (Alternative)

1. Get the database connection string:
   - Go to `exchange-rates-db` service
   - Click **"Info"** tab
   - Copy **"Internal Database URL"**

2. Connect from your local machine:

```bash
# Install psql if you don't have it
# Ubuntu/Debian: sudo apt-get install postgresql-client
# macOS: brew install postgresql

# Connect to database
psql "YOUR_DATABASE_URL_HERE"

# In psql, paste the contents of db/migrations/001_initial_schema.sql
# Then run seed_and_run.py locally with the remote DATABASE_URL
```

---

### Step 5: Verify Deployment

#### Check Web Service

1. Go to `exchange-rates-api` service
2. Click the URL at the top (looks like `https://exchange-rates-api-xxxx.onrender.com`)
3. You should see the web UI with exchange rates

#### Check Database

1. Click **"Shell"** tab in web service
2. Run:

```bash
python3 << 'EOF'
import os
import psycopg2

dsn = os.environ['DATABASE_URL'].replace('postgres://', 'postgresql://', 1)
conn = psycopg2.connect(dsn)
with conn.cursor() as cur:
    cur.execute("SELECT COUNT(*) FROM rate_observation WHERE is_current = TRUE")
    count = cur.fetchone()[0]
    print(f"✅ {count} current exchange rates in database")
conn.close()
EOF
```

#### Check Health Endpoint

Visit: `https://your-app-url.onrender.com/health`

Should return:
```json
{
  "status": "ok",
  "current_rates": 150
}
```

---

### Step 6: Test Cron Jobs (Optional)

Your cron jobs are scheduled to run at:
- 05:00 UTC (08:00 EAT) - Early collection
- 09:00 UTC (12:00 EAT) - Midday collection  
- 12:00 UTC (15:00 EAT) - Afternoon collection

To test them immediately:

1. Go to any cron job service (e.g., `collect-early`)
2. Click **"Manual Deploy"** → **"Run job now"**
3. Check logs to see if data collection worked

---

## 🎛️ Configuration

### Environment Variables

Render automatically sets these from `render.yaml`:
- `DATABASE_URL` - PostgreSQL connection string
- `PYTHON_VERSION` - 3.11
- `FLASK_ENV` - production
- `TZ` - Africa/Addis_Ababa

No manual configuration needed!

---

## 📊 Monitoring & Logs

### View Logs

1. Go to your service (web or cron job)
2. Click **"Logs"** tab
3. Watch real-time logs

### View Metrics

1. Click **"Metrics"** tab
2. See:
   - CPU usage
   - Memory usage
   - Response times
   - HTTP status codes

---

## 🔄 Updating Your App

When you push changes to GitHub:

```bash
git add .
git commit -m "your changes"
git push
```

Render will **automatically**:
1. Detect the push
2. Rebuild your service
3. Deploy the new version
4. Zero-downtime deployment

**Note**: The web service sleeps after 15 min of inactivity (free tier). First request after sleep takes ~30 seconds to wake up.

---

## 🐛 Troubleshooting

### Build Fails

**Check logs**: Go to service → Logs tab → Look for error messages

Common issues:
- Missing dependency: Add to `requirements.txt`
- Python version: Check `PYTHON_VERSION` in render.yaml
- Playwright install: Should be in build command

### Database Connection Fails

**Symptoms**: 503 errors, "Database connection pool is not available"

**Fix**:
1. Check database is **"Available"** (not suspended)
2. Verify `DATABASE_URL` is set correctly
3. Check connection timeout settings

### Web Service Won't Start

**Check**:
1. `gunicorn` is in requirements.txt ✅
2. Start command matches Procfile ✅
3. Port binding: `gunicorn -b 0.0.0.0:$PORT` ✅

### Cron Jobs Not Running

**Check**:
1. Schedule format: `"0 5 * * *"` (correct cron syntax)
2. Time zone: Render uses UTC, adjust accordingly
3. Logs: Click cron job → Logs → See execution history

---

## 💰 Free Tier Limits

Render free tier includes:
- ✅ PostgreSQL: 1 GB storage, 90 day retention
- ✅ Web service: 750 hours/month (always enough)
- ✅ Sleeps after 15 min inactivity
- ✅ Cron jobs: Unlimited runs

**Free tier is perfect for this project!**

---

## 📈 Next Steps After Deployment

1. **Test the UI**: Visit your app URL and browse exchange rates
2. **Wait for cron jobs**: First collection will happen at scheduled time
3. **Monitor logs**: Watch for any errors in first 24 hours
4. **Set up alerts** (optional): Render can email you on failures

---

## 🆘 Need Help?

If you encounter issues:

1. **Check logs first**: 90% of issues are visible in logs
2. **Verify database**: Make sure schema is created
3. **Test locally**: Ensure app works with `python api/app.py`
4. **Render docs**: https://render.com/docs
5. **Ask me**: I'm here to help!

---

## ✅ Success Checklist

After deployment, verify:
- [ ] Web service is **"Live"** (green status)
- [ ] Database is **"Available"** (green status)
- [ ] `/health` endpoint returns `{"status": "ok"}`
- [ ] UI loads at your app URL
- [ ] Database has tables (check with psql or shell)
- [ ] Cron jobs are scheduled correctly

Once all checked, you're live! 🎉

---

**Your app URL will be**: `https://exchange-rates-api-XXXX.onrender.com`

(Render will assign a unique URL when you deploy)
