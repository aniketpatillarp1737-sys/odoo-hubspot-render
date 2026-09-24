# Deploy Odoo + HubSpot on Render — FREE Tier

This setup runs completely on Render’s **free plan**.

---

## Free Tier Limits (important)

| Resource        | Free limit                          | Impact |
|-----------------|-------------------------------------|--------|
| Web Service     | Spins down after ~15 min idle       | First request after sleep takes 30–60 s |
| PostgreSQL      | Free DB expires after ~90 days      | Export data before expiry or upgrade |
| Persistent Disk | **Not available** on free web       | Uploaded files / filestore reset on redeploy |
| RAM             | ~512 MB                             | `workers = 0` (already set) |

This is fine for **testing / demo**. Not recommended for production.

---

## Deploy in 5 steps

### 1. Push to GitHub

```bash
cd odoo-hubspot-render
git init
git add .
git commit -m "Odoo HubSpot free deploy"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/odoo-hubspot.git
git push -u origin main
```

### 2. Create Blueprint on Render

1. Go to https://dashboard.render.com
2. Click **New → Blueprint**
3. Connect your GitHub repo
4. Render reads `render.yaml` and shows:
   - Web Service `odoo-hubspot` (free)
   - PostgreSQL `odoo-db` (free)
5. Click **Apply**

### 3. Wait for first deploy

- Build takes 5–10 minutes
- Watch the logs in the Render dashboard

### 4. Open Odoo

- Click the service URL (e.g. `https://odoo-hubspot-xxxx.onrender.com`)
- Master password = value of `ADMIN_PASSWORD`  
  (Render Dashboard → your service → Environment)
- Create the database when prompted

### 5. Install HubSpot module

1. Go to **Apps**
2. Remove the “Apps” filter
3. Search **Hubspot**
4. Click **Install**
5. Configure under **HubSpot → Instances** with your API token

---

## After deploy tips

- **Cold start**: If the site is slow the first time, wait 30–60 seconds — free instances sleep.
- **Keep alive (optional)**: Use a free cron service (e.g. cron-job.org) to ping your URL every 10 minutes so it doesn’t sleep.
- **Database expiry**: Free Postgres is deleted after ~90 days of inactivity. Export a backup before that.
- **Upgrade later**: When ready for production, change `plan: free` → `plan: starter` (or higher) in `render.yaml` and add a disk.

---

## File structure

```
odoo-hubspot-render/
├── Dockerfile
├── entrypoint.sh
├── render.yaml          ← free plans
├── requirements.txt
├── DEPLOY.md
├── config/odoo.conf
└── addons/hubspot/
```
