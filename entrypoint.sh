#!/bin/bash
set -e

# Build odoo.conf from environment variables (Render injects them)
cat > /etc/odoo/odoo.conf << EOC
[options]
admin_passwd = ${ADMIN_PASSWORD:-admin}
db_host = ${DB_HOST:-db}
db_port = ${DB_PORT:-5432}
db_user = ${DB_USER:-odoo}
db_password = ${DB_PASSWORD:-odoo}
db_name = ${DB_NAME:-odoo}
addons_path = /mnt/extra-addons,/usr/lib/python3/dist-packages/odoo/addons
data_dir = /var/lib/odoo
list_db = False
proxy_mode = True
workers = 0
max_cron_threads = 1
without_demo = all
EOC

echo "Starting Odoo with HubSpot module..."
exec odoo -c /etc/odoo/odoo.conf "$@"
