import logging
import datetime
import time
import json
from odoo import api, fields, models, _

logger = logging.getLogger(__name__)
from odoo.tools import config
config['limit_time_real'] = 10000000


class CalendarEvent(models.Model):
    _inherit = "calendar.event"

    hubspot_id = fields.Char('Hubspot Id', store=True, readonly=True, copy=False)
    hubspot_instance_id = fields.Many2one('hubspot.instance', 'Hubspot Instance Name', help="Hubspot Instance Name",
                                          readonly=True, copy=False)
    
    
    
    

    def convert_epoch_to_gmt_timestamp(self, hubspot_date):
        modified_date = int(str(hubspot_date)[:10])
        formatted_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(modified_date))
        date_time_obj = datetime.datetime.strptime(formatted_time, '%Y-%m-%d %H:%M:%S')
        # dt = False
        # if date_time_obj:
        #     timezone = pytz.timezone(self.env['res.users'].
        #                              sudo().browse([int(2)]).tz or 'UTC')
        # dt = pytz.UTC.localize(date_time_obj)
        # dt = dt.astimezone(timezone)
        # dt = ustr(dt).split('+')[0]
        return date_time_obj

    def write(self, vals):
        '''Update Contact or company details in hubspot on change of details in odoo'''
        res = super(CalendarEvent, self).write(vals)
        if not self.env.context.get('from_hubspot', False):
            for record in self:
                if record.hubspot_id and record.hubspot_instance_id:
                    instance = record.hubspot_instance_id
                    if instance.active and instance.hubspot_app_key:
                        try:
                            if instance.hubspot_is_export_log_meeting:
                                record.UpdateMeetingInHubspot(instance)
                        except Exception as e_log:
                            error_message = 'Error while updating meetings from odoo %d \n\n Odoo vals: %s\n Hubspot response %s' % (
                                record.id, str(vals), str(e_log))
                            self.env['hubspot.logger'].create_log_message('Export Meeting', error_message)
                            logger.exception("Exception in Export Meeting  :\n" + str(e_log))
                            instance._raise_user_error(e_log)

        else:
            logger.info(
                'Error in Synchronization1!\nHubspot API Key and App Name need to be specified for synchronization of data with Odoo.')
        return res

    @api.model
    def _cron_import_meeting_from_hubspot(self):
        hubspot_instance_obj = self.env['hubspot.instance'].search([('active', '=', True),('hubspot_is_import_log_meeting', '=', True)])
        for hubspot_instance in hubspot_instance_obj:
            self.import_log_meeting_from_hubspot(hubspot_instance)

    def import_log_meeting_from_hubspot(self, hubspot_instance):
        modifiedDateForMeeting = float(hubspot_instance.modifiedDateForlogmeeting or 0)
        all_log_meeting = float(hubspot_instance.all_log_meeting or 0)
        if hubspot_instance.hubspot_is_import_log_meeting and hubspot_instance.active: 
            logger.info('Getting All log meeting from hubspot---------------------------')
            try:
                has_more = True
                offset = 0
                while has_more:
                    log_meeting_ids = []
                    record_limit = 90
                    response_get_all_log_meeting = hubspot_instance._send_get_request('/engagements/v1/engagements/paged?offset=' + str(offset) + '&count=' + str(record_limit))
                    json_response_get_all_log_meeting = json.loads(response_get_all_log_meeting)
                    has_more = json_response_get_all_log_meeting['hasMore']
                    offset = json_response_get_all_log_meeting['offset']
                    for log_meeting_id in json_response_get_all_log_meeting['results']:
                        if log_meeting_id['engagement']['id'] and log_meeting_id['engagement']['type'] == 'MEETING':
                            log_meeting_ids.append(log_meeting_id['engagement']['id'])
                    if log_meeting_ids:
                        self.get_meeting_details_and_create(log_meeting_ids, hubspot_instance)
                    hubspot_instance.all_log_meeting = True
                message = 'Completed Getting All Log meeting from hubspot'
                self.env['hubspot.logger'].create_log_message('Import Log Meeting', message)
                logger.info('Completed Getting All Log Meeting from hubspot------------------------------------------------------')
            except Exception as e:
                error_message = 'Error while getting meeting in odoo \nHubspot response %s' % (str(e))
                self.env['hubspot.logger'].create_log_message('Import Log Meeting', error_message)
                logger.exception("Error in Getting All Log Meeting From Hubspot------------>\n" + error_message)
                hubspot_instance._raise_user_error(e)

        else:
            logger.info('Getting modified log meeting from hubspot-------------------')
            try:
                updatedLogMeetingList = []
                has_more = True
                offset = 0
                while has_more:
                    updated_log_meeting_ids = []
                    record_limit = 90
                    response_get_recently_modified_log_meetings = hubspot_instance._send_get_request(
                        '/engagements/v1/engagements/recent/modified?offset=' + str(offset) + '&count=' + str(record_limit))
                    json_recent_update_log_meetings_json_response = json.loads(response_get_recently_modified_log_meetings)
                    record_limit += 1
                    offset = json_recent_update_log_meetings_json_response['offset']
                    has_more = json_recent_update_log_meetings_json_response['hasMore']
                    for logMeetingId in json_recent_update_log_meetings_json_response['results']:
                        if logMeetingId['engagement']['id'] and logMeetingId['engagement']['type'] == 'MEETING':
                            if (int(logMeetingId['engagement']['lastUpdated'])) <= int(modifiedDateForMeeting):
                                break  # Skip Not recently updated activity
                            elif (int(logMeetingId.get('engagement')['lastUpdated'])) > int(modifiedDateForMeeting):
                                updated_log_meeting_ids.append(logMeetingId['engagement']['id'])
                                updated_log_meeting_ids.reverse()
                    if hubspot_instance.active  and updated_log_meeting_ids and hubspot_instance.hubspot_is_import_log_meeting:
                        self.get_meeting_details_and_create(updated_log_meeting_ids, hubspot_instance)
                    else:
                        break
                message = 'Completed Getting All Log Meeting from hubspot'
                self.env['hubspot.logger'].create_log_message('Import Log Meeting', message)
                logger.info(
                    'Completed Getting modified log meeting from hubspot------------------------------------------------------')
            except Exception as e:
                error_message = 'Error while getting log meeting in odoo \nHubspot response %s' % (str(e))
                self.env['hubspot.logger'].create_log_message('Import Log Meeting', error_message)
                logger.exception("Error in getModifiedLogMeetingFromHubspot------------>\n" + str(e))
                hubspot_instance._raise_user_error(e)

    def get_meeting_details_and_create(self, log_meeting_ids, hubspot_instance):
        for log_meeting_id in log_meeting_ids:
            meeting_info = []
            try:
                response_get_log_meeting_by_id = hubspot_instance._send_get_request('/engagements/v1/engagements/' + str(log_meeting_id))
                json_response_get_log_meeting_by_id = json.loads(response_get_log_meeting_by_id)

                logger.info('Get Log Meeting details')
                if json_response_get_log_meeting_by_id['engagement']['type'] == 'MEETING':
                    meeting_info.append(json_response_get_log_meeting_by_id)
                    self.createNewMeetingInOdoo(meeting_info, hubspot_instance)
                    self.env.cr.commit()

            except Exception as e:
                error_message = 'Error while importing hubspot meeting in odoo Id: %s\n Hubspot response %s' % (
                    log_meeting_id, str(e))
                self.env['hubspot.logger'].create_log_message('Import Meeting', error_message)
                logger.exception("Exception In getting meeting info from Hubspot : \n" + error_message)
                hubspot_instance._raise_user_error(e)

    @api.model
    def createNewMeetingInOdoo(self, meeting_dict, hubspot_instance):
        try:
            newMeetingModifiedDate = 10000000.0
            properties = []
            event_dict = {}
            partner_list = []
            calendar_event_obj = self.env['calendar.event']
            res_partner_obj = self.env['res.partner']
            for meeting_dict_details in meeting_dict:
                if 'contactIds' in meeting_dict_details['associations']:
                    for hubspot_contact_id in meeting_dict_details['associations']['contactIds']:
                        res_partner_id = self.env['res.partner'].sudo().search(
                            [('is_company', '=', False), ('hubspot_id', '=', hubspot_contact_id), ('hubspot_instance_id', '=', hubspot_instance.id)],limit=1)

                        if res_partner_id:
                            partner_list.append(res_partner_id.id)
                if 'companyIds' in meeting_dict_details['associations']:
                    for hubspot_company_id in meeting_dict_details['associations']['companyIds']:
                        res_partner_company_id = self.env['res.partner'].sudo().search(
                            [('is_company', '=', True), ('hubspot_id', '=', hubspot_company_id), ('hubspot_instance_id', '=', hubspot_instance.id)],limit=1)
                        if res_partner_company_id:
                            partner_list.append(res_partner_company_id.id)
                if 'dealIds' in meeting_dict_details['associations']:
                    # for hubspot_deal_id in meeting_dict_details['associations']['dealIds']:
                    if len(meeting_dict_details['associations']['dealIds']) > 0:
                        lead_id = self.env['crm.lead'].sudo().search(
                            [('hubspot_id', '=', meeting_dict_details['associations']['dealIds'][0]), ('hubspot_instance_id', '=', hubspot_instance.id)],limit=1)
                        if lead_id:
                            event_dict['opportunity_id'] = lead_id.id
                if 'lastUpdated' in meeting_dict_details['engagement']:
                    if meeting_dict_details['engagement']['lastUpdated']:
                        newMeetingModifiedDate = int(meeting_dict_details['engagement']['lastUpdated'])
                if 'metadata' in meeting_dict_details:
                    if 'title' in meeting_dict_details['metadata']:
                        event_dict['name'] = meeting_dict_details['metadata']['title']
                    elif 'body' in meeting_dict_details['metadata']:
                        if 'bodyPreview' in meeting_dict_details['engagement']:
                            event_dict['name'] = meeting_dict_details['engagement']['bodyPreview']
                if 'ownerId' in meeting_dict_details['engagement']:
                    user_id = self.env['res.partner'].search(
                        [('hubspot_id', '=', meeting_dict_details['engagement']['ownerId']), ('hubspot_instance_id', '=', hubspot_instance.id)], limit=1)
                    # if not user_id:
                    #     get_user = res_partner_obj.getOwnerDetailsFromHubspot(meeting_dict_details['engagement']['ownerId'], hubspot_instance)
                    #     if get_user:
                    #         event_dict['user_id'] = get_user.id
                    # else:
                    #     event_dict['user_id'] = user_id.id
                if 'id' in meeting_dict_details['engagement']:
                    event_dict['hubspot_id'] = meeting_dict_details['engagement']['id']
                if 'timestamp' in meeting_dict_details['engagement']:
                    event_dict['start'] = self.convert_epoch_to_gmt_timestamp(
                        meeting_dict_details['engagement']['timestamp'])
                if 'startTime' in meeting_dict_details['metadata']:
                    event_dict['start'] = self.convert_epoch_to_gmt_timestamp(
                        meeting_dict_details['metadata']['startTime'])
                if 'endTime' in meeting_dict_details['metadata']:
                    event_dict['stop'] = self.convert_epoch_to_gmt_timestamp(
                        meeting_dict_details['metadata']['endTime'])
                    event_dict['stop'] = self.convert_epoch_to_gmt_timestamp(
                        meeting_dict_details['metadata']['endTime'])
                calendar_event_id = calendar_event_obj.sudo().search(
                    [('hubspot_id', '=', meeting_dict_details['engagement']['id']), ('hubspot_instance_id', '=', hubspot_instance.id)],limit=1)
                if not calendar_event_id:
                    event_dict['hubspot_instance_id'] = hubspot_instance.id
                    event_dict['partner_ids'] = [(6, 0, partner_list)]
                    event_record = self.with_context({'from_hubspot': True}).create(event_dict)
                    hubspot_instance.modifiedDateForlogmeeting = newMeetingModifiedDate
                    logger.info("Created New calendar event Into Odoo ----------- " + str(event_record.id))
                    self.env.cr.commit()

                    mail_message_obj = self.env['mail.message']
                elif calendar_event_id:
                    event_dict['partner_ids'] = [(6, 0, partner_list)]
                    odoo_modifiedDate = self.env['mail.activity'].convert_time_to_unix_timestamp(calendar_event_id.write_date)
                    if int(newMeetingModifiedDate) > int(odoo_modifiedDate):
                        calendar_event_id.with_context({'from_hubspot': True}).write(event_dict)
                        hubspot_instance.modifiedDateForlogmeeting = newMeetingModifiedDate
                        logger.info("Write into Existing Odoo calendar event----------- " + str(calendar_event_id.hubspot_id))
                        self.env.cr.commit()

        except Exception as e:
            error_message = 'Error while creating hubspot meeting in odoo vals: %s\n Hubspot response %s' % (
                meeting_dict, str(e))
            self.env['hubspot.logger'].create_log_message('Import Meeting', error_message)
            logger.exception("Exception in Creating New Meeting in Odoo :\n" + error_message)
            hubspot_instance._raise_user_error(e)

    def _cron_export_meeting_to_hubspot(self):
        hubspot_instance_obj = self.env['hubspot.instance'].search([('active', '=', True), ('hubspot_is_export_log_meeting', '=', True)])
        for hubspot_instance in hubspot_instance_obj:
            self.export_log_meeting_to_hubspot(hubspot_instance)

    @api.model
    def export_log_meeting_to_hubspot(self, hubspot_instance):
        # Hubspot Information
        calendar_event_ids = self.env['calendar.event'].search([('hubspot_id', '=', False)])
        if hubspot_instance.default_instance and hubspot_instance.active  and hubspot_instance.hubspot_is_export_log_meeting:
            for calendar_event_id in calendar_event_ids:
                if not calendar_event_id.hubspot_id:
                    calendar_event_id.createNewMeetingInHubspot(hubspot_instance)

    def createNewMeetingInHubspot(self, hubspot_instance):
        for eachNewMeeting in self:
            # create hubspot dictionary
            properties = {}
            metadata_dict = {}
            engagement_dict = {}
            associations_list = []
            partner_list = []
            associations_dict = {}
            partner_company_list = []
            deals_list = []
            for partner_id in eachNewMeeting.partner_ids:
                if not partner_id.is_company and partner_id.hubspot_id and partner_id.hubspot_instance_id.id == hubspot_instance.id:
                    partner_list.append(int(partner_id.hubspot_id))
                elif partner_id.is_company and partner_id.hubspot_id and partner_id.hubspot_instance_id.id == hubspot_instance.id:
                    partner_company_list.append(int(partner_id.hubspot_id))
            if partner_list:
                associations_dict['contactIds'] = partner_list
            if partner_company_list:
                associations_dict['companyIds'] = partner_company_list
            if eachNewMeeting.opportunity_id and eachNewMeeting.opportunity_id.type == 'lead' and eachNewMeeting.opportunity_id.hubspot_id and eachNewMeeting.opportunity_id.hubspot_instance_id.id == hubspot_instance.id:
                deals_list.append(eachNewMeeting.opportunity_id.hubspot_id)
            if deals_list:
                associations_dict['dealIds'] = deals_list
            if eachNewMeeting.name:
                metadata_dict['title'] = eachNewMeeting.name
                engagement_dict['bodyPreview'] = eachNewMeeting.name
            if eachNewMeeting.start:
                metadata_dict['startTime'] = self.env['mail.activity'].convert_time_to_unix_timestamp(eachNewMeeting.start)
            if eachNewMeeting.stop:
                metadata_dict['endTime'] = self.env['mail.activity'].convert_time_to_unix_timestamp(eachNewMeeting.stop)
            account_details = self.env['mail.activity'].get_portal_hubspot_account_details(hubspot_instance)
            if account_details:
                engagement_dict['portalId'] = account_details['portalId']
            engagement_dict['type'] = 'MEETING'
            properties = {"engagement": engagement_dict, 'associations': associations_dict, 'metadata': metadata_dict}
            if properties:
                try:
                    response = hubspot_instance._send_post_request('/engagements/v1/engagements', properties)
                    json_response = json.loads(response)
                    eachNewMeeting.with_context({'from_hubspot': True}).hubspot_id = json_response['engagement']['id']
                    eachNewMeeting.with_context({'from_hubspot': True}).hubspot_instance_id = hubspot_instance.id
                except Exception as e_log:
                    error_message = 'Error while exporting odoo meeting %d \n\n Odoo vals: %s\n Hubspot response %s' % (eachNewMeeting.id, str(properties), str(e_log))
                    self.env['hubspot.logger'].create_log_message('Export Meeting', error_message)
                    logger.exception("Exception in Hubspot Connection  :\n" + str(e_log))
                    hubspot_instance._raise_user_error(e_log)

        message = 'Exported Meeting successfully'
        self.env['hubspot.logger'].create_log_message('Export Meeting', message)
        logger.info('Exported Meeting successfully...')

    def UpdateMeetingInHubspot(self, hubspot_instance):
        for eachNewMeeting in self:
            # create hubspot dictionary
            properties = {}
            metadata_dict = {}
            engagement_dict = {}
            associations_list = []
            partner_list = []
            associations_dict = {}
            for partner_id in eachNewMeeting.partner_ids:
                if not partner_id.is_company and partner_id.hubspot_id:
                    partner_list.append(int(partner_id.hubspot_id))
            if partner_list:
                associations_dict['contactIds'] = partner_list
            if eachNewMeeting.name:
                metadata_dict['title'] = eachNewMeeting.name
                engagement_dict['bodyPreview'] = eachNewMeeting.name
            if eachNewMeeting.start:
                metadata_dict['startTime'] = self.env['mail.activity'].convert_time_to_unix_timestamp(eachNewMeeting.start)
            if eachNewMeeting.stop:
                metadata_dict['endTime'] = self.env['mail.activity'].convert_time_to_unix_timestamp(eachNewMeeting.stop)
            account_details = self.env['mail.activity'].get_portal_hubspot_account_details(hubspot_instance)
            if account_details:
                engagement_dict['portalId'] = account_details['portalId']
            engagement_dict['type'] = 'MEETING'
            properties = {"engagement": engagement_dict, 'associations': associations_dict, 'metadata': metadata_dict}
            if properties:
                try:
                    response = hubspot_instance._send_patch_request('/engagements/v1/engagements/' + eachNewMeeting.hubspot_id, properties)
                    json_response = json.loads(response)
                    eachNewMeeting.with_context({'from_hubspot': True}).hubspot_id = json_response['engagement']['id']
                    if not eachNewMeeting.hubspot_instance_id and eachNewMeeting.hubspot_instance_id == hubspot_instance.id:
                        eachNewMeeting.hubspot_instance_id = hubspot_instance.id
                except Exception as e_log:
                    error_message = 'Error while exporting odoo meeting %d \n\n Odoo vals: %s\n Hubspot response %s' % (eachNewMeeting.id, str(properties), str(e_log))
                    self.env['hubspot.logger'].create_log_message('Export Meeting', error_message)
                    logger.exception("Exception in Hubspot Connection  :\n" + str(e_log))
                    hubspot_instance._raise_user_error(e_log)

        logger.info('Completed Updating Meeting in hubspot')
