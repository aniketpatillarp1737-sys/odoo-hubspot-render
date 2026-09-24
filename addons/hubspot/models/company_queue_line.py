from odoo import models, fields, api, _
import logging

_logger = logging.getLogger("Company Queue Line")

class companyQueueLine(models.Model):
    _name = "company.queue.line"
    _description = "Hubspot Company Queue Line"


    name = fields.Char(string="Company")
    hubspot_instance_id = fields.Many2one("hubspot.instance", string="Instance")
    state = fields.Selection([("draft", "Draft"), ("failed", "Failed"), ("done", "Done"),
                              ("cancel", "Cancelled")],
                             default="draft")
    company_queue_id = fields.Many2one("company.queue", required=True,
                                            copy=False)
    processed_last_date = fields.Datetime()
    hubspot_company_data = fields.Text()
    hubspot_company_data_id = fields.Char(string="Hubspot Company Id")
    hubspot_image_import_state = fields.Selection([('pending', 'Pending'), ('done', 'Done')], default='done')
    hubspot_image_data = fields.Text()



    def process_queue_line_company_data(self):
        if self.company_queue_id:
            queue_id = self.company_queue_id
            hubspot_instance_id = queue_id.hubspot_instance_id
            for line in self:
                self.env['res.partner'].hubspot_queue_company_create(line,hubspot_instance_id)