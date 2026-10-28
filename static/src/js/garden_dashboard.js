import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { registry } from "@web/core/registry";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

/**
 * Tableau de bord de rentabilité (gérant) : barres en OWL pur, sans librairie externe.
 * Les données viennent de `garden.crop.profitability.get_dashboard_data()`.
 */
class GardenDashboardAction extends Component {
    static template = "garden.GardenDashboard";
    static components = { Layout };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.state = useState({ data: null });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.data = await this.orm.call("garden.crop.profitability", "get_dashboard_data", []);
    }

    async onRefresh() {
        await this.load();
    }

    /** Largeur (%) d'une barre ; les valeurs négatives s'affichent en rouge avec la même échelle. */
    barWidth(rows, value) {
        const max = Math.max(...rows.map((r) => Math.abs(r.value)), 0);
        return max ? Math.round((Math.abs(value) / max) * 100) : 0;
    }

    format(value) {
        return (value || 0).toLocaleString(undefined, { maximumFractionDigits: 2 });
    }

    openCrop(row) {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "garden.crop",
            res_id: row.id,
            views: [[false, "form"]],
        });
    }
}

registry.category("actions").add("garden_dashboard", GardenDashboardAction);
