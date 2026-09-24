from odoo import models, fields, api, _
import logging
import json
import time


_logger = logging.getLogger("Hubspot Queue")
logger = logging.getLogger(__name__)


class ContactQueue(models.Model):
    _name = "contact.queue"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Hubspot Contact Queue"

    name = fields.Char()
    hubspot_instance_id = fields.Many2one("hubspot.instance", string="Instance")
    contact_queue_lines_ids = fields.One2many("contact.queue.line",
                                               "contact_queue_id",
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



    @api.depends("contact_queue_lines_ids.state")
    def _compute_status_queue_line(self):
      
        for queue in self:
            lines = queue.contact_queue_lines_ids
            queue.total_records_in_queue_line = len(lines)
            queue.draft_records_in_queue_line = len(lines.filtered(lambda x: x.state == "draft"))
            queue.fail_records_in_queue_line = len(lines.filtered(lambda x: x.state == "failed"))
            queue.done_records_in_queue_line = len(lines.filtered(lambda x: x.state == "done"))
            queue.cancel_records_in_queue_line = len(lines.filtered(lambda x: x.state == "cancel"))
    

    @api.depends("contact_queue_lines_ids.state")
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
            val['name'] = self.env["ir.sequence"].sudo().next_by_code('contact.queue')
        return super().create(vals)

    @api.model
    def _cron_import_contacts_from_hubspot(self):
        hubspot_instance_obj = self.env['hubspot.instance'].search([('active', '=', True), ('hubspot_is_import_contacts', '=', True)])
        for hubspot_instance in hubspot_instance_obj:
            self.import_contacts_from_hubspot(hubspot_instance)
    
    def import_contacts_from_hubspot(self,hubspot_instance):
        """This function is called from cron to import contacts from hubspot"""
        modifiedDateForContact = hubspot_instance.modifiedDateForContact or ''
        # all_contact = hubspot_instance.all_contact or 0

         
        if hubspot_instance.active  and hubspot_instance.hubspot_is_import_contacts: 
            logger.info('Getting All contacts from hubspot---------------------------')
            try:
                has_more = True
                last_processing_contact = self.env['contact.queue'].search([
                    ('state', '!=', 'processing')], order='create_date desc', limit=1)

                if last_processing_contact:
                    if last_processing_contact.has_more:                       
                        vid_offset = last_processing_contact.offset
                        logger.info(f'Continuing from last offset: {vid_offset}')
                    else:
                        vid_offset = 0 
                else:
                    logger.info('No processing queues found; starting from offset 0.')
                    vid_offset = 0 # Adjust this according to your rate limit

                while has_more:
                    
                    contact_ids = []
                    record_limit = 100
                    # if request_count >= max_requests_per_10_seconds:
                    #     logger.info('Rate limit reached, sleeping for 10 seconds...')
                    #     time.sleep(10)  # Sleep for 10 seconds before making more requests
                    #     request_count = 0
                    response_all_contacts = hubspot_instance._send_get_request(
                        '/contacts/v1/lists/all/contacts/all?vidOffset=' + str(vid_offset) + '&count=' + str(record_limit))
                    # request_count += 1  # Increment request count after each API call
                    json_response_all_contacts = json.loads(response_all_contacts)
                    has_more = json_response_all_contacts.get('has-more')
                    vid_offset = json_response_all_contacts.get('vid-offset')
                    self.create_contact_queues(hubspot_instance, json_response_all_contacts,vid_offset,has_more)
            except Exception as e:
                error_message = 'Error while getting contacts in odoo \nHubspot response %s' % (str(e))
                self.env['hubspot.logger'].create_log_message('Import Contacts', error_message)
                logger.exception("Error in Getting All Contacts From Hubspot------------>\n" + error_message)
                hubspot_instance._raise_user_error(e)


    # def create_contact_queues(self,hubspot_instance, results,offset,has_more):
    #     contact_queue_list = []
    #     contact_queue = self.contact_create_queue(hubspot_instance,offset,has_more)
    #     contact_queue_list.append(contact_queue.id)
    #     message = "Contact Queue Created", contact_queue.name
    #     self._cr.commit()
    #     _logger.info(message)
    #     for result in results['contacts']:
    #         if result['canonical-vid']:
    #             get_contact_by_id_response = hubspot_instance._send_get_request('/contacts/v1/contact/vid/' + str(result['canonical-vid']) + '/profile')
    #             contact_profile = json.loads(get_contact_by_id_response)
    #             self.hubspot_create_contact_queue_line(contact_profile, hubspot_instance, contact_queue)
    #     self._cr.commit()
    

    def create_contact_queues(self, hubspot_instance, results, offset, has_more):
        """Creates contact queue and processes contacts from the response"""

        last_queue = self.env['contact.queue'].search(
            [('state', '!=', 'processing')], 
            order='create_date desc', 
            limit=1
        )

        if last_queue and last_queue.total_records_in_queue_line < 100:
            contact_queue = last_queue
        else:
            contact_queue = self.contact_create_queue(hubspot_instance, offset, has_more)
            message = f"Contact Queue Created: {contact_queue.name}"
            self.env.cr.commit()
            _logger.info(message)

        
        incoming_ids = [
            str(result.get('canonical-vid')) 
            for result in results.get('contacts', []) 
            if result.get('canonical-vid')
        ]

        existing_contacts = set(
            str(cid) for cid in self.env['contact.queue.line'].search([
                ('hubspot_contact_data_id', 'in', incoming_ids)
            ]).mapped('hubspot_contact_data_id')
        )

        new_contacts = [
            result for result in results.get('contacts', []) 
            if str(result.get('canonical-vid')) not in existing_contacts
        ]

        if not new_contacts:
            logger.info("No new contacts found. Skipping queue addition.")
            return False

        for result in new_contacts:
            contact_vid = result["canonical-vid"]
            get_contact_by_id_response = hubspot_instance._send_get_request(
                f"/contacts/v1/contact/vid/{contact_vid}/profile"
            )
            if not get_contact_by_id_response:
                logger.error(f"Failed to retrieve details for contact ID {contact_vid} after retries. Skipping this contact.")
                continue
            try:
                contact_profile = json.loads(get_contact_by_id_response)
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing JSON for Contact ID {contact_vid}: {e}")
                continue

            self.hubspot_create_contact_queue_line(contact_profile, hubspot_instance, contact_queue)

        return True


    def contact_create_queue(self,hubspot_instance,offset,has_more,created_by="import"):
        contact_queue_vals = {
            "hubspot_instance_id": hubspot_instance and hubspot_instance.id or False,
            "queue_created_by": created_by,
            "offset":offset,
            "has_more":has_more
        }
        return self.create(contact_queue_vals)


    def hubspot_create_contact_queue_line(self,result, hubspot_instance, contact_queue):
        contact_data_queue_line_obj = self.env["contact.queue.line"]
        data = json.dumps(result)
        contactName = ''
        image_import_state ='pending'
        image_data =''
              
        if 'firstname' in result['properties']:
            if len(result['properties']['firstname']['value']) > 0:
                contactName += result['properties']['firstname']['value'] + ' '
        if 'lastname' in result['properties']:
            if len(result['properties']['lastname']['value']) > 0:
                contactName += result['properties']['lastname']['value']
        elif contactName == '':
            contactName = "Unknown"
        if 'canonical-vid' in result:
            hubspot_contact_id = result['canonical-vid']
            try:

                response_get_associated_contact_attachment_detail = hubspot_instance._send_get_request(
                    f'/engagements/v1/engagements/associated/contact/{hubspot_contact_id}/paged')
            
                    
                        
                img_json = json.loads(response_get_associated_contact_attachment_detail).get('results', [])
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
                logger.error("Failed to parse JSON response for hubspot_contact_id: %s", hubspot_contact_id)
            except Exception as e:
                logger.error("An unexpected error occurred: %s", str(e))
                self.env.cr.commit()
        contact_queue_line_vals = {"hubspot_contact_data_id": result['canonical-vid'],
                                   "hubspot_instance_id": hubspot_instance and hubspot_instance.id or False,
                                   "name": contactName,
                                   "hubspot_contact_data": data,
                                   "contact_queue_id": contact_queue and contact_queue.id or False,
                                   "hubspot_image_import_state": image_import_state,
                                   "hubspot_image_data":image_data
                                   }
        contact_data_queue_line_obj.create(contact_queue_line_vals)
        return True
    

    def queue_manual_contact_process(self):
        if self:
            queue_id = self
        else:
            queue_id = self.env['contact.queue'].search([("state", "!=", 'completed')])
        if queue_id:
            for queue in queue_id:
                contact_queue_line = self.env['contact.queue.line'].search(
                    [("contact_queue_id", "=", queue.id),
                    ("state", "in", ('draft', 'failed'))])
                for lines in contact_queue_line:
                    lines.process_queue_line_contact_data()
            return True
