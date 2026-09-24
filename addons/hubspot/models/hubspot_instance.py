import time
import logging
import requests
import json
import pytz
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)
current_date = '1970-01-01 02:46:40'
current_timestamp_1 = time.time() * 1e3
current_timestamp = 10000 * 1e3


class HubspotInstance(models.Model):
    _name = "hubspot.instance"
    _description = 'Hubspot Instance'

    default_instance = fields.Boolean('Default Instance', help="Hubspot Default Instance", required=True)
    hubspot_app_key = fields.Char('Hubspot App ID', help="Hubspot Instance API key", required=True)
    name = fields.Char('Hubspot App Name', help="Hubspot Instance API Name", required=True)
    odoo_fields = fields.Many2one('ir.model.fields',
                                  domain=[('model_id.model', '=', 'res.partner'), ('readonly', '!=', True)],
                                  string='Odoo Field')
    hubspot_fields = fields.Many2one('hubspot.company.fields',
                                     domain=[('hubspot_compute', '!=', True), ('hubspot_readonly', '!=', True)],
                                     string='Hubspot Field')
    hubspot_field_description = fields.Text("Description")
    active = fields.Boolean("Active", default=True)
    hubspot_is_import_contacts = fields.Boolean("Import Contacts", default=False)
    hubspot_is_import_company = fields.Boolean("Import Companies", default=False)
    hubspot_is_export_contacts = fields.Boolean("Export Contacts", default=False)
    hubspot_is_export_company = fields.Boolean("Export Companies", default=False)
    deals = fields.Boolean("Deals", default=False)
    hubspot_is_import_deals = fields.Boolean("Import Deals", default=False)
    hubspot_is_export_deals = fields.Boolean("Export Deals", default=False)
    tickets = fields.Boolean("Tickets", default=False)
    modifiedDateForContact = fields.Char('Modified Date for Contact', default=str(current_timestamp))
    modifiedDateForCompany = fields.Char('Modified Date for Company', default=str(current_timestamp))
    modifiedDateForDeals = fields.Char('Modified Date for Deals', default=str(current_timestamp))
    all_contact = fields.Boolean("All Customers")
    all_companies = fields.Boolean("All Companies")
    all_deals = fields.Boolean("All Deals")
    # hubspot_sync_contacts = fields.Boolean("Sync Contacts")
    # hubspot_sync_companies = fields.Boolean("Sync Companies")
    # hubspot_sync_deals = fields.Boolean("Sync Deals")

    # hubspot_sync_task = fields.Boolean("Sync Task")
    hubspot_is_import_task = fields.Boolean("Import Task", default=False)
    hubspot_is_export_task = fields.Boolean("Export Task", default=False)
    modifiedDateForTask = fields.Char('Modified Date for Task', default=str(current_timestamp))
    all_task = fields.Boolean("All Task")

    # hubspot_sync_calls= fields.Boolean("Sync Calls")
    hubspot_is_import_calls = fields.Boolean("Import Calls", default=False)

    modifiedDateForCall = fields.Char('Modified Date for Call', default=str(current_timestamp))
    all_call = fields.Boolean("All Call")

    # hubspot_sync_notes = fields.Boolean("Sync Note")
    hubspot_is_import_notes = fields.Boolean("Import Note", default=False)
    hubspot_is_export_notes = fields.Boolean("Export Note", default=False)
    modifiedDateForNotes = fields.Char('Modified Date for Note', default=str(current_timestamp))
    all_notes = fields.Boolean("All Note")

    # hubspot_sync_email = fields.Boolean("Sync Email")
    hubspot_is_import_email = fields.Boolean("Import Email", default=False)
    hubspot_is_export_email = fields.Boolean("Export Email", default=False)
    modifiedDateForEmail = fields.Char('Modified Date for Email', default=str(current_timestamp))
    all_email = fields.Boolean("All Email")

    # hubspot_sync_log_meeting = fields.Boolean("Sync Log Meeting")
    hubspot_is_import_log_meeting = fields.Boolean("Import Log meeting", default=False)
    hubspot_is_export_log_meeting = fields.Boolean("Export Log meeting", default=False)
    modifiedDateForlogmeeting = fields.Char('Modified Date for Log meeting', default=str(current_timestamp))
    all_log_meeting = fields.Boolean("All Log meeting")

    # hubspot_sync_log_email = fields.Boolean("Sync Log Email")
    hubspot_is_import_log_email = fields.Boolean("Import Log Email", default=False)
    hubspot_is_export_log_email = fields.Boolean("Export Log Email", default=False)
    modifiedDateForLogEmail = fields.Char('Modified Date for Log Email', default=str(current_timestamp))
    all_log_email = fields.Boolean("All Log Email")

    hubspot_sync_associations = fields.Boolean("Sync Associations")
    hubspot_is_import_associations = fields.Boolean("Import Associations", default=False)
    hubspot_is_export_associations = fields.Boolean("Export Associations", default=False)
    modifiedDateForAssociations = fields.Char('Modified Date for Associations', default=str(current_timestamp))
    all_associations = fields.Boolean("All Associations")
    contact_field_mapping = fields.One2many('contact.field.mapping', 'hubspot_instance_id',
                                            string=' Contact Field Mapping')
    company_field_mapping = fields.One2many('company.field.mapping', 'hubspot_instance_id',
                                            string=' Company Field Mapping')
    deals_field_mapping = fields.One2many('deals.field.mapping', 'hubspot_instance_id', string=' Deal Field Mapping')

    # hubspot_sync_products = fields.Boolean("Sync Products")
    hubspot_is_import_products = fields.Boolean("Import Products", default=False)
    hubspot_is_export_products = fields.Boolean("Export Products", default=False)
    modifiedDateForProducts = fields.Char('Modified Date for Products', default=str(current_timestamp))
    all_products = fields.Boolean("All Products")

    # hubspot_sync_quotes = fields.Boolean("Sync Quotes")
    hubspot_is_import_quotes = fields.Boolean("Import Quotes", default=False)
    modifiedDateForQuotes = fields.Char('Modified Date for Quotes', default=str(current_timestamp))
    all_quotes = fields.Boolean("All Quotes")

    # Connection health shown on the instance overview; set by action_test_connection ######
    connection_status = fields.Selection(
        [('not_tested', 'Not Tested'), ('connected', 'Connected'),
         ('invalid', 'Invalid Credentials'), ('failed', 'Connection Failed')],
        string="Connection Status", default='not_tested', readonly=True, copy=False,
    )
    last_connection_check = fields.Datetime("Last Connection Test", readonly=True, copy=False)

    # hubspot_sync_invoices = fields.Boolean("Sync Invoices")
    # hubspot_is_import_invoices = fields.Boolean("Import Invoices", default=False)
    # modifiedDateForInvoices = fields.Char('Modified Date for Invoices', default=str(current_timestamp))
    # all_invoices = fields.Boolean("All Invoices")

    # def _send_get_request(self, method):
    #     get_method_response = requests.get('https://api.hubapi.com' + method, headers={'Authorization': 'Bearer ' + self.hubspot_app_key})
    #     if get_method_response.status_code in [200, 201, 202, 203, 204]:

    #         if get_method_response.text:

    #             return get_method_response.text
    #     else:
    #         if get_method_response.text:
    #             # raise Warning("CONNECTION UNSUCCESSFUL")
    #             # raise UserError(_('111111'))
    #             logger.info("response other than 200=========4: %s", get_method_response.text)

    def _send_get_request(self, method, timeout=60):
        """
        Sends a GET request to the specified HubSpot API v endpoint with retry and rate-limit handling.
        :param method: API method endpoint (e.g., '/deals/v1/deal/paged').
        :param timeout: Timeout for the request in seconds.
        :return: Response object or None if the request failed after retries.
        """
        url = 'https://api.hubapi.com' + method
        headers = {'Authorization': 'Bearer ' + self.hubspot_app_key}

        session = requests.Session()

        # Try to use allowed_methods (urllib3 >= 1.26), fall back to method_whitelist for older versions
        try:
            retry_strategy = Retry(
                total=5,
                backoff_factor=1,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["HEAD", "GET", "OPTIONS"]
            )
        except TypeError:
            retry_strategy = Retry(
                total=5,
                backoff_factor=1,
                status_forcelist=[429, 500, 502, 503, 504],
                method_whitelist=["HEAD", "GET", "OPTIONS"]
            )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        while True:
            try:
                response = session.get(url, headers=headers, timeout=timeout)

                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 10))
                    logging.warning(f"Rate limit hit. Retrying after {retry_after} seconds...")
                    time.sleep(retry_after)
                    continue

                remaining = response.headers.get("X-HubSpot-RateLimit-Remaining")
                interval = response.headers.get("X-HubSpot-RateLimit-Interval-Milliseconds")

                if remaining is not None and interval is not None:
                    remaining = int(remaining)
                    interval = int(interval)

                    if remaining == 0:
                        wait_time = interval / 1000
                        logging.warning(f"Approaching rate limit. Waiting for {wait_time} seconds.")
                        time.sleep(wait_time)
                        continue

                if response.status_code == 401:
                    logging.error("Unauthorized! Please check your HubSpot API key.")
                    return None

                response.raise_for_status()
                return response.text

            except requests.exceptions.RequestException as e:
                logging.error(f"Request to {url} failed: {e}")
                return None

    def _send_post_request(self, method, properties):
        post_method_response = requests.post('https://api.hubapi.com' + method, json.dumps(properties),
                                             headers={'Authorization': 'Bearer ' + self.hubspot_app_key,
                                                      'Content-Type': 'application/json'})
        if post_method_response.status_code in [200, 201, 202, 203, 204]:
            if post_method_response.text:
                return post_method_response.text
        else:
            if post_method_response.text:
                raise UserError(_('%s', post_method_response.text))

    def _send_delete_request(self, method):
        delete_method_response = requests.delete('https://api.hubapi.com' + method,
                                                 headers={'Authorization': 'Bearer ' + self.hubspot_app_key})
        if delete_method_response.status_code in [200, 201, 202, 203, 204]:
            if delete_method_response.text:
                return delete_method_response.text
        else:
            if delete_method_response.text:
                raise UserError(_('%s', delete_method_response.text))

    def _send_put_request(self, method, properties):
        put_method_response = requests.put('https://api.hubapi.com' + method, json.dumps(properties),
                                           headers={'Authorization': 'Bearer ' + self.hubspot_app_key,
                                                    'Content-Type': 'application/json'})
        if put_method_response.status_code in [200, 201, 202, 203, 204]:
            if put_method_response.text:
                return put_method_response.text
        else:
            if put_method_response.text:
                raise UserError(_('%s', put_method_response.text))

    def _send_patch_request(self, method, properties):
        patch_method_response = requests.patch('https://api.hubapi.com' + method, json.dumps(properties),
                                               headers={'Authorization': 'Bearer ' + self.hubspot_app_key,
                                                        'Content-Type': 'application/json'})
        if patch_method_response.status_code in [200, 201, 202, 203, 204]:
            if patch_method_response.text:
                return patch_method_response.text
        else:
            if patch_method_response.text:
                raise UserError(_('%s', patch_method_response.text))

    def _raise_user_error(self, exception):
        if self.env.context.get('params') and self.env.context.get('params').get('model'):
            exception = json.loads(str(exception))
            if exception.get('message'):
                raise UserError(_('%s', str(exception.get('message'))))

    def action_import_contact_fields(self):
        return self.env['hubspot.contact.fields'].import_contact_fields(self)

    def action_import_company_fields(self):
        return self.env['hubspot.company.fields'].import_company_fields(self)

    def action_import_deals_fields(self):
        return self.env['hubspot.deals.fields'].import_deals_fields(self)

    def action_import_hubspot_stages(self):
        stage_model = self.env['crm.stage']
        return stage_model.import_hubspot_stages()

    def action_import_products(self):
        return self.env['product.template'].import_products_from_hubspot(self)

    def action_export_products(self):
        return self.env['product.template'].export_products_to_hubspot(self)

    def action_import_quotes(self):
        return self.env['sale.order'].import_quotes_from_hubspot(self)

    # def action_import_invoices(self):
    #     return self.env['account.move'].import_invoices_from_hubspot(self)

    # @api.onchange('hubspot_sync_contacts')
    # def _onchange_hubspot_sync_contacts(self):
    #     if not self.hubspot_sync_contacts:
    #         self.hubspot_is_import_contacts = False
    #         self.hubspot_is_export_contacts = False

    @api.onchange('hubspot_is_import_contacts')
    def _onchange_hubspot_sync_contacts(self):
        if not self.hubspot_is_import_contacts:
            self.hubspot_is_import_contacts = False
            self.hubspot_is_export_contacts = False

    # @api.onchange('hubspot_sync_companies')
    # def _onchange_hubspot_sync_companies(self):
    #     if not self.hubspot_sync_companies:
    #         self.hubspot_is_import_company = False
    #         self.hubspot_is_export_company = False

    @api.onchange('hubspot_is_import_company')
    def _onchange_hubspot_sync_companies(self):
        if not self.hubspot_is_import_company:
            self.hubspot_is_import_company = False
            self.hubspot_is_export_company = False

    # @api.onchange('hubspot_sync_deals')
    # def _onchange_hubspot_sync_deals(self):
    #     if self.hubspot_sync_deals == False:
    #         self.hubspot_is_import_deals = False
    #         self.hubspot_is_export_deals = False

    @api.onchange('hubspot_is_import_deals')
    def _onchange_hubspot_sync_deals(self):
        if self.hubspot_is_import_deals == False:
            self.hubspot_is_import_deals = False
            self.hubspot_is_export_deals = False

    # @api.onchange('hubspot_sync_task')
    # def _onchange_hubspot_sync_task(self):
    #     if not self.hubspot_sync_task:
    #         self.hubspot_is_import_task = False
    #         self.hubspot_is_export_task = False

    @api.onchange('hubspot_is_import_task')
    def _onchange_hubspot_sync_task(self):
        if not self.hubspot_is_import_task:
            self.hubspot_is_import_task = False
            self.hubspot_is_export_task = False

    # @api.onchange('hubspot_sync_notes')
    # def _onchange_hubspot_sync_notes(self):
    #     if self.hubspot_sync_notes == False:
    #         self.hubspot_is_import_notes = False
    #         self.hubspot_is_export_notes = False

    @api.onchange('hubspot_is_import_notes')
    def _onchange_hubspot_sync_notes(self):
        if self.hubspot_is_import_notes == False:
            self.hubspot_is_import_notes = False
            self.hubspot_is_export_notes = False

    # @api.onchange('hubspot_sync_calls')
    # def _onchange_hubspot_sync_calls(self):
    #     if self.hubspot_sync_calls == False:
    #         self.hubspot_is_import_calls= False

    @api.onchange('hubspot_is_import_calls')
    def _onchange_hubspot_sync_calls(self):
        if self.hubspot_is_import_calls == False:
            self.hubspot_is_import_calls = False

    # @api.onchange('hubspot_sync_email')
    # def _onchange_hubspot_sync_email(self):
    #     if self.hubspot_sync_email == False:
    #         self.hubspot_is_import_email = False
    #         self.hubspot_is_export_email = False

    @api.onchange('hubspot_is_import_email')
    def _onchange_hubspot_sync_email(self):
        if self.hubspot_is_import_email == False:
            self.hubspot_is_import_email = False
            self.hubspot_is_export_email = False

    # @api.onchange('hubspot_sync_log_meeting')
    # def _onchange_hubspot_sync_log_meeting(self):
    #     if self.hubspot_sync_log_meeting == False:
    #         self.hubspot_is_import_log_meeting = False
    #         self.hubspot_is_export_log_meeting = False

    @api.onchange('hubspot_is_import_log_meeting')
    def _onchange_hubspot_sync_log_meeting(self):
        if self.hubspot_is_import_log_meeting == False:
            self.hubspot_is_import_log_meeting = False
            self.hubspot_is_export_log_meeting = False

    # @api.onchange('hubspot_sync_log_email')
    # def _onchange_hubspot_sync_log_email(self):
    #     if self.hubspot_sync_log_email == False:
    #         self.hubspot_is_import_log_email = False
    #         self.hubspot_is_export_log_email = False

    @api.onchange('hubspot_is_import_log_email')
    def _onchange_hubspot_sync_log_email(self):
        if self.hubspot_is_import_log_email == False:
            self.hubspot_is_import_log_email = False
            self.hubspot_is_export_log_email = False

    # @api.onchange('hubspot_sync_products')
    # def _onchange_hubspot_sync_products(self):
    #     if self.hubspot_sync_products == False:
    #         self.hubspot_is_import_products = False
    #         self.hubspot_is_export_products = False

    @api.onchange('hubspot_is_import_products')
    def _onchange_hubspot_sync_products(self):
        if self.hubspot_is_import_products == False:
            self.hubspot_is_import_products = False
            self.hubspot_is_export_products = False

    # @api.onchange('hubspot_sync_quotes')
    # def _onchange_hubspot_sync_quotes(self):
    #     if self.hubspot_sync_quotes == False:
    #         self.hubspot_is_import_quotes = False

    @api.onchange('hubspot_is_import_quotes')
    def _onchange_hubspot_sync_quotes(self):
        if self.hubspot_is_import_quotes == False:
            self.hubspot_is_import_quotes = False

    # @api.onchange('hubspot_sync_invoices')
    # def _onchange_hubspot_sync_invoices(self):
    #     if self.hubspot_sync_invoices == False:
    #         self.hubspot_is_import_invoices = False

    @api.model_create_multi
    def create(self, vals_list):
        hubspot_instance = self.env['hubspot.instance'].search([('active', '=', True)])

        for vals in vals_list:
            if vals.get('default_instance'):
                for hubspot_instance_id in hubspot_instance:
                    if hubspot_instance_id.default_instance:
                        raise UserError(_('You already added default instance to another instance'))

        res = super(HubspotInstance, self).create(vals_list)
        return res

    def write(self, vals):
        if 'default_instance' in vals:
            hubspot_instance = self.env['hubspot.instance'].search([])
            for hubspot_instance_id in hubspot_instance:
                if not vals['default_instance']:
                    vals['default_instance'] = False
                elif hubspot_instance_id.default_instance == True:
                    raise UserError(_('You already added default instance to another instance'))
        return super(HubspotInstance, self).write(vals)

    def _set_connection_status(self, status, persist_now=False):
        # persist_now: save on a separate cursor so the status survives the UserError rollback ######
        vals = {'connection_status': status, 'last_connection_check': fields.Datetime.now()}
        if not persist_now:
            self.write(vals)
            return
        with self.env.registry.cursor() as new_cr:
            self.with_env(self.env(cr=new_cr)).write(vals)

    def action_test_connection(self):
        logger.info("In action_test_connection")
        try:
            response = requests.request('GET', 'https://api.hubapi.com/crm/v3/owners',
                                        headers={'Authorization': 'Bearer ' + self.hubspot_app_key},
                                        timeout=30)
        except requests.exceptions.RequestException as e_conn:
            # Network error / timeout: record it, then keep the original error behaviour ######
            logger.warning("HubSpot connection test failed: %s", e_conn)
            self._set_connection_status('failed', persist_now=True)
            raise UserError("CONNECTION UNSUCCESSFUL")
        if response.status_code == 200:
            self._set_connection_status('connected')
            return self.sendMessage("CONNECTION SUCCESSFUL")
        elif response.status_code == 401:
            self._set_connection_status('invalid')
            return self.sendMessage("Invalid Credentials")
        else:
            self._set_connection_status('failed', persist_now=True)
            raise UserError("CONNECTION UNSUCCESSFUL")

    def sendMessage(self, message):
        # view_ref = self.env['ir.model.data'].get_object_reference('hubspot', 'hubspot_message_wizard_form')
        view_ref = self.env['ir.model.data']._xmlid_to_res_id('hubspot.hubspot_message_wizard_form')
        # view_id = view_ref and view_ref[1] or False,
        # if view_id:
        return {
            'type': 'ir.actions.act_window',
            'name': 'Message',
            'res_model': 'hubspot.message.wizard',
            'view_mode': 'form',
            'view_id': view_ref,
            'context': {'message': message},
            'target': 'new',

        }

    def action_import_contacts(self):
        return self.env['contact.queue'].import_contacts_from_hubspot(self)

    def action_update_contacts(self):
        return self.env['res.partner'].update_existing_contacts_from_hubspot(self)

    def action_import_skip_contacts(self):
        return self.env['res.partner'].import_skip_contacts_from_hubspot(self)

    def action_import_companies(self):
        return self.env['company.queue'].import_company_from_hubspot(self)

    def action_update_companies(self):
        return self.env['res.partner'].update_existing_companies_from_hubspot(self)

    def action_export_contacts(self):
        return self.env['res.partner'].export_contacts_to_hubspot(self)

    def action_import_skip_companies(self):
        return self.env['res.partner'].action_import_skip_companies(self)

    def action_export_companies(self):
        return self.env['res.partner'].export_companies_to_hubspot(self)

    # def action_import_deals(self):
    #     return self.env['deal.queue'].import_deals_from_hubspot(self)

    def action_import_deals(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Import Deals'),
            'res_model': 'hubspot.deal.import.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_hubspot_instance_id': self.id
            }
        }

    def action_import_skip_deals(self):
        return self.env['crm.lead'].import_skip_deals_from_hubspot(self)

    def action_export_deals(self):
        return self.env['crm.lead'].export_deals_to_hubspot(self)

    def action_import_task(self):
        return self.env['mail.activity'].import_task_from_hubspot(self)

    def action_export_task(self):
        return self.env['mail.activity'].export_task_to_hubspot(self)

    def action_import_notes(self):
        return self.env['mail.message'].import_note_from_hubspot(self)

    def action_export_notes(self):
        return self.env['mail.message'].export_note_to_hubspot(self)

    def action_import_skip_notes(self):
        return self.env['mail.message'].action_import_skip_notes(self)

    def action_import_email(self):
        return self.env['mail.message'].import_email_from_hubspot(self)

    def action_export_email(self):
        return self.env['mail.message'].export_email_to_hubspot(self)

    def action_import_log_meeting(self):
        return self.env['calendar.event'].import_log_meeting_from_hubspot(self)

    def action_export_log_meeting(self):
        return self.env['calendar.event'].export_log_meeting_to_hubspot(self)

    def action_import_log_email(self):
        return self.env['mail.activity'].import_log_email_from_hubspot(self)

    def action_export_log_email(self):
        return self.env['mail.activity'].export_log_email_to_hubspot(self)

    def action_import_call(self):
        return self.env['mail.activity'].import_call_from_hubspot(self)

    def action_active_inactive(self):
        # status_field = self.active
        if self.active == True:
            self.active = False
        elif self.active == False:
            self.active = True
        return self.active

    def action_open_logger_dashboard(self):
        # Button target resolved at runtime: the logger view file loads after this form ######
        return self.env['ir.actions.actions']._for_xml_id('hubspot.hubspot_logger_dashboard_action')

    # ------------------------------------------------------------------ ######
    # Instance overview API used by the form widgets (caller's access rights) ######
    # ------------------------------------------------------------------ ######

    def _overview_log_domain(self):
        # Logs linked to this instance; unlinked logs count too when only one instance exists ######
        self.ensure_one()
        if self.with_context(active_test=False).search_count([]) <= 1:
            return ['|', ('hubspot_instance_id', '=', self.id), ('hubspot_instance_id', '=', False)]
        return [('hubspot_instance_id', '=', self.id)]

    def _overview_company_partner_ids(self):
        # Odoo 20 derives is_company from the VAT, so HubSpot companies without a VAT look like contacts ######
        # Also count partners created by the company import (queue lines) or logged as company syncs ######
        self.ensure_one()
        hubspot_company_ids = set()
        if self.env['company.queue.line'].has_access('read'):
            hubspot_company_ids = {
                str(value) for value in self.env['company.queue.line'].search(
                    [('hubspot_instance_id', '=', self.id), ('hubspot_company_data_id', '!=', False)]
                ).mapped('hubspot_company_data_id')
            }
        logged_ids = {
            res_id for res_id in self.env['hubspot.logger'].search(self._overview_log_domain() + [
                ('res_model', '=', 'res.partner'), ('record_action', '!=', False),
                ('operation_label', 'ilike', 'compan'),
            ]).mapped('res_id') if res_id
        }
        domain = [('hubspot_instance_id', '=', self.id), ('hubspot_id', '!=', False),
                  '|', '|', ('is_company', '=', True),
                  ('hubspot_id', 'in', list(hubspot_company_ids)),
                  ('id', 'in', list(logged_ids))]
        return self.env['res.partner'].search(domain).ids

    def _overview_kpi_specs(self):
        # (key, label, model, domain, log keywords) for the four KPI cards ######
        self.ensure_one()
        base = [('hubspot_instance_id', '=', self.id), ('hubspot_id', '!=', False)]
        company_ids = self._overview_company_partner_ids() if self.env['res.partner'].has_access('read') else []
        return [
            ('contacts', _('Contacts'), 'res.partner', base + [('id', 'not in', company_ids)], ['contact']),
            ('companies', _('Companies'), 'res.partner', [('id', 'in', company_ids)], ['compan']),
            # Deal import creates leads or opportunities (wizard choice), so count both ######
            ('deals', _('Deals / Leads'), 'crm.lead', base, ['deal', 'lead']),
            # Product import stores the HubSpot id in hubspot_product_id ######
            ('products', _('Products'), 'product.template',
             [('hubspot_instance_id', '=', self.id),
              '|', ('hubspot_id', '!=', False), ('hubspot_product_id', '!=', False)], ['product']),
        ]

    @api.model
    def _overview_keyword_domain(self, keywords):
        # OR of operation_label ilike keyword ######
        if not keywords:
            return []
        return ['|'] * (len(keywords) - 1) + [('operation_label', 'ilike', keyword) for keyword in keywords]

    @api.model
    def _overview_entity_keywords(self, entity):
        keywords = {
            'contacts': ['contact'],
            'companies': ['compan'],
            'deals': ['deal', 'lead'],
            'products': ['product'],
            'quotes': ['quote'],
            'engagements': ['note', 'email', 'meeting', 'task', 'call', 'activit'],
        }
        return keywords.get(entity, [])

    def get_instance_overview(self, entity='all', limit=6):
        """KPI cards and recent sync activity (with synced record details) for this instance. ######"""
        self.ensure_one()
        limit = min(max(int(limit or 6), 1), 50)
        logger_model = self.env['hubspot.logger']
        log_domain = self._overview_log_domain()
        tz_now = fields.Datetime.context_timestamp(self, fields.Datetime.now())
        today_start = fields.Datetime.to_datetime(
            tz_now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(pytz.utc).replace(tzinfo=None)
        )
        kpis = []
        for key, label, model_name, domain, keywords in self._overview_kpi_specs():
            model = self.env[model_name]
            allowed = model.has_access('read')
            kpis.append({
                'key': key,
                'label': label,
                'model': model_name,
                'domain': domain,
                'count': model.search_count(domain) if allowed else False,
                'synced_today': logger_model.search_count(log_domain + [
                    ('log_type', '=', 'record'),
                    ('hubspot_datetime', '>=', today_start),
                ] + self._overview_keyword_domain(keywords)),
            })
        activity_domain = list(log_domain)
        keywords = self._overview_entity_keywords(entity)
        activity_domain += self._overview_keyword_domain(keywords)
        activity = logger_model.search_read(
            activity_domain,
            ['hubspot_datetime', 'status', 'operation_label', 'hubspot_description', 'log_type',
             'record_name', 'record_action', 'res_model', 'res_id', 'hubspot_record_id'],
            limit=limit, order='hubspot_datetime desc, id desc',
        )
        return {
            'kpis': kpis,
            'activity': activity,
            'activity_domain': activity_domain,
            # Counts follow the same entity filter as the activity list ######
            'success_count': logger_model.search_count(activity_domain + [('status', '=', 'success')]),
            'failed_count': logger_model.search_count(activity_domain + [('status', '=', 'failed')]),
        }
