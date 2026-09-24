import logging
import json
from odoo import fields, models, _
logger = logging.getLogger(__name__)
from odoo.tools import config
config['limit_time_real'] = 10000000


class HubspotDealsFields(models.Model):
    _name = "hubspot.deals.fields"
    _description = "Hubspot Deals Fields"

    name = fields.Char("Label Name", readonly=True)
    field_type = fields.Char("Field Type", readonly=True)
    technical_name = fields.Char("Technical Name", readonly=True)
    options = fields.Char('Hubspot options', readonly=True)
    description = fields.Text("Description", readonly=True)
    hubspot_instance_id = fields.Many2one('hubspot.instance', 'Hubspot Instance Name', help="Hubspot Instance Name", readonly=True, copy=False)
    hubspot_contact_fields = fields.Many2one('hubspot.instance', string='Hubspot fields', readonly=True)
    hubspot_compute = fields.Boolean("Hubspot compute", readonly=True)
    hubspot_readonly = fields.Boolean("Hubspot Readonly", readonly=True)



    def import_deals_fields(self, hubspot_instance):
        response_deals_properties = hubspot_instance._send_get_request('/properties/v1/deals/properties')
        json_response_deals_properties = json.loads(response_deals_properties)
        try:
            for deals_property in json_response_deals_properties:
                self.get_deals_property_details_and_create(deals_property, hubspot_instance)

        except Exception as e:
            error_message = 'Error while getting deals property in odoo \nHubspot response %s' % (str(e))
            self.env['hubspot.logger'].create_log_message('Import Deals property', error_message)
            logger.exception("Error in Getting All property From Hubspot------------>\n" + error_message)
            hubspot_instance._raise_user_error(e)

    def get_deals_property_details_and_create(self, deals_property, hubspot_instance):
        deals_property_dict = {}
        option_list = []
        if 'label' in deals_property:
            deals_property_dict['name'] = deals_property['label']
        if 'name' in deals_property:
            deals_property_dict['technical_name'] = deals_property['name']
        if 'fieldType' in deals_property:
            deals_property_dict['field_type'] = deals_property['fieldType']
        if 'description' in deals_property:
            deals_property_dict['description'] = deals_property['description']
        if 'options' in deals_property:
            for options in deals_property['options']:
                option_list.insert(0,(options['value'], options['label']))
                # option_list.append(options['label'])
            deals_property_dict['options'] = option_list
        if 'calculated' in deals_property:
            if deals_property['calculated']:
                deals_property_dict['hubspot_compute'] = True
            else:
                deals_property_dict['hubspot_compute'] = False


        if 'readOnlyValue' in deals_property:
            if deals_property['readOnlyValue']:
                deals_property_dict['hubspot_readonly'] = True
            else:
                deals_property_dict['hubspot_readonly'] = False

        deals_property_dict['hubspot_instance_id'] = hubspot_instance.id
        hubspot_deals_fields_id = self.env['hubspot.deals.fields'].sudo().search([('technical_name', '=', str(deals_property['name'])),('hubspot_instance_id', '=', hubspot_instance.id)], limit=1)
        if hubspot_deals_fields_id:
            hubspot_deals_fields_id.with_context({'from_hubspot': True}).write(deals_property_dict)
            logger.info("Write into Existing Odoo Hubspot Deals Fields----------- " + str(hubspot_deals_fields_id.name))
        else:
            deals_field_record = self.with_context({'from_hubspot': True}).create(deals_property_dict)
            logger.info("Created New Deals property in Odoo ----------- " + str(deals_field_record.id))








