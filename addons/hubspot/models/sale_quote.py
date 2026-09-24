import logging,re
import datetime
import json,requests
from datetime import timezone,datetime
from odoo import api, fields, models, _
from time import sleep
from odoo.exceptions import UserError
from odoo import Command, _, api, fields, models

logger = logging.getLogger(__name__)
from odoo.tools import config
config['limit_time_real'] = 10000000

class SaleQuote(models.Model):
    
    
    _inherit = 'sale.order'
    _description = 'sale.order'
    
    
    hubspot_sale_order_id = fields.Char('Hubspot Sale Order Id', store=True, readonly=True, copy=False)
    hubspot_instance_id = fields.Many2one('hubspot.instance', 'Hubspot Instance Name', help="Hubspot Instance Name", readonly=True, copy=False)
    hubspot_quote_status = fields.Char('Hubspot Quote Status',store=True, readonly=True, copy=False)
    all_products = fields.Boolean("All Products")
    
    
    @api.model
    def _cron_import_quotes_from_hubspot(self):
        hubspot_instance_obj = self.env['hubspot.instance'].sudo().search([('active', '=', True), ('hubspot_is_import_quotes', '=', True)])
        for hubspot_instance in hubspot_instance_obj:
            self.import_quotes_from_hubspot(hubspot_instance)
            
    
   
