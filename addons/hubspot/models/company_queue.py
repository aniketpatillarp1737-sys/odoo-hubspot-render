from odoo import models, fields, api, _
import logging
import json
import time


_logger = logging.getLogger("Hubspot Queue")
logger = logging.getLogger(__name__)


class CompanyQueue(models.Model):
    _name = "company.queue"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Hubspot Company Queue"

    name = fields.Char()
    hubspot_instance_id = fields.Many2one("hubspot.instance", string="Instance")
    company_queue_lines_ids = fields.One2many("company.queue.line",
                                               "company_queue_id",
                                               string="Product Queue Lines")
    state = fields.Selection([("processing", "Processing"),("draft", "Draft"), ("partially_completed", "Partially Completed"),
                              ("completed", "Completed"), ("failed", "Failed")], default="draft",
                              store=True, tracking=True,compute="compute_status")
    queue_status = fields.Char(default="Running")
    queue_created_by = fields.Selection([("import", "By Import Process"), ("webhook", "By Webhook")],default="import")
    is_queue_processing = fields.Boolean("Is Queue Processing", default=False)
    total_records_in_queue_line = fields.Integer(string="Total Records",compute="_compute_status_queue_line")
    draft_records_in_queue_line = fields.Integer(string="Draft Records",compute="_compute_status_queue_line")
    fail_records_in_queue_line = fields.Integer(string="Fail Records",compute="_compute_status_queue_line")
    done_records_in_queue_line = fields.Integer(string="Done Records",compute="_compute_status_queue_line")
    cancel_records_in_queue_line = fields.Integer(string="Cancelled Records",compute="_compute_status_queue_line")
    is_any_action_require = fields.Boolean(default=False)
    time_proccessed_by_queue = fields.Integer(string="Queue Process Times")
    offset = fields.Text(string='Last Offset', help='Last processed offset from HubSpot')
    has_more = fields.Boolean("Has More",default=False)



    @api.depends("company_queue_lines_ids.state")
    def _compute_status_queue_line(self):
      
        for queue in self:
            lines = queue.company_queue_lines_ids
            queue.total_records_in_queue_line = len(lines)
            queue.draft_records_in_queue_line = len(lines.filtered(lambda x: x.state == "draft"))
            queue.fail_records_in_queue_line = len(lines.filtered(lambda x: x.state == "failed"))
            queue.done_records_in_queue_line = len(lines.filtered(lambda x: x.state == "done"))
            queue.cancel_records_in_queue_line = len(lines.filtered(lambda x: x.state == "cancel"))
    

    @api.depends("company_queue_lines_ids.state")
    def compute_status(self):
        for record in self:
            if record.total_records_in_queue_line == 0:
                record.state = 'processing'
            elif record.total_records_in_queue_line == record.done_records_in_queue_line + record.cancel_records_in_queue_line:
                record.state = "completed"
            elif record.draft_records_in_queue_line == record.total_records_in_queue_line:
                record.state = "draft"
            elif record.total_records_in_queue_line == record.fail_records_in_queue_line:
                record.state = "failed"
            else:
                record.state = "partially_completed"


    @api.model_create_multi
    def create(self, vals):
        for val in vals:
            val['name'] = self.env["ir.sequence"].sudo().next_by_code('company.queue')
        return super().create(vals)

    @api.model
    def _cron_import_companies_from_hubspot(self):
        hubspot_instance_obj = self.env['hubspot.instance'].search([('active', '=', True), ('hubspot_is_import_company', '=', True)])
        for hubspot_instance in hubspot_instance_obj:
            self.import_company_from_hubspot(hubspot_instance)
    
    def import_company_from_hubspot(self,hubspot_instance):
        """This function is called from cron to import companies from hubspot"""
        # Hubspot Information
        modifiedDateForCompany = float(hubspot_instance.modifiedDateForCompany or 0)
        all_company = hubspot_instance.all_companies
        if hubspot_instance.active   and hubspot_instance.hubspot_is_import_company: 
            
            try:
                has_more = True
                last_processing_company = self.env['company.queue'].search([('state', '!=', 'processing')], order='create_date desc', limit=1)

                if last_processing_company:
                    if last_processing_company.has_more:                       
                        offset = last_processing_company.offset
                        logger.info(f'Continuing from last offset: {offset}')
                    else:
                        offset = 0 
                else:
                    logger.info('No processing queues found; starting from offset 0.')
                    offset = 0 # Adjust this according to your rate limit
                while has_more:
                    company_ids = []
                    record_limit = 100
                    # properties = 'hs_lastmodifieddate'
                    response_get_all_companies = hubspot_instance._send_get_request(
                        '/companies/v2/companies/paged?offset=' + str(offset) + '&limit=' + str(record_limit))
                    json_response_all_companys = json.loads(response_get_all_companies)
                    has_more = json_response_all_companys.get('has-more')
                    offset = json_response_all_companys['offset']
                    self.create_company_queues(hubspot_instance, json_response_all_companys,offset,has_more)
            except Exception as e:
                error_message = 'Error while getting companies in odoo \nHubspot response %s' % (str(e))
                logger.info("In import companies exception: %s" % error_message)
                self.env['hubspot.logger'].create_log_message('Import Companies', error_message)
                logger.exception("Error in Getting All Companies From Hubspot------------>\n" + error_message)
                hubspot_instance._raise_user_error(e)


    

    def create_company_queues(self, hubspot_instance, results, offset, has_more):
        """Creates a company queue and processes companies from the response."""

        last_queue = self.env['company.queue'].search(
            [('state', '!=', 'processing')], 
            order='create_date desc', 
            limit=1
        )

        if last_queue and last_queue.total_records_in_queue_line < 100:
            company_queue = last_queue
        else:
            company_queue = self.company_create_queue(hubspot_instance, offset, has_more)

        
        incoming_ids = [
            str(result.get('companyId')) 
            for result in results.get('companies', []) 
            if result.get('companyId')
        ]

        existing_companies = set(
            str(cid) for cid in self.env['company.queue.line'].search([
                ('hubspot_company_data_id', 'in', incoming_ids)
            ]).mapped('hubspot_company_data_id')
        )

        new_companies = [
            result for result in results.get('companies', []) 
            if str(result.get('companyId')) not in existing_companies
        ]

        if not new_companies:
            logger.info("No new companies found. Skipping queue addition.")
            return False

        for result in new_companies:
            company_id = result["companyId"]
            response_get_company_by_id = hubspot_instance._send_get_request(
                f"/companies/v2/companies/{company_id}"
            )
            if not response_get_company_by_id:
                logger.error(f"Failed to retrieve details for company ID {company_id} after retries. Skipping this company.")
                continue
            try:
                company_profile = json.loads(response_get_company_by_id)
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing JSON for Company ID {company_id}: {e}")
                continue

            self.hubspot_create_company_queue_line(company_profile, hubspot_instance, company_queue)

        return True


    # def create_company_queues(self,hubspot_instance, results,offset,has_more):
    #     company_queue_list = []
    #     company_queue = self.company_create_queue(hubspot_instance,offset,has_more)
    #     company_queue_list.append(company_queue.id)
    #     message = "Company Queue Created", company_queue.name
    #     self._cr.commit()
    #     _logger.info(message)
    #     for result in results['companies']:
    #         if result['companyId']:
    #             company_id = result['companyId']
    #             response_get_contact_by_id = hubspot_instance._send_get_request('/companies/v2/companies/' + str(company_id))
    #             company_profile = json.loads(response_get_contact_by_id)
    #             self.hubspot_create_company_queue_line(company_profile, hubspot_instance, company_queue)
    #     self._cr.commit()

    def company_create_queue(self,hubspot_instance,offset,has_more,created_by="import"):
        company_queue_vals = {
            "hubspot_instance_id": hubspot_instance and hubspot_instance.id or False,
            "queue_created_by": created_by,
            "offset":offset,
            "has_more":has_more
        }
        return self.create(company_queue_vals)


    def hubspot_create_company_queue_line(self,result, hubspot_instance, company_queue):
        company_data_queue_line_obj = self.env["company.queue.line"]
        data = json.dumps(result)
        companyName = ''
        image_import_state ='pending'
        image_data =''
        if 'name' in result['properties']:
            if len(result['properties']['name']['value']) > 0:
                companyName = result['properties']['name']['value']
            else:
                companyName = 'Unknown'
        
        if result['companyId']:
            hubspot_company_id = result['companyId']
            try:

                response_get_associated_company_attachment_detail = hubspot_instance._send_get_request(
                                                        f'/engagements/v1/engagements/associated/company/{hubspot_company_id}/paged')
                                                                                                       
                img_json = json.loads(response_get_associated_company_attachment_detail).get('results', [])
                img_list = []
                for res in img_json:
                    attachments = res.get('attachments', [])
                    for attachment in attachments:
                        if attachment.get('id'):
                            attachment_id = attachment.get('id')
                            if attachment_id:
                                response_attachment_details = hubspot_instance._send_get_request('/files/v3/files/' + str(attachment_id) + '/signed-url')
                                attachment_details = json.loads(response_attachment_details)
                                if attachment_details:
                                    img_list.append(attachment_details)

                img = img_list
                if img:
                    image_import_state = 'done'
                    image_data = json.dumps(img)
            except json.JSONDecodeError:
                logger.error("Failed to parse JSON response for hubspot_company_id: %s", hubspot_company_id)
            except Exception as e:
                logger.error("An unexpected error occurred: %s", str(e))
                self.env.cr.commit()

        company_queue_line_vals = {"hubspot_company_data_id": hubspot_company_id,
                                   "hubspot_instance_id": hubspot_instance and hubspot_instance.id or False,
                                   "name": companyName,
                                   "hubspot_company_data": data,
                                   "company_queue_id": company_queue and company_queue.id or False,
                                   "hubspot_image_import_state": image_import_state,
                                   "hubspot_image_data":image_data
                                   }
        company_data_queue_line_obj.create(company_queue_line_vals)
        return True
    

    def queue_manual_company_process(self):
        if self:
            queue_id = self
        else:
            queue_id = self.env['company.queue'].search([("state", "!=", 'completed')])
        if queue_id:
            for queue in queue_id:
                company_queue_line = self.env['company.queue.line'].search(
                    [("company_queue_id", "=", queue.id),
                    ("state", "in", ('draft', 'failed'))])
                for lines in company_queue_line:
                    lines.process_queue_line_company_data()
            return True
