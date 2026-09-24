import logging
import datetime
import json
from datetime import timezone
from odoo import api, fields, models, _
logger = logging.getLogger(__name__)
from odoo.tools import config
config['limit_time_real'] = 10000000


class MailActivity(models.Model):
    _inherit = "mail.activity"

    hubspot_id = fields.Char('Hubspot Id', store=True, readonly=True, copy=False)
    hubspot_instance_id = fields.Many2one('hubspot.instance', 'Hubspot Instance Name', help="Hubspot Instance Name",
                                          readonly=True, copy=False)
    hubspot_created_date = fields.Datetime(
        string="HubSpot Created Date",
        help="The date this record was created in HubSpot"
    )

    hubspot_assigned_user_id = fields.Many2one('res.partner', "Hubspot Assigned User")


    # hubspot_write_flag = fields.Boolean()

    # def unlink(self):
    #     '''Delete contact in hubspot on delete of contact or company in odoo'''
    #     for record in self:
    #         if record.hubspot_instance_id and record.hubspot_instance_id.active:
    #             record.deleteFromHubspot(record.hubspot_instance_id)
    #             record._cr.commit()
    #     return super(MailActivity, self).unlink()
    #
    # def deleteFromHubspot(self, hubspot_instance_id):
    #     logger.info('Delete from hubspot')
    #     try:
    #         with PortalConnection(APIKey(hubspot_instance_id.hubspot_app_key), hubspot_instance_id.name) as connection:
    #             headers = {}
    #             for each in self:
    #                 response = connection.send_delete_request('/engagements/v1/engagements/' + str(each.hubspot_id)+ '?hapikey='+hubspot_instance_id.hubspot_app_key)
    #     except Exception as e:
    #         error_message = 'Error while deleting Task in hubspot \nHubspot response %s' % (str(e))
    #         self.env['hubspot.logger'].create_log_message('Delete Task', error_message)
    #         logger.exception("Error in deleted Task From Hubspot------------>\n" + str(e))
    #         logger.info('Completed Delete from hubspot')

    def write(self, vals):
        res = super(MailActivity, self).write(vals)
        # hubspot_write_flag = False
        for record in self:
            if record.env.context.get('from_hubspot') is True:
                return res
            else:
                instance = None
                if record.hubspot_id and record.hubspot_instance_id and record.hubspot_instance_id.active:
                    instance = record.hubspot_instance_id
                    activity_ids = self.search([('hubspot_id', '=', self.hubspot_id), ('hubspot_instance_id', '=', instance.id)])
                    if activity_ids:
                        for activity_id in activity_ids:
                            '''If record have multiple activities & same hubspot ids'''
                            res = super(MailActivity, activity_id).write(vals)
                            self.env.cr.commit()

                if not self.env.context.get('from_hubspot', False):
                    try:
                        if  instance.hubspot_is_export_log_email:
                            record.UpdateLogEmailInHubspot(instance)
                        if  instance.hubspot_is_export_task:
                            record.UpdateTaskInHubspot(instance)
                    except Exception as e_log:
                        error_message = 'Error while updating mail activity from odoo %d \n\n Odoo vals: %s\n Hubspot response %s' % (
                            record.id, str(vals), str(e_log))
                        self.env['hubspot.logger'].create_log_message('Export Mail activity',
                                                                      error_message)
                        logger.exception("Exception in Hubspot Connection  :\n" + str(e_log))
                        self.env['hubspot.instance']._raise_user_error(e_log)

            return res

    def convert_time_to_unix_timestamp(self, deadline_date):
        '''
            This method converts date to unix timestamp
            @param : deadline_date(datetime.date)
            @returns : timestamp in millisecound(str)
        '''
        date_deadline = fields.Datetime.from_string(deadline_date)
        timestamp = date_deadline.replace(tzinfo=timezone.utc)
        generic_epoch = datetime.datetime(1970, 1, 1, 00, 00, 00)
        generic_epoch = generic_epoch.replace(tzinfo=timezone.utc)
        timestamp = (timestamp - generic_epoch).total_seconds()
        return int(timestamp * 1000)

    def convert_epoch_to_gmt_timestamp(self, hubspot_date):
        timestamp, ms = divmod(hubspot_date, 1000)
        dt = datetime.datetime.fromtimestamp(timestamp) + datetime.timedelta(milliseconds=ms)
        formatted_time = dt.strftime('%Y-%m-%d')
        return formatted_time

    def convert_to_gmt_timestamp(self, hubspot_date):
        """
        Converts HubSpot epoch milliseconds to full GMT datetime string.
        Returns format: 'YYYY-MM-DD HH:MM:SS'
        """
        import datetime

        timestamp, ms = divmod(hubspot_date, 1000)
        dt = datetime.datetime.utcfromtimestamp(timestamp) + datetime.timedelta(milliseconds=ms)
        formatted_time = dt.strftime('%Y-%m-%d %H:%M:%S')
        return formatted_time


    def get_portal_hubspot_account_details(self, hubspot_instance):
        try:
            response_all_account_details = hubspot_instance._send_get_request('/integrations/v1/me')
            json_response_all_account_details = json.loads(response_all_account_details)
            return json_response_all_account_details
        except Exception as e:
            error_message = 'Error while getting account in odoo \nHubspot response %s' % (str(e))
            self.env['hubspot.logger'].create_log_message('Getting account details', error_message)
            logger.exception("Error in Getting account details From Hubspot------------>\n" + error_message)
            hubspot_instance._raise_user_error(e)

    @api.model
    def _cron_import_task_from_hubspot(self):
        hubspot_instance_obj = self.env['hubspot.instance'].search(
            [('active', '=', True), ('hubspot_is_import_task', '=', True)])
        for hubspot_instance in hubspot_instance_obj:
            self.import_task_from_hubspot(hubspot_instance)

    def import_task_from_hubspot(self, hubspot_instance):
        modifiedDateForTask = float(hubspot_instance.modifiedDateForTask or 0)
        all_task = float(hubspot_instance.all_task or 0)
        if  hubspot_instance.hubspot_is_import_task and hubspot_instance.active: 
            logger.info('Getting All task from hubspot---------------------------')
            try:
                has_more = True
                offset = 0
                while has_more:
                    task_ids = []
                    record_limit = 100
                    response_all_tasks = hubspot_instance._send_get_request('/engagements/v1/engagements/paged?offset=' + str(offset) + '&limit=' + str(record_limit))
                    json_response_all_tasks = json.loads(response_all_tasks)
                    has_more = json_response_all_tasks.get('hasMore')
                    offset = json_response_all_tasks.get('offset')
                    for task_id in json_response_all_tasks.get('results'):
                        if task_id['engagement']['id'] and task_id['engagement']['type'] == 'TASK':
                            task_ids.append(task_id['engagement']['id'])
                    if task_ids:
                        self.get_task_details_and_create(task_ids, hubspot_instance)
                    hubspot_instance.all_task = True
                message = 'Completed Getting All Task from hubspot'
                self.env['hubspot.logger'].create_log_message('Import Task', message)
                logger.info(
                    'Completed Getting All Task from hubspot------------------------------------------------------')
            except Exception as e:
                error_message = 'Error while getting task in odoo \nHubspot response %s' % (str(e))
                self.env['hubspot.logger'].create_log_message('Import Task', error_message)
                logger.exception("Error in Getting All Task From Hubspot------------>\n" + error_message)
                hubspot_instance._raise_user_error(e)

        else:
            logger.info('Getting modified task from hubspot-------------------')
            try:
                has_more = True
                offset = 0
                while has_more:
                    updated_task_ids = []
                    record_limit = 100
                    response_get_all_tasks = hubspot_instance._send_get_request('/engagements/v1/engagements/recent/modified?offset=' + str(offset) + '&count=' + str(record_limit))
                    json_response_get_all_tasks = json.loads(response_get_all_tasks)
                    record_limit += 1
                    offset = json_response_get_all_tasks.get('offset')
                    for taskId in json_response_get_all_tasks.get('results'):
                        if taskId['engagement']['id'] and taskId['engagement']['type'] == 'TASK':
                            if (int(taskId['engagement']['lastUpdated'])) <= int(modifiedDateForTask):
                                break  # Skip Not recently updated task
                            elif (int(taskId.get('engagement')['lastUpdated'])) > int(modifiedDateForTask):
                                updated_task_ids.append(taskId['engagement']['id'])
                                updated_task_ids.reverse()
                    if hubspot_instance.active  and updated_task_ids and hubspot_instance.hubspot_is_import_task:
                        self.get_task_details_and_create(updated_task_ids, hubspot_instance)
                    else:
                        break

                message = 'Completed Getting All task from hubspot'
                self.env['hubspot.logger'].create_log_message('Import Task', message)
                logger.info(
                    'Completed Getting modified task from hubspot------------------------------------------------------')
            except Exception as e:
                error_message = 'Error while getting task in odoo \nHubspot response %s' % (str(e))
                self.env['hubspot.logger'].create_log_message('Import Task', error_message)
                logger.exception("Error in getModifiedtaskFromHubspot------------>\n" + str(e))
                hubspot_instance._raise_user_error(e)


    def get_task_details_and_create(self, task_ids, hubspot_instance):
        for task_id in task_ids:
            task_info = []
            note_info = []
            email_info = []
            email_log_info = []
            call_log_info =[]

            try:
                response_get_task_by_id = hubspot_instance._send_get_request('/engagements/v1/engagements/' + str(task_id))
                json_response_get_task_by_id = json.loads(response_get_task_by_id)
                logger.info('Getting Engagements Info ---------%s' % str(task_id))
                if json_response_get_task_by_id.get('engagement').get('type') == 'TASK':
                    task_info.append(json_response_get_task_by_id)
                    self.createNewTaskInOdoo(task_info, hubspot_instance)
                    self.env.cr.commit()

                if json_response_get_task_by_id.get('engagement').get('type') == 'NOTE':
                    note_info.append(json_response_get_task_by_id)
                    self.env['mail.message'].createNewNoteInOdoo(note_info, hubspot_instance)
                    self.env.cr.commit()

                if json_response_get_task_by_id.get('engagement').get('type') == 'EMAIL':
                    if 'source' in json_response_get_task_by_id.get('engagement') and json_response_get_task_by_id.get('engagement').get('source') == 'CRM_UI':
                        email_log_info.append(json_response_get_task_by_id)
                        self.createNewLogEmailInOdoo(email_log_info, hubspot_instance)
                        self.env.cr.commit()

                    else:
                        email_info.append(json_response_get_task_by_id)
                        self.env['mail.message'].createNewEmailInOdoo(email_info, hubspot_instance)
                        self.env.cr.commit()

                if json_response_get_task_by_id.get('engagement').get('type') == 'CALL':
                    if 'source' in json_response_get_task_by_id.get('engagement') and json_response_get_task_by_id.get('engagement').get('source') == 'CRM_UI':
                        call_log_info.append(json_response_get_task_by_id)
                        self.createNewLogCallInOdoo(call_log_info, hubspot_instance)
                        self.env.cr.commit()

                   
            except Exception as e:
                error_message = 'Error while importing hubspot task/note in odoo Id: %s\n Hubspot response %s' % (
                    task_id, str(e))
                self.env['hubspot.logger'].create_log_message('Import Task/Note', error_message)
                logger.exception("Exception In getting task/note info from Hubspot : \n" + error_message)
                hubspot_instance._raise_user_error(e)


    @api.model
    def createNewTaskInOdoo(self, task_dict, hubspot_instance):
        try:
            newtaskModifiedDate = 10000000.0
            mail_activity_obj = self.env['mail.activity']
            res_partner_obj = self.env['res.partner']
            res_users_obj = self.env['res.users']

            for task_dict_details in task_dict:
                user_id = None
                mail_activity_dict = {}

                # Step 1 — Check if hubspot_id already exists
                hubspot_id = task_dict_details['engagement'].get('id')
                if not hubspot_id:
                    continue  # skip if no hubspot_id

                existing_activity = self.env['mail.activity'].sudo().search([
                    ('hubspot_id', '=', hubspot_id)
                ], limit=1)

                existing_message = self.env['mail.message'].sudo().search([
                    ('hubspot_id', '=', hubspot_id)
                ], limit=1)

                if existing_activity or existing_message:
                    logger.info(f"Skipping import, hubspot_id {hubspot_id} already exists.")
                    continue  # skip this task

                # Continue building activity
                if 'lastUpdated' in task_dict_details['engagement']:
                    if task_dict_details['engagement']['lastUpdated']:
                        newtaskModifiedDate = int(task_dict_details['engagement']['lastUpdated'])

                if 'createdAt' in task_dict_details['engagement']:
                    mail_activity_dict['hubspot_created_date'] = self.convert_to_gmt_timestamp(
                        task_dict_details['engagement']['createdAt'])

                if 'metadata' in task_dict_details:
                    if 'taskType' in task_dict_details['metadata']:
                        if task_dict_details['metadata']['taskType'] == 'TODO':
                            mail_activity_type_id = self.env['mail.activity.type'].sudo().search(
                                [('name', '=', 'To Do')], limit=1)
                            mail_activity_dict['activity_type_id'] = mail_activity_type_id.id
                        elif task_dict_details['metadata']['taskType'] == 'EMAIL':
                            mail_activity_type_id = self.env['mail.activity.type'].sudo().search(
                                [('name', '=', 'Email')], limit=1)
                            mail_activity_dict['activity_type_id'] = mail_activity_type_id.id
                        elif task_dict_details['metadata']['taskType'] == 'CALL':
                            mail_activity_type_id = self.env['mail.activity.type'].sudo().search(
                                [('name', '=', 'Call')], limit=1)
                            mail_activity_dict['activity_type_id'] = mail_activity_type_id.id

                    if 'subject' in task_dict_details['metadata']:
                        mail_activity_dict['summary'] = task_dict_details['metadata']['subject']

                if 'ownerId' in task_dict_details['engagement']:
                    hubspot_owner_id = task_dict_details['engagement']['ownerId']
                    assigned_partner = res_partner_obj.search([
                        ('hubspot_id', '=', hubspot_owner_id),
                        ('hubspot_instance_id', '=', hubspot_instance.id)
                    ], limit=1)

                    if not assigned_partner:
                        assigned_partner = res_partner_obj.getOwnerDetailsFromHubspot(
                            hubspot_owner_id, hubspot_instance
                        )

                    if assigned_partner:
                        mail_activity_dict['hubspot_assigned_user_id'] = assigned_partner.id
                        existing_user = res_users_obj.sudo().search([
                            ('partner_id', '=', assigned_partner.id)
                        ], limit=1)

                        if existing_user:
                            mail_activity_dict['user_id'] = existing_user.id
                            user_id = existing_user.id
                        else:
                            portal_wizard = self.env['portal.wizard'].sudo().create({
                                'partner_ids': [(4, assigned_partner.id)]
                            })
                            wizard_user = portal_wizard.user_ids.filtered(
                                lambda u: u.partner_id.id == assigned_partner.id
                            )
                            if wizard_user:
                                wizard_user.action_grant_access()
                                new_user = res_users_obj.sudo().search([
                                    ('partner_id', '=', assigned_partner.id)
                                ], limit=1)
                                if new_user:
                                    new_user.sudo().write({
                                        'group_ids': [(6, 0, [
                                            self.env.ref('base.group_system').id,
                                            self.env.ref('sales_team.group_sale_manager').id
                                        ])]
                                    })
                                    mail_activity_dict['user_id'] = new_user.id
                                    user_id = new_user.id

                if 'bodyPreviewHtml' in task_dict_details['engagement']:
                    mail_activity_dict['note'] = task_dict_details['engagement']['bodyPreviewHtml']

                if 'timestamp' in task_dict_details['engagement']:
                    mail_activity_dict['date_deadline'] = self.convert_epoch_to_gmt_timestamp(
                        task_dict_details['engagement']['timestamp'])

                mail_activity_dict['hubspot_id'] = hubspot_id

                # Associations processing
                association_models = [
                    ('contactIds', False, 'res.partner', False),
                    ('companyIds', True, 'res.partner', True),
                    ('dealIds', False, 'crm.lead', 'opportunity')
                ]

                for assoc_field, is_company, model_name, lead_type in association_models:
                    if assoc_field in task_dict_details.get('associations', {}):
                        for assoc_id in task_dict_details['associations'][assoc_field]:
                            domain = [
                                ('hubspot_id', '=', assoc_id),
                                ('hubspot_instance_id', '=', hubspot_instance.id)
                            ]
                            if is_company is not False:
                                domain.append(('is_company', '=', is_company))
                            if lead_type:
                                domain.append(('type', '=', lead_type))

                            res_record = self.env[model_name].sudo().search(domain, limit=1)
                            if res_record:
                                model_id = self.env['ir.model']._get(model_name).id
                                mail_activity_dict.update({
                                    'res_model_id': model_id,
                                    'res_id': res_record.id,
                                    'res_model': model_name
                                })

                                mail_activity_id = mail_activity_obj.sudo().search([
                                    ('hubspot_id', '=', hubspot_id),
                                    ('res_id', '=', res_record.id),
                                    ('res_model', '=', model_name),
                                    ('hubspot_instance_id', '=', hubspot_instance.id)
                                ], limit=1)

                                if mail_activity_id:
                                    odoo_modifiedDate = self.convert_time_to_unix_timestamp(
                                        mail_activity_id.write_date
                                    )
                                    if int(newtaskModifiedDate) > int(odoo_modifiedDate):
                                        mail_activity_id.with_context({'from_hubspot': True}).write(mail_activity_dict)
                                        hubspot_instance.modifiedDateForTask = newtaskModifiedDate
                                        if 'status' in task_dict_details['metadata']:
                                            if task_dict_details['metadata']['status'] == 'COMPLETED':
                                                mail_activity_id.sudo().action_done()
                                        else:
                                            logger.info(f"Write into Existing Odoo Task {hubspot_id}")
                                    continue

                                # Step 2 — Create mail.activity record
                                if user_id:
                                    mail_activity_dict['hubspot_instance_id'] = hubspot_instance.id
                                    created_activity = mail_activity_obj.with_user(user_id).with_context(
                                        {'from_hubspot': True}
                                    ).create(mail_activity_dict)
                                else:
                                    mail_activity_dict['hubspot_instance_id'] = hubspot_instance.id
                                    created_activity = mail_activity_obj.sudo().with_context(
                                        {'from_hubspot': True}
                                    ).create(mail_activity_dict)


                                hubspot_instance.modifiedDateForTask = newtaskModifiedDate
                                if 'status' in task_dict_details['metadata']:
                                    if task_dict_details['metadata']['status'] == 'COMPLETED':
                                        # created_activity.sudo().action_done()
                                        created_activity.with_context(hubspot_id=hubspot_id)._action_done()

                                    else:
                                        logger.info(
                                            f"Created New Task {created_activity.id} with hubspot_id {hubspot_id}")
                                self._cr.commit()

        except Exception as e:
            error_message = f"Error while creating hubspot task in odoo vals: {task_dict}\nHubspot response: {str(e)}"
            self.env['hubspot.logger'].create_log_message('Import Task', error_message)
            logger.exception(f"Exception in Creating New Task in Odoo:\n{error_message}")
            hubspot_instance._raise_user_error(e)

    @api.model
    def _cron_export_task_to_hubspot(self):
        hubspot_instance_obj = self.env['hubspot.instance'].search(
            [('active', '=', True),('hubspot_is_export_task', '=', True)])
        for hubspot_instance in hubspot_instance_obj:
            self.export_task_to_hubspot(hubspot_instance)

    def _action_done(self, feedback=False, attachment_ids=None):
        hubspot_id = ''
        mail_activity_email_id = self.env.ref('mail.mail_activity_data_email').id
        mail_activity_meeting_id = self.env.ref('mail.mail_activity_data_meeting').id
        mail_activity_todo_id = self.env.ref('mail.mail_activity_data_todo').id
        hubspot_instance_id = self.env['hubspot.instance'].search(
            [('active', '=', True), ('hubspot_is_export_task', '=', True), ('default_instance', '=', True)], limit=1)
        if self.activity_type_id.id == mail_activity_todo_id and hubspot_instance_id and not self.hubspot_id:
            self.with_context({'from_hubspot': True}).write({})
            hubspot_id = self.createNewTaskInHubspotMarkAsDone(hubspot_instance_id)

        elif self.activity_type_id.id == mail_activity_todo_id and hubspot_instance_id and self.hubspot_id:
            self.with_context({'from_hubspot': True}).write({})
            hubspot_id = self.UpdateTaskInHubspotMarkAsDone(hubspot_instance_id)

        if self.activity_type_id.id == mail_activity_meeting_id and hubspot_instance_id and not self.hubspot_id:
            self.with_context({'from_hubspot': True}).write({})
            hubspot_id = self.createNewMeetingInHubspotMarkAsDone(hubspot_instance_id)

        elif self.activity_type_id.id == mail_activity_meeting_id and hubspot_instance_id and self.hubspot_id:
            self.with_context({'from_hubspot': True}).write({})
            hubspot_id = self.UpdateMeetingInHubspotMarkAsDone(hubspot_instance_id)
        messages, activities = super(MailActivity, self)._action_done()
        if hubspot_id:
            messages.hubspot_id = hubspot_id
            messages.hubspot_instance_id = hubspot_instance_id.id
            messages.hubspot_object = 'task'

        return messages, activities

    def createNewTaskInHubspotMarkAsDone(self, hubspot_instance):
        for eachNewActivity in self:
            # create hubspot dictionary
            properties = {}
            metadata_dict = {}
            engagement_dict = {}
            associations_list = []
            associations_dict = {}
            if eachNewActivity.summary:
                metadata_dict['subject'] = eachNewActivity.summary
            if eachNewActivity.activity_type_id:
                if eachNewActivity.activity_type_id.name == 'To Do':
                    metadata_dict['taskType'] = 'TODO'
                elif eachNewActivity.activity_type_id.name == 'Email':
                    metadata_dict['taskType'] = 'EMAIL'
                elif eachNewActivity.activity_type_id.name == 'Call':
                    metadata_dict['taskType'] = 'CALL'
            if eachNewActivity.date_deadline:
                engagement_dict['timestamp'] = self.convert_time_to_unix_timestamp(eachNewActivity.date_deadline)
            if eachNewActivity.res_id:
                if eachNewActivity.res_model == 'res.partner':
                    partner_id = self.env['res.partner'].sudo().search([('id', '=', eachNewActivity.res_id)])
                    if partner_id.hubspot_id and not partner_id.is_company and partner_id.hubspot_instance_id.id == hubspot_instance.id:
                        associations_dict['contactIds'] = [partner_id.hubspot_id]
                    else:
                        associations_dict['contactIds'] = []
                    if partner_id.hubspot_id and partner_id.is_company and partner_id.hubspot_instance_id.id == hubspot_instance.id:
                        associations_dict['companyIds'] = [partner_id.hubspot_id]
                    else:
                        associations_dict['companyIds'] = []
                if eachNewActivity.res_model == 'crm.lead':
                    lead_id = self.env['crm.lead'].sudo().search([('id', '=', eachNewActivity.res_id)])
                    if lead_id.hubspot_id and lead_id.hubspot_instance_id.id == hubspot_instance.id:
                        associations_dict['dealIds'] = [lead_id.hubspot_id]
                    else:
                        associations_dict['dealIds'] = []
            # user (Owner) sync
            if eachNewActivity.user_id:
                # if not eachNewActivity.user_id.hubspot_uid:
                #     logger.warning("Odoo User Not Available In Hubspot")
                #     self.env['res.users'].syncAllUsers()
                if eachNewActivity.user_id.hubspot_uid and eachNewActivity.user_id.hubspot_instance_id.id == hubspot_instance.id:
                    associations_dict['ownerIds'] = [eachNewActivity.user_id.hubspot_uid]
                    engagement_dict['ownerId'] = eachNewActivity.user_id.hubspot_uid
                else:
                    associations_dict['ownerIds'] = []
            if eachNewActivity.note:
                engagement_dict['bodyPreviewHtml'] = eachNewActivity.note
                metadata_dict['body'] = eachNewActivity.note
            engagement_dict['active'] = 'true'
            engagement_dict['type'] = 'TASK'

            account_details = self.get_portal_hubspot_account_details(hubspot_instance)
            if account_details:
                engagement_dict['portalId'] = account_details['portalId']

            # engagement_dict['bodyPreviewIsTruncated'] = 'false'
            # engagement_dict['gdprDeleted'] = 'false'
            metadata_dict['status'] = 'COMPLETED'
            metadata_dict['forObjectType'] = 'OWNER'
            # metadata_dict['sendDefaultReminder'] = 'false'
            metadata_dict['priority'] = 'NONE'
            # metadata_dict['isAllDay'] = 'false'
            properties = {"engagement": engagement_dict, 'associations': associations_dict, 'metadata': metadata_dict}
            if properties:
                try:
                    response = hubspot_instance._send_post_request('/engagements/v1/engagements', properties)
                    json_response = json.loads(response)
                    eachNewActivity.with_context({'from_hubspot': True}).hubspot_id = json_response['engagement']['id']
                    eachNewActivity.with_context({'from_hubspot': True}).hubspot_instance_id = hubspot_instance.id
                    message = 'Exported Task successfully Mark Completed'
                    self.env['hubspot.logger'].create_log_message('Export Activity', message)
                    logger.info('Exported Task successfully Mark Completed...')
                    return response['engagement']['id']

                except Exception as e_log:
                    error_message = 'Error while exporting odoo activity %d \n\n Odoo vals: %s\n Hubspot response %s' % (
                        eachNewActivity.id, str(properties), str(e_log))
                    self.env['hubspot.logger'].create_log_message('Export Task', error_message)
                    logger.exception("Exception in Hubspot Connection  :\n" + str(e_log))
                    hubspot_instance._raise_user_error(e_log)

                    return False

    def UpdateTaskInHubspotMarkAsDone(self, hubspot_instance):
        logger.info('Updating task in hubspot')
        for eachNewActivity in self:
            if str(self.convert_time_to_unix_timestamp(
                    eachNewActivity.write_date)) > hubspot_instance.modifiedDateForTask:
                # create hubspot dictionary
                properties = {}
                metadata_dict = {}
                engagement_dict = {}
                associations_list = []
                associations_dict = {}
                if eachNewActivity.summary:
                    metadata_dict['subject'] = eachNewActivity.summary
                if eachNewActivity.activity_type_id:
                    if eachNewActivity.activity_type_id.name == 'To Do':
                        metadata_dict['taskType'] = 'TODO'
                    elif eachNewActivity.activity_type_id.name == 'Email':
                        metadata_dict['taskType'] = 'EMAIL'
                    elif eachNewActivity.activity_type_id.name == 'Call':
                        metadata_dict['taskType'] = 'CALL'
                if eachNewActivity.date_deadline:
                    engagement_dict['timestamp'] = self.convert_time_to_unix_timestamp(eachNewActivity.date_deadline)
                if eachNewActivity.res_id:
                    if eachNewActivity.res_model == 'res.partner':
                        partner_id = self.env['res.partner'].sudo().search([('id', '=', eachNewActivity.res_id)])
                        if partner_id.hubspot_id and not partner_id.is_company:
                            associations_dict['contactIds'] = [partner_id.hubspot_id]
                        else:
                            associations_dict['contactIds'] = []
                        if partner_id.hubspot_id and partner_id.is_company:
                            associations_dict['companyIds'] = [partner_id.hubspot_id]
                        else:
                            associations_dict['companyIds'] = []
                    if eachNewActivity.res_model == 'crm.lead':
                        lead_id = self.env['crm.lead'].sudo().search([('id', '=', eachNewActivity.res_id)])
                        associations_dict['dealIds'] = [lead_id.hubspot_id]
                    else:
                        associations_dict['dealIds'] = []
                # user (Owner) sync
                if eachNewActivity.user_id:
                    # if not eachNewActivity.user_id.hubspot_uid:
                    #     logger.warning("Odoo User Not Available In Hubspot")
                    #     self.env['res.users'].syncAllUsers()
                    if eachNewActivity.user_id.hubspot_uid and eachNewActivity.user_id.hubspot_instance_id.id == hubspot_instance.id:
                        associations_dict['ownerIds'] = [eachNewActivity.user_id.hubspot_uid]
                        engagement_dict['ownerId'] = eachNewActivity.user_id.hubspot_uid
                    else:
                        associations_dict['ownerIds'] = []
                if eachNewActivity.note:
                    engagement_dict['bodyPreviewHtml'] = eachNewActivity.note
                    metadata_dict['body'] = eachNewActivity.note
                if eachNewActivity.hubspot_id:
                    engagement_dict['id'] = eachNewActivity.hubspot_id
                engagement_dict['active'] = 'true'
                account_details = self.get_portal_hubspot_account_details(hubspot_instance)
                if account_details:
                    engagement_dict['portalId'] = account_details['portalId']

                engagement_dict['type'] = 'TASK'
                # engagement_dict['bodyPreviewIsTruncated'] = 'false'
                # engagement_dict['gdprDeleted'] = 'false'
                metadata_dict['status'] = 'COMPLETED'
                metadata_dict['forObjectType'] = 'OWNER'
                # metadata_dict['sendDefaultReminder'] = 'false'
                metadata_dict['priority'] = 'NONE'
                # metadata_dict['isAllDay'] = 'false'
                properties = {"engagement": engagement_dict, 'associations': associations_dict,
                              'metadata': metadata_dict}
                if properties:
                    try:
                        response = hubspot_instance._send_patch_request('/engagements/v1/engagements/'+ eachNewActivity.hubspot_id, properties)
                        parsed_resp = json.loads(response)
                        eachNewActivity.with_context({'from_hubspot': True}).hubspot_id = \
                            parsed_resp['engagement']['id']
                        eachNewActivity.with_context({'from_hubspot': True}).hubspot_instance_id = hubspot_instance.id
                        return parsed_resp['engagement']['id']

                    except Exception as e_log:
                        error_message = 'Error while exporting odoo task %d \n\n Odoo vals: %s\n Hubspot response %s' % (
                            eachNewActivity.id, str(properties), str(e_log))
                        self.env['hubspot.logger'].create_log_message('Export Task', error_message)
                        logger.exception("Exception in Hubspot Connection  :\n" + str(e_log))
                        hubspot_instance._raise_user_error(e_log)

                        return False

        logger.info('Completed Updating task in hubspot')

    def createNewMeetingInHubspotMarkAsDone(self, hubspot_instance):
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
            if eachNewMeeting.res_id:
                if eachNewMeeting.res_model == 'res.partner':
                    partner_id = self.env['res.partner'].sudo().search([('id', '=', eachNewMeeting.res_id)])
                    if partner_id.hubspot_id and not partner_id.is_company and partner_id.hubspot_instance_id.id == hubspot_instance.id:
                        associations_dict['contactIds'] = [partner_id.hubspot_id]
                    else:
                        associations_dict['contactIds'] = []
                    if partner_id.hubspot_id and partner_id.is_company and partner_id.hubspot_instance_id.id == hubspot_instance.id:
                        associations_dict['companyIds'] = [partner_id.hubspot_id]
                    else:
                        associations_dict['companyIds'] = []
                if eachNewMeeting.res_model == 'crm.lead':
                    lead_id = self.env['crm.lead'].sudo().search([('id', '=', eachNewMeeting.res_id)])
                    if lead_id.hubspot_id and lead_id.hubspot_instance_id.id == hubspot_instance.id:
                        associations_dict['dealIds'] = [lead_id.hubspot_id]
                    else:
                        associations_dict['dealIds'] = []

            if eachNewMeeting.summary:
                metadata_dict['title'] = eachNewMeeting.summary
                engagement_dict['bodyPreview'] = eachNewMeeting.summary
            # if eachNewMeeting.start_datetime:
            #     metadata_dict['startTime'] = self.env['mail.activity'].convert_time_to_unix_timestamp(eachNewMeeting.start_datetime)
            if eachNewMeeting.date_deadline:
                metadata_dict['endTime'] = self.env['mail.activity'].convert_time_to_unix_timestamp(eachNewMeeting.date_deadline)
            metadata_dict['meetingOutcome'] = 'COMPLETED'
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
                    return response['engagement']['id']
                except Exception as e_log:
                    error_message = 'Error while exporting odoo meeting %d \n\n Odoo vals: %s\n Hubspot response %s' % (eachNewMeeting.id, str(properties), str(e_log))
                    self.env['hubspot.logger'].create_log_message('Export Meeting', error_message)
                    logger.exception("Exception in Hubspot Connection  :\n" + str(e_log))
                    hubspot_instance._raise_user_error(e_log)

                    return False
        message = 'Exported Meeting successfully'
        self.env['hubspot.logger'].create_log_message('Export Meeting', message)
        logger.info('Exported Meeting successfully...')

    def UpdateMeetingInHubspotMarkAsDone(self, hubspot_instance):
        for eachNewMeeting in self:
            # create hubspot dictionary
            properties = {}
            metadata_dict = {}

            engagement_dict = {}
            associations_list = []
            partner_list = []
            associations_dict = {}
            if eachNewMeeting.res_id:
                if eachNewMeeting.res_model == 'res.partner':
                    partner_id = self.env['res.partner'].sudo().search([('id', '=', eachNewMeeting.res_id)])
                    if partner_id.hubspot_id and not partner_id.is_company and partner_id.hubspot_instance_id.id == hubspot_instance.id:
                        associations_dict['contactIds'] = [partner_id.hubspot_id]
                    else:
                        associations_dict['contactIds'] = []
                    if partner_id.hubspot_id and partner_id.is_company and partner_id.hubspot_instance_id.id == hubspot_instance.id:
                        associations_dict['companyIds'] = [partner_id.hubspot_id]
                    else:
                        associations_dict['companyIds'] = []
                if eachNewMeeting.res_model == 'crm.lead':
                    lead_id = self.env['crm.lead'].sudo().search([('id', '=', eachNewMeeting.res_id)])
                    if lead_id.hubspot_id and lead_id.hubspot_instance_id.id == hubspot_instance.id:
                        associations_dict['dealIds'] = [lead_id.hubspot_id]
                    else:
                        associations_dict['dealIds'] = []
            if eachNewMeeting.summary:
                metadata_dict['title'] = eachNewMeeting.summary
                engagement_dict['bodyPreview'] = eachNewMeeting.summary
            if eachNewMeeting.date_deadline:
                metadata_dict['endTime'] = self.env['mail.activity'].convert_time_to_unix_timestamp(eachNewMeeting.date_deadline)
            metadata_dict['meetingOutcome'] = 'COMPLETED'
            account_details = self.env['mail.activity'].get_portal_hubspot_account_details(hubspot_instance)
            if account_details:
                engagement_dict['portalId'] = account_details['portalId']
            engagement_dict['type'] = 'MEETING'

            properties = {"engagement": engagement_dict, 'associations': associations_dict, 'metadata': metadata_dict}
            if properties:
                try:
                    response = hubspot_instance._send_patch_request('/engagements/v1/engagements/' + eachNewMeeting.hubspot_id, properties)
                    parsed_resp = json.loads(response)
                    eachNewMeeting.with_context({'from_hubspot': True}).hubspot_id = parsed_resp['engagement']['id']
                    if not eachNewMeeting.hubspot_instance_id and eachNewMeeting.hubspot_instance_id == hubspot_instance.id:
                        eachNewMeeting.with_context({'from_hubspot': True}).hubspot_instance_id = hubspot_instance.id
                    return parsed_resp['engagement']['id']
                except Exception as e_log:
                    error_message = 'Error while exporting odoo meeting %d \n\n Odoo vals: %s\n Hubspot response %s' % (eachNewMeeting.id, str(properties), str(e_log))
                    self.env['hubspot.logger'].create_log_message('Export Meeting', error_message)
                    logger.exception("Exception in Hubspot Connection  :\n" + str(e_log))
                    hubspot_instance._raise_user_error(e_log)

        logger.info('Completed Updating Meeting in hubspot')

    @api.model
    def export_task_to_hubspot(self, hubspot_instance):
        # Hubspot Information
        hubspot_app_key = hubspot_instance.hubspot_app_key
        hubspot_app_name = hubspot_instance.name

        # if not hubspot_app_key or not hubspot_app_name:
        #     raise UserError(_(
        #         'Error in Synchronization!\nHubspot API Key and App Name need to be specified for synchronization of data with Odoo.'))

        mail_activity_ids = self.env['mail.activity'].search([('hubspot_id', '=', False)])
        if hubspot_instance.default_instance and hubspot_instance.active  and hubspot_instance.hubspot_is_export_task:
            for mail_activity_id in mail_activity_ids:
                if not mail_activity_id.hubspot_id:
                    mail_activity_id.createNewTaskInHubspot(hubspot_instance)

    def createNewTaskInHubspot(self, hubspot_instance):
        for eachNewActivity in self:
            # create hubspot dictionary
            properties = {}
            metadata_dict = {}
            engagement_dict = {}
            associations_list = []
            associations_dict = {}
            if eachNewActivity.summary:
                metadata_dict['subject'] = eachNewActivity.summary
            if eachNewActivity.activity_type_id:
                if eachNewActivity.activity_type_id.name == 'To Do':
                    metadata_dict['taskType'] = 'TODO'
            if eachNewActivity.date_deadline:
                engagement_dict['timestamp'] = self.convert_time_to_unix_timestamp(eachNewActivity.date_deadline)
            if eachNewActivity.res_id:
                if eachNewActivity.res_model == 'res.partner':
                    partner_id = self.env['res.partner'].sudo().search([('id', '=', eachNewActivity.res_id)])
                    if partner_id.hubspot_id and not partner_id.is_company and partner_id.hubspot_instance_id.id == hubspot_instance.id:
                        associations_dict['contactIds'] = [partner_id.hubspot_id]
                    else:
                        associations_dict['contactIds'] = []
                    if partner_id.hubspot_id and partner_id.is_company and partner_id.hubspot_instance_id.id == hubspot_instance.id:
                        associations_dict['companyIds'] = [partner_id.hubspot_id]
                    else:
                        associations_dict['companyIds'] = []
                if eachNewActivity.res_model == 'crm.lead':
                    lead_id = self.env['crm.lead'].sudo().search([('id', '=', eachNewActivity.res_id)])
                    if lead_id.hubspot_id and lead_id.hubspot_instance_id.id == hubspot_instance.id:
                        associations_dict['dealIds'] = [lead_id.hubspot_id]
                    else:
                        associations_dict['dealIds'] = []
            # user (Owner) sync
            if eachNewActivity.user_id:
                if eachNewActivity.user_id.hubspot_uid and eachNewActivity.user_id.hubspot_instance_id.id == hubspot_instance.id:
                    associations_dict['ownerIds'] = [eachNewActivity.user_id.hubspot_uid]
                    engagement_dict['ownerId'] = eachNewActivity.user_id.hubspot_uid
                else:
                    associations_dict['ownerIds'] = []
            if eachNewActivity.note:
                engagement_dict['bodyPreviewHtml'] = eachNewActivity.note
                metadata_dict['body'] = eachNewActivity.note
            engagement_dict['active'] = 'true'
            engagement_dict['type'] = 'TASK'

            account_details = self.get_portal_hubspot_account_details(hubspot_instance)
            if account_details:
                engagement_dict['portalId'] = account_details['portalId']

            metadata_dict['status'] = 'NOT_STARTED'
            metadata_dict['forObjectType'] = 'OWNER'
            metadata_dict['priority'] = 'NONE'
            properties = {"engagement": engagement_dict, 'associations': associations_dict, 'metadata': metadata_dict}
            if properties:
                try:
                    response_create_task = hubspot_instance._send_post_request('/engagements/v1/engagements', properties)
                    json_response_create_task = json.loads(response_create_task)
                    eachNewActivity.with_context({'from_hubspot': True}).hubspot_id = json_response_create_task['engagement']['id']
                    eachNewActivity.hubspot_instance_id = hubspot_instance.id
                    message = 'Exported Task successfully'
                    self.env['hubspot.logger'].create_log_message('Export Activity', message)
                    logger.info('Exported Task successfully...')
                except Exception as e_log:
                    error_message = 'Error while exporting odoo activity %d \n\n Odoo vals: %s\n Hubspot response %s' % (
                        eachNewActivity.id, str(properties), str(e_log))
                    self.env['hubspot.logger'].create_log_message('Export Task', error_message)
                    logger.exception("Exception in Hubspot Connection  :\n" + str(e_log))
                    hubspot_instance._raise_user_error(e_log)

    def UpdateTaskInHubspot(self, hubspot_instance):
        logger.info('Updating task in hubspot')
        for eachNewActivity in self:
            if str(self.convert_time_to_unix_timestamp(
                    eachNewActivity.write_date)) > hubspot_instance.modifiedDateForTask:
                # create hubspot dictionary
                properties = {}
                metadata_dict = {}
                engagement_dict = {}
                associations_list = []
                associations_dict = {}
                if eachNewActivity.summary:
                    metadata_dict['subject'] = eachNewActivity.summary
                if eachNewActivity.activity_type_id:
                    if eachNewActivity.activity_type_id.name == 'To Do':
                        metadata_dict['taskType'] = 'TODO'
                    elif eachNewActivity.activity_type_id.name == 'Email':
                        metadata_dict['taskType'] = 'EMAIL'
                    elif eachNewActivity.activity_type_id.name == 'Call':
                        metadata_dict['taskType'] = 'CALL'
                if eachNewActivity.date_deadline:
                    engagement_dict['timestamp'] = self.convert_time_to_unix_timestamp(eachNewActivity.date_deadline)
                if eachNewActivity.res_id:
                    if eachNewActivity.res_model == 'res.partner':
                        partner_id = self.env['res.partner'].sudo().search([('id', '=', eachNewActivity.res_id)])
                        if partner_id.hubspot_id and not partner_id.is_company:
                            associations_dict['contactIds'] = [partner_id.hubspot_id]
                        else:
                            associations_dict['contactIds'] = []
                        if partner_id.hubspot_id and partner_id.is_company:
                            associations_dict['companyIds'] = [partner_id.hubspot_id]
                        else:
                            associations_dict['companyIds'] = []
                    if eachNewActivity.res_model == 'crm.lead':
                        lead_id = self.env['crm.lead'].sudo().search([('id', '=', eachNewActivity.res_id)])
                        associations_dict['dealIds'] = [lead_id.hubspot_id]
                    else:
                        associations_dict['dealIds'] = []
                # user (Owner) sync
                if eachNewActivity.user_id:
                    if eachNewActivity.user_id.hubspot_uid and eachNewActivity.user_id.hubspot_instance_id.id == hubspot_instance.id:
                        associations_dict['ownerIds'] = [eachNewActivity.user_id.hubspot_uid]
                        engagement_dict['ownerId'] = eachNewActivity.user_id.hubspot_uid
                    else:
                        associations_dict['ownerIds'] = []
                if eachNewActivity.note:
                    engagement_dict['bodyPreviewHtml'] = eachNewActivity.note
                    metadata_dict['body'] = eachNewActivity.note
                if eachNewActivity.hubspot_id:
                    engagement_dict['id'] = eachNewActivity.hubspot_id
                engagement_dict['active'] = 'true'
                account_details = self.get_portal_hubspot_account_details(hubspot_instance)
                if account_details:
                    engagement_dict['portalId'] = account_details['portalId']

                engagement_dict['type'] = 'TASK'
                metadata_dict['status'] = 'NOT_STARTED'
                metadata_dict['forObjectType'] = 'OWNER'
                metadata_dict['priority'] = 'NONE'
                properties = {"engagement": engagement_dict, 'associations': associations_dict,
                              'metadata': metadata_dict}
                if properties:
                    try:
                        response_update_template = hubspot_instance._send_patch_request('/engagements/v1/engagements/'+eachNewActivity.hubspot_id, properties)
                        parsed_resp_update_template = json.loads(response_update_template)
                        eachNewActivity.with_context({'from_hubspot': True}).hubspot_id = parsed_resp_update_template['engagement']['id']
                        eachNewActivity.with_context({'from_hubspot': True}).hubspot_instance_id = hubspot_instance.id

                    except Exception as e_log:
                        error_message = 'Error while exporting odoo task %d \n\n Odoo vals: %s\n Hubspot response %s' % (
                            eachNewActivity.id, str(properties), str(e_log))
                        self.env['hubspot.logger'].create_log_message('Export Task', error_message)
                        logger.exception("Exception in Hubspot Connection  :\n" + str(e_log))
                        hubspot_instance._raise_user_error(e_log)


        logger.info('Completed Updating task in hubspot')

    @api.model
    def _cron_import_log_email_from_hubspot(self):
        hubspot_instance_obj = self.env['hubspot.instance'].search(
            [('active', '=', True),
             ('hubspot_is_import_log_email', '=', True)])
        for hubspot_instance in hubspot_instance_obj:
            self.import_log_email_from_hubspot(hubspot_instance)

    def import_log_email_from_hubspot(self, hubspot_instance):
        modifiedDateForLogEmail = float(hubspot_instance.modifiedDateForLogEmail or 0)

        all_log_email = float(hubspot_instance.all_log_email or 0)
        if hubspot_instance.hubspot_is_import_log_email and hubspot_instance.active:  
            logger.info('Getting All Logged Email from hubspot---------------------------')
            try:
                has_more = True
                offset = 0
                while has_more:
                    log_email_ids = []
                    record_limit = 100
                    response_get_all_log_email = hubspot_instance._send_get_request('/engagements/v1/engagements/paged?offset=' + str(offset) + '&limit=' + str(record_limit))
                    json_response_get_all_log_email = json.loads(response_get_all_log_email)
                    has_more = json_response_get_all_log_email['hasMore']
                    offset = json_response_get_all_log_email['offset']
                    for log_email_id in json_response_get_all_log_email['results']:
                        if log_email_id['engagement']['id'] and log_email_id['engagement']['type'] == 'EMAIL':
                            if 'source' in log_email_id['engagement'] and log_email_id['engagement'][
                                'source'] == 'CRM_UI':
                                log_email_ids.append(log_email_id['engagement']['id'])

                    if log_email_ids:
                        self.env['mail.activity'].get_task_details_and_create(log_email_ids, hubspot_instance)
                    hubspot_instance.all_log_email = True

                message = 'Completed Getting All Log Email from hubspot'
                self.env['hubspot.logger'].create_log_message('Import Log Email', message)
                logger.info(
                    'Completed Getting Log Email from hubspot------------------------------------------------------')
            except Exception as e:
                error_message = 'Error while getting Log Email in odoo \nHubspot response %s' % (str(e))
                self.env['hubspot.logger'].create_log_message('Import Log Email', error_message)
                logger.exception("Error in Getting All Log Email From Hubspot------------>\n" + error_message)
                hubspot_instance._raise_user_error(e)

        else:

            logger.info('Getting modified log email from hubspot-------------------')
            try:
                updatedLogEmailList = []
                has_more = True
                offset = 0
                while has_more:
                    updated_log_email_ids = []
                    record_limit = 90
                    response_get_recently_modified_log_email = hubspot_instance._send_get_request('/engagements/v1/engagements/recent/modified?offset=' + str(offset) + '&count=' + str(record_limit))
                    json_response_get_recently_modified_log_email = json.loads(response_get_recently_modified_log_email)
                    record_limit += 1
                    offset = json_response_get_recently_modified_log_email['offset']
                    has_more = json_response_get_recently_modified_log_email['hasMore']
                    for logEmailId in json_response_get_recently_modified_log_email['results']:
                        if logEmailId['engagement']['id'] and logEmailId['engagement']['type'] == 'EMAIL':
                            if (int(logEmailId['engagement']['lastUpdated'])) <= int(modifiedDateForLogEmail):
                                break  # Skip Not recently updated note
                            elif (int(logEmailId.get('engagement')['lastUpdated'])) > int(modifiedDateForLogEmail):
                                if 'source' in logEmailId['engagement'] and logEmailId['engagement']['source'] == 'CRM_UI':
                                    updated_log_email_ids.append(logEmailId['engagement']['id'])
                                    updated_log_email_ids.reverse()
                    if  hubspot_instance.active and updated_log_email_ids and hubspot_instance.hubspot_is_import_log_email:
                        self.env['mail.activity'].get_task_details_and_create(updated_log_email_ids,
                                                                              hubspot_instance)
                    else:
                        break
                message = 'Completed Getting All Log Email from hubspot'
                self.env['hubspot.logger'].create_log_message('Import Log Email', message)
                logger.info(
                    'Completed Getting modified log email from hubspot------------------------------------------------------')
            except Exception as e:
                error_message = 'Error while getting log email in odoo \nHubspot response %s' % (str(e))
                self.env['hubspot.logger'].create_log_message('Import Log Email', error_message)
                logger.exception("Error in getModifiedLogEmailFromHubspot------------>\n" + str(e))
                hubspot_instance._raise_user_error(e)

    @api.model
    def createNewLogEmailInOdoo(self, log_email_dict, hubspot_instance):
        try:
            newLogEmailModifiedDate = 10000000.0
            mail_activity_obj = self.env['mail.activity']
            res_partner_obj = self.env['res.partner']
            res_users_obj = self.env['res.users']

            for log_email_dict_details in log_email_dict:
                mail_activity_dict = {}
                user_id = None

                # HubSpot ID
                hubspot_id = log_email_dict_details.get('engagement', {}).get('id')
                if not hubspot_id:
                    logger.warning("⚠️ Missing HubSpot ID in log email record. Skipping.")
                    continue

                # ✅ SKIP if mail.message already exists for this HubSpot ID
                existing_message = self.env['mail.message'].sudo().search([
                    ('hubspot_id', '=', str(hubspot_id))
                ], limit=1)
                if existing_message:
                    logger.info(
                        f"⚡ Skipping Log Email creation — mail.message already exists for HubSpot ID: {hubspot_id}")
                    continue

                # Get last updated
                if log_email_dict_details.get('engagement', {}).get('lastUpdated'):
                    newLogEmailModifiedDate = int(log_email_dict_details['engagement']['lastUpdated'])

                # Created Date
                if log_email_dict_details.get('engagement', {}).get('createdAt'):
                    hubspot_created_date = self.convert_to_gmt_timestamp(
                        log_email_dict_details['engagement']['createdAt'])
                    mail_activity_dict['hubspot_created_date'] = hubspot_created_date

                # Owner / Assigned User
                if log_email_dict_details.get('engagement', {}).get('ownerId'):
                    hubspot_owner_id = log_email_dict_details['engagement']['ownerId']
                    assigned_partner = res_partner_obj.search([
                        ('hubspot_id', '=', hubspot_owner_id),
                        ('hubspot_instance_id', '=', hubspot_instance.id)
                    ], limit=1)

                    if not assigned_partner:
                        assigned_partner = res_partner_obj.getOwnerDetailsFromHubspot(hubspot_owner_id,
                                                                                      hubspot_instance)

                    if assigned_partner:
                        mail_activity_dict['hubspot_assigned_user_id'] = assigned_partner.id
                        existing_user = res_users_obj.sudo().search([
                            ('partner_id', '=', assigned_partner.id)
                        ], limit=1)

                        if existing_user:
                            mail_activity_dict['user_id'] = existing_user.id
                            user_id = existing_user.id
                        else:
                            portal_wizard = self.env['portal.wizard'].sudo().create({
                                'partner_ids': [(4, assigned_partner.id)]
                            })
                            wizard_user = portal_wizard.user_ids.filtered(
                                lambda u: u.partner_id.id == assigned_partner.id
                            )
                            if wizard_user:
                                wizard_user.action_grant_access()
                                new_user = res_users_obj.sudo().search([
                                    ('partner_id', '=', assigned_partner.id)
                                ], limit=1)
                                if new_user:
                                    new_user.sudo().write({
                                        'group_ids': [(6, 0, [
                                            self.env.ref('base.group_system').id,
                                            self.env.ref('sales_team.group_sale_manager').id
                                        ])]
                                    })
                                    mail_activity_dict['user_id'] = new_user.id
                                    user_id = new_user.id

                # Activity Type
                if log_email_dict_details.get('engagement', {}).get('type') == 'EMAIL':
                    mail_activity_type_id = self.env['mail.activity.type'].sudo().search(
                        [('name', '=', 'Email')], limit=1)
                    if mail_activity_type_id:
                        mail_activity_dict['activity_type_id'] = mail_activity_type_id.id

                # Summary / Note
                mail_activity_dict['summary'] = log_email_dict_details.get('engagement', {}).get('bodyPreview', '')
                mail_activity_dict['note'] = log_email_dict_details.get('engagement', {}).get('bodyPreviewHtml', '')

                # Store HubSpot ID
                mail_activity_dict['hubspot_id'] = hubspot_id

                # Deadline
                if log_email_dict_details.get('engagement', {}).get('timestamp'):
                    mail_activity_dict['date_deadline'] = self.convert_epoch_to_gmt_timestamp(
                        log_email_dict_details['engagement']['timestamp'])

                # ⚠️ CRITICAL FIX: Only set model info if we find a valid res_id
                res_record = None
                associations = log_email_dict_details.get('associations', {})

                # Try to find associated record in order: contacts -> companies -> deals
                if 'contactIds' in associations and associations.get('contactIds'):
                    for hubspot_contact_id in associations['contactIds']:
                        res_record = res_partner_obj.sudo().search([
                            ('is_company', '=', False),
                            ('hubspot_id', '=', hubspot_contact_id),
                            ('hubspot_instance_id', '=', hubspot_instance.id)
                        ], limit=1)
                        if res_record:
                            break

                if not res_record and 'companyIds' in associations and associations.get('companyIds'):
                    for hubspot_company_id in associations['companyIds']:
                        res_record = res_partner_obj.sudo().search([
                            ('is_company', '=', True),
                            ('hubspot_id', '=', hubspot_company_id),
                            ('hubspot_instance_id', '=', hubspot_instance.id)
                        ], limit=1)
                        if res_record:
                            break

                if not res_record and 'dealIds' in associations and associations.get('dealIds'):
                    for hubspot_lead_id in associations['dealIds']:
                        res_record = self.env['crm.lead'].sudo().search([
                            ('type', '=', 'opportunity'),
                            ('hubspot_id', '=', hubspot_lead_id),
                            ('hubspot_instance_id', '=', hubspot_instance.id)
                        ], limit=1)
                        if res_record:
                            break

                # ✅ Only proceed if we found a valid record to associate with
                if not res_record:
                    logger.warning(
                        f"⚠️ No valid association found for HubSpot log email {hubspot_id}. Skipping creation.")
                    continue

                # Set model information
                model_id = self.env['ir.model']._get(res_record._name).id
                mail_activity_dict.update({
                    'res_model_id': model_id,
                    'res_id': res_record.id,
                    'res_model': res_record._name
                })

                # Create mail activity
                mail_activity_dict['hubspot_instance_id'] = hubspot_instance.id
                if user_id:
                    create_mail_activity_id = mail_activity_obj.with_user(user_id).with_context(
                        {'from_hubspot': True}
                    ).create(mail_activity_dict)
                else:
                    create_mail_activity_id = mail_activity_obj.sudo().with_context(
                        {'from_hubspot': True}
                    ).create(mail_activity_dict)

                # Mark as done (will create mail.message)
                # create_mail_activity_id.with_context(hubspot_id=hubspot_id)._action_done()

                logger.info(
                    f"✅ Created and Marked Done Log Email Activity {create_mail_activity_id.id} for HubSpot ID {hubspot_id}"
                )

                hubspot_instance.modifiedDateForLogEmail = newLogEmailModifiedDate
                self._cr.commit()

        except Exception as e:
            error_message = f'Error while creating HubSpot log email in Odoo: {log_email_dict}\nException: {str(e)}'
            self.env['hubspot.logger'].create_log_message('Import Log Email', error_message)
            logger.exception("Exception in createNewLogEmailInOdoo:\n" + error_message)
            hubspot_instance._raise_user_error(e)


    # def createNewLogEmailInOdoo(self, log_email_dict, hubspot_instance):
    #     try:
    #         newLogEmailModifiedDate = 10000000.0
    #         mail_activity_obj = self.env['mail.activity']
    #         res_partner_obj = self.env['res.partner']
    #         res_users_obj = self.env['res.users']
    #
    #         for log_email_dict_details in log_email_dict:
    #             mail_activity_dict = {}
    #             user_id = None
    #
    #             # HubSpot ID
    #             hubspot_id = log_email_dict_details.get('engagement', {}).get('id')
    #             if not hubspot_id:
    #                 logger.warning("⚠️ Missing HubSpot ID in log email record. Skipping.")
    #                 continue
    #
    #             # ✅ SKIP if mail.message already exists for this HubSpot ID
    #             existing_message = self.env['mail.message'].sudo().search([
    #                 ('hubspot_id', '=', str(hubspot_id))
    #             ], limit=1)
    #             if existing_message:
    #                 logger.info(
    #                     f"⚡ Skipping Log Email creation — mail.message already exists for HubSpot ID: {hubspot_id}")
    #                 continue
    #
    #             # Get last updated
    #             if log_email_dict_details.get('engagement', {}).get('lastUpdated'):
    #                 newLogEmailModifiedDate = int(log_email_dict_details['engagement']['lastUpdated'])
    #
    #             # Created Date
    #             if log_email_dict_details.get('engagement', {}).get('createdAt'):
    #                 hubspot_created_date = self.convert_to_gmt_timestamp(
    #                     log_email_dict_details['engagement']['createdAt'])
    #                 mail_activity_dict['hubspot_created_date'] = hubspot_created_date
    #
    #             # Owner / Assigned User
    #             if log_email_dict_details.get('engagement', {}).get('ownerId'):
    #                 hubspot_owner_id = log_email_dict_details['engagement']['ownerId']
    #                 assigned_partner = res_partner_obj.search([
    #                     ('hubspot_id', '=', hubspot_owner_id),
    #                     ('hubspot_instance_id', '=', hubspot_instance.id)
    #                 ], limit=1)
    #
    #                 if not assigned_partner:
    #                     assigned_partner = res_partner_obj.getOwnerDetailsFromHubspot(hubspot_owner_id,
    #                                                                                   hubspot_instance)
    #
    #                 if assigned_partner:
    #                     mail_activity_dict['hubspot_assigned_user_id'] = assigned_partner.id
    #                     existing_user = res_users_obj.sudo().search([
    #                         ('partner_id', '=', assigned_partner.id)
    #                     ], limit=1)
    #
    #                     if existing_user:
    #                         mail_activity_dict['user_id'] = existing_user.id
    #                         user_id = existing_user.id
    #                     else:
    #                         portal_wizard = self.env['portal.wizard'].sudo().create({
    #                             'partner_ids': [(4, assigned_partner.id)]
    #                         })
    #                         wizard_user = portal_wizard.user_ids.filtered(
    #                             lambda u: u.partner_id.id == assigned_partner.id
    #                         )
    #                         if wizard_user:
    #                             wizard_user.action_grant_access()
    #                             new_user = res_users_obj.sudo().search([
    #                                 ('partner_id', '=', assigned_partner.id)
    #                             ], limit=1)
    #                             if new_user:
    #                                 new_user.sudo().write({
    #                                     'group_ids': [(6, 0, [
    #                                         self.env.ref('base.group_system').id,
    #                                         self.env.ref('sales_team.group_sale_manager').id
    #                                     ])]
    #                                 })
    #                                 mail_activity_dict['user_id'] = new_user.id
    #                                 user_id = new_user.id
    #
    #             # Activity Type
    #             if log_email_dict_details.get('engagement', {}).get('type') == 'EMAIL':
    #                 mail_activity_type_id = self.env['mail.activity.type'].sudo().search(
    #                     [('name', '=', 'Email')], limit=1)
    #                 if mail_activity_type_id:
    #                     mail_activity_dict['activity_type_id'] = mail_activity_type_id.id
    #
    #             # Summary / Note
    #             mail_activity_dict['summary'] = log_email_dict_details.get('engagement', {}).get('bodyPreview', '')
    #             mail_activity_dict['note'] = log_email_dict_details.get('engagement', {}).get('bodyPreviewHtml', '')
    #
    #             # Store HubSpot ID
    #             mail_activity_dict['hubspot_id'] = hubspot_id
    #
    #             # Deadline
    #             if log_email_dict_details.get('engagement', {}).get('timestamp'):
    #                 mail_activity_dict['date_deadline'] = self.convert_epoch_to_gmt_timestamp(
    #                     log_email_dict_details['engagement']['timestamp'])
    #
    #             # Default model info (required)
    #             default_model = self.env['ir.model']._get('res.partner')
    #             mail_activity_dict.setdefault('res_model_id', default_model.id)
    #             mail_activity_dict.setdefault('res_model', 'res.partner')
    #
    #             # Associations
    #             associations = log_email_dict_details.get('associations', {})
    #             if 'contactIds' in associations and associations.get('contactIds'):
    #                 for hubspot_contact_id in associations['contactIds']:
    #                     res_partner_id = res_partner_obj.sudo().search([
    #                         ('is_company', '=', False),
    #                         ('hubspot_id', '=', hubspot_contact_id),
    #                         ('hubspot_instance_id', '=', hubspot_instance.id)
    #                     ], limit=1)
    #                     if res_partner_id:
    #                         mail_activity_dict['res_id'] = res_partner_id.id
    #
    #             elif 'companyIds' in associations and associations.get('companyIds'):
    #                 for hubspot_company_id in associations['companyIds']:
    #                     res_partner_company_id = res_partner_obj.sudo().search([
    #                         ('is_company', '=', True),
    #                         ('hubspot_id', '=', hubspot_company_id),
    #                         ('hubspot_instance_id', '=', hubspot_instance.id)
    #                     ], limit=1)
    #                     if res_partner_company_id:
    #                         mail_activity_dict['res_id'] = res_partner_company_id.id
    #
    #             elif 'dealIds' in associations and associations.get('dealIds'):
    #                 for hubspot_lead_id in associations['dealIds']:
    #                     lead_id = self.env['crm.lead'].sudo().search([
    #                         ('type', '=', 'opportunity'),
    #                         ('hubspot_id', '=', hubspot_lead_id),
    #                         ('hubspot_instance_id', '=', hubspot_instance.id)
    #                     ], limit=1)
    #                     if lead_id:
    #                         mail_activity_dict['res_id'] = lead_id.id
    #                         mail_activity_dict['res_model_id'] = self.env['ir.model']._get('crm.lead').id
    #                         mail_activity_dict['res_model'] = 'crm.lead'
    #
    #             # Create mail activity
    #             mail_activity_dict['hubspot_instance_id'] = hubspot_instance.id
    #             if user_id:
    #                 create_mail_activity_id = mail_activity_obj.with_user(user_id).with_context(
    #                     {'from_hubspot': True}
    #                 ).create(mail_activity_dict)
    #             else:
    #                 create_mail_activity_id = mail_activity_obj.sudo().with_context(
    #                     {'from_hubspot': True}
    #                 ).create(mail_activity_dict)
    #
    #             # Mark as done (will create mail.message)
    #             # create_mail_activity_id._action_done()
    #             create_mail_activity_id.with_context(hubspot_id=hubspot_id)._action_done()
    #
    #             logger.info(
    #                 f"✅ Created and Marked Done Log Email Activity {create_mail_activity_id.id} for HubSpot ID {hubspot_id}"
    #             )
    #
    #             hubspot_instance.modifiedDateForLogEmail = newLogEmailModifiedDate
    #             logger.info(
    #                 f"✅ Completed Log Email Sync for HubSpot ID {hubspot_id} → Activity ID {create_mail_activity_id.id}")
    #             self._cr.commit()
    #
    #     except Exception as e:
    #         error_message = f'Error while creating HubSpot log email in Odoo: {log_email_dict}\nException: {str(e)}'
    #         self.env['hubspot.logger'].create_log_message('Import Log Email', error_message)
    #         logger.exception("Exception in createNewLogEmailInOdoo:\n" + error_message)
    #         hubspot_instance._raise_user_error(e)

    def _cron_export_log_email_to_hubspot(self):
        hubspot_instance_obj = self.env['hubspot.instance'].search([('active', '=', True),('hubspot_is_export_log_email', '=', True)])
        for hubspot_instance in hubspot_instance_obj:
            self.export_log_email_to_hubspot(hubspot_instance)

    def export_log_email_to_hubspot(self, hubspot_instance):
        mail_activity_ids = self.env['mail.activity'].search([('hubspot_id', '=', False)])
        if hubspot_instance.default_instance and hubspot_instance.active and hubspot_instance.hubspot_is_export_log_email:
            for mail_activity_id in mail_activity_ids:
                if not mail_activity_id.hubspot_id and mail_activity_id.activity_type_id.name == 'Email':
                    mail_activity_id.createNewLogEmailInHubspot(hubspot_instance)

    def createNewLogEmailInHubspot(self, hubspot_instance):
        for eachNewLogActivity in self:
            # create hubspot dictionary
            properties = {}
            metadata_dict = {}
            engagement_dict = {}
            associations_list = []
            associations_dict = {}
            if eachNewLogActivity.summary:
                engagement_dict['bodyPreview'] = eachNewLogActivity.summary
            if eachNewLogActivity.note:
                metadata_dict['html'] = eachNewLogActivity.note
                engagement_dict['bodyPreviewHtml'] = eachNewLogActivity.note

            if eachNewLogActivity.activity_type_id:
                if eachNewLogActivity.activity_type_id.name == 'Email':
                    engagement_dict['type'] = 'EMAIL'
            if eachNewLogActivity.date_deadline:
                engagement_dict['timestamp'] = self.convert_time_to_unix_timestamp(eachNewLogActivity.date_deadline)
            if eachNewLogActivity.res_id:
                if eachNewLogActivity.res_model == 'res.partner':
                    partner_id = self.env['res.partner'].sudo().search(
                        [('hubspot_instance_id', '=', hubspot_instance.id), ('id', '=', eachNewLogActivity.res_id)])
                    if partner_id.hubspot_id and not partner_id.is_company:
                        associations_dict['contactIds'] = [partner_id.hubspot_id]
                    else:
                        associations_dict['contactIds'] = []
                    if partner_id.hubspot_id and partner_id.is_company:
                        associations_dict['companyIds'] = [partner_id.hubspot_id]
                    else:
                        associations_dict['companyIds'] = []
                if eachNewLogActivity.res_model == 'crm.lead':
                    lead_id = self.env['crm.lead'].sudo().search(
                        [('hubspot_instance_id', '=', hubspot_instance.id), ('id', '=', eachNewLogActivity.res_id)])
                    if lead_id.hubspot_id:
                        associations_dict['dealIds'] = [lead_id.hubspot_id]
                else:
                    associations_dict['dealIds'] = []
            # user (Owner) sync
            if eachNewLogActivity.user_id:
                if eachNewLogActivity.user_id.hubspot_uid and eachNewLogActivity.user_id.hubspot_instance_id.id == hubspot_instance.id:
                    associations_dict['ownerIds'] = [eachNewLogActivity.user_id.hubspot_uid]
                    engagement_dict['ownerId'] = eachNewLogActivity.user_id.hubspot_uid
            engagement_dict['active'] = 'true'
            engagement_dict['type'] = 'EMAIL'
            engagement_dict['source'] = 'CRM_UI'
            account_details = self.get_portal_hubspot_account_details(hubspot_instance)
            if account_details:
                engagement_dict['portalId'] = account_details['portalId']
            properties = {"engagement": engagement_dict, 'associations': associations_dict, 'metadata': metadata_dict}
            if properties:
                try:
                    response = hubspot_instance._send_post_request('/engagements/v1/engagements', properties)
                    json_response = json.loads(response)
                    eachNewLogActivity.with_context({'from_hubspot': True}).hubspot_id = json_response['engagement'][
                        'id']
                    eachNewLogActivity.hubspot_instance_id = hubspot_instance.id
                except Exception as e_log:
                    error_message = 'Error while exporting odoo Log Email %d \n\n Odoo vals: %s\n Hubspot response %s' % (
                        eachNewLogActivity.id, str(properties), str(e_log))
                    self.env['hubspot.logger'].create_log_message('Export Log Email', error_message)
                    logger.exception("Exception in Hubspot Connection  :\n" + str(e_log))
                    hubspot_instance._raise_user_error(e_log)

        message = 'Exported Log Email successfully'
        self.env['hubspot.logger'].create_log_message('Export Log Email', message)
        logger.info('Exported Log Email successfully...')

    def UpdateLogEmailInHubspot(self, hubspot_instance):
        for eachNewLogActivity in self:
            # create hubspot dictionary
            properties = {}
            metadata_dict = {}
            engagement_dict = {}
            associations_list = []
            associations_dict = {}
            if eachNewLogActivity.summary:
                engagement_dict['bodyPreview'] = eachNewLogActivity.summary
            if eachNewLogActivity.note:
                metadata_dict['html'] = eachNewLogActivity.note
                engagement_dict['bodyPreviewHtml'] = eachNewLogActivity.note
            if eachNewLogActivity.activity_type_id:
                if eachNewLogActivity.activity_type_id.name == 'Email':
                    engagement_dict['type'] = 'EMAIL'
            if eachNewLogActivity.date_deadline:
                engagement_dict['timestamp'] = self.convert_time_to_unix_timestamp(eachNewLogActivity.date_deadline)
            if eachNewLogActivity.res_id:
                if eachNewLogActivity.res_model == 'res.partner':
                    partner_id = self.env['res.partner'].sudo().search(
                        [('hubspot_instance_id', '=', hubspot_instance.id), ('id', '=', eachNewLogActivity.res_id)])
                    if partner_id.hubspot_id and not partner_id.is_company:
                        associations_dict['contactIds'] = [partner_id.hubspot_id]
                    else:
                        associations_dict['contactIds'] = []
                    if partner_id.hubspot_id and partner_id.is_company:
                        associations_dict['companyIds'] = [partner_id.hubspot_id]
                    else:
                        associations_dict['companyIds'] = []
                if eachNewLogActivity.res_model == 'crm.lead':
                    lead_id = self.env['crm.lead'].sudo().search(
                        [('hubspot_instance_id', '=', hubspot_instance.id), ('id', '=', eachNewLogActivity.res_id)])
                    if lead_id.hubspot_id:
                        associations_dict['dealIds'] = [lead_id.hubspot_id]
                else:
                    associations_dict['dealIds'] = []
            # user (Owner) sync
            if eachNewLogActivity.user_id:
                # if not eachNewActivity.user_id.hubspot_uid:
                #     logger.warning("Odoo User Not Available In Hubspot")
                #     self.env['res.users'].syncAllUsers()
                if eachNewLogActivity.user_id.hubspot_uid and eachNewLogActivity.user_id.hubspot_instance_id.id == hubspot_instance.id:
                    associations_dict['ownerIds'] = [eachNewLogActivity.user_id.hubspot_uid]
                    engagement_dict['ownerId'] = eachNewLogActivity.user_id.hubspot_uid
            engagement_dict['active'] = 'true'
            engagement_dict['type'] = 'EMAIL'
            engagement_dict['source'] = 'CRM_UI'
            account_details = self.get_portal_hubspot_account_details(hubspot_instance)
            if account_details:
                engagement_dict['portalId'] = account_details['portalId']
            properties = {"engagement": engagement_dict, 'associations': associations_dict, 'metadata': metadata_dict}
            if properties:
                try:
                    response = hubspot_instance._send_patch_request('/engagements/v1/engagements/'+ eachNewLogActivity.hubspot_id, properties)
                    parsed_resp = json.loads(response)
                    eachNewLogActivity.with_context({'from_hubspot': True}).hubspot_id = parsed_resp['engagement']['id']
                    eachNewLogActivity.with_context({'from_hubspot': True}).hubspot_instance_id = hubspot_instance.id
                except Exception as e_log:
                    error_message = 'Error while exporting odoo log email %d \n\n Odoo vals: %s\n Hubspot response %s' % (
                        eachNewLogActivity.id, str(properties), str(e_log))
                    self.env['hubspot.logger'].create_log_message('Export Email Log', error_message)
                    logger.exception("Exception in Hubspot Connection  :\n" + str(e_log))
                    hubspot_instance._raise_user_error(e_log)

                logger.info('Completed Updating Email Log in hubspot')


    @api.model
    def _cron_import_call_from_hubspot(self):
        hubspot_instance_obj = self.env['hubspot.instance'].search(
            [('active', '=', True),('hubspot_is_import_calls', '=', True)])
        for hubspot_instance in hubspot_instance_obj:
            self.import_call_from_hubspot(hubspot_instance)

    def import_call_from_hubspot(self, hubspot_instance):
        modifiedDateForCall= float(hubspot_instance.modifiedDateForCall or 0)
        all_call = float(hubspot_instance.all_call or 0)
        if hubspot_instance.hubspot_is_import_calls and hubspot_instance.active:  
            logger.info('Getting All lOG  Calls from hubspot---------------------------')
            try:
                has_more = True
                offset = 0
                while has_more:
                    call_ids = []
                    record_limit = 100
                    response_all_calls = hubspot_instance._send_get_request('/engagements/v1/engagements/paged?offset=' + str(offset) + '&limit=' + str(record_limit))
                    json_response_all_calls = json.loads(response_all_calls)
                    has_more = json_response_all_calls.get('hasMore')
                    offset = json_response_all_calls.get('offset')
                    for call_id in json_response_all_calls.get('results'):
                        if call_id['engagement']['id'] and call_id['engagement']['type'] == 'CALL':
                            call_ids.append(call_id['engagement']['id'])
                    if call_ids:
                        self.get_task_details_and_create(call_ids, hubspot_instance)
                    hubspot_instance.all_call = True
                message = 'Completed Getting All Log Calls from hubspot'
                self.env['hubspot.logger'].create_log_message('Import Log Calls', message)
                logger.info(
                    'Completed Getting All lOG Calls from hubspot------------------------------------------------------')
            except Exception as e:
                error_message = 'Error while getting calls in odoo \nHubspot response %s' % (str(e))
                self.env['hubspot.logger'].create_log_message('Import Calls', error_message)
                logger.exception("Error in Getting All Calls From Hubspot------------>\n" + error_message)
                hubspot_instance._raise_user_error(e)
        else:
            logger.info('Getting modified LOG Calls from hubspot-------------------')
            try:
                has_more = True
                offset = 0
                while has_more:
                    updated_call_ids = []
                    record_limit = 100
                    response_get_all_calls = hubspot_instance._send_get_request('/engagements/v1/engagements/recent/modified?offset=' + str(offset) + '&count=' + str(record_limit))
                    json_response_get_all_calls = json.loads(response_get_all_calls)
                    record_limit += 1
                    offset = json_response_get_all_calls.get('offset')
                    for callId in json_response_get_all_calls.get('results'):
                        if callId['engagement']['id'] and callId['engagement']['type'] == 'CALL':
                            if (int(callId['engagement']['lastUpdated'])) <= int(modifiedDateForCall):
                                break  # Skip Not recently updated task
                            elif (int(callId.get('engagement')['lastUpdated'])) > int(modifiedDateForCall):
                                updated_call_ids.append(callId['engagement']['id'])
                                updated_call_ids.reverse()
                    if hubspot_instance.active  and updated_call_ids and hubspot_instance.hubspot_is_import_calls:
                        self.get_task_details_and_create(updated_call_ids, hubspot_instance)
                    else:
                        break

                message = 'Completed Getting All LOG  Calls from hubspot'
                self.env['hubspot.logger'].create_log_message('Import Calls', message)
                logger.info(
                    'Completed Getting modified log calls from hubspot------------------------------------------------------')
                
            
            except Exception as e:
                error_message = 'Error while getting calls in odoo \nHubspot response %s' % (str(e))
                self.env['hubspot.logger'].create_log_message('Import Log Calls', error_message)
                logger.exception("Error in Getting All log Calls From Hubspot------------>\n" + error_message)
                hubspot_instance._raise_user_error(e)
      


    @api.model
    def createNewLogCallInOdoo(self, call_log_info, hubspot_instance):
        try:
            newcallModifiedDate = 10000000.0
            call_activity_obj = self.env['mail.activity']
            mail_message_obj = self.env['mail.message']
            res_partner_obj = self.env['res.partner']
            res_users_obj = self.env['res.users']

            for log_call_details in call_log_info:
                call_activity_dict_base = {}
                user_id = None

                # --- HubSpot ID deduplication check ---
                hubspot_id = log_call_details.get('engagement', {}).get('id')
                if not hubspot_id:
                    continue

                existing_hubspot = mail_message_obj.sudo().search([
                    ('hubspot_id', '=', str(hubspot_id))
                ], limit=1)
                if existing_hubspot:
                    logger.info(f"⚡ Skipping existing Call log with HubSpot ID: {hubspot_id}")
                    continue

                # --- Last Updated ---
                if 'lastUpdated' in log_call_details.get('engagement', {}):
                    if log_call_details['engagement']['lastUpdated']:
                        newcallModifiedDate = int(log_call_details['engagement']['lastUpdated'])

                # --- Created Date ---
                if 'createdAt' in log_call_details.get('engagement', {}):
                    call_activity_dict_base['hubspot_created_date'] = self.convert_to_gmt_timestamp(
                        log_call_details['engagement']['createdAt'])

                # --- Activity Type ---
                call_activity_type_id = self.env['mail.activity.type'].sudo().search(
                    [('name', '=', 'Call')], limit=1)
                if call_activity_type_id:
                    call_activity_dict_base['activity_type_id'] = call_activity_type_id.id

                # --- Summary with hubspot date time ---
                if 'timestamp' in log_call_details.get('engagement', {}):
                    call_activity_dict_base['summary'] = self.convert_to_gmt_timestamp(
                        log_call_details['engagement']['timestamp'])

                # --- Note ---
                call_activity_dict_base['note'] = log_call_details.get('engagement', {}).get('bodyPreviewHtml', '')

                # --- Owner assignment ---
                if 'ownerId' in log_call_details.get('engagement', {}):
                    hubspot_owner_id = log_call_details['engagement']['ownerId']
                    assigned_partner = res_partner_obj.search([
                        ('hubspot_id', '=', hubspot_owner_id),
                        ('hubspot_instance_id', '=', hubspot_instance.id)
                    ], limit=1)

                    if not assigned_partner:
                        assigned_partner = res_partner_obj.getOwnerDetailsFromHubspot(hubspot_owner_id,
                                                                                      hubspot_instance)

                    if assigned_partner:
                        call_activity_dict_base['hubspot_assigned_user_id'] = assigned_partner.id
                        existing_user = res_users_obj.sudo().search([
                            ('partner_id', '=', assigned_partner.id)
                        ], limit=1)

                        if existing_user:
                            call_activity_dict_base['user_id'] = existing_user.id
                            user_id = existing_user.id
                        else:
                            portal_wizard = self.env['portal.wizard'].sudo().create({
                                'partner_ids': [(4, assigned_partner.id)]
                            })
                            wizard_user = portal_wizard.user_ids.filtered(
                                lambda u: u.partner_id.id == assigned_partner.id
                            )
                            if wizard_user:
                                wizard_user.action_grant_access()
                                new_user = res_users_obj.sudo().search([
                                    ('partner_id', '=', assigned_partner.id)
                                ], limit=1)
                                if new_user:
                                    new_user.sudo().write({
                                        'group_ids': [(6, 0, [
                                            # self.env.ref('base.group_user').id,
                                            self.env.ref('base.group_system').id,
                                            self.env.ref('sales_team.group_sale_manager').id
                                        ])]
                                    })
                                    call_activity_dict_base['user_id'] = new_user.id
                                    user_id = new_user.id

                # --- HubSpot ID ---
                call_activity_dict_base['hubspot_id'] = hubspot_id
                call_activity_dict_base['hubspot_instance_id'] = hubspot_instance.id

                # --- Association Processing (Multiple Activities) ---
                processed_associations = []

                for assoc_type in ['dealIds', 'contactIds', 'companyIds']:
                    if assoc_type in log_call_details.get('associations', {}):
                        for assoc_id in log_call_details['associations'][assoc_type]:
                            record = None

                            if assoc_type == 'dealIds':
                                record = self.env['crm.lead'].sudo().search([
                                    ('type', '=', 'opportunity'),
                                    ('hubspot_id', '=', assoc_id),
                                    ('hubspot_instance_id', '=', hubspot_instance.id)
                                ], limit=1)
                                if not record:
                                    logger.warning(
                                        f"Lead with HubSpot ID {assoc_id} not found in Odoo. Skipping activity creation.")
                                    continue

                            elif assoc_type == 'contactIds':
                                record = res_partner_obj.sudo().search([
                                    ('is_company', '=', False),
                                    ('hubspot_id', '=', assoc_id),
                                    ('hubspot_instance_id', '=', hubspot_instance.id)
                                ], limit=1)

                            elif assoc_type == 'companyIds':
                                record = res_partner_obj.sudo().search([
                                    ('is_company', '=', True),
                                    ('hubspot_id', '=', assoc_id),
                                    ('hubspot_instance_id', '=', hubspot_instance.id)
                                ], limit=1)

                            if record and record.id not in processed_associations:
                                processed_associations.append(record.id)

                                # Get the correct model reference
                                model_id = self.env['ir.model']._get(record._name).id

                                call_activity_dict = call_activity_dict_base.copy()
                                call_activity_dict.update({
                                    'res_model_id': model_id,
                                    'res_id': record.id,
                                    'res_model': record._name
                                })

                                if user_id:
                                    new_call_activity = call_activity_obj.with_user(user_id).with_context(
                                        {'from_hubspot': True}
                                    ).create(call_activity_dict)
                                else:
                                    new_call_activity = call_activity_obj.sudo().with_context(
                                        {'from_hubspot': True}
                                    ).create(call_activity_dict)

                                # ✅ Automatically mark as Done
                                # new_call_activity._action_done()
                                new_call_activity.with_context(hubspot_id=hubspot_id)._action_done()
                                logger.info(
                                    f"✅ Created and marked Done Call Activity {new_call_activity.id} for HubSpot ID {hubspot_id}")

                hubspot_instance.modifiedDateForCall = newcallModifiedDate

        except Exception as e:
            error_message = f'Error while creating hubspot log call in odoo: {call_activity_dict_base}\nException: {str(e)}'
            self.env['hubspot.logger'].create_log_message('Import Log Calls', error_message)
            logger.exception("Exception in Creating New Log calls in Odoo :\n" + error_message)
            hubspot_instance._raise_user_error(e)
