#!/bin/bash
set -e

mkdir -p /etc/odoo /var/lib/odoo

cat > /etc/odoo/odoo.conf << EOC
[options]
admin_passwd = ${ADMIN_PASSWORD:-admin}
db_host = ${DB_HOST:-db}
db_port = ${DB_PORT:-5432}
db_user = ${DB_USER:-odoo}
db_password = ${DB_PASSWORD:-odoo}
db_name = ${DB_NAME:-postgres}
addons_path = /mnt/extra-addons,/usr/lib/python3/dist-packages/odoo/addons
data_dir = /var/lib/odoo
list_db = False
proxy_mode = True
workers = 0
max_cron_threads = 1
limit_memory_hard = 2684354560
limit_memory_soft = 2147483648
limit_request = 8192
limit_time_cpu = 600
limit_time_real = 1200
without_demo = all
http_interface = 0.0.0.0
http_port = 8069
EOC

DB="${DB_NAME:-postgres}"

echo "=========================================="
echo " Odoo + HubSpot  |  Free tier on Render"
echo " DB Host: ${DB_HOST}"
echo " DB Name: ${DB}"
echo "=========================================="

if [ "$1" = "odoo" ] || [ "$1" = "odoo-bin" ]; then
  shift
fi

# Check if Odoo tables already exist (fast, no full Odoo boot)
NEED_INIT=$(python3 - << PY
import os, sys
try:
    import psycopg2
    conn = psycopg2.connect(
        host=os.environ.get("DB_HOST", "db"),
        port=os.environ.get("DB_PORT", "5432"),
        user=os.environ.get("DB_USER", "odoo"),
        password=os.environ.get("DB_PASSWORD", "odoo"),
        dbname=os.environ.get("DB_NAME", "postgres"),
        connect_timeout=10,
        sslmode="require",
    )
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'ir_module_module'")
    exists = cur.fetchone() is not None
    cur.close()
    conn.close()
    print("0" if exists else "1")
except Exception as e:
    print("1")
    sys.stderr.write(f"DB check error: {e}\n")
PY
)

if [ "$NEED_INIT" = "1" ]; then
  echo ">>> Database is empty. Installing Odoo base module (2–5 minutes)..."
  odoo -c /etc/odoo/odoo.conf \
       -d "$DB" \
       -i base \
       --stop-after-init \
       --without-demo=all
  echo ">>> Base module installed."
else
  echo ">>> Database already initialized."
fi

echo ">>> Starting Odoo HTTP server on port 8069..."
exec odoo -c /etc/odoo/odoo.conf "$@"
