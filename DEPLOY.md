# Deploy Odoo + HubSpot Module on Render

This project runs **Odoo** with the custom **HubSpot Integration** module on the [Render](https://render.com) platform using Docker + PostgreSQL.

---

## Prerequisites

1. A free [Render account](https://dashboard.render.com/register)
2. GitHub / GitLab account (to push this repo)
3. HubSpot API credentials (Private App token or OAuth)

---

## Quick Deploy (Blueprint)

### 1. Push this folder to a Git repository

```bash
cd odoo-hubspot-render
git init
git add .
git commit -m "Odoo HubSpot ready for Render"
git remote add origin <your-repo-url>
git push -u origin main
```

### 2. Deploy with Render Blueprint

1. Go to [Render Dashboard](https://dashboard.render.com)
2. Click **New → Blueprint**
3. Connect the Git repository that contains this project
4. Render will detect `render.yaml` and create:
   - Web Service (`odoo-hubspot`)
   - PostgreSQL database (`odoo-db`)
   - Persistent disk for Odoo data
5. Click **Apply**

### 3. First Login

- Open the service URL (e.g. `https://odoo-hubspot.onrender.com`)
- Master password = value of `ADMIN_PASSWORD` (auto-generated — find it in Render → Environment)
- Create your first database / admin user when prompted

### 4. Install the HubSpot Module

1. Go to **Apps** → remove "Apps" filter → search **Hubspot**
2. Install **Odoo Hubspot Integration**
3. Configure under **HubSpot → Instances**

---

## Manual Deploy (without Blueprint)

1. **Create PostgreSQL**  
   New → PostgreSQL → name `odoo-db` → create

2. **Create Web Service**  
   New → Web Service → connect repo → Runtime: **Docker**

3. **Environment Variables** (link from the database):

| Key            | Value                          |
|----------------|--------------------------------|
| `ADMIN_PASSWORD` | strong password              |
| `DB_HOST`      | from PostgreSQL Internal Host  |
| `DB_PORT`      | 5432                           |
| `DB_USER`      | from PostgreSQL                |
| `DB_PASSWORD`  | from PostgreSQL                |
| `DB_NAME`      | from PostgreSQL                |

4. **Disk**  
   Add disk → Mount path: `/var/lib/odoo` → Size: 10 GB

5. Deploy

---

## Important Notes

| Topic              | Detail |
|--------------------|--------|
| **Odoo version**   | Dockerfile uses `odoo:18.0`. Module declares 20.0 — test compatibility or change the image tag when Odoo 20 official image is available. |
| **Plan**           | Free / Starter is fine for testing. Use Standard+ for production (more RAM, always-on). |
| **Cold starts**    | Free tier spins down after inactivity. First request may take 30–60 s. |
| **Workers**        | Set to `0` on small instances (entrypoint already does this). |
| **HubSpot API**    | After install, add your HubSpot Private App access token in the Instance form. |

---

## Local Test (optional)

```bash
docker build -t odoo-hubspot .
docker run -p 8069:8069 \
  -e ADMIN_PASSWORD=admin \
  -e DB_HOST=host.docker.internal \
  -e DB_PORT=5432 \
  -e DB_USER=odoo \
  -e DB_PASSWORD=odoo \
  -e DB_NAME=odoo \
  odoo-hubspot
```

---

## File Structure

```
odoo-hubspot-render/
├── Dockerfile
├── entrypoint.sh
├── render.yaml          ← Render Blueprint
├── requirements.txt
├── DEPLOY.md            ← this file
├── config/
│   └── odoo.conf
└── addons/
    └── hubspot/         ← your cleaned module
```
