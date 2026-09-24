import csv
import io
import re
from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models, _

# Keywords used to classify log lines as Failed, checked first (case-insensitive) ######
HUBSPOT_LOG_FAILED_KEYWORDS = (
    'error', 'exception', 'failed', 'failure', 'invalid', 'traceback',
    'not enough api calls', 'skipping', 'unauthorized', 'forbidden',
)
# Keywords used to classify log lines as Success ######
HUBSPOT_LOG_SUCCESS_KEYWORDS = (
    'completed', 'successfully', 'success', 'done', 'created/updated', 'synced',
)
# Known typos in existing operation names, normalised only for display/grouping ######
HUBSPOT_LOG_OPERATION_FIXES = {
    'contacs': 'Contacts',
}
# Date ranges accepted by the dashboard ######
HUBSPOT_DASHBOARD_RANGES = ('today', '7d', '30d', 'month', 'all')
# Sort orders accepted by the dashboard (whitelist, never passed through raw) ######
HUBSPOT_DASHBOARD_ORDERS = {
    'hubspot_datetime desc': 'hubspot_datetime desc, id desc',
    'hubspot_datetime asc': 'hubspot_datetime asc, id asc',
}
# Fields sent to the dashboard list/timeline ######
HUBSPOT_DASHBOARD_FIELDS = [
    'hubspot_datetime', 'status', 'operation_label', 'operation_type', 'user_id',
    'hubspot_description', 'log_type', 'record_name', 'record_action', 'res_model',
    'res_id', 'hubspot_record_id', 'debug_logs',
]
# Markers that split an error description into request / response parts ######
HUBSPOT_REQUEST_MARKER = re.compile(r'(?:odoo\s+)?vals\s*:', re.IGNORECASE)
HUBSPOT_RESPONSE_MARKER = re.compile(r'hubspot\s+response\s*:?|exception\s*:', re.IGNORECASE)


