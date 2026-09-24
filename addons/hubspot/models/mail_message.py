import logging
import json,requests

from odoo import api, fields, models, _
import base64,zlib
logger = logging.getLogger(__name__)
from odoo.tools import config
config['limit_time_real'] = 10000000
from PIL import Image
from io import BytesIO,StringIO
import urllib.request



class MailMessage(models.Model):
    _inherit = "mail.message"

    hubspot_id = fields.Char('Hubspot Id',  store=True, readonly=True, copy=False)
    hubspot_instance_id = fields.Many2one('hubspot.instance', 'Hubspot Instance Name', help="Hubspot Instance Name", readonly=True, copy=False)
    hubspot_object = fields.Selection([('note', 'Note'), ('mail', 'Mail'), ('task', 'Task')], string='Hubspot Object')

    # def unlink(self):
    #     '''Delete contact in hubspot on delete of contact or company in odoo'''
    #     for record in self:
    #         mail_subtype_id = self.env.ref('mail.mt_comment').id
    #         note_subtype_id = self.env.ref('mail.mt_note').id

    #         if record.hubspot_instance_id and record.hubspot_instance_id.active and record.hubspot_instance_id.hubspot_sync_notes and record.subtype_id.id == note_subtype_id:
    #             record.deleteFromHubspot(record.hubspot_instance_id)
    #             self._cr.commit()
    #         if record.hubspot_instance_id.hubspot_sync_email and record.hubspot_instance_id and record.hubspot_instance_id.active and record.message_type == 'comment' and record.subtype_id.id == mail_subtype_id:
    #             record.deleteEmailFromHubspot(record.hubspot_instance_id)
    #             self._cr.commit()
    #     return super(MailMessage, self).unlink()

    # def deleteFromHubspot(self, hubspot_instance_id):
    #     logger.info('Delete from hubspot')
    #     try:
    #         headers = {}
    #         for each in self:
    #             hubspot_instance_id._send_delete_request('/engagements/v1/engagements/' + str(each.hubspot_id))

    #     except Exception as e:
    #         error_message = 'Error while deleting Mail message in hubspot \nHubspot response %s' % (str(e))
    #         self.env['hubspot.logger'].create_log_message('Mail message', error_message)
    #         logger.exception("Error in deleted Mail message From Hubspot------------>\n" + str(e))
    #         hubspot_instance_id._raise_user_error(e)

    # def deleteEmailFromHubspot(self, hubspot_instance_id):
    #     logger.info('Delete from hubspot')
    #     try:
    #         for each in self:
    #             hubspot_instance_id._send_delete_request('/engagements/v1/engagements/' + str(each.hubspot_id))

    #     except Exception as e:
    #         error_message = 'Error while deleting Mail mail in hubspot \nHubspot response %s' % (str(e))
    #         self.env['hubspot.logger'].create_log_message('Mail mail', error_message)
    #         logger.exception("Error in deleted Mail mail From Hubspot------------>\n" + str(e))
    #         hubspot_instance_id._raise_user_error(e)

    #     logger.info('Completed Delete from hubspot')

    @api.model
    def _cron_import_note_from_hubspot(self):
        hubspot_instance_obj = self.env['hubspot.instance'].search([('active', '=', True),('hubspot_is_import_notes', '=', True)])
        for hubspot_instance in hubspot_instance_obj:
            self.import_note_from_hubspot(hubspot_instance)

    def import_note_from_hubspot(self, hubspot_instance):
        modifiedDateForNotes = float(hubspot_instance.modifiedDateForNotes or 0)

        all_note = float(hubspot_instance.all_notes or 0)
        if hubspot_instance.hubspot_is_import_notes and hubspot_instance.active: 
            logger.info('Getting All note from hubspot---------------------------')
            try:
                has_more = True
                offset = 0
                while has_more:
                    note_ids = []
                    record_limit = 90
                    response_get_all_notes = hubspot_instance._send_get_request('/engagements/v1/engagements/paged?offset=' + str(offset) + '&count=' + str(record_limit))
                    json_response_get_all_notes = json.loads(response_get_all_notes)
                    has_more = json_response_get_all_notes.get('hasMore')
                    offset = json_response_get_all_notes.get('offset')
                    for note_id in json_response_get_all_notes.get('results'):
                        if note_id['engagement']['id'] and note_id['engagement']['type'] == 'NOTE':
                            note_ids.append(note_id['engagement']['id'])
                    if note_ids:
                        self.env['mail.activity'].get_task_details_and_create(note_ids, hubspot_instance)
                hubspot_instance.all_notes = True
                message = 'Completed Getting All Note from hubspot'
                self.env['hubspot.logger'].create_log_message('Import Note', message)
                logger.info('Completed Getting All Note from hubspot------------------------------------------------------')
            except Exception as e:
                error_message = 'Error while getting Note in odoo \nHubspot response %s' % (str(e))
                self.env['hubspot.logger'].create_log_message('Import Note', error_message)
                logger.exception("Error in Getting All Note From Hubspot------------>\n" + error_message)
                hubspot_instance._raise_user_error(e)
        else:

            logger.info('Getting modified note from hubspot-------------------')
            try:
                has_more = True
                offset = 0
                while has_more:
                    updated_note_ids = []
                    record_limit = 100
                    response_get_all_notes = hubspot_instance._send_get_request('/engagements/v1/engagements/recent/modified?offset=' + str(offset) + '&count=' + str(record_limit))
                    json_response_all_notes = json.loads(response_get_all_notes)
                    record_limit += 1
                    offset = json_response_all_notes.get('offset')
                    has_more = json_response_all_notes.get('hasMore')
                    for noteId in json_response_all_notes.get('results'):
                        if noteId['engagement']['id'] and noteId['engagement']['type'] == 'NOTE':
                            if (int(noteId['engagement']['lastUpdated'])) <= int(modifiedDateForNotes):
                                break  # Skip Not recently updated note
                            elif (int(noteId.get('engagement')['lastUpdated'])) > int(modifiedDateForNotes):
                                updated_note_ids.append(noteId['engagement']['id'])
                                updated_note_ids.reverse()
                    if updated_note_ids and hubspot_instance.hubspot_is_import_notes  and hubspot_instance.active:
                        self.env['mail.activity'].get_task_details_and_create(updated_note_ids, hubspot_instance)
                    else:
                        break
                    # new_modifiedDateForTask = updatedTaskList['results'][0]['properties']['hs_lastmodifieddate']['value']
                    # hubspot_instance.modifiedDateForNotes = new_modifiedDateForTask
                    # hubspot_instance.all_task = True

                message = 'Completed Getting All note from hubspot'
                self.env['hubspot.logger'].create_log_message('Import Note', message)
                logger.info('Completed Getting modified note from hubspot------------------------------------------------------')
            except Exception as e:
                error_message = 'Error while getting note in odoo \nHubspot response %s' % (str(e))
                self.env['hubspot.logger'].create_log_message('Import note', error_message)
                logger.exception("Error in getModifiedNoteFromHubspot------------>\n" + str(e))
                hubspot_instance._raise_user_error(e)


    def action_import_skip_notes(self, hubspot_instance):
        if  hubspot_instance.hubspot_is_import_notes and hubspot_instance.active:  
            logger.info('Getting All skipped note from hubspot---------------------------')
            try:
                has_more = True
                offset = 0
                while has_more:
                    note_ids = []
                    record_limit = 90
                    response_get_all_notes = hubspot_instance._send_get_request('/engagements/v1/engagements/paged?offset=' + str(offset) + '&limit=' + str(record_limit))
                    json_response_get_all_notes = json.loads(response_get_all_notes)

                    has_more = json_response_get_all_notes.get('hasMore')
                    offset = json_response_get_all_notes.get('offset')
                    for note_id in json_response_get_all_notes['results']:
                        if note_id.get('engagement').get('id') and note_id['engagement']['type'] == 'NOTE':
                            # mail_message_id = self.env['mail.message'].sudo().search(
                            #     [('hubspot_instance_id', '=', hubspot_instance.id), ('hubspot_id', '=', note_id.get('engagement').get('id')), ('hubspot_object', '=', 'note')])
                            # if not mail_message_id:
                            note_ids.append(note_id['engagement']['id'])
                    if len(note_ids) > 0:
                        logger.info('\n\n\nAll skipped notes ------------------------------------------\n{}'.format(note_ids))
                        logger.info('\n\n\nTotal skipped notes {}'.format(len(note_ids)))
                        self.env['mail.activity'].with_context({'from_skipped_notes': True}).get_task_details_and_create(note_ids, hubspot_instance)
                message = 'Completed Getting skipped Note from hubspot'
                self.env['hubspot.logger'].create_log_message('Import Note', message)
                logger.info('Completed Getting skipped Note from hubspot------------------------------------------------------')
            except Exception as e:
                error_message = 'Error while getting skipped Notes in odoo \nHubspot response %s' % (str(e))
                self.env['hubspot.logger'].create_log_message('Import Note', error_message)
                logger.exception("Error in Getting skipped Note From Hubspot------------>\n" + error_message)
                hubspot_instance._raise_user_error(e)

    @api.model
    def createNewNoteInOdoo(self, note_dict, hubspot_instance):
        try:
            newNoteModifiedDate = 10000000.0
            properties = []
            mail_message_dict = {}
            mail_message_obj = self.env['mail.message']
            for note_dict_details in note_dict:
                if 'lastUpdated' in note_dict_details['engagement']:
                    if note_dict_details['engagement']['lastUpdated']:
                        newNoteModifiedDate = int(note_dict_details['engagement']['lastUpdated'])

                # if 'ownerId' in note_dict_details['engagement']:
                #     user_id = self.env['res.partner'].search([('hubspot_id', '=', note_dict_details['engagement']['ownerId']), ('hubspot_instance_id', '=', hubspot_instance.id)],
                #                                            limit=1)
                #     if not user_id:
                #         user_id = self.env['res.partner'].getOwnerDetailsFromHubspot(note_dict_details['engagement']['ownerId'], hubspot_instance)
                #         if user_id:
                #             mail_message_dict['hubspot_id'] = user_id.id
                #     else:
                #         mail_message_dict['hubspot_id'] = user_id.id

                if 'ownerId' in note_dict_details['engagement']:
                    # Step 1: Find the HubSpot owner in res.partner
                    partner_owner = self.env['res.partner'].search([
                        ('hubspot_id', '=', note_dict_details['engagement']['ownerId']),
                        ('hubspot_instance_id', '=', hubspot_instance.id)
                    ], limit=1)

                    # If not found, fetch details from HubSpot and create
                    if not partner_owner:
                        partner_owner = self.env['res.partner'].getOwnerDetailsFromHubspot(
                            note_dict_details['engagement']['ownerId'], hubspot_instance
                        )

                    # Step 2: Map partner to user if possible
                    author_user = False
                    if partner_owner:
                        author_user = self.env['res.users'].sudo().search([
                            ('partner_id', '=', partner_owner.id)
                        ], limit=1)

                    # Step 3: Set author_id
                    if author_user:
                        mail_message_dict['author_id'] = author_user.partner_id.id
                    elif partner_owner:
                        mail_message_dict['author_id'] = partner_owner.id
                    else:
                        # Optional: fallback to admin or skip
                        mail_message_dict['author_id'] = self.env.ref('base.user_admin').partner_id.id

                if 'bodyPreviewHtml' in note_dict_details['engagement']:
                    mail_message_dict['body'] = note_dict_details['engagement']['bodyPreviewHtml']
                if 'id' in note_dict_details['engagement']:
                    mail_message_dict['hubspot_id'] = note_dict_details['engagement']['id']

                if 'timestamp' in note_dict_details['engagement']:
                    mail_message_dict['date'] = self.env['mail.activity'].convert_epoch_to_gmt_timestamp(
                        note_dict_details['engagement']['timestamp'])

                mail_message_dict['message_type'] = 'comment'
                mail_message_dict['hubspot_object'] = 'note'
                mail_message_dict['subtype_id'] = self.env.ref('mail.mt_note').id
                if 'contactIds' in note_dict_details['associations']:
                    for hubspot_contact_id in note_dict_details['associations']['contactIds']:
                        res_partner_id = self.env['res.partner'].sudo().search(
                            [('is_company', '=', False), ('hubspot_id', '=', hubspot_contact_id),
                             ('hubspot_instance_id', '=', hubspot_instance.id)], limit=1)
                        if res_partner_id:
                            mail_message_dict['res_id'] = res_partner_id.id
                            mail_message_dict['record_name'] = res_partner_id.name
                            mail_message_dict['model'] = 'res.partner'
                            mail_message_id = mail_message_obj.sudo().search(
                                [('hubspot_id', '=', note_dict_details['engagement']['id']),
                                 ('res_id', '=', res_partner_id.id), ('model', '=', 'res.partner'),
                                 ('hubspot_instance_id', '=', hubspot_instance.id),
                                 ('hubspot_object', '=', 'note')], limit=1)

                            if mail_message_id:
                                odoo_modifiedDate = self.env['mail.activity'].convert_time_to_unix_timestamp(
                                    mail_message_id.write_date)

                                if self.env.context.get('from_skipped_notes'):
                                    mail_message_id.with_context({'from_hubspot': True}).write(mail_message_dict)
                                    hubspot_instance.modifiedDateForNotes = newNoteModifiedDate
                                    logger.info(
                                        "Write into Existing Odoo Task----------- " + str(mail_message_id.hubspot_id))
                                elif int(newNoteModifiedDate) > int(odoo_modifiedDate):
                                    mail_message_id.with_context({'from_hubspot': True}).write(mail_message_dict)
                                    hubspot_instance.modifiedDateForNotes = newNoteModifiedDate
                                    logger.info(
                                        "Write into Existing Odoo Task----------- " + str(mail_message_id.hubspot_id))
                            if not mail_message_id:
                                if self.env.context.get('from_skipped_notes'):
                                    mail_message_dict['hubspot_instance_id'] = hubspot_instance.id
                                    create_mail_message_id = self.with_context({'from_hubspot': True}).create(
                                        mail_message_dict)
                                    hubspot_instance.modifiedDateForNotes = newNoteModifiedDate
                                    logger.info(
                                        "Created New Note Into Odoo ----------- " + str(create_mail_message_id.id))
                                elif not self.env.context.get('from_skipped_notes'):
                                    mail_message_dict['hubspot_instance_id'] = hubspot_instance.id
                                    create_mail_message_id = self.with_context({'from_hubspot': True}).create(
                                        mail_message_dict)
                                    hubspot_instance.modifiedDateForNotes = newNoteModifiedDate
                                    logger.info(
                                        "Created New Note Into Odoo ----------- " + str(create_mail_message_id.id))

                if 'companyIds' in note_dict_details['associations']:
                    for hubspot_company_id in note_dict_details['associations']['companyIds']:
                        res_partner_company_id = self.env['res.partner'].sudo().search(
                            [('is_company', '=', True), ('hubspot_id', '=', hubspot_company_id),
                             ('hubspot_instance_id', '=', hubspot_instance.id)], limit=1)
                        if res_partner_company_id:
                            mail_message_dict['res_id'] = res_partner_company_id.id
                            mail_message_dict['model'] = 'res.partner'
                            mail_message_dict['record_name'] = res_partner_company_id.name
                            mail_message_id = mail_message_obj.sudo().search(
                                [('hubspot_id', '=', note_dict_details['engagement']['id']),
                                 ('res_id', '=', res_partner_company_id.id), ('model', '=', 'res.partner'),
                                 ('hubspot_instance_id', '=', hubspot_instance.id),
                                 ('hubspot_object', '=', 'note')], limit=1)
                            if mail_message_id:
                                odoo_modifiedDate = self.env['mail.activity'].convert_time_to_unix_timestamp(
                                    mail_message_id.write_date)
                                if self.env.context.get('from_skipped_notes'):
                                    mail_message_id.with_context({'from_hubspot': True}).write(mail_message_dict)
                                    hubspot_instance.modifiedDateForNotes = newNoteModifiedDate
                                    logger.info(
                                        "Write into Existing Odoo Note----------- " + str(mail_message_id.hubspot_id))

                                if int(newNoteModifiedDate) > int(odoo_modifiedDate):
                                    mail_message_id.with_context({'from_hubspot': True}).write(mail_message_dict)
                                    hubspot_instance.modifiedDateForNotes = newNoteModifiedDate
                                    logger.info(
                                        "Write into Existing Odoo Note----------- " + str(mail_message_id.hubspot_id))

                            if not mail_message_id:
                                if self.env.context.get('from_skipped_notes'):
                                    mail_message_dict['hubspot_instance_id'] = hubspot_instance.id
                                    create_mail_message_id = self.with_context({'from_hubspot': True}).create(
                                        mail_message_dict)
                                    hubspot_instance.modifiedDateForNotes = newNoteModifiedDate
                                    logger.info(
                                        "Created New Note Into Odoo ----------- " + str(create_mail_message_id.id))
                                elif not self.env.context.get('from_skipped_notes'):
                                    mail_message_dict['hubspot_instance_id'] = hubspot_instance.id
                                    create_mail_message_id = self.with_context({'from_hubspot': True}).create(
                                        mail_message_dict)
                                    hubspot_instance.modifiedDateForNotes = newNoteModifiedDate
                                    logger.info(
                                        "Created New Note Into Odoo ----------- " + str(create_mail_message_id.id))

                if 'dealIds' in note_dict_details['associations']:
                    for hubspot_lead_id in note_dict_details['associations']['dealIds']:
                        lead_id = self.env['crm.lead'].sudo().search(
                            [('type', '=', 'opportunity'), ('hubspot_id', '=', hubspot_lead_id),
                             ('hubspot_instance_id', '=', hubspot_instance.id)], limit=1)
                        if lead_id:
                            model_id = self.env['ir.model']._get('crm.lead').id
                            mail_message_dict['res_id'] = lead_id.id
                            mail_message_dict['model'] = 'crm.lead'

                            mail_message_dict['record_name'] = lead_id.name
                            if 'attachments' in note_dict_details:
                                for attachment_id_list in note_dict_details['attachments']:
                                    if 'id' in attachment_id_list:
                                        attachment_details = self.get_attachment_by_id(attachment_id_list['id'],
                                                                                       hubspot_instance)
                                        if attachment_details:
                                            create_attachment = self.create_attachment(attachment_details, lead_id,
                                                                                       mail_message_dict['model'])

                            mail_message_id = mail_message_obj.sudo().search(
                                [('hubspot_id', '=', note_dict_details['engagement']['id']),
                                 ('res_id', '=', lead_id.id), ('model', '=', 'crm.lead'),
                                 ('hubspot_instance_id', '=', hubspot_instance.id),
                                 ('hubspot_object', '=', 'note')])

                            if mail_message_id:
                                odoo_modifiedDate = self.env['mail.activity'].convert_time_to_unix_timestamp(
                                    mail_message_id.write_date)
                                if self.env.context.get('from_skipped_notes'):
                                    hubspot_instance.modifiedDateForNotes = newNoteModifiedDate
                                    mail_message_id.with_context({'from_hubspot': True}).write(mail_message_dict)
                                    logger.info(
                                        "Write into Existing Odoo Note----------- " + str(mail_message_id.hubspot_id))

                                if int(newNoteModifiedDate) > int(odoo_modifiedDate):
                                    hubspot_instance.modifiedDateForNotes = newNoteModifiedDate
                                    mail_message_id.with_context({'from_hubspot': True}).write(mail_message_dict)
                                    logger.info(
                                        "Write into Existing Odoo Note----------- " + str(mail_message_id.hubspot_id))
                            if not mail_message_id:
                                if self.env.context.get('from_skipped_notes'):
                                    mail_message_dict['hubspot_instance_id'] = hubspot_instance.id
                                    create_mail_activity_id = self.with_context({'from_hubspot': True}).create(
                                        mail_message_dict)
                                    hubspot_instance.modifiedDateForNotes = newNoteModifiedDate
                                    logger.info(
                                        "Created New Note Into Odoo ----------- " + str(create_mail_activity_id.id))
                                elif not self.env.context.get('from_skipped_notes'):
                                    mail_message_dict['hubspot_instance_id'] = hubspot_instance.id
                                    create_mail_activity_id = self.with_context({'from_hubspot': True}).create(
                                        mail_message_dict)
                                    hubspot_instance.modifiedDateForNotes = newNoteModifiedDate
                                    logger.info("Created New Note Into Odoo ----------- 44444" + str(
                                        create_mail_activity_id.id))
        except Exception as e:
            error_message = 'Error while creating hubspot note in odoo vals: %s\n Hubspot response %s' % (
                note_dict, str(e))
            self.env['hubspot.logger'].create_log_message('Import Note', error_message)
            logger.exception("Exception in Creating New Note in Odoo :\n" + error_message)
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
    

    # @api.model
    # def create_attachment(self, attachment_details, res_id, res_model):
    #     url = attachment_details['url']
    #     file_data = None

    #     if attachment_details['type'] == 'IMG':
    #         response_content = requests.get(url.strip()).content
    #         file_data = base64.b64encode(response_content).replace(b'\n', b'')
    #     elif attachment_details['type'] == 'DOCUMENT':
    #         response_content = requests.get(url.strip()).content
    #         file_data = base64.b64encode(response_content)

    #     if file_data:
            
    #         existing_attachment = self.env['ir.attachment'].search([
    #             ('res_model', '=', res_model),
    #             ('res_id', '=', res_id.id),
    #             ('name', '=', f"{attachment_details['name']}.{attachment_details['extension']}")
    #         ], limit=1)

    #         if not existing_attachment:
                
    #             attachment_id = self.env['ir.attachment'].create({
    #                 'name': f"{attachment_details['name']}.{attachment_details['extension']}",
    #                 'type': 'binary',
    #                 'datas': file_data,
    #                 'res_model': res_model,
    #                 'res_id': res_id.id,
    #             })
    #             return attachment_id
    #         else:
               
    #             return existing_attachment
    #     else:
    #         raise ValueError("Attachment type not supported or file data is None")
    
    @api.model
    def create_attachment(self, attachment_details, res_id, res_model):
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
                ('res_model', '=',  res_model),
                ('res_id', '=', res_id.id),
                ('name', '=', attachment_details['name'])
            ], limit=1)
            
            if not existing_attachment:
                try:
                    attachment_id = self.env['ir.attachment'].create({
                        'name': attachment_details['name'],
                        'type': 'binary',
                        'datas': file_data,
                        'res_model': res_model,
                        'res_id': res_id.id,
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

    @api.model
    def _cron_export_note_to_hubspot(self):
        hubspot_instance_obj = self.env['hubspot.instance'].search([('active', '=', True),  ('hubspot_is_export_notes', '=', True)])
        for hubspot_instance in hubspot_instance_obj:
            self.export_note_to_hubspot(hubspot_instance)

    def export_note_to_hubspot(self, hubspot_instance):
        # Hubspot Information
        hubspot_app_key = hubspot_instance.hubspot_app_key
        hubspot_app_name = hubspot_instance.name

        # if not hubspot_app_key or not hubspot_app_name:
        #     raise UserError(_(
        #         'Error in Synchronization!\nHubspot API Key and App Name need to be specified for synchronization of data with Odoo.'))

        mail_message_ids = self.env['mail.message'].search([('hubspot_id', '=', False)])
        if hubspot_instance.default_instance and hubspot_instance.active  and hubspot_instance.hubspot_is_export_notes:
            for mail_message_id in mail_message_ids:
                if not mail_message_id.hubspot_id and mail_message_id.message_type == 'comment':
                    mail_message_id.createNewNoteInHubspot(hubspot_instance)

    def createNewNoteInHubspot(self, hubspot_instance):
        for eachNewMessage in self:
            # create hubspot dictionary
            properties = {}
            metadata_dict = {}
            engagement_dict = {}
            associations_list = []
            associations_dict = {}
            subtype_id = self.env.ref('mail.mt_note').id
            if eachNewMessage.subtype_id.id == subtype_id:
                if eachNewMessage.date:
                    engagement_dict['timestamp'] = self.env['mail.activity'].convert_time_to_unix_timestamp(eachNewMessage.date)
                if eachNewMessage.res_id:
                    if eachNewMessage.model == 'res.partner':
                        partner_id = self.env['res.partner'].sudo().search([('id', '=', eachNewMessage.res_id), ('hubspot_instance_id', '=', hubspot_instance.id)])
                        if partner_id.hubspot_id and not partner_id.is_company:
                            associations_dict['contactIds'] = [int(partner_id.hubspot_id)]
                        else:
                            associations_dict['contactIds'] = []
                        if partner_id.hubspot_id and partner_id.is_company:
                            associations_dict['companyIds'] = [partner_id.hubspot_id]
                        else:
                            associations_dict['companyIds'] = []
                    if eachNewMessage.model == 'crm.lead':
                        lead_id = self.env['crm.lead'].sudo().search([('id', '=', eachNewMessage.res_id), ('hubspot_instance_id', '=', hubspot_instance.id)])
                        if lead_id.hubspot_id:
                            associations_dict['dealIds'] = [lead_id.hubspot_id]
                        else:
                            associations_dict['dealIds'] = []

                associations_dict['workflowIds'] = []
                associations_dict['ticketIds'] = []
                associations_dict['contentIds'] = []
                associations_dict['quoteIds'] = []
                if eachNewMessage.body:
                    metadata_dict['body'] = eachNewMessage.body
                engagement_dict['active'] = 'true'
                engagement_dict['type'] = 'NOTE'
                account_details = self.env['mail.activity'].get_portal_hubspot_account_details(hubspot_instance)
                if account_details:
                    engagement_dict['portalId'] = account_details['portalId']
                properties = {"engagement": engagement_dict, 'associations': associations_dict, 'metadata': metadata_dict, 'attachments': []}
                if properties:
                    try:
                        response = hubspot_instance._send_post_request('/engagements/v1/engagements', properties)
                        json_response = json.loads(response)
                        eachNewMessage.with_context({'from_hubspot': True}).hubspot_id = json_response['engagement']['id']
                        eachNewMessage.hubspot_instance_id = hubspot_instance.id
                        eachNewMessage.hubspot_object = 'note'

                    except Exception as e_log:
                        error_message = 'Error while exporting odoo message %d \n\n Odoo vals: %s\n Hubspot response %s' % (eachNewMessage.id, str(properties), str(e_log))
                        self.env['hubspot.logger'].create_log_message('Export Activity', error_message)
                        logger.exception("Exception in Hubspot Connection  :\n" + str(e_log))
                        hubspot_instance._raise_user_error(e_log)

                message = 'Exported Note successfully'
                self.env['hubspot.logger'].create_log_message('Export Note', message)
                logger.info('Exported Note successfully...')

    def UpdateNoteInHubspot(self, hubspot_instance):
        for eachNewMessage in self:
            # create hubspot dictionary
            properties = {}
            metadata_dict = {}
            engagement_dict = {}
            associations_list = []
            associations_dict = {}
            if eachNewMessage.date:
                engagement_dict['timestamp'] = self.env['mail.activity'].convert_time_to_unix_timestamp(eachNewMessage.date)
            if eachNewMessage.res_id:
                if eachNewMessage.model == 'res.partner':
                    partner_id = self.env['res.partner'].sudo().search([('id', '=', eachNewMessage.res_id)])
                    if partner_id.hubspot_id and not partner_id.is_company:
                        associations_dict['contactIds'] = [partner_id.hubspot_id]
                    else:
                        associations_dict['contactIds'] = []
                    if partner_id.hubspot_id and partner_id.is_company:
                        associations_dict['companyIds'] = [partner_id.hubspot_id]
                    else:
                        associations_dict['companyIds'] = []
                if eachNewMessage.model == 'crm.lead':
                    lead_id = self.env['crm.lead'].sudo().search([('id', '=', eachNewMessage.res_id)])
                    associations_dict['dealIds'] = [lead_id.hubspot_id]
                else:
                    associations_dict['dealIds'] = []
            # user (Owner) sync
            # if eachNewMessage.moderator_id:
            #     # if not eachNewActivity.user_id.hubspot_uid:
            #     #     logger.warning("Odoo User Not Available In Hubspot")
            #     #     self.env['res.users'].syncAllUsers()
            #     if eachNewMessage.moderator_id.hubspot_uid:
            #         # associations_dict['ownerIds'] = [eachNewMessage.moderator_id.hubspot_uid]
            #         # engagement_dict['ownerId'] = eachNewMessage.moderator_id.hubspot_uid
            #         associations_dict['ownerIds'] = ['60424253']
            #         engagement_dict['ownerId'] = '60424253'
            #     else:
            #         associations_dict['ownerIds'] = []

            if eachNewMessage.body:
                engagement_dict['bodyPreviewHtml'] = eachNewMessage.body
                engagement_dict['bodyPreview'] = eachNewMessage.body
                metadata_dict['body'] = eachNewMessage.body
            engagement_dict['active'] = 'true'
            engagement_dict['type'] = 'NOTE'
            account_details = self.env['mail.activity'].get_portal_hubspot_account_details(hubspot_instance)
            if account_details:
                engagement_dict['portalId'] = account_details['portalId']
                properties = {"engagement": engagement_dict, 'associations': associations_dict, 'metadata': metadata_dict}
                if properties:
                    try:
                        response = hubspot_instance._send_patch_request('/engagements/v1/engagements/'+ eachNewMessage.hubspot_id)
                        parsed_resp = json.loads(response)

                        eachNewMessage.with_context({'from_hubspot': True}).hubspot_id = parsed_resp['engagement']['id']
                        eachNewMessage.hubspot_instance_id = hubspot_instance.id
                    except Exception as e_log:
                        error_message = 'Error while exporting odoo note %d \n\n Odoo vals: %s\n Hubspot response %s' % (eachNewMessage.id, str(properties), str(e_log))
                        self.env['hubspot.logger'].create_log_message('Export Note', error_message)
                        logger.exception("Exception in Hubspot Connection  :\n" + str(e_log))
                        hubspot_instance._raise_user_error(e_log)

        logger.info('Completed Updating note in hubspot')

    @api.model
    def _cron_import_email_from_hubspot(self):
        hubspot_instance_obj = self.env['hubspot.instance'].search([('active', '=', True), ('hubspot_is_import_email', '=', True)])
        for hubspot_instance in hubspot_instance_obj:
            self.import_email_from_hubspot(hubspot_instance)

    def import_email_from_hubspot(self, hubspot_instance):
        modifiedDateForEmail = float(hubspot_instance.modifiedDateForEmail or 0)

        all_email = float(hubspot_instance.all_email or 0)
        if   hubspot_instance.hubspot_is_import_email and hubspot_instance.active and not all_email: 
            logger.info('Getting All email from hubspot---------------------------')
            try:
                has_more = True
                offset = 0
                while has_more:
                    email_ids = []
                    record_limit = 90
                    response_get_all_email = hubspot_instance._send_get_request('/engagements/v1/engagements/paged?offset=' + str(offset) + '&limit=' + str(record_limit))
                    json_response_all_email = json.loads(response_get_all_email)

                    has_more = json_response_all_email['hasMore']
                    offset = json_response_all_email['offset']
                    for email_id in json_response_all_email['results']:
                        if email_id['engagement']['id'] and email_id['engagement']['type'] == 'EMAIL' or email_id['engagement']['type'] == 'INCOMING_EMAIL':
                            email_ids.append(email_id['engagement']['id'])
                    if email_ids:
                        self.env['mail.activity'].get_task_details_and_create(email_ids, hubspot_instance)
                    hubspot_instance.all_email = True

                message = 'Completed Getting All Email from hubspot'
                self.env['hubspot.logger'].create_log_message('Import Email', message)
                logger.info('Completed Getting All Email from hubspot------------------------------------------------------')
            except Exception as e:
                error_message = 'Error while getting Email in odoo \nHubspot response %s' % (str(e))
                self.env['hubspot.logger'].create_log_message('Import Email', error_message)
                logger.exception("Error in Getting All Email From Hubspot------------>\n" + error_message)
                hubspot_instance._raise_user_error(e)
        elif all_email and hubspot_instance.hubspot_is_import_email and hubspot_instance.active:

            logger.info('Getting modified email from hubspot-------------------test====')
            try:
                has_more = True
                offset = 0
                while has_more:
                    updated_email_ids = []
                    record_limit = 100
                    response_get_recently_modified_email = hubspot_instance._send_get_request(
                        '/engagements/v1/engagements/recent/modified?offset=' + str(offset) + '&count=' + str(record_limit))
                    json_response_get_recently_modified_email = json.loads(response_get_recently_modified_email)
                    record_limit += 1
                    offset = json_response_get_recently_modified_email['offset']
                    has_more = json_response_get_recently_modified_email['hasMore']
                    for noteId in json_response_get_recently_modified_email['results']:
                        if noteId['engagement']['id'] and noteId['engagement']['type'] == 'EMAIL' or noteId['engagement']['type'] == 'INCOMING_EMAIL':
                            if (int(noteId['engagement']['lastUpdated'])) <= int(modifiedDateForEmail):
                                break  # Skip Not recently updated note
                            elif (int(noteId.get('engagement')['lastUpdated'])) > int(modifiedDateForEmail):

                                updated_email_ids.append(noteId['engagement']['id'])
                                updated_email_ids.reverse()
                    if hubspot_instance.active and updated_email_ids and hubspot_instance.hubspot_is_import_email:
                        self.env['mail.activity'].get_task_details_and_create(updated_email_ids, hubspot_instance)
                    else:
                        break

                message = 'Completed Getting All email from hubspot'
                self.env['hubspot.logger'].create_log_message('Import Email', message)
                logger.info('Completed Getting modified email from hubspot------------------------------------------------------')
            except Exception as e:
                error_message = 'Error while getting email in odoo \nHubspot response %s' % (str(e))
                self.env['hubspot.logger'].create_log_message('Import Email', error_message)
                logger.exception("Error in getModifiedEmailFromHubspot------------>\n" + str(e))
                hubspot_instance._raise_user_error(e)


    @api.model
    def createNewEmailInOdoo(self, email_dict, hubspot_instance):
        try:
            newEmailModifiedDate = 10000000.0
            properties = []
            mail_notification_dict = {}
            mail_message_dict = {}

            mail_message_obj = self.env['mail.message']
            mail_notification_obj = self.env['mail.notification']

            for email_dict_details in email_dict:
                if 'lastUpdated' in email_dict_details['engagement']:
                    if email_dict_details['engagement']['lastUpdated']:
                        newEmailModifiedDate = int(email_dict_details['engagement']['lastUpdated'])
                if 'html' in email_dict_details['metadata']:
                    mail_message_dict['body'] = email_dict_details['metadata']['html']

                if 'id' in email_dict_details['engagement']:
                    mail_message_dict['hubspot_id'] = email_dict_details['engagement']['id']

                if 'timestamp' in email_dict_details['engagement']:
                    mail_message_dict['date'] = self.env['mail.activity'].convert_epoch_to_gmt_timestamp(email_dict_details['engagement']['timestamp'])
                    mail_notification_dict['read_date'] = self.env['mail.activity'].convert_epoch_to_gmt_timestamp(email_dict_details['engagement']['timestamp'])

                if 'metadata' in email_dict_details:
                    if 'subject' in email_dict_details['metadata']:
                        mail_message_dict['subject'] = email_dict_details['metadata']['subject']

                    if 'from' in email_dict_details['metadata']:
                        if 'email' in email_dict_details['metadata']['from']:
                            mail_message_dict['email_from'] = email_dict_details['metadata']['from']['email']
                            mail_message_dict['reply_to'] = email_dict_details['metadata']['from']['email']

                    if 'status' in email_dict_details['metadata']:
                        if email_dict_details['metadata']['status'] == 'SENT':
                            mail_notification_dict['notification_status'] = 'sent'
                        if email_dict_details['metadata']['status'] == 'OUTGOING':
                            mail_notification_dict['state'] = 'ready'
                        if email_dict_details['metadata']['status'] == 'EXCEPTION':
                            mail_notification_dict['state'] = 'exception'
                        if email_dict_details['metadata']['status'] == 'CANCELLED':
                            mail_notification_dict['state'] = 'canceled'

                mail_message_dict['hubspot_instance_id'] = hubspot_instance.id
                mail_message_dict['message_type'] = 'comment'
                mail_message_dict['subtype_id'] = self.env.ref('mail.mt_comment').id
                mail_message_dict['parent_id'] = False
                mail_message_dict['hubspot_object'] = 'mail'
                mail_notification_dict['notification_type'] = 'email'
                mail_notification_dict['is_read'] = True

                if 'contactIds' in email_dict_details['associations']:
                    for hubspot_contact_id in email_dict_details['associations']['contactIds']:
                        res_partner_id = self.env['res.partner'].sudo().search(
                            [('is_company', '=', False), ('hubspot_instance_id', '=', hubspot_instance.id),
                             ('hubspot_id', '=', hubspot_contact_id)],limit=1)
                        if res_partner_id:
                            mail_message_dict['model'] = 'res.partner'
                            mail_message_dict['res_id'] = res_partner_id.id
                            mail_message_dict['partner_ids'] = [(4, res_partner_id.id)]
                            mail_notification_dict['res_partner_id'] = res_partner_id.id
                            mail_message_id = mail_message_obj.sudo().search(
                                [('res_id', '=', res_partner_id.id), ('model', '=', 'res.partner'),
                                 ('hubspot_id', '=', email_dict_details['engagement']['id']),
                                 ('hubspot_instance_id', '=',
                                  hubspot_instance.id), ('hubspot_object', '=', 'mail')],limit=1)
                            if not mail_message_id:
                                mail_message_record = self.with_context({'from_hubspot': True}).sudo().create(mail_message_dict)
                                hubspot_instance.modifiedDateForEmail = newEmailModifiedDate
                                if mail_message_record:
                                    logger.info("Created New Mail Into Odoo ----------- " + str(mail_message_record.id))
                                    mail_notification_dict['mail_message_id'] = mail_message_record.id
                                    mail_notification_record = mail_notification_obj.sudo().create(mail_notification_dict)
                                    self.env.cr.commit()

                                    if mail_notification_record:
                                        logger.info("Created New mail notification Into Odoo ----------- " + str(mail_notification_record.id))

                                        mail_message_update_record = mail_message_record.write({'notification_ids': [(4, mail_notification_record.id)]})
                                        self.env.cr.commit()

                                        if mail_message_update_record:
                                            logger.info("Updated New mail notification Into Odoo ----------- " + str(mail_message_record.id))
                if 'companyIds' in email_dict_details['associations']:
                    for hubspot_company_id in email_dict_details['associations']['companyIds']:
                        res_partner_company_id = self.env['res.partner'].sudo().search(
                            [('is_company', '=', True), ('hubspot_id', '=', hubspot_company_id), ('hubspot_instance_id', '=', hubspot_instance.id)],limit=1)
                        if res_partner_company_id:
                            mail_message_dict['model'] = 'res.partner'
                            mail_message_dict['res_id'] = res_partner_company_id.id
                            mail_message_dict['partner_ids'] = [(4, res_partner_company_id.id)]
                            mail_notification_dict['res_partner_id'] = res_partner_company_id.id
                            mail_message_id = mail_message_obj.sudo().search(
                                [('hubspot_id', '=', email_dict_details['engagement']['id']),
                                 ('hubspot_instance_id', '=',
                                  hubspot_instance.id),
                                 ('hubspot_object', '=', 'mail'), ('res_id', '=', res_partner_company_id.id),
                                 ('model', '=', 'res.partner')],limit=1)
                            if not mail_message_id:
                                mail_message_record = self.with_context({'from_hubspot': True}).sudo().create(mail_message_dict)
                                hubspot_instance.modifiedDateForEmail = newEmailModifiedDate
                                if mail_message_record:
                                    logger.info("Created New Mail Into Odoo ----------- " + str(mail_message_record.id))
                                    mail_notification_dict['mail_message_id'] = mail_message_record.id
                                    mail_notification_record = mail_notification_obj.sudo().create(mail_notification_dict)
                                    if mail_notification_record:
                                        logger.info("Created New mail notification Into Odoo ----------- " + str(mail_notification_record.id))

                                        mail_message_update_record = mail_message_record.write({'notification_ids': [(4, mail_notification_record.id)]})
                                        if mail_message_update_record:
                                            logger.info("Updated New mail notification Into Odoo ----------- " + str(mail_message_record.id))
                if 'dealIds' in email_dict_details['associations']:
                    for hubspot_lead_id in email_dict_details['associations']['dealIds']:
                        lead_id = self.env['crm.lead'].sudo().search(
                            [('type', '=', 'opportunity'), ('hubspot_id', '=', hubspot_lead_id), ('hubspot_instance_id', '=', hubspot_instance.id)],limit=1)
                        if lead_id:
                            mail_message_dict['model'] = 'crm.lead'
                            mail_message_dict['res_id'] = lead_id.id
                            if lead_id.partner_id:
                                mail_message_dict['partner_ids'] = [(4, lead_id.partner_id.id)]
                                mail_notification_dict['res_partner_id'] = lead_id.partner_id.id
                            lead_mail_message_id = mail_message_obj.sudo().search(
                                [('hubspot_id', '=', email_dict_details['engagement']['id']),
                                 ('res_id', '=', lead_id.id), ('model', '=', 'crm.lead'),
                                 ('hubspot_instance_id', '=', hubspot_instance.id), ('hubspot_object', '=', 'mail')],limit=1)
                            if not lead_mail_message_id:
                                lead_mail_message_record = self.with_context({'from_hubspot': True}).sudo().create(mail_message_dict)
                                hubspot_instance.modifiedDateForEmail = newEmailModifiedDate
                                if lead_mail_message_record and mail_notification_dict.get('res_partner_id'):
                                    logger.info("Created New Mail Into Odoo ----------- " + str(lead_mail_message_record.id))
                                    mail_notification_dict['mail_message_id'] = lead_mail_message_record.id
                                    lead_mail_notification_record = mail_notification_obj.sudo().create(mail_notification_dict)
                                    self.env.cr.commit()

                                    if lead_mail_notification_record:
                                        logger.info("Created New mail notification Into Odoo ----------- " + str(lead_mail_notification_record.id))
                                        lead_mail_message_dict = {'notification_ids': [(4, lead_mail_notification_record.id)]}
                                        lead_mail_message_update_record = lead_mail_message_record.write(lead_mail_message_dict)
                                        self.env.cr.commit()

                                        if lead_mail_message_update_record:
                                            logger.info("Updated New mail notification Into Odoo ----------- " + str(lead_mail_message_record.id))
        except Exception as e:
            error_message = 'Error while creating hubspot email in odoo vals: %s\n Hubspot response %s' % (
                email_dict, str(e))
            self.env['hubspot.logger'].create_log_message('Import Email', error_message)
            logger.exception("Exception in Creating New Email in Odoo :\n" + error_message)
            hubspot_instance._raise_user_error(e)

    @api.model
    def _cron_export_email_to_hubspot(self):
        hubspot_instance_obj = self.env['hubspot.instance'].search(
            [('active', '=', True),('hubspot_is_export_email', '=', True)])
        for hubspot_instance in hubspot_instance_obj:
            self.export_email_to_hubspot(hubspot_instance)

    def export_email_to_hubspot(self, hubspot_instance):
        # Hubspot Information
        hubspot_app_key = hubspot_instance.hubspot_app_key
        hubspot_app_name = hubspot_instance.name
        subtype_id = self.env.ref('mail.mt_comment').id  # subtype is Discussions
        # if not hubspot_app_key or not hubspot_app_name:
        #     raise UserError(_(
        #         'Error in Synchronization!\nHubspot API Key and App Name need to be specified for synchronization of data with Odoo.'))
        if hubspot_instance.default_instance and hubspot_instance.active and hubspot_instance.hubspot_is_export_email:
            mail_message_ids = self.env['mail.message'].search([('hubspot_id', '=', False), ('message_type', '=', 'comment'), ('subtype_id', '=', subtype_id)])
            for mail_message_id in mail_message_ids:
                if not mail_message_id.hubspot_id:
                    mail_message_id.createNewEmailInHubspot(hubspot_instance)

    def createNewEmailInHubspot(self, hubspot_instance):
        for eachNewMail in self:
            subtype_id = self.env.ref('mail.mt_comment').id  # subtype is Discussions
            if eachNewMail.subtype_id.id == subtype_id:
                # create hubspot dictionary
                properties = {}
                metadata_dict = {}
                engagement_dict = {}
                associations_list = []
                associations_dict = {}
                to_list = []
                cc_list = []
                from_dict = {}

                if eachNewMail.date:
                    engagement_dict['timestamp'] = self.env['mail.activity'].convert_time_to_unix_timestamp(eachNewMail.date)
                if eachNewMail.res_id:
                    if eachNewMail.model == 'res.partner':
                        partner_id = self.env['res.partner'].sudo().search(
                            [('id', '=', eachNewMail.res_id), ('hubspot_instance_id', '=', hubspot_instance.id)])
                        if partner_id.hubspot_id and not partner_id.is_company:
                            associations_dict['contactIds'] = [int(partner_id.hubspot_id)]
                        else:
                            associations_dict['contactIds'] = []
                        if partner_id.hubspot_id and partner_id.is_company:
                            associations_dict['companyIds'] = [partner_id.hubspot_id]
                        else:
                            associations_dict['companyIds'] = []
                    if eachNewMail.model == 'crm.lead':
                        lead_id = self.env['crm.lead'].sudo().search(
                            [('id', '=', eachNewMail.res_id), ('hubspot_instance_id', '=', hubspot_instance.id)])
                        if lead_id.hubspot_id:
                            associations_dict['dealIds'] = [lead_id.hubspot_id]
                        else:
                            associations_dict['dealIds'] = []

                associations_dict['workflowIds'] = []
                associations_dict['ticketIds'] = []
                associations_dict['contentIds'] = []
                associations_dict['quoteIds'] = []

                if eachNewMail.body:
                    metadata_dict.update({'html': eachNewMail.body})
                engagement_dict['active'] = 'true'
                engagement_dict['type'] = 'EMAIL'

                account_details = self.env['mail.activity'].get_portal_hubspot_account_details(hubspot_instance)
                if account_details:
                    engagement_dict['portalId'] = account_details['portalId']

                for partner_id in eachNewMail.partner_ids:
                    if partner_id.email:
                        to_list.append({'email': partner_id.email})

                if eachNewMail.email_from:
                    if eachNewMail.email_from.find('<') != -1:
                        from_dict['email'] = self.env['mail.mail'].convert_email_from_to_email(eachNewMail.email_from)
                    else:
                        from_dict['email'] = eachNewMail.email_from
                if eachNewMail.subject:
                    metadata_dict.update({'subject': eachNewMail.subject})

                metadata_dict.update({'from': from_dict, 'to': to_list, 'cc': cc_list})
                metadata_dict.update({'trackerKey': eachNewMail.message_id})

                properties = {"engagement": engagement_dict, 'associations': associations_dict, 'metadata': metadata_dict, 'attachments': [], 'attachments': []}
                if properties:
                    try:
                        response_create_new_email = hubspot_instance._send_post_request('/engagements/v1/engagements', properties)
                        json_response_create_new_email = json.loads(response_create_new_email)
                        eachNewMail.with_context({'from_hubspot': True}).hubspot_id = json_response_create_new_email['engagement']['id']
                        eachNewMail.hubspot_instance_id = hubspot_instance.id
                        eachNewMail.hubspot_object = 'mail'
                        message = 'Exported Email successfully'
                        self.env['hubspot.logger'].create_log_message('Export Email', message)
                        logger.info('Exported Email successfully...')
                    except Exception as e_log:
                        error_message = 'Error while exporting odoo email %d \n\n Odoo vals: %s\n Hubspot response %s' % (
                            eachNewMail.id, str(properties), str(e_log))
                        self.env['hubspot.logger'].create_log_message('Export Email', error_message)
                        logger.exception("Exception in Hubspot Connection  :\n" + str(e_log))
                        hubspot_instance._raise_user_error(e_log)

