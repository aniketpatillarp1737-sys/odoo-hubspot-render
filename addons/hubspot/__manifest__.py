{
    'name': 'Odoo Hubspot Integration',
    'version': '18.0.1.0.0',
    'category': 'Services',
    'author': 'Your Company',
    'website': '',
    'summary': 'Integration of Odoo Partners with hubspot contacts Odoo Hubspot Integration App odoo hubspot odoo Hubspot connector odoo Hubspot integration hubspot crm',
    'description': """
Hubspot Integration
==========================
Odoo Partners are imported and updated from and to Hubspot.
Using Hubspot API data is synced.
<keywords>
Odoo Hubspot Integration App
Hubspot
odoo hubspot
odoo Hubspot connector
odoo Hubspot integration
hubspot crm
    """,
    'depends': ['base', 'base_setup', 'sale_management', 'crm', 'stock','product'],
    'data': [
        'security/ir.access.csv',
        'security/res_groups.xml',
        'data/tag_data.xml',
        'data/hubspot_service_product.xml',
        'views/res_partner_view.xml',
        'views/hubspot_scheduler.xml',
        'views/hubspot_instance_view.xml',
        'views/hubspot_logger_view.xml',
        'views/mail_activity_view.xml',
        'views/mail_message_view.xml',
        'views/crm_lead_view.xml',
        'wizards/message_view.xml',
        'wizards/hubspot_deals_wizard_view.xml',
        'views/calendar_event_view.xml',
        'views/hubspot_contact_fields.xml',
        'views/hubspot_company_fields.xml',
        'views/hubspot_deals_fields.xml',
        'views/product_template_view.xml',
        'views/tax_view.xml',
        'views/sale_quote.xml',
        'views/contact_queue_view.xml',
        'views/contact_queue_line_view.xml',
        'views/company_queue_view.xml',
        'views/company_queue_line_view.xml',
        'views/deal_queue_view.xml',
        'views/deal_queue_line_view.xml'

    ],
    # Backend assets for the HubSpot Logger dashboard ######
    'assets': {
        'web.assets_backend': [
            'hubspot/static/src/hubspot_logger_dashboard/hubspot_logger_dashboard.scss',
            'hubspot/static/src/hubspot_logger_dashboard/hubspot_logger_dashboard.js',
            'hubspot/static/src/hubspot_logger_dashboard/hubspot_logger_dashboard.xml',
            'hubspot/static/src/hubspot_instance/hubspot_instance.scss',
            'hubspot/static/src/hubspot_instance/hubspot_instance_overview.js',
            'hubspot/static/src/hubspot_instance/hubspot_instance_overview.xml',
        ],
    },
    'images': ['static/description/Odoo_HubSpot _ntegration.gif'],
    'live_test_url': '',
    'price': 299.00,
    'currency': 'USD',
    'license': 'OPL-1',
    'application': True,
    'auto_install': False,
    'installable': True,
}
