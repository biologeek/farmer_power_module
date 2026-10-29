import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { useSetupAction } from "@web/search/action_hook";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const DAY = 24 * 3600 * 1000;
const LANE_HEIGHT = 36;

/**
 * Plan de culture : Gantt d'occupation des planches (sans dépendance Enterprise).
 *
 * Une ligne par planche, regroupées par îlot ; chaque culture affiche une barre prévue (hachurée,
 * semis -> fin de récolte) et une barre réalisée (pleine). Couleur selon la famille botanique.
 * Un clic sur une barre ouvre la fiche de la culture.
 */
class GardenBedOccupancyAction extends Component {
    static template = "garden.GardenBedOccupancy";
    static components = { Layout };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.state = useState({
            groups: [],
            families: [],
            seasons: [],
            sites: [],
            startDate: false,
            endDate: false,
            today: false,
            seasonId: false,
            siteId: false,
            hideEmpty: false,
        });
        useSetupAction({
            getLocalState: () => ({
                seasonId: this.state.seasonId,
                siteId: this.state.siteId,
                hideEmpty: this.state.hideEmpty,
            }),
        });
        const saved = this.props.state || {};
        this.state.seasonId = saved.seasonId || false;
        this.state.siteId = saved.siteId || false;
        this.state.hideEmpty = saved.hideEmpty || false;
        onWillStart(() => this._loadData());
    }

    async _loadData() {
        const data = await this.orm.call("garden.bed", "get_occupancy_data", [
            this.props.action.domain || [],
            this.state.seasonId,
            this.state.siteId,
        ]);
        this.state.groups = data.groups || [];
        this.state.families = data.families || [];
        this.state.seasons = data.seasons || [];
        this.state.sites = data.sites || [];
        this.state.startDate = data.start_date || false;
        this.state.endDate = data.end_date || false;
        this.state.today = data.today || false;
    }

    async onFilterChange(field, ev) {
        const value = parseInt(ev.target.value, 10);
        this.state[field] = value || false;
        await this._loadData();
    }

    onHideEmptyChange(ev) {
        this.state.hideEmpty = ev.target.checked;
    }

    _ts(value) {
        return value ? new Date(value).getTime() : 0;
    }

    /** Bornes affichées : du 1er du mois de début à la fin du mois de fin. */
    get range() {
        const start = new Date(this._ts(this.state.startDate));
        const end = new Date(this._ts(this.state.endDate));
        const from = Date.UTC(start.getUTCFullYear(), start.getUTCMonth(), 1);
        const to = Date.UTC(end.getUTCFullYear(), end.getUTCMonth() + 1, 1);
        return { from, to, span: Math.max(to - from, DAY) };
    }

    get months() {
        const { from, to, span } = this.range;
        const months = [];
        const cursor = new Date(from);
        while (cursor.getTime() < to) {
            const next = Date.UTC(cursor.getUTCFullYear(), cursor.getUTCMonth() + 1, 1);
            months.push({
                key: cursor.getTime(),
                label: cursor.toLocaleDateString(undefined, {
                    month: "short",
                    year: "2-digit",
                    timeZone: "UTC",
                }),
                left: ((cursor.getTime() - from) / span) * 100,
                width: ((next - cursor.getTime()) / span) * 100,
            });
            cursor.setTime(next);
        }
        return months;
    }

    get visibleGroups() {
        return this.state.groups
            .map((group) => ({
                ...group,
                beds: group.beds.filter((bed) => !this.state.hideEmpty || bed.crops.length),
            }))
            .filter((group) => group.beds.length);
    }

    get todayStyle() {
        const { from, span } = this.range;
        const left = ((this._ts(this.state.today) - from) / span) * 100;
        return left >= 0 && left <= 100 ? `left: ${left}%;` : "display: none;";
    }

    rowStyle(bed) {
        return `height: ${bed.lanes * LANE_HEIGHT}px;`;
    }

    /** Style d'une barre entre deux dates ; `row` = 0 (prévu) ou 1 (réalisé). */
    barStyle(crop, kind) {
        const start = kind === "planned" ? crop.planned_start : crop.real_start;
        const end = kind === "planned" ? crop.planned_end || crop.planned_start : crop.real_end || crop.real_start;
        if (!start) {
            return "display: none;";
        }
        const { from, span } = this.range;
        const left = ((this._ts(start) - from) / span) * 100;
        const width = Math.max(((this._ts(end) - this._ts(start) + DAY) / span) * 100, 0.4);
        const top = crop.lane * LANE_HEIGHT + (kind === "planned" ? 3 : 19);
        return `left: ${left}%; width: ${width}%; top: ${top}px;`;
    }

    barTitle(crop) {
        const parts = [
            `${crop.name} — ${crop.label}`,
            `${crop.family_label} · ${crop.state_label} · ${crop.share}%`,
            _t("Expected: %(start)s → %(end)s", {
                start: this.formatDate(crop.planned_start),
                end: this.formatDate(crop.planned_end),
            }),
        ];
        if (crop.real_start) {
            parts.push(_t("Actual: %(start)s → %(end)s", {
                start: this.formatDate(crop.real_start),
                end: this.formatDate(crop.real_end),
            }));
        }
        return parts.concat(crop.warnings).join("\n");
    }

    openCrop(crop) {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "garden.crop",
            res_id: crop.id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    formatDate(date) {
        if (!date) {
            return "-";
        }
        return new Date(date).toLocaleDateString(undefined, {
            year: "numeric",
            month: "short",
            day: "numeric",
            timeZone: "UTC",
        });
    }
}

registry.category("actions").add("garden_bed_occupancy", GardenBedOccupancyAction);
