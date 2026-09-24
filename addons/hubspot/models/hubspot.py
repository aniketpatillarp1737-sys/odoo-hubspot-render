# -*- coding: utf-8 -*-

import datetime,time
import logging
import json
from odoo import api, fields, models, _
import requests
from datetime import timezone
# from tzlocal import get_localzone
import random



logger = logging.getLogger(__name__)
# local_tz = get_localzone()
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from odoo.exceptions import UserError
# from tzlocal import get_localzone
import base64,zlib
# local_tz = get_localzone()
skip_mapped_contact = []
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
from odoo.tools import config
config['limit_time_real'] = 10000000


def convert_time_to_unix_timestamp(deadline_date):
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


class ResPartner(models.Model):
    _inherit = "res.partner"

    # Added the size of Integer, Error returned by the Customer
    #     hubspot_id = fields.Integer('Hubspot Vid',readonly = True,default = 0,size=50)
    # name = fields.Char(index=True,default="Unknown")
    hubspot_id = fields.Char('Hubspot Id', store=True, readonly=True, copy=False)
    hubspot_instance_id = fields.Many2one('hubspot.instance', 'Hubspot Instance Name', help="Hubspot Instance Name", readonly=True, copy=False)
    
    
    def write(self, vals):
        '''Update Contact or compnay details in hubspot on change of details in odoo'''
        res = super(ResPartner, self).write(vals)
        # Hubspot Information
        for record in self:
            instance = ''
            if record.hubspot_id and record.hubspot_instance_id and record.hubspot_instance_id.active:
                instance = record.hubspot_instance_id
            # Hubspot Information
            if instance:
                if instance.hubspot_app_key:
                    if not self.env.context.get('from_hubspot'):
                        contact_field_mapping = self.env['contact.field.mapping'].search([('hubspot_instance_id', '=', instance.id)])
                        company_field_mapping = self.env['company.field.mapping'].search([('hubspot_instance_id', '=', instance.id)])

                        try:
                            if instance.hubspot_is_export_company and record.is_company:
                                record.UpdateCompaniesInHubspot(instance)
                                if len(company_field_mapping):
                                    record.UpdateCompaniesInHubspotFieldMapping(company_field_mapping, instance)

                            elif instance.hubspot_is_export_contacts and not record.is_company and instance.hubspot_is_export_contacts:
                                record.UpdateContactsInHubspot(instance)
                                if len(contact_field_mapping):
                                    record.UpdateContactsInHubspotFieldMapping(contact_field_mapping, instance)
                        except Exception as e_log:
                            error_message = 'Error while updating contacts/companies from odoo %d \n\n Odoo vals: %s\n Hubspot response %s' % (
                                record.id, str(vals), str(e_log))
                            self.env['hubspot.logger'].create_log_message('Export Contacts/Companies', error_message)
                            logger.exception("Exception in Hubspot Connection  :\n" + str(e_log))
                            instance._raise_user_error(e_log)

        return res
    
   


    def UpdateContactsInHubspotFieldMapping(self, contact_field_mapping, hubspot_instance):
        properties = []
        for contact_field_mapping_id in contact_field_mapping:
            for eachContact in self:
                if contact_field_mapping_id.odoo_fields.name and contact_field_mapping_id.hubspot_fields.technical_name:
                    partner_read_obj = self.read()[0]
                    if not self.is_company:
                        partner_dict = {}
                        if contact_field_mapping_id.odoo_fields.name in partner_read_obj.keys():
                            if partner_read_obj.values():
                                if partner_read_obj.get(contact_field_mapping_id.odoo_fields.name):
                                    if contact_field_mapping_id.hubspot_fields.field_type == 'date':
                                        format_date = convert_time_to_unix_timestamp(partner_read_obj.get(contact_field_mapping_id.odoo_fields.name))
                                        properties.append(
                                            {'property': contact_field_mapping_id.hubspot_fields.technical_name,
                                             'value': format_date})
                                    else:
                                        properties.append(
                                            {'property': contact_field_mapping_id.hubspot_fields.technical_name,
                                             'value': str(partner_read_obj.get(contact_field_mapping_id.odoo_fields.name))})
                if len(properties) > 0:
                    try:
                        hubspot_instance._send_post_request('/contacts/v1/contact/vid/' + str(eachContact.hubspot_id) + '/profile', ({'properties': properties}))
                        eachContact.with_context({'from_hubspot': True})
                        logger.info('Completed updating contacts in hubspot with custom field mapping')
                    except Exception as e_log:
                        error_message = 'Custom field mapping error while updating contacts from odoo id %d \n\n Odoo vals: %s\n Hubspot response %s' % (
                            eachContact.id, str(properties), str(e_log))
                        self.env['hubspot.logger'].create_log_message('Export Contacts', error_message)
                        logger.exception("Exception in updating contacts :\n" + str(e_log))
                        hubspot_instance._raise_user_error(e_log)

    # def unlink(self):
    #     '''Delete contact in hubspot on delete of contact or company in odoo'''
    #     # Hubspot Information

    #     for record in self:
    #         if record.hubspot_instance_id and record.hubspot_instance_id.active:
    #             if record.hubspot_instance_id.hubspot_sync_contacts or record.hubspot_instance_id.hubspot_sync_companies:
    #                 record.deleteFromHubspot(record.hubspot_instance_id)
    #                 self._cr.commit()
    #     return super(ResPartner, self).unlink()


    @api.model
    def _cron_update_contacts_from_hubspot(self):
        hubspot_instance_obj = self.env['hubspot.instance'].search([('active', '=', True), ('hubspot_is_import_contacts', '=', True)])
        for hubspot_instance in hubspot_instance_obj:
            self.update_existing_contacts_from_hubspot(hubspot_instance)
    

    @api.model
    def _cron_import_skipped_contacts_from_hubspot(self):
        hubspot_instance_obj = self.env['hubspot.instance'].search([('active', '=', True), ('hubspot_is_import_contacts', '=', True)])
        for hubspot_instance in hubspot_instance_obj:
            self.import_skip_contacts_from_hubspot(hubspot_instance)

    @api.model
    def import_skip_contacts_from_hubspot(self, hubspot_instance):
        """This function is called from cron to import contacts from hubspot"""
      
        
        if hubspot_instance.active  and hubspot_instance.hubspot_is_import_contacts:
            logger.info('Getting All skipped contacts from hubspot---------------------------')
            try:
                has_more = True
                vid_offset = 0
                while has_more:
                    contact_ids = []
                    record_limit = 90
                    response_all_contacts = hubspot_instance._send_get_request('/contacts/v1/lists/all/contacts/all?vidOffset=' + str(vid_offset) + '&count=' + str(record_limit))
                    json_response_all_contacts = json.loads(response_all_contacts)
                    has_more = json_response_all_contacts['has-more']
                    vid_offset = json_response_all_contacts['vid-offset']
                    for contacts_id in json_response_all_contacts['contacts']:
                        # res_partner_id = self.env['res.partner'].sudo().search(
                        #     [('hubspot_instance_id', '=', hubspot_instance.id), ('is_company', '=', False), ('hubspot_id', '=', contacts_id.get('canonical-vid'))])
                        # if not res_partner_id:
                        contact_ids.append(contacts_id['canonical-vid'])
                    if len(contact_ids) > 0:
                        logger.info('\n\n\nAll skipped contacts ------------------------------------------\n{}'.format(contact_ids))
                        logger.info('\n\n\nTotal skipped contacts {}'.format(len(contact_ids)))
                        self.with_context({'from_skipped_contacts': True}).get_contact_details_and_create(contact_ids, hubspot_instance)
                message = 'Completed Getting skipped contacts from hubspot'
                self.env['hubspot.logger'].create_log_message('Import Contacts', message)
                logger.info('Completed Getting skipped contacts from hubspot------------------------------------------------------')
            except Exception as e:
                error_message = 'Error while getting skipped contacts in odoo \nHubspot response %s' % (str(e))
                self.env['hubspot.logger'].create_log_message('Import Contacts', error_message)
                logger.exception("Error in Getting skipped Contacts From Hubspot------------>\n" + error_message)
                hubspot_instance._raise_user_error(e)

       
    def hubspot_queue_contact_create(self,line,hubspot_instance):
        partner_id = ''
        update_partner_id = ''
        contact_info = {}
        contact_profile = json.loads(line.hubspot_contact_data)
        if ('properties' in contact_profile):
            if 'canonical-vid' in contact_profile:
                contact_info.update({'hubspot_id': (contact_profile['canonical-vid'])})
            if 'identity-profiles' in contact_profile:
                contact_info.update({'identity-profiles': contact_profile['identity-profiles']})
            if 'firstname' in contact_profile['properties']:
                contact_info.update({'firstname': contact_profile['properties']['firstname']})
            if 'lastname' in contact_profile['properties']:
                contact_info.update({'lastname': contact_profile['properties']['lastname']})
            if 'associatedcompanyid' in contact_profile['properties']:
                contact_info.update(
                    {'associatedcompanyid': contact_profile['properties']['associatedcompanyid']})
            if 'jobtitle' in contact_profile['properties']:
                contact_info.update({'jobtitle': contact_profile['properties']['jobtitle']})
            if 'phone' in contact_profile['properties']:
                contact_info.update({'phone': contact_profile['properties']['phone']})
            # if 'mobilephone' in contact_profile['properties']:
            #     contact_info.update({'mobilephone': contact_profile['properties']['mobilephone']})
            if 'address' in contact_profile['properties']:
                contact_info.update({'address': contact_profile['properties']['address']})
            if 'lifecyclestage' in contact_profile['properties']:
                contact_info.update({'lifecyclestage': contact_profile['properties']['lifecyclestage']})
            if 'closedate' in contact_profile['properties']:
                contact_info.update({'closedate': contact_profile['properties']['closedate']})
            if 'notes_next_activity_date' in contact_profile['properties']:
                contact_info.update(
                    {'notes_next_activity_date': contact_profile['properties']['notes_next_activity_date']})
            if 'country' in contact_profile['properties']:
                contact_info.update({'country': contact_profile['properties']['country']})
            if 'website' in contact_profile['properties']:
                contact_info.update({'website': contact_profile['properties']['website']})
            if 'state' in contact_profile['properties']:
                contact_info.update({'state': contact_profile['properties']['state']})
            # if 'salutation' in contact_profile['properties']:
            #     contact_info.update({'title': contact_profile['properties']['salutation']})
            if 'zip' in contact_profile['properties']:
                contact_info.update({'zip': contact_profile['properties']['zip']})
            if 'city' in contact_profile['properties']:
                contact_info.update({'city': contact_profile['properties']['city']})
            if 'hubspot_owner_id' in contact_profile['properties']:
                contact_info.update({'hubspot_owner_id': contact_profile['properties']['hubspot_owner_id']})
            if 'lastmodifieddate' in contact_profile['properties']:
                contact_info.update({'lastmodifieddate': contact_profile['properties']['lastmodifieddate']})

            partner_id = self.createQueueContactsInOdoo(contact_info, hubspot_instance,line)
            self.env.cr.commit()

                  
            field_mapping_partner_id = self.createNewContactsInOdooFieldMapping(contact_profile, hubspot_instance)


    def get_contact_details_and_create(self, contact_ids, hubspot_instance):
        partner_id = ''
        update_partner_id = ''
        for contact_id in contact_ids:
            try:
                paged=0
                contact_info = {}
                get_contact_by_id_response = hubspot_instance._send_get_request('/contacts/v1/contact/vid/' + str(contact_id) + '/profile')
             
                contact_profile = json.loads(get_contact_by_id_response)
                        
                if ('properties' in contact_profile):
                    if 'canonical-vid' in contact_profile:
                        contact_info.update({'hubspot_id': contact_profile['canonical-vid']})
                    if 'identity-profiles' in contact_profile:
                        contact_info.update({'identity-profiles': contact_profile['identity-profiles']})
                    if 'firstname' in contact_profile['properties']:
                        contact_info.update({'firstname': contact_profile['properties']['firstname']})
                    if 'lastname' in contact_profile['properties']:
                        contact_info.update({'lastname': contact_profile['properties']['lastname']})
                    if 'associatedcompanyid' in contact_profile['properties']:
                        contact_info.update(
                            {'associatedcompanyid': contact_profile['properties']['associatedcompanyid']})
                    if 'jobtitle' in contact_profile['properties']:
                        contact_info.update({'jobtitle': contact_profile['properties']['jobtitle']})
                    if 'phone' in contact_profile['properties']:
                        contact_info.update({'phone': contact_profile['properties']['phone']})
                    # if 'mobilephone' in contact_profile['properties']:
                    #     contact_info.update({'mobilephone': contact_profile['properties']['mobilephone']})
                    if 'address' in contact_profile['properties']:
                        contact_info.update({'address': contact_profile['properties']['address']})
                    if 'lifecyclestage' in contact_profile['properties']:
                        contact_info.update({'lifecyclestage': contact_profile['properties']['lifecyclestage']})
                    if 'closedate' in contact_profile['properties']:
                        contact_info.update({'closedate': contact_profile['properties']['closedate']})
                    if 'notes_next_activity_date' in contact_profile['properties']:
                        contact_info.update(
                            {'notes_next_activity_date': contact_profile['properties']['notes_next_activity_date']})
                    if 'country' in contact_profile['properties']:
                        contact_info.update({'country': contact_profile['properties']['country']})
                    if 'website' in contact_profile['properties']:
                        contact_info.update({'website': contact_profile['properties']['website']})
                    if 'state' in contact_profile['properties']:
                        contact_info.update({'state': contact_profile['properties']['state']})
                    # if 'salutation' in contact_profile['properties']:
                    #     contact_info.update({'title': contact_profile['properties']['salutation']})
                    if 'zip' in contact_profile['properties']:
                        contact_info.update({'zip': contact_profile['properties']['zip']})
                    if 'city' in contact_profile['properties']:
                        contact_info.update({'city': contact_profile['properties']['city']})
                    if 'hubspot_owner_id' in contact_profile['properties']:
                        contact_info.update({'hubspot_owner_id': contact_profile['properties']['hubspot_owner_id']})
                    if 'lastmodifieddate' in contact_profile['properties']:
                        contact_info.update({'lastmodifieddate': contact_profile['properties']['lastmodifieddate']})
                    
                    partner_id = self.createImportContactsInOdoo(contact_info, hubspot_instance)
                    
                    # hubspot_instance.modifiedDateForContact = contact_profile.get('properties').get('lastmodifieddate').get('value')
                    self.env.cr.commit()

                  
                    field_mapping_partner_id = self.createNewContactsInOdooFieldMapping(contact_profile, hubspot_instance)
            except Exception as e:
                error_message = 'Error while importing hubspot contact in hubspot Id: %s\n Hubspot response %s' % (
                    contact_id, str(e))
                self.env['hubspot.logger'].create_log_message('Import Companies', error_message)
                logger.exception("Exception In getting contact info from Hubspot : \n" + error_message)
                hubspot_instance._raise_user_error(e)
        return partner_id
    
    def update_contact_details_and_create(self, contact_ids, hubspot_instance):
        
        update_partner_id = ''
        for contact_id in contact_ids:
            try:
                paged=0
                contact_info = {}
                get_contact_by_id_response = hubspot_instance._send_get_request('/contacts/v1/contact/vid/' + str(contact_id) + '/profile')
             
                contact_profile = json.loads(get_contact_by_id_response)
                        
                if ('properties' in contact_profile):
                    if 'canonical-vid' in contact_profile:
                        contact_info.update({'hubspot_id': contact_profile['canonical-vid']})
                    if 'identity-profiles' in contact_profile:
                        contact_info.update({'identity-profiles': contact_profile['identity-profiles']})
                    if 'firstname' in contact_profile['properties']:
                        contact_info.update({'firstname': contact_profile['properties']['firstname']})
                    if 'lastname' in contact_profile['properties']:
                        contact_info.update({'lastname': contact_profile['properties']['lastname']})
                    if 'associatedcompanyid' in contact_profile['properties']:
                        contact_info.update(
                            {'associatedcompanyid': contact_profile['properties']['associatedcompanyid']})
                    if 'jobtitle' in contact_profile['properties']:
                        contact_info.update({'jobtitle': contact_profile['properties']['jobtitle']})
                    if 'phone' in contact_profile['properties']:
                        contact_info.update({'phone': contact_profile['properties']['phone']})
                    # if 'mobilephone' in contact_profile['properties']:
                    #     contact_info.update({'mobilephone': contact_profile['properties']['mobilephone']})
                    if 'address' in contact_profile['properties']:
                        contact_info.update({'address': contact_profile['properties']['address']})
                    if 'lifecyclestage' in contact_profile['properties']:
                        contact_info.update({'lifecyclestage': contact_profile['properties']['lifecyclestage']})
                    if 'closedate' in contact_profile['properties']:
                        contact_info.update({'closedate': contact_profile['properties']['closedate']})
                    if 'notes_next_activity_date' in contact_profile['properties']:
                        contact_info.update(
                            {'notes_next_activity_date': contact_profile['properties']['notes_next_activity_date']})
                    if 'country' in contact_profile['properties']:
                        contact_info.update({'country': contact_profile['properties']['country']})
                    if 'website' in contact_profile['properties']:
                        contact_info.update({'website': contact_profile['properties']['website']})
                    if 'state' in contact_profile['properties']:
                        contact_info.update({'state': contact_profile['properties']['state']})
                    # if 'salutation' in contact_profile['properties']:
                    #     contact_info.update({'title': contact_profile['properties']['salutation']})
                    if 'zip' in contact_profile['properties']:
                        contact_info.update({'zip': contact_profile['properties']['zip']})
                    if 'city' in contact_profile['properties']:
                        contact_info.update({'city': contact_profile['properties']['city']})
                    if 'hubspot_owner_id' in contact_profile['properties']:
                        contact_info.update({'hubspot_owner_id': contact_profile['properties']['hubspot_owner_id']})
                    if 'lastmodifieddate' in contact_profile['properties']:
                        contact_info.update({'lastmodifieddate': contact_profile['properties']['lastmodifieddate']})
                    
                    update_partner_id = self.createNewContactsInOdoo(contact_info, hubspot_instance)
                    
                    # hubspot_instance.modifiedDateForContact = contact_profile.get('properties').get('lastmodifieddate').get('value')
                    self.env.cr.commit()

                  
                    field_mapping_partner_id = self.createNewContactsInOdooFieldMapping(contact_profile, hubspot_instance)
            except Exception as e:
                error_message = 'Error while importing hubspot contact in hubspot Id: %s\n Hubspot response %s' % (
                    contact_id, str(e))
                self.env['hubspot.logger'].create_log_message('Import Companies', error_message)
                logger.exception("Exception In getting contact info from Hubspot : \n" + error_message)
                hubspot_instance._raise_user_error(e)
        return update_partner_id
   
    @api.model
    def createNewContactsInOdoo(self, contact_info, hubspot_instance):
        try:
            newcontactModifiedDate = 10000000.0
            iban_detail = False
            if 'lastmodifieddate' in contact_info:
                if contact_info['lastmodifieddate']['value']:
                    newcontactModifiedDate = int(contact_info['lastmodifieddate']['value'])
            vals = {}
            # if contact_info['hubspot_id']:
            #     vals['hubspot_id'] = contact_info['hubspot_id']
            # contactName = ''
              
            # if 'firstname' in contact_info:
            #     if len(contact_info['firstname']['value']) > 0:
            #         contactName += contact_info['firstname']['value'] + ' '
            # if 'lastname' in contact_info:
            #     if len(contact_info['lastname']['value']) > 0:
            #         contactName += contact_info['lastname']['value']
            # elif contactName == '':
            #     contactName = "Unknown"
            # vals['name'] = contactName
            # vals['customer_rank'] = 1
            for each_identity in contact_info['identity-profiles']:
                if 'identities' in each_identity:
                    for each_key in each_identity['identities']:
                        if each_key['type'] == 'EMAIL':
                            vals['email'] = each_key['value']
                            break
            if 'associatedcompanyid' in contact_info and hubspot_instance.hubspot_is_import_company:
                if contact_info['associatedcompanyid']['value']:
                    companyId = self.search([('hubspot_id', '=', contact_info['associatedcompanyid']['value'])],limit=1)
                    if companyId:
                        vals['parent_id'] = companyId.id
                    else:
                        # Hubspot Information
                        hubspot_app_key = hubspot_instance.hubspot_app_key
                        # if Param.get_param('hubspot.all_companies'):
                        AllCompanies = self.getCompaniesFromHubspot(hubspot_instance, contact_info['associatedcompanyid']['value'])
                        self.createNewCompaniesInOdoo(AllCompanies, hubspot_instance)
                        hubspot_instance.all_companies = True
                        companyId = self.search([('hubspot_id', '=', contact_info['associatedcompanyid']['value'])],limit=1)
                        if companyId:
                            vals['parent_id'] = companyId.id

            if 'jobtitle' in contact_info:
                if contact_info['jobtitle']['value']:
                    vals['function'] = contact_info['jobtitle']['value']

            # if 'mobilephone' in contact_info:
            #     if contact_info['mobilephone']['value']:
            #         vals['mobile'] = contact_info['mobilephone']['value']

            if 'phone' in contact_info:
                if contact_info['phone']['value']:
                    vals['phone'] = contact_info['phone']['value']

            if 'address' in contact_info:
                if contact_info['address']['value']:
                    vals['street2'] = contact_info['address']['value']

            if 'city' in contact_info:
                if contact_info['city']['value']:
                    vals['city'] = contact_info['city']['value']

            if 'website' in contact_info:
                if contact_info['website']['value']:
                    vals['website'] = contact_info['website']['value']
            if 'zip' in contact_info:
                if contact_info['zip']['value']:
                    vals['zip'] = contact_info['zip']['value']
            country_id = None
            if 'country' in contact_info and contact_info['country']['value']:
                if contact_info['country']['value'] in ['usa', 'USA', 'us', 'US', 'United States of America', 'united states of america', 'united states', 'United States']:
                    country = self.env['res.country'].search([('code', 'like', 'US')], limit=1)
                else:
                    
                    country = self.env['res.country'].search(['|', ('code', '=', contact_info['country']['value']),
                                                              ('name', '=', contact_info['country']['value'])], limit=1)

                if len(country):
                    country_id = country.id
                    vals['country_id'] = country_id

            if 'state' in contact_info:
                if contact_info['state']['value']:
                    if country_id:
                        state_id = self.env['res.country.state'].search(
                            ['|', ('name', '=', contact_info['state']['value']), ('code', '=', contact_info['state']['value']),
                             ('country_id', '=', country_id)], limit=1)
                    else:
                        state_id = self.env['res.country.state'].search(
                            ['|', ('name', '=', contact_info['state']['value']), ('code', '=', contact_info['state']['value'])], limit=1)
                    if state_id:
                        vals['state_id'] = state_id.id

            # if 'title' in contact_info:
            #     if contact_info['title']['value']:
            #         title_id = self.env['res.partner.title'].search([('name', '=', contact_info['title']['value'])],
            #                                                         limit=1)
            #         if title_id:
            #             vals['title'] = title_id.id
            
                    

            # Sync Owner
            if 'hubspot_owner_id' in contact_info:
                if contact_info['hubspot_owner_id']['value']:
                    owner_id = int(contact_info['hubspot_owner_id']['value'])
                    if owner_id:
                        res_user_id = self.env['res.partner'].search(
                            ['|', ('active', '=', True), ('active', '=', False), ('hubspot_id', '=', owner_id), ('hubspot_instance_id', '=', hubspot_instance.id)], limit=1)
                        if res_user_id:
                            # vals['user_id'] = res_user_id.id
                            logger.info("+++++++owner already as contact ======")
                            
                        else:
                            get_user = self.env['res.partner'].getOwnerDetailsFromHubspot(owner_id, hubspot_instance)
                           
                            if get_user:
                                logger.info("++++++++owner created as contact")
                                # vals['user_id'] = get_user.id
            
            if contact_info['hubspot_id']:
                vals['hubspot_id'] = contact_info['hubspot_id']
            contactName = ''
              
            if 'firstname' in contact_info:
                if len(contact_info['firstname']['value']) > 0:
                    contactName += contact_info['firstname']['value'] + ' '
            if 'lastname' in contact_info:
                if len(contact_info['lastname']['value']) > 0:
                    contactName += contact_info['lastname']['value']
            elif contactName == '':
                contactName = "Unknown"
            vals['name'] = contactName
            vals['customer_rank'] = 1
            

            update_partner_id = self.search(
                ['|', ('active', '=', True), ('active', '=', False), ('hubspot_id', '=', str(contact_info['hubspot_id'])), ('hubspot_instance_id', '=', hubspot_instance.id)],
                limit=1)
            
           
            
            if update_partner_id:
                
                odoo_modifiedDate = convert_time_to_unix_timestamp(update_partner_id.write_date)
                if self.env.context.get('from_skipped_contacts'):
                    vals['hubspot_instance_id'] = hubspot_instance.id
                    update_partner_id.with_context({'from_hubspot': True}).write(vals)
                    # hubspot_instance.modifiedDateForContact = newcontactModifiedDate
                    logger.info("Write into Existing Odoo Contact-----------skippedcontact " + str(update_partner_id.hubspot_id))
                    hubspot_contact_id = vals['hubspot_id']
                    try:
                   
                        response_get_associated_contact_attachment_detail = hubspot_instance._send_get_request(
                            f'/engagements/v1/engagements/associated/contact/{hubspot_contact_id}/paged')
                        
                        
                    
                        
                        
                        json_response_get_associated_contact_attachment_detail = json.loads(response_get_associated_contact_attachment_detail)
                        
                        
                        results = json_response_get_associated_contact_attachment_detail.get('results', [])
                
                        if results:
                            contact_id = self.env['res.partner'].sudo().search(
                                [('type', '=', 'contact'), ('hubspot_id', '=', hubspot_contact_id), ('hubspot_instance_id', '=', hubspot_instance.id)],limit=1)
                        
                            model_id = self.env['ir.model']._get('res.partner').id
                            model_name = 'res.partner'
                            
                            for result in results:
                                attachments = result.get('attachments', [])
                                for attachment in attachments:
                                    attachment_id = attachment.get('id')
                                    if attachment_id:
                                        attachment_details = self.get_attachment_by_id(attachment_id, hubspot_instance)
                                        if attachment_details:
                                            create_attachment = self.create_attachment(attachment_details, contact_id, model_name)
                                            if create_attachment:
                                                logger.info("Attachment created successfully: %s" % create_attachment.id)
                                            else:
                                                logger.warning("Failed to create attachment for: %s" % attachment_details['name'])
                        else:
                            logger.warning("No attachments found in the response for hubspot_contact_id: %s", hubspot_contact_id)
                        
                            
                    
                    except json.JSONDecodeError:
                        logger.error("Failed to parse JSON response for hubspot_contact_id: %s", hubspot_contact_id)
                    except Exception as e:
                        logger.error("An unexpected error occurred: %s", str(e))
                    return update_partner_id
                elif int(newcontactModifiedDate) > int(odoo_modifiedDate):
                    vals['hubspot_instance_id'] = hubspot_instance.id
                    update_partner_id.with_context({'from_hubspot': True}).write(vals)
                    # hubspot_instance.modifiedDateForContact = newcontactModifiedDate
                    logger.info("Write into Existing Odoo Contact-----------normal write " + str(update_partner_id.hubspot_id))
                    hubspot_contact_id = vals['hubspot_id']
                    try:
                   
                        response_get_associated_contact_attachment_detail = hubspot_instance._send_get_request(
                            f'/engagements/v1/engagements/associated/contact/{hubspot_contact_id}/paged')
                    
                       
                        
                        
                        json_response_get_associated_contact_attachment_detail = json.loads(response_get_associated_contact_attachment_detail)
                        
                        
                        results = json_response_get_associated_contact_attachment_detail.get('results', [])
                
                        if results:
                            contact_id = self.env['res.partner'].sudo().search(
                                [('type', '=', 'contact'), ('hubspot_id', '=', hubspot_contact_id), ('hubspot_instance_id', '=', hubspot_instance.id)],limit=1)
                        
                            model_id = self.env['ir.model']._get('res.partner').id
                            model_name = 'res.partner'
                            
                            for result in results:
                                attachments = result.get('attachments', [])
                                for attachment in attachments:
                                    attachment_id = attachment.get('id')
                                    if attachment_id:
                                        attachment_details = self.get_attachment_by_id(attachment_id, hubspot_instance)
                                        if attachment_details:
                                            create_attachment = self.create_attachment(attachment_details, contact_id, model_name)
                                            if create_attachment:
                                                logger.info("Attachment created successfully: %s" % create_attachment.id)
                                            else:
                                                logger.warning("Failed to create attachment for: %s" % attachment_details['name'])
                        else:
                            logger.warning("No attachments found in the response for hubspot_contact_id: %s", hubspot_contact_id)
                        
                
                    except json.JSONDecodeError:
                        logger.error("Failed to parse JSON response for hubspot_contact_id: %s", hubspot_contact_id)
                    except Exception as e:
                        logger.error("An unexpected error occurred: %s", str(e))
                    return update_partner_id
                    
                    
                    
            else:
                if 'email' in vals:
                    update_partner_id = self.search(['|', ('active', '=', True), ('active', '=', False), ('email', '=', vals['email']), ('is_company', '=', False),
                                              ('hubspot_id', '=', False), ('hubspot_instance_id', '=', False)], limit=1)
                    if update_partner_id:
                        if self.env.context.get('from_skipped_contacts'):
                            vals['hubspot_instance_id'] = hubspot_instance.id
                            # hubspot_instance.modifiedDateForContact = newcontactModifiedDate
                            update_partner_id.with_context({'from_hubspot': True}).write(vals)
                            logger.info("Write into Existing Odoo Contact----------- email skippedcontact " + str(update_partner_id.hubspot_id))
                            hubspot_contact_id = vals['hubspot_id']
                            try:
                   
                                response_get_associated_contact_attachment_detail = hubspot_instance._send_get_request(
                                    f'/engagements/v1/engagements/associated/contact/{hubspot_contact_id}/paged')
                            
                                
                                
                                json_response_get_associated_contact_attachment_detail = json.loads(response_get_associated_contact_attachment_detail)
                                
                                
                                results = json_response_get_associated_contact_attachment_detail.get('results', [])
                        
                                if results:
                                    contact_id = self.env['res.partner'].sudo().search(
                                        [('type', '=', 'contact'), ('hubspot_id', '=', hubspot_contact_id), ('hubspot_instance_id', '=', hubspot_instance.id)],limit=1)
                                
                                    model_id = self.env['ir.model']._get('res.partner').id
                                    model_name = 'res.partner'
                                    
                                    for result in results:
                                        attachments = result.get('attachments', [])
                                        for attachment in attachments:
                                            attachment_id = attachment.get('id')
                                            if attachment_id:
                                                attachment_details = self.get_attachment_by_id(attachment_id, hubspot_instance)
                                                if attachment_details:
                                                    create_attachment = self.create_attachment(attachment_details, contact_id, model_name)
                                                    if create_attachment:
                                                        logger.info("Attachment created successfully: %s" % create_attachment.id)
                                                    else:
                                                        logger.warning("Failed to create attachment for: %s" % attachment_details['name'])
                                else:
                                    logger.warning("No attachments found in the response for hubspot_contact_id: %s", hubspot_contact_id)
                           
                            except json.JSONDecodeError:
                                logger.error("Failed to parse JSON response for hubspot_contact_id: %s", hubspot_contact_id)
                            except Exception as e:
                                logger.error("An unexpected error occurred: %s", str(e))
                            return update_partner_id
                        elif not self.env.context.get('from_skipped_contacts'):
                            vals['hubspot_instance_id'] = hubspot_instance.id
                            # hubspot_instance.modifiedDateForContact = newcontactModifiedDate
                            update_partner_id.with_context({'from_hubspot': True}).write(vals)
                            logger.info("Write into Existing Odoo Contact-----------email normal write " + str(update_partner_id.hubspot_id))
                            hubspot_contact_id = vals['hubspot_id']
                            try:
                   
                                response_get_associated_contact_attachment_detail = hubspot_instance._send_get_request(
                                    f'/engagements/v1/engagements/associated/contact/{hubspot_contact_id}/paged')
                            
                                
                                
                                
                                json_response_get_associated_contact_attachment_detail = json.loads(response_get_associated_contact_attachment_detail)
                                
                                
                                results = json_response_get_associated_contact_attachment_detail.get('results', [])
                        
                                if results:
                                    contact_id = self.env['res.partner'].sudo().search(
                                        [('type', '=', 'contact'), ('hubspot_id', '=', hubspot_contact_id), ('hubspot_instance_id', '=', hubspot_instance.id)],limit=1)
                                
                                    model_id = self.env['ir.model']._get('res.partner').id
                                    model_name = 'res.partner'
                                    
                                    for result in results:
                                        attachments = result.get('attachments', [])
                                        for attachment in attachments:
                                            attachment_id = attachment.get('id')
                                            if attachment_id:
                                                attachment_details = self.get_attachment_by_id(attachment_id, hubspot_instance)
                                                if attachment_details:
                                                    create_attachment = self.create_attachment(attachment_details, contact_id, model_name)
                                                    if create_attachment:
                                                        logger.info("Attachment created successfully: %s" % create_attachment.id)
                                                    else:
                                                        logger.warning("Failed to create attachment for: %s" % attachment_details['name'])
                                else:
                                    logger.warning("No attachments found in the response for hubspot_contact_id: %s", hubspot_contact_id)
                            
                                
                        
                            except json.JSONDecodeError:
                                logger.error("Failed to parse JSON response for hubspot_contact_id: %s", hubspot_contact_id)
                            except Exception as e:
                                logger.error("An unexpected error occurred: %s", str(e))
                                            
                            return update_partner_id
                   
          

        except Exception as e:
            error_message = 'Error while creating hubspot contacts in odoo vals: %s\n Hubspot response %s' % (
                contact_info, str(e))
            log_message = self.env['hubspot.logger'].create_log_message('Import Contacs', error_message)
            logger.exception("Exception in Creating New Contacts in Odoo :\n" + error_message)
            
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
    def create_attachment(self, attachment_details, contact_id, model_name):
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
                ('res_id', '=', contact_id.id),
                ('name', '=', attachment_details['name'],)
            ], limit=1)
            
            if not existing_attachment:
                try:
                    attachment_id = self.env['ir.attachment'].create({
                        'name': attachment_details['name'],
                        'type': 'binary',
                        'datas': file_data,
                        'res_model': model_name,
                        'res_id': contact_id.id,
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
    def update_existing_contacts_from_hubspot(self,hubspot_instance):
        modifiedDateForContact = hubspot_instance.modifiedDateForContact or ''
        if hubspot_instance.active and hubspot_instance.hubspot_is_import_contacts: 
                try:
                    has_more = True
                    vid_offset = 0
                    while has_more:
                        updated_contact_ids = []
                        record_limit = 90
                        recent_update_contact_response = hubspot_instance._send_get_request(
                            '/contacts/v1/lists/recently_updated/contacts/recent?vidOffset=' + str(vid_offset) + '&count=' + str(record_limit))
                        recent_update_contact_json_response = json.loads(recent_update_contact_response)
                        record_limit += 1
                        has_more = recent_update_contact_json_response['has-more']
                        vid_offset = recent_update_contact_json_response['vid-offset']
                        hubspot_modifiedDateForContact = ''
                        for contacts_id in recent_update_contact_json_response['contacts']:
                            if (contacts_id['properties']['lastmodifieddate']['value']) <= modifiedDateForContact:
                                break  # Skip Not recently updated contact
                            elif (recent_update_contact_json_response.get('contacts')[0]['properties']['lastmodifieddate']['value']) > modifiedDateForContact:
                                updated_contact_ids.append(contacts_id['canonical-vid'])
                                hubspot_modifiedDateForContact = recent_update_contact_json_response.get('contacts')[0].get('properties').get('lastmodifieddate').get('value')

                        updated_contact_ids.reverse()
                        if hubspot_instance.active  and updated_contact_ids and hubspot_instance.hubspot_is_import_contacts:
                            self.update_contact_details_and_create(updated_contact_ids, hubspot_instance)
                            hubspot_instance.modifiedDateForContact = hubspot_modifiedDateForContact

                        else:
                            break
                        hubspot_instance.all_contact = True

                    message = 'Completed Getting All contacts from hubspot'
                    self.env['hubspot.logger'].create_log_message('Import Contacts', message)
                    logger.info(
                        'Completed Getting modified contacts from hubspot------------------------------------------------------')
                except Exception as e:
                    error_message = 'Error while getting contacts in odoo \nHubspot response %s' % (str(e))
                    self.env['hubspot.logger'].create_log_message('Import Contacts', error_message)
                    logger.exception("Error in getModifiedContactsFromHubspot------------>\n" + str(e))
                    hubspot_instance._raise_user_error(e)
            
    def createQueueContactsInOdoo(self, contact_info, hubspot_instance,line):
        try:
            newcontactModifiedDate = 10000000.0
           
            if 'lastmodifieddate' in contact_info:
                if contact_info['lastmodifieddate']['value']:
                    newcontactModifiedDate = int(contact_info['lastmodifieddate']['value'])
            vals = {}
            # if contact_info['hubspot_id']:
            #     vals['hubspot_id'] = contact_info['hubspot_id']
            # contactName = ''
              
            # if 'firstname' in contact_info:
            #     if len(contact_info['firstname']['value']) > 0:
            #         contactName += contact_info['firstname']['value'] + ' '
            # if 'lastname' in contact_info:
            #     if len(contact_info['lastname']['value']) > 0:
            #         contactName += contact_info['lastname']['value']
            # elif contactName == '':
            #     contactName = "Unknown"
            # vals['name'] = contactName
            # vals['customer_rank'] = 1
            for each_identity in contact_info['identity-profiles']:
                if 'identities' in each_identity:
                    for each_key in each_identity['identities']:
                        if each_key['type'] == 'EMAIL':
                            vals['email'] = each_key['value']
                            break
            if 'associatedcompanyid' in contact_info and hubspot_instance.hubspot_is_import_company:
                if contact_info['associatedcompanyid']['value']:
                    companyId = self.search([('hubspot_id', '=', contact_info['associatedcompanyid']['value'])],limit=1)
                    if companyId:
                        vals['parent_id'] = companyId.id
                    else:
                        # Hubspot Information
                        hubspot_app_key = hubspot_instance.hubspot_app_key
                        # if Param.get_param('hubspot.all_companies'):
                        AllCompanies = self.getCompaniesFromHubspot(hubspot_instance, contact_info['associatedcompanyid']['value'])
                        self.createNewCompaniesInOdoo(AllCompanies, hubspot_instance)
                        hubspot_instance.all_companies = True
                        companyId = self.search([('hubspot_id', '=', contact_info['associatedcompanyid']['value'])],limit=1)
                        if companyId:
                            vals['parent_id'] = companyId.id

            if 'jobtitle' in contact_info:
                if contact_info['jobtitle']['value']:
                    vals['function'] = contact_info['jobtitle']['value']

            # if 'mobilephone' in contact_info:
            #     if contact_info['mobilephone']['value']:
            #         vals['mobile'] = contact_info['mobilephone']['value']

            if 'phone' in contact_info:
                if contact_info['phone']['value']:
                    vals['phone'] = contact_info['phone']['value']

            if 'address' in contact_info:
                if contact_info['address']['value']:
                    vals['street2'] = contact_info['address']['value']

            if 'city' in contact_info:
                if contact_info['city']['value']:
                    vals['city'] = contact_info['city']['value']

            if 'website' in contact_info:
                if contact_info['website']['value']:
                    vals['website'] = contact_info['website']['value']
            if 'zip' in contact_info:
                if contact_info['zip']['value']:
                    vals['zip'] = contact_info['zip']['value']
            country_id = None
            if 'country' in contact_info and contact_info['country']['value']:
                if contact_info['country']['value'] in ['usa', 'USA', 'us', 'US', 'United States of America', 'united states of america', 'united states', 'United States']:
                    country = self.env['res.country'].search([('code', 'like', 'US')], limit=1)
                else:
                    
                    country = self.env['res.country'].search(['|', ('code', '=', contact_info['country']['value']),
                                                              ('name', '=', contact_info['country']['value'])], limit=1)

                if len(country):
                    country_id = country.id
                    vals['country_id'] = country_id

            if 'state' in contact_info:
                if contact_info['state']['value']:
                    if country_id:
                        state_id = self.env['res.country.state'].search(
                            ['|', ('name', '=', contact_info['state']['value']), ('code', '=', contact_info['state']['value']),
                             ('country_id', '=', country_id)], limit=1)
                    else:
                        state_id = self.env['res.country.state'].search(
                            ['|', ('name', '=', contact_info['state']['value']), ('code', '=', contact_info['state']['value'])], limit=1)
                    if state_id:
                        vals['state_id'] = state_id.id

            # if 'title' in contact_info:
            #     if contact_info['title']['value']:
            #         title_id = self.env['res.partner.title'].search([('name', '=', contact_info['title']['value'])],
            #                                                         limit=1)
            #         if title_id:
            #             vals['title'] = title_id.id
            
                    

            # Sync Owner
            if 'hubspot_owner_id' in contact_info:
                if contact_info['hubspot_owner_id']['value']:
                    owner_id = int(contact_info['hubspot_owner_id']['value'])
                    if owner_id:
                        res_user_id = self.env['res.partner'].search(
                            ['|', ('active', '=', True), ('active', '=', False), ('hubspot_id', '=', owner_id), ('hubspot_instance_id', '=', hubspot_instance.id)], limit=1)
                        if res_user_id:
                            vals['hubspot_id'] = res_user_id.id
                        else:
                            get_user = self.env['res.partner'].getOwnerDetailsFromHubspot(owner_id, hubspot_instance)
                            if get_user:
                                vals['hubspot_id'] = get_user.id
            
            if contact_info['hubspot_id']:
                vals['hubspot_id'] = contact_info['hubspot_id']
            contactName = ''
              
            if 'firstname' in contact_info:
                if len(contact_info['firstname']['value']) > 0:
                    contactName += contact_info['firstname']['value'] + ' '
            if 'lastname' in contact_info:
                if len(contact_info['lastname']['value']) > 0:
                    contactName += contact_info['lastname']['value']
            elif contactName == '':
                contactName = "Unknown"
            vals['name'] = contactName
            vals['customer_rank'] = 1
            partner_id = self.search(
                ['|', ('active', '=', True), ('active', '=', False), ('hubspot_id', '=', str(contact_info['hubspot_id'])), ('hubspot_instance_id', '=', hubspot_instance.id)],
                limit=1)
            
            if not partner_id:
                if 'email' in vals:
                    if self.env.context.get('from_skipped_contacts'):
                        vals['hubspot_instance_id'] = hubspot_instance.id
                        partner_id = self.with_context({'from_hubspot': True}).create(vals)
                        # hubspot_instance.modifiedDateForContact = newcontactModifiedDate
                        logger.info("Created New Contact Into Odoo -----------2 " + str(partner_id.id))
                        line.state='done'
                        hubspot_contact_id = vals['hubspot_id']
                        results =''
                        if line.hubspot_image_data:
                            results = json.loads(line.hubspot_image_data)
                    
                        if results:
                            contact_id = self.env['res.partner'].sudo().search(
                                    [('type', '=', 'contact'), ('hubspot_id', '=', hubspot_contact_id), ('hubspot_instance_id', '=', hubspot_instance.id)],limit=1)
                                        
                                        
                            model_id = self.env['ir.model']._get('res.partner').id
                            model_name = 'res.partner'
                            
                            for result in results:
                                if result:
                                    create_attachment = self.create_attachment(result, contact_id, model_name)
                                    if create_attachment:
                                        logger.info("Attachment created successfully: %s" % create_attachment.id)
                                    else:
                                        logger.warning("Failed to create attachment for: %s" % result['name'])
                        
                        self.env.cr.commit()

                        return partner_id
                    elif not self.env.context.get('from_skipped_contacts'):
                        vals['hubspot_instance_id'] = hubspot_instance.id
                        partner_id = self.with_context({'from_hubspot': True}).create(vals)
                        # hubspot_instance.modifiedDateForContact = newcontactModifiedDate
                        logger.info("Created New Contact Into Odoo -----------3 " + str(partner_id.id))
                        line.state='done'
                        hubspot_contact_id = vals['hubspot_id']
                        results =''
                        if line.hubspot_image_data:
                            results = json.loads(line.hubspot_image_data)
                    
                        if results:
                            contact_id = self.env['res.partner'].sudo().search(
                                    [('type', '=', 'contact'), ('hubspot_id', '=', hubspot_contact_id), ('hubspot_instance_id', '=', hubspot_instance.id)],limit=1)
                                        
                                        
                            model_id = self.env['ir.model']._get('res.partner').id
                            model_name = 'res.partner'
                            
                            for result in results:
                                if result:
                                    create_attachment = self.create_attachment(result, contact_id, model_name)
                                    if create_attachment:
                                        logger.info("Attachment created successfully: %s" % create_attachment.id)
                                    else:
                                        logger.warning("Failed to create attachment for: %s" % result['name'])
                            
                        self.env.cr.commit()

                        
                        
                        return partner_id
                    
                else:
                    if self.env.context.get('from_skipped_contacts'):
                        vals['hubspot_instance_id'] = hubspot_instance.id
                        partner_id = self.with_context({'from_hubspot': True}).create(vals)
                        # hubspot_instance.modifiedDateForContact = newcontactModifiedDate
                        logger.info("Created New Contact Into Odoo -----------4 " + str(partner_id.id))
                        line.state='done'
                        hubspot_contact_id = vals['hubspot_id']
                        results =''
                        if line.hubspot_image_data:
                            results = json.loads(line.hubspot_image_data)
                    
                        if results:
                            contact_id = self.env['res.partner'].sudo().search(
                                    [('type', '=', 'contact'), ('hubspot_id', '=', hubspot_contact_id), ('hubspot_instance_id', '=', hubspot_instance.id)],limit=1)
                                        
                                        
                            model_id = self.env['ir.model']._get('res.partner').id
                            model_name = 'res.partner'
                            
                            for result in results:
                                if result:
                                    create_attachment = self.create_attachment(result, contact_id, model_name)
                                    if create_attachment:
                                        logger.info("Attachment created successfully: %s" % create_attachment.id)
                                    else:
                                        logger.warning("Failed to create attachment for: %s" % result['name'])
                        
                        self.env.cr.commit()

                        return partner_id
                    elif not self.env.context.get('from_skipped_contacts'):
                        vals['hubspot_instance_id'] = hubspot_instance.id
                        partner_id = self.with_context({'from_hubspot': True}).create(vals)
                        # hubspot_instance.modifiedDateForContact = newcontactModifiedDate
                        logger.info("Created New Contact Into Odoo -----------5 " + str(partner_id.id))
                        line.state='done'
                        hubspot_contact_id = vals['hubspot_id']
                        results =''
                        if line.hubspot_image_data:
                            results = json.loads(line.hubspot_image_data)
                    
                        if results:
                            contact_id = self.env['res.partner'].sudo().search(
                                    [('type', '=', 'contact'), ('hubspot_id', '=', hubspot_contact_id), ('hubspot_instance_id', '=', hubspot_instance.id)],limit=1)
                                        
                                        
                            model_id = self.env['ir.model']._get('res.partner').id
                            model_name = 'res.partner'
                            
                            for result in results:
                                if result:
                                    create_attachment = self.create_attachment(result, contact_id, model_name)
                                    if create_attachment:
                                        logger.info("Attachment created successfully: %s" % create_attachment.id)
                                    else:
                                        logger.warning("Failed to create attachment for: %s" % result['name'])
                        
                        
                        self.env.cr.commit()
                        return partner_id
            else:
                logger.info("+++++++++++ Contacts already imported")
                line.state = 'done'
                return partner_id           
                
                

          

        except Exception as e:
            error_message = 'Error while creating hubspot contacts in odoo vals: %s\n Hubspot response %s' % (
                contact_info, str(e))
            log_message = self.env['hubspot.logger'].create_log_message('Import Contacs', error_message)
            logger.exception("Exception in Creating New Contacts in Odoo :\n" + error_message)

    @api.model
    def createImportContactsInOdoo(self, contact_info, hubspot_instance):
        try:
            newcontactModifiedDate = 10000000.0
            iban_detail = False
            if 'lastmodifieddate' in contact_info:
                if contact_info['lastmodifieddate']['value']:
                    newcontactModifiedDate = int(contact_info['lastmodifieddate']['value'])
            vals = {}
            # if contact_info['hubspot_id']:
            #     vals['hubspot_id'] = contact_info['hubspot_id']
            # contactName = ''
              
            # if 'firstname' in contact_info:
            #     if len(contact_info['firstname']['value']) > 0:
            #         contactName += contact_info['firstname']['value'] + ' '
            # if 'lastname' in contact_info:
            #     if len(contact_info['lastname']['value']) > 0:
            #         contactName += contact_info['lastname']['value']
            # elif contactName == '':
            #     contactName = "Unknown"
            # vals['name'] = contactName
            # vals['customer_rank'] = 1
            for each_identity in contact_info['identity-profiles']:
                if 'identities' in each_identity:
                    for each_key in each_identity['identities']:
                        if each_key['type'] == 'EMAIL':
                            vals['email'] = each_key['value']
                            break
            if 'associatedcompanyid' in contact_info and hubspot_instance.hubspot_is_import_company:
                if contact_info['associatedcompanyid']['value']:
                    companyId = self.search([('hubspot_id', '=', contact_info['associatedcompanyid']['value'])],limit=1)
                    if companyId:
                        vals['parent_id'] = companyId.id
                    else:
                        # Hubspot Information
                        hubspot_app_key = hubspot_instance.hubspot_app_key
                        # if Param.get_param('hubspot.all_companies'):
                        AllCompanies = self.getCompaniesFromHubspot(hubspot_instance, contact_info['associatedcompanyid']['value'])
                        self.createNewCompaniesInOdoo(AllCompanies, hubspot_instance)
                        hubspot_instance.all_companies = True
                        companyId = self.search([('hubspot_id', '=', contact_info['associatedcompanyid']['value'])],limit=1)
                        if companyId:
                            vals['parent_id'] = companyId.id

            if 'jobtitle' in contact_info:
                if contact_info['jobtitle']['value']:
                    vals['function'] = contact_info['jobtitle']['value']

            # if 'mobilephone' in contact_info:
            #     if contact_info['mobilephone']['value']:
            #         vals['mobile'] = contact_info['mobilephone']['value']

            if 'phone' in contact_info:
                if contact_info['phone']['value']:
                    vals['phone'] = contact_info['phone']['value']

            if 'address' in contact_info:
                if contact_info['address']['value']:
                    vals['street2'] = contact_info['address']['value']

            if 'city' in contact_info:
                if contact_info['city']['value']:
                    vals['city'] = contact_info['city']['value']

            if 'website' in contact_info:
                if contact_info['website']['value']:
                    vals['website'] = contact_info['website']['value']
            if 'zip' in contact_info:
                if contact_info['zip']['value']:
                    vals['zip'] = contact_info['zip']['value']
            country_id = None
            if 'country' in contact_info and contact_info['country']['value']:
                if contact_info['country']['value'] in ['usa', 'USA', 'us', 'US', 'United States of America', 'united states of america', 'united states', 'United States']:
                    country = self.env['res.country'].search([('code', 'like', 'US')], limit=1)
                else:
                    
                    country = self.env['res.country'].search(['|', ('code', '=', contact_info['country']['value']),
                                                              ('name', '=', contact_info['country']['value'])], limit=1)

                if len(country):
                    country_id = country.id
                    vals['country_id'] = country_id

            if 'state' in contact_info:
                if contact_info['state']['value']:
                    if country_id:
                        state_id = self.env['res.country.state'].search(
                            ['|', ('name', '=', contact_info['state']['value']), ('code', '=', contact_info['state']['value']),
                             ('country_id', '=', country_id)], limit=1)
                    else:
                        state_id = self.env['res.country.state'].search(
                            ['|', ('name', '=', contact_info['state']['value']), ('code', '=', contact_info['state']['value'])], limit=1)
                    if state_id:
                        vals['state_id'] = state_id.id

            # if 'title' in contact_info:
            #     if contact_info['title']['value']:
            #         title_id = self.env['res.partner.title'].search([('name', '=', contact_info['title']['value'])],
            #                                                         limit=1)
            #         if title_id:
            #             vals['title'] = title_id.id
            
                    

            # Sync Owner
            if 'hubspot_owner_id' in contact_info:
                if contact_info['hubspot_owner_id']['value']:
                    owner_id = int(contact_info['hubspot_owner_id']['value'])
                    if owner_id:
                        res_user_id = self.env['res.partner'].search(
                            ['|', ('active', '=', True), ('active', '=', False), ('hubspot_id', '=', owner_id), ('hubspot_instance_id', '=', hubspot_instance.id)], limit=1)
                        if res_user_id:
                            vals['hubspot_id'] = res_user_id.id
                        else:
                            get_user = self.env['res.partner'].getOwnerDetailsFromHubspot(owner_id, hubspot_instance)
                            if get_user:
                                vals['hubspot_id'] = get_user.id
            if contact_info['hubspot_id']:
                vals['hubspot_id'] = contact_info['hubspot_id']
                contactName = ''
                
                if 'firstname' in contact_info:
                    if len(contact_info['firstname']['value']) > 0:
                        contactName += contact_info['firstname']['value'] + ' '
                if 'lastname' in contact_info:
                    if len(contact_info['lastname']['value']) > 0:
                        contactName += contact_info['lastname']['value']
                elif contactName == '':
                    contactName = "Unknown"
                vals['name'] = contactName
                vals['customer_rank'] = 1
            
            partner_id = self.search(
                ['|', ('active', '=', True), ('active', '=', False), ('hubspot_id', '=', str(contact_info['hubspot_id'])), ('hubspot_instance_id', '=', hubspot_instance.id)],
                limit=1)
            
            if not partner_id:
                if 'email' in vals:
                    if self.env.context.get('from_skipped_contacts'):
                        vals['hubspot_instance_id'] = hubspot_instance.id
                        partner_id = self.with_context({'from_hubspot': True}).create(vals)
                        # hubspot_instance.modifiedDateForContact = newcontactModifiedDate
                        logger.info("Created New Contact Into Odoo -----------2 " + str(partner_id.id))
                        hubspot_contact_id = vals['hubspot_id']
                        try:
                
                            response_get_associated_contact_attachment_detail = hubspot_instance._send_get_request(
                                f'/engagements/v1/engagements/associated/contact/{hubspot_contact_id}/paged')
                        
                                
                                    
                            json_response_get_associated_contact_attachment_detail = json.loads(response_get_associated_contact_attachment_detail)
                            
                            
                            results = json_response_get_associated_contact_attachment_detail.get('results', [])
                    
                            if results:
                                contact_id = self.env['res.partner'].sudo().search(
                                    [('type', '=', 'contact'), ('hubspot_id', '=', hubspot_contact_id), ('hubspot_instance_id', '=', hubspot_instance.id)],limit=1)
                            
                                model_id = self.env['ir.model']._get('res.partner').id
                                model_name = 'res.partner'
                                        
                                for result in results:
                                    attachments = result.get('attachments', [])
                                    for attachment in attachments:
                                        attachment_id = attachment.get('id')
                                        if attachment_id:
                                            attachment_details = self.get_attachment_by_id(attachment_id, hubspot_instance)
                                            if attachment_details:
                                                create_attachment = self.create_attachment(attachment_details, contact_id, model_name)
                                                if create_attachment:
                                                    logger.info("Attachment created successfully: %s" % create_attachment.id)
                                                else:
                                                    logger.warning("Failed to create attachment for: %s" % attachment_details['name'])
                            else:
                                logger.warning("No attachments found in the response for hubspot_contact_id: %s", hubspot_contact_id)
                                
                                    
                                
                        except json.JSONDecodeError:
                            logger.error("Failed to parse JSON response for hubspot_contact_id: %s", hubspot_contact_id)
                        except Exception as e:
                            logger.error("An unexpected error occurred: %s", str(e))
                        self.env.cr.commit()
                        return partner_id
                    elif not self.env.context.get('from_skipped_contacts'):
                        vals['hubspot_instance_id'] = hubspot_instance.id
                        partner_id = self.with_context({'from_hubspot': True}).create(vals)
                        # hubspot_instance.modifiedDateForContact = newcontactModifiedDate
                        logger.info("Created New Contact Into Odoo -----------3 " + str(partner_id.id))
                        
                        hubspot_contact_id = vals['hubspot_id']
                        try:
                
                            response_get_associated_contact_attachment_detail = hubspot_instance._send_get_request(
                                f'/engagements/v1/engagements/associated/contact/{hubspot_contact_id}/paged')
                            
                            
                            
                            json_response_get_associated_contact_attachment_detail = json.loads(response_get_associated_contact_attachment_detail)
                            
                            
                            results = json_response_get_associated_contact_attachment_detail.get('results', [])
                    
                            if results:
                                contact_id = self.env['res.partner'].sudo().search(
                                    [('type', '=', 'contact'), ('hubspot_id', '=', hubspot_contact_id), ('hubspot_instance_id', '=', hubspot_instance.id)],limit=1)
                            
                                model_id = self.env['ir.model']._get('res.partner').id
                                model_name = 'res.partner'
                                
                                for result in results:
                                    attachments = result.get('attachments', [])
                                    for attachment in attachments:
                                        attachment_id = attachment.get('id')
                                        if attachment_id:
                                            attachment_details = self.get_attachment_by_id(attachment_id, hubspot_instance)
                                            if attachment_details:
                                                create_attachment = self.create_attachment(attachment_details, contact_id, model_name)
                                                if create_attachment:
                                                    logger.info("Attachment created successfully: %s" % create_attachment.id)
                                                else:
                                                    logger.warning("Failed to create attachment for: %s" % attachment_details['name'])
                            else:
                                logger.warning("No attachments found in the response for hubspot_contact_id: %s", hubspot_contact_id)
                        
                            
            
                        except json.JSONDecodeError:
                            logger.error("Failed to parse JSON response for hubspot_contact_id: %s", hubspot_contact_id)
                        except Exception as e:
                            logger.error("An unexpected error occurred: %s", str(e))
                            
                        self.env.cr.commit()
                        
                        
                        return partner_id
                    
                else:
                    if self.env.context.get('from_skipped_contacts'):
                        vals['hubspot_instance_id'] = hubspot_instance.id
                        partner_id = self.with_context({'from_hubspot': True}).create(vals)
                        # hubspot_instance.modifiedDateForContact = newcontactModifiedDate
                        logger.info("Created New Contact Into Odoo -----------4 " + str(partner_id.id))
                        hubspot_contact_id = vals['hubspot_id']
                        try:
                   
                            response_get_associated_contact_attachment_detail = hubspot_instance._send_get_request(
                                f'/engagements/v1/engagements/associated/contact/{hubspot_contact_id}/paged')
                        
                            
                            
                            json_response_get_associated_contact_attachment_detail = json.loads(response_get_associated_contact_attachment_detail)
                            
                            
                            results = json_response_get_associated_contact_attachment_detail.get('results', [])
                    
                            if results:
                                contact_id = self.env['res.partner'].sudo().search(
                                    [('type', '=', 'contact'), ('hubspot_id', '=', hubspot_contact_id), ('hubspot_instance_id', '=', hubspot_instance.id)],limit=1)
                            
                                model_id = self.env['ir.model']._get('res.partner').id
                                model_name = 'res.partner'
                                
                                for result in results:
                                    attachments = result.get('attachments', [])
                                    for attachment in attachments:
                                        attachment_id = attachment.get('id')
                                        if attachment_id:
                                            attachment_details = self.get_attachment_by_id(attachment_id, hubspot_instance)
                                            if attachment_details:
                                                create_attachment = self.create_attachment(attachment_details, contact_id, model_name)
                                                if create_attachment:
                                                    logger.info("Attachment created successfully: %s" % create_attachment.id)
                                                else:
                                                    logger.warning("Failed to create attachment for: %s" % attachment_details['name'])
                            else:
                                logger.warning("No attachments found in the response for hubspot_contact_id: %s", hubspot_contact_id)
                    
                        
                
                        except json.JSONDecodeError:
                            logger.error("Failed to parse JSON response for hubspot_contact_id: %s", hubspot_contact_id)
                        except Exception as e:
                            logger.error("An unexpected error occurred: %s", str(e))
                        
                        self.env.cr.commit()
                        return partner_id
                    elif not self.env.context.get('from_skipped_contacts'):
                        vals['hubspot_instance_id'] = hubspot_instance.id
                        partner_id = self.with_context({'from_hubspot': True}).create(vals)
                        # hubspot_instance.modifiedDateForContact = newcontactModifiedDate
                        logger.info("Created New Contact Into Odoo -----------5 " + str(partner_id.id))

                        hubspot_contact_id = vals['hubspot_id']
                        try:
                   
                            response_get_associated_contact_attachment_detail = hubspot_instance._send_get_request(
                                f'/engagements/v1/engagements/associated/contact/{hubspot_contact_id}/paged')
                        
                           
                            
                            json_response_get_associated_contact_attachment_detail = json.loads(response_get_associated_contact_attachment_detail)
                            
                            
                            results = json_response_get_associated_contact_attachment_detail.get('results', [])
                    
                            if results:
                                contact_id = self.env['res.partner'].sudo().search(
                                    [('type', '=', 'contact'), ('hubspot_id', '=', hubspot_contact_id), ('hubspot_instance_id', '=', hubspot_instance.id)],limit=1)
                            
                                model_id = self.env['ir.model']._get('res.partner').id
                                model_name = 'res.partner'
                                
                                for result in results:
                                    attachments = result.get('attachments', [])
                                    for attachment in attachments:
                                        attachment_id = attachment.get('id')
                                        if attachment_id:
                                            attachment_details = self.get_attachment_by_id(attachment_id, hubspot_instance)
                                            if attachment_details:
                                                create_attachment = self.create_attachment(attachment_details, contact_id, model_name)
                                                if create_attachment:
                                                    logger.info("Attachment created successfully: %s" % create_attachment.id)
                                                else:
                                                    logger.warning("Failed to create attachment for: %s" % attachment_details['name'])
                            else:
                                logger.warning("No attachments found in the response for hubspot_contact_id: %s", hubspot_contact_id)
                      
                            
                    
                        except json.JSONDecodeError:
                            logger.error("Failed to parse JSON response for hubspot_contact_id: %s", hubspot_contact_id)
                        except Exception as e:
                            logger.error("An unexpected error occurred: %s", str(e))
                        
                        
                        self.env.cr.commit()
                        return partner_id
            else:
                logger.info("+++++++++++ Contacts already imported")
                return partner_id           
                
                

          

        except Exception as e:
            error_message = 'Error while creating hubspot contacts in odoo vals: %s\n Hubspot response %s' % (
                contact_info, str(e))
            log_message = self.env['hubspot.logger'].create_log_message('Import Contacs', error_message)
            logger.exception("Exception in Creating New Contacts in Odoo :\n" + error_message)
            
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
    def createNewContactsInOdooFieldMapping(self, contact_info, hubspot_instance):
        contact_field_mapping = self.env['contact.field.mapping'].search([('hubspot_instance_id', '=', hubspot_instance.id)])
        vals = {}
        try:
            newcontactModifiedDate = 10000000.0
            
            for contact_field_mapping_id in contact_field_mapping:
                technical_name = contact_field_mapping_id.hubspot_fields.technical_name
                if technical_name in contact_info['properties']:
                    if 'lastmodifieddate' in contact_info['properties'] and contact_info['properties']['lastmodifieddate']['value']:
                        newcontactModifiedDate = int(contact_info['properties']['lastmodifieddate']['value'])
                    
                    field_value = contact_info['properties'][technical_name]
                    
                    if contact_field_mapping_id.hubspot_fields.field_type == 'date':
                        if 'versions' in field_value and field_value['versions']:
                            timestamp = field_value['versions'][0]['timestamp']
                            vals[contact_field_mapping_id.odoo_fields.name] = self.env['mail.activity'].convert_epoch_to_gmt_timestamp(timestamp)
                        else:
                            logger.info(f"No timestamp available for {technical_name}")
                    else:
                        vals[contact_field_mapping_id.odoo_fields.name] = field_value.get('value', '')

            partner_id = self.search(
                ['|', ('active', '=', True), ('active', '=', False), 
                ('hubspot_id', '=', str(contact_info['canonical-vid'])), 
                ('hubspot_instance_id', '=', hubspot_instance.id)],
                limit=1
            )
            
            if partner_id and vals:
                try:
                    odoo_modifiedDate = convert_time_to_unix_timestamp(partner_id.write_date)
                    vals['hubspot_instance_id'] = hubspot_instance.id
                    partner_id.with_context({'from_hubspot': True}).write(vals)
                    logger.info(f"Updated existing Odoo contact with HubSpot ID {partner_id.hubspot_id}")
                    self.env.cr.commit()
                    return partner_id
                except Exception as update_exception:
                    error_message = f"Error updating contact {contact_info['canonical-vid']} in Odoo: {str(update_exception)}"
                    self.env['hubspot.logger'].create_log_message('Import Contacts', error_message)
                    logger.warning(error_message)
            elif not partner_id and vals:
                try:
                    partner_id = self.with_context({'from_hubspot': True}).create(vals)
                    hubspot_instance.modifiedDateForContact = newcontactModifiedDate
                    logger.info(f"Created new contact in Odoo with ID {partner_id.id}")
                    self.env.cr.commit()
                    return partner_id
                except Exception as create_exception:
                    error_message = f"Error creating contact {contact_info['canonical-vid']} in Odoo: {str(create_exception)}"
                    self.env['hubspot.logger'].create_log_message('Import Contacts', error_message)
                    logger.warning(error_message)
        except Exception as e:
            error_message = f"Error while creating or updating HubSpot contacts in Odoo. Contact info: {contact_info}\n HubSpot response: {str(e)}"
            self.env['hubspot.logger'].create_log_message('Import Contacts', error_message)
            logger.exception("Exception while handling HubSpot contact import in Odoo:\n" + error_message)
            hubspot_instance._raise_user_error(e)
        
        logger.info('Contacts imported or updated successfully in Odoo from custom field mapping')



    @api.model
    def _cron_export_contacts_to_hubspot(self):
        hubspot_instance_obj = self.env['hubspot.instance'].search([('active', '=', True), ('hubspot_is_export_contacts', '=', True)])
        for hubspot_instance in hubspot_instance_obj:
            self.export_contacts_to_hubspot(hubspot_instance)

    # Export Contacts
    @api.model
    def export_contacts_to_hubspot(self, hubspot_instance):
        """This function is called from cron to export contacts to hubspot"""
        # Hubspot Information
        srch_partner_ids = self.env['res.partner'].search([('hubspot_id', '=', False), ('type', '=', 'contact'),
                                                           ('active', '=', True)])

        if hubspot_instance.default_instance and hubspot_instance.active and hubspot_instance.hubspot_is_export_contacts:
            for partner in srch_partner_ids:
                if not partner.hubspot_id and not partner.is_company:
                    contact_field_mapping = self.env['contact.field.mapping'].search(
                        [('hubspot_instance_id', '=', hubspot_instance.id)])
                    partner.createNewContactsInHubspot(hubspot_instance)
                    if len(contact_field_mapping):
                        partner.createNewContactsInHubspotFieldMapping(hubspot_instance, contact_field_mapping)

    def createNewContactsInHubspotFieldMapping(self, hubspot_instance, contact_field_mapping):
        properties = []
        odoo_field_list = []
        for contact_field_mapping_id in contact_field_mapping:
            if contact_field_mapping_id.odoo_fields.name and contact_field_mapping_id.hubspot_fields.technical_name:
                odoo_field_list.append(contact_field_mapping_id.odoo_fields.name)
                partner_read_obj = self.read()[0]
                if not self.is_company:
                    partner_dict = {}
                    if contact_field_mapping_id.odoo_fields.name in partner_read_obj.keys():
                        if partner_read_obj.values():
                            if partner_read_obj.get(contact_field_mapping_id.odoo_fields.name):
                                if contact_field_mapping_id.hubspot_fields.field_type == 'date':
                                    
                                    format_date = convert_time_to_unix_timestamp(partner_read_obj.get(contact_field_mapping_id.odoo_fields.name))
                                    properties.append({'property': contact_field_mapping_id.hubspot_fields.technical_name, 'value': format_date})
                                else:
                                    properties.append({'property': contact_field_mapping_id.hubspot_fields.technical_name,
                                                       'value': str(partner_read_obj.get(contact_field_mapping_id.odoo_fields.name))})

        if properties:
            try:
                try:
                    if self.hubspot_id and self.hubspot_instance_id:
                        response_create_contact = hubspot_instance._send_post_request('/contacts/v1/contact/vid/' + str(self.hubspot_id) + '/profile', {'properties': properties})
                        json_response_create_contact = json.loads(response_create_contact)
                    else:
                        response_create_contact = hubspot_instance._send_post_request('/contacts/v1/contact/', ({'properties': properties}))
                        json_response_create_contact = json.loads(response_create_contact)
                        self.with_context(from_hubspot=True).write({'hubspot_id': json_response_create_contact['canonical-vid']})
                        self.with_context(from_hubspot=True).write({'hubspot_instance_id': hubspot_instance.id})
                    if self.parent_id and hubspot_instance.hubspot_is_export_company:
                        if not self.parent_id.hubspot_id:
                            self.parent_id.createNewCompanyInHubspot(hubspot_instance)
                        hubspot_instance._send_put_request('/companies/v2/companies/' + str(self.parent_id.hubspot_id) + '/contacts/' + str(self.hubspot_id), ({'properties': {}}))
                        self.with_context(from_hubspot=True).write({'hubspot_id': json_response_create_contact['canonical-vid']})
                except Exception as e:
                    response_existing_contact = hubspot_instance._send_get_request('/contacts/v1/contact/email/' + str(self.email) + '/profile')
                    json_response_existing_contact = json.loads(response_existing_contact)
                    if json_response_existing_contact:
                        self.with_context(from_hubspot=True).write({'hubspot_id': json_response_existing_contact['canonical-vid']})
                        self.with_context(from_hubspot=True).write({'hubspot_instance_id': hubspot_instance.id})
                    else:
                        error_message = 'For custom field mapping error while exporting odoo contact %d \n\n Odoo vals: %s\n Hubspot response %s' % (
                            self.id, str(properties), str(json_response_existing_contact))
                        self.env['hubspot.logger'].create_log_message('Export Contacts', error_message)
                        logger.exception("Exception in Creating contacts in hubspot using field mapping :\n" + error_message)
                    hubspot_instance._raise_user_error(e)
            except Exception as e:
                error_message = 'For custom field mapping error while exporting odoo contact %d \n\n Odoo vals: %s\n Hubspot response %s' % (
                    self.id, str(properties), str(e))
                self.env['hubspot.logger'].create_log_message('Export Contacts', error_message)
                logger.exception("Exception in Hubspot Connection  :\n" + str(e))
                hubspot_instance._raise_user_error(e)

    def createNewContactsInHubspot(self, hubspot_instance):
        logger.info('Creating new contacts in hubspot')
        for eachNewContact in self:
            if not eachNewContact.is_company:
                # create hubspot dictionary
                properties = []
                if eachNewContact.email:
                    properties.append({'property': 'email', 'value': str(eachNewContact.email)})

                if eachNewContact.name:
                    properties.append({'property': 'firstname', 'value': (eachNewContact.name).split(' ')[0]})
                    if len(eachNewContact.name.split(' ')) > 1:
                        properties.append({'property': 'lastname', 'value': (eachNewContact.name).split(' ')[-1]})
                if eachNewContact.parent_id:
                    properties.append({'property': 'company', 'value': eachNewContact.parent_id.name})
                # if eachNewContact.mobile:
                #     properties.append({'property': 'mobilephone', 'value': eachNewContact.mobile})
                if eachNewContact.phone:
                    properties.append({'property': 'phone', 'value': eachNewContact.phone})
                if eachNewContact.function:
                    properties.append({'property': 'jobtitle', 'value': eachNewContact.function})
                if eachNewContact.city:
                    properties.append({'property': 'city', 'value': eachNewContact.city})
                if eachNewContact.state_id:
                    properties.append({'property': 'state', 'value': eachNewContact.state_id.name})
                if eachNewContact.country_id:
                    properties.append({'property': 'country', 'value': eachNewContact.country_id.name})
                if eachNewContact.street or eachNewContact.street2:
                    address = ''
                    if eachNewContact.street:
                        address += eachNewContact.street
                    elif eachNewContact.street2:
                        address += eachNewContact.street2
                    properties.append({'property': 'address', 'value': address})
                if eachNewContact.zip:
                    properties.append({'property': 'zip', 'value': eachNewContact.zip})
                if eachNewContact.website:
                    properties.append({'property': 'website', 'value': eachNewContact.website})
                #                 if eachNewContact.fax:
                #                     properties.append({'property': 'fax', 'value': eachNewContact.fax})
                # if eachNewContact.title:
                #     properties.append({'property': 'salutation', 'value': eachNewContact.title.name})

                # user (Owner) sync
                if eachNewContact.user_id:
                    if not eachNewContact.user_id.hubspot_uid:
                        logger.warning("Odoo User Not Available In Hubspot")
                        self.env['res.partner'].syncAllUsers(hubspot_instance)
                    if eachNewContact.user_id.hubspot_uid:
                        properties.append({'property': 'hubspot_owner_id', 'value': eachNewContact.user_id.hubspot_uid})
                else:
                    properties.append({'property': 'hubspot_owner_id', 'value': ''})
                # create new hubspot contact
                if properties:
                    try:
                        try:
                            response_create_contact = hubspot_instance._send_post_request('/contacts/v1/contact/', {'properties': properties})
                            json_response_create_contact = json.loads(response_create_contact)
                            if not json_response_create_contact['canonical-vid']:
                                self.env['hubspot.logger'].create_log_message('Export Contacts', str(json_response_create_contact) + "\nvals: " + str(properties))
                            context_dict = {}
                            context_dict['hubspot_id'] = json_response_create_contact['canonical-vid']
                            eachNewContact.with_context(from_hubspot=True).write(context_dict)
                            eachNewContact.with_context(from_hubspot=True).hubspot_instance_id = hubspot_instance.id
                            if eachNewContact.parent_id and hubspot_instance.hubspot_is_export_company:
                                if not eachNewContact.parent_id.hubspot_id:
                                    eachNewContact.parent_id.createNewCompanyInHubspot(hubspot_instance)
                                hubspot_instance._send_put_request(
                                    '/companies/v2/companies/' + str(eachNewContact.parent_id.hubspot_id) + '/contacts/' + str(eachNewContact.hubspot_id), ({'properties': {}}))
                                eachNewContact.with_context(from_hubspot=True).hubspot_id = eachNewContact['canonical-vid']
                        except Exception as e:
                            response_get_contact = hubspot_instance._send_get_request('/contacts/v1/contact/email/' + str(eachNewContact.email) + '/profile')
                            existingContact = json.loads(response_get_contact)
                            
                            if existingContact:
                                eachNewContact.with_context(from_hubspot=True).hubspot_id = existingContact['canonical-vid']
                                eachNewContact.hubspot_instance_id = hubspot_instance.id
                            else:
                                error_message = 'Error while exporting odoo contact %d \n\n Odoo vals: %s\n Hubspot response %s' % (
                                    eachNewContact.id, str(properties), str(existingContact))
                                self.env['hubspot.logger'].create_log_message('Export Contacts', error_message)
                            hubspot_instance._raise_user_error(e)
                    except Exception as e:
                        error_message = 'Error while exporting odoo contact %d \n\n Odoo vals: %s\n Hubspot response %s' % (
                            eachNewContact.id, str(properties), str(e))
                        self.env['hubspot.logger'].create_log_message('Export Contacts', error_message)
                        logger.exception("Exception in Hubspot Connection  :\n" + str(e))
                        hubspot_instance._raise_user_error(e)
        message = 'Exported contacts successfully'
        self.env['hubspot.logger'].create_log_message('Export Contacts', message)
        logger.info('Exported contacts successfully...')

        
                

    @api.model
    def action_import_skip_companies(self, hubspot_instance):
        if hubspot_instance.active  and hubspot_instance.hubspot_is_import_company:  
            logger.info('Getting All skipped companies from hubspot---------------------------')
            try:
                has_more = True
                offset = 0
                while has_more:
                    company_ids = []
                    record_limit = 90
                    properties = 'hs_lastmodifieddate'
                    response_get_all_companies = hubspot_instance._send_get_request(
                        '/companies/v2/companies/paged?offset=' + str(offset) + '&count=' + str(record_limit) + '&properties=' + properties)
                    json_response_all_contacts = json.loads(response_get_all_companies)
                    has_more = json_response_all_contacts['has-more']
                    offset = json_response_all_contacts['offset']
                    for companies_id in json_response_all_contacts['companies']:
                        # res_partner_id = self.env['res.partner'].sudo().search(
                        #     [('hubspot_instance_id', '=', hubspot_instance.id), ('is_company', '=', True), ('hubspot_id', '=', companies_id.get('companyId'))])
                        # if not res_partner_id:
                        company_ids.append(companies_id['companyId'])
                    if len(company_ids) > 0:
                        logger.info('\n\n\nAll skipped companies ------------------------------------------\n{}'.format(company_ids))
                        logger.info('\n\n\nTotal skipped companies {}'.format(len(company_ids)))
                        self.with_context({'from_skipped_companies': True}).get_company_details_and_create(company_ids, hubspot_instance)

                msg = 'Completed Getting skipped Companies from hubspot'
                self.env['hubspot.logger'].create_log_message('Import Companies', msg)
                logger.info('Completed Getting skipped Companies from hubspot------------------------------------------------------')
            except Exception as e:
                error_message = 'Error while getting skipped companies in odoo \nHubspot response %s' % (str(e))
                logger.info("In skipped import companies exception: %s" % error_message)
                self.env['hubspot.logger'].create_log_message('Import Companies', error_message)
                logger.exception("Error in Getting skipped Companies From Hubspot------------>\n" + error_message)
                hubspot_instance._raise_user_error(e)

    def hubspot_queue_company_create(self,line,hubspot_instance):
        
            company_info_list = []
            company_id = self.createNewQueueCompaniesInOdoo(line, hubspot_instance)
            company_field_mapping = self.env['company.field.mapping'].search([('hubspot_instance_id', '=', hubspot_instance.id)])
            if len(company_field_mapping) > 0:
                company_info = json.loads(line.hubspot_company_data)
                company_info_list.append(company_info)
                self.createNewCompaniesInOdooFieldMapping(company_info_list, company_field_mapping, hubspot_instance)
      
           
           

    def get_company_details_and_create(self, company_ids, hubspot_instance):
        company_id = ''
        for company_id in company_ids:
            try:
                company_info = []
                response_get_contact_by_id = hubspot_instance._send_get_request('/companies/v2/companies/' + str(company_id))
                json_response_get_contact_by_id = json.loads(response_get_contact_by_id)
                company_info.append(json_response_get_contact_by_id)
                logger.info('get company details')
                company_id = self.createNewCompaniesInOdoo(company_info, hubspot_instance)
                company_field_mapping = self.env['company.field.mapping'].search([('hubspot_instance_id', '=', hubspot_instance.id)])
                if len(company_field_mapping) > 0:
                    self.createNewCompaniesInOdooFieldMapping(company_info, company_field_mapping, hubspot_instance)
                    

            except Exception as e:
                error_message = 'Error while importing hubspot companies in odoo Id: %s\n Hubspot response %s' % (
                    company_id, str(e))
                self.env['hubspot.logger'].create_log_message('Import Companies', error_message)
                logger.exception("Exception In getting companies info from Hubspot : \n" + error_message)
                hubspot_instance._raise_user_error(e)
        return company_id
    
    def updated_company_details_and_create(self, company_ids, hubspot_instance):
        company_id = ''
        for company_id in company_ids:
            try:
                company_info = []
                response_get_contact_by_id = hubspot_instance._send_get_request('/companies/v2/companies/' + str(company_id))
                json_response_get_contact_by_id = json.loads(response_get_contact_by_id)
                company_info.append(json_response_get_contact_by_id)
                logger.info('get company details')
                company_id = self.UpdateNewCompaniesInOdoo(company_info, hubspot_instance)
                company_field_mapping = self.env['company.field.mapping'].search([('hubspot_instance_id', '=', hubspot_instance.id)])
                if len(company_field_mapping) > 0:
                    self.createNewCompaniesInOdooFieldMapping(company_info, company_field_mapping, hubspot_instance)
                    
            except Exception as e:
                error_message = 'Error while importing hubspot companies in odoo Id: %s\n Hubspot response %s' % (
                    company_id, str(e))
                self.env['hubspot.logger'].create_log_message('Import Companies', error_message)
                logger.exception("Exception In getting companies info from Hubspot : \n" + error_message)
                hubspot_instance._raise_user_error(e)
        return company_id
    
    @api.model
    def UpdateNewCompaniesInOdoo(self, changedCompanies, hubspot_instance):
        try:
           
            for eachCompany in changedCompanies:
                vals = {}
                newmodifiedDateForCompany = 10000000.0
                if eachCompany.get('properties'):
                    if eachCompany.get('properties').get('hs_lastmodifieddate'):
                        if eachCompany.get('properties'):
                            newmodifiedDateForCompany = int(eachCompany.get('properties').get('hs_lastmodifieddate').get('value'))
                    # if 'name' in eachCompany['properties']:
                    #     if 'value' in eachCompany['properties']['name']:
                    #         if eachCompany['companyId']:
                    #             vals.update({'hubspot_id': eachCompany['companyId']})
                    #         if 'name' in eachCompany['properties']:
                    #             if len(eachCompany['properties']['name']['value']) > 0:
                    #                 vals.update({'name': eachCompany['properties']['name']['value']})
                    #             else:
                    #                 vals.update({'name': 'Unknown'})
                            if 'zip' in eachCompany['properties']:
                                vals.update({'zip': eachCompany['properties']['zip']['value']})

                            if 'city' in eachCompany['properties']:
                                vals.update({'city': eachCompany['properties']['city']['value']})

                            if 'website' in eachCompany['properties']:
                                vals.update({'website': eachCompany['properties']['website']['value']})

                            if 'address' in eachCompany['properties']:
                                vals.update({'street': eachCompany['properties']['address']['value']})
                            if 'address2' in eachCompany['properties']:
                                vals.update({'street2': eachCompany['properties']['address2']['value']})
                            if 'phone' in eachCompany['properties']:
                                vals.update({'phone': eachCompany['properties']['phone']['value']})
                            country_id = None
                           
                            if 'country' in eachCompany['properties'] and eachCompany['properties']['country']['value']:
                                if eachCompany['properties']['country']['value'] in ['usa', 'USA', 'United States of America', 'united states of america', 'united states',
                                                                                     'United States']:
                                    country = self.env['res.country'].search([('code', '=', 'US')], limit=1)
                                else:
                                    country = self.env['res.country'].search(['|', ('code', '=', eachCompany['properties']['country']['value']),
                                                                              ('name', '=', eachCompany['properties']['country']['value'])], limit=1)

                                if len(country):
                                    country_id = country.id
                                    vals['country_id'] = country_id
                            
                                    
                            if 'state' in eachCompany['properties']:
                                if eachCompany['properties']['state']['value']:
                                    if country_id:
                                        state_id = self.env['res.country.state'].search(
                                            ['|', ('name', '=', eachCompany['properties']['state']['value']),
                                             ('code', '=', eachCompany['properties']['state']['value']),
                                             ('country_id', '=', country_id)], limit=1)

                                    else:
                                        state_id = self.env['res.country.state'].search(
                                            ['|', ('name', '=', eachCompany['properties']['state']['value']),
                                             ('code', '=', eachCompany['properties']['state']['value'])], limit=1)

                                    if state_id:
                                        vals['state_id'] = state_id.id
                           
                            for each_identity in eachCompany['properties']:
                                # if eachCompany['properties'][each_identity].has_key('zip'):
                                if 'zip' in eachCompany['properties'][each_identity]:
                                    vals.update({'zip': each_identity['value']})
                                # if eachCompany['properties'][each_identity].has_key('city'):
                                if 'city' in eachCompany['properties'][each_identity]:
                                    vals.update({'city': each_identity['value']})
                                # Sync Owner
                                if 'hubspot_owner_id' in eachCompany['properties']:
                                    owner_id = eachCompany['properties']['hubspot_owner_id']['value']
                                    if owner_id:
                                        res_user_id = self.env['res.partner'].search(
                                            ['|', ('active', '=', True), ('active', '=', False), ('hubspot_id', '=', owner_id), ('hubspot_instance_id', '=', hubspot_instance.id)],
                                            limit=1)
                                        if res_user_id:
                                            vals.update({'hubspot_id': res_user_id.id})
                                        else:
                                            get_user = self.env['res.partner'].getOwnerDetailsFromHubspot(owner_id, hubspot_instance)
                                            if get_user:
                                                vals.update({'hubspot_id': get_user.id})
                            if 'name' in eachCompany['properties']:
                                if 'value' in eachCompany['properties']['name']:
                                    if eachCompany['companyId']:
                                        vals.update({'hubspot_id': eachCompany['companyId']})
                                    if 'name' in eachCompany['properties']:
                                        if len(eachCompany['properties']['name']['value']) > 0:
                                            vals.update({'name': eachCompany['properties']['name']['value']})
                                        else:
                                            vals.update({'name': 'Unknown'})
                            if len(vals) > 0:
                                company_id = self.search(['|', ('active', '=', True), ('active', '=', False), ('hubspot_id', '=', str(eachCompany['companyId'])),
                                                          ('hubspot_instance_id', '=', hubspot_instance.id)])
                                
                                if company_id:
                                    
                                    
                                    odoo_modifiedDate = convert_time_to_unix_timestamp(company_id.write_date)
                                    if self.env.context.get('from_skipped_companies'):
                                        vals['hubspot_instance_id'] = hubspot_instance.id
                                        company_id.with_context({'from_hubspot': True}).write(vals)
                                        # hubspot_instance.modifiedDateForCompany = newmodifiedDateForCompany
                                        logger.info("Write into Existing Odoo Company----------- " + str(company_id.hubspot_id))
                                        hubspot_company_id = vals['hubspot_id']
                                        try:
                                            response_get_associated_company_attachment_detail = hubspot_instance._send_get_request(
                                                f'/engagements/v1/engagements/associated/company/{hubspot_company_id}/paged')
                                            
                                            
                                            json_response_get_associated_company_attachment_detail = json.loads(response_get_associated_company_attachment_detail)
                                            
                                            
                                            results = json_response_get_associated_company_attachment_detail.get('results', [])
                                            contact_id = self.env['res.partner'].sudo().search(
                                                    [('type', '=', 'contact'), ('hubspot_id', '=', hubspot_company_id), ('hubspot_instance_id', '=', hubspot_instance.id)])
                                        
                                            if results:
                                                
                                                
                                                model_id = self.env['ir.model']._get('res.partner').id
                                                model_name = 'res.partner'
                                                
                                                for result in results:
                                                    attachments = result.get('attachments', [])
                                                    for attachment in attachments:
                                                        attachment_id = attachment.get('id')
                                                        if attachment_id:
                                                            attachment_details = self.get_attachment_by_id(attachment_id, hubspot_instance)
                                                            if attachment_details:
                                                                create_attachment = self.create_attachment(attachment_details, contact_id, model_name)
                                                                if create_attachment:
                                                                    logger.info("Attachment created successfully: %s" % create_attachment.id)
                                                                else:
                                                                    logger.warning("Failed to create attachment for: %s" % attachment_details['name'])
                                            else:
                                                logger.warning("No attachments found in the response for hubspot_company_id: %s", hubspot_company_id)
                                           
                                            
                                               
                                        
                                        except json.JSONDecodeError:
                                            logger.error("Failed to parse JSON response for hubspot_company_id: %s", hubspot_company_id)
                                        except Exception as e:
                                            logger.error("An unexpected error occurred: %s", str(e))
                                        self.env.cr.commit()
                                        
                                        return company_id
                                    elif int(newmodifiedDateForCompany) > int(odoo_modifiedDate):
                                        vals['hubspot_instance_id'] = hubspot_instance.id
                                        company_id.with_context({'from_hubspot': True}).write(vals)
                                        # hubspot_instance.modifiedDateForCompany = newmodifiedDateForCompany
                                        logger.info("Write into Existing Odoo Company-----------0 " + str(company_id.hubspot_id))
                                        self.env.cr.commit()
                                        hubspot_company_id = vals['hubspot_id']
                                        try:
                                            response_get_associated_company_attachment_detail = hubspot_instance._send_get_request(
                                                f'/engagements/v1/engagements/associated/company/{hubspot_company_id}/paged')
                                            
                                            
                                            
                                            
                                            json_response_get_associated_company_attachment_detail = json.loads(response_get_associated_company_attachment_detail)
                                            
                                            
                                            results = json_response_get_associated_company_attachment_detail.get('results', [])
                                            contact_id = self.env['res.partner'].sudo().search(
                                                    [('type', '=', 'contact'), ('hubspot_id', '=', hubspot_company_id), ('hubspot_instance_id', '=', hubspot_instance.id)])
                                            if results:
                                                
                                                
                                                model_id = self.env['ir.model']._get('res.partner').id
                                                model_name = 'res.partner'
                                                
                                                for result in results:
                                                    attachments = result.get('attachments', [])
                                                    for attachment in attachments:
                                                        attachment_id = attachment.get('id')
                                                        if attachment_id:
                                                            attachment_details = self.get_attachment_by_id(attachment_id, hubspot_instance)
                                                            if attachment_details:
                                                                create_attachment = self.create_attachment(attachment_details, contact_id, model_name)
                                                                if create_attachment:
                                                                    logger.info("Attachment created successfully: %s" % create_attachment.id)
                                                                else:
                                                                    logger.warning("Failed to create attachment for: %s" % attachment_details['name'])
                                            else:
                                                logger.warning("No attachments found in the response for hubspot_company_id: %s", hubspot_company_id)
                                          
                                            
                                    
                                            
                                        except json.JSONDecodeError:
                                            logger.error("Failed to parse JSON response for hubspot_company_id: %s", hubspot_company_id)
                                        except Exception as e:
                                            logger.error("An unexpected error occurred: %s", str(e))
                                        return company_id
                                
                                    # Create new company in Odoo
                                    
                                if 'website' in vals:
                                    company_id = self.search(
                                        ['|', ('active', '=', True), ('active', '=', False), ('website', '=', ("http://" + vals['website'])), ('is_company', '=', True),
                                            ('hubspot_id', '=', False), ('hubspot_instance_id', '=', False)], limit=1)
                                    if company_id:
                                        odoo_modifiedDate = convert_time_to_unix_timestamp(company_id.write_date)
                                        if self.env.context.get('from_skipped_companies'):
                                            vals['hubspot_instance_id'] = hubspot_instance.id
                                            company_id.with_context({'from_hubspot': True}).write(vals)
                                            # hubspot_instance.modifiedDateForCompany = newmodifiedDateForCompany
                                            logger.info("Write into Existing Odoo Company----------- 1" + str(company_id.hubspot_id))
                                            self.env.cr.commit()
                                            hubspot_company_id = vals['hubspot_id']
                                            try:
                                                response_get_associated_company_attachment_detail = hubspot_instance._send_get_request(
                                                    f'/engagements/v1/engagements/associated/company/{hubspot_company_id}/paged')
                                                
                                                
                                                json_response_get_associated_company_attachment_detail = json.loads(response_get_associated_company_attachment_detail)                                                    
                                                results = json_response_get_associated_company_attachment_detail.get('results', [])
                                                contact_id = self.env['res.partner'].sudo().search(
                                                    [('type', '=', 'contact'), ('hubspot_id', '=', hubspot_company_id), ('hubspot_instance_id', '=', hubspot_instance.id)])
                                                
                                            
                                                if results:
                                                   
                                                    
                                                    model_id = self.env['ir.model']._get('res.partner').id
                                                    model_name = 'res.partner'
                                                    
                                                    for result in results:
                                                        attachments = result.get('attachments', [])
                                                        for attachment in attachments:
                                                            attachment_id = attachment.get('id')
                                                            if attachment_id:
                                                                attachment_details = self.get_attachment_by_id(attachment_id, hubspot_instance)
                                                                if attachment_details:
                                                                    create_attachment = self.create_attachment(attachment_details, contact_id, model_name)
                                                                    if create_attachment:
                                                                        logger.info("Attachment created successfully: %s" % create_attachment.id)
                                                                    else:
                                                                        logger.warning("Failed to create attachment for: %s" % attachment_details['name'])
                                                else:
                                                    logger.warning("No attachments found in the response for hubspot_company_id: %s", hubspot_company_id)
                                               
                                                
                                                   
                                            
                                            except json.JSONDecodeError:
                                                logger.error("Failed to parse JSON response for hubspot_company_id: %s", hubspot_company_id)
                                            except Exception as e:
                                                logger.error("An unexpected error occurred: %s", str(e))
                                            return company_id

                                        elif int(newmodifiedDateForCompany) > int(odoo_modifiedDate):
                                            vals['hubspot_instance_id'] = hubspot_instance.id
                                            company_id.with_context({'from_hubspot': True}).write(vals)
                                            # hubspot_instance.modifiedDateForCompany = newmodifiedDateForCompany
                                            logger.info("Write into Existing Odoo Company-----------new write " + str(company_id.hubspot_id))
                                            
                                            hubspot_company_id = vals['hubspot_id']
                                            try:
                                                response_get_associated_company_attachment_detail = hubspot_instance._send_get_request(
                                                    f'/engagements/v1/engagements/associated/company/{hubspot_company_id}/paged')
                                                
                                                
                                                
                                                
                                                json_response_get_associated_company_attachment_detail = json.loads(response_get_associated_company_attachment_detail)                                                    
                                                results = json_response_get_associated_company_attachment_detail.get('results', [])
                                                contact_id = self.env['res.partner'].sudo().search(
                                                        [('type', '=', 'contact'), ('hubspot_id', '=', hubspot_company_id), ('hubspot_instance_id', '=', hubspot_instance.id)])
                                            
                                                if results:
                                                   
                                                    
                                                    model_id = self.env['ir.model']._get('res.partner').id
                                                    model_name = 'res.partner'
                                                    
                                                    for result in results:
                                                        attachments = result.get('attachments', [])
                                                        for attachment in attachments:
                                                            attachment_id = attachment.get('id')
                                                            if attachment_id:
                                                                attachment_details = self.get_attachment_by_id(attachment_id, hubspot_instance)
                                                                if attachment_details:
                                                                    create_attachment = self.create_attachment(attachment_details, contact_id, model_name)
                                                                    if create_attachment:
                                                                        logger.info("Attachment created successfully: %s" % create_attachment.id)
                                                                    else:
                                                                        logger.warning("Failed to create attachment for: %s" % attachment_details['name'])
                                                else:
                                                    logger.warning("No attachments found in the response for hubspot_company_id: %s", hubspot_company_id)
                                                
                                                    
                                            
                                            
                                            
                                            except json.JSONDecodeError:
                                                logger.error("Failed to parse JSON response for hubspot_company_id: %s", hubspot_company_id)
                                            except Exception as e:
                                                logger.error("An unexpected error occurred: %s", str(e))
                                            self.env.cr.commit()
                                            return company_id
                                       
        except Exception as e:
            error_message = 'Error while creating hubspot companies in odoo %s\n Hubspot response %s' % (
                changedCompanies, str(e))
            self.env['hubspot.logger'].create_log_message('Import Companies', error_message)
            logger.exception("Exception in Creating New Company in Odoo : " + str(e))
            hubspot_instance._raise_user_error(e)
        logger.info('Companies imported successfully in Odoo')

    def createNewQueueCompaniesInOdoo(self,line,hubspot_instance):
        eachCompany = json.loads(line.hubspot_company_data)
        newmodifiedDateForCompany = 10000000.0
        vals = {}
        if eachCompany.get('properties'):
            if eachCompany.get('properties').get('hs_lastmodifieddate'):
                if eachCompany.get('properties'):
                    newmodifiedDateForCompany = int(eachCompany.get('properties').get('hs_lastmodifieddate').get('value'))
            # if 'name' in eachCompany['properties']:
            #     if 'value' in eachCompany['properties']['name']:
            #         if eachCompany['companyId']:
            #             vals.update({'hubspot_id': eachCompany['companyId']})
            #         if 'name' in eachCompany['properties']:
            #             if len(eachCompany['properties']['name']['value']) > 0:
            #                 vals.update({'name': eachCompany['properties']['name']['value']})
            #             else:
            #                 vals.update({'name': 'Unknown'})
                    if 'zip' in eachCompany['properties']:
                        vals.update({'zip': eachCompany['properties']['zip']['value']})

                    if 'city' in eachCompany['properties']:
                        vals.update({'city': eachCompany['properties']['city']['value']})

                    if 'website' in eachCompany['properties']:
                        vals.update({'website': eachCompany['properties']['website']['value']})

                    if 'address' in eachCompany['properties']:
                        vals.update({'street': eachCompany['properties']['address']['value']})
                    if 'address2' in eachCompany['properties']:
                        vals.update({'street2': eachCompany['properties']['address2']['value']})
                    if 'phone' in eachCompany['properties']:
                        vals.update({'phone': eachCompany['properties']['phone']['value']})
                    country_id = None
                    
                    if 'country' in eachCompany['properties'] and eachCompany['properties']['country']['value']:
                        if eachCompany['properties']['country']['value'] in ['usa', 'USA', 'United States of America', 'united states of america', 'united states',
                                                                                'United States']:
                            country = self.env['res.country'].search([('code', '=', 'US')], limit=1)
                        else:
                            country = self.env['res.country'].search(['|', ('code', '=', eachCompany['properties']['country']['value']),
                                                                        ('name', '=', eachCompany['properties']['country']['value'])], limit=1)

                        if len(country):
                            country_id = country.id
                            vals['country_id'] = country_id
                    
                            
                    if 'state' in eachCompany['properties']:
                        if eachCompany['properties']['state']['value']:
                            if country_id:
                                state_id = self.env['res.country.state'].search(
                                    ['|', ('name', '=', eachCompany['properties']['state']['value']),
                                        ('code', '=', eachCompany['properties']['state']['value']),
                                        ('country_id', '=', country_id)], limit=1)

                            else:
                                state_id = self.env['res.country.state'].search(
                                    ['|', ('name', '=', eachCompany['properties']['state']['value']),
                                        ('code', '=', eachCompany['properties']['state']['value'])], limit=1)

                            if state_id:
                                vals['state_id'] = state_id.id
                    for each_identity in eachCompany['properties']:
                        # if eachCompany['properties'][each_identity].has_key('zip'):
                        if 'zip' in eachCompany['properties'][each_identity]:
                            vals.update({'zip': each_identity['value']})
                        # if eachCompany['properties'][each_identity].has_key('city'):
                        if 'city' in eachCompany['properties'][each_identity]:
                            vals.update({'city': each_identity['value']})
                        # Sync Owner
                        if 'hubspot_owner_id' in eachCompany['properties']:
                            owner_id = eachCompany['properties']['hubspot_owner_id']['value']
                            if owner_id:
                                res_user_id = self.env['res.partner'].search(
                                    ['|', ('active', '=', True), ('active', '=', False), ('hubspot_id', '=', owner_id), ('hubspot_instance_id', '=', hubspot_instance.id)],
                                    limit=1)
                                if res_user_id:
                                    vals.update({'hubspot_id': res_user_id.id})
                                else:
                                    get_user = self.env['res.partner'].getOwnerDetailsFromHubspot(owner_id, hubspot_instance)
                                    if get_user:
                                        vals.update({'hubspot_id': get_user.id})
                        if 'name' in eachCompany['properties']:
                            if 'value' in eachCompany['properties']['name']:
                                if eachCompany['companyId']:
                                    vals.update({'hubspot_id': eachCompany['companyId']})
                                if 'name' in eachCompany['properties']:
                                    if len(eachCompany['properties']['name']['value']) > 0:
                                        vals.update({'name': eachCompany['properties']['name']['value']})
                                    else:
                                        vals.update({'name': 'Unknown'})
                        
                    if len(vals) > 0:
                        company_id = self.search(['|', ('active', '=', True), ('active', '=', False), ('hubspot_id', '=', str(eachCompany['companyId'])),
                                                    ('hubspot_instance_id', '=', hubspot_instance.id)],limit=1)
                        if not company_id:
                                    
                            vals.update({'is_company': True})
                            if 'website' in vals:
                                if self.env.context.get('from_skipped_companies'):
                                    vals.update({'hubspot_instance_id': hubspot_instance.id})
                                    hubspot_company_id = self.with_context({'from_hubspot': True}).create(vals)
                                    line.state = 'done'
                                    logger.info("Created New Company Into Odoo1 ----------- " + str(hubspot_company_id.id))
                                    hubspot_company_id = vals['hubspot_id']

                                    
                                    contact_id = self.env['res.partner'].sudo().search(
                                            [('type', '=', 'contact'), ('hubspot_id', '=', hubspot_company_id), ('hubspot_instance_id', '=', hubspot_instance.id)],limit=1)
                                    
                                    results =''
                                    if line.hubspot_image_data:
                                        results = json.loads(line.hubspot_image_data)
                                
                                    if results:
                                        
                                        
                                        model_id = self.env['ir.model']._get('res.partner').id
                                        model_name = 'res.partner'
                                        
                                        for result in results:
                                            if result:
                                                create_attachment = self.create_attachment(result, contact_id, model_name)
                                                if create_attachment:
                                                    logger.info("Attachment created successfully: %s" % create_attachment.id)
                                                else:
                                                    logger.warning("Failed to create attachment for: %s" % result['name'])
                                    
                                    else:
                                        logger.warning("No attachments found in the response for hubspot_company_id: %s", hubspot_company_id)
                                        
                                        
                                    # hubspot_instance.modifiedDateForCompany = newmodifiedDateForCompany
                                    self.env.cr.commit()
                                    return hubspot_company_id
                                elif not self.env.context.get('from_skipped_companies'):
                                    vals.update({'hubspot_instance_id': hubspot_instance.id})
                                    hubspot_company_id = self.with_context({'from_hubspot': True}).create(vals)
                                    line.state='done'
                                    logger.info("Created New Company Into Odoo2 -----------created new " + str(hubspot_company_id.id))
                                    hubspot_company_id = vals['hubspot_id']
                                    
                                    contact_id = self.env['res.partner'].sudo().search(
                                            [('type', '=', 'contact'), ('hubspot_id', '=', hubspot_company_id), ('hubspot_instance_id', '=', hubspot_instance.id)],limit=1)
                                    results =''
                                    if line.hubspot_image_data:
                                        results = json.loads(line.hubspot_image_data)
                                
                                    if results:
                            
                                        model_id = self.env['ir.model']._get('res.partner').id
                                        model_name = 'res.partner'
                                        
                                        for result in results:
                                            if result:
                                                create_attachment = self.create_attachment(result, contact_id, model_name)
                                                if create_attachment:
                                                    logger.info("Attachment created successfully: %s" % create_attachment.id)
                                                else:
                                                    logger.warning("Failed to create attachment for: %s" % result['name'])
                                    
                                    else:
                                        logger.warning("No attachments found in the response for hubspot_company_id: %s", hubspot_company_id)
                                    # hubspot_instance.modifiedDateForCompany = newmodifiedDateForCompany
                                    self.env.cr.commit()
                                    return hubspot_company_id
                            else:
                                if self.env.context.get('from_skipped_companies'):
                                    vals.update({'hubspot_instance_id': hubspot_instance.id})
                                    hubspot_company_id = self.with_context({'from_hubspot': True}).create(vals)
                                    logger.info("Created New Company Into Odoo3 ----------- " + str(hubspot_company_id.id))
                                    # hubspot_instance.modifiedDateForCompany = newmodifiedDateForCompany
                                    hubspot_company_id = vals['hubspot_id']
                                    contact_id = self.env['res.partner'].sudo().search(
                                            [('type', '=', 'contact'), ('hubspot_id', '=', hubspot_company_id), ('hubspot_instance_id', '=', hubspot_instance.id)],limit=1)
                                    
                                    results =''
                                    if line.hubspot_image_data:
                                        results = json.loads(line.hubspot_image_data)
                                
                                    if results:
                                        
                                        
                                        model_id = self.env['ir.model']._get('res.partner').id
                                        model_name = 'res.partner'
                                        
                                        for result in results:
                                            if result:
                                                create_attachment = self.create_attachment(result, contact_id, model_name)
                                                if create_attachment:
                                                    logger.info("Attachment created successfully: %s" % create_attachment.id)
                                                else:
                                                    logger.warning("Failed to create attachment for: %s" % result['name'])
                                    
                                    else:
                                        logger.warning("No attachments found in the response for hubspot_company_id: %s", hubspot_company_id)
                                    self.env.cr.commit()
                                    return hubspot_company_id
                                elif not self.env.context.get('from_skipped_companies'):
                                        vals.update({'hubspot_instance_id': hubspot_instance.id})
                                        hubspot_company_id = self.with_context({'from_hubspot': True}).create(vals)
                                        logger.info("Created New Company Into Odoo4 ----------- " + str(hubspot_company_id.id))
                                        line.state = 'done'
                                        # hubspot_instance.modifiedDateForCompany = newmodifiedDateForCompany
                                        hubspot_company_id = vals['hubspot_id']
                                        contact_id = self.env['res.partner'].sudo().search(
                                            [('type', '=', 'contact'), ('hubspot_id', '=', hubspot_company_id), ('hubspot_instance_id', '=', hubspot_instance.id)],limit=1)
                                    
                                        results =''
                                        if line.hubspot_image_data:
                                            results = json.loads(line.hubspot_image_data)
                                    
                                        if results:
                                            
                                            
                                            model_id = self.env['ir.model']._get('res.partner').id
                                            model_name = 'res.partner'
                                            
                                            for result in results:
                                                if result:
                                                    create_attachment = self.create_attachment(result, contact_id, model_name)
                                                    if create_attachment:
                                                        logger.info("Attachment created successfully: %s" % create_attachment.id)
                                                    else:
                                                        logger.warning("Failed to create attachment for: %s" % result['name'])
                                        
                                        else:
                                            logger.warning("No attachments found in the response for hubspot_company_id: %s", hubspot_company_id)
                                        self.env.cr.commit()
                                        return hubspot_company_id
                        else:
                            logger.info("All companies already imported")
                            line.state = 'done'




    @api.model
    def createNewCompaniesInOdoo(self, changedCompanies, hubspot_instance):
        try:
            for eachCompany in changedCompanies:
                vals = {}
                newmodifiedDateForCompany = 10000000.0
                if eachCompany.get('properties'):
                    if eachCompany.get('properties').get('hs_lastmodifieddate'):
                        if eachCompany.get('properties'):
                            newmodifiedDateForCompany = int(eachCompany.get('properties').get('hs_lastmodifieddate').get('value'))
                    # if 'name' in eachCompany['properties']:
                    #     if 'value' in eachCompany['properties']['name']:
                    #         if eachCompany['companyId']:
                    #             vals.update({'hubspot_id': eachCompany['companyId']})
                    #         if 'name' in eachCompany['properties']:
                    #             if len(eachCompany['properties']['name']['value']) > 0:
                    #                 vals.update({'name': eachCompany['properties']['name']['value']})
                    #             else:
                    #                 vals.update({'name': 'Unknown'})
                            if 'zip' in eachCompany['properties']:
                                vals.update({'zip': eachCompany['properties']['zip']['value']})

                            if 'city' in eachCompany['properties']:
                                vals.update({'city': eachCompany['properties']['city']['value']})

                            if 'website' in eachCompany['properties']:
                                vals.update({'website': eachCompany['properties']['website']['value']})

                            if 'address' in eachCompany['properties']:
                                vals.update({'street': eachCompany['properties']['address']['value']})
                            if 'address2' in eachCompany['properties']:
                                vals.update({'street2': eachCompany['properties']['address2']['value']})
                            if 'phone' in eachCompany['properties']:
                                vals.update({'phone': eachCompany['properties']['phone']['value']})
                            country_id = None
                           
                            if 'country' in eachCompany['properties'] and eachCompany['properties']['country']['value']:
                                if eachCompany['properties']['country']['value'] in ['usa', 'USA', 'United States of America', 'united states of america', 'united states',
                                                                                     'United States']:
                                    country = self.env['res.country'].search([('code', '=', 'US')], limit=1)
                                else:
                                    country = self.env['res.country'].search(['|', ('code', '=', eachCompany['properties']['country']['value']),
                                                                              ('name', '=', eachCompany['properties']['country']['value'])], limit=1)

                                if len(country):
                                    country_id = country.id
                                    vals['country_id'] = country_id
                            
                                    
                            if 'state' in eachCompany['properties']:
                                if eachCompany['properties']['state']['value']:
                                    if country_id:
                                        state_id = self.env['res.country.state'].search(
                                            ['|', ('name', '=', eachCompany['properties']['state']['value']),
                                             ('code', '=', eachCompany['properties']['state']['value']),
                                             ('country_id', '=', country_id)], limit=1)

                                    else:
                                        state_id = self.env['res.country.state'].search(
                                            ['|', ('name', '=', eachCompany['properties']['state']['value']),
                                             ('code', '=', eachCompany['properties']['state']['value'])], limit=1)

                                    if state_id:
                                        vals['state_id'] = state_id.id
                           
                            for each_identity in eachCompany['properties']:
                                # if eachCompany['properties'][each_identity].has_key('zip'):
                                if 'zip' in eachCompany['properties'][each_identity]:
                                    vals.update({'zip': each_identity['value']})
                                # if eachCompany['properties'][each_identity].has_key('city'):
                                if 'city' in eachCompany['properties'][each_identity]:
                                    vals.update({'city': each_identity['value']})
                                # Sync Owner
                                if 'hubspot_owner_id' in eachCompany['properties']:
                                    owner_id = eachCompany['properties']['hubspot_owner_id']['value']
                                    if owner_id:
                                        res_user_id = self.env['res.partner'].search(
                                            ['|', ('active', '=', True), ('active', '=', False), ('hubspot_id', '=', owner_id), ('hubspot_instance_id', '=', hubspot_instance.id)],
                                            limit=1)
                                        if res_user_id:
                                            vals.update({'hubspot_id': res_user_id.id})
                                        else:
                                            get_user = self.env['res.partner'].getOwnerDetailsFromHubspot(owner_id, hubspot_instance)
                                            if get_user:
                                                vals.update({'hubspot_id': get_user.id})
                                if 'name' in eachCompany['properties']:
                                    if 'value' in eachCompany['properties']['name']:
                                        if eachCompany['companyId']:
                                            vals.update({'hubspot_id': eachCompany['companyId']})
                                        if 'name' in eachCompany['properties']:
                                            if len(eachCompany['properties']['name']['value']) > 0:
                                                vals.update({'name': eachCompany['properties']['name']['value']})
                                            else:
                                                vals.update({'name': 'Unknown'})
                            if len(vals) > 0:
                                company_id = self.search(['|', ('active', '=', True), ('active', '=', False), ('hubspot_id', '=', str(eachCompany['companyId'])),
                                                          ('hubspot_instance_id', '=', hubspot_instance.id)],limit=1)
                               
                                if not company_id:
                                    
                                        vals.update({'is_company': True})
                                        if 'website' in vals:
                                            

                                                
                                            
                                            if self.env.context.get('from_skipped_companies'):
                                                vals.update({'hubspot_instance_id': hubspot_instance.id})
                                                hubspot_company_id = self.with_context({'from_hubspot': True}).create(vals)
                                                logger.info("Created New Company Into Odoo1 ----------- " + str(hubspot_company_id.id))
                                                hubspot_company_id = vals['hubspot_id']


                                                try:
                                                        
                                                    response_get_associated_company_attachment_detail = hubspot_instance._send_get_request(
                                                        f'/engagements/v1/engagements/associated/company/{hubspot_company_id}/paged')
                                                    
                                                    
                                                    
                                                    
                                                    json_response_get_associated_company_attachment_detail = json.loads(response_get_associated_company_attachment_detail)
                                                    contact_id = self.env['res.partner'].sudo().search(
                                                            [('type', '=', 'contact'), ('hubspot_id', '=', hubspot_company_id), ('hubspot_instance_id', '=', hubspot_instance.id)])
                                                    
                                                    results = json_response_get_associated_company_attachment_detail.get('results', [])
                                                
                                                    if results:
                                                        
                                                        
                                                        model_id = self.env['ir.model']._get('res.partner').id
                                                        model_name = 'res.partner'
                                                        
                                                        for result in results:
                                                            attachments = result.get('attachments', [])
                                                            for attachment in attachments:
                                                                attachment_id = attachment.get('id')
                                                                if attachment_id:
                                                                    attachment_details = self.get_attachment_by_id(attachment_id, hubspot_instance)
                                                                    if attachment_details:
                                                                        create_attachment = self.create_attachment(attachment_details, contact_id, model_name)
                                                                        if create_attachment:
                                                                            logger.info("Attachment created successfully: %s" % create_attachment.id)
                                                                        else:
                                                                            logger.warning("Failed to create attachment for: %s" % attachment_details['name'])
                                                  
                                                    else:
                                                        logger.warning("No attachments found in the response for hubspot_company_id: %s", hubspot_company_id)
                                                    
                                                   
                                                   
                                                    # hubspot_instance.modifiedDateForCompany = newmodifiedDateForCompany
                                                
                                                except json.JSONDecodeError:
                                                    logger.error("Failed to parse JSON response for hubspot_company_id: %s", hubspot_company_id)
                                                except Exception as e:
                                                    logger.error("An unexpected error occurred: %s", str(e))
                                                # hubspot_instance.modifiedDateForCompany = newmodifiedDateForCompany
                                                self.env.cr.commit()
                                                return hubspot_company_id
                                            elif not self.env.context.get('from_skipped_companies'):
                                                vals.update({'hubspot_instance_id': hubspot_instance.id})
                                                hubspot_company_id = self.with_context({'from_hubspot': True}).create(vals)
                                                logger.info("Created New Company Into Odoo2 -----------created new " + str(hubspot_company_id.id))
                                                hubspot_company_id = vals['hubspot_id']
                                                
                                                try:
                                                    response_get_associated_company_attachment_detail = hubspot_instance._send_get_request(
                                                        f'/engagements/v1/engagements/associated/company/{hubspot_company_id}/paged')
                                                    
                                                    
                                                    
                                                    json_response_get_associated_company_attachment_detail = json.loads(response_get_associated_company_attachment_detail)
                                                    
                                                    
                                                    results = json_response_get_associated_company_attachment_detail.get('results', [])
                                                    contact_id = self.env['res.partner'].sudo().search(
                                                            [('type', '=', 'contact'), ('hubspot_id', '=', hubspot_company_id), ('hubspot_instance_id', '=', hubspot_instance.id)])
                                                
                                                    if results:
                                                        
                                                        
                                                        model_id = self.env['ir.model']._get('res.partner').id
                                                        model_name = 'res.partner'
                                                        
                                                        for result in results:
                                                            attachments = result.get('attachments', [])
                                                            for attachment in attachments:
                                                                attachment_id = attachment.get('id')
                                                                if attachment_id:
                                                                    attachment_details = self.get_attachment_by_id(attachment_id, hubspot_instance)
                                                                    if attachment_details:
                                                                        create_attachment = self.create_attachment(attachment_details, contact_id, model_name)
                                                                        if create_attachment:
                                                                            logger.info("Attachment created successfully: %s" % create_attachment.id)
                                                                        else:
                                                                            logger.warning("Failed to create attachment for: %s" % attachment_details['name'])
                                                    else:
                                                        logger.warning("No attachments found in the response for hubspot_company_id: %s", hubspot_company_id)
                                                    
                                                    # hubspot_instance.modifiedDateForCompany = newmodifiedDateForCompany
                                                
                                                except json.JSONDecodeError:
                                                    logger.error("Failed to parse JSON response for hubspot_company_id: %s", hubspot_company_id)
                                                except Exception as e:
                                                    logger.error("An unexpected error occurred: %s", str(e))
                                                # hubspot_instance.modifiedDateForCompany = newmodifiedDateForCompany
                                                self.env.cr.commit()
                                                return hubspot_company_id
                                        else:
                                            if self.env.context.get('from_skipped_companies'):
                                                vals.update({'hubspot_instance_id': hubspot_instance.id})
                                                hubspot_company_id = self.with_context({'from_hubspot': True}).create(vals)
                                                logger.info("Created New Company Into Odoo3 ----------- " + str(hubspot_company_id.id))
                                                # hubspot_instance.modifiedDateForCompany = newmodifiedDateForCompany
                                                hubspot_company_id = vals['hubspot_id']
                                                try:
                                                    response_get_associated_company_attachment_detail = hubspot_instance._send_get_request(
                                                        f'/engagements/v1/engagements/associated/company/{hubspot_company_id}/paged')
                                                    
                                                    
                                                    
                                                    
                                                    json_response_get_associated_company_attachment_detail = json.loads(response_get_associated_company_attachment_detail)
                                                    
                                                    
                                                    results = json_response_get_associated_company_attachment_detail.get('results', [])
                                                    contact_id = self.env['res.partner'].sudo().search(
                                                            [('type', '=', 'contact'), ('hubspot_id', '=', hubspot_company_id), ('hubspot_instance_id', '=', hubspot_instance.id)])
                                                        
                                                
                                                    if results:
                                                       
                                                        model_id = self.env['ir.model']._get('res.partner').id
                                                        model_name = 'res.partner'
                                                        
                                                        for result in results:
                                                            attachments = result.get('attachments', [])
                                                            for attachment in attachments:
                                                                attachment_id = attachment.get('id')
                                                                if attachment_id:
                                                                    attachment_details = self.get_attachment_by_id(attachment_id, hubspot_instance)
                                                                    if attachment_details:
                                                                        create_attachment = self.create_attachment(attachment_details, contact_id, model_name)
                                                                        if create_attachment:
                                                                            logger.info("Attachment created successfully: %s" % create_attachment.id)
                                                                        else:
                                                                            logger.warning("Failed to create attachment for: %s" % attachment_details['name'])
                                                    else:
                                                        logger.warning("No attachments found in the response for hubspot_company_id: %s", hubspot_company_id)
                                                    
                                                    # hubspot_instance.modifiedDateForCompany = newmodifiedDateForCompany
                                                
                                                
                                                except json.JSONDecodeError:
                                                    logger.error("Failed to parse JSON response for hubspot_company_id: %s", hubspot_company_id)
                                                except Exception as e:
                                                    logger.error("An unexpected error occurred: %s", str(e))
                                                self.env.cr.commit()
                                                return hubspot_company_id
                                            elif not self.env.context.get('from_skipped_companies'):
                                                    vals.update({'hubspot_instance_id': hubspot_instance.id})
                                                    hubspot_company_id = self.with_context({'from_hubspot': True}).create(vals)
                                                    logger.info("Created New Company Into Odoo4 ----------- " + str(hubspot_company_id.id))
                                                    # hubspot_instance.modifiedDateForCompany = newmodifiedDateForCompany
                                                    hubspot_company_id = vals['hubspot_id']
                                                    try:
                                                        response_get_associated_company_attachment_detail = hubspot_instance._send_get_request(
                                                            f'/engagements/v1/engagements/associated/company/{hubspot_company_id}/paged')
                                                        
                                                                                                        
                                                        json_response_get_associated_company_attachment_detail = json.loads(response_get_associated_company_attachment_detail)
                                                        
                                                        
                                                        results = json_response_get_associated_company_attachment_detail.get('results', [])
                                                        contact_id = self.env['res.partner'].sudo().search(
                                                                [('type', '=', 'contact'), ('hubspot_id', '=', hubspot_company_id), ('hubspot_instance_id', '=', hubspot_instance.id)])
                                                    
                                                        if results:
                                                            
                                                            
                                                            model_id = self.env['ir.model']._get('res.partner').id
                                                            model_name = 'res.partner'
                                                            
                                                            for result in results:
                                                                attachments = result.get('attachments', [])
                                                                for attachment in attachments:
                                                                    attachment_id = attachment.get('id')
                                                                    if attachment_id:
                                                                        attachment_details = self.get_attachment_by_id(attachment_id, hubspot_instance)
                                                                        if attachment_details:
                                                                            create_attachment = self.create_attachment(attachment_details, contact_id, model_name)
                                                                            if create_attachment:
                                                                                logger.info("Attachment created successfully: %s" % create_attachment.id)
                                                                            else:
                                                                                logger.warning("Failed to create attachment for: %s" % attachment_details['name'])
                                                        else:
                                                            logger.warning("No attachments found in the response for hubspot_company_id: %s", hubspot_company_id)
                                                        
                                                        # hubspot_instance.modifiedDateForCompany = newmodifiedDateForCompany
                                                        
                                                
                                                    except json.JSONDecodeError:
                                                        logger.error("Failed to parse JSON response for hubspot_company_id: %s", hubspot_company_id)
                                                    except Exception as e:
                                                        logger.error("An unexpected error occurred: %s", str(e))
                                                    self.env.cr.commit()
                                                    return hubspot_company_id
                            else:
                                logger.info("All companies already imported")
        except Exception as e:
            error_message = 'Error while creating hubspot companies in odoo %s\n Hubspot response %s' % (
                changedCompanies, str(e))
            self.env['hubspot.logger'].create_log_message('Import Companies', error_message)
            logger.exception("Exception in Creating New Company in Odoo : " + str(e))
            hubspot_instance._raise_user_error(e)
        logger.info('Companies imported successfully in Odoo')

    @api.model
    def _cron_update_companies_from_hubspot(self):
        hubspot_instance_obj = self.env['hubspot.instance'].search([('active', '=', True), ('hubspot_is_import_company', '=', True)])
        for hubspot_instance in hubspot_instance_obj:
            self.update_existing_companies_from_hubspot(hubspot_instance)
    
    

    @api.model
    def update_existing_companies_from_hubspot(self, hubspot_instance):

        if hubspot_instance.active  and hubspot_instance.hubspot_is_import_company:
            modifiedDateForCompany = hubspot_instance.modifiedDateForCompany or ''
            logger.info('Getting modified Companies from hubspot-------------------2')
            try:
                changedCompanies = []
                hasMore = True
                offset = 0
                first = False
                oldData = False
                newcompanyModifiedDate = modifiedDateForCompany
                limit = 0
                record_limit = 90

                while hasMore:
                    response_get_recently_modified_companies = hubspot_instance._send_get_request(
                        '/companies/v2/companies/recent/modified?vidOffset=' + str(offset) + '&count=' + str(record_limit))
                    json_response_get_recently_modified_companies = json.loads(response_get_recently_modified_companies)
                    record_limit += 1
                    hasMore = json_response_get_recently_modified_companies['hasMore']
                    offset = json_response_get_recently_modified_companies['offset']
                    hubspot_modifiedDateForCompany = ''
                    # Correct the following line to convert offset to a string
                    # response_get_recently_modified_companies_total = hubspot_instance._send_get_request(
                    #     '/companies/v2/companies/recent/modified?count=' + str(record_limit) +
                    #     '&offset=' + str(json_response_get_recently_modified_companies['offset']))  # Convert offset to string
                    # json_response_get_recently_modified_companies_new = json.loads(response_get_recently_modified_companies_total)

                    for eachContact in json_response_get_recently_modified_companies['results']:
                        if (eachContact['properties']['hs_lastmodifieddate']['value']) <= modifiedDateForCompany:
                            break  # Skip Not recently updated contact
                        else:
                            changedCompanies.append(eachContact['companyId'])

                    changedCompanies.reverse()
                    if changedCompanies and hubspot_instance.active and hubspot_instance.hubspot_is_import_company:
                        self.updated_company_details_and_create(changedCompanies, hubspot_instance)
                        hubspot_instance.modifiedDateForCompany = hubspot_modifiedDateForCompany

                    hubspot_instance.modifiedDateForCompany = newcompanyModifiedDate

                msg = 'Completed Getting All Companies from hubspot'
                self.env['hubspot.logger'].create_log_message('Import Companies', msg)
                logger.info('Completed Getting modified companies from hubspot------------------------------------------------------')

            except Exception as e:
                error_message = 'Error while getting companies in odoo \nHubspot response %s' % (str(e))
                self.env['hubspot.logger'].create_log_message('Import Companies', error_message)
                logger.exception("Error in getting companies------------>\n" + error_message)
                hubspot_instance._raise_user_error(e)


   

    @api.model
    def createNewCompaniesInOdooFieldMapping(self, changedCompanies, company_field_mapping, hubspot_instance):
        logger.info('Create new custom field mapping companies in odoo')
        try:
            newmodifiedDateForCompany = 10000000.0
            for eachCompany in changedCompanies:
                vals = {}
                if 'properties' in eachCompany:
                    if 'hs_lastmodifieddate' in eachCompany['properties']:
                        newmodifiedDateForCompany = int(eachCompany['properties']['hs_lastmodifieddate']['value'])
                    
                    for mapping in company_field_mapping:
                        field_name = mapping.hubspot_fields.technical_name
                        if field_name in eachCompany['properties']:
                            field_value = eachCompany['properties'][field_name]
                            if mapping.hubspot_fields.field_type == 'date':
                                # Convert timestamp to GMT timestamp
                                vals[mapping.odoo_fields.name] = self.env['mail.activity'].convert_epoch_to_gmt_timestamp(field_value['timestamp'])
                            else:
                                vals[mapping.odoo_fields.name] = field_value['value']

                # Create or update the company in Odoo
                if vals:
                    company_id = self.search([
                        '|', ('active', '=', True), ('active', '=', False),
                        ('hubspot_id', '=', str(eachCompany['companyId'])),
                        ('hubspot_instance_id', '=', hubspot_instance.id)
                    ])
                    if company_id:
                        try:
                            company_id.with_context(from_hubspot=True).write(vals)
                            self.env.cr.commit()
                        except Exception as update_exception:
                            error_message = f'Error updating company {eachCompany["companyId"]} in Odoo: {str(update_exception)}'
                            self.env['hubspot.logger'].create_log_message('Import Companies', error_message)
                            logger.warning(error_message)
                    else:
                        try:
                            new_company = self.with_context(from_hubspot=True).create(vals)
                            vals.update({'hubspot_instance_id': hubspot_instance.id})
                            hubspot_instance.modifiedDateForCompany = newmodifiedDateForCompany
                            self.env.cr.commit()
                            return new_company
                        except Exception as create_exception:
                            error_message = f'Error creating company {eachCompany["companyId"]} in Odoo: {str(create_exception)}'
                            self.env['hubspot.logger'].create_log_message('Import Companies', error_message)
                            logger.warning(error_message)
        
        except Exception as e:
            error_message = f'Error while creating hubspot companies from custom field mapping in odoo: {str(e)}'
            self.env['hubspot.logger'].create_log_message('Import Companies', error_message)
            logger.exception("Exception in Creating New Company from custom field mapping in Odoo: " + str(e))
            hubspot_instance._raise_user_error(e)
        
        logger.info('Companies imported successfully in Odoo from custom field mapping')

    





    @api.model
    def _cron_export_companies_to_hubspot(self):
        hubspot_instance_obj = self.env['hubspot.instance'].search([('active', '=', True), ('hubspot_is_export_company', '=', True)])
        for hubspot_instance in hubspot_instance_obj:
            self.export_companies_to_hubspot(hubspot_instance)

    @api.model
    def export_companies_to_hubspot(self, hubspot_instance):
        """This function is called from cron to export accounts to hubspot"""
        # Hubspot Information
        srch_partner_ids = self.env['res.partner'].search([('hubspot_id', '=', False), ('type', '=', 'contact'),
                                                           ('active', '=', True), ('is_company', '=', True)])
        # Export Companies
        if hubspot_instance.default_instance and hubspot_instance.active and hubspot_instance.hubspot_is_export_company:
            for partner in srch_partner_ids:
                if not partner.hubspot_id and partner.is_company:
                    partner.createNewCompanyInHubspot(hubspot_instance)
                    company_field_mapping = self.env['company.field.mapping'].search([('hubspot_instance_id', '=', hubspot_instance.id)])
                    if len(company_field_mapping):
                        partner.createNewCompanyInHubspotFieldMapping(hubspot_instance, company_field_mapping)

    def createNewCompanyInHubspot(self, hubspot_instance):
        logger.info('Creating new companies in hubspot')
        properties = []
        for eachCompany in self:
            if eachCompany.is_company:
                if eachCompany.name:
                    properties.append({'name': 'name', 'value': eachCompany.name})
                if eachCompany.phone:
                    properties.append({'name': 'phone', 'value': eachCompany.phone})
                if eachCompany.website:
                    properties.append({'name': 'website', 'value': eachCompany.website})
                if eachCompany.street:
                    properties.append({'name': 'address', 'value': eachCompany.street})
                if eachCompany.city:
                    properties.append({'name': 'city', 'value': eachCompany.city})
                if eachCompany.state_id:
                    properties.append({'name': 'state', 'value': eachCompany.state_id.name})
                if eachCompany.country_id:
                    properties.append({'name': 'country', 'value': eachCompany.country_id.name})
                if eachCompany.zip:
                    properties.append({'name': 'zip', 'value': eachCompany.zip})
                if eachCompany.email and len(eachCompany.email.split('@')) > 1:
                    properties.append({'name': 'domain', 'value': eachCompany.email.split('@')[1]})

                # Sync owner
                if eachCompany.user_id:
                    if not eachCompany.user_id.hubspot_uid:
                        logger.warning("Odoo User Not Available In Hubspot")
                        eachCompany.env['res.partner'].syncAllUsers(eachCompany.hubspot_instance_id)
                    if eachCompany.user_id.hubspot_uid:
                        properties.append({'name': 'hubspot_owner_id', 'value': eachCompany.user_id.hubspot_uid})
                else:
                    properties.append({'name': 'hubspot_owner_id', 'value': ''})

            # Create new hubspot Account(company)
            if len(properties) > 0:
                try:
                    response_create_company = hubspot_instance._send_post_request('/companies/v2/companies/', {'properties': properties})
                    json_response_create_company = json.loads(response_create_company)
                    eachCompany.with_context({'from_hubspot': True}).hubspot_id = json_response_create_company['companyId']
                    eachCompany.hubspot_instance_id = hubspot_instance.id
                except Exception as e:
                    error_message = 'Error while creating new company %d in hubspot \n\n Odoo vals: %s\n Hubspot response %s' % (
                        eachCompany.id, str(properties), str(e))

                    self.env['hubspot.logger'].create_log_message('Export Companies', str(error_message))
                    logger.exception("Exception in Creating New Company in hubspot :\n" + str(e))
                    hubspot_instance._raise_user_error(e)
        message = 'Company Export Completed'
        self.env['hubspot.logger'].create_log_message('Export Companies', str(message))
        logger.info('Company Export Completed...')

    def createNewCompanyInHubspotFieldMapping(self, hubspot_instance, company_field_mapping):
        properties = []
        odoo_field_list = []
        partner_list = []
        for company_field_mapping_id in company_field_mapping:
            if company_field_mapping_id.odoo_fields.name and company_field_mapping_id.hubspot_fields.technical_name:
                odoo_field_list.append(company_field_mapping_id.odoo_fields.name)
                partner_read_obj = self.read()[0]
                if self.is_company:
                    partner_dict = {}
                    # for odoo_field in odoo_field_list:
                    if company_field_mapping_id.odoo_fields.name in partner_read_obj.keys():
                        if partner_read_obj.values():
                            if partner_read_obj.get(company_field_mapping_id.odoo_fields.name):
                                if company_field_mapping_id.hubspot_fields.field_type == 'date':
                                    format_date = convert_time_to_unix_timestamp(partner_read_obj.get(company_field_mapping_id.odoo_fields.name))

                                    properties.append({'name': company_field_mapping_id.hubspot_fields.technical_name,
                                                       'value': format_date})
                                else:
                                    properties.append({'name': company_field_mapping_id.hubspot_fields.technical_name,
                                                       'value': str(partner_read_obj.get(company_field_mapping_id.odoo_fields.name))})
        if len(properties) > 0:
            try:
                if self.hubspot_id and self.hubspot_instance_id:
                    response_update_companies = hubspot_instance._send_put_request('/companies/v2/companies/' + str(self.hubspot_id), ({'properties': properties}))
                    json_response_update_companies = json.loads(response_update_companies)
                else:
                    response_update_companies = hubspot_instance._send_post_request('/companies/v2/companies/', ({'properties': properties}))
                    json_response_update_companies = json.loads(response_update_companies)
                    self.with_context(from_hubspot=True).hubspot_id = json_response_update_companies['companyId']
                    self.with_context(from_hubspot=True).hubspot_instance_id = hubspot_instance.id
            except Exception as e:
                error_message = 'Error while creating new company %d in hubspot for custom field mapping \n\n Odoo vals: %s\n Hubspot response %s' % (
                    self.id, str(properties), str(e))
                self.env['hubspot.logger'].create_log_message('Export Companies', str(error_message))
                logger.exception("Exception in Creating New Company in hubspot for custom field mapping:\n" + str(e))
                hubspot_instance._raise_user_error(e)

        message = 'Field Mapping Company Export Completed'
        self.env['hubspot.logger'].create_log_message('Export Companies', str(message))
        logger.info('Field Mapping Company Export Completed...')

    def UpdateContactsInHubspot(self, hubspot_instance):
        logger.info('Updating contacts in hubspot')
        count = 0
        properties = []
        for eachContact in self:
            count += 1
            if eachContact.email:
                properties.append({'property': 'email', 'value': eachContact.email})
            if len(eachContact.name):
                properties.append({'property': 'firstname', 'value': (eachContact.name).split(' ')[0]})
                if len(eachContact.name.split(' ')) > 1:
                    properties.append({'property': 'lastname', 'value': (eachContact.name).split(' ')[-1]})

            if eachContact.street or eachContact.street2:
                address = ''
                if eachContact.street:
                    address += eachContact.street
                elif eachContact.street2:
                    address += eachContact.street2
                properties.append({'property': 'address', 'value': address})
            if eachContact.zip:
                properties.append({'property': 'zip', 'value': eachContact.zip})
            if eachContact.website:
                properties.append({'property': 'website', 'value': eachContact.website})
            if eachContact.phone:
                properties.append({'property': 'phone', 'value': eachContact.phone})
            #                     if eachContact.fax:
            #                         properties.append({'property': 'fax', 'value': eachContact.fax})
            # if eachContact.title:
            #     properties.append({'property': 'salutation', 'value': eachContact.title.name})
            if eachContact.parent_id:
                properties.append({'property': 'company', 'value': eachContact.parent_id.name})
            # if eachContact.mobile:
            #     properties.append({'property': 'mobilephone', 'value': eachContact.mobile})
            if eachContact.function:
                properties.append({'property': 'jobtitle', 'value': eachContact.function})
            if eachContact.city:
                properties.append({'property': 'city', 'value': eachContact.city})
            if eachContact.state_id:
                properties.append({'property': 'state', 'value': eachContact.state_id.name})
            if eachContact.country_id:
                properties.append({'property': 'country', 'value': eachContact.country_id.name})
            if eachContact.user_id:
                if not eachContact.user_id.hubspot_uid:
                    logger.warning("Odoo User Not Available In Hubspot")
                    eachContact.env['res.partner'].syncAllUsers(eachContact.hubspot_instance_id)
                if eachContact.user_id.hubspot_uid:
                    properties.append(
                        {'property': 'hubspot_owner_id', 'value': eachContact.user_id.hubspot_uid})
            else:
                properties.append({'property': 'hubspot_owner_id', 'value': ''})
            if eachContact.parent_id:

                if eachContact.parent_id.hubspot_id:
                    properties.append(
                        {'property': 'associatedcompanyid', 'value': eachContact.parent_id.hubspot_id})
            else:
                properties.append({'property': 'associatedcompanyid', 'value': ''})
            if len(properties) > 0:
                try:
                    hubspot_instance._send_post_request('/contacts/v1/contact/vid/' + str(eachContact.hubspot_id) + '/profile', ({'properties': properties}))
                    eachContact.with_context({'from_hubspot': True})
                    logger.info('Completed updating contacts in hubspot')

                except Exception as e_log:
                    error_message = 'Error while updating contacts from odoo id %d \n\n Odoo vals: %s\n Hubspot response %s' % (
                        eachContact.id, str(properties), str(e_log))
                    self.env['hubspot.logger'].create_log_message('Export Contacts', error_message)
                    logger.exception("Exception in updating contacts :\n" + str(e_log))
                    hubspot_instance._raise_user_error(e_log)

    def UpdateCompaniesInHubspot(self, hubspot_instance):
        logger.info('Updating companies in hubspot')
        for eachCompany in self:
            if eachCompany.is_company:
                properties = []
                if eachCompany.name:
                    properties.append({'name': 'name', 'value': eachCompany.name})
                if eachCompany.phone:
                    properties.append({'name': 'phone', 'value': eachCompany.phone})
                if eachCompany.website:
                    properties.append({'name': 'website', 'value': eachCompany.website})
                if eachCompany.street:
                    properties.append({'name': 'address', 'value': eachCompany.street})
                if eachCompany.city:
                    properties.append({'name': 'city', 'value': eachCompany.city})
                if eachCompany.state_id:
                    properties.append({'name': 'state', 'value': eachCompany.state_id.name})
                if eachCompany.country_id:
                    properties.append({'name': 'country', 'value': eachCompany.country_id.name})
                if eachCompany.zip:
                    properties.append({'name': 'zip', 'value': eachCompany.zip})
                if eachCompany.email and len(eachCompany.email.split('@')) > 1:
                    properties.append({'name': 'domain', 'value': eachCompany.email.split('@')[1]})
                    # create new hubspot contact
            if len(properties) > 0:
                try:
                    hubspot_instance._send_put_request('/companies/v2/companies/' + eachCompany.hubspot_id, {'properties': properties})
                except Exception as e_log:
                    error_message = 'Error while updating companies from odoo id %d \n\n Odoo vals: %s\n Hubspot response %s' % (eachCompany.id, str(properties), str(e_log))
                    self.env['hubspot.logger'].create_log_message('Export Companies', error_message)
                    logger.exception("Exception in updating companies :\n" + str(e_log))
                    hubspot_instance._raise_user_error(e_log)

    def UpdateCompaniesInHubspotFieldMapping(self, company_field_mapping, hubspot_instance):
        logger.info('Updating companies in hubspot custom field mapping')
        for eachCompany in self:
            for company_field_mapping_id in company_field_mapping:
                properties = []

                if company_field_mapping_id.odoo_fields.name and company_field_mapping_id.hubspot_fields.technical_name:
                    partner_company_read_obj = self.read()[0]
                    if self.is_company:
                        if company_field_mapping_id.odoo_fields.name in partner_company_read_obj.keys():
                            if partner_company_read_obj.values():
                                if partner_company_read_obj.get(company_field_mapping_id.odoo_fields.name):
                                    if company_field_mapping_id.hubspot_fields.field_type == 'date':
                                        format_date = convert_time_to_unix_timestamp(partner_company_read_obj.get(company_field_mapping_id.odoo_fields.name))
                                        properties.append(
                                            {'name': company_field_mapping_id.hubspot_fields.technical_name,
                                             'value': format_date})
                                    else:
                                        properties.append(
                                            {'name': company_field_mapping_id.hubspot_fields.technical_name,
                                             'value': str(partner_company_read_obj.get(company_field_mapping_id.odoo_fields.name))})
            if len(properties) > 0:
                try:
                    hubspot_instance._send_put_request('/companies/v2/companies/' + str(eachCompany.hubspot_id), ({'properties': properties}))
                    logger.info('Completed Updating companies in hubspot with field mapping')
                except Exception as e_log:
                    error_message = 'Error while updating companies from odoo with field mapping id %d \n\n Odoo vals: %s\n Hubspot response %s' % (
                        eachCompany.id, str(properties), str(e_log))
                    self.env['hubspot.logger'].create_log_message('Export Companies',
                                                                  error_message)
                    logger.exception("Exception in updating companies with field mapping :\n" + str(e_log))
                    hubspot_instance._raise_user_error(e_log)

    def getCompaniesFromHubspot(self, hubspot_instance_id, hubspot_company_id):
        logger.info('Getting  companies from hubspot')
        newCompanies = []
        # global companyModifiedDate
        response_get_company_by_id = hubspot_instance_id._send_get_request('/companies/v2/companies/' + str(hubspot_company_id))
        json_response_get_company_by_id = json.loads(response_get_company_by_id)
        newCompanies.append(json_response_get_company_by_id)
        logger.info('Completed Getting modified Companies from hubspot')
        return newCompanies

    # def deleteFromHubspot(self, hubspot_instance_id):
    #     try:
    #         for each in self:
    #             if not each.is_company and hubspot_instance_id.hubspot_is_export_contacts:
    #                 logger.info('Delete from hubspot')
    #                 hubspot_instance_id._send_delete_request('/contacts/v1/contact/vid/' + str(each.hubspot_id))
    #             elif hubspot_instance_id.hubspot_is_export_company:
    #                 logger.info('Delete from hubspot')
    #                 hubspot_instance_id._send_delete_request('/companies/v2/companies/' + str(each.hubspot_id))
    #     except Exception as e:
    #         error_message = 'Error while deleting Contacts/Companies in hubspot \nHubspot response %s' % (str(e))
    #         self.env['hubspot.logger'].create_log_message('Delete Contacts/Company', error_message)
    #         logger.exception("Error in deleted Contacts/Companies From Hubspot------------>\n" + str(e))
    #         hubspot_instance_id._raise_user_error(e)
    #     logger.info('Completed Delete from hubspot')


    ############creating hubspot owner to respartner#########


    # def _cron_syncAllUsers(self):
    #     hubspot_instance_obj = self.env['hubspot.instance'].search([('active', '=', True)])
    #     for hubspot_instance in hubspot_instance_obj:
    #         self.syncAllUsers(hubspot_instance)

    def syncAllUsers(self, hubspot_instance):
        try:
            
            logger.info('Getting All Users from hubspot')
            allUsers = self.search(['|', ('active', '=', True), ('active', '=', False), ('hubspot_id', '!=', False),('hubspot_instance_id', '=', hubspot_instance.id), ('id', 'not in', [3, 1, 5, 4])])
            Userids = allUsers.read(['hubspot_id'])
            UserHubspotIds = [each['hubspot_id'] for each in Userids]
            response_get_all_users = hubspot_instance._send_get_request('/crm/v3/owners/')
            json_response_all_contacts = json.loads(response_get_all_users)

            logger.info("Owner response logger9 %s: " % json_response_all_contacts)
            for owner in json_response_all_contacts:
                try:
                    owner_id = str(owner.get('id'))
                    user_dict = {'hubspot_id': owner_id}
                    if owner.get('email'):
                        # user_dict.update({'login': owner.get('email')})
                        user_dict.update({'email': owner.get('email')})
                        
                    user_name = ''
                    if owner.get('firstName'):
                        user_name += owner.get('firstName') + ' '
                        
                        logger.info("user_name===== first name>>>>{}".format(user_name))
                        # user_dict.update({'name': owner.get('firstName')})
                    if owner.get('lastName'):
                        user_name += owner.get('lastName')
                        
                        # user_dict.update({'name': owner.get('lastName')})
                    user_dict['name'] = user_name
                    
                    if not owner.get('firstName') and not owner.get('lastName'):
                        user_dict.update({'name': owner.get('email')})
                        logger.info("user_dict1 update first name no last name===== >>>>{}".format(user_dict))
                    hubspot_modifiedDate = owner.get('updatedAt')
                    if owner_id in UserHubspotIds:
                        search_user = self.search(
                            ['|', ('active', '=', True), ('active', '=', False), ('hubspot_id', '=', owner_id), ('hubspot_instance_id', '=', hubspot_instance.id)], limit=1)
                        
                        odoo_modifiedDate = convert_time_to_unix_timestamp(search_user.write_date)
                        logger.info("Owner Is Available with hubspot id in odoo: " + str(search_user))
                        if int(hubspot_modifiedDate) > int(odoo_modifiedDate):
                            search_user.with_context({'from_hubspot': True}).write(user_dict)
                            search_user.write({'hubspot_instance_id':hubspot_instance.id})
                            
                            self.env.cr.commit()
                    else:
                        search_user = self.search(
                            ['|', ('active', '=', True), ('active', '=', False), ('email', '=', owner.get('email'))], limit=1)
                        
                        if search_user:
                            logger.info("Found owner with email in odoo: " + str(search_user))
                            search_user.with_context({'from_hubspot': True}).write(user_dict)
                            search_user.with_context({'from_hubspot': True}).write({'hubspot_instance_id':hubspot_instance.id})
                            self.env.cr.commit()
                        else:
                            email_exists = self.search(['|', ('active', '=', True), ('active', '=', False), ('hubspot_instance_id', '=', hubspot_instance.id),
                                                        ('hubspot_id', '=', owner.get('id'))], limit=1)
                            
                            if not email_exists and owner.get('email'):
                                user_id = self.with_context({'from_hubspot': True}).create(user_dict)
                                
                                user_id.write({'hubspot_instance_id': hubspot_instance.id})
                                logger.info("Owner created in odoo : {}".format(user_id))
                                self.env.cr.commit()
                            else:
                                logger.info("Before formatting email_id owner dict logger5 %s: " % str(owner))
                                email_id = owner.get('email') + str(random.randint(0, 999))
                                logger.info("email_id logger6 %s: " % str(email_id))
                                user_dict.update({'email': email_id})
                                logger.info("In if not email_exists exists logger7 %s: " % user_dict)
                                user_id = self.with_context({'from_hubspot': True}).create(user_dict)
                                user_id.write({'hubspot_instance_id': hubspot_instance.id})
                                logger.info("Owner created in odoo : {}".format(user_id))
                                self.env.cr.commit()
                except Exception as ex:
                    error_message = 'Error while sync users in odoo vals: %s\n Hubspot response %s' % (owner, str(ex))
                    self.env['hubspot.logger'].create_log_message('Import Users', error_message)
                    logger.exception("Exception in sync users in Odoo :\n" + error_message)
                    hubspot_instance._raise_user_error(ex)
                message = 'Done Syncing Users'
                self.env['hubspot.logger'].create_log_message('Import Users', message)
                logger.info('Done Syncing Users')
        except Exception as ex:
            error_message = 'Error while getting users in odoo \nHubspot response %s' % (str(ex))
            self.env['hubspot.logger'].create_log_message('Import Users', error_message)
            logger.exception("Error in getting users From Hubspot------------>\n" + error_message)
            hubspot_instance._raise_user_error(ex)


   

    def getOwnerDetailsFromHubspot(self, owner_id, hubspot_instance):
        '''
        Args:
            @param owner_id: hubspot owner id used to update or add in user
        Returns:
            @return: return user if availble with same email or create new one
        '''
        logger.info('Getting Owner Details from hubspot')
        # Hubspot Owner Information
        try:
            response_get_user_by_id = hubspot_instance._send_get_request('/crm/v3/owners/' + str(owner_id))
            if not response_get_user_by_id:
                warning_msg = f"Empty or None response for HubSpot owner ID {owner_id}. Skipping owner import."
                logger.warning(warning_msg)
                self.env['hubspot.logger'].create_log_message('Import Users', warning_msg)
                return False
            

            try:
                json_response_get_user_by_id = json.loads(response_get_user_by_id)
            except json.JSONDecodeError as e:
                warning_msg = f"Invalid JSON for HubSpot owner ID {owner_id}. Error: {str(e)}"
                logger.warning(warning_msg)
                self.env['hubspot.logger'].create_log_message('Import Users', warning_msg)
                return False
            
            # json_response_get_user_by_id = json.loads(response_get_user_by_id)
            res_user_id = self.createNewUserInOdoo(json_response_get_user_by_id, hubspot_instance)
            # self.syncAllUsers(hubspot_instance)
            # search_user = self.search(
            #     ['|', ('active', '=', True), ('active', '=', False), ('hubspot_id', '=', owner_id), ('hubspot_instance_id', '=', hubspot_instance.id)])
            message = 'Created/updated user as Contact in odoo'
            self.env['hubspot.logger'].create_log_message('Import Users', message)
            logger.info('Created/updated user in odoo')
            return res_user_id
        except Exception as ex:
            error_message = 'Error while importing hubspot users in odoo Id: %s\n Hubspot response %s' % (owner_id, str(ex))
            self.env['hubspot.logger'].create_log_message('Import Users', error_message)
            logger.exception("Could not get owner details from hubspot : %s " % ex)
            hubspot_instance._raise_user_error(ex)

        return False


    # def getOwnerDetailsFromHubspot(self, owner_id, hubspot_instance):
    #     '''
    #     Args:
    #         @param owner_id: hubspot owner id used to update or add in user
    #     Returns:
    #         @return: return user if available with same email or create new one
    #     '''
    #     logger.info(f"Getting Owner Details from HubSpot for ID {owner_id}")
    #     try:
            
    #         endpoint = f"/crm/v3/owners/{owner_id}?archived=true"
    #         response_get_user_by_id = hubspot_instance._send_get_request(endpoint)

    #         if not response_get_user_by_id or 'Not Found' in response_get_user_by_id:
    #             warning_msg = f"Owner ID {owner_id} not found or is deleted in HubSpot."
    #             logger.warning(warning_msg)
    #             self.env['hubspot.logger'].create_log_message('Import Users', warning_msg)
    #             return False

    #         try:
    #             json_response_get_user_by_id = json.loads(response_get_user_by_id)
    #         except json.JSONDecodeError as e:
    #             warning_msg = f"Invalid JSON for HubSpot owner ID {owner_id}. Error: {str(e)}"
    #             logger.warning(warning_msg)
    #             self.env['hubspot.logger'].create_log_message('Import Users', warning_msg)
    #             return False

    #         # Create or update the user in Odoo
    #         res_user_id = self.createNewUserInOdoo(json_response_get_user_by_id, hubspot_instance)

    #         message = f"Created/updated user from HubSpot owner ID {owner_id}"
    #         self.env['hubspot.logger'].create_log_message('Import Users', message)
    #         logger.info(message)
    #         return res_user_id

    #     except Exception as ex:
    #         error_message = f"Error while importing HubSpot owner ID {owner_id}\nHubSpot response: {str(ex)}"
    #         self.env['hubspot.logger'].create_log_message('Import Users', error_message)
    #         logger.exception("Could not get owner details from HubSpot: %s", ex)
    #         # hubspot_instance._raise_user_error(ex)
    #         return False

        

    def createNewUserInOdoo(self, hubspot_dict, hubspot_instance):
        try:
            user_dict = {'hubspot_id': hubspot_dict.get('id')}
            logger.info("user_dict new user>>>>{}".format(user_dict))
            if hubspot_dict.get('email'):
               
                user_dict.update({'email': hubspot_dict.get('email')})
                logger.info("user_dict=====update email>>>{}".format(user_dict))
            user_name = ''
            if hubspot_dict.get('firstName'):
                user_name += hubspot_dict.get('firstName') + ' '
                logger.info("user_name===== first name>>>>{}".format(user_name))
            if hubspot_dict.get('lastName'):
                user_name += hubspot_dict.get('lastName')
                logger.info("user_name===== last name>>>>{}".format(user_name))
            user_dict['name'] = user_name
           
            if not hubspot_dict.get('firstName') and not hubspot_dict.get('lastName'):
                user_dict.update({'name': hubspot_dict.get('email')})
                logger.info("user_name===== first name>>>>{}".format(user_dict))
            res_partner_id = self.search(['|', ('active', '=', True), ('active', '=', False), ('hubspot_id', '=', str(hubspot_dict.get('id'))), ('hubspot_instance_id', '=', hubspot_instance.id)], limit=1)
            logger.info("res_user_id===== e>>>>{}".format(res_partner_id))
            hubspot_modifiedDate = hubspot_dict.get('updatedAt')
            if res_partner_id:
                odoo_modifiedDate = convert_time_to_unix_timestamp(res_partner_id.write_date)
                logger.info("odoo modified date====>>>>{}".format(odoo_modifiedDate))
                if int(hubspot_modifiedDate) > int(odoo_modifiedDate):
                    res_partner_id.with_context({'from_hubspot': True}).write(user_dict)
                    logger.info("res_uuser_id=====write>>>>{}".format(res_partner_id))
                    return res_partner_id
            else:
                if 'login' in user_dict or 'email' in user_dict:
                    user_id = self.search(['|', ('active', '=', True), ('active', '=', False), ('email', '=', hubspot_dict.get('email')), ('hubspot_id', '=', False), ('hubspot_instance_id', '=', False)], limit=1)
                    logger.info("user_id=====>>>>{}".format(user_id))
                    if user_id:
                        user_id.with_context({'from_hubspot': True}).write(user_dict)
                        user_id.write({'hubspot_instance_id': hubspot_instance.id})
                        logger.info("user_name===== hubspot instance write>>>>{}".format(user_id))
                        return user_id
                    else:
                        res_user_email_exists = self.search(['|', ('active', '=', True), ('active', '=', False), ('email', '=', hubspot_dict.get('email')), ('hubspot_instance_id', '!=', hubspot_instance.id)], limit=1)
                        logger.info("resuser exists email>>>>{}".format(res_user_email_exists))
                        if res_user_email_exists:
                            email_id = hubspot_dict.get('email') + str(random.randint(0, 999))
                            logger.info("email_id logger6 %s: " % str(email_id))
                            user_dict.update({'email': email_id})
                            logger.info("In if not email_exists exists logger7 %s: " % user_dict)
                            user_id = self.with_context({'from_hubspot': True}).create(user_dict)
                            user_id.write({'hubspot_instance_id': hubspot_instance.id})
                            logger.info("Owner created in odoo : {}".format(user_id))
                            self.env.cr.commit()
                            return user_id
                        else:
                            user_id = self.with_context({'from_hubspot': True}).create(user_dict)
                            logger.info("user_id else>>>>{}".format(user_id))
                            user_id.with_context({'from_hubspot': True}).write({'hubspot_instance_id': hubspot_instance.id})
                            logger.info("user_id write===== hubspot instacne>>>>{}".format(user_id))
                            logger.info("Owner updated in odoo : {}".format(user_id))
                            self.env.cr.commit()
        except Exception as ex:
            error_message = 'Error while creating hubspot deals in odoo vals: %s\n Hubspot response %s' % (hubspot_dict, str(ex))
            self.env['hubspot.logger'].create_log_message('Import Users', error_message)
            logger.exception("Exception in Creating New Users in Odoo :\n" + error_message)
            hubspot_instance._raise_user_error(ex)
    
    
     #########################EXPORT CONTACT/COMPANY SERVER ACTION#############################

   
          
        
    def create_contactcompanies_in_hubspot(self):
        if self.is_company:
            if self.hubspot_id:
                
                raise UserError('Record Already Exported  !!company!!')   
            else:
                self.create_company_new()

                
        else:
            if self.hubspot_id:
                raise UserError('Record Already Exported !! contact !!')
            else:
                self.create_contact_new()
            

        
        
        
    def create_contact_new(self):
        hubspot_instance_model = self.env['hubspot.instance'].search([('default_instance', '=', True)])
        
        if not self.is_company:
                # create hubspot dictionary
            properties = []
            if self.email:
                properties.append({'property': 'email', 'value': str(self.email)})
            if self.name:
                properties.append({'property': 'firstname', 'value': (self.name).split(' ')[0]})
                if len(self.name.split(' ')) > 1:
                    properties.append({'property': 'lastname', 'value': (self.name).split(' ')[-1]})
            if self.parent_id:
                properties.append({'property': 'company', 'value': self.parent_id.name})
            # if self.mobile:
            #     properties.append({'property': 'mobilephone', 'value': self.mobile})
            if self.phone:
                properties.append({'property': 'phone', 'value': self.phone})
            if self.function:
                properties.append({'property': 'jobtitle', 'value': self.function})
            if self.city:
                properties.append({'property': 'city', 'value': self.city})
            if self.state_id:
                properties.append({'property': 'state', 'value': self.state_id.name})
            if self.country_id:
                properties.append({'property': 'country', 'value': self.country_id.name})
            if self.street or self.street2:
                address = ''
                if self.street:
                    address += self.street
                elif self.street2:
                    address += self.street2
                properties.append({'property': 'address', 'value': address})
            if self.zip:
                properties.append({'property': 'zip', 'value': self.zip})
            if self.website:
                properties.append({'property': 'website', 'value': self.website})
            #                 if eachNewContact.fax:
            #                     properties.append({'property': 'fax', 'value': eachNewContact.fax})
            # if self.title:
            #     properties.append({'property': 'salutation', 'value': self.title.name})

            # NEW CODE
            contact_field_mapping = self.env['contact.field.mapping'].search(
                    [('hubspot_instance_id', '=', hubspot_instance_model.id)])
            if contact_field_mapping:
                for contact_field_mapping_id in contact_field_mapping:
                    if contact_field_mapping_id.odoo_fields.name and contact_field_mapping_id.hubspot_fields.technical_name:
                        partner_read_obj = self.read()[0]
                        properties.append({
                            'property': contact_field_mapping_id.hubspot_fields.technical_name,
                            'value': partner_read_obj.get(contact_field_mapping_id.odoo_fields.name)
                        })

            # user (Owner) sync
            if self.user_id:
                if not self.user_id.hubspot_uid:
                    logger.warning("Odoo User Not Available In Hubspot")
                    self.env['res.partner'].syncAllUsers(hubspot_instance_model)
                if self.user_id.hubspot_uid:
                    properties.append({'property': 'hubspot_owner_id', 'value': self.user_id.hubspot_uid})
            else:
                properties.append({'property': 'hubspot_owner_id', 'value': ''})
            # create new hubspot contact
            if properties:
                try:
                    try:
                        response_create_contact = hubspot_instance_model._send_post_request('/contacts/v1/contact/', {'properties': properties})
                        json_response_create_contact = json.loads(response_create_contact)
                        if not json_response_create_contact['canonical-vid']:
                            self.env['hubspot.logger'].create_log_message('Export Contacts', str(json_response_create_contact) + "\nvals: " + str(properties))
                        context_dict = {}
                        context_dict['hubspot_id'] = json_response_create_contact['canonical-vid']
                        self.with_context(from_hubspot=True).write(context_dict)
                        self.with_context(from_hubspot=True).hubspot_instance_id = hubspot_instance_model.id
                        if self.parent_id and hubspot_instance_model.hubspot_is_export_company:
                            if not self.parent_id.hubspot_id:
                                self.parent_id.createNewCompanyInHubspot(hubspot_instance_model)
                            hubspot_instance_model._send_put_request(
                                '/companies/v2/companies/' + str(self.parent_id.hubspot_id) + '/contacts/' + str(self.hubspot_id), ({'properties': {}}))
                            self.with_context(from_hubspot=True).hubspot_id = json_response_create_contact['canonical-vid']
                    except Exception as e:
                        response_get_contact = hubspot_instance_model._send_get_request('/contacts/v1/contact/email/' + str(self.email) + '/profile')
                        existingContact = json.loads(response_get_contact)
                        
                        if existingContact:
                            self.with_context(from_hubspot=True).hubspot_id = existingContact['canonical-vid']
                            self.hubspot_instance_id = hubspot_instance_model.id
                        else:
                            error_message = 'Error while exporting odoo contact %d \n\n Odoo vals: %s\n Hubspot response %s' % (
                                self.id, str(properties), str(existingContact))
                            self.env['hubspot.logger'].create_log_message('Export Contacts', error_message)
                        hubspot_instance_model._raise_user_error(e)
                except Exception as e:
                    error_message = 'Error while exporting odoo contact %d \n\n Odoo vals: %s\n Hubspot response %s' % (
                        self.id, str(properties), str(e))
                    self.env['hubspot.logger'].create_log_message('Export Contacts', error_message)
                    logger.exception("Exception in Hubspot Connection  :\n" + str(e))
                    hubspot_instance_model._raise_user_error(e)
        message = 'Exported contacts successfully'
        self.env['hubspot.logger'].create_log_message('Export Contacts', message)
        logger.info('Exported contacts successfully...')
        
        
        
        
    def create_company_new(self):
        hubspot_instance_model = self.env['hubspot.instance'].search([('default_instance', '=', True)])
        logger.info('Creating new companies in hubspot')
        properties = []
        if self.is_company:
            if self.name:
                properties.append({'name': 'name', 'value': self.name})
            if self.phone:
                properties.append({'name': 'phone', 'value': self.phone})
            if self.website:
                properties.append({'name': 'website', 'value': self.website})
            if self.street:
                properties.append({'name': 'address', 'value': self.street})
            if self.city:
                properties.append({'name': 'city', 'value': self.city})
            if self.state_id:
                properties.append({'name': 'state', 'value': self.state_id.name})
            if self.country_id:
                properties.append({'name': 'country', 'value': self.country_id.name})
            if self.zip:
                properties.append({'name': 'zip', 'value': self.zip})
            if self.email and len(self.email.split('@')) > 1:
                properties.append({'name': 'domain', 'value': self.email.split('@')[1]})

            # Sync owner
            if self.user_id:
                if not self.user_id.hubspot_uid:
                    logger.warning("Odoo User Not Available In Hubspot")
                    self.env['res.partner'].syncAllUsers(self.hubspot_instance_id)
                if self.user_id.hubspot_uid:
                    properties.append({'name': 'hubspot_owner_id', 'value': self.user_id.hubspot_uid})
            else:
                properties.append({'name': 'hubspot_owner_id', 'value': ''})

            # NEW CODE
            company_field_mapping = self.env['company.field.mapping'].search(
                [('hubspot_instance_id', '=', hubspot_instance_model.id)])
            if company_field_mapping:
                for company_field_mapping_id in company_field_mapping:
                    if company_field_mapping_id.odoo_fields.name and company_field_mapping_id.hubspot_fields.technical_name:
                        partner_read_obj = self.read()[0]
                        properties.append({
                            'property': company_field_mapping_id.hubspot_fields.technical_name,
                            'value': partner_read_obj.get(company_field_mapping_id.odoo_fields.name)
                        })

        # Create new hubspot Account(company)
        if len(properties) > 0:
            try:
                response_create_company = hubspot_instance_model._send_post_request('/companies/v2/companies/', {'properties': properties})
                json_response_create_company = json.loads(response_create_company)
                self.with_context({'from_hubspot': True}).hubspot_id = json_response_create_company['companyId']
                self.hubspot_instance_id = hubspot_instance_model.id
            except Exception as e:
                error_message = 'Error while creating new company %d in hubspot \n\n Odoo vals: %s\n Hubspot response %s' % (
                    self.id, str(properties), str(e))

                self.env['hubspot.logger'].create_log_message('Export Companies', str(error_message))
                logger.exception("Exception in Creating New Company in hubspot :\n" + str(e))
                hubspot_instance_model._raise_user_error(e)
        message = 'Company Export Completed'
        self.env['hubspot.logger'].create_log_message('Export Companies', str(message))
        logger.info('Company Export Completed...')
        
            
            
            




   
