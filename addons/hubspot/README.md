# Odoo HubSpot Integration

Seamless bidirectional integration between **Odoo** and **HubSpot CRM**.

Sync contacts, companies, deals, activities, and more between Odoo and HubSpot in real time.

---

## Features

- Sync **Contacts** (Partners) between Odoo and HubSpot
- Sync **Companies**
- Sync **Deals / Opportunities**
- Sync **Activities** and **Messages**
- Field mapping support for Contacts, Companies, and Deals
- Queue-based processing for reliable data transfer
- Multi-instance support
- Detailed logging and dashboard
- Scheduler-based automatic synchronization

---

## Requirements

- **Odoo** 20.0
- Python packages (install via pip):

```bash
pip3 install hubspot-connection==1.0rc8.post0
pip3 install hubspot-contacts==1.1.1
```

---

## Installation

1. Extract the module into your Odoo `addons` directory.
2. Install the required Python packages (see above).
3. Restart the Odoo server.
4. Update the Apps list.
5. Search for **Odoo Hubspot Integration** and install it.

---

## Configuration

1. Go to **HubSpot → Instances**.
2. Create a new HubSpot instance and provide your HubSpot API credentials.
3. Configure field mappings for Contacts, Companies, and Deals as needed.
4. Enable the desired schedulers for automatic sync.

---

## Supported Models

| Odoo Model          | HubSpot Object |
|---------------------|----------------|
| `res.partner`       | Contacts / Companies |
| `crm.lead`          | Deals          |
| `mail.activity`     | Activities     |
| `calendar.event`    | Meetings       |
| `product.template`  | Products       |

---

## License

OPL-1 (Odoo Proprietary License v1.0)
