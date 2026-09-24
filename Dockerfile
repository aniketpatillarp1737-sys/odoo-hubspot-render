# ============================================================
# Odoo + HubSpot Integration — Render Free Tier
# ============================================================
FROM odoo:18.0

USER root

# Install HubSpot Python packages
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

# Copy fixed entrypoint
COPY ./entrypoint.sh /entrypoint-custom.sh
RUN chmod +x /entrypoint-custom.sh \
    && chown -R odoo:odoo /mnt/extra-addons \
    && mkdir -p /etc/odoo && chown -R odoo:odoo /etc/odoo

USER odoo

EXPOSE 8069

# Use our entrypoint; no extra CMD args
ENTRYPOINT ["/entrypoint-custom.sh"]
CMD []
