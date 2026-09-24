import logging
import random
import json
from odoo import fields, models

from .hubspot import convert_time_to_unix_timestamp
import logging
logger = logging.getLogger(__name__)
from odoo.tools import config
config['limit_time_real'] = 10000000


class ResUsers(models.Model):
    _inherit = "res.users"

    hubspot_uid = fields.Char('Hubspot User id', readonly=True, copy=False)
    hubspot_instance_id = fields.Many2one('hubspot.instance', 'Hubspot Instance Name', help="Hubspot Instance Name", readonly=True, copy=False)

    # def _cron_syncAllUsers(self):
    #     hubspot_instance_obj = self.env['hubspot.instance'].search([('active', '=', True)])
    #     for hubspot_instance in hubspot_instance_obj:
    #         self.syncAllUsers(hubspot_instance)

    # def syncAllUsers(self, hubspot_instance):
    #     try:
            
    #         logger.info('Getting All Users from hubspot')
    #         allUsers = self.search(['|', ('active', '=', True), ('active', '=', False), ('hubspot_uid', '!=', False),('hubspot_instance_id', '=', hubspot_instance.id), ('id', 'not in', [3, 1, 5, 4])])
    #         Userids = allUsers.read(['hubspot_uid'])
    #         UserHubspotIds = [each['hubspot_uid'] for each in Userids]
    #         response_get_all_users = hubspot_instance._send_get_request('/owners/v2/owners')
    #         json_response_all_contacts = json.loads(response_get_all_users)

    #         logger.info("Owner response logger9 %s: " % json_response_all_contacts)
    #         for owner in json_response_all_contacts:
    #             try:
    #                 owner_id = str(owner.get('ownerId'))
    #                 user_dict = {'hubspot_uid': owner_id}
    #                 if owner.get('email'):
    #                     user_dict.update({'login': owner.get('email')})
    #                     user_dict.update({'email': owner.get('email')})
                        
    #                 user_name = ''
    #                 if owner.get('firstName'):
    #                     user_name += owner.get('firstName') + ' '
                        
    #                     logger.info("user_name===== first name>>>>{}".format(user_name))
    #                     # user_dict.update({'name': owner.get('firstName')})
    #                 if owner.get('lastName'):
    #                     user_name += owner.get('lastName')
                        
    #                     # user_dict.update({'name': owner.get('lastName')})
    #                 user_dict['name'] = user_name
                    
    #                 if not owner.get('firstName') and not owner.get('lastName'):
    #                     user_dict.update({'name': owner.get('email')})
    #                     logger.info("user_dict1 update first name no last name===== >>>>{}".format(user_dict))
    #                 hubspot_modifiedDate = owner.get('updatedAt')
    #                 if owner_id in UserHubspotIds:
    #                     search_user = self.search(
    #                         ['|', ('active', '=', True), ('active', '=', False), ('hubspot_uid', '=', owner_id), ('hubspot_instance_id', '=', hubspot_instance.id)], limit=1)
                        
    #                     odoo_modifiedDate = convert_time_to_unix_timestamp(search_user.write_date)
    #                     logger.info("Owner Is Available with hubspot id in odoo: " + str(search_user))
    #                     if int(hubspot_modifiedDate) > int(odoo_modifiedDate):
    #                         search_user.with_context({'from_hubspot': True}).write(user_dict)
    #                         search_user.write({'hubspot_instance_id':hubspot_instance.id})
                            
    #                         self._cr.commit()
    #                 else:
    #                     search_user = self.search(
    #                         ['|', ('active', '=', True), ('active', '=', False), ('login', '=', owner.get('email'))], limit=1)
                        
    #                     if search_user:
    #                         logger.info("Found owner with email in odoo: " + str(search_user))
    #                         search_user.with_context({'from_hubspot': True}).write(user_dict)
    #                         search_user.with_context({'from_hubspot': True}).write({'hubspot_instance_id':hubspot_instance.id})
    #                         self._cr.commit()
    #                     else:
    #                         email_exists = self.search(['|', ('active', '=', True), ('active', '=', False), ('hubspot_instance_id', '=', hubspot_instance.id),
    #                                                     ('hubspot_uid', '=', owner.get('ownerId'))], limit=1)
                            
    #                         if not email_exists and owner.get('email'):
    #                             user_id = self.with_context({'from_hubspot': True}).create(user_dict)
                                
    #                             user_id.write({'hubspot_instance_id': hubspot_instance.id})
    #                             logger.info("Owner created in odoo : {}".format(user_id))
    #                             self._cr.commit()
    #                         else:
    #                             logger.info("Before formatting email_id owner dict logger5 %s: " % str(owner))
    #                             email_id = owner.get('email') + str(random.randint(0, 999))
    #                             logger.info("email_id logger6 %s: " % str(email_id))
    #                             user_dict.update({'login': email_id})
    #                             logger.info("In if not email_exists exists logger7 %s: " % user_dict)
    #                             user_id = self.with_context({'from_hubspot': True}).create(user_dict)
    #                             user_id.write({'hubspot_instance_id': hubspot_instance.id})
    #                             logger.info("Owner created in odoo : {}".format(user_id))
    #                             self._cr.commit()
    #             except Exception as ex:
    #                 error_message = 'Error while sync users in odoo vals: %s\n Hubspot response %s' % (owner, str(ex))
    #                 self.env['hubspot.logger'].create_log_message('Import Users', error_message)
    #                 logger.exception("Exception in sync users in Odoo :\n" + error_message)
    #                 hubspot_instance._raise_user_error(ex)
    #             message = 'Done Syncing Users'
    #             self.env['hubspot.logger'].create_log_message('Import Users', message)
    #             logger.info('Done Syncing Users')
    #     except Exception as ex:
    #         error_message = 'Error while getting users in odoo \nHubspot response %s' % (str(ex))
    #         self.env['hubspot.logger'].create_log_message('Import Users', error_message)
    #         logger.exception("Error in getting users From Hubspot------------>\n" + error_message)
    #         hubspot_instance._raise_user_error(ex)

    # def getOwnerDetailsFromHubspot(self, owner_id, hubspot_instance):
    #     '''
    #     Args:
    #         @param owner_id: hubspot owner id used to update or add in user
    #     Returns:
    #         @return: return user if availble with same email or create new one
    #     '''
    #     logger.info('Getting Owner Details from hubspot')
    #     # Hubspot Owner Information
    #     try:
    #         response_get_user_by_id = hubspot_instance._send_get_request('/owners/v2/owners/' + str(owner_id))
    #         json_response_get_user_by_id = json.loads(response_get_user_by_id)
    #         res_user_id = self.createNewUserInOdoo(json_response_get_user_by_id, hubspot_instance)
    #         logger.info("res_user_id===== first name>>>>{}".format(res_user_id))
    #         # self.syncAllUsers(hubspot_instance)
    #         # search_user = self.search(
    #         #     ['|', ('active', '=', True), ('active', '=', False), ('hubspot_uid', '=', owner_id), ('hubspot_instance_id', '=', hubspot_instance.id)])
    #         message = 'Created/updated user in odoo'
    #         self.env['hubspot.logger'].create_log_message('Import Users', message)
    #         logger.info('Created/updated user in odoo')
    #         return res_user_id
    #     except Exception as ex:
    #         error_message = 'Error while importing hubspot users in odoo Id: %s\n Hubspot response %s' % (owner_id, str(ex))
    #         self.env['hubspot.logger'].create_log_message('Import Users', error_message)
    #         logger.exception("Could not get owner details from hubspot : %s " % ex)
    #         hubspot_instance._raise_user_error(ex)

    #     return False

    # def createNewUserInOdoo(self, hubspot_dict, hubspot_instance):
    #     try:
    #         user_dict = {'hubspot_uid': hubspot_dict.get('ownerId')}
    #         logger.info("user_dict new user>>>>{}".format(user_dict))
    #         if hubspot_dict.get('email'):
    #             user_dict.update({'login': hubspot_dict.get('email')})
    #             logger.info("user_dict get email====={}".format(user_dict))
    #             user_dict.update({'email': hubspot_dict.get('email')})
    #             logger.info("user_dict=====update email>>>{}".format(user_dict))
    #         user_name = ''
    #         if hubspot_dict.get('firstName'):
    #             user_name += hubspot_dict.get('firstName') + ' '
    #             logger.info("user_name===== first name>>>>{}".format(user_name))
    #         if hubspot_dict.get('lastName'):
    #             user_name += hubspot_dict.get('lastName')
    #             logger.info("user_name===== last name>>>>{}".format(user_name))
    #         user_dict['name'] = user_name
           
    #         if not hubspot_dict.get('firstName') and not hubspot_dict.get('lastName'):
    #             user_dict.update({'name': hubspot_dict.get('email')})
    #             logger.info("user_name===== first name>>>>{}".format(user_dict))
    #         res_user_id = self.search(['|', ('active', '=', True), ('active', '=', False), ('hubspot_uid', '=', str(hubspot_dict.get('ownerId'))), ('hubspot_instance_id', '=', hubspot_instance.id)], limit=1)
    #         logger.info("res_user_id===== e>>>>{}".format(res_user_id))
    #         hubspot_modifiedDate = hubspot_dict.get('updatedAt')
    #         if res_user_id:
    #             odoo_modifiedDate = convert_time_to_unix_timestamp(res_user_id.write_date)
    #             logger.info("odoo modified date====>>>>{}".format(odoo_modifiedDate))
    #             if int(hubspot_modifiedDate) > int(odoo_modifiedDate):
    #                 res_user_id.with_context({'from_hubspot': True}).write(user_dict)
    #                 logger.info("res_uuser_id=====write>>>>{}".format(res_user_id))
    #                 return res_user_id
    #         else:
    #             if 'login' in user_dict or 'email' in user_dict:
    #                 user_id = self.search(['|', ('active', '=', True), ('active', '=', False), ('login', '=', hubspot_dict.get('email')), ('hubspot_uid', '=', False), ('hubspot_instance_id', '=', False)], limit=1)
    #                 logger.info("user_id=====>>>>{}".format(user_id))
    #                 if user_id:
    #                     user_id.with_context({'from_hubspot': True}).write(user_dict)
    #                     user_id.write({'hubspot_instance_id': hubspot_instance.id})
    #                     logger.info("user_name===== hubspot instance write>>>>{}".format(user_id))
    #                     return user_id
    #                 else:
    #                     res_user_email_exists = self.search(['|', ('active', '=', True), ('active', '=', False), ('login', '=', hubspot_dict.get('email')), ('hubspot_instance_id', '!=', hubspot_instance.id)], limit=1)
    #                     logger.info("resuser exists email>>>>{}".format(res_user_email_exists))
    #                     if res_user_email_exists:
    #                         email_id = hubspot_dict.get('email') + str(random.randint(0, 999))
    #                         logger.info("email_id logger6 %s: " % str(email_id))
    #                         user_dict.update({'login': email_id, 'email': email_id})
    #                         logger.info("In if not email_exists exists logger7 %s: " % user_dict)
    #                         user_id = self.with_context({'from_hubspot': True}).create(user_dict)
    #                         user_id.write({'hubspot_instance_id': hubspot_instance.id})
    #                         logger.info("Owner created in odoo : {}".format(user_id))
    #                         self._cr.commit()
    #                         return user_id
    #                     else:
    #                         user_id = self.with_context({'from_hubspot': True}).create(user_dict)
    #                         logger.info("user_id else>>>>{}".format(user_id))
    #                         user_id.with_context({'from_hubspot': True}).write({'hubspot_instance_id': hubspot_instance.id})
    #                         logger.info("user_id write===== hubspot instacne>>>>{}".format(user_id))
    #                         logger.info("Owner updated in odoo : {}".format(user_id))
    #                         self._cr.commit()
    #     except Exception as ex:
    #         error_message = 'Error while creating hubspot deals in odoo vals: %s\n Hubspot response %s' % (hubspot_dict, str(ex))
    #         self.env['hubspot.logger'].create_log_message('Import Users', error_message)
    #         logger.exception("Exception in Creating New Users in Odoo :\n" + error_message)
    #         hubspot_instance._raise_user_error(ex)





