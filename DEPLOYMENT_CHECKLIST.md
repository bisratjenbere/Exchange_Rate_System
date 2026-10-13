# Deployment Checklist
## Quick Reference for Production Deployment

---

## Pre-Deployment (Do This First)

### 1. Local Testing
```bash
# Run all tests
python3 -m pytest tests/ -q

# Should see: "429 passed"
```

### 2. Check Git Status
```bash
# Ensure .gitignore is working
git status

# Should NOT see:
# - .env
# - *.pem
# - *credentials*
# - __pycache__/
```

### 3. Verify Required Files
```bash
ls -la render.yaml requirements.txt gunicorn.conf.py Procfile
# All should exist
```

---

## Deployment Steps (Render.com)

### Step 1: Push to GitHub

```bash
git add .
git commit -m "feat(deploy): production deployment configuration"
git push origin main
```

### Step 2: Create Render Account

1. Go to https://render.com
2. Sign up with GitHub
3. Authorize Render to access your repositories

### Step 3: Deploy via Blueprint

1. Click **"New +"** → **"Blueprint"**
2. Select your repository
3. Render auto-detects `render.yaml`
4. Click **"Apply"**
5. Wait 5-10 minutes for services to spin up

### Step 4: Initialize Database

1. Go to Render Dashboard
2. Click **"exchange-rates-api"** service
3. Click **"Shell"** tab (terminal icon)
4. Run:
```bash
python3 scripts/init_database.py
```

5. Should see:
```
✅ Database initialization complete!
```

### Step 5: Verify Deployment

#### Test API Health
```bash
curl https://your-app.onrender.com/health
# Should return: {"status":"ok"}
```

#### Test Rates Endpoint
```bash
curl https://your-app.onrender.com/rates | jq '.[] | {bank, currency, buying_rate}'
# Should return: JSON array of rates
```

#### Visit UI
Open browser: `https://your-app.onrender.com/`
- Should see: Compare Banks view with data

#### Check Cron Logs
1. Render Dashboard → **"collect-early"** cron job
2. Click **"Logs"**
3. Wait for next scheduled run (05:00, 09:00, or 12:00 UTC)
4. Should see: Collection success logs

---

## Post-Deployment Setup

### 1. Set Up Monitoring (5 minutes)

**UptimeRobot** (recommended):
1. Sign up: https://uptimerobot.com
2. Add HTTP monitor: `https://your-app.onrender.com/health`
3. Set interval: 5 minutes
4. Add your email for alerts

### 2. Document Production URLs

Update your README.md:
```markdown
## Production Deployment

- **API**: https://exchange-rates-api-xxxx.onrender.com
- **Health Check**: https://exchange-rates-api-xxxx.onrender.com/health
- **Admin Dashboard**: https://dashboard.render.com
```

### 3. Team Access

1. Render Dashboard → Settings → Collaborators
2. Invite team members
3. Set appropriate permissions

---

## Verification Checklist

After deployment, verify these:

- [ ] `/health` returns `{"status":"ok"}`
- [ ] `/rates` returns array with 250+ rates
- [ ] UI loads and shows data
- [ ] Cron job "collect-early" scheduled (check Events tab)
- [ ] Cron job "collect-midday" scheduled
- [ ] Cron job "collect-afternoon" scheduled
- [ ] Database has >0 rows: `SELECT COUNT(*) FROM rate_observation;`
- [ ] Uptime monitoring configured
- [ ] Team has Render dashboard access
- [ ] Production URL documented

---

## Troubleshooting

### Issue: "Build failed"

**Check**:
1. requirements.txt has all dependencies
2. Python version in runtime.txt is 3.11.x
3. No syntax errors: `python3 -m py_compile api/app.py`

**Fix**: Review build logs in Render Dashboard

---

### Issue: "Service unhealthy"

**Check**:
1. DATABASE_URL environment variable is set
2. Gunicorn is binding to correct PORT
3. Health endpoint works: `/health`

**Fix**:
```bash
# In Render Shell:
echo $DATABASE_URL  # should be postgresql://...
echo $PORT          # should be a number (10000)
python3 -c "from api.app import app; print(app)"  # should import
```

---

### Issue: "No data in /rates"

**Check**:
1. Database initialized: `python3 scripts/init_database.py`
2. Cron jobs ran: Check logs
3. Sources seeded: `SELECT COUNT(*) FROM rate_source;` should be >0

**Fix**:
```bash
# In Render Shell:
python3 -m scheduler.run_job  # Manual collection run
python3 seed_and_run.py --check  # Check source status
```

---

### Issue: "Cron jobs not running"

**Check**:
1. Cron schedule is valid (use https://crontab.guru)
2. DATABASE_URL is set for cron service
3. Check Events tab for execution history

**Fix**: Trigger manual run in Shell to test

---

## Rollback Procedure

If deployment has issues:

### Option 1: Revert Code
```bash
git revert HEAD
git push origin main
# Render auto-deploys reverted version
```

### Option 2: Manual Deploy Previous Version
1. Render Dashboard → Deployments tab
2. Find working deployment
3. Click **"Redeploy"**

---

## Daily Operations

### Morning Check (09:00 EAT)
```bash
# Check health
curl https://your-app.onrender.com/health

# Check latest rates
curl https://your-app.onrender.com/rates | jq 'length'
# Should be 250+
```

### Review Cron Logs
1. Render Dashboard → Cron Jobs
2. Check all 3 collection jobs ran successfully
3. Note any failed sources

### Weekly Review
1. Check database size (should grow ~1MB/week)
2. Review failed source adapters
3. Update STATUS.md

---

## Scaling Triggers

Upgrade to paid tier ($14/month) when:

- [ ] Cold starts (30s delay) affecting users
- [ ] Need >750 hours/month uptime
- [ ] Database approaching 1GB limit
- [ ] Need faster response times

---

## Emergency Contacts

- **Render Support**: https://render.com/docs/support
- **Render Status**: https://status.render.com
- **Documentation**: See DEPLOYMENT_GUIDE.md

---

## Success Criteria

Your deployment is successful when:

✅ API responds within 2 seconds (after cold start)  
✅ Cron jobs run 3× daily without errors  
✅ Trusted rates count increases daily  
✅ Uptime monitoring shows >99% availability  
✅ No errors in last 24 hours of logs  

**Congratulations! You're in production! 🚀**

