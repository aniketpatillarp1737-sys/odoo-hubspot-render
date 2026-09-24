from odoo import models, fields, api, _
import logging
import json
import time


_logger = logging.getLogger("Hubspot Queue")
logger = logging.getLogger(__name__)


class DealQueue(models.Model):
    _name = "deal.queue"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Hubspot Deal Queue"

    name = fields.Char()
    hubspot_instance_id = fields.Many2one("hubspot.instance", string="Instance")
    deal_queue_lines_ids = fields.One2many("deal.queue.line",
                                               "deal_queue_id",
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



    @api.depends("deal_queue_lines_ids.state")
    def _compute_status_queue_line(self):
        for queue in self:
            lines = queue.deal_queue_lines_ids
            queue.total_records_in_queue_line = len(lines)
            queue.draft_records_in_queue_line = len(lines.filtered(lambda x: x.state == "draft"))
            queue.fail_records_in_queue_line = len(lines.filtered(lambda x: x.state == "failed"))
            queue.done_records_in_queue_line = len(lines.filtered(lambda x: x.state == "done"))
            queue.cancel_records_in_queue_line = len(lines.filtered(lambda x: x.state == "cancel"))
    

    @api.depends("deal_queue_lines_ids.state")
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
            val['name'] = self.env["ir.sequence"].sudo().next_by_code('deal.queue')
        return super().create(vals)

    @api.model
    def _cron_import_deals_from_hubspot(self):
        hubspot_instance_obj = self.env['hubspot.instance'].search([('active', '=', True), ('hubspot_is_import_deals', '=', True)])
        for hubspot_instance in hubspot_instance_obj:
            self.import_deals_from_hubspot(hubspot_instance)

    def import_deals_from_hubspot(self, hubspot_instance):
        modifiedDateForDeals = float(hubspot_instance.modifiedDateForDeals or 0)
        all_deals = float(hubspot_instance.all_deals or 0)

        # Get import_type from context
        import_type = self.env.context.get('deal_import_type', 'opportunity')

        if hubspot_instance.hubspot_is_import_deals and hubspot_instance.active:
            logger.info('Getting All deals from hubspot---------------------------')
            try:
                has_more = True
                last_processing_deal = self.env['deal.queue'].search([('state', '!=', 'processing')],
                                                                     order='create_date desc', limit=1)

                print("\n\n\n last_processing_deal", last_processing_deal)

                if last_processing_deal:
                    if last_processing_deal.has_more:
                        offset = last_processing_deal.offset
                        logger.info(f'Continuing from last offset: {offset}')
                    else:
                        offset = 0
                else:
                    logger.info('No processing queues found; starting from offset 0.')
                    offset = 0
                while has_more:
                    deals_ids = []
                    record_limit = 100
                    response_all_deals = hubspot_instance._send_get_request(
                        '/deals/v1/deal/paged?offset=' + str(offset) + '&limit=' + str(record_limit))

                    json_response_all_deals = json.loads(response_all_deals)

                    has_more = json_response_all_deals.get('hasMore')
                    offset = json_response_all_deals.get('offset')

                    # Pass import_type to create_deal_queues
                    self.create_deal_queues(hubspot_instance, json_response_all_deals, offset, has_more, import_type)
            except Exception as e:
                error_message = 'Error while getting deals in odoo \nHubspot response %s' % (str(e))
                self.env['hubspot.logger'].create_log_message('Import Deals', error_message)
                logger.exception("Error in Getting All Deals From Hubspot------------>\n" + error_message)
                hubspot_instance._raise_user_error(e)

    def create_deal_queues(self, hubspot_instance, results, offset, has_more, import_type='opportunity'):
        deal_queue_list = []
        deal_queue = self.deal_create_queue(hubspot_instance, offset, has_more)
        deal_queue_list.append(deal_queue.id)
        message = "Deal Queue Created", deal_queue.name
        self._cr.commit()
        _logger.info(message)
        for result in results['deals']:
            if result['dealId']:
                get_deal_by_id_response = hubspot_instance._send_get_request('/deals/v1/deal/' + str(result['dealId']))
                deal_profile = json.loads(get_deal_by_id_response)
                # Pass import_type to queue line creation
                self.hubspot_create_deal_queue_line(deal_profile, hubspot_instance, deal_queue, import_type)
        self._cr.commit()
    
    # def import_deals_from_hubspot(self,hubspot_instance):
    #     modifiedDateForDeals = float(hubspot_instance.modifiedDateForDeals or 0)
    #     all_deals = float(hubspot_instance.all_deals or 0)
    #     if  hubspot_instance.hubspot_is_import_deals and hubspot_instance.active:
    #         logger.info('Getting All deals from hubspot---------------------------')
    #         try:
    #             has_more = True
    #             last_processing_deal = self.env['deal.queue'].search([('state', '!=', 'processing')], order='create_date desc', limit=1)
    #
    #             print("\n\n\n last_processing_deal", last_processing_deal)
    #
    #             if last_processing_deal:
    #                 if last_processing_deal.has_more:
    #                     offset = last_processing_deal.offset
    #                     logger.info(f'Continuing from last offset: {offset}')
    #                 else:
    #                     offset = 0
    #             else:
    #                 logger.info('No processing queues found; starting from offset 0.')
    #                 offset = 0
    #             while has_more:
    #                 deals_ids = []
    #                 record_limit = 100
    #                 response_all_deals = hubspot_instance._send_get_request('/deals/v1/deal/paged?offset=' + str(offset) + '&limit=' + str(record_limit))
    #
    #                 json_response_all_deals = json.loads(response_all_deals)
    #
    #                 has_more = json_response_all_deals.get('hasMore')
    #                 offset = json_response_all_deals.get('offset')
    #                 self.create_deal_queues(hubspot_instance, json_response_all_deals,offset,has_more)
    #         except Exception as e:
    #             error_message = 'Error while getting deals in odoo \nHubspot response %s' % (str(e))
    #             self.env['hubspot.logger'].create_log_message('Import Deals', error_message)
    #             logger.exception("Error in Getting All Deals From Hubspot------------>\n" + error_message)
    #             hubspot_instance._raise_user_error(e)

    # def create_deal_queues(self,hubspot_instance, results,offset,has_more):
    #     deal_queue_list = []
    #     deal_queue = self.deal_create_queue(hubspot_instance,offset,has_more)
    #     deal_queue_list.append(deal_queue.id)
    #     message = "Deal Queue Created", deal_queue.name
    #     self._cr.commit()
    #     _logger.info(message)
    #     for result in results['deals']:
    #         if result['dealId']:
    #             get_deal_by_id_response =  hubspot_instance._send_get_request('/deals/v1/deal/' + str(result['dealId']))
    #             deal_profile = json.loads(get_deal_by_id_response)
    #             self.hubspot_create_deal_queue_line(deal_profile, hubspot_instance, deal_queue)
    #     self._cr.commit()


    # def create_deal_queues(self, hubspot_instance, results, offset, has_more):
    #
    #     last_queue = self.env['deal.queue'].search(
    #         [('state', '!=', 'processing')],
    #         order='create_date desc',
    #         limit=1
    #     )
    #
    #     if last_queue and last_queue.total_records_in_queue_line < 100:
    #         deal_queue = last_queue
    #     else:
    #         deal_queue = self.deal_create_queue(hubspot_instance, offset, has_more)
    #
    #
    #     incoming_ids = [
    #         str(result.get('dealId'))
    #         for result in results.get('deals', [])
    #         if result.get('dealId')
    #     ]
    #
    #     existing_deals = set(
    #         str(deal_id) for deal_id in self.env['deal.queue.line'].search([
    #             ('hubspot_deal_data_id', 'in', incoming_ids)
    #         ]).mapped('hubspot_deal_data_id')
    #     )
    #
    #     new_deals = []
    #     for result in results.get('deals', []):
    #         deal_id = str(result.get('dealId'))
    #         if deal_id and deal_id not in existing_deals:
    #             new_deals.append(result)
    #         else:
    #             _logger.info(f"Skipping duplicate deal ID: {deal_id}")
    #
    #     if not new_deals:
    #         logger.info("No new deals found. Skipping queue addition.")
    #         return False
    #
    #     for result in new_deals:
    #         deal_id = str(result.get('dealId'))
    #         get_deal_by_id_response = hubspot_instance._send_get_request(f'/deals/v1/deal/{deal_id}')
    #         if not get_deal_by_id_response:
    #             logger.error(f"Failed to retrieve details for deal ID {deal_id} after retries. Skipping this deal.")
    #             continue
    #
    #         try:
    #             deal_profile = json.loads(get_deal_by_id_response)
    #         except json.JSONDecodeError as e:
    #             logger.error(f"Error parsing JSON for deal ID {deal_id}: {e}")
    #             continue
    #
    #         self.hubspot_create_deal_queue_line(deal_profile, hubspot_instance, deal_queue)
    #
    #     return True


    def deal_create_queue(self,hubspot_instance,offset,has_more,created_by="import"):
        deal_queue_vals = {
            "hubspot_instance_id": hubspot_instance and hubspot_instance.id or False,
            "queue_created_by": created_by,
            "offset":offset,
            "has_more":has_more
        }
        return self.create(deal_queue_vals)

    def hubspot_create_deal_queue_line(self, result, hubspot_instance, deal_queue, import_type='opportunity'):
        deal_data_queue_line_obj = self.env["deal.queue.line"]
        data = json.dumps(result)
        dealName = ''
        image_import_state = 'pending'
        image_data = ''
        if 'dealname' in result['properties']:
            dealName = result['properties']['dealname']['value']
        elif dealName == '':
            dealName = "Unknown"
        if result['dealId']:
            hubspot_deal_id = result['dealId']
            hubspot_pipeline = ''
            hubspot_deal_stage = ''
            try:
                pipeline_value = result['properties']['pipeline']['value']
                dealstage_value = result['properties']['dealstage']['value']
                response_get_associated_deal_pipeline = hubspot_instance._send_get_request(
                    f'/crm/v3/pipelines/deals/{pipeline_value}')
                response_pipeline = json.loads(response_get_associated_deal_pipeline)
                hubspot_pipeline = json.dumps(response_pipeline)
                if 'dealstage' in result['properties']:
                    response_get_associated_deal_stage = hubspot_instance._send_get_request(
                        f'/crm/v3/pipelines/deals/{pipeline_value}/stages/{dealstage_value}')
                    response_deal_stage = json.loads(response_get_associated_deal_stage)
                    hubspot_deal_stage = json.dumps(response_deal_stage)

            except Exception as e:
                logger.error("An unexpected error occurred: %s", str(e))
            try:
                response_get_associated_deal_attachment_detail = hubspot_instance._send_get_request(
                    f'/engagements/v1/engagements/associated/deal/{hubspot_deal_id}/paged')

                img_json = json.loads(response_get_associated_deal_attachment_detail).get('results', [])
                img_list = []
                for res in img_json:
                    attachments = res.get('attachments', [])
                    for attachment in attachments:
                        if attachment.get('id'):
                            attachment_id = attachment.get('id')
                            if attachment_id:
                                response_attachment_details = hubspot_instance._send_get_request(
                                    '/files/v3/files/' + str(attachment_id) + '/signed-url')
                                attachment_details = json.loads(response_attachment_details)
                                if attachment_details:
                                    img_list.append(attachment_details)

                img = img_list
                if img:
                    image_import_state = 'done'
                    image_data = json.dumps(img)
            except json.JSONDecodeError:
                logger.error("Failed to parse JSON response for hubspot_deal_id: %s", hubspot_deal_id)
            except Exception as e:
                logger.error("An unexpected error occurred: %s", str(e))
                self.env.cr.commit()

        deal_queue_line_vals = {
            "hubspot_deal_data_id": result['dealId'],
            "hubspot_instance_id": hubspot_instance and hubspot_instance.id or False,
            "name": dealName,
            "hubspot_deal_data": data,
            "deal_queue_id": deal_queue and deal_queue.id or False,
            "hubspot_image_import_state": image_import_state,
            "hubspot_image_data": image_data,
            'hubspot_pipeline': hubspot_pipeline,
            'hubspot_deal_stage': hubspot_deal_stage,
            'import_type': import_type  # ✅ ADD THIS LINE
        }
        deal_data_queue_line_obj.create(deal_queue_line_vals)
        return True


    # def hubspot_create_deal_queue_line(self,result, hubspot_instance, deal_queue):
    #     deal_data_queue_line_obj = self.env["deal.queue.line"]
    #     data = json.dumps(result)
    #     dealName = ''
    #     image_import_state ='pending'
    #     image_data =''
    #     if 'dealname' in result['properties']:
    #         dealName = result['properties']['dealname']['value']
    #     elif dealName == '':
    #         dealName = "Unknown"
    #     if result['dealId']:
    #         hubspot_deal_id = result['dealId']
    #         hubspot_pipeline =''
    #         hubspot_deal_stage = ''
    #         try:
    #             pipeline_value = result['properties']['pipeline']['value']
    #             dealstage_value =  result['properties']['dealstage']['value']
    #             response_get_associated_deal_pipeline = hubspot_instance._send_get_request(f'/crm/v3/pipelines/deals/{pipeline_value}')
    #             response_pipeline = json.loads(response_get_associated_deal_pipeline)
    #             hubspot_pipeline = json.dumps(response_pipeline)
    #             if 'dealstage' in result['properties']:
    #                 response_get_associated_deal_stage = hubspot_instance._send_get_request(f'/crm/v3/pipelines/deals/{pipeline_value}/stages/{dealstage_value}')
    #                 response_deal_stage = json.loads(response_get_associated_deal_stage)
    #                 hubspot_deal_stage =  json.dumps(response_deal_stage)
    #
    #         except Exception as e:
    #             logger.error("An unexpected error occurred: %s", str(e))
    #         try:
    #
    #             response_get_associated_deal_attachment_detail = hubspot_instance._send_get_request(
    #                             f'/engagements/v1/engagements/associated/deal/{hubspot_deal_id}/paged')
    #
    #             img_json = json.loads(response_get_associated_deal_attachment_detail).get('results', [])
    #             img_list = []
    #             for res in img_json:
    #                 attachments = res.get('attachments', [])
    #                 for attachment in attachments:
    #                     if attachment.get('id'):
    #                         attachment_id = attachment.get('id')
    #                         if attachment_id:
    #                             response_attachment_details = hubspot_instance._send_get_request('/files/v3/files/' + str(attachment_id) + '/signed-url')
    #                             attachment_details = json.loads(response_attachment_details)
    #                             if attachment_details:
    #                                 img_list.append(attachment_details)
    #
    #             img = img_list
    #             if img:
    #                 image_import_state = 'done'
    #                 image_data = json.dumps(img)
    #         except json.JSONDecodeError:
    #             logger.error("Failed to parse JSON response for hubspot_deal_id: %s", hubspot_deal_id)
    #         except Exception as e:
    #             logger.error("An unexpected error occurred: %s", str(e))
    #             self.env.cr.commit()
    #
    #     deal_queue_line_vals = {"hubspot_deal_data_id": result['dealId'],
    #                                "hubspot_instance_id": hubspot_instance and hubspot_instance.id or False,
    #                                "name": dealName,
    #                                "hubspot_deal_data": data,
    #                                "deal_queue_id": deal_queue and deal_queue.id or False,
    #                                "hubspot_image_import_state": image_import_state,
    #                                "hubspot_image_data":image_data,
    #                                'hubspot_pipeline':hubspot_pipeline,
    #                                'hubspot_deal_stage':hubspot_deal_stage
    #
    #                                }
    #     deal_data_queue_line_obj.create(deal_queue_line_vals)
    #     return True
    

    def queue_manual_deal_process(self):
        if self:
            queue_id = self
        else:
            queue_id = self.env['deal.queue'].search([("state", "!=", 'completed')])
        if queue_id:
            for queue in queue_id:
                deal_queue_line = self.env['deal.queue.line'].search(
                    [("deal_queue_id", "=", queue.id),
                    ("state", "in", ('draft', 'failed'))])
                for lines in deal_queue_line:
                    lines.process_queue_line_deal_data()
            return True
