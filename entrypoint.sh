#!/bin/bash
set -e

# Build odoo.conf from environment variables injected by Render
mkdir -p /etc/odoo
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

echo "Starting Odoo (Free tier) with HubSpot module..."
echo "DB Host: ${DB_HOST}"
echo "DB Name: ${DB_NAME}"

# Official image CMD is often "odoo" — strip it if present so we don't pass it as an arg
if [ "$1" = "odoo" ] || [ "$1" = "odoo-bin" ]; then
  shift
fi

exec odoo -c /etc/odoo/odoo.conf "$@"
