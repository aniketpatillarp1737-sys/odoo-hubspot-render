from odoo import models, fields, _
from odoo.exceptions import UserError


class HubspotDealImportWizard(models.TransientModel):
    _name = 'hubspot.deal.import.wizard'
    _description = 'HubSpot Deal Import Wizard'

    import_type = fields.Selection([
        ('lead', 'Leads'),
        ('opportunity', 'Opportunities')
    ], string="Import As", required=True, default='opportunity')

    hubspot_instance_id = fields.Many2one(
        'hubspot.instance',
        string="HubSpot Instance",
        required=True
    )
    #
    # def action_confirm_import_deals(self):
    #     self.ensure_one()
    #
    #     # Pass import_type through context
    #     return self.with_context(
    #         deal_import_type=self.import_type
    #     ).hubspot_instance_id.env['deal.queue'].import_deals_from_hubspot(
    #         self.hubspot_instance_id
    #     )

    def action_confirm_import_deals(self):
        self.ensure_one()

        # Pass import_type through context and call the method
        self.env['deal.queue'].with_context(
            deal_import_type=self.import_type
        ).import_deals_from_hubspot(self.hubspot_instance_id)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Deal import has been started. Check the queue for progress.'),
                'type': 'success',
                'sticky': False,
            }
        }