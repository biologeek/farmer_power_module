import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { useSetupAction } from "@web/search/action_hook";
import { registry } from "@web/core/registry";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

class GardenStatisticsAction extends Component {
    static template = "garden.GardenStatistics";
    static components = { Layout };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.state = useState({ pie: [], stacked: { categories: [], series: [] } });
        useSetupAction({
            getLocalState: () => ({ pie: this.state.pie, stacked: this.state.stacked }),
        });
        onWillStart(this._loadData.bind(this));
    }

    async _loadData() {
        const data = await this.orm.call("garden.operation", "get_statistics_data", [this.props.action.context || {}]);
        this.state.pie = data.pie || [];
        this.state.stacked = data.stacked || { categories: [], series: [] };
        // render charts after DOM update
        setTimeout(() => this._renderCharts(), 50);
    }

    _renderCharts() {
        try {
            if (window.Chart && this.state.pie.length) {
                const ctx = document.getElementById('garden-pie-chart');
                if (ctx) {
                    const labels = this.state.pie.map(p => p.label);
                    const data = this.state.pie.map(p => p.value);
                    const pieColors = this._palette(labels.length);
                    new Chart(ctx.getContext('2d'), {
                        type: 'pie',
                        data: { labels, datasets: [{ data, backgroundColor: pieColors, borderColor: pieColors.map(() => '#ffffff'), borderWidth: 1 }] },
                        options: { responsive: true },
                    });
                }
            }

            if (window.Chart && this.state.stacked.series.length) {
                const ctx = document.getElementById('garden-stacked-chart');
                if (ctx) {
                    const labels = this.state.stacked.categories || [];
                    const palette = this._palette(this.state.stacked.series.length || 1);
                    const datasets = this.state.stacked.series.map((s, idx) => ({
                        label: s.name,
                        data: s.data,
                        backgroundColor: palette[idx] || palette[0],
                    }));
                    new Chart(ctx.getContext('2d'), {
                        type: 'bar',
                        data: { labels, datasets },
                        options: { scales: { x: { stacked: true }, y: { stacked: true } } },
                    });
                }
            }
        } catch (err) {
            console.error('Error rendering garden statistics charts', err);
        }
    }

    _palette(n) {
        // simple color palette generator
        const base = [
            '#4dc9f6', '#f67019', '#f53794', '#537bc4', '#acc236', '#166a8f', '#00a950', '#58595b', '#8549ba'
        ];
        if (n <= base.length) return base.slice(0, n);
        const out = [];
        for (let i = 0; i < n; i++) out.push(base[i % base.length]);
        return out;
    }
}

class GardenProductionStatisticsAction extends Component {
    static template = "garden.GardenProductionStatistics";
    static components = { Layout };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.state = useState({ month_totals: [], bed_totals: [], crop_totals: [] });
        useSetupAction({
            getLocalState: () => ({ month_totals: this.state.month_totals, bed_totals: this.state.bed_totals, crop_totals: this.state.crop_totals }),
        });
        onWillStart(this._loadData.bind(this));
    }

    async _loadData() {
        const data = await this.orm.call("garden.crop", "get_production_statistics_data", [this.props.action.context || {}]);
        this.state.month_totals = data.month_totals || [];
        this.state.bed_totals = data.bed_totals || [];
        this.state.crop_totals = data.crop_totals || [];
    }
}

registry.category('actions').add('garden_statistics', GardenStatisticsAction);
registry.category('actions').add('garden_production_statistics', GardenProductionStatisticsAction);
