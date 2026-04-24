# Deployment Guide: Vercel (Frontend) + Render (Backend)

This guide covers deploying the Agentic Trading dashboard to Vercel and the API to Render.

## Architecture

```
Vercel (Frontend)
├── Static HTML/CSS/JS files
├── Served from: agentic-trading/frontend/
└── Calls API at: https://agentic-trading-api.onrender.com

Render (Backend)
├── FastAPI Python server
├── Served from: agentic-trading/backend/
└── Exposes: /health, /runs, /compare, /ticker, etc.
```

## Frontend Deployment (Vercel)

### Step 1: Connect GitHub

1. Go to [vercel.com](https://vercel.com) and sign in with GitHub
2. Click "Import Project"
3. Select `https://github.com/Allan-Feng/AgenticTrading`
4. Vercel will auto-detect the `vercel.json` configuration

### Step 2: Configure Project Root

In Vercel Dashboard → Project Settings:
- **Root Directory:** `agentic-trading/frontend`
- **Build Command:** (leave blank - static files only)
- **Output Directory:** `.` (current directory)

### Step 3: Add Environment Variables

In Vercel Dashboard → Settings → Environment Variables:

```
API_URL = https://agentic-trading-api.onrender.com
```

### Step 4: Update Frontend Config

In `agentic-trading/frontend/app.js`, update the API detection:

```javascript
const API_BASE = window.location.hostname === 'localhost' 
  ? 'http://localhost:8000'
  : 'https://agentic-trading-api.onrender.com';  // ← Update this URL
```

### Step 5: Deploy

Push to GitHub or click "Deploy" in Vercel dashboard.

**Frontend URL:** `https://your-project.vercel.app`

---

## Backend Deployment (Render)

### Step 1: Create New Web Service

1. Go to [render.com](https://render.com) and sign in
2. Click "New +" → "Web Service"
3. Connect GitHub and select `Allan-Feng/AgenticTrading`

### Step 2: Configure Service

**Basic Settings:**
- **Name:** `agentic-trading-api`
- **Environment:** Python 3
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `python app.py`
- **Root Directory:** `agentic-trading/backend`

### Step 3: Add Persistent Storage (for SQLite)

1. In Render dashboard, go to Disks
2. Click "Add Disk"
   - **Name:** `database`
   - **Mount Path:** `/app/data`
   - **Size:** 1 GB

3. Update backend code to use persistent path:
   ```python
   DATABASE_PATH = '/app/data/backtest.db'  # Uses persistent Render disk
   ```

### Step 4: Add Environment Variables

In Render Dashboard → Environment:

```
PYTHONUNBUFFERED=true
DATABASE_URL=/app/data/backtest.db
CORS_ORIGINS=https://your-project.vercel.app,http://localhost:3000
```

### Step 5: Deploy

Render will automatically build and deploy on every GitHub push.

**Backend URL:** `https://agentic-trading-api.onrender.com`

---

## Local Testing

Before deploying, test locally:

```bash
# Terminal 1: Start backend
cd agentic-trading/backend
python app.py
# Server runs at http://localhost:8000

# Terminal 2: Open frontend
# Visit http://localhost:8000/ in browser
# (Backend serves frontend static files)
```

---

## Troubleshooting

### Frontend shows "Cannot read properties of null"

**Solution:** Update `API_URL` in Vercel environment variables to match your Render backend URL.

### Backend crashes on startup

**Solution:** Check Render logs for missing dependencies
```bash
# Run locally to test:
cd agentic-trading/backend
pip install -r requirements.txt
python app.py
```

### Database file not persisting

**Solution:** Render disks only persist with `mount` path set correctly. Verify:
```python
# In backend/database.py
DATABASE_PATH = '/app/data/backtest.db'  # Must use /app/data
```

### CORS errors when calling API from frontend

**Solution:** Add Vercel domain to backend CORS:

In `agentic-trading/backend/app.py`:
```python
origins = [
    "http://localhost:3000",
    "http://localhost:8000",
    "https://your-project.vercel.app",  # Add your Vercel URL
    "https://agentic-trading-api.onrender.com"
]
```

Then redeploy to Render.

---

## Monitoring

### Vercel
- Dashboard: [vercel.com/dashboard](https://vercel.com/dashboard)
- Logs: Click project → "Deployments" tab
- Analytics: View page load times and errors

### Render
- Dashboard: [render.com/dashboard](https://render.com/dashboard)
- Logs: Click service → "Logs" tab
- Metrics: CPU, memory, disk usage

---

## Updating Code

The deployment is automatic on every GitHub push:

```bash
# Make changes locally
cd agentic-trading/frontend
# Edit files...

# Commit and push
git add .
git commit -m "Update dashboard styling"
git push origin main

# Vercel & Render automatically redeploy within 1-2 minutes
```

---

## Environment URLs

**Development:**
- Frontend: `http://localhost:8000/`
- Backend: `http://localhost:8000/`

**Production:**
- Frontend: `https://your-project.vercel.app`
- Backend: `https://agentic-trading-api.onrender.com`

---

## Next Steps

1. ✅ Deploy backend to Render first (takes ~5 min)
2. ✅ Note the Render URL (e.g., `https://agentic-trading-api.onrender.com`)
3. ✅ Add that URL to Vercel environment variables
4. ✅ Deploy frontend to Vercel (takes ~2 min)
5. ✅ Test: Visit Vercel URL, check console for API calls

That's it! Your dashboard is now live. 🚀