class hubspotLogger(models.Model):
    _name = "hubspot.logger"
    _order = "id desc"
    _description = "Hubspot Loggers"

    hubspot_datetime = fields.Datetime('Hubspot DateTime', default=fields.Datetime.now, index=True)
    hubspot_user_id = fields.Char("User id", default=lambda self: self.env.user.id)
    hubspot_operation = fields.Char("Operation")
    hubspot_description = fields.Text("Description")
    debug_logs = fields.Boolean("Odoo Debug Logs", default=False)
    name = fields.Char("Name")

    # Success/Failed status: stored so it can be filtered/grouped, back-filled on upgrade ######
    status = fields.Selection(
        [('success', 'Success'), ('failed', 'Failed')],
        string="Status", compute='_compute_status', store=True, readonly=False, index=True,
    )
    # Import/Export direction derived from the operation name ######
    operation_type = fields.Selection(
        [('import', 'Import'), ('export', 'Export'), ('other', 'Other')],
        string="Sync Type", compute='_compute_operation_details', store=True, index=True,
    )
    # Normalised operation name so 'Import note' and 'Import Note' group together ######
    operation_label = fields.Char(
        string="Operation Name", compute='_compute_operation_details', store=True,
    )
    # Real user record resolved from the legacy Char user id ######
    user_id = fields.Many2one(
        'res.users', string="User", compute='_compute_user_id', store=True,
    )

    # Per-record sync details, filled only for record-level success logs ######
    res_model = fields.Char("Record Model", index=True, readonly=True)
    res_id = fields.Many2oneReference("Record ID", model_field='res_model', readonly=True)
    record_name = fields.Char("Record Name", readonly=True)
    hubspot_record_id = fields.Char("HubSpot Record ID", index=True, readonly=True)
    # Instance of the synced record, used by the HubSpot Instance overview ######
    hubspot_instance_id = fields.Many2one('hubspot.instance', string="HubSpot Instance", index=True,
                                          readonly=True, ondelete='set null')
    record_action = fields.Selection(
        [('created', 'Created in Odoo'), ('updated', 'Updated in Odoo'),
         ('exported', 'Exported to HubSpot'), ('export_updated', 'Updated in HubSpot')],
        string="Record Action", readonly=True,
    )
    # Log category used by the dashboard filters and badges ######
    log_type = fields.Selection(
        [('record', 'Record Sync'), ('summary', 'Sync Summary'),
         ('error', 'Error Log'), ('debug', 'Debug Log')],
        string="Log Type", compute='_compute_log_type', store=True, index=True,
    )

    @api.model
    def _detect_log_status(self, description):
        # Classify a log description; unknown text is treated as failed (only raw API dumps hit this) ######
        text = (description or '').lower()
        if any(keyword in text for keyword in HUBSPOT_LOG_FAILED_KEYWORDS):
            return 'failed'
        if any(keyword in text for keyword in HUBSPOT_LOG_SUCCESS_KEYWORDS):
            return 'success'
        return 'failed'

    @api.depends('hubspot_description')
    def _compute_status(self):
        for log in self:
            log.status = self._detect_log_status(log.hubspot_description)

    @api.depends('hubspot_operation')
    def _compute_operation_details(self):
        for log in self:
            words = []
            for word in (log.hubspot_operation or '').split():
                fixed = HUBSPOT_LOG_OPERATION_FIXES.get(word.lower())
                words.append(fixed or (word[:1].upper() + word[1:]))
            label = ' '.join(words)
            first_word = label.split(' ')[0].lower() if label else ''
            if first_word in ('import', 'getting'):
                operation_type = 'import'
            elif first_word == 'export':
                operation_type = 'export'
            else:
                operation_type = 'other'
            log.operation_label = label or _('Undefined')
            log.operation_type = operation_type

    @api.depends('hubspot_user_id')
    def _compute_user_id(self):
        # Batch the existence check so upgrade back-fill does one query, not one per log ######
        user_ids = {
            int(value) for value in self.mapped('hubspot_user_id')
            if value and str(value).strip().isdigit()
        }
        existing_ids = set(self.env['res.users'].browse(list(user_ids)).exists().ids)
        for log in self:
            value = (log.hubspot_user_id or '').strip()
            user_id = int(value) if value.isdigit() else False
            log.user_id = user_id if user_id in existing_ids else False

    @api.depends('debug_logs', 'res_model', 'status')
    def _compute_log_type(self):
        for log in self:
            if log.debug_logs:
                log.log_type = 'debug'
            elif log.res_model:
                log.log_type = 'record'
            elif log.status == 'failed':
                log.log_type = 'error'
            else:
                log.log_type = 'summary'

    def create_log_message(self, hubspot_operation, hubspot_description, is_debug=False, status=None):
        # Optional explicit status; when omitted it is auto-detected from the description ######
        extra_vals = {}
        if status in ('success', 'failed'):
            extra_vals['status'] = status
        if is_debug:
            self.env['hubspot.logger'].create(dict({
                'hubspot_operation': hubspot_operation,
                'hubspot_description': hubspot_description,
                'debug_logs': True
            }, **extra_vals))
            self.env.cr.commit()
        else:
            self.env['hubspot.logger'].create(dict({
                'hubspot_operation': hubspot_operation,
                'hubspot_description': hubspot_description,
            }, **extra_vals))
            self.env.cr.commit()
        return True

    # ------------------------------------------------------------------ ######
    # Record-level success logging (called from hubspot.record.sync.mixin) ######
    # ------------------------------------------------------------------ ######

    @api.model
    def _log_record_sync(self, records, direction, action, vals_by_id=None):
        """Create one Success log per synced record, without committing. ######"""
        if not records:
            return
        # Avoid duplicate rows when the same record is written several times in one transaction ######
        seen = self.env.cr.precommit.data.setdefault('hubspot.logger.synced_records', set())
        verb = {
            'created': _('created in Odoo from HubSpot'),
            'updated': _('updated in Odoo from HubSpot'),
            'exported': _('exported to HubSpot'),
            'export_updated': _('synced to HubSpot'),
        }[action]
        vals_list = []
        for record in records:
            key = (record._name, record.id, direction)
            if key in seen:
                continue
            seen.add(key)
            label, plural = record._hubspot_log_labels((vals_by_id or {}).get(record.id))
            target_model, target_id = record._hubspot_log_target()
            name = record._hubspot_log_name()
            hubspot_id = record._hubspot_log_hubspot_id() or ''
            operation = '%s %s' % (_('Import') if direction == 'import' else _('Export'), plural)
            description = _("%(subject)s was %(verb)s successfully.\nHubSpot ID: %(hid)s\nOdoo ID: %(oid)s") % {
                'subject': record._hubspot_log_subject(label, name), 'verb': verb,
                'hid': hubspot_id or '-', 'oid': target_id,
            }
            record_vals = (vals_by_id or {}).get(record.id) or {}
            instance = record['hubspot_instance_id'] if 'hubspot_instance_id' in record._fields else False
            instance_id = (instance.id if instance else False) or record_vals.get('hubspot_instance_id') or False
            vals_list.append({
                'hubspot_operation': operation,
                'hubspot_description': description,
                'status': 'success',
                'res_model': target_model,
                'res_id': target_id,
                'record_name': name,
                'hubspot_record_id': hubspot_id,
                'record_action': action,
                'hubspot_instance_id': instance_id,
            })
        if vals_list:
            # sudo: logging is a side effect of the sync and must not fail on logger ACLs ######
            self.sudo().create(vals_list)

    # ------------------------------------------------------------------ ######
    # Dashboard API (read-only, runs with the caller's access rights) ######
    # ------------------------------------------------------------------ ######

    @api.model
    def _dashboard_range_bounds(self, date_range):
        """Return (start, previous_start, now) in naive UTC for the selected range. ######"""
        now_utc = fields.Datetime.now()
        if date_range not in HUBSPOT_DASHBOARD_RANGES or date_range == 'all':
            return False, False, now_utc
        tz = pytz.timezone(self.env.context.get('tz') or self.env.user.tz or 'UTC')
        today_local = pytz.utc.localize(now_utc).astimezone(tz).date()
        if date_range == 'today':
            start_date = today_local
        elif date_range == '7d':
            start_date = today_local - timedelta(days=6)
        elif date_range == '30d':
            start_date = today_local - timedelta(days=29)
        else:
            start_date = today_local.replace(day=1)
        start_utc = tz.localize(datetime.combine(start_date, time.min)).astimezone(pytz.utc).replace(tzinfo=None)
        previous_start = start_utc - (now_utc - start_utc)
        return start_utc, previous_start, now_utc

    @api.model
    def _dashboard_domain(self, filters, with_range=True):
        """Build a safe domain from dashboard filters (all values validated). ######"""
        filters = filters or {}
        domain = []
        search = (filters.get('search') or '').strip()
        if search:
            domain += ['|', '|', '|',
                       ('hubspot_description', 'ilike', search),
                       ('operation_label', 'ilike', search),
                       ('record_name', 'ilike', search),
                       ('hubspot_record_id', 'ilike', search)]
        operation = filters.get('operation')
        if operation and isinstance(operation, str):
            domain.append(('operation_label', '=', operation))
        if filters.get('status') in ('success', 'failed'):
            domain.append(('status', '=', filters['status']))
        if filters.get('log_type') in ('record', 'summary', 'error', 'debug'):
            domain.append(('log_type', '=', filters['log_type']))
        user_id = filters.get('user_id')
        if user_id and str(user_id).isdigit():
            domain.append(('user_id', '=', int(user_id)))
        if with_range:
            start, _previous, _now = self._dashboard_range_bounds(filters.get('date_range'))
            if start:
                domain.append(('hubspot_datetime', '>=', start))
        return domain

    @api.model
    def _dashboard_kpis(self, date_range):
        start, previous_start, _now = self._dashboard_range_bounds(date_range)
        kpi_domains = {
            'total': [],
            'success': [('status', '=', 'success')],
            'failed': [('status', '=', 'failed')],
            'debug': [('debug_logs', '=', True)],
        }
        kpis = {}
        for key, extra in kpi_domains.items():
            current_domain = extra + ([('hubspot_datetime', '>=', start)] if start else [])
            value = self.search_count(current_domain)
            trend = False
            if start:
                previous = self.search_count(extra + [
                    ('hubspot_datetime', '>=', previous_start),
                    ('hubspot_datetime', '<', start),
                ])
                if previous:
                    trend = round((value - previous) * 100.0 / previous)
            kpis[key] = {'value': value, 'trend': trend}
        return kpis

    @api.model
    def get_dashboard_data(self, filters=None, offset=0, limit=20, order=None):
        """Single RPC for the dashboard: rows, total, KPI cards and filter options. ######"""
        filters = filters or {}
        limit = min(max(int(limit or 20), 1), 200)
        offset = max(int(offset or 0), 0)
        order_sql = HUBSPOT_DASHBOARD_ORDERS.get(order, HUBSPOT_DASHBOARD_ORDERS['hubspot_datetime desc'])
        domain = self._dashboard_domain(filters)
        operations = [
            label for (label,) in self._read_group([('operation_label', '!=', False)], ['operation_label'])
        ]
        users = [
            {'id': user.id, 'name': user.display_name}
            for (user,) in self._read_group([('user_id', '!=', False)], ['user_id'])
        ]
        return {
            'records': self.search_read(domain, HUBSPOT_DASHBOARD_FIELDS, offset=offset, limit=limit, order=order_sql),
            'total': self.search_count(domain),
            'kpis': self._dashboard_kpis(filters.get('date_range')),
            'operations': sorted(operations, key=lambda label: label.lower()),
            'users': sorted(users, key=lambda user: user['name'].lower()),
        }

    @api.model
    def _split_description(self, text):
        """Split 'summary / Odoo vals / HubSpot response' style descriptions. ######"""
        text = text or ''
        request_match = HUBSPOT_REQUEST_MARKER.search(text)
        response_match = HUBSPOT_RESPONSE_MARKER.search(text)
        if response_match and request_match and request_match.start() > response_match.start():
            request_match = False
        first_marker = min(
            [match.start() for match in (request_match, response_match) if match] or [len(text)]
        )
        summary = text[:first_marker].strip()
        request = ''
        if request_match:
            request_end = response_match.start() if response_match else len(text)
            request = text[request_match.end():request_end].strip()
        response = text[response_match.end():].strip() if response_match else ''
        return summary or text.strip(), request, response

    @api.model
    def get_log_details(self, log_id):
        """Full detail payload for the side panel of one log. ######"""
        log = self.browse(int(log_id)).exists()
        if not log:
            return False
        data = log.read(HUBSPOT_DASHBOARD_FIELDS + ['hubspot_operation', 'hubspot_user_id'])[0]
        summary, request, response = self._split_description(log.hubspot_description)
        can_open = False
        model_label = ''
        if log.res_model and log.res_id and log.res_model in self.env:
            model_label = self.env[log.res_model]._description
            can_open = bool(self.env[log.res_model].browse(log.res_id).exists())
        timeline_domain = [('hubspot_datetime', '<=', log.hubspot_datetime)] if log.hubspot_datetime else []
        data.update({
            'summary': summary,
            'request': request,
            'response': response,
            'can_open': can_open,
            'model_label': model_label,
            'timeline': self.search_read(
                timeline_domain,
                ['hubspot_datetime', 'status', 'operation_label', 'log_type'],
                limit=6, order='hubspot_datetime desc, id desc',
            ),
        })
        return data

    @api.model
    def export_logs_csv(self, filters=None, ids=None):
        """CSV export of selected ids, or of all logs matching the filters (max 50,000). ######"""
        if ids:
            domain = [('id', 'in', [int(log_id) for log_id in ids])]
        else:
            domain = self._dashboard_domain(filters or {})
        logs = self.search(domain, limit=50000, order='hubspot_datetime desc, id desc')
        status_labels = dict(self._fields['status']._description_selection(self.env))
        type_labels = dict(self._fields['log_type']._description_selection(self.env))
        sync_labels = dict(self._fields['operation_type']._description_selection(self.env))
        action_labels = dict(self._fields['record_action']._description_selection(self.env))
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow([
            _('Date & Time'), _('Status'), _('Log Type'), _('Operation'), _('Sync Type'),
            _('User'), _('Record'), _('Record Action'), _('HubSpot ID'), _('Description'),
        ])
        for log in logs:
            local_dt = fields.Datetime.context_timestamp(self, log.hubspot_datetime) if log.hubspot_datetime else False
            writer.writerow([
                local_dt.strftime('%Y-%m-%d %H:%M:%S') if local_dt else '',
                status_labels.get(log.status, ''),
                type_labels.get(log.log_type, ''),
                log.operation_label or '',
                sync_labels.get(log.operation_type, ''),
                log.user_id.display_name or '',
                log.record_name or '',
                action_labels.get(log.record_action, ''),
                log.hubspot_record_id or '',
                log.hubspot_description or '',
            ])
        return {
            'filename': 'hubspot_logs_%s.csv' % fields.Datetime.now().strftime('%Y%m%d_%H%M%S'),
            'content': buffer.getvalue(),
        }
