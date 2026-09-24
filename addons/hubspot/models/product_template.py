import logging
import datetime
import json,re,requests
from datetime import timezone
from odoo import api, fields, models, _
from odoo.exceptions import UserError
logger = logging.getLogger(__name__)
from odoo.tools import config
config['limit_time_real'] = 10000000

class ProductTemplate(models.Model):
    _inherit = "product.template"

    hubspot_id = fields.Char('Hubspot Id', store=True, readonly=True, copy=False)
    hubspot_product_id = fields.Char('Hubspot Product Id',store=True, readonly=True, copy=False)
    hubspot_instance_id = fields.Many2one('hubspot.instance', 'Hubspot Instance Name', help="Hubspot Instance Name", readonly=True, copy=False)
    

    
    
    
   


                

########################################## Import Products###############################################    
    
    # @api.model
    # def import_products_from_hubspot(self, hubspot_instance):
    #     """This function is called from cron to import products from hubspot"""
    #     modifiedDateForProducts = hubspot_instance.modifiedDateForProducts or ''
    #     all_products = hubspot_instance.all_products
    #     if hubspot_instance.active and hubspot_instance.hubspot_sync_products  and hubspot_instance.hubspot_is_import_products:  
    #         logger.info('Getting All Products from hubspot---------------------------')
           
    #         record_limit = 1
    #         response_all_products = hubspot_instance._send_get_request('/crm/v3/objects/products?limit=100&properties=name,description,price,hs_sku,hs_product_type')
    #         json_response_all_products = json.loads(response_all_products)
            
    #         hubspot_modifiedDateForProduct = ''
    #         if json_response_all_products and 'results' in json_response_all_products:
    #             for product_id in json_response_all_products['results']:
    #                 product_id_1 = product_id['id']
    #                 product_name = product_id['properties']['name']
    #                 hubspot_price = product_id['properties']['price']
    #                 product_default_code = product_id['properties']['hs_sku']
    #                 hubspot_product_type = product_id['properties']['hs_product_type']
    #                 product_description = product_id['properties']['description']
    #                 cleaned_description = re.sub(r'<[^>]*>', '', product_description) if product_description else ''
    #                 # image_url = product_data['properties'].get('hs_images')

    #                 product_type_mapping = {
    #                     'inventory': 'consu',
    #                     'non_inventory': 'consu',
    #                     'service': 'service',
    #                 }
    #                 odoo_detailed_type = product_type_mapping.get(hubspot_product_type, 'consu')
    #                 is_storable = hubspot_product_type == 'inventory'

    #                 odoo_product_data = {
    #                     'hubspot_product_id': product_id_1,
    #                     'name': product_name,
    #                     'list_price': hubspot_price,
    #                     'default_code': product_default_code,
    #                     'type': odoo_detailed_type,
    #                     'description_sale': cleaned_description,
    #                     'hubspot_instance_id': hubspot_instance.id,
    #                     'is_storable': is_storable,  
    #                 }

    #                 # if image_url:
    #                 #     try:
    #                 #         image_response = requests.get(image_url)
    #                 #         if image_response.status_code == 200:
    #                 #             odoo_product_data['image_1920'] = base64.b64encode(image_response.content)
    #                 #     except Exception as e:
    #                 #         logger.error(f"Failed to download image for product {product_name}: {e}")

                   
    #                 existing_product = self.env['product.template'].search([('hubspot_product_id', '=', product_id)], limit=1)
    #                 if existing_product:
                        
    #                     existing_product.write(odoo_product_data)
    #                 else:
                       
    #                     self.env['product.template'].create(odoo_product_data)
            
           
           
    #         logger.info('Products imported successfully in Odoo')  


    @api.model
    def _cron_import_products_from_hubspot(self):
        hubspot_instance_obj = self.env['hubspot.instance'].search([('active', '=', True), ('hubspot_is_import_products', '=', True)])
        for hubspot_instance in hubspot_instance_obj:
            self.import_products_from_hubspot(hubspot_instance)

    @api.model
    def import_products_from_hubspot(self, hubspot_instance):
        """This function is called from cron to import products from HubSpot with pagination support."""
        if hubspot_instance.active  and hubspot_instance.hubspot_is_import_products:
            url = "/crm/v3/objects/products?limit=100&properties=name,description,price,hs_sku,hs_product_type"
            logger.info('Starting product import from HubSpot')
            try:
                while url:
                    response = hubspot_instance._send_get_request(url)
                    json_response = json.loads(response)
                    products = json_response.get('results', [])

                    
                    for product in products:
                        product_data = self._prepare_product_data(product, hubspot_instance)
                        self._update_or_create_product(product_data)
                    
                    after = json_response.get('paging', {}).get('next', {}).get('after')
                    url = f"/crm/v3/objects/products?&after={after}&properties=name,description,price,hs_sku,hs_product_type" if after else None
                logger.info('Products imported successfully in Odoo')
                # Summary row in the HubSpot Logger (previously only written to the server log) ######
                self.env['hubspot.logger'].create_log_message('Import Products', 'Completed Getting All Products from HubSpot')
                
            except Exception as e:
                logger.error(f"Error during HubSpot product import: {e}")
                # Failures were silently swallowed; record them in the HubSpot Logger ######
                self.env['hubspot.logger'].create_log_message(
                    'Import Products', 'Error while importing products from HubSpot: %s' % e)

    @api.model
    def _prepare_product_data(self, product, hubspot_instance):
        """Prepare product data from HubSpot response to Odoo format."""
        product_id = product['id']
        product_name = product['properties'].get('name', '')
        hubspot_price = product['properties'].get('price', 0.0)
        product_default_code = product['properties'].get('hs_sku', '')
        hubspot_product_type = product['properties'].get('hs_product_type', 'consu')
        product_description = product['properties'].get('description', '')
        cleaned_description = re.sub(r'<[^>]*>', '', product_description) if product_description else ''
        
        product_type_mapping = {
            'inventory': 'consu',
            'non_inventory': 'consu',
            'service': 'service',
        }
        odoo_detailed_type = product_type_mapping.get(hubspot_product_type, 'consu')
        is_storable = hubspot_product_type == 'inventory'
        
        return {
            'hubspot_product_id': product_id,
            'name': product_name,
            'list_price': hubspot_price,
            'default_code': product_default_code,
            'type': odoo_detailed_type,
            'description_sale': cleaned_description,
            'hubspot_instance_id': hubspot_instance.id,
            'is_storable': is_storable,  
        }

    @api.model
    def _update_or_create_product(self, product_data):
        """Create or update the product in Odoo based on HubSpot data."""
        product_search = self.env['product.product'].search([('hubspot_product_id', '=', product_data['hubspot_product_id'])])
        
        if product_search:
            product_search.write(product_data)
            # One Success row per synced product (record details in the logger) ######
            self.env['hubspot.logger']._log_record_sync(product_search.product_tmpl_id, 'import', 'updated')
        else:
            new_product = self.env['product.product'].create(product_data)
            self.env['hubspot.logger']._log_record_sync(new_product.product_tmpl_id, 'import', 'created')


    
    
    
#########################################Update Products###################################################  
    
   
            
            
            
  
    
 
   

    
    
    
    
        
        
       
        
  