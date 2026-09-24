from odoo import api, models, _

# Keys written by export code when only the HubSpot id is linked back to Odoo ######
HUBSPOT_EXPORT_WRITE_KEYS = {'hubspot_id', 'hubspot_instance_id'}


class HubspotRecordSyncMixin(models.AbstractModel):
    """Logs one Success row per record synced with HubSpot.

    Imports create records with context from_hubspot=True and 'hubspot_id' in vals;
    exports write only {'hubspot_id'} (and 'hubspot_instance_id') with the same context.
    Hooking create/write here avoids editing the ~100 import/export call sites. ######
    """
    _name = 'hubspot.record.sync.mixin'
    _description = 'HubSpot Record Sync Logging'

    def _hubspot_log_labels(self, vals=None):
        # (singular, plural) label shown in the operation name and description ######
        self.ensure_one()
        return _('Record'), _('Records')

    def _hubspot_log_subject(self, label, name):
        # Subject line of the log description, e.g. "Contact 'John Doe'" ######
        return "%s '%s'" % (label, name)

    def _hubspot_log_target(self):
        # Record opened by the dashboard "View Record" button ######
        self.ensure_one()
        return self._name, self.id

    def _hubspot_log_name(self):
        self.ensure_one()
        return self.display_name or '#%s' % self.id

    @api.model
    def _hubspot_log_id_field(self):
        # Field holding the HubSpot id on this model (products and quotes use their own field) ######
        return 'hubspot_id'

    def _hubspot_log_hubspot_id(self):
        self.ensure_one()
        return self[self._hubspot_log_id_field()]

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if self.env.context.get('from_hubspot'):
            vals_by_id = {
                record.id: vals for record, vals in zip(records, vals_list) if vals.get(self._hubspot_log_id_field())
            }
            self.env['hubspot.logger']._log_record_sync(
                self.browse(list(vals_by_id)), 'import', 'created', vals_by_id,
            )
        return records

    def write(self, vals):
        if not self.env.context.get('from_hubspot') or not vals:
            return super().write(vals)
        keys = set(vals)
        id_field = self._hubspot_log_id_field()
        is_export_link = id_field in keys and keys <= (HUBSPOT_EXPORT_WRITE_KEYS | {id_field})
        previous_ids = {record.id: record[id_field] for record in self} if is_export_link else {}
        result = super().write(vals)
        logger = self.env['hubspot.logger']
        if is_export_link:
            new_records = self.filtered(lambda record: not previous_ids.get(record.id))
            logger._log_record_sync(new_records, 'export', 'exported')
            logger._log_record_sync(self - new_records, 'export', 'export_updated')
        elif not keys <= (HUBSPOT_EXPORT_WRITE_KEYS | {id_field}):
            # Inbound update: only records actually linked to HubSpot are logged ######
            logger._log_record_sync(self.filtered(id_field), 'import', 'updated')
        return result


class ResPartner(models.Model):
    _name = 'res.partner'
    _inherit = ['res.partner', 'hubspot.record.sync.mixin']

    def _hubspot_log_labels(self, vals=None):
        self.ensure_one()
        # Odoo 20 computes is_company from the VAT, so prefer the value the import sent ######
        is_company = vals['is_company'] if vals and 'is_company' in vals else self.is_company
        if is_company:
            return _('Company'), _('Companies')
        return _('Contact'), _('Contacts')


class CrmLead(models.Model):
    _name = 'crm.lead'
    _inherit = ['crm.lead', 'hubspot.record.sync.mixin']

    def _hubspot_log_labels(self, vals=None):
        self.ensure_one()
        if self.type == 'opportunity':
            return _('Deal'), _('Deals')
        return _('Lead'), _('Leads')


class MailMessage(models.Model):
    _name = 'mail.message'
    _inherit = ['mail.message', 'hubspot.record.sync.mixin']

    def _hubspot_log_labels(self, vals=None):
        # Singular operation names match the existing 'Import Note' / 'Import Email' logs ######
        self.ensure_one()
        if self.message_type == 'email':
            return _('Email'), _('Email')
        return _('Note'), _('Note')

    def _hubspot_log_subject(self, label, name):
        return _("%(label)s on '%(name)s'") % {'label': label, 'name': name}

    def _hubspot_log_target(self):
        # Open the document the note/email is posted on, not the raw message ######
        self.ensure_one()
        if self.model and self.res_id:
            return self.model, self.res_id
        return self._name, self.id

    def _hubspot_log_name(self):
        self.ensure_one()
        return self.record_name or self.subject or '#%s' % self.id


class MailActivity(models.Model):
    _name = 'mail.activity'
    _inherit = ['mail.activity', 'hubspot.record.sync.mixin']

    def _hubspot_log_labels(self, vals=None):
        # Singular operation name matches the existing 'Export Activity' logs ######
        self.ensure_one()
        return _('Activity'), _('Activity')

    def _hubspot_log_subject(self, label, name):
        return _("%(label)s on '%(name)s'") % {'label': label, 'name': name}

    def _hubspot_log_target(self):
        # Activities are deleted when marked done, so link to their document ######
        self.ensure_one()
        if self.res_model and self.res_id:
            return self.res_model, self.res_id
        return self._name, self.id

    def _hubspot_log_name(self):
        self.ensure_one()
        return self.res_name or self.summary or self.activity_type_id.name or '#%s' % self.id


class CalendarEvent(models.Model):
    _name = 'calendar.event'
    _inherit = ['calendar.event', 'hubspot.record.sync.mixin']

    def _hubspot_log_labels(self, vals=None):
        # Singular operation name matches the existing 'Import Meeting' / 'Export Meeting' logs ######
        self.ensure_one()
        return _('Meeting'), _('Meeting')


class ProductTemplate(models.Model):
    _name = 'product.template'
    _inherit = ['product.template', 'hubspot.record.sync.mixin']

    def _hubspot_log_labels(self, vals=None):
        # Singular operation name matches the 'Import Products' summary logs ######
        self.ensure_one()
        return _('Product'), _('Products')

    def _hubspot_log_hubspot_id(self):
        # The product import stores the HubSpot id in hubspot_product_id ######
        self.ensure_one()
        return self.hubspot_product_id or self.hubspot_id


class SaleOrder(models.Model):
    _name = 'sale.order'
    _inherit = ['sale.order', 'hubspot.record.sync.mixin']

    def _hubspot_log_labels(self, vals=None):
        self.ensure_one()
        return _('Quote'), _('Quotes')

    @api.model
    def _hubspot_log_id_field(self):
        # sale.order has no hubspot_id; the quote import uses hubspot_sale_order_id ######
        return 'hubspot_sale_order_id'
