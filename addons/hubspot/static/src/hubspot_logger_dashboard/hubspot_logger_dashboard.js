import { Component, onMounted, onWillStart, onWillUnmount, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { browser } from "@web/core/browser/browser";
import { deserializeDateTime } from "@web/core/l10n/dates";
import { _t } from "@web/core/l10n/translation";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

// Badge/label metadata; icons are Odoo 20 odoo_ui_icons (Material Symbols) names ######
const STATUS_META = {
    success: { label: _t("Success"), cls: "o_hs_badge_success", icon: "check_circle" },
    failed: { label: _t("Failed"), cls: "o_hs_badge_danger", icon: "cancel" },
};
const LOG_TYPE_META = {
    record: { label: _t("Record Sync"), cls: "o_hs_tag_info", icon: "autorenew" },
    summary: { label: _t("Sync Summary"), cls: "o_hs_tag_success", icon: "list_alt" },
    error: { label: _t("Error Log"), cls: "o_hs_tag_danger", icon: "bug_report" },
    debug: { label: _t("Debug Log"), cls: "o_hs_tag_purple", icon: "code" },
};
const RECORD_ACTION_LABELS = {
    created: _t("Created in Odoo"),
    updated: _t("Updated in Odoo"),
    exported: _t("Exported to HubSpot"),
    export_updated: _t("Updated in HubSpot"),
};
const DATE_RANGES = [
    { key: "today", label: _t("Today") },
    { key: "7d", label: _t("Last 7 Days") },
    { key: "30d", label: _t("Last 30 Days") },
    { key: "month", label: _t("This Month") },
    { key: "all", label: _t("All Time") },
];
const DEFAULT_FILTERS = {
    search: "",
    operation: "",
    status: "",
    user_id: "",
    log_type: "",
    date_range: "7d",
};

export class HubspotLoggerDashboard extends Component {
    static template = "hubspot.LoggerDashboard";
    // Owl 3 (Odoo 20): props are declared with useProps, not a static schema ######
    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.statusMeta = STATUS_META;
        this.logTypeMeta = LOG_TYPE_META;
        this.recordActionLabels = RECORD_ACTION_LABELS;
        this.dateRanges = DATE_RANGES;
        // Owl 3 (Odoo 20): proxy() replaces useState() ######
        this.state = proxy({
            loading: false,
            records: [],
            total: 0,
            kpis: {},
            operations: [],
            users: [],
            filters: { ...DEFAULT_FILTERS },
            order: "hubspot_datetime desc",
            page: 1,
            limit: 20,
            view: "list",
            showFilters: true,
            rangeMenuOpen: false,
            rowMenuId: false,
            selected: {},
            activeId: false,
            details: false,
            detailsLoading: false,
            sections: { technical: true, request: false, response: false, error: true },
        });
        this.searchTimer = false;
        // Close open menus on any outside click ######
        this.onDocumentClick = () => {
            this.state.rangeMenuOpen = false;
            this.state.rowMenuId = false;
        };
        onWillStart(() => this.loadData());
        onMounted(() => document.addEventListener("click", this.onDocumentClick));
        onWillUnmount(() => {
            document.removeEventListener("click", this.onDocumentClick);
            browser.clearTimeout(this.searchTimer);
        });
    }

    // ---------------------------------------------------------------- ######
    // Data loading ######
    // ---------------------------------------------------------------- ######

    get filterPayload() {
        const filters = this.state.filters;
        return {
            search: filters.search,
            operation: filters.operation,
            status: filters.status,
            user_id: filters.user_id ? parseInt(filters.user_id) : false,
            log_type: filters.log_type,
            date_range: filters.date_range,
        };
    }

    async loadData() {
        this.state.loading = true;
        try {
            const result = await this.orm.call("hubspot.logger", "get_dashboard_data", [], {
                filters: this.filterPayload,
                offset: (this.state.page - 1) * this.state.limit,
                limit: this.state.limit,
                order: this.state.order,
            });
            this.state.records = result.records;
            this.state.total = result.total;
            this.state.kpis = result.kpis;
            this.state.operations = result.operations;
            this.state.users = result.users;
        } finally {
            this.state.loading = false;
        }
    }

    async reload(resetPage = true) {
        if (resetPage) {
            this.state.page = 1;
        }
        this.state.selected = {};
        await this.loadData();
    }

    async openDetails(logId) {
        this.state.activeId = logId;
        this.state.detailsLoading = true;
        try {
            this.state.details = await this.orm.call("hubspot.logger", "get_log_details", [logId]);
            this.state.sections.error = this.state.details && this.state.details.status === "failed";
        } finally {
            this.state.detailsLoading = false;
        }
    }

    closeDetails() {
        this.state.activeId = false;
        this.state.details = false;
    }

    // ---------------------------------------------------------------- ######
    // Filters, sorting, pagination ######
    // ---------------------------------------------------------------- ######

    setFilter(name, value) {
        this.state.filters[name] = value;
        this.reload();
    }

    onSearchInput(ev) {
        this.state.filters.search = ev.target.value;
        browser.clearTimeout(this.searchTimer);
        this.searchTimer = browser.setTimeout(() => this.reload(), 350);
    }

    clearFilters() {
        this.state.filters = { ...DEFAULT_FILTERS, date_range: this.state.filters.date_range };
        this.reload();
    }

    get hasActiveFilters() {
        const f = this.state.filters;
        return Boolean(f.search || f.operation || f.status || f.user_id || f.log_type);
    }

    toggleRangeMenu() {
        this.state.rowMenuId = false;
        this.state.rangeMenuOpen = !this.state.rangeMenuOpen;
    }

    selectRange(key) {
        this.state.rangeMenuOpen = false;
        this.setFilter("date_range", key);
    }

    get currentRangeLabel() {
        const range = DATE_RANGES.find((r) => r.key === this.state.filters.date_range);
        return range ? range.label : "";
    }

    toggleSort() {
        this.state.order =
            this.state.order === "hubspot_datetime desc" ? "hubspot_datetime asc" : "hubspot_datetime desc";
        this.reload();
    }

    setKpiFilter(key) {
        // Clicking a KPI card applies the matching filter ######
        const filters = this.state.filters;
        filters.status = "";
        filters.log_type = "";
        if (key === "success" || key === "failed") {
            filters.status = key;
        } else if (key === "debug") {
            filters.log_type = "debug";
        }
        this.reload();
    }

    get pageCount() {
        return Math.max(1, Math.ceil(this.state.total / this.state.limit));
    }

    get pageItems() {
        const count = this.pageCount;
        const current = this.state.page;
        const pages = new Set([1, count, current - 1, current, current + 1]);
        const sorted = [...pages].filter((p) => p >= 1 && p <= count).sort((a, b) => a - b);
        const items = [];
        let previous = 0;
        for (const page of sorted) {
            if (page - previous > 1) {
                items.push({ key: `gap-${page}`, gap: true });
            }
            items.push({ key: `page-${page}`, page });
            previous = page;
        }
        return items;
    }

    goToPage(page) {
        if (page < 1 || page > this.pageCount || page === this.state.page) {
            return;
        }
        this.state.page = page;
        this.state.selected = {};
        this.loadData();
    }

    get rangeStart() {
        return this.state.total ? (this.state.page - 1) * this.state.limit + 1 : 0;
    }

    get rangeEnd() {
        return Math.min(this.state.page * this.state.limit, this.state.total);
    }

    // ---------------------------------------------------------------- ######
    // Selection and row actions ######
    // ---------------------------------------------------------------- ######

    get selectedIds() {
        return Object.keys(this.state.selected)
            .filter((id) => this.state.selected[id])
            .map((id) => parseInt(id));
    }

    get allSelected() {
        return this.state.records.length > 0 && this.state.records.every((r) => this.state.selected[r.id]);
    }

    toggleSelect(logId) {
        this.state.selected[logId] = !this.state.selected[logId];
    }

    toggleSelectAll() {
        const value = !this.allSelected;
        for (const record of this.state.records) {
            this.state.selected[record.id] = value;
        }
    }

    toggleRowMenu(logId) {
        this.state.rangeMenuOpen = false;
        this.state.rowMenuId = this.state.rowMenuId === logId ? false : logId;
    }

    async openRecord(resModel, resId) {
        this.state.rowMenuId = false;
        if (!resModel || !resId) {
            return;
        }
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: resModel,
            res_id: resId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    async openLogForm(logId) {
        this.state.rowMenuId = false;
        await this.openRecord("hubspot.logger", logId);
    }

    async openClassicView() {
        await this.action.doAction("hubspot.hubspot_logger_action");
    }

    async exportLogs() {
        const ids = this.selectedIds;
        const result = await this.orm.call("hubspot.logger", "export_logs_csv", [], {
            filters: this.filterPayload,
            ids: ids.length ? ids : false,
        });
        const blob = new Blob(["\ufeff" + result.content], { type: "text/csv;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = result.filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
    }

    async copyText(text, message) {
        try {
            await browser.navigator.clipboard.writeText(text === undefined || text === null ? "" : String(text));
            this.notification.add(message || _t("Copied to clipboard"), { type: "success" });
        } catch {
            this.notification.add(_t("Could not access the clipboard"), { type: "warning" });
        }
    }

    copyDetails() {
        const d = this.state.details;
        if (!d) {
            return;
        }
        const lines = [
            `${_t("Status")}: ${this.statusLabel(d.status)}`,
            `${_t("Operation")}: ${d.operation_label || ""}`,
            `${_t("Date & Time")}: ${this.formatDate(d.hubspot_datetime)} ${this.formatTime(d.hubspot_datetime)}`,
            `${_t("User")}: ${d.user_id ? d.user_id[1] : "-"}`,
            `${_t("Log Type")}: ${this.logTypeLabel(d.log_type)}`,
        ];
        if (d.res_model) {
            lines.push(
                `${_t("Record")}: ${d.record_name || ""} (${d.model_label || d.res_model} #${d.res_id})`,
                `${_t("Record Action")}: ${RECORD_ACTION_LABELS[d.record_action] || ""}`,
                `${_t("HubSpot ID")}: ${d.hubspot_record_id || "-"}`
            );
        }
        lines.push("", d.hubspot_description || "");
        this.copyText(lines.join("\n"), _t("Log details copied"));
    }

    noop() {}

    toggleFilters() {
        this.state.showFilters = !this.state.showFilters;
    }

    viewDetailsFromMenu(logId) {
        this.state.rowMenuId = false;
        this.openDetails(logId);
    }

    copyFromMenu(text) {
        this.state.rowMenuId = false;
        this.copyText(text);
    }

    isUserSelected(userId) {
        return String(this.state.filters.user_id) === String(userId);
    }

    trendAbs(value) {
        return Math.abs(value || 0);
    }

    get logTypeKeys() {
        return Object.keys(LOG_TYPE_META);
    }

    toggleSection(name) {
        this.state.sections[name] = !this.state.sections[name];
    }

    setView(view) {
        this.state.view = view;
    }

    // ---------------------------------------------------------------- ######
    // Formatting helpers ######
    // ---------------------------------------------------------------- ######

    formatDate(value) {
        return value ? deserializeDateTime(value).toFormat("dd LLL yyyy") : "";
    }

    formatTime(value) {
        return value ? deserializeDateTime(value).toFormat("hh:mm a") : "";
    }

    formatNumber(value) {
        return (value || 0).toLocaleString();
    }

    statusLabel(status) {
        return (STATUS_META[status] || {}).label || "-";
    }

    logTypeLabel(logType) {
        return (LOG_TYPE_META[logType] || {}).label || "-";
    }

    avatarUrl(user) {
        return user ? `/web/image/res.users/${user[0]}/avatar_128` : "";
    }

    get timelineGroups() {
        const groups = [];
        let current = false;
        for (const record of this.state.records) {
            const key = this.formatDate(record.hubspot_datetime);
            if (!current || current.key !== key) {
                current = { key, items: [] };
                groups.push(current);
            }
            current.items.push(record);
        }
        return groups;
    }

    get kpiCards() {
        const kpis = this.state.kpis || {};
        return [
            { key: "total", title: _t("Total Logs"), subtitle: _t("All integration activities"), icon: "description", cls: "o_hs_kpi_primary", data: kpis.total || {} },
            { key: "success", title: _t("Successful Operations"), subtitle: _t("Completed successfully"), icon: "check", cls: "o_hs_kpi_success", data: kpis.success || {} },
            { key: "failed", title: _t("Failed Operations"), subtitle: _t("Requires attention"), icon: "close", cls: "o_hs_kpi_danger", data: kpis.failed || {} },
            { key: "debug", title: _t("Debug Logs"), subtitle: _t("Development & diagnostic events"), icon: "bug_report", cls: "o_hs_kpi_warning", data: kpis.debug || {} },
        ];
    }
}

registry.category("actions").add("hubspot_logger_dashboard", HubspotLoggerDashboard);
