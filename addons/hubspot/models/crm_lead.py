import logging
import random
import json
from datetime import datetime, timezone
from odoo import api, fields, models, _
import requests
import base64,zlib
logger = logging.getLogger(__name__)
from odoo.tools import config
config['limit_time_real'] = 10000000


class CrmLead(models.Model):
    _inherit = "crm.lead"

    hubspot_id = fields.Char('Hubspot Id', store=True, readonly=True, copy=False)
    hubspot_instance_id = fields.Many2one('hubspot.instance', 'Hubspot Instance Name', help="Hubspot Instance Name", readonly=True, copy=False)
    hubspot_deal_stage = fields.Char('Hubspot Deal Stage')
    hubspot_deal_type = fields.Char('Hubspot Deal Type')
    hubspot_pipeline = fields.Char('Hubspot Pipeline',readonly=True)
    partner_ids = fields.Many2many('res.partner', 'crm_lead_res_partner_rel', 'lead_id', 'partner_id', 'Partners')
    

    def write(self, vals):
        '''Update Contact or company details in hubspot on change of details in odoo'''
        res = super(CrmLead, self).write(vals)
        for record in self:
            if vals.get('stage_id'):
                stage_id = self.env['crm.stage'].sudo().search([('id', '=', vals.get('stage_id'))])
                record.hubspot_deal_stage = stage_id.name
            # Hubspot Information
            if record.hubspot_instance_id.hubspot_app_key and record.hubspot_instance_id.name:
                if not self.env.context.get('from_hubspot', False):
                    deals_field_mapping = self.env['deals.field.mapping'].search([('hubspot_instance_id', '=', record.hubspot_instance_id.id)])
                    try:
                        instance = ''
                        if record.hubspot_id and record.hubspot_instance_id and record.type == 'lead':
                            instance = record.hubspot_instance_id
                        if instance:
                            if instance.active  and instance.hubspot_is_export_deals and record.type == 'lead':
                                record.UpdateDealsInHubspot(instance)
                                if len(deals_field_mapping):
                                    record.UpdateDealsInHubspotFieldMapping(deals_field_mapping, instance)
                    except Exception as e_log:
                        error_message = 'Error while updating crm leads from odoo %d \n\n Odoo vals: %s\n Hubspot response %s' % (
                            record.id, str(vals), str(e_log))
                        self.env['hubspot.logger'].create_log_message('Export Deals', error_message)
                        logger.exception("Exception updating crm leads  :\n" + str(e_log))
                        instance._raise_user_error(e_log)

        return res

    # def unlink(self):
    #     '''Delete contact in hubspot on delete of contact or company in odoo'''
    #     for record in self:
    #         if record.hubspot_instance_id.hubspot_sync_deals and record.hubspot_instance_id and record.hubspot_instance_id.active and record.hubspot_instance_id.hubspot_is_export_deals:
    #             record.deleteFromHubspot(record.hubspot_instance_id)
    #             self._cr.commit()
    #     return super(CrmLead, self).unlink()

    # def deleteFromHubspot(self, hubspot_instance_id):
    #     logger.info('Delete from hubspot')
    #     try:
    #         for each in self:
    #             response = hubspot_instance_id._send_delete_request('/deals/v1/deal/' + str(each.hubspot_id))
    #     except Exception as e:
    #         error_message = 'Error while deleting deals in hubspot \nHubspot response %s' % (str(e))
    #         self.env['hubspot.logger'].create_log_message('Delete Deals', error_message)
    #         logger.exception("Error in deleted Deals From Hubspot------------>\n" + str(e))
    #         logger.info('Completed Delete from hubspot')
    #         hubspot_instance_id._raise_user_error(e)

    # def convert_time_to_unix_timestamp(self, deadline_date):
    #     '''
    #         This method converts date to unix timestamp
    #         @param : deadline_date(datetime.date)
    #         @returns : timestamp in millisecound(str)
    #     '''
    #     date_deadline = fields.Datetime.from_string(deadline_date)
    #     timestamp = date_deadline.replace(tzinfo=timezone.utc)
    #     generic_epoch = datetime.datetime(1970, 1, 1, 00, 00, 00)
    #     generic_epoch = generic_epoch.replace(tzinfo=timezone.utc)
    #     timestamp = (timestamp - generic_epoch).total_seconds()
    #     return int(timestamp * 1000)

    def convert_time_to_unix_timestamp(self, deadline_date):
        '''
            Converts a datetime or datetime string (ISO 8601) to a UNIX timestamp in milliseconds.
        '''
        if not deadline_date:
            return 0

        if isinstance(deadline_date, datetime):
            date_deadline = deadline_date
        elif isinstance(deadline_date, str):
            try:
                date_deadline = datetime.strptime(deadline_date, "%Y-%m-%dT%H:%M:%S.%fZ")
            except ValueError:
                try:
                    date_deadline = datetime.strptime(deadline_date, "%Y-%m-%dT%H:%M:%SZ")
                except ValueError:
                    _logger.warning(f"Invalid date format from HubSpot: {deadline_date}")
                    return 0
        else:
            _logger.warning(f"Unsupported type for deadline_date: {type(deadline_date)}")
            return 0

        # Ensure UTC
        date_deadline = date_deadline.replace(tzinfo=timezone.utc)
        return int(date_deadline.timestamp() * 1000)


    def hubspot_queue_deal_create(self,line,hubspot_instance):
        deals_info = []
        try:
            deals = json.loads(line.hubspot_deal_data)
            print("deals ---------------------------------------------->\n\n\n", deals)
            deals_info.append(deals)
            deal_id = deals_info[0]['dealId']

           
            if deals_info:
                self.createQueueNewDealsInOdoo(deals_info,line,hubspot_instance)
                # self._cr.commit()
                deals_field_mapping = self.env['deals.field.mapping'].search([('hubspot_instance_id', '=', hubspot_instance.id)])
                if len(deals_field_mapping) > 0:
                    self.createNewDealsInOdooFieldMapping(deals_info, hubspot_instance)
        except Exception as e:
                error_message = 'Error while importing hubspot deals in odoo Id: %s\n Hubspot response %s' % (
                    deal_id, str(e))
                self.env['hubspot.logger'].create_log_message('Import Deals', error_message)
                logger.exception("Exception In getting deals info from Hubspot : \n" + error_message)
                hubspot_instance._raise_user_error(e)
         



    def import_skip_deals_from_hubspot(self, hubspot_instance):
        if  hubspot_instance.hubspot_is_import_deals and hubspot_instance.active: 
            logger.info('Getting All skipped deals from hubspot---------------------------')
            try:
                has_more = True
                offset = 0
                while has_more:
                    deals_ids = []
                    record_limit = 90
                    response_all_deals = hubspot_instance._send_get_request('/deals/v1/deal/paged?offset=' + str(offset) + '&limit=' + str(record_limit))
                    json_response_all_deals = json.loads(response_all_deals)
                    has_more = json_response_all_deals.get('hasMore')
                    offset = json_response_all_deals.get('offset')
                    for deals_id in json_response_all_deals['deals']:
                        if deals_id['dealId']:
                            deals_ids.append(deals_id['dealId'])
                    if deals_ids:
                        self.with_context({'from_skipped_deals': True}).get_deals_details_and_create(deals_ids, hubspot_instance)
                message = 'Completed Getting All deals from hubspot'
                self.env['hubspot.logger'].create_log_message('Import Deals', message)
                logger.info('Completed Getting All deals from hubspot------------------------------------------------------')
            except Exception as e:
                error_message = 'Error while getting deals in odoo \nHubspot response %s' % (str(e))
                self.env['hubspot.logger'].create_log_message('Import Deals', error_message)
                logger.exception("Error in Getting All Deals From Hubspot------------>\n" + error_message)
                hubspot_instance._raise_user_error(e)


    def get_deals_details_and_create(self, deals_ids, hubspot_instance):
        for deals_id in deals_ids:
            deals_info = []
            try:
                get_deals_by_id_response = hubspot_instance._send_get_request('/deals/v1/deal/' + str(deals_id))
                
                deals_profile = json.loads(get_deals_by_id_response)
                deals_info.append(deals_profile)
                logger.info('get deals details')
             
                self.createNewDealsInOdoo(deals_info, hubspot_instance)
                self.env.cr.commit()
                deals_field_mapping = self.env['deals.field.mapping'].search([('hubspot_instance_id', '=', hubspot_instance.id)])
                if len(deals_field_mapping) > 0:
                    self.createNewDealsInOdooFieldMapping(deals_info, hubspot_instance)
            except Exception as e:
                error_message = 'Error while importing hubspot deals in odoo Id: %s\n Hubspot response %s' % (
                    deals_id, str(e))
                self.env['hubspot.logger'].create_log_message('Import Deals', error_message)
                logger.exception("Exception In getting deals info from Hubspot : \n" + error_message)
                hubspot_instance._raise_user_error(e)


    def createQueueNewDealsInOdoo(self, deals_info, line, hubspot_instance):
        """
        Import deals from HubSpot as either Leads or Opportunities based on import_type
        """
        import json
        from datetime import timezone

        res_partner_obj = self.env['res.partner']
        vals = {}

        # Get import type from context (set by wizard or queue line)
        import_type = self.env.context.get('deal_import_type', 'opportunity')

        # FIX #1: helpers (get_company_details_and_create / get_contact_details_and_create)
        # can return None, an empty recordset, or several records -> never touch .id raw.
        def _first_partner(result):
            """Normalise a helper result (None / empty / recordset / list of ids) to one record."""
            if not result:                                       # None or empty
                return self.env['res.partner'].browse()          # empty recordset, safe to .id-check
            if hasattr(result, 'ids'):                           # already a recordset
                return result[:1]
            return self.env['res.partner'].browse(result)[:1]    # list of ids

        # FIX #2: collect the touched record instead of returning inside the loop
        last_crm_lead = self.env['crm.lead'].browse()

        for deals_dict_details in deals_info:
            vals = {}  # Reset vals for each deal

            # FIX #3: reset per deal - it used to be initialised once outside the loop, so a deal
            # without hs_lastmodifieddate inherited the previous deal's date
            newdealsModifiedDate = 10000000.0

            # FIX #4: raw dict indexing -> .get(), so a partial payload no longer raises KeyError
            properties = deals_dict_details.get('properties') or {}

            # ============ DEAL NAME ============
            dealname = (properties.get('dealname') or {}).get('value')
            if dealname:
                vals['name'] = dealname

            # ============ LAST MODIFIED DATE ============
            hs_modified = (properties.get('hs_lastmodifieddate') or {}).get('value')
            if hs_modified:
                newdealsModifiedDate = int(float(hs_modified))   # FIX: tolerate float-like strings

            # ============ PIPELINE (Only for Opportunities) ============
            if import_type == 'opportunity' and line.hubspot_pipeline:
                response_pipeline = json.loads(line.hubspot_pipeline)
                pipeline_label = response_pipeline.get('label')   # FIX: .get() instead of ['label']
                if pipeline_label:
                    vals['hubspot_pipeline'] = pipeline_label

            # ============ DEAL STAGE (Only for Opportunities) ============
            if import_type == 'opportunity' and 'dealstage' in properties and line.hubspot_deal_stage:
                deal_stages = (json.loads(line.hubspot_deal_stage) or {}).get('label')
                if deal_stages:
                    vals['hubspot_deal_stage'] = deal_stages

                    # --- Map HubSpot deal stage to Odoo CRM stage ---
                    crm_stage = self.env['crm.stage'].sudo().search(
                        [('name', 'ilike', deal_stages)], limit=1)
                    if not crm_stage:
                        # Create new stage if not found (only for opportunities)
                        crm_stage = self.env['crm.stage'].sudo().create({
                            'name': deal_stages,
                            'sequence': 10
                        })
                    vals['stage_id'] = crm_stage.id

            # ============ CLOSE DATE ============
            # FIX #5: 'timestamp' can be missing/empty; some responses carry the epoch under 'value'
            closedate = (properties.get('closedate') or {}).get('timestamp')
            if closedate:
                vals['date_closed'] = self.env['mail.activity'].convert_epoch_to_gmt_timestamp(closedate)

            # ============ DEAL TYPE ============
            dealtype = (properties.get('dealtype') or {}).get('value')
            if dealtype == 'newbusiness':
                vals['hubspot_deal_type'] = 'New Business'
            elif dealtype == 'existingbusiness':
                vals['hubspot_deal_type'] = 'Existing Business'

            # ============ DEAL OWNER ============
            # FIX #6: renamed the local variable - the old code reused `partner_id` for the owner,
            # the contact AND the company, which is what makes this block so easy to misread
            owner_hs_id = (properties.get('hubspot_owner_id') or {}).get('value')
            if owner_hs_id:
                owner_partner = self.env['res.partner'].search(
                    [('hubspot_id', '=', str(owner_hs_id)),
                     ('hubspot_instance_id', '=', hubspot_instance.id)], limit=1)

                if not owner_partner:
                    # If not found, try to fetch from HubSpot
                    owner_partner = self.env['res.partner'].getOwnerDetailsFromHubspot(
                        owner_hs_id, hubspot_instance)

                if owner_partner:
                    # Now find the corresponding res.users record
                    user = self.env['res.users'].search(
                        [('partner_id', '=', owner_partner.id)], limit=1)
                    if user:
                        vals['user_id'] = user.id
                    else:
                        logger.warning(
                            f"No res.users found for partner {owner_partner.name} (ID: {owner_partner.id})")

            # ============ AMOUNT ============
            amount = (properties.get('amount') or {}).get('value')
            if amount not in (None, ''):    # FIX #7: an empty amount used to be written verbatim
                vals['expected_revenue'] = amount

            # ============ HUBSPOT DEAL ID ============
            deal_id = deals_dict_details.get('dealId')
            if not deal_id:
                logger.warning("Skipping HubSpot deal without a dealId: %s", deals_dict_details)
                continue                    # FIX: everything below keys off deal_id
            vals['hubspot_id'] = deal_id

            # ============ ASSOCIATIONS (CONTACTS / COMPANIES) ============
            partner_list = []
            associations = deals_dict_details.get('associations') or {}
            associated_vids = associations.get('associatedVids') or []              # FIX #4
            associated_company_ids = associations.get('associatedCompanyIds') or []  # FIX #4

            # ---- Primary partner: contacts take precedence (unchanged behaviour) ----
            if associated_vids and hubspot_instance.hubspot_is_import_contacts:
                primary_contact = res_partner_obj.sudo().search(
                    [('hubspot_id', '=', str(associated_vids[0])),
                     ('hubspot_instance_id', '=', hubspot_instance.id)], limit=1)
                if not primary_contact:
                    # FIX #8: the old code re-searched with ('hubspot_id', '=', res_partner_id.id),
                    # i.e. it compared a HubSpot id against an Odoo id. Use the returned record.
                    primary_contact = _first_partner(
                        res_partner_obj.get_contact_details_and_create(
                            [associated_vids[0]], hubspot_instance))
                if primary_contact:
                    vals['partner_id'] = primary_contact.id

                for contact_id in associated_vids:
                    partner = self.env['res.partner'].sudo().search(
                        [('hubspot_id', '=', str(contact_id)),      # FIX #9: str() consistently
                         ('is_company', '=', False),
                         ('hubspot_instance_id', '=', hubspot_instance.id)], limit=1)
                    if not partner and hubspot_instance.hubspot_is_import_contacts:
                        partner = _first_partner(
                            self.env['res.partner'].get_contact_details_and_create(
                                [contact_id], hubspot_instance))
                    if partner:                                     # FIX #10: guard before .id
                        partner_list.append(partner.id)

            # ---- PRIMARY PARTNER: company (only if no contact became the primary) ----
            # FIX #11: this used to be an `elif`, so companies were dropped whenever the deal
            # happened to have any associated contact
            if not vals.get('partner_id') and associated_company_ids and hubspot_instance.hubspot_is_import_company:
                company = self.env['res.partner'].sudo().search(
                    [('hubspot_id', '=', str(associated_company_ids[0])),
                     ('hubspot_instance_id', '=', hubspot_instance.id)], limit=1)
                if not company:
                    # FIX #8 (company side): same wrong re-search removed
                    company = _first_partner(
                        res_partner_obj.get_company_details_and_create(
                            [associated_company_ids[0]], hubspot_instance))
                if company:
                    vals['partner_id'] = company.id

            # ---- COMPANY FOLLOWERS ----
            if associated_company_ids and hubspot_instance.hubspot_is_import_company:
                for company_id in associated_company_ids:
                    company = self.env['res.partner'].sudo().search(
                        [('hubspot_id', '=', str(company_id)),
                         ('is_company', '=', True),
                         ('hubspot_instance_id', '=', hubspot_instance.id)], limit=1)
                    if not company:
                        company = _first_partner(
                            self.env['res.partner'].get_company_details_and_create(
                                [company_id], hubspot_instance))
                    if company:                                     # FIX #10: THE CRASH LINE
                        partner_list.append(company.id)

            if partner_list:
                vals['partner_ids'] = [(6, 0, partner_list)]

            # ✅ SET TYPE BASED ON IMPORT SELECTION
            vals['type'] = import_type  # Either 'lead' or 'opportunity'

            # ============ EXISTING DEALS HANDLING ============
            crm_lead_id = self.env['crm.lead'].sudo().search(
                ['|', ('active', '=', True), ('active', '=', False),
                 ('hubspot_id', '=', str(deal_id)),
                 ('hubspot_instance_id', '=', hubspot_instance.id),
                 ('type', '=', import_type)], limit=1)

            # ---------- UPDATE EXISTING ----------
            if crm_lead_id:
                odoo_modifiedDate = self.convert_time_to_unix_timestamp(crm_lead_id.write_date)
                if self.env.context.get('from_skipped_deals') or \
                        int(newdealsModifiedDate) > int(odoo_modifiedDate):
                    crm_lead_id.with_context({'from_hubspot': True}).write(vals)
                    self._cr.commit()
                    logger.info(f"Updated existing Odoo {import_type}: {crm_lead_id.hubspot_id}")
                # FIX #12: mark the line done even when Odoo's copy is newer - the old code
                # silently fell out of the method without updating state, leaving the queue line stale
                line.state = 'done'
                last_crm_lead = crm_lead_id
                continue            # FIX #2: was `return` -> stopped processing every remaining deal

            # ---------- CREATE NEW ----------
            if 'name' in vals:
                crm_lead_exists = self.env['crm.lead'].sudo().search(
                    ['|', ('active', '=', True), ('active', '=', False),
                     ('name', '=', vals['name']),
                     ('type', '=', import_type),
                     ('hubspot_id', '=', False),
                     ('hubspot_instance_id', '=', False)], limit=1)
                if crm_lead_exists:
                    vals['hubspot_instance_id'] = hubspot_instance.id
                    crm_lead_exists.with_context({'from_hubspot': True}).write(vals)
                    line.state = 'done'
                    logger.info(f"Updated existing unnamed Odoo {import_type}: {crm_lead_exists.id}")
                    last_crm_lead = crm_lead_exists
                    continue

            vals['hubspot_instance_id'] = hubspot_instance.id
            new_crm_lead = self.with_context({'from_hubspot': True}).create(vals)
            line.state = 'done'
            logger.info(f"Created new Odoo {import_type}: {new_crm_lead.id}")
            last_crm_lead = new_crm_lead

        return last_crm_lead     # FIX #2: single exit point, after every deal has been processed


    # def createQueueNewDealsInOdoo(self, deals_info, line, hubspot_instance):
    #     """
    #     Import deals from HubSpot as either Leads or Opportunities based on import_type
    #     """
    #     import json
    #     from datetime import timezone
    #
    #     newdealsModifiedDate = 10000000.0
    #     res_partner_obj = self.env['res.partner']
    #     vals = {}
    #
    #     # Get import type from context (set by wizard or queue line)
    #     import_type = self.env.context.get('deal_import_type', 'opportunity')
    #
    #     for deals_dict_details in deals_info:
    #         vals = {}  # Reset vals for each deal
    #
    #         # ============ DEAL NAME ============
    #         if 'dealname' in deals_dict_details['properties']:
    #             vals['name'] = deals_dict_details['properties']['dealname']['value']
    #
    #         # ============ LAST MODIFIED DATE ============
    #         if 'hs_lastmodifieddate' in deals_dict_details['properties']:
    #             if deals_dict_details['properties']['hs_lastmodifieddate']['value']:
    #                 newdealsModifiedDate = int(deals_dict_details['properties']['hs_lastmodifieddate']['value'])
    #
    #         # ============ PIPELINE (Only for Opportunities) ============
    #         if import_type == 'opportunity' and line.hubspot_pipeline:
    #             response_pipeline = json.loads(line.hubspot_pipeline)
    #             pipeline_label = response_pipeline['label']
    #             vals['hubspot_pipeline'] = pipeline_label
    #
    #         # ============ DEAL STAGE (Only for Opportunities) ============
    #         if import_type == 'opportunity' and 'dealstage' in deals_dict_details['properties']:
    #             if line.hubspot_deal_stage:
    #                 response_deal_stage = json.loads(line.hubspot_deal_stage)
    #                 deal_stages = response_deal_stage['label']
    #                 vals['hubspot_deal_stage'] = deal_stages
    #
    #                 # --- Map HubSpot deal stage to Odoo CRM stage ---
    #                 crm_stage = self.env['crm.stage'].sudo().search([('name', 'ilike', deal_stages)], limit=1)
    #                 if crm_stage:
    #                     vals['stage_id'] = crm_stage.id
    #                 else:
    #                     # Create new stage if not found (only for opportunities)
    #                     new_stage = self.env['crm.stage'].sudo().create({
    #                         'name': deal_stages,
    #                         'sequence': 10
    #                     })
    #                     vals['stage_id'] = new_stage.id
    #
    #         # ============ CLOSE DATE ============
    #         if 'closedate' in deals_dict_details['properties']:
    #             closedate = deals_dict_details['properties']['closedate']['timestamp']
    #             vals['date_closed'] = self.env['mail.activity'].convert_epoch_to_gmt_timestamp(closedate)
    #
    #         # ============ DEAL TYPE ============
    #         if 'dealtype' in deals_dict_details['properties']:
    #             if deals_dict_details['properties']['dealtype']['value'] == 'newbusiness':
    #                 vals['hubspot_deal_type'] = 'New Business'
    #             elif deals_dict_details['properties']['dealtype']['value'] == 'existingbusiness':
    #                 vals['hubspot_deal_type'] = 'Existing Business'
    #
    #         # ============ DEAL OWNER ============
    #         if 'hubspot_owner_id' in deals_dict_details['properties'] and deals_dict_details['properties'].get(
    #                 'hubspot_owner_id').get('value'):
    #             hubspot_owner_id = deals_dict_details['properties']['hubspot_owner_id']['value']
    #
    #             # First try to find res.partner with this hubspot_id
    #             partner_id = self.env['res.partner'].search(
    #                 [('hubspot_id', '=', hubspot_owner_id),
    #                  ('hubspot_instance_id', '=', hubspot_instance.id)], limit=1)
    #
    #             if not partner_id:
    #                 # If not found, try to fetch from HubSpot
    #                 partner_id = self.env['res.partner'].getOwnerDetailsFromHubspot(
    #                     hubspot_owner_id, hubspot_instance)
    #
    #             if partner_id:
    #                 # Now find the corresponding res.users record
    #                 user = self.env['res.users'].search([('partner_id', '=', partner_id.id)], limit=1)
    #                 if user:
    #                     vals['user_id'] = user.id
    #                 else:
    #                     # If no user exists, either skip or create one
    #                     logger.warning(f"No res.users found for partner {partner_id.name} (ID: {partner_id.id})")
    #                     # Optionally, you can skip setting user_id or handle it differently
    #
    #         # ============ AMOUNT ============
    #         if 'amount' in deals_dict_details['properties']:
    #             vals['expected_revenue'] = deals_dict_details['properties']['amount']['value']
    #
    #         # ============ HUBSPOT DEAL ID ============
    #         if deals_dict_details['dealId']:
    #             vals['hubspot_id'] = deals_dict_details['dealId']
    #
    #         # ============ ASSOCIATIONS (CONTACTS / COMPANIES) ============
    #         partner_list = []
    #         if 'associations' in deals_dict_details:
    #             if deals_dict_details['associations']['associatedVids'] and hubspot_instance.hubspot_is_import_contacts:
    #                 contact_ids = deals_dict_details['associations']['associatedVids']
    #                 partner_id = res_partner_obj.sudo().search(
    #                     [('hubspot_id', '=', str(contact_ids[0])),
    #                      ('hubspot_instance_id', '=', hubspot_instance.id)], limit=1)
    #                 if partner_id:
    #                     vals['partner_id'] = partner_id.id
    #                 else:
    #                     res_partner_ids = res_partner_obj.get_contact_details_and_create([contact_ids[0]],
    #                                                                                      hubspot_instance)
    #                     for res_partner_id in res_partner_ids:
    #                         partner_id = res_partner_obj.sudo().search(
    #                             [('hubspot_id', '=', res_partner_id.id)], limit=1)
    #                         if partner_id:
    #                             vals['partner_id'] = partner_id.id
    #
    #                 for contact_id in deals_dict_details['associations']['associatedVids']:
    #                     partner_id = self.env['res.partner'].sudo().search(
    #                         [('hubspot_id', '=', contact_id),
    #                          ('is_company', '=', False),
    #                          ('hubspot_instance_id', '=', hubspot_instance.id)], limit=1)
    #                     if partner_id:
    #                         partner_list.append(partner_id.id)
    #                     elif hubspot_instance.hubspot_is_import_contacts:
    #                         partner_id = self.env['res.partner'].get_contact_details_and_create([contact_id],
    #                                                                                             hubspot_instance)
    #                         partner_list.append(partner_id.id)
    #
    #             elif deals_dict_details['associations'][
    #                 'associatedCompanyIds'] and hubspot_instance.hubspot_is_import_company:
    #                 company_id = self.env['res.partner'].sudo().search(
    #                     [('hubspot_id', '=', str(deals_dict_details['associations']['associatedCompanyIds'][0])),
    #                      ('hubspot_instance_id', '=', hubspot_instance.id)], limit=1)
    #                 if company_id:
    #                     vals['partner_id'] = company_id.id
    #                 else:
    #                     res_partner_ids = res_partner_obj.get_company_details_and_create(
    #                         [deals_dict_details['associations']['associatedCompanyIds'][0]], hubspot_instance)
    #                     for res_partner_id in res_partner_ids:
    #                         company_id = res_partner_obj.sudo().search(
    #                             [('hubspot_id', '=', res_partner_id.id)], limit=1)
    #                         if company_id:
    #                             vals['partner_id'] = company_id.id
    #
    #                 for company_id in deals_dict_details['associations']['associatedCompanyIds']:
    #                     company_partner_id = self.env['res.partner'].sudo().search(
    #                         [('hubspot_id', '=', company_id),
    #                          ('is_company', '=', True),
    #                          ('hubspot_instance_id', '=', hubspot_instance.id)], limit=1)
    #                     if company_partner_id:
    #                         partner_list.append(company_partner_id.id)
    #                     elif hubspot_instance.hubspot_is_import_company:
    #                         company_partner_id = self.env['res.partner'].get_company_details_and_create([company_id],
    #                                                                                                     hubspot_instance)
    #                         partner_list.append(company_partner_id.id)
    #
    #         if partner_list:
    #             vals['partner_ids'] = [(6, 0, partner_list)]
    #
    #         # ✅ SET TYPE BASED ON IMPORT SELECTION
    #         vals['type'] = import_type  # Either 'lead' or 'opportunity'
    #
    #         # ============ EXISTING DEALS HANDLING ============
    #         crm_lead_id = self.env['crm.lead'].sudo().search(
    #             ['|', ('active', '=', True), ('active', '=', False),
    #              ('hubspot_id', '=', str(deals_dict_details['dealId'])),
    #              ('hubspot_instance_id', '=', hubspot_instance.id),
    #              ('type', '=', import_type)], limit=1)
    #
    #         # ---------- UPDATE EXISTING ----------
    #         if crm_lead_id:
    #             line.state = 'done'
    #             odoo_modifiedDate = self.convert_time_to_unix_timestamp(crm_lead_id.write_date)
    #             if self.env.context.get('from_skipped_deals') or int(newdealsModifiedDate) > int(odoo_modifiedDate):
    #                 crm_lead_id.with_context({'from_hubspot': True}).write(vals)
    #                 line.state = 'done'
    #                 self._cr.commit()
    #                 logger.info(f"Updated existing Odoo {import_type}: {crm_lead_id.hubspot_id}")
    #                 return crm_lead_id
    #
    #         # ---------- CREATE NEW ----------
    #         else:
    #             if 'name' in vals:
    #                 crm_lead_exists = self.env['crm.lead'].sudo().search(
    #                     ['|', ('active', '=', True), ('active', '=', False),
    #                      ('name', '=', vals['name']),
    #                      ('type', '=', import_type),
    #                      ('hubspot_id', '=', False),
    #                      ('hubspot_instance_id', '=', False)], limit=1)
    #                 if crm_lead_exists:
    #                     vals['hubspot_instance_id'] = hubspot_instance.id
    #                     crm_lead_exists.with_context({'from_hubspot': True}).write(vals)
    #                     line.state = 'done'
    #                     logger.info(f"Updated existing unnamed Odoo {import_type}: {crm_lead_exists.id}")
    #                     return crm_lead_exists
    #                 else:
    #                     vals['hubspot_instance_id'] = hubspot_instance.id
    #                     crm_lead_id = self.with_context({'from_hubspot': True}).create(vals)
    #                     line.state = 'done'
    #                     logger.info(f"Created new Odoo {import_type}: {crm_lead_id.id}")
    #                     return crm_lead_id

    @api.model
    def createNewDealsInOdoo(self, deals_dict, hubspot_instance):
        try:
            newdealsModifiedDate = 10000000.0
            res_partner_obj = self.env['res.partner']
            # pipeline_label = None
            vals = {}
            for deals_dict_details in deals_dict:
                pipeline_value = deals_dict_details['properties']['pipeline']['value']
                dealstage_value = deals_dict_details['properties']['dealstage']['value']
                response_get_associated_deal_pipeline = hubspot_instance._send_get_request(
                    f'/crm/v3/pipelines/deals/{pipeline_value}')
                response_pipeline = json.loads(response_get_associated_deal_pipeline)
                pipeline_label = response_pipeline['label']
                vals['hubspot_pipeline'] = pipeline_label

                if 'dealstage' in deals_dict_details['properties']:
                    response_get_associated_deal_stage = hubspot_instance._send_get_request(
                        f'/crm/v3/pipelines/deals/{pipeline_value}/stages/{dealstage_value}')
                    response_deal_stage = json.loads(response_get_associated_deal_stage)
                    deal_stages = response_deal_stage['label']
                    vals['hubspot_deal_stage'] = deal_stages

                    crm_stage = self.env['crm.stage'].sudo().search([('name', '=', deal_stages)], limit=1)
                    if crm_stage:
                        vals['stage_id'] = crm_stage.id

                if 'hs_lastmodifieddate' in deals_dict_details['properties']:
                    if deals_dict_details['properties']['hs_lastmodifieddate']['value']:
                        newdealsModifiedDate = int(deals_dict_details['properties']['hs_lastmodifieddate']['value'])
                if deals_dict_details['dealId']:
                    vals['hubspot_id'] = deals_dict_details['dealId']
                if 'dealname' in deals_dict_details['properties']:
                    vals['name'] = deals_dict_details['properties']['dealname']['value']

                if 'closedate' in deals_dict_details['properties']:
                    closedate = deals_dict_details['properties']['closedate']['timestamp']
                    vals['date_closed'] = self.env['mail.activity'].convert_epoch_to_gmt_timestamp(closedate)

                if 'dealtype' in deals_dict_details['properties']:

                    if deals_dict_details['properties']['dealtype']['value'] == 'newbusiness':
                        vals['hubspot_deal_type'] = 'New Business'
                    if deals_dict_details['properties']['dealtype']['value'] == 'existingbusiness':
                        vals['hubspot_deal_type'] = 'Existing Business'
                # if 'hubspot_owner_id' in deals_dict_details['properties'] and deals_dict_details['properties'].get(
                #         'hubspot_owner_id').get('value'):
                #
                #     user_id = self.env['res.partner'].search(
                #         [('hubspot_id', '=', deals_dict_details['properties']['hubspot_owner_id']['value']),
                #          ('hubspot_instance_id', '=', hubspot_instance.id)], limit=1)
                #     if not user_id:
                #         get_user = self.env['res.partner'].getOwnerDetailsFromHubspot(
                #             deals_dict_details['properties']['hubspot_owner_id']['value'], hubspot_instance)
                #         if get_user:
                #             vals['hubspot_id'] = get_user.id
                #
                #     else:
                #         vals['hubspot_id'] = user_id.id
                if 'amount' in deals_dict_details['properties']:
                    vals['expected_revenue'] = deals_dict_details['properties']['amount']['value']

                partner_list = []
                if 'associations' in deals_dict_details:
                    if deals_dict_details['associations'][
                        'associatedVids'] and hubspot_instance.hubspot_is_import_contacts:
                        contact_ids = deals_dict_details['associations']['associatedVids']
                        partner_id = res_partner_obj.sudo().search([('hubspot_id', '=', str(contact_ids[0])),
                                                                    ('hubspot_instance_id', '=', hubspot_instance.id)],
                                                                   limit=1)
                        if partner_id:
                            vals['partner_id'] = partner_id.id

                        else:
                            res_partner_ids = res_partner_obj.get_contact_details_and_create([contact_ids[0]],
                                                                                             hubspot_instance)
                            for res_partner_id in res_partner_ids:
                                partner_id = res_partner_obj.sudo().search([('hubspot_id', '=', res_partner_id.id)],
                                                                           limit=1)
                                if partner_id:
                                    vals['partner_id'] = partner_id.id
                        for contact_id in deals_dict_details['associations']['associatedVids']:
                            partner_id = self.env['res.partner'].sudo().search(
                                [('hubspot_id', '=', contact_id), ('is_company', '=', False),
                                 ('hubspot_instance_id', '=', hubspot_instance.id)], limit=1)
                            if partner_id:
                                partner_list.append(partner_id.id)
                            else:
                                if hubspot_instance.hubspot_is_import_contacts:
                                    partner_id = self.env['res.partner'].get_contact_details_and_create([contact_id],
                                                                                                        hubspot_instance)
                                    partner_list.append(partner_id.id)

                    elif deals_dict_details['associations'][
                        'associatedCompanyIds'] and hubspot_instance.hubspot_is_import_company:
                        company_id = self.env['res.partner'].sudo().search(
                            [('hubspot_id', '=', str(deals_dict_details['associations']['associatedCompanyIds'][0])),
                             ('hubspot_instance_id', '=', hubspot_instance.id)], limit=1)
                        if company_id:
                            vals['partner_id'] = company_id.id

                        else:
                            res_partner_ids = res_partner_obj.get_company_details_and_create(
                                [deals_dict_details['associations']['associatedCompanyIds'][0]], hubspot_instance)
                            for res_partner_id in res_partner_ids:
                                company_id = res_partner_obj.sudo().search([('hubspot_id', '=', res_partner_id.id)],
                                                                           limit=1)
                                if company_id:
                                    vals['partner_id'] = company_id.id
                    for company_id in deals_dict_details['associations']['associatedCompanyIds']:
                        company_partner_id = self.env['res.partner'].sudo().search(
                            [('hubspot_id', '=', company_id), ('is_company', '=', True),
                             ('hubspot_instance_id', '=', hubspot_instance.id)])
                        if company_partner_id:
                            partner_list.append(company_partner_id.id)
                        else:
                            if hubspot_instance.hubspot_is_import_company:
                                company_partner_id = self.env['res.partner'].get_company_details_and_create(
                                    [company_id], hubspot_instance)
                                partner_list.append(company_partner_id.id)
                if len(partner_list) > 0:
                    vals['partner_ids'] = [(6, 0, partner_list)]
                # vals['type'] = 'lead'
                vals['type'] = 'opportunity'
                crm_lead_id = self.env['crm.lead'].sudo().search(
                    ['|', ('active', '=', True), ('active', '=', False),
                     ('hubspot_id', '=', str(deals_dict_details['dealId'])),
                     ('hubspot_instance_id', '=', hubspot_instance.id),
                     ('type', '=', 'opportunity')], limit=1)
                if crm_lead_id:
                    # hubspot_deal_id = vals['hubspot_id']
                    # logger.info("Updated deal id====0========: %s",hubspot_deal_id)
                    # try:
                    #     response_get_associated_deal_attachment_detail = hubspot_instance._send_get_request(
                    #         f'/engagements/v1/engagements/associated/deal/{hubspot_deal_id}/paged')
                    #     if response_get_associated_deal_attachment_detail. == 200:

                    #         logger.info("Raw response content=======================o: %s", response_get_associated_deal_attachment_detail)

                    #         json_response_get_associated_deal_attachment_detail = json.loads(response_get_associated_deal_attachment_detail)

                    #         logger.info("Parsed JSON response==============0: %s", json.dumps(json_response_get_associated_deal_attachment_detail, indent=4))

                    #         results = json_response_get_associated_deal_attachment_detail.get('results', [])

                    #         if results:
                    #             deal_id = self.env['crm.lead'].sudo().search(
                    #             [('type', '=', 'opportunity'), ('hubspot_id', '=', hubspot_deal_id), ('hubspot_instance_id', '=', hubspot_instance.id)])

                    #             model_id = self.env['ir.model']._get('crm.lead').id
                    #             model_name = 'crm.lead'

                    #             for result in results:
                    #                 attachments = result.get('attachments', [])
                    #                 for attachment in attachments:
                    #                     attachment_id = attachment.get('id')
                    #                     if attachment_id:
                    #                         attachment_details = self.get_attachment_by_id(attachment_id, hubspot_instance)
                    #                         if attachment_details:
                    #                             create_attachment = self.create_attachment(attachment_details, deal_id, model_name)
                    #                             if create_attachment:
                    #                                 logger.info("Attachment created successfully: %s" % create_attachment.id)
                    #                             else:
                    #                                 logger.warning("Failed to create attachment for: %s" % attachment_details['name'])
                    #         else:
                    #             logger.warning("No attachments found in the response for hubspot_deal_id: %s", hubspot_deal_id)
                    #     else:
                    #         logger.warning("Received non-200 status code: %s for hubspot_deal_id: %s", response_get_associated_deal_attachment_detail.status_code, hubspot_deal_id)

                    # except json.JSONDecodeError:
                    #     logger.error("Failed to parse JSON response for hubspot_deal_id: %s", hubspot_deal_id)
                    # except Exception as e:
                    #     logger.error("An unexpected error occurred: %s", str(e))

                    odoo_modifiedDate = self.convert_time_to_unix_timestamp(crm_lead_id.write_date)
                    if self.env.context.get('from_skipped_deals'):
                        crm_lead_id.with_context({'from_hubspot': True}).write(vals)
                        self._cr.commit()
                        # hubspot_instance.modifiedDateForDeals = newdealsModifiedDate
                        hubspot_deal_id = vals['hubspot_id']
                        try:
                            response_get_associated_deal_attachment_detail = hubspot_instance._send_get_request(
                                f'/engagements/v1/engagements/associated/deal/{hubspot_deal_id}/paged')

                            json_response_get_associated_deal_attachment_detail = json.loads(
                                response_get_associated_deal_attachment_detail)
                            results = json_response_get_associated_deal_attachment_detail.get('results', [])

                            if results:
                                deal_id = self.env['crm.lead'].sudo().search(
                                    [('type', '=', 'opportunity'), ('hubspot_id', '=', hubspot_deal_id),
                                     ('hubspot_instance_id', '=', hubspot_instance.id)], limit=1)

                                model_id = self.env['ir.model']._get('crm.lead').id
                                model_name = 'crm.lead'

                                for result in results:
                                    attachments = result.get('attachments', [])
                                    for attachment in attachments:
                                        attachment_id = attachment.get('id')
                                        if attachment_id:
                                            attachment_details = self.get_attachment_by_id(attachment_id,
                                                                                           hubspot_instance)
                                            if attachment_details:
                                                create_attachment = self.create_attachment(attachment_details, deal_id,
                                                                                           model_name)
                                                if create_attachment:
                                                    logger.info(
                                                        "Attachment created successfully: %s" % create_attachment.id)
                                                else:
                                                    logger.warning(
                                                        "Failed to create attachment for: %s" % attachment_details[
                                                            'name'])
                            else:
                                logger.warning("No attachments found in the response for hubspot_deal_id: %s",
                                               hubspot_deal_id)


                        except json.JSONDecodeError:
                            logger.error("Failed to parse JSON response for hubspot_deal_id: %s", hubspot_deal_id)
                        except Exception as e:
                            logger.error("An unexpected error occurred: %s", str(e))

                        logger.info("Write into Existing Odoo Deals----------- " + str(crm_lead_id.hubspot_id))
                    elif int(newdealsModifiedDate) > int(odoo_modifiedDate):
                        crm_lead_id.with_context({'from_hubspot': True}).write(vals)
                        self._cr.commit()
                        # hubspot_instance.modifiedDateForDeals = newdealsModifiedDate
                        logger.info("Write into Existing Odoo Deals----------- " + str(crm_lead_id.hubspot_id))
                        hubspot_deal_id = vals['hubspot_id']
                        try:
                            response_get_associated_deal_attachment_detail = hubspot_instance._send_get_request(
                                f'/engagements/v1/engagements/associated/deal/{hubspot_deal_id}/paged')

                            json_response_get_associated_deal_attachment_detail = json.loads(
                                response_get_associated_deal_attachment_detail)
                            results = json_response_get_associated_deal_attachment_detail.get('results', [])

                            if results:
                                deal_id = self.env['crm.lead'].sudo().search(
                                    [('type', '=', 'opportunity'), ('hubspot_id', '=', hubspot_deal_id),
                                     ('hubspot_instance_id', '=', hubspot_instance.id)], limit=1)

                                model_id = self.env['ir.model']._get('crm.lead').id
                                model_name = 'crm.lead'

                                for result in results:
                                    attachments = result.get('attachments', [])
                                    for attachment in attachments:
                                        attachment_id = attachment.get('id')
                                        if attachment_id:
                                            attachment_details = self.get_attachment_by_id(attachment_id,
                                                                                           hubspot_instance)
                                            if attachment_details:
                                                create_attachment = self.create_attachment(attachment_details, deal_id,
                                                                                           model_name)
                                                if create_attachment:
                                                    logger.info(
                                                        "Attachment created successfully: %s" % create_attachment.id)
                                                else:
                                                    logger.warning(
                                                        "Failed to create attachment for: %s" % attachment_details[
                                                            'name'])
                            else:
                                logger.warning("No attachments found in the response for hubspot_deal_id: %s",
                                               hubspot_deal_id)


                        except json.JSONDecodeError:
                            logger.error("Failed to parse JSON response for hubspot_deal_id: %s", hubspot_deal_id)
                        except Exception as e:
                            logger.error("An unexpected error occurred: %s", str(e))
                        return crm_lead_id
                else:
                    if 'name' in vals:
                        crm_lead_exists = self.env['crm.lead'].sudo().search(
                            ['|', ('active', '=', True), ('active', '=', False), ('name', '=', vals['name']),
                             ('type', '=', 'opportunity'),
                             ('hubspot_id', '=', False), ('hubspot_instance_id', '=', False)], limit=1)
                        if crm_lead_exists:
                            if self.env.context.get('from_skipped_deals'):
                                vals['hubspot_instance_id'] = hubspot_instance.id
                                crm_lead_exists.with_context({'from_hubspot': True}).write(vals)
                                logger.info(
                                    "Write into Existing Odoo Deals name----------- " + str(crm_lead_exists.hubspot_id))
                                # hubspot_instance.modifiedDateForDeals = newdealsModifiedDate
                                hubspot_deal_id = vals['hubspot_id']
                                try:
                                    response_get_associated_deal_attachment_detail = hubspot_instance._send_get_request(
                                        f'/engagements/v1/engagements/associated/deal/{hubspot_deal_id}/paged')

                                    json_response_get_associated_deal_attachment_detail = json.loads(
                                        response_get_associated_deal_attachment_detail)
                                    results = json_response_get_associated_deal_attachment_detail.get('results', [])

                                    if results:
                                        deal_id = self.env['crm.lead'].sudo().search(
                                            [('type', '=', 'opportunity'), ('hubspot_id', '=', hubspot_deal_id),
                                             ('hubspot_instance_id', '=', hubspot_instance.id)], limit=1)

                                        model_id = self.env['ir.model']._get('crm.lead').id
                                        model_name = 'crm.lead'

                                        for result in results:
                                            attachments = result.get('attachments', [])
                                            for attachment in attachments:
                                                attachment_id = attachment.get('id')
                                                if attachment_id:
                                                    attachment_details = self.get_attachment_by_id(attachment_id,
                                                                                                   hubspot_instance)
                                                    if attachment_details:
                                                        create_attachment = self.create_attachment(attachment_details,
                                                                                                   deal_id, model_name)
                                                        if create_attachment:
                                                            logger.info(
                                                                "Attachment created successfully: %s" % create_attachment.id)
                                                        else:
                                                            logger.warning("Failed to create attachment for: %s" %
                                                                           attachment_details['name'])
                                    else:
                                        logger.warning("No attachments found in the response for hubspot_deal_id: %s",
                                                       hubspot_deal_id)


                                except json.JSONDecodeError:
                                    logger.error("Failed to parse JSON response for hubspot_deal_id: %s",
                                                 hubspot_deal_id)
                                except Exception as e:
                                    logger.error("An unexpected error occurred: %s", str(e))
                            elif not self.env.context.get('from_skipped_deals'):
                                vals['hubspot_instance_id'] = hubspot_instance.id
                                crm_lead_exists.with_context({'from_hubspot': True}).write(vals)
                                logger.info(
                                    "Write into Existing Odoo Deals name----------- " + str(crm_lead_exists.hubspot_id))
                                # hubspot_instance.modifiedDateForDeals = newdealsModifiedDate
                                hubspot_deal_id = vals['hubspot_id']
                                try:
                                    response_get_associated_deal_attachment_detail = hubspot_instance._send_get_request(
                                        f'/engagements/v1/engagements/associated/deal/{hubspot_deal_id}/paged')

                                    json_response_get_associated_deal_attachment_detail = json.loads(
                                        response_get_associated_deal_attachment_detail)
                                    results = json_response_get_associated_deal_attachment_detail.get('results', [])

                                    if results:
                                        deal_id = self.env['crm.lead'].sudo().search(
                                            [('type', '=', 'opportunity'), ('hubspot_id', '=', hubspot_deal_id),
                                             ('hubspot_instance_id', '=', hubspot_instance.id)], limit=1)

                                        model_id = self.env['ir.model']._get('crm.lead').id
                                        model_name = 'crm.lead'

                                        for result in results:
                                            attachments = result.get('attachments', [])
                                            for attachment in attachments:
                                                attachment_id = attachment.get('id')
                                                if attachment_id:
                                                    attachment_details = self.get_attachment_by_id(attachment_id,
                                                                                                   hubspot_instance)
                                                    if attachment_details:
                                                        create_attachment = self.create_attachment(attachment_details,
                                                                                                   deal_id, model_name)
                                                        if create_attachment:
                                                            logger.info(
                                                                "Attachment created successfully: %s" % create_attachment.id)
                                                        else:
                                                            logger.warning("Failed to create attachment for: %s" %
                                                                           attachment_details['name'])
                                    else:
                                        logger.warning("No attachments found in the response for hubspot_deal_id: %s",
                                                       hubspot_deal_id)

                                except json.JSONDecodeError:
                                    logger.error("Failed to parse JSON response for hubspot_deal_id: %s",
                                                 hubspot_deal_id)
                                except Exception as e:
                                    logger.error("An unexpected error occurred: %s", str(e))
                                return crm_lead_exists
                        else:
                            if self.env.context.get('from_skipped_deals'):
                                vals['hubspot_instance_id'] = hubspot_instance.id
                                crm_lead_id = self.with_context({'from_hubspot': True}).create(vals)
                                # hubspot_instance.modifiedDateForDeals = newdealsModifiedDate
                                logger.info("Created New Deals Into Odoo ----------- " + str(crm_lead_id.id))
                                hubspot_deal_id = vals['hubspot_id']
                                try:
                                    response_get_associated_deal_attachment_detail = hubspot_instance._send_get_request(
                                        f'/engagements/v1/engagements/associated/deal/{hubspot_deal_id}/paged')

                                    json_response_get_associated_deal_attachment_detail = json.loads(
                                        response_get_associated_deal_attachment_detail)

                                    results = json_response_get_associated_deal_attachment_detail.get('results', [])

                                    if results:
                                        deal_id = self.env['crm.lead'].sudo().search(
                                            [('type', '=', 'opportunity'), ('hubspot_id', '=', hubspot_deal_id),
                                             ('hubspot_instance_id', '=', hubspot_instance.id)], limit=1)

                                        model_id = self.env['ir.model']._get('crm.lead').id
                                        model_name = 'crm.lead'

                                        for result in results:
                                            attachments = result.get('attachments', [])
                                            for attachment in attachments:
                                                attachment_id = attachment.get('id')
                                                if attachment_id:
                                                    attachment_details = self.get_attachment_by_id(attachment_id,
                                                                                                   hubspot_instance)
                                                    if attachment_details:
                                                        create_attachment = self.create_attachment(attachment_details,
                                                                                                   deal_id, model_name)
                                                        if create_attachment:
                                                            logger.info(
                                                                "Attachment created successfully: %s" % create_attachment.id)
                                                        else:
                                                            logger.warning("Failed to create attachment for: %s" %
                                                                           attachment_details['name'])
                                    else:
                                        logger.warning("No attachments found in the response for hubspot_deal_id: %s",
                                                       hubspot_deal_id)


                                except json.JSONDecodeError:
                                    logger.error("Failed to parse JSON response for hubspot_deal_id: %s",
                                                 hubspot_deal_id)
                                except Exception as e:
                                    logger.error("An unexpected error occurred: %s", str(e))
                            elif not self.env.context.get('from_skipped_deals'):
                                vals['hubspot_instance_id'] = hubspot_instance.id
                                crm_lead_id = self.with_context({'from_hubspot': True}).create(vals)
                                # hubspot_instance.modifiedDateForDeals = newdealsModifiedDate
                                logger.info("Created New Deals Into Odoo ----------- " + str(crm_lead_id.id))
                                hubspot_deal_id = vals['hubspot_id']
                                try:
                                    response_get_associated_deal_attachment_detail = hubspot_instance._send_get_request(
                                        f'/engagements/v1/engagements/associated/deal/{hubspot_deal_id}/paged')

                                    json_response_get_associated_deal_attachment_detail = json.loads(
                                        response_get_associated_deal_attachment_detail)

                                    results = json_response_get_associated_deal_attachment_detail.get('results', [])

                                    if results:
                                        deal_id = self.env['crm.lead'].sudo().search(
                                            [('type', '=', 'opportunity'), ('hubspot_id', '=', hubspot_deal_id),
                                             ('hubspot_instance_id', '=', hubspot_instance.id)], limit=1)

                                        model_id = self.env['ir.model']._get('crm.lead').id
                                        model_name = 'crm.lead'

                                        for result in results:
                                            attachments = result.get('attachments', [])
                                            for attachment in attachments:
                                                attachment_id = attachment.get('id')
                                                if attachment_id:
                                                    attachment_details = self.get_attachment_by_id(attachment_id,
                                                                                                   hubspot_instance)
                                                    if attachment_details:
                                                        create_attachment = self.create_attachment(attachment_details,
                                                                                                   deal_id, model_name)
                                                        if create_attachment:
                                                            logger.info(
                                                                "Attachment created successfully: %s" % create_attachment.id)
                                                        else:
                                                            logger.warning("Failed to create attachment for: %s" %
                                                                           attachment_details['name'])
                                    else:
                                        logger.warning("No attachments found in the response for hubspot_deal_id: %s",
                                                       hubspot_deal_id)


                                except json.JSONDecodeError:
                                    logger.error("Failed to parse JSON response for hubspot_deal_id: %s",
                                                 hubspot_deal_id)
                                except Exception as e:
                                    logger.error("An unexpected error occurred: %s", str(e))
                                return crm_lead_id
        except Exception as e:
            error_message = 'Error while creating hubspot deals in odoo vals: %s\n Hubspot response %s' % (
                deals_dict, str(e))
            self.env['hubspot.logger'].create_log_message('Import Deals', error_message)
            logger.exception("Exception in Creating New Deals in Odoo :\n" + error_message)
            hubspot_instance._raise_user_error(e)
            
    def get_attachment_by_id(self, file_id, hubspot_instance):
        try:
            response_attachment_details = hubspot_instance._send_get_request('/files/v3/files/' + str(file_id) + '/signed-url')
            json_response_attachment_details = json.loads(response_attachment_details)
            return json_response_attachment_details
        except Exception as e:
            error_message = 'Error while getting attachment in odoo \nHubspot response %s' % (str(e))
            self.env['hubspot.logger'].create_log_message('Getting attachment details', error_message)
            logger.exception("Error in Getting attachement details From Hubspot------------>\n" + error_message)
            hubspot_instance._raise_user_error(e)
    
    @api.model
    def create_attachment(self, attachment_details, deal_id, model_name):
        url = attachment_details['url']
        file_data = None

        try:
            response_content = requests.get(url.strip()).content
            file_data = base64.b64encode(response_content).replace(b'\n', b'') if attachment_details['type'] == 'IMG' else base64.b64encode(response_content)
        except Exception as e:
            logger.exception("Error fetching or encoding file data: %s" % str(e))
            raise ValueError("Error fetching or encoding file data: %s" % str(e))

        if file_data:
            existing_attachment = self.env['ir.attachment'].search([
                ('res_model', '=', model_name),
                ('res_id', '=', deal_id.id),
                ('name', '=', attachment_details['name'],)
            ], limit=1)
            
            if not existing_attachment:
                try:
                    attachment_id = self.env['ir.attachment'].create({
                        'name':attachment_details['name'],
                        'type': 'binary',
                        'datas': file_data,
                        'res_model': model_name,
                        'res_id': deal_id.id,
                    })
                    return attachment_id
                except Exception as e:
                    logger.exception("Error creating attachment: %s" % str(e))
                    raise ValueError("Error creating attachment: %s" % str(e))
            else:
                return existing_attachment
        else:
            logger.error("Attachment type not supported or file data is None for attachment: %s" % attachment_details['name'])
            return None
            
        

    # @api.model
    # def createNewDealsInOdooFieldMapping(self, deals_info, hubspot_instance):
    #     deals_field_mapping = self.env['deals.field.mapping'].search([('hubspot_instance_id', '=', hubspot_instance.id)])
    #     vals = {}
    #     try:
    #         newDealsModifiedDate = 10000000.0
    #         for deals_info_dict in deals_info:
    #             for deals_field_mapping_id in deals_field_mapping:
    #                 if deals_field_mapping_id.hubspot_fields.technical_name in deals_info_dict['properties']:
    #                     if 'lastmodifieddate' in deals_info_dict['properties']:
    #                         if deals_info_dict['properties']['lastmodifieddate']['value']:
    #                             newDealsModifiedDate = int(deals_info_dict['properties']['lastmodifieddate']['value'])
    #                     if deals_field_mapping_id.hubspot_fields.field_type == 'date':
    #                         vals[deals_field_mapping_id.odoo_fields.name] = self.env['mail.activity'].convert_epoch_to_gmt_timestamp(
    #                             deals_info_dict['properties'][deals_field_mapping_id.hubspot_fields.technical_name]['timestamp'])
    #                     else:
    #                         vals[deals_field_mapping_id.odoo_fields.name] = deals_info_dict['properties'][deals_field_mapping_id.hubspot_fields.technical_name]['value']
    #             vals['type'] = 'lead'
    #             lead_id = self.search(
    #                 ['|', ('active', '=', True), ('active', '=', False), ('hubspot_id', '=', str(deals_info_dict['dealId'])), ('hubspot_instance_id', '=', hubspot_instance.id),
    #                  ('type', '=', 'lead')], limit=1)
    #             if lead_id and vals:
    #                 odoo_modifiedDate = self.convert_time_to_unix_timestamp(lead_id.write_date)
    #                 vals['hubspot_instance_id'] = hubspot_instance.id
    #                 lead_id.with_context({'from_hubspot': True}).write(vals)
    #                 logger.info("Write into Existing Odoo deals----------- " + str(lead_id.hubspot_id))
    #                 self._cr.commit()
    #                 return lead_id
    #             else:
    #                 deals_id = self.with_context({'from_hubspot': True}).create(vals)
    #                 hubspot_instance.modifiedDateForDeals = newDealsModifiedDate
    #                 logger.info("Created New Deals Into Odoo ----------- " + str(deals_id.id))
    #                 self._cr.commit()
    #                 return deals_id

    #     except Exception as e:
    #         error_message = 'Error while creating hubspot deals in odoo vals using field mapping: %s\n Hubspot response %s' % (
    #             deals_info, str(e))
    #         self.env['hubspot.logger'].create_log_message('Import Deals', error_message)
    #         logger.exception("Exception in Creating New Deals in Odoo :\n" + error_message)
    #         hubspot_instance._raise_user_error(e)

    @api.model
    def createNewDealsInOdooFieldMapping(self, deals_info, hubspot_instance):
        deals_field_mapping = self.env['deals.field.mapping'].search([('hubspot_instance_id', '=', hubspot_instance.id)])
        vals = {}
        try:
            newDealsModifiedDate = 10000000.0
            
            for deals_info_dict in deals_info:
                try:
                    for deals_field_mapping_id in deals_field_mapping:
                        try:
                            technical_name = deals_field_mapping_id.hubspot_fields.technical_name
                            if technical_name in deals_info_dict['properties']:
                                if 'lastmodifieddate' in deals_info_dict['properties']:
                                    if deals_info_dict['properties']['lastmodifieddate']['value']:
                                        newDealsModifiedDate = int(deals_info_dict['properties']['lastmodifieddate']['value'])

                                if deals_field_mapping_id.hubspot_fields.field_type == 'date':
                                    timestamp = deals_info_dict['properties'][technical_name]['timestamp']
                                    vals[deals_field_mapping_id.odoo_fields.name] = self.env['mail.activity'].convert_epoch_to_gmt_timestamp(timestamp)
                                else:
                                    vals[deals_field_mapping_id.odoo_fields.name] = deals_info_dict['properties'][technical_name].get('value', '')
                        except Exception as field_mapping_exception:
                            error_message = f"Error processing field mapping for {technical_name}: {str(field_mapping_exception)}"
                            self.env['hubspot.logger'].create_log_message('Import Deals', error_message)
                            logger.warning(error_message)

                    vals['type'] = 'lead'
                    lead_id = self.search(
                        ['|', ('active', '=', True), ('active', '=', False), 
                        ('hubspot_id', '=', str(deals_info_dict['dealId'])), 
                        ('hubspot_instance_id', '=', hubspot_instance.id), 
                        ('type', '=', 'opportunity')],
                        limit=1
                    )

                    if lead_id and vals:
                        try:
                            odoo_modifiedDate = self.convert_time_to_unix_timestamp(lead_id.write_date)
                            vals['hubspot_instance_id'] = hubspot_instance.id
                            lead_id.with_context({'from_hubspot': True}).write(vals)
                            logger.info(f"Updated existing Odoo deal with HubSpot ID {lead_id.hubspot_id}")
                            self.env.cr.commit()

                            return lead_id
                        except Exception as update_exception:
                            error_message = f"Error updating deal {deals_info_dict['dealId']} in Odoo: {str(update_exception)}"
                            self.env['hubspot.logger'].create_log_message('Import Deals', error_message)
                            logger.warning(error_message)
                    else:
                        try:
                            deals_id = self.with_context({'from_hubspot': True}).create(vals)
                            hubspot_instance.modifiedDateForDeals = newDealsModifiedDate
                            logger.info(f"Created new deal in Odoo with ID {deals_id.id}")
                            self.env.cr.commit()

                            return deals_id
                        except Exception as create_exception:
                            error_message = f"Error creating deal {deals_info_dict['dealId']} in Odoo: {str(create_exception)}"
                            self.env['hubspot.logger'].create_log_message('Import Deals', error_message)
                            logger.warning(error_message)

                except Exception as deal_processing_exception:
                    error_message = f"Error processing deal {deals_info_dict['dealId']} in HubSpot: {str(deal_processing_exception)}"
                    self.env['hubspot.logger'].create_log_message('Import Deals', error_message)
                    logger.exception("Exception while handling HubSpot deal import in Odoo:\n" + error_message)

        except Exception as e:
            error_message = f"Error while creating HubSpot deals in Odoo using field mapping: {deals_info}\n HubSpot response: {str(e)}"
            self.env['hubspot.logger'].create_log_message('Import Deals', error_message)
            logger.exception("Exception in Creating New Deals in Odoo:\n" + error_message)
            hubspot_instance._raise_user_error(e)

        logger.info('Deals imported or updated successfully in Odoo from custom field mapping')


    @api.model
    def _cron_export_deals_to_hubspot(self):
        hubspot_instance_obj = self.env['hubspot.instance'].search([('active', '=', True), ('hubspot_is_export_deals', '=', True)])
        for hubspot_instance in hubspot_instance_obj:
            self.export_deals_to_hubspot(hubspot_instance)

    @api.model
    def export_deals_to_hubspot(self, hubspot_instance):
        # Hubspot Information

        # crm_lead_ids = self.env['crm.lead'].search([('hubspot_id', '=', False), ('type', '=', 'opportunity')])
        crm_lead_ids = self.env['crm.lead'].search([('hubspot_id', '=', False)])
        if hubspot_instance.default_instance and hubspot_instance.active and hubspot_instance.hubspot_is_export_deals:
            for lead_id in crm_lead_ids:
                if not lead_id.hubspot_id:
                    lead_id.createNewDealsInHubspot(hubspot_instance)
                    deals_field_mapping = self.env['deals.field.mapping'].search([('hubspot_instance_id', '=', hubspot_instance.id)])
                    if len(deals_field_mapping):
                        lead_id.createNewDealsInHubspotFieldMapping(hubspot_instance, deals_field_mapping)

    def createNewDealsInHubspot(self, hubspot_instance):
        logger.info('Creating new leads in hubspot')
        print("\n\n\n=============createNewDealsInHubspot=======",self)
        for eachNewDeal in self:
            if eachNewDeal.type == 'lead':
                # create hubspot dictionary
                associatedVids = []
                associatedCompanyIds = []
                properties = []
                if eachNewDeal.name:
                    properties.append({'name': 'dealname', 'value': eachNewDeal.name})
                if eachNewDeal.hubspot_deal_stage:
                    if eachNewDeal.hubspot_deal_stage == 'Appointment scheduled':
                        properties.append({'name': 'dealstage', 'value': 'appointmentscheduled'})
                    if eachNewDeal.hubspot_deal_stage == 'Qualified to buy':
                        properties.append({'name': 'dealstage', 'value': 'qualifiedtobuy'})
                    if eachNewDeal.hubspot_deal_stage == 'Presentation scheduled':
                        properties.append({'name': 'dealstage', 'value': 'presentationscheduled'})
                    if eachNewDeal.hubspot_deal_stage == 'Decision maker bought-In':
                        properties.append({'name': 'dealstage', 'value': 'decisionmakerboughtin'})
                    if eachNewDeal.hubspot_deal_stage == 'Contract sent':
                        properties.append({'name': 'dealstage', 'value': 'contractsent'})
                    if eachNewDeal.hubspot_deal_stage == 'Closed won':
                        properties.append({'name': 'dealstage', 'value': 'closedwon'})
                else:
                    properties.append({'name': 'dealstage', 'value': 'appointmentscheduled'})
                if eachNewDeal.hubspot_deal_type:
                    if eachNewDeal.hubspot_deal_type == 'New Business':
                        properties.append({'name': 'dealtype', 'value': 'newbusiness'})
                    if eachNewDeal.hubspot_deal_type == 'Existing Business':
                        properties.append({'name': 'dealtype', 'value': 'existingbusiness'})
                else:
                    properties.append({'name': 'dealtype', 'value': 'newbusiness'})

                if eachNewDeal.expected_revenue:
                    properties.append({'name': 'amount', 'value': eachNewDeal.expected_revenue})
                if eachNewDeal.partner_id:
                    if eachNewDeal.partner_id.hubspot_id:
                        if eachNewDeal.partner_id.is_company:
                            associatedCompanyIds.append(eachNewDeal.partner_id.hubspot_id)

                        elif not eachNewDeal.partner_id.is_company:
                            associatedVids.append(eachNewDeal.partner_id.hubspot_id)
                # user (Owner) sync
                if eachNewDeal.user_id:
                    if eachNewDeal.user_id.hubspot_uid:
                        properties.append({'name': 'hubspot_owner_id', 'value': eachNewDeal.user_id.hubspot_uid})

                # NEW CODE
                print("\n\n\n=============hubspot_instance===================", hubspot_instance)
                # 5/0
                # deals_field_mapping = self.env['deals.field.mapping'].search(
                #     [('hubspot_instance_id', '=', hubspot_instance.id)])
                # if deals_field_mapping:
                #     for deals_field_mapping_id in deals_field_mapping:
                #         if deals_field_mapping_id.odoo_fields.name and deals_field_mapping_id.hubspot_fields.technical_name:
                #             deal_read_obj = eachNewDeal.read()[0]
                #             print("\n\n\n=============deal_read_obj===================",deal_read_obj)
                #             properties.append({
                #                 'property': deals_field_mapping_id.hubspot_fields.technical_name,
                #                 'value': deal_read_obj.get(deals_field_mapping_id.odoo_fields.name)
                #             })

                if properties:
                    try:
                        # try:
                        if associatedVids:
                            vals = {"associations": {"associatedVids": associatedVids}, 'properties': properties}
                            response_create_deals = hubspot_instance._send_post_request('/deals/v1/deal/', vals)
                            json_response_create_deals = json.loads(response_create_deals)

                            eachNewDeal.with_context({'from_hubspot': True}).hubspot_id = json_response_create_deals['dealId']
                            eachNewDeal.hubspot_instance_id = hubspot_instance.id
                            eachNewDeal.hubspot_deal_type = 'New Business'
                            eachNewDeal.hubspot_deal_stage = 'Appointment scheduled'
                        elif associatedCompanyIds:
                            vals = {"associations": {"associatedCompanyIds": associatedCompanyIds}, 'properties': properties}
                            response_create_deals = hubspot_instance._send_post_request('/deals/v1/deal/', vals)
                            json_response_create_deals = json.loads(response_create_deals)
                            eachNewDeal.with_context({'from_hubspot': True}).hubspot_id = json_response_create_deals['dealId']
                            eachNewDeal.hubspot_instance_id = hubspot_instance.id
                            eachNewDeal.hubspot_deal_type = 'New Business'
                            eachNewDeal.hubspot_deal_stage = 'Appointment scheduled'
                        else:
                            response_create_deals = hubspot_instance._send_post_request('/deals/v1/deal/', ({'properties': properties}))
                            json_response_create_deals = json.loads(response_create_deals)
                            eachNewDeal.with_context({'from_hubspot': True}).hubspot_id = json_response_create_deals['dealId']
                            eachNewDeal.hubspot_instance_id = hubspot_instance.id
                            eachNewDeal.hubspot_deal_type = 'New Business'
                            eachNewDeal.hubspot_deal_stage = 'Appointment scheduled'
                    except Exception as e_log:
                        error_message = 'Error while exporting odoo deals %d \n\n Odoo vals: %s\n Hubspot response %s' % (eachNewDeal.id, str(properties), str(e_log))
                        self.env['hubspot.logger'].create_log_message('Export Deals', error_message)
                        logger.exception("Exception in Hubspot Connection  :\n" + str(e_log))
                        hubspot_instance._raise_user_error(e_log)

                    message = 'Exported deals successfully'
                    self.env['hubspot.logger'].create_log_message('Export deals', message)
                    logger.info('Exported deals successfully...')

    def createNewDealsInHubspotFieldMapping(self, hubspot_instance, deals_field_mapping):
        properties = []
        odoo_field_list = []
        lead_list = []
        print("\n\n=============createNewDealsInHubspotFieldMapping=========",hubspot_instance)
        for deals_field_mapping_id in deals_field_mapping:
            if deals_field_mapping_id.odoo_fields.name and deals_field_mapping_id.hubspot_fields.technical_name:
                odoo_field_list.append(deals_field_mapping_id.odoo_fields.name)
                lead_read_obj = self.read()[0]
                if deals_field_mapping_id.odoo_fields.name in lead_read_obj.keys():
                    if lead_read_obj.values():
                        if lead_read_obj.get(deals_field_mapping_id.odoo_fields.name):
                            if deals_field_mapping_id.hubspot_fields.field_type == 'date':
                                format_date = self.convert_time_to_unix_timestamp(lead_read_obj.get(deals_field_mapping_id.odoo_fields.name))
                                properties.append({'name': deals_field_mapping_id.hubspot_fields.technical_name,
                                                   'value': format_date})
                            else:
                                properties.append(
                                    {'name': deals_field_mapping_id.hubspot_fields.technical_name, 'value': str(lead_read_obj.get(deals_field_mapping_id.odoo_fields.name))})
        if properties:
            try:
                if self.hubspot_id and self.hubspot_instance_id:
                    response_create_deals = hubspot_instance._send_put_request('/deals/v1/deal/' + str(self.hubspot_id), ({'properties': properties}))
                    json_response_create_deals = json.loads(response_create_deals)
                else:
                    response_create_deals = hubspot_instance._send_post_request('/deals/v1/deal/', ({'properties': properties}))
                    json_response_create_deals = json.loads(response_create_deals)
                    self.with_context(from_hubspot=True).hubspot_id = json_response_create_deals['dealId']
                    self.with_context(from_hubspot=True).hubspot_instance_id = hubspot_instance.id
            except Exception as e_log:
                error_message = 'Error while exporting odoo deals field mapping %d \n\n Odoo vals: %s\n Hubspot response %s' % (self.id, str(properties), str(e_log))
                self.env['hubspot.logger'].create_log_message('Export Deals', error_message)
                logger.exception("Exception in Hubspot Connection:\n" + str(e_log))
                hubspot_instance._raise_user_error(e_log)


    def UpdateDealsInHubspot(self, hubspot_instance):
        logger.info('Updating Deals in hubspot')
        for eachNewDeal in self:
            if eachNewDeal.type == 'lead':
                # create hubspot dictionary
                associatedVids = []
                associatedCompanyIds = []
                properties = []
                if eachNewDeal.name:
                    properties.append({'name': 'dealname', 'value': eachNewDeal.name})
                if eachNewDeal.hubspot_deal_stage:
                    if eachNewDeal.hubspot_deal_stage == 'Appointment scheduled':
                        properties.append({'name': 'dealstage', 'value': 'appointmentscheduled'})
                    if eachNewDeal.hubspot_deal_stage == 'Qualified to buy':
                        properties.append({'name': 'dealstage', 'value': 'qualifiedtobuy'})
                    if eachNewDeal.hubspot_deal_stage == 'Presentation scheduled':
                        properties.append({'name': 'dealstage', 'value': 'presentationscheduled'})
                    if eachNewDeal.hubspot_deal_stage == 'Decision maker bought-In':
                        properties.append({'name': 'dealstage', 'value': 'decisionmakerboughtin'})
                    if eachNewDeal.hubspot_deal_stage == 'Contract sent':
                        properties.append({'name': 'dealstage', 'value': 'contractsent'})
                    if eachNewDeal.hubspot_deal_stage == 'Closed won':
                        properties.append({'name': 'dealstage', 'value': 'closedwon'})
                else:
                    properties.append({'name': 'dealstage', 'value': 'appointmentscheduled'})
                if eachNewDeal.hubspot_deal_type:
                    if eachNewDeal.hubspot_deal_type == 'New Business':
                        properties.append({'name': 'dealtype', 'value': 'newbusiness'})
                    if eachNewDeal.hubspot_deal_type == 'Existing Business':
                        properties.append({'name': 'dealtype', 'value': 'existingbusiness'})
                else:
                    properties.append({'name': 'dealtype', 'value': 'newbusiness'})
                if eachNewDeal.expected_revenue:
                    properties.append({'name': 'amount', 'value': eachNewDeal.expected_revenue})
                if eachNewDeal.partner_id:
                    if eachNewDeal.partner_id.hubspot_id:
                        if eachNewDeal.partner_id.is_company:
                            associatedCompanyIds.append(eachNewDeal.partner_id.hubspot_id)
                        elif not eachNewDeal.partner_id.is_company:
                            associatedVids.append(eachNewDeal.partner_id.hubspot_id)
                # user (Owner) sync
                if eachNewDeal.user_id:
                    if not eachNewDeal.user_id.hubspot_uid:
                        logger.warning("Odoo User Not Available In Hubspot")
                        self.env['crm.lead'].syncAllUsers(eachNewDeal.hubspot_instance_id)
                    if eachNewDeal.user_id.hubspot_uid:
                        properties.append({'name': 'hubspot_owner_id', 'value': eachNewDeal.user_id.hubspot_uid})
                else:
                    properties.append({'property': 'hubspot_owner_id', 'value': ''})
                properties_vals = {'properties': properties}
                if properties:
                    try:
                        if associatedVids:
                            vals = {"associations": {"associatedVids": associatedVids}, 'properties': properties}
                            response = hubspot_instance._send_put_request('/deals/v1/deal/' + str(eachNewDeal.hubspot_id), vals)
                            parsed_resp = json.loads(response)
                            eachNewDeal.with_context({'from_hubspot': True}).hubspot_id = parsed_resp['dealId']
                        elif associatedCompanyIds:
                            vals = {"associations": {"associatedCompanyIds": associatedCompanyIds}, 'properties': properties}
                            response = hubspot_instance._send_put_request('/deals/v1/deal/' + str(eachNewDeal.hubspot_id), vals)
                            parsed_resp = json.loads(response)
                            eachNewDeal.with_context({'from_hubspot': True}).hubspot_id = parsed_resp['dealId']
                        else:
                            response = hubspot_instance._send_put_request('/deals/v1/deal/' + str(eachNewDeal.hubspot_id), properties_vals)
                            parsed_resp = json.loads(response)
                            eachNewDeal.with_context({'from_hubspot': True}).hubspot_id = parsed_resp['dealId']
                    except Exception as e_log:
                        error_message = 'Error while exporting odoo deals %d \n\n Odoo vals: %s\n Hubspot response %s' % (eachNewDeal.id, str(properties), str(e_log))
                        self.env['hubspot.logger'].create_log_message('Export Deals', error_message)
                        logger.exception("Exception in Hubspot Connection  :\n" + str(e_log))
                        hubspot_instance._raise_user_error(e_log)

        logger.info('Completed Updating deals in hubspot')

    def UpdateDealsInHubspotFieldMapping(self, deals_field_mapping, hubspot_instance):
        properties = []
        for eachNewDeal in self:
            for deals_field_mapping_id in deals_field_mapping:
                if deals_field_mapping_id.odoo_fields.name and deals_field_mapping_id.hubspot_fields.technical_name:
                    lead_read_obj = self.read()[0]
                    if deals_field_mapping_id.odoo_fields.name in lead_read_obj.keys():
                        if lead_read_obj.values():
                            if lead_read_obj.get(deals_field_mapping_id.odoo_fields.name):
                                if deals_field_mapping_id.hubspot_fields.field_type == 'date':
                                    format_date = self.convert_time_to_unix_timestamp(lead_read_obj.get(deals_field_mapping_id.odoo_fields.name))
                                    properties.append(
                                        {'name': deals_field_mapping_id.hubspot_fields.technical_name,
                                         'value': format_date})
                                else:
                                    properties.append(
                                        {'name': deals_field_mapping_id.hubspot_fields.technical_name,
                                         'value': str(lead_read_obj.get(deals_field_mapping_id.odoo_fields.name))})
            if properties:
                try:
                    hubspot_instance._send_put_request('/deals/v1/deal/' + str(eachNewDeal.hubspot_id), ({'properties': properties}))
                    eachNewDeal.with_context({'from_hubspot': True})
                    logger.info('Completed updating deals in hubspot with custom field mapping')
                except Exception as e_log:
                    error_message = 'Error while exporting odoo deals with field mapping %d \n\n Odoo vals: %s\n Hubspot response %s' % (
                    eachNewDeal.id, str(properties), str(e_log))
                    self.env['hubspot.logger'].create_log_message('Export Deals', error_message)
                    logger.exception("Exception in Hubspot Connection  :\n" + str(e_log))
                    hubspot_instance._raise_user_error(e_log)

    def syncAllUsers(self, hubspot_instance):
        try:
            logger.info('Getting All Users from HubSpot')

            partner_model = self.env['res.partner']
            allPartners = partner_model.search([
                ('hubspot_id', '!=', False),
                ('hubspot_instance_id', '=', hubspot_instance.id)
            ])
            PartnerHubspotIds = allPartners.mapped('hubspot_id')

            response_get_all_users = hubspot_instance._send_get_request('/crm/v3/owners/')
            json_response_all_contacts = json.loads(response_get_all_users)

            logger.info("HubSpot Owners Response: %s" % json_response_all_contacts)

            for owner in json_response_all_contacts.get('results', []):
                try:
                    owner_id = str(owner['id'])
                    partner_dict = {
                        'hubspot_id': owner_id,
                        'hubspot_instance_id': hubspot_instance.id
                    }

                    if owner.get('email'):
                        partner_dict['email'] = owner['email']

                    
                    name_parts = []
                    if owner.get('firstName'):
                        name_parts.append(owner['firstName'])
                    if owner.get('lastName'):
                        name_parts.append(owner['lastName'])

                    if name_parts:
                        partner_dict['name'] = ' '.join(name_parts)
                    elif owner.get('email'):
                        partner_dict['name'] = owner['email']

                    hubspot_modifiedDate = self.convert_time_to_unix_timestamp(owner.get('updatedAt'))

                    if owner_id in PartnerHubspotIds:
                        existing_partner = partner_model.search([
                            ('hubspot_id', '=', owner_id),
                            ('hubspot_instance_id', '=', hubspot_instance.id)
                        ], limit=1)

                        odoo_modifiedDate = self.convert_time_to_unix_timestamp(existing_partner.write_date)

                        if hubspot_modifiedDate > odoo_modifiedDate:
                            existing_partner.with_context({'from_hubspot': True}).write(partner_dict)
                            self.env.cr.commit()

                    else:
                        # Search by email if not matched by hubspot_id
                        existing_partner = partner_model.search([
                            ('email', '=', owner.get('email'))
                        ], limit=1)

                        if existing_partner:
                            existing_partner.with_context({'from_hubspot': True}).write(partner_dict)
                            self.env.cr.commit()
                        else:
                            # Avoid duplicate email errors
                            email = owner.get('email') or ''
                            if email and partner_model.search([('email', '=', email)], limit=1):
                                email = email.split('@')[0] + str(random.randint(100, 999)) + '@temp.email'
                                partner_dict['email'] = email

                            new_partner = partner_model.with_context({'from_hubspot': True}).create(partner_dict)
                            logger.info("Partner created in Odoo: %s" % new_partner)
                            self.env.cr.commit()

                except Exception as ex:
                    error_message = 'Error while syncing user: %s\nException: %s' % (owner, str(ex))
                    self.env['hubspot.logger'].create_log_message('Import Users', error_message)
                    logger.exception("Exception syncing a user: %s" % error_message)
                    hubspot_instance._raise_user_error(ex)

            message = 'Done Syncing Users'
            self.env['hubspot.logger'].create_log_message('Import Users', message)
            logger.info(message)

        except Exception as ex:
            error_message = 'Error while getting users from HubSpot: %s' % str(ex)
            self.env['hubspot.logger'].create_log_message('Import Users', error_message)
            logger.exception("Critical error in syncAllUsers: %s" % error_message)
            hubspot_instance._raise_user_error(ex)



