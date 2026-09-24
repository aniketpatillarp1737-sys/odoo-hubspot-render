from odoo import api, fields, models


class hubspot_response_message_wizard(models.TransientModel):
    _name = 'hubspot.message.wizard'
    _description = "Show response message on wizard"

    def _get_sf_message(self):
        return self.env.context.get('message')

    message = fields.Text("Response", default=_get_sf_message, readonly=True)