#############################import quotes##########################################
    
    @api.model
    def import_quotes_from_hubspot(self, hubspot_instance):
        """This function is called from cron to import quotes from HubSpot"""
    
        if hubspot_instance.active  and hubspot_instance.hubspot_is_import_quotes:
            logger.info('Getting All Quotes from HubSpot---------------------------')
            
           
            next_page_url = '/crm/v3/objects/quotes?limit=100&properties=hs_quote_amount,hs_status'
            
            try:
                while next_page_url:
                    
                    response_all_quotes = hubspot_instance._send_get_request(next_page_url)
                    json_response_all_quotes = json.loads(response_all_quotes)
                    if json_response_all_quotes.get('results'):
                        for quote_info in json_response_all_quotes['results']:
                            self.create_quote_and_sale_order_lines(quote_info, hubspot_instance)
                    else:
                        logger.info("No quotes found in the current page.")
                    
                    after = json_response_all_quotes.get('paging', {}).get('next', {}).get('after')
                    next_page_url = f"/crm/v3/objects/quotes?&after={after}&properties=hs_quote_amount,hs_status" if after else None
                # Summary row in the HubSpot Logger (previously only written to the server log) ######
                self.env['hubspot.logger'].create_log_message('Import Quotes', 'Completed Getting All Quotes from HubSpot')
                    
            
            except Exception as e:
                logger.error(f"Error during HubSpot quotes import: {e}")
                # Failures were silently swallowed; record them in the HubSpot Logger ######
                self.env['hubspot.logger'].create_log_message(
                    'Import Quotes', 'Error while importing quotes from HubSpot: %s' % e)

             
    @api.model
    def create_quote_and_sale_order_lines(self,quote_info,hubspot_instance):
        
        hubspot_instance_model = self.env['hubspot.instance'].sudo().search([('default_instance', '=', True),('active', '=', True)])
        properties = quote_info.get('properties', {})
        

        quote_id = properties.get('hs_object_id')
        quote_name = properties.get('hs_title')
        quote_create_date_str = properties.get('hs_createdate')
        quote_status = properties.get('hs_status')
        quote_amount =   properties.get('hs_quote_amount')
        quote_line_item_contact = ''
        response_get_associated_contacts_line_item = hubspot_instance._send_get_request(f'/crm/v3/objects/quotes/{quote_id}/associations/contacts')
        json_response_get_associated_contacts_line_item = json.loads(response_get_associated_contacts_line_item)
        if json_response_get_associated_contacts_line_item['results']:
            quote_line_item_contact = json_response_get_associated_contacts_line_item['results'][0]['id']
        else:
           
            logger.info("++++++++++++=no associated contact======")
              
        response_get_associated_quote_line_item_contact_detail = hubspot_instance._send_get_request(f'/crm/v3/objects/contacts/{quote_line_item_contact}')
        json_response_get_associated_quote_line_item_contact_detail = json.loads(response_get_associated_quote_line_item_contact_detail)
        hubspot_contact_id = json_response_get_associated_quote_line_item_contact_detail['properties']['hs_object_id']
        contact_search = self.env['res.partner'].sudo().search([('hubspot_id', '=', hubspot_contact_id)],limit=1)
        if not contact_search:
            raise UserError(_('Please import contacts before importing quotes.'))
        
        order = self.env['sale.order'].sudo().search([('hubspot_sale_order_id', '=', quote_id)],limit=1)
        if not order:
            
            quote_create_date = datetime.strptime(quote_create_date_str, '%Y-%m-%dT%H:%M:%S.%fZ')
            quote_vals = {
                'date_order':quote_create_date.strftime('%Y-%m-%d %H:%M:%S'),
                'hubspot_sale_order_id':quote_id,
                'partner_id':contact_search.id,
                'hubspot_instance_id':hubspot_instance_model.id,
                'hubspot_quote_status':quote_status,
                'amount_total':quote_amount
                
            }
            quote = self.env['sale.order'].create(quote_vals)
            quote_line_item = self.create_quote_line_item(quote_info,quote,quote_amount,hubspot_instance)
            # One Success row per imported quote (record details in the logger) ######
            self.env['hubspot.logger']._log_record_sync(quote, 'import', 'created')
           
            self.env.cr.commit()

            
            

    def create_quote_line_item(self, quote, quote_info, quote_amount, hubspot_instance):
        tax_line_item_value = None
        discount_line_item_value = None
        fee_line_item_value = None
        properties = quote.get('properties', {})
        
        quote_id = properties.get('hs_object_id')

        response_get_associated_quote_line_item = hubspot_instance._send_get_request(
            f'/crm/v3/objects/quotes/{quote_id}/associations/line_items')
        json_response_associated_quote_line_item = json.loads(response_get_associated_quote_line_item)

        response_get_associated_tax_line_item = hubspot_instance._send_get_request(
            f'/crm/v3/objects/quotes/{quote_id}/associations/taxes')
        json_response_associated_tax_line_item = json.loads(response_get_associated_tax_line_item)
        quote_line_item_tax_id = None
        if json_response_associated_tax_line_item['results']:
            quote_line_item_tax_id = json_response_associated_tax_line_item['results'][0]['id']
        else:
            logger.info("No ID value present in the response.")

        quote_tax_search = None
        properties = ["hs_type", "hs_value", "hs_label", "hs_object_source", "hs_object_source_id"]
        properties_string = ",".join(properties)
        limit=0
        if quote_line_item_tax_id:
            response_get_associated_tax = hubspot_instance._send_get_request(f'/crm/v3/objects/taxes/{quote_line_item_tax_id}?limit={limit}&properties={properties_string}')
            json_response_get_associated_tax = json.loads(response_get_associated_tax)
            if json_response_get_associated_tax:
                all_properties = json_response_get_associated_tax.get('properties')
                hubspot_tax_name = all_properties.get('hs_label')
                hubspot_tax_computation = all_properties.get('hs_type')
                hubspot_tax_value = all_properties.get('hs_value')
                hubspot_tax_id_value = all_properties.get('hs_object_id')
               
                tax_data = {
                    'name': hubspot_tax_name,
                    'amount': hubspot_tax_value,
                    'hubspot_tax_id': hubspot_tax_id_value,
                    
                }
                hubspot_tax_search = self.env['account.tax'].sudo().search([('name', '=', hubspot_tax_name)],limit=1)
               
                if hubspot_tax_search:
                    tax_id = self.env['account.tax'].write(tax_data)
                else:
                    tax_id = self.env['account.tax'].create(tax_data)
                   
                quote_tax_search = self.env['account.tax'].sudo().search([('name', '=', hubspot_tax_name)],limit=1)
            else:
                logger.info("++++++++++++=no tax")
        response_get_associated_discount_line_item = hubspot_instance._send_get_request(f'/crm/v3/objects/quotes/{quote_id}/associations/discounts')
        json_response_associated_discount_line_item = json.loads(response_get_associated_discount_line_item)
        quote_line_item_discount_id = None
        if json_response_associated_discount_line_item['results']:
            quote_line_item_discount_id = json_response_associated_discount_line_item['results'][0]['id']
        else:
            logger.info("No ID value present in the response.")
        if quote_line_item_discount_id:
            response_get_associated_discount = hubspot_instance._send_get_request(f'/crm/v3/objects/discount/{quote_line_item_discount_id}?limit={limit}&properties={properties_string}')
            json_response_get_associated_discount = json.loads(response_get_associated_discount)
            if json_response_get_associated_discount:
                all_properties = json_response_get_associated_discount.get('properties')
                
                hubspot_discount_name = all_properties.get('hs_label')
                hubspot_discount_type = all_properties.get('hs_type')
                hubspot_discount_value = all_properties.get('hs_value')
                hubspot_discount_id_value = all_properties.get('hs_object_id')
                discount_line_item_value = float(hubspot_discount_value)
            
        
        else:
            logger.info("++++++++++++=no discount")   
        

       

        response_get_associated_fee_line_item = hubspot_instance._send_get_request(f'/crm/v3/objects/quotes/{quote_id}/associations/fees')
        json_response_associated_fee_line_item = json.loads(response_get_associated_fee_line_item)
        quote_line_item_fee_id = None
        if json_response_associated_fee_line_item['results']:
            quote_line_item_fee_id = json_response_associated_fee_line_item['results'][0]['id']
        else:
            logger.info("No fee ID value present in the response.")
        if quote_line_item_fee_id:
            response_get_associated_fees =  hubspot_instance._send_get_request(f'/crm/v3/objects/fees/{quote_line_item_fee_id}?limit={limit}&properties={properties_string}')
            json_response_get_associated_fees = json.loads(response_get_associated_fees)
            if json_response_get_associated_fees:
                all_properties = json_response_get_associated_fees.get('properties')
                
                hubspot_fee_name = all_properties.get('hs_label')
                hubspot_fee_type = all_properties.get('hs_type')
                hubspot_fee_value = all_properties.get('hs_value')
                hubspot_fee_id_value = all_properties.get('hs_object_id')
                fee_line_item_value = float(hubspot_fee_value)
        
        
        else:
        
            logger.info("No fees found in the response.")
       
        quote_ids = [item['id'] for item in json_response_associated_quote_line_item['results']]
        for quote_value_id in quote_ids:
            if isinstance(quote_value_id, dict):
                quote_value_id = quote_value_id['id'] 

            response_get_associated_quote_line_item_detail = hubspot_instance._send_get_request(f'/crm/v3/objects/line_items/{quote_value_id}')
            json_response_get_associated_quote_line_item_detail = json.loads(response_get_associated_quote_line_item_detail)

            quantity = float(json_response_get_associated_quote_line_item_detail['properties']['quantity'])
            amount = float(json_response_get_associated_quote_line_item_detail['properties']['amount'])
            unit_price = float(amount / quantity)

            hubspot_product_id_value = json_response_get_associated_quote_line_item_detail['properties']['hs_product_id']
            if hubspot_product_id_value:
                response_get_product_details = hubspot_instance._send_get_request(f'/crm/v3/objects/products/{hubspot_product_id_value}')
                hubspot_product_details = json.loads(response_get_product_details)
                hubspot_product_name = hubspot_product_details.get('properties', {}).get('name')
                hubspot_product_price = hubspot_product_details.get('properties', {}).get('price')
                hubspot_product_default_code = hubspot_product_details.get('properties', {}).get('hs_sku')
                hubspot_product_type = hubspot_product_details.get('properties', {}).get('hs_product_type')
                hubspot_product_description = hubspot_product_details.get('properties', {}).get('description')
                hubspot_cleaned_description = re.sub(r'<[^>]*>', '', hubspot_product_description) if hubspot_product_description else ''
                hubspot_id = hubspot_instance.id
                hubspot_product_type_mapping = {
                    'inventory': 'consu',
                    'non_inventory': 'consu',
                    'service': 'service',
                }
                odoo_detailed_type = hubspot_product_type_mapping.get(hubspot_product_type, 'consu')
                is_storable = hubspot_product_type == 'inventory'
                if not odoo_detailed_type:
                
                    raise ValueError(f"Invalid hubspot_product_type: {hubspot_product_type}")

                

            else:
                logger.info("++++++++++++no product_id==========")
            
            products = self.env['product.product'].sudo().search([('hubspot_product_id', '=', hubspot_product_id_value)],limit=1)
            
            if not products:
                raise UserError(_('Please import products before importing quotes.'))

            product_data = {
                'hubspot_product_id': hubspot_product_id_value if hubspot_product_id_value else '',
                'name': hubspot_product_name if hubspot_product_name else '',
                'list_price': hubspot_product_price if hubspot_product_price else '',
                'default_code': hubspot_product_default_code if hubspot_product_default_code else '',
                'type': odoo_detailed_type if odoo_detailed_type else '',
                'description': hubspot_cleaned_description if hubspot_cleaned_description else '',
                'hubspot_instance_id': hubspot_id,
                'is_storable': is_storable,
            }
           
            
            if products:
                order_line_data = {
                    'product_id': products.id if products.id else '',
                    'order_id': quote_info.id if quote_info.id else '',
                    'name': products.name if products.name else '',
                    'price_unit': unit_price if unit_price else '',
                    'product_uom_qty': quantity if quantity else '',
                    'discount': discount_line_item_value if discount_line_item_value and hubspot_discount_type == 'PERCENT' else '',
                    'tax_ids': [(6, 0, quote_tax_search.ids)] if quote_tax_search else False
                }
                order_line = self.env['sale.order.line'].create(order_line_data)
               
            else:
                products = self.env['product.product'].create(product_data)
                order_line_data = {
                    'product_id': products.id if products.id else '',
                    'order_id': quote_info.id if quote_info.id else '',
                    'name': products.name if products.name else '',
                    'price_unit': unit_price if unit_price else '',
                    'product_uom_qty': quantity if quantity else '',
                    'discount':discount_line_item_value if discount_line_item_value and hubspot_discount_type == 'PERCENT' else '',
                    'tax_ids': [(6, 0, quote_tax_search.ids)] if quote_tax_search else False
                }
                order_line = self.env['sale.order.line'].create(order_line_data)
                return products
            
            service_type_product_fee_search = None
            existing_service_fee_line = None
            service_type_product_discount_search = None
            service_type_product_fee_search = self.env['product.product'].sudo().search([('name', '=', 'Fees')], limit=1)
            if not service_type_product_fee_search:
                service_type_product_fee_search = self.env['product.product'].create({
                'name': 'Fees',
                'type': 'service',  
                'list_price': 0.0  
               
            })
            service_type_product_discount_search = self.env['product.product'].sudo().search([('name', '=', 'Discount')], limit=1)
            if not service_type_product_discount_search:
                
                service_type_product_discount_search = self.env['product.product'].create({
                'name': 'Discount',
                'type': 'service',  
                'list_price': 0.0  
               
            })
            

                
            

            if fee_line_item_value and hubspot_fee_type == 'FIXED':
                existing_service_fee_line = self.env['sale.order.line'].sudo().search([
                    ('product_id', '=', service_type_product_fee_search.id),
                    ('order_id', '=', quote_info.id)
                ])

               
                if not existing_service_fee_line:
                    order_line_service_product_data = {
                        'product_id': service_type_product_fee_search.id,
                        'order_id': quote_info.id,
                        'name': service_type_product_fee_search.name,
                        'price_unit': fee_line_item_value,
                        'tax_ids': [(6, 0, quote_tax_search.ids)] if quote_tax_search else False,
                    }
                    order_line_service = self.env['sale.order.line'].create(order_line_service_product_data)
                    
            
            if discount_line_item_value and hubspot_discount_type == 'FIXED':
                existing_service_discount_line = self.env['sale.order.line'].sudo().search([
                    ('product_id', '=', service_type_product_discount_search.id),
                    ('order_id', '=', quote_info.id)
                ])
                vals = {
                    'order_id': quote_info.id,
                    'product_id': service_type_product_discount_search.id,
                    'sequence': 999,
                    'price_unit': -discount_line_item_value,
                    'tax_ids': [(6, 0, quote_tax_search.ids)] if quote_tax_search else False,
                    }
                
               
            
                
                if not existing_service_discount_line:
                    
                        order_line_service_product_data = {
                            'product_id': service_type_product_discount_search.id,
                            'order_id': quote_info.id,
                            'name': service_type_product_discount_search.name,
                            'tax_ids': [(6, 0, quote_tax_search.ids)] if quote_tax_search else False,
                           
                        }
                        order_line_service = self.env['sale.order.line'].create(vals)
                    
            else:
                logger.info("complete==========")
                


                
                
                

                  
class SaleOrderLine(models.Model):
        
    
    _inherit = 'sale.order.line'
    _description = 'Sale Order Lines'
    
    
    
    
    discount_fee = fields.Float('Discount Fee',store=True, copy=False)
                          
class Taxes(models.Model):
        
    
    _inherit = 'account.tax'
    _description = 'Taxes'
    
    
    
    hubspot_tax_id = fields.Char('Hubspot Tax Id' ,store=True, readonly=True, copy=False)
   




        