class CRMStage(models.Model):
    _inherit = "crm.stage"

    hubspot_stage_id = fields.Char("HubSpot Stage ID", copy=False, index=True)

    def import_hubspot_stages(self):
        """Import HubSpot Deal Stages into Odoo CRM Stages"""
        logger.info("Importing HubSpot deal stages into Odoo CRM...")

        # API URL
        pipeline_id = "default"  # Can be changed dynamically if you manage multiple pipelines
        url = f"/crm/v3/pipelines/deals/{pipeline_id}/stages"

        try:
            # Use your HubSpot instance's send request
            instance = self.env['hubspot.instance'].search([], limit=1)
            if not instance:
                raise UserError(_("No HubSpot instance found. Please configure one first."))

            response_text = instance._send_get_request(url)
            if not response_text:
                raise UserError(_("No response received from HubSpot."))

            response = json.loads(response_text)
            stages = response.get("results", [])

            if not stages:
                raise UserError(_("No deal stages found in HubSpot."))

            created, updated = 0, 0
            CrmStage = self.env["crm.stage"]

            for stage in stages:
                stage_id = stage.get("id")
                label = stage.get("label")
                order = stage.get("displayOrder", 0)
                probability = float(stage.get("metadata", {}).get("probability", 0.0) or 0.0)

                existing_stage = CrmStage.search([("hubspot_stage_id", "=", stage_id)], limit=1)

                vals = {
                    "name": label,
                    "sequence": order,
                    # "probability": probability * 100,
                    "hubspot_stage_id": stage_id,
                }

                if existing_stage:
                    existing_stage.write(vals)
                    updated += 1
                else:
                    CrmStage.create(vals)
                    created += 1

            message = f"✅ HubSpot Deal Stages Imported: {created} created, {updated} updated."
            logger.info(message)
            return instance.sendMessage(message)

        except Exception as e:
            logger.error(f"Error while importing HubSpot deal stages: {e}", exc_info=True)
            raise UserError(_("Failed to import HubSpot deal stages: %s") % e)


