from odoo import models, fields, api, _
import logging

_logger = logging.getLogger("Contact Queue Line")

class ContactQueueLine(models.Model):
    _name = "contact.queue.line"
    _description = "Hubspot Contact Queue Line"


    name = fields.Char(string="Contact")
    hubspot_instance_id = fields.Many2one("hubspot.instance", string="Instance")
    state = fields.Selection([("draft", "Draft"), ("failed", "Failed"), ("done", "Done"),
                              ("cancel", "Cancelled")],
                             default="draft")
    contact_queue_id = fields.Many2one("contact.queue", required=True,
                                            copy=False)
    processed_last_date = fields.Datetime()
    hubspot_contact_data = fields.Text()
    hubspot_contact_data_id = fields.Char(string="Hubspot Contact Id")
    hubspot_image_import_state = fields.Selection([('pending', 'Pending'), ('done', 'Done')], default='done')
    hubspot_image_data = fields.Text()



    def process_queue_line_contact_data(self):
        if self.contact_queue_id:
            queue_id = self.contact_queue_id
            hubspot_instance_id = queue_id.hubspot_instance_id
            for line in self:
                self.env['res.partner'].hubspot_queue_contact_create(line,hubspot_instance_id)