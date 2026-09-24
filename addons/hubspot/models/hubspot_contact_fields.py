import logging
import json
from odoo import fields, models, _
logger = logging.getLogger(__name__)
from odoo.tools import config
config['limit_time_real'] = 10000000


class HubspotContactFields(models.Model):
    _name = "hubspot.contact.fields"
    _description = "Hubspot contact Fields"

    name = fields.Char("Label Name", readonly=True)
    field_type = fields.Char("Field Type", readonly=True)
    technical_name = fields.Char("Technical Name", readonly=True)
    # hubspot_options = fields.Many2one("hubspot.options.fields", 'Hubspot options')
    options = fields.Char('Hubspot options', readonly=True)


    description = fields.Text("Description", readonly=True)
    hubspot_instance_id = fields.Many2one('hubspot.instance', 'Hubspot Instance Name', help="Hubspot Instance Name", readonly=True, copy=False)
    hubspot_contact_fields = fields.Many2one('hubspot.instance', string='Hubspot fields', readonly=True)
    hubspot_compute = fields.Boolean("Hubspot compute", readonly=True)
    hubspot_readonly = fields.Boolean("Hubspot Readonly", readonly=True)

    def import_contact_fields(self, hubspot_instance):
        response_contact_properties = hubspot_instance._send_get_request('/properties/v1/contacts/properties')
        json_response_contact_properties = json.loads(response_contact_properties)

        try:
            for contact_property in json_response_contact_properties:
                self.get_contact_property_details_and_create(contact_property, hubspot_instance)

        except Exception as e:
            error_message = 'Error while getting contact property in odoo \nHubspot response %s' % (str(e))
            self.env['hubspot.logger'].create_log_message('Import Contact property', error_message)
            logger.exception("Error in Getting All property From Hubspot------------>\n" + error_message)
            hubspot_instance._raise_user_error(e)

    def get_contact_property_details_and_create(self, contact_property, hubspot_instance):
        contact_property_dict = {}
        option_list = []
        if 'label' in contact_property:
            contact_property_dict['name'] = contact_property['label']
        if 'name' in contact_property:
            contact_property_dict['technical_name'] = contact_property['name']
        if 'fieldType' in contact_property:
            contact_property_dict['field_type'] = contact_property['fieldType']
        if 'description' in contact_property:
            contact_property_dict['description'] = contact_property['description']
        if 'options' in contact_property:
            for options in contact_property['options']:
                option_list.insert(0,(options['value'], options['label']))
                # option_list.append(options['label'])
            contact_property_dict['options'] = option_list
        if 'calculated' in contact_property:
            if contact_property['calculated']:
                contact_property_dict['hubspot_compute'] = True
            else:
                contact_property_dict['hubspot_compute'] = False


        if 'readOnlyValue' in contact_property:
            if contact_property['readOnlyValue']:
                contact_property_dict['hubspot_readonly'] = True
            else:
                contact_property_dict['hubspot_readonly'] = False

        contact_property_dict['hubspot_instance_id'] = hubspot_instance.id
        hubspot_contact_fields_id = self.env['hubspot.contact.fields'].sudo().search([('technical_name', '=', str(contact_property['name'])),('hubspot_instance_id', '=', hubspot_instance.id)], limit=1)
        if hubspot_contact_fields_id:
            hubspot_contact_fields_id.with_context({'from_hubspot': True}).write(contact_property_dict)
            logger.info("Write into Existing Odoo Hubspot Contact Fields----------- " + str(hubspot_contact_fields_id.name))
        else:
            contact_field_record = self.with_context({'from_hubspot': True}).create(contact_property_dict)
            logger.info("Created New Contact property in Odoo ----------- " + str(contact_field_record.id))








