from odoo import models, fields, api, _
import logging

_logger = logging.getLogger("deal Queue Line")

class DealQueueLine(models.Model):
    _name = "deal.queue.line"
    _description = "Hubspot Deal Queue Line"

    name = fields.Char(string="Deal")
    hubspot_instance_id = fields.Many2one("hubspot.instance", string="Instance")
    state = fields.Selection([("draft", "Draft"), ("failed", "Failed"), ("done", "Done"),
                              ("cancel", "Cancelled")],
                             default="draft")
    deal_queue_id = fields.Many2one("deal.queue", required=True, copy=False)
    processed_last_date = fields.Datetime()
    hubspot_deal_data = fields.Text()
    hubspot_deal_data_id = fields.Char(string="Hubspot deal Id")
    hubspot_image_import_state = fields.Selection([('pending', 'Pending'), ('done', 'Done')], default='done')
    hubspot_image_data = fields.Text()
    hubspot_pipeline = fields.Text()
    hubspot_deal_stage = fields.Text()
    import_type = fields.Selection([
        ('lead', 'Lead'),
        ('opportunity', 'Opportunity')
    ], string="Import Type", default='opportunity', help="Determines whether to import as Lead or Opportunity")

    def process_queue_line_deal_data(self):
        if self.deal_queue_id:
            queue_id = self.deal_queue_id
            hubspot_instance_id = queue_id.hubspot_instance_id
            for line in self:
                # Pass import_type through context
                self.env['crm.lead'].with_context(
                    deal_import_type=line.import_type
                ).hubspot_queue_deal_create(line, hubspot_instance_id)