# ============================================================
# Odoo + HubSpot Integration — Render Deployment
# ============================================================
# Note: Official image currently at 18.0.
# If you need exact Odoo 20, replace the base image later.
FROM odoo:18.0

USER root

# Install system deps + HubSpot Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3-pip \
    && pip3 install --no-cache-dir --break-system-packages \
        hubspot-connection==1.0rc8.post0 \
        hubspot-contacts==1.1.1 \
        requests \
        six \
        future \
        voluptuous \
    || pip3 install --no-cache-dir \
        hubspot-connection==1.0rc8.post0 \
        hubspot-contacts==1.1.1 \
        requests \
        six \
        future \
        voluptuous \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy custom HubSpot module
COPY ./addons /mnt/extra-addons

# Copy entrypoint that builds odoo.conf from Render env vars
COPY ./entrypoint.sh /entrypoint-custom.sh
RUN chmod +x /entrypoint-custom.sh \
    && chown -R odoo:odoo /mnt/extra-addons

USER odoo

EXPOSE 8069

ENTRYPOINT ["/entrypoint-custom.sh"]
CMD ["odoo"]
