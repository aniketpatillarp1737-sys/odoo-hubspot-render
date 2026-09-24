import { Component, onPatched, onWillStart, proxy, t, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { deserializeDateTime } from "@web/core/l10n/dates";
import { _t } from "@web/core/l10n/translation";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

// Icons are Odoo 20 odoo_ui_icons (Material Symbols) names ######
const KPI_ICONS = {
    contacts: "group",
    companies: "business",
    deals: "handshake",
    products: "inventory_2",
};
const STATUS_ICONS = {
    success: "check_circle",
    failed: "cancel",
};
const RECORD_ACTION_LABELS = {
    created: _t("Created in Odoo"),
    updated: _t("Updated in Odoo"),
    exported: _t("Exported to HubSpot"),
    export_updated: _t("Updated in HubSpot"),
};

/**
 * Form view widget for hubspot.instance.
 * mode="kpis"     -> record counts + "synced today" cards ######
 * mode="activity" -> recent sync activity with synced record details ######
 */
export class HubspotInstanceOverview extends Component {
    static template = "hubspot.InstanceOverview";
    // Owl 3 (Odoo 20): props are declared with useProps ######
    props = useProps({
        ...standardWidgetProps,
        mode: t.string().optional("kpis"),
        entity: t.string().optional("all"),
        limit: t.number().optional(6),
        title: t.string().optional(""),
        subtitle: t.string().optional(""),
    });

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.recordActionLabels = RECORD_ACTION_LABELS;
        this.state = proxy({ loading: false, data: false });
        this.loadedKey = false;
        onWillStart(() => this.load());
        // Reload after the record is saved or a sync button ran (write_date changes) ######
        onPatched(() => {
            if (this.recordKey !== this.loadedKey) {
                this.load();
            }
        });
    }

    get recordKey() {
        const record = this.props.record;
        return `${record.resId || ""}|${record.data.write_date || ""}`;
    }

    async load() {
        this.loadedKey = this.recordKey;
        const resId = this.props.record.resId;
        if (!resId) {
            this.state.data = false;
            return;
        }
        this.state.loading = true;
        try {
            this.state.data = await this.orm.call("hubspot.instance", "get_instance_overview", [[resId]], {
                entity: this.props.entity,
                limit: this.props.limit,
            });
        } finally {
            this.state.loading = false;
        }
    }

    kpiIcon(key) {
        return KPI_ICONS[key] || "database";
    }

    statusIcon(status) {
        return STATUS_ICONS[status] || "info";
    }

    formatNumber(value) {
        return value === false ? "-" : (value || 0).toLocaleString();
    }

    formatDate(value) {
        return value ? deserializeDateTime(value).toFormat("dd LLL, hh:mm a") : "";
    }

    async openKpi(kpi) {
        if (kpi.count === false) {
            return;
        }
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: kpi.label,
            res_model: kpi.model,
            domain: kpi.domain,
            views: [[false, "list"], [false, "form"]],
            target: "current",
        });
    }

    async openActivity(log) {
        const hasRecord = log.res_model && log.res_id;
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: hasRecord ? log.res_model : "hubspot.logger",
            res_id: hasRecord ? log.res_id : log.id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    async openAllActivity() {
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: this.props.title || _t("HubSpot Logs"),
            res_model: "hubspot.logger",
            domain: this.state.data ? this.state.data.activity_domain : [],
            views: [[false, "list"], [false, "form"]],
            target: "current",
        });
    }
}

export const hubspotInstanceOverview = {
    component: HubspotInstanceOverview,
    extractProps: ({ attrs }) => ({
        mode: attrs.mode || "kpis",
        entity: attrs.entity || "all",
        limit: attrs.limit ? parseInt(attrs.limit) : 6,
        title: attrs.title || "",
        subtitle: attrs.subtitle || "",
    }),
};

registry.category("view_widgets").add("hubspot_instance_overview", hubspotInstanceOverview);
