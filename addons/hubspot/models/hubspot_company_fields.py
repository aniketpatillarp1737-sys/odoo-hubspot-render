import logging
import json
from odoo import fields, models, _
logger = logging.getLogger(__name__)
from odoo.tools import config
config['limit_time_real'] = 10000000


class HubspotCompanyFields(models.Model):
    _name = "hubspot.company.fields"
    _description = "Hubspot Company Fields"

    name = fields.Char("Label Name", readonly=True)
    field_type = fields.Char("Field Type", readonly=True)
    technical_name = fields.Char("Technical Name", readonly=True)
    options = fields.Char('Hubspot options', readonly=True)
    description = fields.Text("Description", readonly=True)
    hubspot_instance_id = fields.Many2one('hubspot.instance', 'Hubspot Instance Name', help="Hubspot Instance Name", readonly=True, copy=False)
    hubspot_company_fields = fields.Many2one('hubspot.instance', string='Hubspot fields', readonly=True)
    hubspot_compute = fields.Boolean("Hubspot compute", readonly=True)
    hubspot_readonly = fields.Boolean("Hubspot Readonly", readonly=True)

    def import_company_fields(self, hubspot_instance):
        hubspot_app_key = hubspot_instance.hubspot_app_key
        hubspot_app_name = hubspot_instance.name
        contact_property_dict = {}
        response_company_properties = hubspot_instance._send_get_request('/properties/v1/companies/properties/')
        json_response_company_properties = json.loads(response_company_properties)
        try:
            for company_property in json_response_company_properties:
                self.get_company_property_details_and_create(company_property, hubspot_instance)
        except Exception as e:
            error_message = 'Error while getting company property in odoo \nHubspot response %s' % (str(e))
            self.env['hubspot.logger'].create_log_message('Import Company property', error_message)
            logger.exception("Error in Getting All property From Hubspot------------>\n" + error_message)
            hubspot_instance._raise_user_error(e)

    def get_company_property_details_and_create(self, company_property, hubspot_instance):
        company_property_dict = {}
        option_list = []
        if 'label' in company_property:
            company_property_dict['name'] = company_property['label']
        if 'name' in company_property:
            company_property_dict['technical_name'] = company_property['name']
        if 'fieldType' in company_property:
            company_property_dict['field_type'] = company_property['fieldType']
        if 'description' in company_property:
            company_property_dict['description'] = company_property['description']
        if 'options' in company_property:
            for options in company_property['options']:
                option_list.insert(0,(options['value'], options['label']))
                # option_list.append(options['label'])
            company_property_dict['options'] = option_list
        if 'calculated' in company_property:
            if company_property['calculated']:
                company_property_dict['hubspot_compute'] = True
            else:
                company_property_dict['hubspot_compute'] = False


        if 'readOnlyValue' in company_property:
            if company_property['readOnlyValue']:
                company_property_dict['hubspot_readonly'] = True
            else:
                company_property_dict['hubspot_readonly'] = False
        company_property_dict['hubspot_instance_id'] = hubspot_instance.id
        hubspot_company_fields_id = self.env['hubspot.company.fields'].sudo().search([('technical_name', '=', str(company_property['name'])),('hubspot_instance_id', '=', hubspot_instance.id)], limit=1)
        if hubspot_company_fields_id:
            hubspot_company_fields_id.with_context({'from_hubspot': True}).write(company_property_dict)
            logger.info("Write into Existing Odoo Hubspot Company Fields----------- " + str(hubspot_company_fields_id.name))
        else:
            company_field_record = self.with_context({'from_hubspot': True}).create(company_property_dict)
            logger.info("Created New Company property in Odoo ----------- " + str(company_field_record.id))








