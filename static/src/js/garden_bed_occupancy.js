import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { useSetupAction } from "@web/search/action_hook";
import { registry } from "@web/core/registry";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

class GardenBedOccupancyAction extends Component {
    static template = "garden.GardenBedOccupancy";
    static components = { Layout };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.state = useState({ beds: [], startDate: false, endDate: false });
        useSetupAction({
            getLocalState: () => ({
                beds: this.state.beds,
                startDate: this.state.startDate,
                endDate: this.state.endDate,
            }),
        });
        onWillStart(this._loadData.bind(this));
    }

    async _loadData() {
        const data = await this.orm.call("garden.bed", "get_occupancy_data", [this.props.action.context || {}]);
        this.state.beds = data.beds || [];
        this.state.startDate = data.start_date || false;
        this.state.endDate = data.end_date || false;
    }

    _toTimestamp(value) {
        return value ? new Date(value).getTime() : 0;
    }

    _range() {
        const start = this._toTimestamp(this.state.startDate);
        const end = this._toTimestamp(this.state.endDate) || start;
        return { start, end, diff: Math.max(end - start, 1) };
    }

    getBarStyle(crop) {
        const range = this._range();
        const cropStart = this._toTimestamp(crop.date_start);
        const cropEnd = this._toTimestamp(crop.date_end || crop.date_start);
        const left = ((cropStart - range.start) / range.diff) * 100;
        const width = ((Math.max(cropEnd, cropStart) - cropStart) / range.diff) * 100;
        return `left: ${Math.max(Math.min(left, 100), 0)}%; width: ${Math.max(Math.min(width, 100 - left), 1)}%;`;
    }

    getTickStyle(position) {
        return position === 0 ? "left: 0%;" : "left: 100%; transform: translateX(-100%);";
    }

    formatDate(date) {
        if (!date) {
            return "-";
        }
        const parsed = new Date(date);
        return parsed.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
    }
}

registry.category("actions").add("garden_bed_occupancy", GardenBedOccupancyAction);
